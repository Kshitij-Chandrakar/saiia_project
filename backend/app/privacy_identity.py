"""Durable supported Auth minimization, separate from successful logout."""

import json
import logging
from uuid import uuid4

import requests

from app.commercial.executor_connection import check_executor_identity
from app.privacy_credentials import CredentialUnavailable


class IdentityCleanupWorker:
    def __init__(self, connect, admin):
        self.connect, self.admin = connect, admin

    def call(self, action, task):
        with self.connect() as c:
            check_executor_identity(c, "privacy_identity_executor")
            return c.execute(
                "select public.privacy_identity_call(%s,%s::jsonb)",
                (action, json.dumps(task)),
            ).fetchone()[0]

    def run_one(self):
        task = self.call("claim", {"lease_id": str(uuid4())})
        if not task:
            return False
        try:
            if not self.call("verify", task)["verified"]:
                self.admin.soft_delete(task["account_id"])
        except (requests.RequestException, CredentialUnavailable):
            logging.getLogger("privacy").warning(
                "Identity cleanup deferred: auth_unavailable"
            )
        # Authoritative absence, never a 401 or the caller's success flag.
        self.call("finish", task)
        return True
