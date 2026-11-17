"""Explicit disposable-candidate worker. No scheduler, DSN or activation path."""

from uuid import UUID

from app.commercial.executor_connection import check_executor_identity
from app.privacy_content import ContentBlocked


class RetirementCandidateWorker:
    def __init__(self, connect, *, local_candidate=False):
        if local_candidate is not True:
            raise ContentBlocked("retirement_disabled")
        self.connect = connect

    def retire_usage(self, account_id, revision):
        return self._execute("usage", account_id, revision)

    def retire_replies(self, run_id, revision):
        return self._execute("replies", run_id, revision)

    def retire_security(self, request_id, revision):
        return self._execute("security", request_id, revision)

    def _execute(self, kind, identity, revision):
        if kind not in {"replies", "security", "usage"}:
            raise ContentBlocked("retirement_invalid_scope")
        statement = (
            "select public.privacy_retire_legacy_replies(%s,%s)"
            if kind == "replies"
            else "select public.privacy_retire_legacy_security(%s,%s)"
        )
        if kind == "usage":
            statement = "select public.privacy_retire_usage(%s,%s)"
        identity = str(UUID(str(identity)))
        if type(revision) is not int or revision < 1:
            raise ContentBlocked("retirement_invalid_revision")
        with self.connect() as c:
            check_executor_identity(c, "privacy_retirement_executor")
            # Calls use the existing bounded native principal contract. A single
            # DB transaction owns locking, exact membership, CAS and attestation.
            c.execute("set local lock_timeout='5s'")
            c.execute("set local statement_timeout='10s'")
            count = c.execute(statement, (identity, revision)).fetchone()[0]
            if kind == "usage":
                return {**count, "full_account_erasure": False}
            return {
                "state": "retired" if count else "already_retired",
                "removed": count,
                "full_account_erasure": False,
            }
