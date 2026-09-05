import hashlib
import logging
import socket
from datetime import datetime, timezone

import pytest

from app.email.service import EmailService
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.unsubscribe import (
    MarketingUnsubscribeService,
    MarketingUnsubscribeValidationError,
)


TEST_USER_ID = "00000000-0000-4000-8000-000000000001"


class FakeUnsubscribeClient:
    def __init__(self) -> None:
        self.tokens: list[dict[str, object]] = []
        self.marketing_opt_in: dict[str, bool] = {TEST_USER_ID: True}
        self.consume_calls: list[str] = []

    def insert_token(
        self,
        *,
        user_id: str,
        recipient_email: str,
        token_hash: str,
        email_category: str,
        expires_at: str,
    ) -> None:
        self.tokens.append(
            {
                "user_id": user_id,
                "recipient_email": recipient_email,
                "token_hash": token_hash,
                "email_category": email_category,
                "expires_at": expires_at,
                "used": False,
                "revoked": False,
            }
        )

    def consume_token(self, *, token_hash: str) -> bool:
        self.consume_calls.append(token_hash)
        for token in self.tokens:
            try:
                expires_at = datetime.fromisoformat(str(token["expires_at"]).replace("Z", "+00:00"))
            except ValueError:
                continue
            if (
                token["token_hash"] != token_hash
                or token["used"]
                or token["revoked"]
                or expires_at <= datetime.now(timezone.utc)
            ):
                continue
            token["used"] = True
            self.marketing_opt_in[str(token["user_id"])] = False
            return True
        return False

    def get_marketing_opt_in(self, *, user_id: str) -> bool:
        return self.marketing_opt_in.get(user_id, False)


def _service() -> tuple[MarketingUnsubscribeService, FakeUnsubscribeClient]:
    client = FakeUnsubscribeClient()
    return MarketingUnsubscribeService(client=client), client


def test_token_generation_returns_raw_once_and_stores_only_hash() -> None:
    service, client = _service()

    created = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )

    stored = client.tokens[0]
    assert created.raw_token
    assert stored["token_hash"] == hashlib.sha256(created.raw_token.encode()).hexdigest()
    assert created.raw_token not in stored.values()
    assert all("raw_token" not in token for token in client.tokens)


def test_raw_token_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _service()

    with caplog.at_level(logging.INFO):
        created = service.create_token(
            user_id=TEST_USER_ID,
            recipient_email="user@example.com",
        )

    assert created.raw_token not in caplog.text


def test_valid_token_opts_out_only_marketing_and_used_token_is_rejected() -> None:
    service, _ = _service()
    created = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )

    result = service.unsubscribe(raw_token=created.raw_token)

    assert result.unsubscribed is True
    assert service.is_marketing_allowed(user_id=TEST_USER_ID) is False
    assert service.unsubscribe(raw_token=created.raw_token).unsubscribed is False


def test_expired_and_revoked_tokens_are_rejected() -> None:
    service, client = _service()
    expired = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )
    revoked = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )
    client.tokens[0]["expires_at"] = "2000-01-01T00:00:00Z"
    client.tokens[1]["revoked"] = True

    assert service.unsubscribe(raw_token=expired.raw_token).unsubscribed is False
    assert service.unsubscribe(raw_token=revoked.raw_token).unsubscribed is False


def test_invalid_token_returns_safe_generic_result() -> None:
    service, client = _service()

    result = service.unsubscribe(raw_token="not-a-valid-token")

    assert result.unsubscribed is False
    assert client.consume_calls == []


def test_token_creation_validates_server_context() -> None:
    service, _ = _service()

    with pytest.raises(MarketingUnsubscribeValidationError):
        service.create_token(
            user_id="not-a-uuid",
            recipient_email="user@example.com",
        )


def test_transactional_email_remains_available_after_marketing_opt_out() -> None:
    service, _ = _service()
    created = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )
    service.unsubscribe(raw_token=created.raw_token)

    provider = DryRunEmailProvider()
    email_service = EmailService(provider)
    result = email_service.send_transactional_email(
        recipient_email="user@example.com",
        subject="Account security notice",
        email_type="account_security",
    )

    assert result.dry_run is True
    assert len(provider.records) == 1


def test_unsubscribe_foundation_never_requires_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("unsubscribe foundation attempted network access")

    monkeypatch.setattr(socket, "socket", fail_socket)
    service, _ = _service()

    created = service.create_token(
        user_id=TEST_USER_ID,
        recipient_email="user@example.com",
    )

    assert service.unsubscribe(raw_token=created.raw_token).unsubscribed is True
