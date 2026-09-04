from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.email.event_store import (
    OutboundEmailEventClaim,
    OutboundEmailEventConflictError,
    OutboundEmailEventRecord,
    OutboundEmailEventService,
    OutboundEmailEventValidationError,
)


def _future_iso(seconds: int = 300) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _past_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")


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
        if event.user_id != user_id or event.status != "pending" or not event.pending_expires_at or event.pending_expires_at > _past_iso():
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
        key, event = self._find(event_id)
        if event.user_id != user_id or event.status != "needs_reconciliation" or event.reconciliation_token != reconciliation_token:
            raise OutboundEmailEventConflictError("reconciliation claim is no longer active")
        if outcome == "retry":
            updated = replace(event, status="sending", claim_token=f"new-{event_id}", reconciliation_token=None, lease_expires_at=lease_expires_at)
        else:
            updated = replace(event, status=outcome, reconciliation_token=None, provider=provider, provider_message_id=provider_message_id, error_code=error_code)
        self.records[key] = updated
        return updated


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

    client.records[key] = replace(stored, pending_expires_at=_past_iso())
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
