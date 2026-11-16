"""Opt-in local C15 engine; only injected disposable DB and Storage adapters.

No environment connection factory, scheduler or real Storage implementation is
provided. The migration deliberately grants no application principal access.
"""

import hashlib
import json
import secrets
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import sql

from app.privacy_registry import (
    CLEANUP_ORDER,
    CONTENT,
    EXCLUSIONS,
    PRIVATE_LIFECYCLE,
    PROFILE_FIELDS,
    RETAINED,
    SAFE_METADATA,
    VERSION,
    project_result,
)


class ContentBlocked(Exception):
    """Safe reason only; never carries row/provider content."""


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 1024**3
    max_entries: int = 10_000
    max_row_bytes: int = 1024**2

    def __post_init__(self):
        if self.max_bytes < 1 or self.max_entries < 1 or self.max_row_bytes < 1:
            raise ValueError("positive export limits required")


def owned_key(account, key):
    """Exact UUID namespace, no normalization, traversal, URL or guessed prefix."""
    parts = key.split("/")
    if (
        len(parts) < 3
        or parts[0] != str(UUID(account))
        or any(p in ("", ".", "..") for p in parts)
        or any(c in key for c in ("\\", "\x00", ":", "?", "#", "%"))
        or any(ord(c) < 32 or ord(c) == 127 for c in key)
        or len(key) > 2048
    ):
        raise ContentBlocked("object_ownership_ambiguous")
    return key


class ContentEngine:
    def __init__(
        self,
        connect,
        storage,
        *,
        local_rehearsal=False,
        limits=None,
        credential_connect=None,
    ):
        self.credential_connect = credential_connect
        if not local_rehearsal:
            raise ContentBlocked("production_activation_disabled")
        self.connect, self.storage = connect, storage
        self.limits = limits or Limits()

    def download_presence(self, user, job_id, box):
        from app.privacy_otp import matches

        if box is None:
            raise ContentBlocked("fresh_export_proof_required")
        document = {
            "request_id": str(job_id),
            "session_id": str(UUID((user.claims or {})["session_id"])),
            "verified_email": user.email,
            "purpose": ":export.v1",
        }
        hashed = matches(box, user.user_id, document)
        with self.transaction() as c:
            self.lock(c, user.user_id)
            c.execute(
                "select otp_version,email_fingerprint from privacy_export_proofs where account_id=%s and request_id=%s and session_id=%s and verified_at>clock_timestamp()-interval '5 minutes' and expires_at>clock_timestamp()",
                (user.user_id, job_id, document["session_id"]),
            )
            row = c.fetchone()
            if not row or row[1] != hashed["email_fingerprints"].get(row[0]):
                raise ContentBlocked("fresh_export_proof_required")

    def proof(
        self,
        user,
        request_id,
        action,
        *,
        box=None,
        code="",
        sender=None,
        operation_scope="export",
        resource=None,
    ):
        """Separate export receipt: never accepts a deletion OTP or Google SSO."""
        from app.privacy import recent_presence
        from app.privacy_otp import matches, reserve

        if operation_scope not in {"export", "session", "history"} or (
            operation_scope == "session"
        ) != (resource is not None):
            raise ContentBlocked("invalid_scope")
        resource = str(UUID(resource)) if resource is not None else None
        if action == "download_begin" and operation_scope != "export":
            raise ContentBlocked("invalid_scope")
        account = str(UUID(user.user_id))
        session = str(UUID((user.claims or {})["session_id"]))
        request_id = str(UUID(request_id))
        rejected = False
        with self.transaction() as c:
            self.lock(c, account)
            if action == "download_begin":
                c.execute(
                    "select 1 from privacy_content_jobs where account_id=%s and id=%s and kind='export' and state='ready' and expires_at>clock_timestamp()",
                    (account, request_id),
                )
                if not c.fetchone():
                    raise ContentBlocked("download_unavailable")
                c.execute(
                    "update privacy_export_proofs set session_id=%s,started_at=clock_timestamp(),expires_at=clock_timestamp()+interval '5 minutes',otp_hash=null,verified_at=null,consumed_at=null where account_id=%s and request_id=%s",
                    (session, account, request_id),
                )
            if action == "begin":
                c.execute(
                    "select count(*) from privacy_export_proofs where account_id=%s and started_at>clock_timestamp()-interval '1 hour'",
                    (account,),
                )
                if c.fetchone()[0] >= 10:
                    raise ContentBlocked("export_request_rate_limited")
                c.execute(
                    "insert into privacy_export_proofs(request_id,account_id,session_id,operation_scope,resource_id) values(%s,%s,%s,%s,%s) on conflict do nothing",
                    (request_id, account, session, operation_scope, resource),
                )
            c.execute(
                "select started_at,expires_at,session_id,otp_hash,otp_version,email_fingerprint,sent_at,attempts,verified_at,consumed_at,clock_timestamp(),operation_scope,resource_id from privacy_export_proofs where request_id=%s and account_id=%s for update",
                (request_id, account),
            )
            row = c.fetchone()
            if row and (
                row[11] != operation_scope or str(row[12] or "") != str(resource or "")
            ):
                raise ContentBlocked("proof_scope_mismatch")
            if operation_scope == "session" and row and row[9] is None:
                c.execute(
                    "select 1 from interview_sessions where id=%s and user_id=%s",
                    (resource, account),
                )
                if not c.fetchone():
                    raise ContentBlocked("scope_unavailable")
            password_confirmation = (
                action == "confirm"
                and (user.claims or {}).get("c15_auth_method") == "password"
            )
            if not row or (str(row[2]) != session and not password_confirmation):
                raise ContentBlocked("export_proof_unavailable")
            if row[9] is not None:
                if action == "confirm":
                    c.execute(
                        "select 1 from privacy_content_jobs where id=%s and account_id=%s",
                        (request_id, account),
                    )
                    if c.fetchone():
                        return {"state": "requested", "request_id": request_id}
                raise ContentBlocked("export_proof_consumed")
            if row[1] <= row[10]:
                raise ContentBlocked("export_proof_expired")
            document = {
                "request_id": request_id,
                "session_id": session,
                "verified_email": user.email,
                "purpose": (
                    ":export.v1"
                    if operation_scope == "export"
                    else ":" + operation_scope + ".erase.v1"
                ),
            }
            if action == "otp_start":
                providers = (
                    (user.claims or {}).get("app_metadata", {}).get("providers", [])
                )
                if (
                    "google" not in providers
                    or "email" in providers
                    or box is None
                    or sender is None
                ):
                    raise ContentBlocked("export_mailbox_unavailable")
                c.execute(
                    "select count(*) filter(where sent_at>clock_timestamp()-interval '1 hour'),count(*) filter(where sent_at>clock_timestamp()-interval '1 day') from privacy_export_otp_sends where account_id=%s",
                    (account,),
                )
                hour, day = c.fetchone()
                if (
                    (row[6] and (row[10] - row[6]).total_seconds() < 60)
                    or hour >= 3
                    or day >= 10
                ):
                    raise ContentBlocked("export_otp_rate_limited")
                code, reserved = reserve(box, account, document)
                c.execute(
                    "insert into privacy_export_otp_sends(account_id) values(%s)",
                    (account,),
                )
                c.execute(
                    "update privacy_export_proofs set otp_hash=%s,otp_version=%s,email_fingerprint=%s,sent_at=clock_timestamp(),verified_at=null,attempts=0 where request_id=%s",
                    (
                        reserved["otp_hash"],
                        reserved["otp_key_version"],
                        reserved["email_fingerprint"],
                        request_id,
                    ),
                )
            elif action == "otp_verify":
                if box is None or row[7] >= 5 or row[8] is not None:
                    raise ContentBlocked("export_otp_unavailable")
                hashed = matches(box, account, document, code)
                valid = (
                    row[3] is not None
                    and secrets.compare_digest(
                        row[3], hashed["otp_hashes"].get(row[4], "")
                    )
                    and row[5] == hashed["email_fingerprints"].get(row[4])
                )
                c.execute(
                    "update privacy_export_proofs set attempts=attempts+1,verified_at=case when %s then clock_timestamp() else null end,otp_hash=case when %s then null else otp_hash end where request_id=%s",
                    (valid, valid, request_id),
                )
                rejected = not valid
            elif action == "confirm":
                if row[8] is None:
                    _, at = recent_presence(user)
                    from datetime import datetime

                    if datetime.fromisoformat(at) < row[0]:
                        raise ContentBlocked("fresh_export_proof_required")
                else:
                    if box is None or row[5] != matches(box, account, document)[
                        "email_fingerprints"
                    ].get(row[4]):
                        raise ContentBlocked("export_mailbox_changed")
                # Snapshot and proof consumption share one account-locked TX.
                c.execute(
                    "select state from privacy_content_jobs where id=%s and account_id=%s",
                    (request_id, account),
                )
                existing = c.fetchone()
                if not existing:
                    self._request_in_transaction(
                        c, account, request_id, operation_scope, resource
                    )
                elif existing[0] != "ready":
                    raise ContentBlocked("download_unavailable")
                c.execute(
                    "update privacy_export_proofs set consumed_at=clock_timestamp(),otp_hash=null,session_id=%s where request_id=%s",
                    (session, request_id),
                )
                c.execute(
                    "insert into privacy_lifecycle_audit(request_id,action) values(%s,'export.confirmed')",
                    (request_id,),
                )
            elif action not in {"begin", "download_begin"}:
                raise ContentBlocked("invalid_action")
        if rejected:
            raise ContentBlocked("export_otp_rejected")
        if action == "otp_start":
            # Reservation remains committed if delivery fails. No real sender
            # is supplied by application composition in this stage.
            sender(user.email, code)
        return {
            "state": (
                "requested"
                if action == "confirm"
                else (
                    "proof_pending"
                    if action == "begin"
                    else (
                        "mailbox_verified"
                        if action == "otp_verify"
                        else "code_requested"
                    )
                )
            ),
            "request_id": request_id,
            # Auth AMR timestamps have whole-second precision. Presence must
            # follow the operation, not merely share its truncated second.
            "not_before": int(row[0].timestamp()) + 1,
        }

    @contextmanager
    def transaction(self):
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute("set local statement_timeout='15s'")
            cursor.execute("set local lock_timeout='5s'")
            yield cursor

    @staticmethod
    def lock(cursor, account, *, restricted=False):
        cursor.execute("select to_regclass('public.privacy_restore_state') is not null")
        if cursor.fetchone()[0]:
            cursor.execute("select public.privacy_restore_accessible()")
            if not cursor.fetchone()[0]:
                raise ContentBlocked("restore_quarantined")
            if not restricted:
                cursor.execute(
                    "select 1 from privacy_restored_subjects where account_id=%s",
                    (account,),
                )
                if cursor.fetchone():
                    raise ContentBlocked("account_restricted")
        cursor.execute(
            "select id from auth.users where id=%s for no key update", (account,)
        )
        if not cursor.fetchone():
            raise ContentBlocked("account_unavailable")
        cursor.execute(
            "select 1 from public.subscription_deletion_jobs where account_id=%s",
            (account,),
        )
        if cursor.fetchone() and not restricted:
            raise ContentBlocked("account_restricted")
        if not restricted:
            cursor.execute(
                "select public.privacy_email_denied(email) from auth.users where id=%s",
                (account,),
            )
            if cursor.fetchone()[0]:
                raise ContentBlocked("account_restricted")

    @staticmethod
    def columns(cursor):
        cursor.execute(
            "select table_name,column_name from information_schema.columns where table_schema='public'"
        )
        result: dict[str, set[str]] = {}
        for table, column in cursor.fetchall():
            result.setdefault(table, set()).add(column)
        # Follow indirect children too: relying only on direct Auth FKs misses
        # result/replay/evidence stores behind session or ledger parents.
        cursor.execute(
            """with recursive linked(oid) as (
          select 'auth.users'::regclass::oid union
          select f.conrelid from pg_constraint f join linked p on p.oid=f.confrelid
          where f.contype='f'
        ) select c.relname from linked l join pg_class c on c.oid=l.oid
          join pg_namespace n on n.oid=c.relnamespace where n.nspname='public'"""
        )
        for (table,) in cursor.fetchall():
            result.setdefault(table, set()).add("__account_linked__")
        return result

    @staticmethod
    def coverage(columns):
        # Kept visible even when these are justified retention envelopes: their
        # complete field/retirement classification is not assumed by this stage.
        return sorted(
            t
            for t, c in columns.items()
            if ({"account_id", "user_id", "__account_linked__"} & c)
            and t not in CONTENT
            and t not in SAFE_METADATA
            and t not in RETAINED
            and t not in PRIVATE_LIFECYCLE
        )

    @staticmethod
    def row(job):
        return dict(
            zip(
                (
                    "id",
                    "account",
                    "kind",
                    "resource",
                    "state",
                    "lease",
                    "artifact",
                    "progress",
                    "blockers",
                ),
                job,
            )
        )

    def sessions(self, account, cursor=None):
        cursor = str(UUID(cursor)) if cursor is not None else None
        with self.transaction() as c:
            self.lock(c, account)
            c.execute(
                "select id,title from interview_sessions where user_id=%s and (%s::uuid is null or id>%s::uuid) order by id limit 201",
                (account, cursor, cursor),
            )
            rows = c.fetchall()
            return {
                "sessions": [
                    {"id": str(row[0]), "title": row[1]} for row in rows[:200]
                ],
                "next_cursor": str(rows[199][0]) if len(rows) > 200 else None,
            }

    def status(self, account, job_id):
        with self.transaction() as c:
            c.execute(
                "select state,revision,created_at,ready_at,expires_at,progress,blockers from privacy_content_jobs where account_id=%s and id=%s",
                (account, job_id),
            )
            row = c.fetchone()
            if not row:
                raise ContentBlocked("request_unavailable")
            c.execute("select clock_timestamp()")
            expired = row[4] is not None and row[4] <= c.fetchone()[0]
            return dict(
                zip(
                    (
                        "state",
                        "revision",
                        "created_at",
                        "ready_at",
                        "expires_at",
                        "progress",
                        "blockers",
                    ),
                    (("expired" if expired else row[0]), *row[1:]),
                )
            )

    def request(self, account, job_id, kind="export", resource=None):
        account, job_id = str(UUID(account)), str(UUID(job_id))
        if kind not in {"export", "session", "history", "account"}:
            raise ContentBlocked("invalid_scope")
        if (kind == "session") != (resource is not None):
            raise ContentBlocked("invalid_scope")
        with self.transaction() as c:
            return self._request_in_transaction(c, account, job_id, kind, resource)

    def _request_in_transaction(self, c, account, job_id, kind, resource):
        self.lock(c, account, restricted=kind == "account")
        if kind == "account":
            c.execute(
                "select request_id from privacy_deletion_requests where account_id=%s and state='accepted_restricted'",
                (account,),
            )
            accepted = c.fetchone()
            if not accepted or str(accepted[0]) != job_id:
                raise ContentBlocked("accepted_deletion_required")
        if kind == "session":
            c.execute(
                "select id from interview_sessions where user_id=%s and id=%s for update",
                (account, resource),
            )
            if not c.fetchone():
                raise ContentBlocked("scope_unavailable")
        c.execute(
            "select kind,resource_id from privacy_content_jobs where account_id=%s and id=%s",
            (account, job_id),
        )
        previous = c.fetchone()
        if previous:
            if previous[0] != kind or str(previous[1] or "") != str(resource or ""):
                raise ContentBlocked("idempotency_conflict")
            return job_id
        c.execute(
            "insert into privacy_content_jobs(id,account_id,kind,resource_id,registry_version,cutoff_at) values(%s,%s,%s,%s,%s,clock_timestamp())",
            (job_id, account, kind, resource, VERSION),
        )
        if kind == "export":
            self.snapshot(c, account, job_id)
        else:
            if kind == "history":
                self.history_dependencies(c, account, job_id)
            if kind in {"session", "history"}:
                c.execute(
                    "insert into privacy_erased_sessions(account_id,session_id,job_id) select user_id,id,%s from interview_sessions where user_id=%s and (%s::uuid is null or id=%s::uuid) on conflict do nothing",
                    (job_id, account, resource, resource),
                )
                c.execute(
                    "select public.privacy_capture_erasure_keys(%s,%s)",
                    (account, job_id),
                )
            c.execute(
                "update privacy_content_jobs set state='expired',capability_hash=null where account_id=%s and kind='export' and state in ('pending','running','ready')",
                (account,),
            )
            if kind == "account":
                c.execute(
                    "insert into privacy_content_objects(job_id,bucket,object_key) select %s,'resumes',storage_path from resumes where user_id=%s on conflict do nothing",
                    (job_id, account),
                )
        c.execute(
            "insert into privacy_lifecycle_audit(request_id,action) values(%s,%s)",
            (
                job_id,
                "export.requested" if kind == "export" else "content.scope_accepted",
            ),
        )
        return job_id

    @staticmethod
    def history_dependencies(c, account, job_id):
        c.execute(
            "select 1 from privacy_erased_sessions e join privacy_content_jobs owner on owner.id=e.job_id join interview_sessions s on s.id=e.session_id and s.user_id=e.account_id join privacy_content_jobs requested on requested.id=%s and requested.account_id=e.account_id where e.account_id=%s and owner.id<>requested.id and owner.state<>'primary_verified' and s.created_at<=requested.cutoff_at limit 1",
            (job_id, account),
        )
        if c.fetchone():
            raise ContentBlocked("previous_session_cleanup_pending")

    def snapshot(self, c, account, job_id):
        from app.privacy_schema import validate_schema

        validate_schema(c)
        columns = self.columns(c)
        unknown = self.coverage(columns)
        # Unknown categories are an explicit blocker, not silently omitted.
        if unknown:
            raise ContentBlocked("unclassified_tables:" + ",".join(unknown))
        statements = [
            sql.SQL(
                "select 'auth_identity'::text,jsonb_build_object('id',id,'email',email,'email_confirmed_at',email_confirmed_at) from auth.users where id=%s"
            )
        ]
        parameters = [account]
        for table, (owner, session_column, field_names) in (
            CONTENT | SAFE_METADATA
        ).items():
            if table not in columns:
                continue
            if session_column and table != "interview_sessions":
                c.execute(
                    sql.SQL(
                        "select 1 from public.{} t where t.{}=%s and t.{} is not null and not exists(select 1 from interview_sessions s where s.id=t.{} and s.user_id=%s) limit 1"
                    ).format(
                        sql.Identifier(table),
                        sql.Identifier(owner),
                        sql.Identifier(session_column),
                        sql.Identifier(session_column),
                    ),
                    (account, account),
                )
                if c.fetchone():
                    raise ContentBlocked("nested_resource_owner_mismatch:" + table)
            if table == "resume_chunks":
                c.execute(
                    "select 1 from resume_chunks c where c.user_id=%s and not exists(select 1 from resumes r where r.id=c.resume_id and r.user_id=%s) limit 1",
                    (account, account),
                )
                if c.fetchone():
                    raise ContentBlocked("nested_resource_owner_mismatch:resume_chunks")
            fields = [f for f in field_names.split() if f in columns[table]]
            if not fields:
                continue
            projection = sql.SQL(",").join(
                part
                for field in fields
                for part in (sql.Literal(field), sql.Identifier(field))
            )
            statements.append(
                sql.SQL(
                    "select {}::text,jsonb_build_object({}) from public.{} where {}=%s"
                ).format(
                    sql.Literal(table),
                    projection,
                    sql.Identifier(table),
                    sql.Identifier(owner),
                )
            )
            parameters.append(account)
        # One SQL statement gives all categories one database snapshot. A named
        # cursor bounds Python memory; writes use the same account-locked TX.
        c.execute(
            "update privacy_content_jobs set cutoff_at=clock_timestamp() where id=%s",
            (job_id,),
        )
        count, size = 0, 0
        with c.connection.cursor(name="c15_snapshot") as source:
            source.execute(
                sql.SQL(
                    "select category,case when octet_length(document::text)>%s then null else document end from ({}) as snapshot_rows(category,document)"
                ).format(sql.SQL(" union all ").join(statements)),
                [min(self.limits.max_row_bytes, self.limits.max_bytes), *parameters],
            )
            while rows := source.fetchmany(16):
                for table, item in rows:
                    if item is None:
                        raise ContentBlocked(
                            "export_row_limit_exceeded_no_archive_published"
                        )
                    if table == "user_settings":
                        from app.privacy_settings import public_settings

                        for setting in ("overlay_settings", "notification_preferences"):
                            if setting in item:
                                item[setting] = public_settings(item[setting])
                    if table == "job_contexts" and "source_file_metadata" in item:
                        from app.privacy_settings import job_metadata

                        item["source_file_metadata"] = job_metadata(
                            item["source_file_metadata"]
                        )
                    if isinstance(item.get("confirmed_profile"), dict):
                        item["confirmed_profile"] = {
                            k: v
                            for k, v in item["confirmed_profile"].items()
                            if k in PROFILE_FIELDS
                        }
                    for key in ("response", "result"):
                        if key in item:
                            item[key] = project_result(item[key])
                    document = json.dumps(item, default=str)
                    count += 1
                    size += len(document.encode())
                    if count > self.limits.max_entries or size > self.limits.max_bytes:
                        raise ContentBlocked(
                            "export_limit_exceeded_no_archive_published"
                        )
                    c.execute(
                        "insert into privacy_export_rows(job_id,category,document) values(%s,%s,%s::jsonb)",
                        (job_id, table, document),
                    )
        c.execute(
            "insert into privacy_content_objects(job_id,bucket,object_key,source_id,original_name) select %s,'resumes',storage_path,id,original_filename from resumes where user_id=%s on conflict do nothing",
            (job_id, account),
        )
        c.execute(
            "select object_key from privacy_content_objects where job_id=%s and bucket='resumes'",
            (job_id,),
        )
        for (key,) in c.fetchall():
            owned_key(str(account), key)
            version = self.storage.stat("resumes", key)
            if version is None:
                raise ContentBlocked("resume_file_missing")
            c.execute(
                "update privacy_content_objects set version=%s where job_id=%s and bucket='resumes' and object_key=%s",
                (version, job_id, key),
            )

    def claim(self):
        lease = str(uuid4())
        with self.transaction() as c:
            c.execute(
                "update privacy_content_jobs set state='failed',lease_id=null,revision=revision+1 where state='running' and lease_until<clock_timestamp() and attempts>=5"
            )
            c.execute(
                """update privacy_content_jobs set state='running',lease_id=%s,
             lease_until=clock_timestamp()+interval '30 seconds',attempts=attempts+1,revision=revision+1
             where id=(select id from privacy_content_jobs where
             (state='pending' or state='running' and lease_until<clock_timestamp())
             and retry_at<=clock_timestamp() and attempts<5 order by created_at for update skip locked limit 1)
             returning id,account_id,kind,resource_id,state,lease_id,artifact_key,progress,blockers""",
                (lease,),
            )
            row = c.fetchone()
            return self.row(row) if row else None

    def live(self, c, job, *, restrict=True):
        self.lock(c, job["account"], restricted=restrict)
        c.execute(
            "select 1 from privacy_content_jobs where id=%s and lease_id=%s and state='running' and lease_until>clock_timestamp() for update",
            (job["id"], job["lease"]),
        )
        if not c.fetchone():
            raise ContentBlocked("stale_worker")
        if hasattr(c, "scope"):
            c.scope(job)

    def run_one(self):
        job = self.claim()
        if not job:
            return False
        try:
            if job["kind"] == "export":
                self.build(job)
            else:
                self.cleanup(job)
        except PermissionError:
            self.finish(job, "blocked", ["storage_forbidden_not_absence"])
        except ContentBlocked as exc:
            if str(exc) != "stale_worker":
                self.finish(job, "blocked", [str(exc)])
        except Exception as error:  # noqa: BLE001 -- redact all external/driver errors
            # Storage/network errors never enter logs or status verbatim.
            import logging
            import traceback

            logging.getLogger("privacy").warning(
                "Content worker deferred: type=%s sqlstate=%s frames=%s",
                type(error).__name__,
                getattr(error, "sqlstate", None),
                [
                    (frame.name, frame.lineno)
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            )
            with self.transaction() as c:
                c.execute(
                    "update privacy_content_jobs set state=case when attempts>=5 then 'failed' else 'pending' end,retry_at=clock_timestamp()+least(300,power(2,attempts)::integer)*interval '1 second',lease_id=null where id=%s and lease_id=%s and state='running'",
                    (job["id"], job["lease"]),
                )
        return True

    def finish(self, job, state, blockers=None):
        with self.transaction() as c:
            self.live(c, job)
            if state == "primary_verified" and job["kind"] == "history":
                self.history_dependencies(c, job["account"], job["id"])
            c.execute(
                "update privacy_content_jobs set state=%s,blockers=%s::jsonb,lease_id=null,revision=revision+1 where id=%s",
                (state, json.dumps(blockers or []), job["id"]),
            )
            c.execute(
                "insert into privacy_lifecycle_audit(request_id,action) values(%s,%s)",
                (job["id"], "content." + state),
            )
            if job["kind"] == "account":
                c.execute(
                    "update privacy_followup_tasks set state=%s where request_id=%s and kind='personal_cleanup'",
                    (
                        "succeeded" if state == "primary_verified" else "blocked",
                        job["id"],
                    ),
                )

    LEASE_RENEW_INTERVAL = 5

    def renew(self, job):
        with self.transaction() as c:
            self.live(c, job, restrict=False)
            c.execute(
                "update privacy_content_jobs set lease_until=clock_timestamp()+interval '30 seconds' where id=%s and lease_id=%s and state='running'",
                (job["id"], job["lease"]),
            )

    @contextmanager
    def keep_lease(self, job):
        self.renew(job)
        stop = threading.Event()
        failures = []

        def heartbeat():
            while not stop.wait(self.LEASE_RENEW_INTERVAL):
                try:
                    self.renew(job)
                except Exception:  # noqa: BLE001 -- lost lease prevents publication
                    failures.append(True)
                    return

        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=20)
        if worker.is_alive() or failures:
            raise ContentBlocked("export_lease_unavailable")

    def build(self, job):
        with self.keep_lease(job):
            self._build(job)
        with self.transaction() as c:
            self.live(c, job, restrict=False)
            c.execute(
                "update privacy_content_jobs set state='ready',ready_at=clock_timestamp(),expires_at=clock_timestamp()+interval '24 hours',lease_id=null,revision=revision+1 where id=%s",
                (job["id"],),
            )

    def _build(self, job):
        account, job_id = str(job["account"]), str(job["id"])
        key = f"{account}/{job_id}/{job['lease']}.zip"
        # Record before put: a crash at either side leaves a removable artifact.
        with self.transaction() as c:
            self.live(c, job, restrict=False)
            c.execute(
                "update privacy_content_jobs set artifact_key=%s where id=%s",
                (key, job_id),
            )
            c.execute(
                "insert into privacy_content_objects(job_id,bucket,object_key) values(%s,'exports',%s) on conflict do nothing",
                (job_id, key),
            )
        with tempfile.TemporaryFile() as output:
            size, entries = 0, 1
            with zipfile.ZipFile(
                output, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                with self.transaction() as c:
                    c.execute(
                        "select cutoff_at from privacy_content_jobs where id=%s",
                        (job_id,),
                    )
                    cutoff = c.fetchone()[0]
                    c.execute(
                        "select object_key,version,source_id,original_name from privacy_content_objects where job_id=%s and bucket='resumes' order by object_key",
                        (job_id,),
                    )
                    files = c.fetchall()
                    manifest = json.dumps(
                        {
                            "version": VERSION,
                            "cutoff_at": str(cutoff),
                            "exclusions": EXCLUSIONS,
                            "expiry": "24 hours after ready",
                            "coverage": "registered primary stores only",
                            "included_categories": list(CONTENT | SAFE_METADATA),
                            "files": [
                                {
                                    "archive_path": f"files/resume-{index}.bin",
                                    "resume_id": str(source_id),
                                    "original_filename": name,
                                }
                                for index, (_, _, source_id, name) in enumerate(files)
                            ],
                        }
                    ).encode()
                    size += len(manifest)
                    archive.writestr("manifest.json", manifest)
                    if (
                        size > self.limits.max_bytes
                        or entries > self.limits.max_entries
                    ):
                        raise ContentBlocked(
                            "export_limit_exceeded_no_archive_published"
                        )
                    after = 0
                    while True:
                        c.execute(
                            "select ordinal,category,document from privacy_export_rows where job_id=%s and ordinal>%s order by ordinal limit 100",
                            (job_id, after),
                        )
                        rows = c.fetchall()
                        if not rows:
                            break
                        for ordinal, category, document in rows:
                            data = json.dumps(document, default=str).encode()
                            size += len(data)
                            entries += 1
                            if (
                                size > self.limits.max_bytes
                                or entries > self.limits.max_entries
                            ):
                                raise ContentBlocked(
                                    "export_limit_exceeded_no_archive_published"
                                )
                            archive.writestr(f"data/{category}/{ordinal}.json", data)
                            after = ordinal
                for index, (source, expected, _, _) in enumerate(files):
                    owned_key(account, source)
                    # Adapter must stream an authoritative, version-bound read.
                    before = self.storage.stat("resumes", source)
                    if before is None or before != expected:
                        raise ContentBlocked("resume_file_missing_or_changed")
                    entries += 1
                    if entries > self.limits.max_entries:
                        raise ContentBlocked(
                            "export_limit_exceeded_no_archive_published"
                        )
                    with archive.open(f"files/resume-{index}.bin", "w") as target:
                        for chunk in self.storage.read("resumes", source, before):
                            size += len(chunk)
                            if size > self.limits.max_bytes:
                                raise ContentBlocked(
                                    "export_limit_exceeded_no_archive_published"
                                )
                            target.write(chunk)
                    if self.storage.stat("resumes", source) != before:
                        raise ContentBlocked("resume_changed_during_export")
            output.seek(0)
            self.storage.put("exports", key, output)

    def authorize(self, account, job_id):
        token = secrets.token_urlsafe(32)
        with self.transaction() as c:
            self.lock(c, account)
            c.execute(
                "update privacy_content_jobs set capability_hash=%s,capability_expires_at=clock_timestamp()+interval '60 seconds' where id=%s and account_id=%s and state='ready' and expires_at>clock_timestamp() returning id",
                (hashlib.sha256(token.encode()).hexdigest(), job_id, account),
            )
            if not c.fetchone():
                raise ContentBlocked("download_unavailable")
        return token

    def download(self, account, job_id, token):
        with self.transaction() as c:
            self.lock(c, account)
            c.execute(
                "update privacy_content_jobs set capability_hash=null where id=%s and account_id=%s and state='ready' and expires_at>clock_timestamp() and capability_expires_at>clock_timestamp() and capability_hash=%s returning artifact_key",
                (job_id, account, hashlib.sha256(token.encode()).hexdigest()),
            )
            row = c.fetchone()
            if not row:
                raise ContentBlocked("download_unavailable")
        key = owned_key(str(account), row[0])
        version = self.storage.stat("exports", key)
        if version is None:
            raise ContentBlocked("artifact_missing")
        return self.deliver(account, job_id, key, version)

    def deliver(self, account, job_id, key, version):
        # Recheck between chunks. Previously delivered bytes cannot be recalled.
        for chunk in self.storage.read("exports", key, version):
            with self.transaction() as c:
                self.lock(c, account)
                c.execute(
                    "select 1 from privacy_content_jobs where id=%s and account_id=%s and state='ready' and expires_at>clock_timestamp()",
                    (job_id, account),
                )
                if not c.fetchone():
                    raise ContentBlocked("download_unavailable")
            yield chunk

    def queue_accepted(self):
        """Explicit local outbox intake; no configured production scheduler."""
        with self.transaction() as c:
            c.execute(
                "select r.account_id,r.request_id from privacy_deletion_requests r join privacy_followup_tasks t using(request_id) where r.state='accepted_restricted' and t.kind='personal_cleanup' and t.state='pending' and not exists(select 1 from privacy_content_jobs j where j.id=r.request_id) order by r.accepted_at limit 1"
            )
            row = c.fetchone()
        if row:
            self.request(str(row[0]), str(row[1]), "account")
        return bool(row)

    @staticmethod
    def retained_blockers(c, columns, account, exceptions=None):
        # Fixed ownership vocabulary, including indirect children. No caller
        # supplies identifiers/predicates. Empty or foreign rows do not prove a
        # private payload remains for this subject.
        owners = (
            "account_id",
            "user_id",
            "actor_subject",
            "reviewer_subject",
            "subject_id",
        )
        indirect = {
            "subscription_auto_replies": ("subscription_auto_runs", "run_id", "run_id"),
            "billing_evidence": ("billing_operations", "operation_id", "operation_id"),
            "billing_payable_quotes": (
                "billing_operations",
                "operation_id",
                "operation_id",
            ),
            "billing_email_delivery_events": (
                "billing_notification_sources",
                "source_id",
                "id",
            ),
        }
        blockers = []
        for table in sorted(RETAINED & columns.keys()):
            owned = [name for name in owners if name in columns[table]]
            if (
                table == "subscription_admin_permissions"
                and "approved_by" in columns[table]
            ):
                owned.append("approved_by")
            if owned:
                condition = sql.SQL(" or ").join(
                    sql.SQL("{}=%s").format(sql.Identifier(name)) for name in owned
                )
                c.execute(
                    sql.SQL("select exists(select 1 from {} where {})").format(
                        sql.Identifier(table), condition
                    ),
                    [account] * len(owned),
                )
            elif table in indirect:
                parent, child_key, parent_key = indirect[table]
                c.execute(
                    sql.SQL(
                        "select exists(select 1 from {} child join {} parent on child.{}=parent.{} where parent.account_id=%s)"
                    ).format(
                        sql.Identifier(table),
                        sql.Identifier(parent),
                        sql.Identifier(child_key),
                        sql.Identifier(parent_key),
                    ),
                    (account,),
                )
            else:
                blockers.append(table + ":retained_ownership_unverified")
                continue
            if c.fetchone()[0]:
                from app.privacy_retained import primary_safe

                category = primary_safe(c, table, account)
                if category is None:
                    blockers.append(
                        table + ":retained_payload_minimization_not_verified"
                    )
                elif exceptions is not None:
                    exceptions[table] = category
        return blockers

    def cleanup(self, job):
        blockers: list[str] = []
        with self.transaction() as c:
            credential_rpc = c.execute(
                "select to_regprocedure('public.privacy_auto_credentials_erase(uuid,uuid)') is not null"
            ).fetchone()[0]
            redaction_rpc = c.execute(
                "select to_regprocedure('public.privacy_redact_legacy_auto(uuid,uuid)') is not null"
            ).fetchone()[0]
        if job["kind"] == "account" and credential_rpc:
            if self.credential_connect is None:
                raise ContentBlocked("restricted_cleanup_principal_unavailable")
            from app.commercial.executor_connection import check_executor_identity

            with self.credential_connect() as connection:
                check_executor_identity(connection, "privacy_cleanup_executor")
                connection.execute(
                    "select public.privacy_auto_credentials_erase(%s,%s)",
                    (job["id"], job["lease"]),
                )
                if redaction_rpc:
                    connection.execute(
                        "select public.privacy_redact_legacy_auto(%s,%s)",
                        (job["id"], job["lease"]),
                    )
        with self.transaction() as c:
            has_minimizer = c.execute(
                "select to_regclass('public.privacy_minimized_records') is not null"
            ).fetchone()[0]
        if job["kind"] == "account" and has_minimizer:
            from app.privacy_remaining import Minimizer

            blockers.extend(Minimizer(self).run(job["account"], job=job)["blockers"])
        with self.transaction() as c:
            self.live(c, job)
            if (
                job["kind"] == "account"
                and c.execute(
                    "select to_regclass('public.privacy_auto_reply_payloads') is not null"
                ).fetchone()[0]
            ):
                if not credential_rpc:
                    c.execute(
                        "select public.privacy_auto_payload_erase(%s,%s)",
                        (job["id"], job["lease"]),
                    )
                c.execute(
                    "select 1 from privacy_auto_reply_payloads where account_id=%s and state='available' limit 1",
                    (job["account"],),
                )
                if c.fetchone():
                    raise ContentBlocked("auto_reply_payload_absence_unverified")
                c.execute(
                    "update privacy_content_jobs set progress=progress||jsonb_build_object('auto_reply_payloads','verified_erased') where id=%s",
                    (job["id"],),
                )
            from app.privacy_schema import validate_schema

            validate_schema(c)
            columns = self.columns(c)
            blockers.extend("unclassified_table:" + t for t in self.coverage(columns))
            if job["kind"] == "account":
                exceptions: dict[str, str] = {}
                blockers.extend(
                    self.retained_blockers(c, columns, job["account"], exceptions)
                )
                c.execute(
                    "update privacy_content_jobs set progress=progress||jsonb_build_object('retained_exceptions',%s::jsonb) where id=%s",
                    (json.dumps(exceptions), job["id"]),
                )
        for table in CLEANUP_ORDER:
            if table not in columns:
                continue
            owner, session, _ = CONTENT[table]
            if job["kind"] != "account" and session is None:
                if table == "subscription_notes_versions":
                    with self.transaction() as c:
                        self.live(c, job)
                        c.execute(
                            "select 1 from subscription_notes_versions v join usage_operations o using(operation_id) where v.account_id=%s and (o.account_id<>v.account_id or o.operation<>'notes.generate') limit 1",
                            (job["account"],),
                        )
                        if c.fetchone():
                            blockers.append(
                                "subscription_notes_versions:ambiguous_operation_owner"
                            )
                        else:
                            # notes.claim binds usage resource_id to its session
                            # in 20261024100000_subscription_auxiliary_execution.
                            c.execute(
                                "delete from subscription_notes_versions v using usage_operations o,privacy_erased_sessions e where v.operation_id=o.operation_id and o.operation='notes.generate' and v.account_id=%s and o.account_id=v.account_id and o.resource_id=e.session_id and e.job_id=%s and e.account_id=v.account_id",
                                (job["account"], job["id"]),
                            )
                            c.execute(
                                "select count(*) from subscription_notes_versions v join usage_operations o using(operation_id) join privacy_erased_sessions e on o.resource_id=e.session_id and e.account_id=v.account_id where v.account_id=%s and e.job_id=%s",
                                (job["account"], job["id"]),
                            )
                            if c.fetchone()[0]:
                                raise ContentBlocked(
                                    "notes_version_absence_not_verified"
                                )
                            c.execute(
                                "update privacy_content_jobs set progress=progress||jsonb_build_object('subscription_notes_versions','scope_verified_absent') where id=%s",
                                (job["id"],),
                            )
                continue
            with self.transaction() as c:
                self.live(c, job)
                predicate = sql.SQL("{}=%s").format(sql.Identifier(owner))
                params = [job["account"]]
                if table == "resumes":
                    c.execute(
                        "select 1 from usage_operations where account_id=%s and state in ('reserved','dispatched','checkpointed','uncertain') and lease_until>clock_timestamp() and resource_id in (select id from resumes where user_id=%s) limit 1",
                        (job["account"], job["account"]),
                    )
                    if c.fetchone():
                        blockers.append("resumes:active_processing_lease")
                        continue
                if job["kind"] == "session":
                    assert session is not None
                    predicate += sql.SQL(" and {}=%s").format(sql.Identifier(session))
                    params.append(job["resource"])
                elif job["kind"] == "history":
                    assert session is not None
                    predicate += sql.SQL(
                        " and {} in (select session_id from privacy_erased_sessions where job_id=%s and account_id=%s)"
                    ).format(sql.Identifier(session))
                    params.extend((job["id"], job["account"]))
                try:
                    with c.connection.transaction():
                        c.execute(
                            sql.SQL("delete from public.{} where {}").format(
                                sql.Identifier(table), predicate
                            ),
                            params,
                        )
                        c.execute(
                            sql.SQL("select count(*) from public.{} where {}").format(
                                sql.Identifier(table), predicate
                            ),
                            params,
                        )
                        if c.fetchone()[0]:
                            raise ContentBlocked("absence_not_verified")
                except (
                    Exception
                ) as exc:  # noqa: BLE001 -- savepoint preserves protections
                    # SQLSTATE identifies integrity/immutability blockers without
                    # exposing private SQL errors or bypassing any protection.
                    blockers.append(
                        table
                        + ":"
                        + (getattr(exc, "sqlstate", None) or "verification_blocked")
                    )
                    continue
                c.execute(
                    "update privacy_content_jobs set progress=progress||jsonb_build_object(%s::text,'verified_absent'),revision=revision+1 where id=%s",
                    (table, job["id"]),
                )
        if job["kind"] == "account":
            self.remove_objects(job)
            with self.transaction() as c:
                self.live(c, job)
                c.execute(
                    "select name from storage.objects where bucket_id='resumes' and split_part(name,'/',1)=%s limit 1",
                    (str(job["account"]),),
                )
                if c.fetchone():
                    raise ContentBlocked("resume_object_absence_not_verified")
        self.finish(job, "blocked" if blockers else "primary_verified", blockers)

    def remove_objects(self, job):
        with self.transaction() as c:
            self.live(c, job)
            c.execute(
                "select bucket,object_key from privacy_content_objects where job_id=%s and state<>'verified'",
                (job["id"],),
            )
            objects = c.fetchall()
        for bucket, key in objects:
            owned_key(str(job["account"]), key)
            # This manifest originated from owned rows before their deletion.
            # Shared references, live uploads and foreign keys fail closed.
            with self.transaction() as c:
                self.live(c, job)
                c.execute("select 1 from resumes where storage_path=%s", (key,))
                if c.fetchone():
                    raise ContentBlocked("file_reference_or_live_upload_remains")
                if self.storage.stat(bucket, key) is not None:
                    self.storage.remove(bucket, key)
                if self.storage.stat(bucket, key) is not None:
                    raise ContentBlocked("object_absence_not_verified")
                c.execute(
                    "update privacy_content_objects set state='verified' where job_id=%s and bucket=%s and object_key=%s",
                    (job["id"], bucket, key),
                )

    def expire_one(self):
        with self.transaction() as c:
            c.execute(
                "update privacy_export_proofs set otp_hash=null,email_fingerprint=null where expires_at<=clock_timestamp() and (otp_hash is not null or email_fingerprint is not null)"
            )
            c.execute(
                "delete from privacy_export_otp_sends where sent_at<=clock_timestamp()-interval '1 day'"
            )
            c.execute(
                "select id,account_id from privacy_content_jobs where kind='export' and retry_at<=clock_timestamp() and (state in ('blocked','failed','expired') or expires_at<=clock_timestamp() or exists(select 1 from subscription_deletion_jobs d where d.account_id=privacy_content_jobs.account_id)) and (exists(select 1 from privacy_content_objects o where o.job_id=privacy_content_jobs.id and o.bucket='exports') or exists(select 1 from privacy_export_rows r where r.job_id=privacy_content_jobs.id)) order by retry_at,created_at for update skip locked limit 1"
            )
            row = c.fetchone()
            if not row:
                return False
            job_id, account = row
            c.execute(
                "update privacy_content_jobs set state='expired',capability_hash=null where id=%s",
                (job_id,),
            )
            c.execute(
                "select object_key from privacy_content_objects where job_id=%s and bucket='exports'",
                (job_id,),
            )
            for (key,) in c.fetchall():
                owned_key(str(account), key)
                if self.storage.stat("exports", key) is not None:
                    self.storage.remove("exports", key)
                if self.storage.stat("exports", key) is not None:
                    raise ContentBlocked("object_absence_not_verified")
                c.execute(
                    "update privacy_content_objects set state='verified' where job_id=%s and bucket='exports' and object_key=%s",
                    (job_id, key),
                )
            c.execute("delete from privacy_export_rows where job_id=%s", (job_id,))
            # Reconcile invalid artifacts repeatedly: a timed-out old put may
            # complete after an earlier absence check. Never reauthorize it.
            c.execute(
                "update privacy_content_jobs set retry_at=clock_timestamp()+interval '30 seconds' where id=%s",
                (job_id,),
            )
        return True

    def retry(self, account, job_id):
        with self.transaction() as c:
            self.lock(c, account, restricted=True)
            c.execute(
                "update privacy_content_jobs set state='pending',retry_at=clock_timestamp(),revision=revision+1 where account_id=%s and id=%s and kind<>'export' and state in ('blocked','failed') and attempts<5 returning id",
                (account, job_id),
            )
            if not c.fetchone():
                raise ContentBlocked("retry_unavailable")
