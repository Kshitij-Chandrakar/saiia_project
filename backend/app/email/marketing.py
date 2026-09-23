"""Backend-only, single-recipient marketing foundation. No scheduler or send route."""
from dataclasses import dataclass, field
import re
from uuid import UUID

import requests

from app.email.config import MarketingEmailSettings, load_marketing_email_settings
from app.email.dry_run_provider import DryRunEmailProvider
from app.email.event_store import OutboundEmailEventConflictError, OutboundEmailEventError
from app.email.provider import EmailSendResult, EmailValidationError, mask_recipient_email, normalize_safe_metadata, utc_timestamp, validate_recipient_email
from app.email.unsubscribe import RAW_TOKEN_RE


@dataclass(frozen=True, slots=True)
class MarketingEmailRequest:
    recipient_email: str = field(repr=False)
    raw_token: str = field(repr=False)
    idempotency_key: str
    safe_metadata: dict[str, object]
    email_type: str = field(default="marketing_product_update", init=False)
    subject: str = field(default="What’s new in Intervu AI", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipient_email", validate_recipient_email(self.recipient_email))
        if not RAW_TOKEN_RE.fullmatch(self.raw_token):
            raise EmailValidationError("Marketing unsubscribe token is required.")
        if not re.fullmatch(r"[A-Za-z0-9._~:-]{1,128}", self.idempotency_key):
            raise EmailValidationError("Marketing provider idempotency key is invalid.")
        if set(self.safe_metadata) - {"campaign_key", "template_key", "dry_run"}:
            raise EmailValidationError("Marketing metadata contains an unsupported field.")
        object.__setattr__(self, "safe_metadata", normalize_safe_metadata(self.safe_metadata))

    @property
    def unsubscribe_url(self) -> str:
        return f"https://intervucopilot.in/unsubscribe?token={self.raw_token}"

    @property
    def text_body(self) -> str:
        return (
            "Intervu AI product updates\n\n"
            "Visit your Intervu AI dashboard to explore the product.\n"
            "You received this email because you opted in to product updates.\n\n"
            f"Unsubscribe: {self.unsubscribe_url}"
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "List-Unsubscribe": f"<https://intervucopilot.in/api/email/unsubscribe/one-click?token={self.raw_token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }


class ResendMarketingProvider:
    """No automatic retries: uncertain sends stay blocked for reconciliation."""

    def __init__(self, settings: MarketingEmailSettings, *, session=None) -> None:
        self.settings = settings
        self._session = session or requests.Session()
        self._dry_run = DryRunEmailProvider()

    def send_email(self, request: MarketingEmailRequest) -> EmailSendResult:
        if not isinstance(request, MarketingEmailRequest):
            raise EmailValidationError("Marketing provider requires a validated marketing request.")
        if not self.settings.live_delivery_requested:
            return self._dry_run.send_email(request)
        payload = {
            "from": f"{self.settings.from_name} <{self.settings.from_email}>",
            "to": [request.recipient_email],
            "subject": request.subject,
            "text": request.text_body,
            "headers": request.headers,
        }
        if self.settings.reply_to:
            payload["reply_to"] = self.settings.reply_to
        try:
            response = self._session.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.settings.resend_api_key}",
                         "Idempotency-Key": request.idempotency_key},
                json=payload, timeout=10, allow_redirects=False,
            )
            if response.status_code != 200:
                raise ValueError("provider rejected request")
            message_id = str(UUID(response.json()["id"]))
        except Exception:
            # Provider exceptions/responses may contain addresses, bodies or credentials.
            raise OutboundEmailEventError("Marketing provider result requires reconciliation.") from None
        return EmailSendResult(
            status="sent", provider="resend", message_id=message_id, dry_run=False,
            recipient_masked=mask_recipient_email(request.recipient_email),
            email_type=request.email_type, created_at=utc_timestamp(),
        )


class MarketingEmailService:
    def __init__(self, *, event_store, unsubscribe_service, settings=None, provider=None):
        self.settings = settings or load_marketing_email_settings()
        self._events = event_store
        self._unsubscribe = unsubscribe_service
        self._provider = provider or ResendMarketingProvider(self.settings)

    def send_marketing_email(self, *, user_id: str, recipient_email: str,
                             campaign_key: str, template_key: str, idempotency_key: str):
        try:
            user_id = str(UUID(user_id))
        except (ValueError, TypeError, AttributeError):
            raise EmailValidationError("Marketing user context is invalid.") from None
        if template_key != "product_update" or not re.fullmatch(r"[a-z0-9_-]{1,64}", campaign_key):
            raise EmailValidationError("Marketing campaign or template is invalid.")
        recipient_email = validate_recipient_email(recipient_email)
        claim = self._events.reserve(
            user_id=user_id, session_id=None, email_type="marketing_product_update",
            recipient_email=recipient_email, idempotency_key=idempotency_key,
            safe_metadata={"campaign_key": campaign_key, "template_key": template_key,
                           "dry_run": not self.settings.live_delivery_requested},
        )
        if claim.event.status in {"sent", "canceled"}:
            return claim.event
        if claim.conflict_reason or claim.event.status != "pending":
            raise OutboundEmailEventConflictError("Marketing event already claimed; reconcile before retrying.")
        event = self._events.begin_send(user_id=user_id, event_id=claim.event.id)
        context = dict(user_id=user_id, event_id=event.id, claim_token=event.claim_token)
        try:
            if not self._unsubscribe.is_marketing_allowed(user_id=user_id):
                return self._events.cancel(**context)
            token = self._unsubscribe.create_token(user_id=user_id, recipient_email=recipient_email)
            request = MarketingEmailRequest(
                recipient_email=recipient_email, raw_token=token.raw_token,
                idempotency_key=f"marketing:{event.id}", safe_metadata=event.metadata_json,
            )
            # Re-read after token persistence; an intervening opt-out must stop dispatch.
            if not self._unsubscribe.is_marketing_allowed(user_id=user_id):
                return self._events.cancel(**context)
        except Exception:
            self._events.mark_failed(**context, error_code="marketing_guard_failed")
            raise OutboundEmailEventError("Marketing consent or unsubscribe setup failed.") from None
        # Enforce the live gate here as well as at the provider boundary.
        provider = self._provider if self.settings.live_delivery_requested else DryRunEmailProvider()
        result = provider.send_email(request)
        # On provider/commit failure leave 'sending' for existing reconciliation;
        # never automatically resend an uncertain result.
        return self._events.mark_sent(**context, provider=result.provider, provider_message_id=result.message_id)
