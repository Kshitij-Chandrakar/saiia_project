"""Private PostgreSQL coordination; never an alternative entitlement authority."""

import hashlib
import json
import secrets
from typing import Any

from app.commercial.account_entitlements import ID, json_query
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, _input
from app.commercial.subscription_service import SubscriptionService


class HostedCoordination:
    def __init__(self, service: SubscriptionService) -> None:
        self.service = service

    def available(self, actor: VerifiedActor) -> None:
        subject = self.service._channel._actor(actor)
        self.service._channel._transaction(
            False,
            lambda q: q("SELECT public.subscription_access_check(%s)", (subject,)),
        )

    def claim_stream(self, actor: VerifiedActor, run: str, session: str) -> None:
        subject = self.service._channel._actor(actor)
        self.service._channel._transaction(
            True,
            lambda q: q(
                "SELECT public.subscription_relay_claim(%s,%s,%s)",
                (subject, _input(ID, run), _input(ID, session)),
            ),
        )

    def prepare_deletion(self, actor: VerifiedActor, request_id: str) -> dict[str, Any]:
        """Resumable self-owned barrier only. Purge/unlink is deliberately absent."""
        subject = self.service._channel._actor(actor)
        key = _input(ID, request_id)
        return self.service._channel._transaction(
            True,
            lambda q: json_query(
                q, "SELECT public.subscription_deletion_prepare(%s,%s)", (subject, key)
            ),
        )

    def frame(self, lease: Any, session: str, sequence: int, data: bytes) -> bool:
        if type(sequence) is not int or not 0 < sequence <= 2**53 - 1:
            raise CatalogStoreError(ErrorCode.INVALID)
        if not isinstance(data, bytes) or not 2 <= len(data) <= 6400 or len(data) % 2:
            raise CatalogStoreError(ErrorCode.INVALID)
        subject = self.service._channel._actor(lease.actor)
        row = lease.row
        return (
            self.service._channel._transaction(
                True,
                lambda q: q(
                    "SELECT public.subscription_relay_frame(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        subject,
                        row["run_id"],
                        row["owner_token"],
                        row["fence"],
                        _input(ID, session),
                        lease.source,
                        sequence,
                        hashlib.sha256(data).hexdigest(),
                        len(data),
                    ),
                ),
            )
            is True
        )


class SharedHandoff:
    """Ephemeral encrypted credentials, separate from usage/audit records.

    The existing five-minute/three-active/five-second rules are retained in SQL.
    Encryption key is backend-controlled and must be identical across workers.
    """

    def __init__(self, service: SubscriptionService, key: str) -> None:
        self.service = service
        try:
            from cryptography.fernet import Fernet

            self.cipher = Fernet(key.encode("ascii"))
        except (ImportError, ValueError, TypeError, UnicodeError):
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def create(self, actor: VerifiedActor, state: str, refresh_token: str) -> str:
        subject = self.service._channel._actor(actor)
        if not 16 <= len(state) <= 256 or not 1 <= len(refresh_token) <= 8192:
            raise CatalogStoreError(ErrorCode.INVALID)
        code = secrets.token_urlsafe(32)
        ciphertext = self.cipher.encrypt(
            json.dumps(
                {
                    "access_token": actor._bearer,
                    "refresh_token": refresh_token,
                }
            ).encode()
        ).decode()
        self.service._channel._transaction(
            True,
            lambda q: q(
                "SELECT public.subscription_handoff('create',%s,%s,%s,%s)",
                (subject, self.digest(code), self.digest(state), ciphertext),
            ),
        )
        return code

    def exchange(self, code: str, state: str) -> dict[str, str]:
        from cryptography.fernet import InvalidToken

        if not 32 <= len(code) <= 256 or not 16 <= len(state) <= 256:
            raise CatalogStoreError(ErrorCode.INVALID)
        record = self.service._channel._transaction(
            True,
            lambda q: json_query(
                q,
                "SELECT public.subscription_handoff('exchange',null,%s,%s,null)",
                (self.digest(code), self.digest(state)),
            ),
        )
        try:
            payload = json.loads(
                self.cipher.decrypt(record["ciphertext"].encode(), ttl=300)
            )
            actor = VerifiedActor(record["account_id"], payload["access_token"])
            HostedCoordination(self.service).available(actor)
            return {key: str(payload[key]) for key in ("access_token", "refresh_token")}
        except (InvalidToken, ValueError, TypeError, KeyError, UnicodeError):
            # A consumed/uncertain exchange never creates a replacement handoff.
            raise CatalogStoreError(ErrorCode.DENIED) from None
