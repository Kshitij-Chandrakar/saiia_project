"""Private provisioning adapter. Never mount this as a public/admin endpoint.

The caller must be a separately restricted control-plane worker. Keep the email
lock through the bounded Auth call so accepted suppression cannot race creation.
An uncertain remote commit is not retried as a new import; operator correlation
must resolve it. Direct project administrators remain outside this boundary.
"""

from uuid import UUID

from app.privacy_content import ContentBlocked


class ProvisioningGate:
    def __init__(self, connect, create):
        self.connect, self.create = connect, create

    def provision(self, operation, email, password):
        operation = str(UUID(operation))
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ContentBlocked("provisioning_invalid")
        try:
            with self.connect() as c:
                allowed = c.execute(
                    "select public.privacy_provisioning_check(%s)", (email,)
                ).fetchone()[0]
                if not allowed:
                    raise ContentBlocked("provisioning_denied")
                # Fixed operation reference is local correlation, never an Auth
                # idempotency guarantee. Do not retry an uncertain HTTP result.
                return self.create(operation, email, password)
        except ContentBlocked:
            raise
        except Exception:  # noqa: BLE001 -- never expose Auth/DB credentials or payloads
            raise ContentBlocked("provisioning_unavailable") from None
