import logging

from app.email.provider import (
    EmailProvider,
    EmailSendRequest,
    EmailSendResult,
    mask_recipient_email,
    utc_timestamp,
)


logger = logging.getLogger("email")


class DryRunEmailProvider:
    """In-memory provider that never opens a network or SMTP connection."""

    def __init__(self) -> None:
        self._records: list[dict[str, object]] = []

    @property
    def records(self) -> tuple[dict[str, object], ...]:
        return tuple(self._records)

    def send_email(self, request: EmailSendRequest) -> EmailSendResult:
        created_at = utc_timestamp()
        recipient_masked = mask_recipient_email(request.recipient_email)
        record = {
            "email_type": request.email_type,
            "recipient_masked": recipient_masked,
            "dry_run": True,
            "created_at": created_at,
            "metadata": dict(request.safe_metadata),
        }
        self._records.append(record)
        logger.info(
            "email_dry_run email_type=%s recipient=%s dry_run=true",
            request.email_type,
            recipient_masked,
        )
        return EmailSendResult(
            status="dry_run",
            provider="dry_run",
            message_id="dry-run",
            dry_run=True,
            recipient_masked=recipient_masked,
            email_type=request.email_type,
            created_at=created_at,
        )
