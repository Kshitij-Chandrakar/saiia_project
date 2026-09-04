import socket

import pytest

from app.email.config import EmailConfigurationError, EmailSettings, load_email_settings
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.provider import EmailSendRequest, EmailValidationError
from app.email.service import build_email_service


def test_email_settings_default_to_disabled_dry_run() -> None:
    settings = load_email_settings({})

    assert settings.enabled is False
    assert settings.dry_run is True
    assert settings.provider == "resend"
    assert settings.resend_api_key == ""
    assert settings.live_delivery_requested is False


def test_dry_run_send_returns_safe_result_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run email attempted network access")

    monkeypatch.setattr(socket, "socket", fail_socket)
    provider = DryRunEmailProvider()
    result = provider.send_email(
        EmailSendRequest(
            recipient_email="mentor@example.com",
            subject="Interview notes ready",
            email_type="ai_notes_ready",
            safe_metadata={"session_id": "30000000-0000-4000-8000-000000000001"},
        )
    )

    assert result.status == "dry_run"
    assert result.dry_run is True
    assert result.provider == "dry_run"
    assert result.message_id == "dry-run"
    assert result.recipient_masked == "m***@example.com"
    assert provider.records[0]["email_type"] == "ai_notes_ready"


def test_missing_resend_secret_does_not_fail_dry_run_mode() -> None:
    service = build_email_service(EmailSettings(enabled=False, dry_run=True, resend_api_key=""))

    result = service.send_transactional_email(
        recipient_email="mentor@example.com",
        subject="Welcome",
        email_type="welcome",
    )

    assert result.dry_run is True


@pytest.mark.parametrize(
    "metadata",
    [
        {"access_token": "secret"},
        {"callback_url": "https://example.com/auth/callback?code=secret"},
    ],
)
def test_sensitive_metadata_is_rejected(metadata: dict[str, str]) -> None:
    with pytest.raises(EmailValidationError):
        EmailSendRequest(
            recipient_email="mentor@example.com",
            subject="Safe test",
            email_type="welcome",
            safe_metadata=metadata,
        )


@pytest.mark.parametrize("email_type", ["auth_signup_verification", "auth_password_reset"])
def test_supabase_auth_email_types_are_not_routed_through_transactional_service(email_type: str) -> None:
    service = build_email_service()

    with pytest.raises(EmailValidationError, match="backend transactional"):
        service.send_transactional_email(
            recipient_email="mentor@example.com",
            subject="Auth message",
            email_type=email_type,
        )


def test_live_provider_mode_fails_closed_without_provider_call() -> None:
    with pytest.raises(EmailConfigurationError, match="not implemented"):
        build_email_service(EmailSettings(enabled=True, dry_run=False, resend_api_key="placeholder"))
