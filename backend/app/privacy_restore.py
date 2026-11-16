"""Encrypted external evidence and an explicit fail-closed local restore gate.

The key ring AND expected checkpoint must be supplied outside the restored DB.
No backup discovery, remote restore, credential loading or scheduler is provided.
"""

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql

from app.privacy_content import ContentBlocked
from app.privacy_registry import CLEANUP_ORDER, CONTENT, VERSION

FIELDS = (
    "account_id",
    "request_id",
    "session_id",
    "reauthenticated_at",
    "policy_version",
    "scope",
    "confirmation_hash",
    "status_hash",
    "email_key_version",
    "email_digest",
    "state",
    "revision",
    "created_at",
    "expires_at",
    "status_expires_at",
    "accepted_at",
    "primary_cleanup_target_at",
    "usage_retention_until",
    "security_retention_until",
)


class RestoreJournal:
    def __init__(self, path, keys, current):
        self.path = Path(path)
        if current not in keys or any(len(k) != 32 for k in keys.values()):
            raise ContentBlocked("restore_key_unavailable")
        self.keys, self.current = keys, current

    def initialize(self):
        if self.path.is_symlink():
            raise ContentBlocked("restore_evidence_unavailable")
        with self.path.open("xb"):
            pass
        os.chmod(self.path, 0o600)
        return self.append(
            {"kind": "genesis", "event_id": "genesis"}, hashlib.sha256(b"").hexdigest()
        )

    def read(self, expected):
        try:
            if not expected or self.path.is_symlink():
                raise ValueError()
            raw = self.path.read_bytes()
            if (
                len(raw) > 16 * 1024 * 1024
                or hashlib.sha256(raw).hexdigest() != expected
            ):
                raise ValueError()
            previous = "genesis"
            result = []
            for index, line in enumerate(raw.splitlines(keepends=True)):
                if not line.endswith(b"\n"):
                    raise ValueError()
                outer = json.loads(line)
                aad = f"c15.restore.v1:{index}:{previous}".encode()
                clear = AESGCM(self.keys[outer["key_version"]]).decrypt(
                    base64.b64decode(outer["nonce"], validate=True),
                    base64.b64decode(outer["ciphertext"], validate=True),
                    aad,
                )
                result.append(json.loads(clear))
                previous = hashlib.sha256(line).hexdigest()
            return result
        except Exception:  # noqa: BLE001 -- no identifiers, ciphertext or keys in diagnostics
            raise ContentBlocked("restore_evidence_unavailable") from None

    def append(self, event, expected):
        records = self.read(expected)
        previous = "genesis"
        if records:
            raw = self.path.read_bytes().splitlines(keepends=True)
            previous = hashlib.sha256(raw[-1]).hexdigest()
        for existing in records:
            if existing["event_id"] == event["event_id"]:
                if existing != event:
                    raise ContentBlocked("restore_evidence_conflict")
                return expected
        data = json.dumps(event, sort_keys=True, default=str).encode()
        if len(data) > 1024 * 1024:
            raise ContentBlocked("restore_evidence_size")
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(self.keys[self.current]).encrypt(
            nonce, data, f"c15.restore.v1:{len(records)}:{previous}".encode()
        )
        line = (
            json.dumps(
                {
                    "key_version": self.current,
                    "nonce": base64.b64encode(nonce).decode(),
                    "ciphertext": base64.b64encode(encrypted).decode(),
                },
                sort_keys=True,
            ).encode()
            + b"\n"
        )
        with self.path.open("ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


class RestoreGate:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def matching_keys(c):
        c.execute("select version,secret from privacy_matching_keys order by version")
        return {
            str(version): hashlib.sha256(bytes(secret)).hexdigest()
            for version, secret in c.fetchall()
        }

    def publish(self, account, journal, expected, job_id=None):
        # Advisory lock serializes this DB's publishers; journal is a dedicated
        # external volume, never a path selected by a customer or restored SQL.
        with self.engine.transaction() as c:
            c.execute(
                "select pg_advisory_xact_lock(hashtextextended('c15.restore.publisher.v1',0))"
            )
            self.engine.lock(c, account, restricted=True)
            if job_id is not None:
                c.execute(
                    "select kind,resource_id,created_at from privacy_content_jobs where id=%s and account_id=%s and kind in ('session','history')",
                    (job_id, account),
                )
                job = c.fetchone()
                if not job:
                    raise ContentBlocked("restore_scope_unverified")
                c.execute(
                    "select session_id from privacy_erased_sessions where job_id=%s and account_id=%s order by session_id",
                    (job_id, account),
                )
                sessions = [str(r[0]) for r in c.fetchall()]
                c.execute(
                    "select key_version,encode(digest,'hex') from privacy_erased_session_keys where job_id=%s and account_id=%s order by key_version,digest",
                    (job_id, account),
                )
                keys = [{"version": v, "digest": d} for v, d in c.fetchall()]
                payload = {
                    "kind": "sessions",
                    "matching_keys": self.matching_keys(c),
                    "event_id": str(job_id),
                    "account": str(account),
                    "scope": job[0],
                    "resource": str(job[1]) if job[1] else None,
                    "created_at": str(job[2]),
                    "sessions": sessions,
                    "keys": keys,
                }
                checkpoint = journal.append(payload, expected)
                c.execute(
                    "update privacy_restore_outbox set checkpoint=%s where request_id=%s",
                    (checkpoint, job_id),
                )
                return checkpoint
            c.execute(
                "select "
                + ",".join(FIELDS)
                + " from privacy_deletion_requests where account_id=%s and state='accepted_restricted'",
                (account,),
            )
            row = c.fetchone()
            if not row:
                raise ContentBlocked("accepted_deletion_required")
            event = dict(zip(FIELDS, row))
            event["email_digest"] = bytes(event["email_digest"]).hex()
            event = json.loads(json.dumps(event, default=str))
            payload = {
                "kind": "account",
                "matching_keys": self.matching_keys(c),
                "event_id": event["request_id"],
                "request": event,
            }
            checkpoint = journal.append(payload, expected)
            c.execute(
                "update privacy_restore_outbox set checkpoint=%s where request_id=%s",
                (checkpoint, event["request_id"]),
            )
            return checkpoint

    def apply(self, journal, expected):
        # Persist quarantine BEFORE reading evidence, including on missing key,
        # corrupt/truncated evidence, old checkpoint or a replay transaction crash.
        with self.engine.transaction() as c:
            c.execute(
                "update privacy_restore_state set required=true,ready=false,checkpoint=null"
            )
        records = journal.read(expected)
        if not records or records[0] != {"kind": "genesis", "event_id": "genesis"}:
            raise ContentBlocked("restore_evidence_unavailable")
        with self.engine.transaction() as c:
            for record in records[1:]:
                current_keys = self.matching_keys(c)
                if not record.get("matching_keys") or any(
                    current_keys.get(version) != fingerprint
                    for version, fingerprint in record["matching_keys"].items()
                ):
                    raise ContentBlocked("restore_matching_key_unavailable")
                if record["kind"] == "sessions":
                    self._replay_sessions(c, record)
                    continue
                if record["kind"] != "account":
                    raise ContentBlocked("restore_scope_unverified")
                request = record["request"]
                account = str(UUID(request["account_id"]))
                req = str(UUID(request["request_id"]))
                c.execute(
                    "select 1 from privacy_matching_keys where version=%s",
                    (request["email_key_version"],),
                )
                if not c.fetchone():
                    raise ContentBlocked("restore_matching_key_unavailable")
                c.execute(
                    "insert into privacy_email_suppression(key_version,digest) values(%s,decode(%s,'hex')) on conflict do nothing",
                    (request["email_key_version"], request["email_digest"]),
                )
                c.execute(
                    "insert into privacy_restored_subjects(account_id,request_id) values(%s,%s) on conflict do nothing",
                    (account, req),
                )
                c.execute(
                    "select 1 from auth.users where id=%s for no key update", (account,)
                )
                if not c.fetchone():
                    continue  # no Auth/profile data to expose; external deny marker survives
                # Restore can revive a run that was active in the old snapshot.
                # Reuse account -> binding -> run -> slice lock/settlement order,
                # bounded by the independently witnessed acceptance time. A
                # restriction flag alone does not close its recovery credential.
                c.execute(
                    "select 1 from account_plan_bindings where account_id=%s for update",
                    (account,),
                )
                c.execute(
                    "select run_id from subscription_auto_runs where account_id=%s and active order by run_id for update",
                    (account,),
                )
                for (run,) in c.fetchall():
                    c.execute(
                        "select public.subscription_auto_finish_slice(%s,%s)",
                        (run, request["accepted_at"]),
                    )
                    c.execute(
                        "update subscription_auto_runs set active=false,fence=fence+1 where run_id=%s",
                        (run,),
                    )
                c.execute(
                    "delete from subscription_auth_handoffs where account_id=%s",
                    (account,),
                )
                c.execute(
                    "insert into subscription_deletion_jobs(account_id,request_id) values(%s,%s) on conflict do nothing",
                    (account, req),
                )
                values = [
                    bytes.fromhex(request[f]) if f == "email_digest" else request[f]
                    for f in FIELDS
                ]
                c.execute(
                    "select request_id,state,accepted_at,policy_version,email_key_version,email_digest from privacy_deletion_requests where account_id=%s",
                    (account,),
                )
                existing = c.fetchone()
                if (
                    existing
                    and existing[1] == "accepted_restricted"
                    and str(existing[0]) != req
                ):
                    raise ContentBlocked("restore_evidence_conflict")
                if (
                    existing
                    and existing[1] == "accepted_restricted"
                    and (
                        existing[2] != datetime.fromisoformat(request["accepted_at"])
                        or existing[3] != request["policy_version"]
                        or existing[4] != request["email_key_version"]
                        or bytes(existing[5]).hex() != request["email_digest"]
                    )
                ):
                    raise ContentBlocked("restore_evidence_conflict")
                if not existing:
                    c.execute(
                        "insert into privacy_deletion_requests("
                        + ",".join(FIELDS)
                        + ") values("
                        + ",".join(["%s"] * len(FIELDS))
                        + ")",
                        values,
                    )
                elif existing[1] != "accepted_restricted":
                    c.execute(
                        "update privacy_deletion_requests set "
                        + ",".join(f + "=%s" for f in FIELDS[1:])
                        + " where account_id=%s",
                        values[1:] + [account],
                    )
                c.execute(
                    "insert into privacy_followup_tasks(request_id,kind,due_at) values(%s,'personal_cleanup',%s),(%s,'billing_review',clock_timestamp()) on conflict do nothing",
                    (req, request["primary_cleanup_target_at"], req),
                )
                c.execute(
                    "insert into privacy_lifecycle_audit(request_id,action) select %s,'restore.restriction_replayed' where not exists(select 1 from privacy_lifecycle_audit where request_id=%s and action='restore.restriction_replayed')",
                    (req, req),
                )
            c.execute(
                "update privacy_restore_state set ready=true,checkpoint=%s", (expected,)
            )
        return {
            "state": "restrictions_replayed",
            "content_cleanup": "pending",
            "billing": "unverified",
        }

    def _replay_sessions(self, c, record):
        from app.privacy_schema import validate_schema

        validate_schema(c)
        account = str(UUID(record["account"]))
        request = str(UUID(record["event_id"]))
        sessions = [str(UUID(value)) for value in record["sessions"]]
        for session in sessions:
            c.execute(
                "insert into privacy_restored_sessions values(%s,%s) on conflict do nothing",
                (account, session),
            )
        for key in record["keys"]:
            c.execute(
                "insert into privacy_restored_replays values(%s,%s,decode(%s,'hex')) on conflict do nothing",
                (account, key["version"], key["digest"]),
            )
        c.execute("select 1 from auth.users where id=%s", (account,))
        if not c.fetchone():
            return
        c.execute(
            "insert into privacy_content_jobs(id,account_id,kind,resource_id,registry_version,state,created_at) values(%s,%s,%s,%s,%s,'pending',%s) on conflict do nothing",
            (
                request,
                account,
                record["scope"],
                record["resource"],
                VERSION,
                record["created_at"],
            ),
        )
        for session in sessions:
            c.execute(
                "insert into privacy_erased_sessions values(%s,%s,%s) on conflict do nothing",
                (account, session, request),
            )
        # Scope-linked email copies and accounting RESTRICT paths are left
        # quarantined rather than bypassed or assigned a new retention clock.
        c.execute(
            "select 1 from outbound_email_events where user_id=%s and session_id=any(%s::uuid[]) limit 1",
            (account, sessions),
        )
        if c.fetchone():
            raise ContentBlocked("restore_session_email_treatment_pending")
        c.execute(
            "delete from subscription_notes_versions v using usage_operations o where v.operation_id=o.operation_id and v.account_id=%s and o.account_id=v.account_id and o.operation='notes.generate' and o.resource_id=any(%s::uuid[])",
            (account, sessions),
        )
        for table in CLEANUP_ORDER:
            owner, session, _ = CONTENT[table]
            if session is None:
                continue
            c.execute(
                sql.SQL(
                    "delete from public.{} where {}=%s and {}=any(%s::uuid[])"
                ).format(
                    sql.Identifier(table),
                    sql.Identifier(owner),
                    sql.Identifier(session),
                ),
                (account, sessions),
            )
            c.execute(
                sql.SQL(
                    "select count(*) from public.{} where {}=%s and {}=any(%s::uuid[])"
                ).format(
                    sql.Identifier(table),
                    sql.Identifier(owner),
                    sql.Identifier(session),
                ),
                (account, sessions),
            )
            if c.fetchone()[0]:
                raise ContentBlocked("restore_scope_absence_unverified")
        c.execute(
            "update privacy_content_jobs set state='primary_verified' where id=%s",
            (request,),
        )
