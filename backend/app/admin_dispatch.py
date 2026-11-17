"""Restricted durable admin dispatch. Providers are supplied by existing composition."""

import json
import logging


class CancellationDispatcher:
    def __init__(self, connect, billing):
        self.connect, self.billing = connect, billing

    def call(self, action, document):
        with self.connect() as c:
            c.execute("set local statement_timeout='5s'")
            return c.execute(
                "select public.administration_command(%s,%s::jsonb)",
                (action, json.dumps(document)),
            ).fetchone()[0]

    def run_one(self):
        if self.billing is None or not self.billing.enabled:
            return False
        command = self.call("claim", {})
        if not command:
            return False
        identity = {"id": command["id"], "lease": command["lease"]}
        if not self.call("dispatch", identity)["allowed"]:
            return True
        outcome = "unknown"
        try:
            if command["reconcile_only"]:
                result = self.billing.view(
                    self.billing.reconcile(command["account_id"], command["billing_id"])
                )
            else:
                result = self.billing._cancel_account(
                    command["account_id"], command["billing_id"]
                )
            if result.get("provider_state") in {"cancelled", "completed", "expired"}:
                outcome = "confirmed"
        except Exception:  # noqa: BLE001 -- provider/driver errors must not expose payloads
            logging.getLogger(__name__).warning("Cancellation outcome unknown")
        self.call("finish", {**identity, "outcome": outcome})
        return True
