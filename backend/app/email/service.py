from collections.abc import Mapping

from app.email.config import EmailConfigurationError, EmailSettings, load_email_settings
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.provider import EmailProvider, EmailSendRequest, EmailSendResult


class EmailService:
    """Safe service boundary for future backend transactional email sends."""

    def __init__(self, provider: EmailProvider) -> None:
        self._provider = provider

    def send_transactional_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        email_type: str,
        safe_metadata: Mapping[str, object] | None = None,
    ) -> EmailSendResult:
        request = EmailSendRequest(
            recipient_email=recipient_email,
            subject=subject,
            email_type=email_type,
            safe_metadata=safe_metadata or {},
        )
        return self._provider.send_email(request)


def build_email_service(email_settings: EmailSettings | None = None) -> EmailService:
    """Build the dry-run service and fail closed for unimplemented live mode."""

    settings = email_settings or load_email_settings()
    if settings.live_delivery_requested:
        raise EmailConfigurationError("Live email delivery is not implemented in C10.3A.")
    return EmailService(DryRunEmailProvider())
