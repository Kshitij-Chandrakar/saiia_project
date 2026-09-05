from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from app.email.event_store import (
    OutboundEmailEventClaim,
    OutboundEmailEventConflictError,
    OutboundEmailEventError,
    OutboundEmailEventRecord,
    OutboundEmailEventService,
    OutboundEmailEventValidationError,
    OutboundEmailEventRequest,
    SupabaseOutboundEmailEventClient,
)
from app.email.provider import EmailSendRequest, EmailSendResult
from app.email.service import (
    EmailService,
    send_ai_notes_ready_email_dry_run,
    send_session_summary_email_dry_run,
    send_transcript_export_email_dry_run,
    send_welcome_email_dry_run,
)


def _future_iso(seconds: int = 300) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _past_iso(seconds: int = 300) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _record(
    *,
    event_id: str = "event-1",
    session_id: str | None = None,
    status: str = "pending",
    claim_token: str | None = None,
    reconciliation_token: str | None = None,
    pending_expires_at: str | None = None,
    lease_expires_at: str | None = None,
) -> OutboundEmailEventRecord:
    return OutboundEmailEventRecord(
        id=event_id,
        user_id="user-1",
        session_id=session_id,
        email_type="ai_notes_ready",
        recipient_email="mentor@example.com",
        provider=None,
        provider_message_id=None,
        idempotency_key="notes-1",
        claim_token=claim_token,
        reconciliation_token=reconciliation_token,
        row_version=1,
        sending_started_at=None,
        lease_expires_at=lease_expires_at,
        pending_expires_at=pending_expires_at,
        status=status,
        error_code=None,
        metadata_json={},
        created_at="2026-09-04T00:00:00Z",
        updated_at="2026-09-04T00:00:00Z",
    )


class FakeEventClient:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str, str | None, str], OutboundEmailEventRecord] = {}
        self.claim_calls: list[dict[str, object]] = []
        self.complete_calls: list[dict[str, object]] = []
        self.resolve_calls: list[dict[str, object]] = []
        self._next_id = 1

    def _key(self, request) -> tuple[str, str, str, str | None, str]:
        return (request.user_id, request.email_type, request.recipient_email, request.session_id, request.idempotency_key)

    def claim_event(self, *, request, pending_expires_at: str) -> OutboundEmailEventClaim:
        self.claim_calls.append({"request": request, "pending_expires_at": pending_expires_at})
        key = self._key(request)
        existing = self.records.get(key)
        if existing is not None:
            return OutboundEmailEventClaim(
                event=existing,
                replayed=existing.status == "sent",
                conflict_reason=None if existing.status == "sent" else "already_processing",
            )
        event = replace(
            _record(event_id=f"event-{self._next_id}", session_id=request.session_id, pending_expires_at=pending_expires_at),
            user_id=request.user_id,
            email_type=request.email_type,
            recipient_email=request.recipient_email,
            idempotency_key=request.idempotency_key,
            metadata_json=dict(request.safe_metadata),
        )
        self._next_id += 1
        self.records[key] = event
        return OutboundEmailEventClaim(event=event, replayed=False)

    def _find(self, event_id: str) -> tuple[tuple[str, str, str, str | None, str], OutboundEmailEventRecord]:
        for key, event in self.records.items():
            if event.id == event_id:
                return key, event
        raise AssertionError(f"unknown event: {event_id}")

    def begin_send(self, *, user_id: str, event_id: str, lease_expires_at: str) -> OutboundEmailEventRecord:
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "pending":
            raise OutboundEmailEventConflictError("event is not claimable")
        updated = replace(event, status="sending", claim_token=f"claim-{event_id}", lease_expires_at=lease_expires_at)
        self.records[key] = updated
        return updated

    def reclaim_pending(self, *, user_id: str, event_id: str, lease_expires_at: str) -> OutboundEmailEventRecord:
        key, event = self._find(event_id)
        try:
            pending_expires_at = datetime.fromisoformat(
                (event.pending_expires_at or "").replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            raise OutboundEmailEventConflictError("pending lease is not expired")
        if pending_expires_at.tzinfo is None:
            pending_expires_at = pending_expires_at.replace(tzinfo=timezone.utc)
        if (
            event.user_id != user_id
            or event.status != "pending"
            or not event.pending_expires_at
            or not pending_expires_at < datetime.now(timezone.utc)
        ):
            raise OutboundEmailEventConflictError("pending lease is not expired")
        updated = replace(event, status="sending", claim_token=f"claim-{event_id}", lease_expires_at=lease_expires_at)
        self.records[key] = updated
        return updated

    def complete_event(self, *, user_id: str, event_id: str, claim_token: str, status: str, provider: str | None, provider_message_id: str | None, error_code: str | None) -> OutboundEmailEventRecord:
        self.complete_calls.append({"event_id": event_id, "claim_token": claim_token, "status": status})
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "sending" or event.claim_token != claim_token:
            raise OutboundEmailEventConflictError("event claim is no longer active")
        updated = replace(
            event,
            status=status,
            provider=provider,
            provider_message_id=provider_message_id,
            error_code=error_code,
            claim_token=None,
            lease_expires_at=None,
        )
        self.records[key] = updated
        return updated

    def retry_failed(self, *, user_id: str, event_id: str, pending_expires_at: str, retryable: bool) -> OutboundEmailEventRecord:
        if not retryable:
            raise OutboundEmailEventConflictError("permanent failure")
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "failed":
            raise OutboundEmailEventConflictError("event is not retryable")
        updated = replace(event, status="pending", pending_expires_at=pending_expires_at, error_code=None)
        self.records[key] = updated
        return updated

    def reconcile_expired(self, *, user_id: str, event_id: str) -> OutboundEmailEventRecord:
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "sending":
            raise OutboundEmailEventConflictError("event is not reconcilable")
        updated = replace(event, status="needs_reconciliation", claim_token=None, reconciliation_token=f"reconcile-{event_id}")
        self.records[key] = updated
        return updated

    def resolve_reconciliation(self, *, user_id: str, event_id: str, reconciliation_token: str, outcome: str, provider_state: str, retryable: bool, lease_expires_at: str | None, provider: str | None, provider_message_id: str | None, error_code: str | None) -> OutboundEmailEventRecord:
        self.resolve_calls.append({"outcome": outcome, "provider_state": provider_state})
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "needs_reconciliation" or event.reconciliation_token != reconciliation_token:
            raise OutboundEmailEventConflictError("reconciliation claim is no longer active")
        if outcome == "retry":
            updated = replace(event, status="sending", claim_token=f"new-{event_id}", reconciliation_token=None, lease_expires_at=lease_expires_at)
        else:
            updated = replace(event, status=outcome, reconciliation_token=None, provider=provider, provider_message_id=provider_message_id, error_code=error_code)
        self.records[key] = updated
        return updated


class CountingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error
        self.requests: list[EmailSendRequest] = []

    def send_email(self, request: EmailSendRequest) -> EmailSendResult:
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return EmailSendResult(
            status="dry_run",
            provider="dry_run",
            message_id="dry-run",
            dry_run=True,
            recipient_masked="m***@example.com",
            email_type=request.email_type,
            created_at="2026-09-04T00:00:00Z",
        )


def _event_kwargs(*, idempotency_key: str = "email-1") -> dict[str, object]:
    return {
        "email_type": "ai_notes_ready",
        "user_id": "user-1",
        "session_id": "session-1",
        "recipient_email": "mentor@example.com",
        "idempotency_key": idempotency_key,
    }


def _send_kwargs(*, idempotency_key: str = "email-1") -> dict[str, object]:
    return {"subject": "Interview notes ready", **_event_kwargs(idempotency_key=idempotency_key)}


class FakeRpcResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> list[dict[str, object]]:
        return [self.payload]


class FakeRpcSession:
    def __init__(self, responses: list[FakeRpcResponse]) -> None:
        self.responses = responses
        self.post_calls: list[dict[str, object]] = []
        self.get_calls = 0

    def post(self, url: str, **kwargs: object) -> FakeRpcResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self.responses.pop(0)

    def get(self, *args: object, **kwargs: object) -> None:
        self.get_calls += 1
        raise AssertionError("atomic lifecycle RPC wrapper performed a follow-up select")


def test_reserve_uses_null_safe_scope_and_keeps_session_scopes_separate() -> None:
    client = FakeEventClient()
    service = OutboundEmailEventService(client=client)

    first = service.reserve(
        user_id="user-1",
        session_id=None,
        email_type="welcome",
        recipient_email="mentor@example.com",
        idempotency_key="welcome-1",
    )
    replay = service.reserve(
        user_id="user-1",
        session_id=None,
        email_type="welcome",
        recipient_email="mentor@example.com",
        idempotency_key="welcome-1",
    )
    session_scoped = service.reserve(
        user_id="user-1",
        session_id="session-1",
        email_type="welcome",
        recipient_email="mentor@example.com",
        idempotency_key="welcome-1",
    )

    assert first.event.id == replay.event.id
    assert replay.already_processing is True
    assert session_scoped.event.id != first.event.id
    assert client.claim_calls[0]["pending_expires_at"]


def test_supabase_lifecycle_wrappers_parse_atomic_rpc_rows_without_followup_select() -> None:
    sent_payload = asdict(
        _record(
            event_id="event-sent",
            status="sent",
        )
    )
    sent_payload.update({"provider": "dry_run", "provider_message_id": "dry-run", "replayed": True, "conflict_reason": None})
    sending_payload = asdict(
        _record(
            event_id="event-sending",
            status="sending",
            claim_token="claim-event-sending",
            lease_expires_at=_future_iso(),
            pending_expires_at=None,
        )
    )
    sending_payload.update({"replayed": False, "conflict_reason": None})
    session = FakeRpcSession([FakeRpcResponse(sent_payload), FakeRpcResponse(sending_payload)])
    client = object.__new__(SupabaseOutboundEmailEventClient)
    client._rest_url = "https://example.supabase.co/rest/v1"
    client._headers = {}
    client._session = session

    claim = client.claim_event(
        request=OutboundEmailEventRequest(
            user_id="user-1",
            session_id=None,
            email_type="welcome",
            recipient_email="mentor@example.com",
            idempotency_key="welcome-1",
            safe_metadata={},
        ),
        pending_expires_at=_future_iso(),
    )
    sending = client.begin_send(
        user_id="user-1",
        event_id="event-sending",
        lease_expires_at=_future_iso(),
    )

    assert claim.event.id == "event-sent"
    assert claim.replayed is True
    assert claim.conflict_reason is None
    assert sending.id == "event-sending"
    assert sending.status == "sending"
    assert session.get_calls == 0


def test_status_transitions_fence_stale_claims_and_permanent_failures() -> None:
    client = FakeEventClient()
    service = OutboundEmailEventService(client=client)
    event = service.reserve(
        user_id="user-1",
        session_id="session-1",
        email_type="ai_notes_ready",
        recipient_email="mentor@example.com",
        idempotency_key="notes-1",
    ).event
    sending = service.begin_send(user_id="user-1", event_id=event.id)
    failed = service.mark_failed(user_id="user-1", event_id=event.id, claim_token=sending.claim_token or "", error_code="provider_timeout")

    with pytest.raises(OutboundEmailEventConflictError, match="Permanent"):
        service.retry_failed(user_id="user-1", event_id=event.id, retryable=False)
    retried = service.retry_failed(user_id="user-1", event_id=failed.id, retryable=True)
    sending_again = service.begin_send(user_id="user-1", event_id=retried.id)
    service.mark_sent(user_id="user-1", event_id=retried.id, claim_token=sending_again.claim_token or "", provider="dry_run")

    with pytest.raises(OutboundEmailEventConflictError):
        service.mark_failed(user_id="user-1", event_id=retried.id, claim_token=sending_again.claim_token or "", error_code="late_failure")


def test_pending_reclaim_requires_present_expired_lease_and_reconciliation_fences_stale_worker() -> None:
    client = FakeEventClient()
    service = OutboundEmailEventService(client=client)
    event = service.reserve(
        user_id="user-1",
        session_id="session-1",
        email_type="session_summary",
        recipient_email="mentor@example.com",
        idempotency_key="summary-1",
    ).event
    key, stored = client._find(event.id)
    client.records[key] = replace(stored, pending_expires_at=None)

    with pytest.raises(OutboundEmailEventConflictError):
        service.reclaim_pending(user_id="user-1", event_id=event.id)

    client.records[key] = replace(stored, pending_expires_at=_past_iso(10))
    sending = service.reclaim_pending(user_id="user-1", event_id=event.id)
    key, _ = client._find(event.id)
    client.records[key] = replace(sending, lease_expires_at=_past_iso())
    reconciled = service.reconcile_expired(user_id="user-1", event_id=event.id)

    with pytest.raises(OutboundEmailEventConflictError):
        service.resolve_reconciliation(
            user_id="user-1",
            event_id=event.id,
            reconciliation_token=reconciled.reconciliation_token or "",
            outcome="retry",
            provider_state="unknown",
            retryable=True,
        )
    blocked = service.resolve_reconciliation(
        user_id="user-1",
        event_id=event.id,
        reconciliation_token=reconciled.reconciliation_token or "",
        outcome="retry_blocked",
        provider_state="unknown",
    )
    assert blocked.status == "retry_blocked"

    with pytest.raises(OutboundEmailEventConflictError):
        service.resolve_reconciliation(
            user_id="user-1",
            event_id=event.id,
            reconciliation_token=reconciled.reconciliation_token or "",
            outcome="sent",
            provider_state="sent",
        )


@pytest.mark.parametrize("email_type", [
    "auth_signup_verification",
    "auth_password_reset",
    "auth_email_change_confirmation_future",
    "auth_magic_link_future",
])
def test_supabase_auth_email_types_are_rejected_by_backend_event_store(email_type: str) -> None:
    service = OutboundEmailEventService(client=FakeEventClient())

    with pytest.raises(OutboundEmailEventValidationError, match="backend transactional"):
        service.reserve(
            user_id="user-1",
            session_id=None,
            email_type=email_type,
            recipient_email="mentor@example.com",
            idempotency_key="auth-1",
        )


def test_event_metadata_rejects_sensitive_values_before_client_call() -> None:
    client = FakeEventClient()
    service = OutboundEmailEventService(client=client)

    with pytest.raises(OutboundEmailEventValidationError):
        service.reserve(
            user_id="user-1",
            session_id=None,
            email_type="welcome",
            recipient_email="mentor@example.com",
            idempotency_key="welcome-2",
            safe_metadata={"authorization": "Bearer secret"},
        )
    assert client.claim_calls == []


def test_retry_blocked_rejects_non_unknown_provider_state_before_client_call() -> None:
    client = FakeEventClient()
    service = OutboundEmailEventService(client=client)

    with pytest.raises(OutboundEmailEventConflictError, match="retry_blocked"):
        service.resolve_reconciliation(
            user_id="user-1",
            event_id="event-1",
            reconciliation_token="reconcile-event-1",
            outcome="retry_blocked",
            provider_state="sent",
        )

    assert client.resolve_calls == []


def test_email_service_claims_event_before_dry_run_send_and_completes_it() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    result = service.send_transactional_email(
        **_send_kwargs(),
        safe_metadata={"source": "notes"},
    )

    assert provider.calls == 1
    assert len(client.claim_calls) == 1
    event = next(iter(client.records.values()))
    assert event.status == "sent"
    assert event.metadata_json == {"source": "notes", "dry_run": True}
    assert result.event_id == event.id
    assert result.event_status == "sent"
    assert result.replayed is False


def test_welcome_dry_run_uses_deterministic_event_and_replays_without_provider_call() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    first = send_welcome_email_dry_run(
        email_service=service,
        user_id="user-1",
        recipient_email="mentor@example.com",
        display_name="Mentor",
    )
    replay = send_welcome_email_dry_run(
        email_service=service,
        user_id="user-1",
        recipient_email="mentor@example.com",
        display_name="Different name is not persisted",
    )

    assert provider.calls == 1
    assert provider.requests[0].email_type == "welcome"
    assert "Welcome to intervuAI, Mentor." in provider.requests[0].text_body
    assert first.event_id == replay.event_id
    assert replay.replayed is True
    event = next(iter(client.records.values()))
    assert event.email_type == "welcome"
    assert event.idempotency_key == "welcome:user-1"
    assert event.metadata_json == {"template_version": "welcome_v1", "dry_run": True}
    assert "Mentor" not in str(event.metadata_json)


@pytest.mark.parametrize(
    ("helper", "email_type", "idempotency_key"),
    [
        (send_ai_notes_ready_email_dry_run, "ai_notes_ready", "ai_notes_ready:user-1:session-1"),
        (send_session_summary_email_dry_run, "session_summary", "session_summary:user-1:session-1"),
        (send_transcript_export_email_dry_run, "transcript_export", "transcript_export:user-1:session-1"),
    ],
)
def test_feature_email_dry_run_helpers_use_event_idempotency_and_no_raw_content(
    helper,
    email_type: str,
    idempotency_key: str,
) -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    first = helper(
        email_service=service,
        user_id="user-1",
        session_id="session-1",
        recipient_email="mentor@example.com",
        display_name="Mentor",
        session_title="Backend practice",
        session_date="2026-09-04",
    )
    replay = helper(
        email_service=service,
        user_id="user-1",
        session_id="session-1",
        recipient_email="mentor@example.com",
        display_name="Different name is not persisted",
        session_title="Different title is not persisted",
    )

    assert provider.calls == 1
    assert provider.requests[0].email_type == email_type
    assert "Backend practice" in provider.requests[0].text_body
    assert "Question text from the transcript" not in provider.requests[0].text_body
    assert first.event_id == replay.event_id
    assert replay.replayed is True
    event = next(iter(client.records.values()))
    assert event.email_type == email_type
    assert event.idempotency_key == idempotency_key
    assert event.metadata_json == {"template_version": f"{email_type}_v1", "dry_run": True}
    assert "Backend practice" not in str(event.metadata_json)


def test_email_service_replays_sent_event_without_second_provider_call() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    service.send_transactional_email(**_send_kwargs())
    replay = service.send_transactional_email(**_send_kwargs())

    assert provider.calls == 1
    assert replay.replayed is True
    assert replay.event_status == "sent"
    assert replay.message_id == "dry-run"


def test_email_service_active_event_does_not_call_provider_again() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    event = event_service.reserve(**_event_kwargs()).event
    event_service.begin_send(user_id="user-1", event_id=event.id)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    with pytest.raises(OutboundEmailEventConflictError, match="already processing"):
        service.send_transactional_email(**_send_kwargs())

    assert provider.calls == 0


def test_email_service_reclaims_expired_pending_event_before_send() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    event = event_service.reserve(**_event_kwargs()).event
    key, stored = client._find(event.id)
    client.records[key] = replace(stored, pending_expires_at=_past_iso())
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    result = service.send_transactional_email(**_send_kwargs())

    assert provider.calls == 1
    assert result.event_status == "sent"


def test_email_service_does_not_reclaim_pending_event_without_lease() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    event = event_service.reserve(**_event_kwargs()).event
    key, stored = client._find(event.id)
    client.records[key] = replace(stored, pending_expires_at=None)
    provider = CountingProvider()
    service = EmailService(provider, event_store=event_service)

    with pytest.raises(OutboundEmailEventConflictError, match="reconciliation"):
        service.send_transactional_email(**_send_kwargs())

    assert provider.calls == 0


def test_email_service_marks_permanent_provider_failure_and_does_not_retry() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider(error=RuntimeError("provider failed"))
    service = EmailService(provider, event_store=event_service)

    with pytest.raises(OutboundEmailEventError, match="provider failed"):
        service.send_transactional_email(**_send_kwargs())

    with pytest.raises(OutboundEmailEventConflictError, match="Permanent"):
        service.send_transactional_email(**_send_kwargs(), retry_failed=True)

    event = next(iter(client.records.values()))
    assert event.status == "failed"
    assert event.error_code == "provider_error"
    assert provider.calls == 1


def test_email_service_retries_explicitly_retryable_provider_failure() -> None:
    client = FakeEventClient()
    event_service = OutboundEmailEventService(client=client)
    provider = CountingProvider(error=TimeoutError("provider timeout"))
    service = EmailService(provider, event_store=event_service)

    with pytest.raises(OutboundEmailEventError, match="provider failed"):
        service.send_transactional_email(**_send_kwargs())

    provider.error = None
    result = service.send_transactional_email(**_send_kwargs(), retry_failed=True)

    assert provider.calls == 2
    assert result.event_status == "sent"
