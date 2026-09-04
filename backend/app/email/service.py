from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Final

from app.email.config import EmailConfigurationError, EmailSettings, load_email_settings
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.event_store import (
    OutboundEmailEventConflictError,
    OutboundEmailEventError,
    OutboundEmailEventService,
    OutboundEmailEventRecord,
)
from app.email.provider import (
    EmailProvider,
    EmailSendRequest,
    EmailSendResult,
    mask_recipient_email,
    utc_timestamp,
)
from app.email.templates import WELCOME_TEMPLATE_VERSION, render_welcome_email


_RETRYABLE_PROVIDER_ERROR_CODES: Final = frozenset(
    {"provider_timeout", "provider_unavailable", "provider_rate_limited"}
)


def _is_expired(value: str | None) -> bool:
    if not value:
        return False
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= datetime.now(timezone.utc)


def _provider_error_code(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, ConnectionError):
        return "provider_unavailable"
    return "provider_error"


class EmailService:
    """Safe service boundary for future backend transactional email sends."""

    def __init__(
        self,
        provider: EmailProvider,
        *,
        event_store: OutboundEmailEventService | None = None,
    ) -> None:
        self._provider = provider
        self._event_store = event_store

    def send_transactional_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        email_type: str,
        text_body: str = "",
        safe_metadata: Mapping[str, object] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        idempotency_key: str | None = None,
        retry_failed: bool = False,
    ) -> EmailSendResult:
        request = EmailSendRequest(
            recipient_email=recipient_email,
            subject=subject,
            email_type=email_type,
            text_body=text_body,
            safe_metadata=safe_metadata or {},
        )
        has_event_context = any(
            value is not None for value in (user_id, session_id, idempotency_key)
        )
        if not has_event_context:
            return self._provider.send_email(request)
        if not user_id or not idempotency_key or self._event_store is None:
            raise OutboundEmailEventError(
                "Backend transactional email event context is incomplete."
            )
        return self._send_with_event(
            request=request,
            user_id=user_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
            retry_failed=retry_failed,
        )

    def _send_with_event(
        self,
        *,
        request: EmailSendRequest,
        user_id: str,
        session_id: str | None,
        idempotency_key: str,
        retry_failed: bool,
    ) -> EmailSendResult:
        if self._event_store is None:
            raise OutboundEmailEventError("Outbound email event store is unavailable.")

        event_metadata = dict(request.safe_metadata)
        event_metadata["dry_run"] = True
        claim = self._event_store.reserve(
            user_id=user_id,
            session_id=session_id,
            email_type=request.email_type,
            recipient_email=request.recipient_email,
            idempotency_key=idempotency_key,
            safe_metadata=event_metadata,
        )
        event = claim.event

        if event.status == "sent":
            return self._replay_result(request=request, event=event)

        if event.status == "pending":
            if not event.pending_expires_at:
                raise OutboundEmailEventConflictError(
                    "Outbound email event requires reconciliation."
                )
            if _is_expired(event.pending_expires_at):
                event = self._event_store.reclaim_pending(
                    user_id=user_id,
                    event_id=event.id,
                )
            elif claim.conflict_reason:
                raise OutboundEmailEventConflictError(
                    "Outbound email event is already processing."
                )
            else:
                event = self._event_store.begin_send(
                    user_id=user_id,
                    event_id=event.id,
                )
        elif event.status == "sending":
            if not event.lease_expires_at or _is_expired(event.lease_expires_at):
                if event.lease_expires_at:
                    self._event_store.reconcile_expired(
                        user_id=user_id,
                        event_id=event.id,
                    )
                raise OutboundEmailEventConflictError(
                    "Outbound email event requires reconciliation."
                )
            raise OutboundEmailEventConflictError(
                "Outbound email event is already processing."
            )
        elif event.status == "failed" and retry_failed:
            if event.error_code not in _RETRYABLE_PROVIDER_ERROR_CODES:
                raise OutboundEmailEventConflictError(
                    "Permanent email failures are not retryable."
                )
            event = self._event_store.retry_failed(
                user_id=user_id,
                event_id=event.id,
                retryable=True,
            )
            event = self._event_store.begin_send(
                user_id=user_id,
                event_id=event.id,
            )
        else:
            raise OutboundEmailEventConflictError(
                "Outbound email event is not ready to send."
            )

        claim_token = event.claim_token
        if event.status != "sending" or not claim_token:
            raise OutboundEmailEventConflictError(
                "Outbound email event claim is not active."
            )

        try:
            result = self._provider.send_email(request)
        except Exception as error:
            self._mark_failed_after_provider_error(
                user_id=user_id,
                event=event,
                error_code=_provider_error_code(error),
            )
            raise OutboundEmailEventError(
                "Transactional email provider failed."
            ) from error

        completed = self._event_store.mark_sent(
            user_id=user_id,
            event_id=event.id,
            claim_token=claim_token,
            provider=result.provider,
            provider_message_id=result.message_id,
        )
        return self._result_with_event(
            result,
            event=completed,
            replayed=False,
        )

    def _mark_failed_after_provider_error(
        self,
        *,
        user_id: str,
        event: OutboundEmailEventRecord,
        error_code: str,
    ) -> None:
        if self._event_store is None or not event.claim_token:
            raise OutboundEmailEventError(
                "Outbound email event could not be finalized safely."
            )
        try:
            self._event_store.mark_failed(
                user_id=user_id,
                event_id=event.id,
                claim_token=event.claim_token,
                error_code=error_code,
                provider="dry_run",
            )
        except Exception as error:
            raise OutboundEmailEventError(
                "Outbound email event could not be finalized safely."
            ) from error

    @staticmethod
    def _replay_result(
        *,
        request: EmailSendRequest,
        event: OutboundEmailEventRecord,
    ) -> EmailSendResult:
        return EmailSendResult(
            status="dry_run",
            provider=event.provider or "dry_run",
            message_id=event.provider_message_id or "dry-run",
            dry_run=True,
            recipient_masked=mask_recipient_email(request.recipient_email),
            email_type=request.email_type,
            created_at=event.created_at or utc_timestamp(),
            event_id=event.id,
            event_status=event.status,
            replayed=True,
        )

    @staticmethod
    def _result_with_event(
        result: EmailSendResult,
        *,
        event: OutboundEmailEventRecord,
        replayed: bool,
    ) -> EmailSendResult:
        return EmailSendResult(
            status=result.status,
            provider=result.provider,
            message_id=result.message_id,
            dry_run=result.dry_run,
            recipient_masked=result.recipient_masked,
            email_type=result.email_type,
            created_at=result.created_at,
            event_id=event.id,
            event_status=event.status,
            replayed=replayed,
        )


def build_email_service(
    email_settings: EmailSettings | None = None,
    *,
    event_store: OutboundEmailEventService | None = None,
) -> EmailService:
    """Build the dry-run service and fail closed for unimplemented live mode."""

    settings = email_settings or load_email_settings()
    if settings.live_delivery_requested:
        raise EmailConfigurationError("Live email delivery is not implemented in C10.3C.")
    return EmailService(DryRunEmailProvider(), event_store=event_store)


def send_welcome_email_dry_run(
    *,
    email_service: EmailService,
    user_id: str,
    recipient_email: str,
    display_name: str | None = None,
    support_email: str | None = None,
    dashboard_path: str = "/auth/dashboard",
) -> EmailSendResult:
    """Render and persist one deterministic, dry-run welcome event per user."""

    if not user_id.strip():
        raise OutboundEmailEventError("Welcome email user context is incomplete.")
    template = render_welcome_email(
        display_name=display_name,
        support_email=support_email,
        dashboard_path=dashboard_path,
    )
    return email_service.send_transactional_email(
        recipient_email=recipient_email,
        subject=template.subject,
        email_type=template.email_type,
        text_body=template.text_body,
        safe_metadata={
            "template_version": WELCOME_TEMPLATE_VERSION,
            "dry_run": True,
        },
        user_id=user_id,
        idempotency_key=f"welcome:{user_id}",
    )
