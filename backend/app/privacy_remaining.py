"""Local-only minimization and category-scoped retention; no provider adapters."""

from datetime import timedelta
from uuid import uuid4

from app.privacy_content import ContentBlocked


class Minimizer:
    def __init__(self, engine):
        self.engine = engine

    def run(self, account, *, job=None):
        counts = {"email": 0, "relay": 0}
        blockers = []
        with self.engine.transaction() as c:
            self.engine.lock(c, account, restricted=True)
            if job is not None:
                if str(job["account"]) != str(account) or job["kind"] != "account":
                    raise ContentBlocked("cleanup_scope_mismatch")
                self.engine.live(c, job)
            c.execute(
                "select accepted_at from privacy_deletion_requests where account_id=%s and state='accepted_restricted'",
                (account,),
            )
            accepted = c.fetchone()
            if not accepted:
                raise ContentBlocked("accepted_deletion_required")
            c.execute(
                "select id,email_type,status,created_at from outbound_email_events where user_id=%s and email_type not like 'billing_%%' and status in ('pending','sent','failed','canceled','retry_blocked') and (email_type not like 'privacy_%%' or status<>'pending') for update",
                (account,),
            )
            for event, kind, status, occurred in c.fetchall():
                try:
                    with c.connection.transaction():
                        if kind in {
                            "welcome",
                            "ai_notes_ready",
                            "session_summary",
                            "transcript_export",
                            "marketing_product_update",
                        }:
                            # Owner-approved primary erasure: no replacement
                            # delivery envelope for ordinary nonfinancial mail.
                            c.execute(
                                "delete from outbound_email_events where id=%s and user_id=%s",
                                (event, account),
                            )
                            counts["email"] += 1
                            continue
                        category = (
                            "security_audit"
                            if kind == "account_security"
                            else "unapproved"
                        )
                        deadline = (
                            accepted[0] + timedelta(days=180)
                            if category == "security_audit"
                            else None
                        )
                        c.execute(
                            "insert into privacy_minimized_records(account_id,source_kind,source_id,category,event_kind,outcome,occurred_at,confirmation_at,eligible_at) values(%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
                            (
                                account,
                                "security_email"
                                if category == "security_audit"
                                else "ordinary_email",
                                event,
                                category,
                                kind,
                                status,
                                occurred,
                                accepted[0],
                                deadline,
                            ),
                        )
                        c.execute(
                            "delete from outbound_email_events where id=%s and user_id=%s",
                            (event, account),
                        )
                        counts["email"] += 1
                except Exception:  # noqa: BLE001 -- integrity failures stay blocked; no private driver text
                    blockers.append("outbound_email_events:integrity_dependency")
            c.execute(
                "select run_id,source,last_sequence,created_at from subscription_relay_frames where account_id=%s for update",
                (account,),
            )
            for run, source, sequence, occurred in c.fetchall():
                try:
                    with c.connection.transaction():
                        c.execute(
                            "insert into privacy_minimized_records(account_id,source_kind,source_id,category,event_kind,outcome,quantity,occurred_at,confirmation_at,eligible_at) values(%s,'relay_recovery',%s,'usage_recovery',%s,'closed',%s,%s,%s,%s) on conflict do nothing",
                            (
                                account,
                                run,
                                "relay." + source,
                                sequence,
                                occurred,
                                accepted[0],
                                accepted[0] + timedelta(days=90),
                            ),
                        )
                        c.execute(
                            "delete from subscription_relay_frames where run_id=%s and account_id=%s",
                            (run, account),
                        )
                        counts["relay"] += 1
                except Exception:  # noqa: BLE001 -- no trigger or FK bypass
                    blockers.append("subscription_relay_frames:integrity_dependency")
            c.execute(
                "select x.run_id,x.created_at,r.account_id,s.user_id,r.active from subscription_relay_connections x join subscription_auto_runs r using(run_id) join interview_sessions s on s.id=x.session_id where x.account_id=%s for update of x",
                (account,),
            )
            for run, occurred, run_owner, session_owner, active in c.fetchall():
                if (
                    str(run_owner) != str(account)
                    or str(session_owner) != str(account)
                    or active
                ):
                    blockers.append(
                        "subscription_relay_connections:ownership_or_live_writer"
                    )
                    continue
                c.execute(
                    "insert into privacy_minimized_records(account_id,source_kind,source_id,category,event_kind,outcome,quantity,occurred_at,confirmation_at,eligible_at) values(%s,'relay_recovery',%s,'usage_recovery','relay.connection','closed',0,%s,%s,%s) on conflict do nothing",
                    (
                        account,
                        run,
                        occurred,
                        accepted[0],
                        accepted[0] + timedelta(days=90),
                    ),
                )
                c.execute(
                    "delete from subscription_relay_connections where account_id=%s and run_id=%s",
                    (account, run),
                )
                counts["relay"] += 1
        return {
            "minimized": counts,
            "blockers": blockers,
            "immutable_history": "unchanged",
        }


class RetentionWorker:
    def __init__(self, connect):
        self.connect = connect

    def call(self, action, lease):
        with self.connect() as connection, connection.cursor() as c:
            c.execute("select public.privacy_retention_call(%s,%s)", (action, lease))
            return c.fetchone()[0]

    def run_one(self):
        lease = str(uuid4())
        if not self.call("claim", lease):
            return False
        self.call("finish", lease)
        return True
