from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any, NoReturn, Protocol

import requests
from requests.adapters import HTTPAdapter

from app.cloud.interview_sessions import _validate_supabase_url
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.email.provider import (
    BACKEND_TRANSACTIONAL_EMAIL_TYPES,
    EmailValidationError,
    normalize_safe_metadata,
    validate_recipient_email,
)


logger = logging.getLogger("email_event_store")

SAFE_FAILURE_MESSAGE = "Outbound email event storage is temporarily unavailable."
EVENT_STATUSES = frozenset(
    {
        "pending",
        "sending",
        "sent",
        "failed",
        "canceled",
        "needs_reconciliation",
        "retry_blocked",
    }
)
RECONCILIATION_OUTCOMES = frozenset({"sent", "failed", "retry", "retry_blocked"})
PROVIDER_STATES = frozenset({"sent", "permanent_failure", "not_sent", "unknown"})
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._~:-]{1,128}$")
SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
MAX_IDEMPOTENCY_KEY_CHARS = 128
MAX_PROVIDER_MESSAGE_ID_CHARS = 255
MAX_LEASE_SECONDS = 3600
DEFAULT_PENDING_LEASE_SECONDS = 300
DEFAULT_SENDING_LEASE_SECONDS = 300
SUPABASE_HTTP_POOL_SIZE = 20
SUPABASE_MUTATION_TIMEOUT = 8


class OutboundEmailEventError(RuntimeError):
    """Base error for backend-owned outbound email event operations."""


class OutboundEmailEventNotFoundError(OutboundEmailEventError):
    """Raised when an event is missing or not owned by the caller."""


class OutboundEmailEventConflictError(OutboundEmailEventError):
    """Raised when an event state or claim prevents a mutation."""


class OutboundEmailEventValidationError(OutboundEmailEventError, ValueError):
    """Raised when an outbound event request is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class OutboundEmailEventRecord:
    id: str
    user_id: str
    session_id: str | None
    email_type: str
    recipient_email: str
    provider: str | None
    provider_message_id: str | None
    idempotency_key: str
    claim_token: str | None
    reconciliation_token: str | None
    row_version: int
    sending_started_at: str | None
    lease_expires_at: str | None
    pending_expires_at: str | None
    status: str
    error_code: str | None
    metadata_json: dict[str, object]
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True, slots=True)
class OutboundEmailEventClaim:
    event: OutboundEmailEventRecord
    replayed: bool
    conflict_reason: str | None = None

    @property
    def already_processing(self) -> bool:
        return self.event.status in {"pending", "sending"}


@dataclass(frozen=True, slots=True)
class OutboundEmailEventRequest:
    user_id: str
    session_id: str | None
    email_type: str
    recipient_email: str
    idempotency_key: str
    safe_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.email_type not in BACKEND_TRANSACTIONAL_EMAIL_TYPES:
            raise OutboundEmailEventValidationError(
                "Email type is not a backend transactional email."
            )
        try:
            recipient = validate_recipient_email(self.recipient_email)
        except EmailValidationError as exc:
            raise OutboundEmailEventValidationError(str(exc)) from exc
        key = str(self.idempotency_key or "").strip()
        if not IDEMPOTENCY_KEY_RE.fullmatch(key):
            raise OutboundEmailEventValidationError("Idempotency key is invalid.")
        if len(key) > MAX_IDEMPOTENCY_KEY_CHARS:
            raise OutboundEmailEventValidationError("Idempotency key is too long.")
        if self.session_id is not None:
            session_id = str(self.session_id).strip()
            if not session_id:
                raise OutboundEmailEventValidationError("Session id is invalid.")
            object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "recipient_email", recipient)
        object.__setattr__(self, "idempotency_key", key)
        try:
            metadata = normalize_safe_metadata(self.safe_metadata)
        except (EmailValidationError, TypeError) as exc:
            raise OutboundEmailEventValidationError(str(exc)) from exc
        object.__setattr__(self, "safe_metadata", metadata)


def _record_from_payload(payload: Mapping[str, Any]) -> OutboundEmailEventRecord:
    metadata = payload.get("metadata_json")
    return OutboundEmailEventRecord(
        id=str(payload.get("id") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id")).strip() if payload.get("session_id") else None,
        email_type=str(payload.get("email_type") or ""),
        recipient_email=str(payload.get("recipient_email") or ""),
        provider=str(payload.get("provider")).strip() if payload.get("provider") else None,
        provider_message_id=(
            str(payload.get("provider_message_id")).strip()
            if payload.get("provider_message_id")
            else None
        ),
        idempotency_key=str(payload.get("idempotency_key") or ""),
        claim_token=str(payload.get("claim_token")).strip() if payload.get("claim_token") else None,
        reconciliation_token=(
            str(payload.get("reconciliation_token")).strip()
            if payload.get("reconciliation_token")
            else None
        ),
        row_version=max(1, int(payload.get("row_version") or 1)),
        sending_started_at=payload.get("sending_started_at"),
        lease_expires_at=payload.get("lease_expires_at"),
        pending_expires_at=payload.get("pending_expires_at"),
        status=str(payload.get("status") or ""),
        error_code=str(payload.get("error_code")).strip() if payload.get("error_code") else None,
        metadata_json=dict(metadata) if isinstance(metadata, dict) else {},
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _lease_expiry(seconds: int, field: str) -> str:
    try:
        duration = int(seconds)
    except (TypeError, ValueError) as exc:
        raise OutboundEmailEventValidationError(f"{field} is invalid.") from exc
    if duration < 1 or duration > MAX_LEASE_SECONDS:
        raise OutboundEmailEventValidationError(
            f"{field} must be between 1 and {MAX_LEASE_SECONDS} seconds."
        )
    return (_utc_now() + timedelta(seconds=duration)).isoformat().replace("+00:00", "Z")


def _safe_optional_code(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if not SAFE_CODE_RE.fullmatch(normalized):
        raise OutboundEmailEventValidationError(f"{field} is invalid.")
    return normalized


def _safe_provider_message_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > MAX_PROVIDER_MESSAGE_ID_CHARS:
        raise OutboundEmailEventValidationError("Provider message id is invalid.")
    if any(ord(character) < 33 for character in normalized):
        raise OutboundEmailEventValidationError("Provider message id is invalid.")
    return normalized


class OutboundEmailEventClient(Protocol):
    def claim_event(
        self,
        *,
        request: OutboundEmailEventRequest,
        pending_expires_at: str,
    ) -> OutboundEmailEventClaim:
        ...

    def begin_send(self, *, user_id: str, event_id: str, lease_expires_at: str) -> OutboundEmailEventRecord:
        ...

    def reclaim_pending(
        self,
        *,
        user_id: str,
        event_id: str,
        lease_expires_at: str,
    ) -> OutboundEmailEventRecord:
        ...

    def complete_event(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
        status: str,
        provider: str | None,
        provider_message_id: str | None,
        error_code: str | None,
    ) -> OutboundEmailEventRecord:
        ...

    def retry_failed(
        self,
        *,
        user_id: str,
        event_id: str,
        pending_expires_at: str,
        retryable: bool,
    ) -> OutboundEmailEventRecord:
        ...

    def reconcile_expired(self, *, user_id: str, event_id: str) -> OutboundEmailEventRecord:
        ...

    def resolve_reconciliation(
        self,
        *,
        user_id: str,
        event_id: str,
        reconciliation_token: str,
        outcome: str,
        provider_state: str,
        retryable: bool,
        lease_expires_at: str | None,
        provider: str | None,
        provider_message_id: str | None,
        error_code: str | None,
    ) -> OutboundEmailEventRecord:
        ...


class SupabaseOutboundEmailEventClient:
    """Service-role client for backend-owned outbound email event RPCs."""

    def __init__(self) -> None:
        supabase_settings = get_supabase_settings().require_configured()
        if supabase_settings.service_role_key == supabase_settings.anon_key:
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        supabase_url = _validate_supabase_url(supabase_settings.supabase_url)
        self._rest_url = f"{supabase_url}/rest/v1"
        self._service_role_key = supabase_settings.service_role_key
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=SUPABASE_HTTP_POOL_SIZE,
            pool_maxsize=SUPABASE_HTTP_POOL_SIZE,
            pool_block=True,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._headers = {
            "apikey": supabase_settings.service_role_key,
            "Authorization": f"Bearer {supabase_settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_error_payload(self, response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _safe_error_code(self, response: requests.Response) -> str:
        value = str(self._safe_error_payload(response).get("code") or "").strip()
        return value[:80] if SAFE_CODE_RE.fullmatch(value) else "unavailable"

    def _safe_error_message(self, response: requests.Response) -> str:
        value = str(self._safe_error_payload(response).get("message") or "").strip()
        return re.sub(r"\s+", " ", value)[:240] if value else "unavailable"

    def _log_failure(self, operation: str, response: requests.Response) -> None:
        logger.error(
            "Outbound email event failure: operation=%s status=%s error_code=%s message=%s",
            operation,
            response.status_code,
            self._safe_error_code(response),
            self._safe_error_message(response),
        )

    def _raise_response(self, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(operation, response)
        code = self._safe_error_code(response)
        if code == "P0002":
            raise OutboundEmailEventConflictError("Outbound email event claim is no longer active.")
        if code == "P0001":
            raise OutboundEmailEventConflictError("Outbound email event state changed. Please retry.")
        raise OutboundEmailEventError(SAFE_FAILURE_MESSAGE)

    def _rpc(self, function: str, payload: dict[str, object]) -> dict[str, Any]:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/{function}",
                headers={**self._headers, "Prefer": "return=representation"},
                json=payload,
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error(
                "Outbound email event failure: operation=%s status=request_error error_type=%s",
                function,
                type(exc).__name__,
            )
            raise OutboundEmailEventError(SAFE_FAILURE_MESSAGE) from exc
        if response.status_code != 200:
            self._raise_response(function, response)
        data = response.json()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise OutboundEmailEventError(SAFE_FAILURE_MESSAGE)
        return data[0]

    @staticmethod
    def _record_from_rpc_result(payload: Mapping[str, Any]) -> OutboundEmailEventRecord:
        record = _record_from_payload(payload)
        if not record.id:
            raise OutboundEmailEventError(SAFE_FAILURE_MESSAGE)
        return record

    def claim_event(
        self,
        *,
        request: OutboundEmailEventRequest,
        pending_expires_at: str,
    ) -> OutboundEmailEventClaim:
        result = self._rpc(
            "claim_outbound_email_event",
            {
                "p_user_id": request.user_id,
                "p_session_id": request.session_id,
                "p_email_type": request.email_type,
                "p_recipient_email": request.recipient_email,
                "p_idempotency_key": request.idempotency_key,
                "p_metadata_json": request.safe_metadata,
                "p_pending_expires_at": pending_expires_at,
            },
        )
        return OutboundEmailEventClaim(
            event=self._record_from_rpc_result(result),
            replayed=bool(result.get("replayed")),
            conflict_reason=str(result.get("conflict_reason")).strip()
            if result.get("conflict_reason")
            else None,
        )

    def begin_send(self, *, user_id: str, event_id: str, lease_expires_at: str) -> OutboundEmailEventRecord:
        result = self._rpc(
            "begin_outbound_email_event_send",
            {"p_user_id": user_id, "p_event_id": event_id, "p_lease_expires_at": lease_expires_at},
        )
        return self._record_from_rpc_result(result)

    def reclaim_pending(
        self,
        *,
        user_id: str,
        event_id: str,
        lease_expires_at: str,
    ) -> OutboundEmailEventRecord:
        result = self._rpc(
            "reclaim_outbound_email_event_pending",
            {"p_user_id": user_id, "p_event_id": event_id, "p_lease_expires_at": lease_expires_at},
        )
        return self._record_from_rpc_result(result)

    def complete_event(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
        status: str,
        provider: str | None,
        provider_message_id: str | None,
        error_code: str | None,
    ) -> OutboundEmailEventRecord:
        result = self._rpc(
            "complete_outbound_email_event",
            {
                "p_user_id": user_id,
                "p_event_id": event_id,
                "p_claim_token": claim_token,
                "p_status": status,
                "p_provider": provider,
                "p_provider_message_id": provider_message_id,
                "p_error_code": error_code,
            },
        )
        return self._record_from_rpc_result(result)

    def retry_failed(
        self,
        *,
        user_id: str,
        event_id: str,
        pending_expires_at: str,
        retryable: bool,
    ) -> OutboundEmailEventRecord:
        result = self._rpc(
            "retry_outbound_email_event",
            {
                "p_user_id": user_id,
                "p_event_id": event_id,
                "p_pending_expires_at": pending_expires_at,
                "p_retryable": retryable,
            },
        )
        return self._record_from_rpc_result(result)

    def reconcile_expired(self, *, user_id: str, event_id: str) -> OutboundEmailEventRecord:
        result = self._rpc(
            "reconcile_outbound_email_event",
            {"p_user_id": user_id, "p_event_id": event_id},
        )
        return self._record_from_rpc_result(result)

    def resolve_reconciliation(
        self,
        *,
        user_id: str,
        event_id: str,
        reconciliation_token: str,
        outcome: str,
        provider_state: str,
        retryable: bool,
        lease_expires_at: str | None,
        provider: str | None,
        provider_message_id: str | None,
        error_code: str | None,
    ) -> OutboundEmailEventRecord:
        result = self._rpc(
            "resolve_outbound_email_event_reconciliation",
            {
                "p_user_id": user_id,
                "p_event_id": event_id,
                "p_reconciliation_token": reconciliation_token,
                "p_outcome": outcome,
                "p_provider_state": provider_state,
                "p_retryable": retryable,
                "p_lease_expires_at": lease_expires_at,
                "p_provider": provider,
                "p_provider_message_id": provider_message_id,
                "p_error_code": error_code,
            },
        )
        return self._record_from_rpc_result(result)


class OutboundEmailEventService:
    """Validates and coordinates the backend-only event lifecycle."""

    def __init__(self, *, client: OutboundEmailEventClient | None = None) -> None:
        self._client = client or SupabaseOutboundEmailEventClient()

    def reserve(
        self,
        *,
        user_id: str,
        session_id: str | None,
        email_type: str,
        recipient_email: str,
        idempotency_key: str,
        safe_metadata: Mapping[str, object] | None = None,
        pending_lease_seconds: int = DEFAULT_PENDING_LEASE_SECONDS,
    ) -> OutboundEmailEventClaim:
        request = OutboundEmailEventRequest(
            user_id=user_id,
            session_id=session_id,
            email_type=email_type,
            recipient_email=recipient_email,
            idempotency_key=idempotency_key,
            safe_metadata=safe_metadata or {},
        )
        return self._client.claim_event(
            request=request,
            pending_expires_at=_lease_expiry(pending_lease_seconds, "pending_lease_seconds"),
        )

    def begin_send(
        self,
        *,
        user_id: str,
        event_id: str,
        sending_lease_seconds: int = DEFAULT_SENDING_LEASE_SECONDS,
    ) -> OutboundEmailEventRecord:
        return self._client.begin_send(
            user_id=user_id,
            event_id=event_id,
            lease_expires_at=_lease_expiry(sending_lease_seconds, "sending_lease_seconds"),
        )

    def reclaim_pending(
        self,
        *,
        user_id: str,
        event_id: str,
        sending_lease_seconds: int = DEFAULT_SENDING_LEASE_SECONDS,
    ) -> OutboundEmailEventRecord:
        return self._client.reclaim_pending(
            user_id=user_id,
            event_id=event_id,
            lease_expires_at=_lease_expiry(sending_lease_seconds, "sending_lease_seconds"),
        )

    def mark_sent(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
        provider: str | None = None,
        provider_message_id: str | None = None,
    ) -> OutboundEmailEventRecord:
        return self._complete(
            user_id=user_id,
            event_id=event_id,
            claim_token=claim_token,
            status="sent",
            provider=provider,
            provider_message_id=provider_message_id,
            error_code=None,
        )

    def mark_failed(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
        error_code: str,
        provider: str | None = None,
    ) -> OutboundEmailEventRecord:
        return self._complete(
            user_id=user_id,
            event_id=event_id,
            claim_token=claim_token,
            status="failed",
            provider=provider,
            provider_message_id=None,
            error_code=error_code,
        )

    def cancel(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
    ) -> OutboundEmailEventRecord:
        return self._complete(
            user_id=user_id,
            event_id=event_id,
            claim_token=claim_token,
            status="canceled",
            provider=None,
            provider_message_id=None,
            error_code=None,
        )

    def retry_failed(
        self,
        *,
        user_id: str,
        event_id: str,
        retryable: bool,
        pending_lease_seconds: int = DEFAULT_PENDING_LEASE_SECONDS,
    ) -> OutboundEmailEventRecord:
        if not retryable:
            raise OutboundEmailEventConflictError("Permanent email failures are not retryable.")
        return self._client.retry_failed(
            user_id=user_id,
            event_id=event_id,
            pending_expires_at=_lease_expiry(pending_lease_seconds, "pending_lease_seconds"),
            retryable=retryable,
        )

    def reconcile_expired(self, *, user_id: str, event_id: str) -> OutboundEmailEventRecord:
        return self._client.reconcile_expired(user_id=user_id, event_id=event_id)

    def resolve_reconciliation(
        self,
        *,
        user_id: str,
        event_id: str,
        reconciliation_token: str,
        outcome: str,
        provider_state: str,
        retryable: bool = False,
        provider: str | None = None,
        provider_message_id: str | None = None,
        error_code: str | None = None,
        sending_lease_seconds: int = DEFAULT_SENDING_LEASE_SECONDS,
    ) -> OutboundEmailEventRecord:
        if outcome not in RECONCILIATION_OUTCOMES:
            raise OutboundEmailEventValidationError("Reconciliation outcome is invalid.")
        if provider_state not in PROVIDER_STATES:
            raise OutboundEmailEventValidationError("Provider state is invalid.")
        if outcome == "sent" and provider_state != "sent":
            raise OutboundEmailEventConflictError("Reconciliation cannot mark an unconfirmed event sent.")
        if outcome == "failed" and provider_state != "permanent_failure":
            raise OutboundEmailEventConflictError("Only confirmed permanent failures can be marked failed.")
        if outcome == "retry" and (provider_state != "not_sent" or not retryable):
            raise OutboundEmailEventConflictError("Only confirmed retryable failures can be retried.")
        if outcome == "retry_blocked" and provider_state != "unknown":
            raise OutboundEmailEventConflictError("retry_blocked requires unknown provider state.")
        lease_expires_at = (
            _lease_expiry(sending_lease_seconds, "sending_lease_seconds") if outcome == "retry" else None
        )
        return self._client.resolve_reconciliation(
            user_id=user_id,
            event_id=event_id,
            reconciliation_token=reconciliation_token,
            outcome=outcome,
            provider_state=provider_state,
            retryable=retryable,
            lease_expires_at=lease_expires_at,
            provider=provider,
            provider_message_id=_safe_provider_message_id(provider_message_id),
            error_code=_safe_optional_code(error_code, field="error_code"),
        )

    def _complete(
        self,
        *,
        user_id: str,
        event_id: str,
        claim_token: str,
        status: str,
        provider: str | None,
        provider_message_id: str | None,
        error_code: str | None,
    ) -> OutboundEmailEventRecord:
        if status not in {"sent", "failed", "canceled"}:
            raise OutboundEmailEventValidationError("Event completion status is invalid.")
        token = str(claim_token or "").strip()
        if not token:
            raise OutboundEmailEventValidationError("Claim token is required.")
        return self._client.complete_event(
            user_id=user_id,
            event_id=event_id,
            claim_token=token,
            status=status,
            provider=str(provider).strip()[:80] if provider else None,
            provider_message_id=_safe_provider_message_id(provider_message_id),
            error_code=_safe_optional_code(error_code, field="error_code"),
        )


def build_outbound_email_event_service(
    client: OutboundEmailEventClient | None = None,
) -> OutboundEmailEventService:
    return OutboundEmailEventService(client=client)
