"""Opt-in, one-task revocation runner. No provider client or scheduler installed.

The injected revoker must use a supported global-refresh-session API, bounded
network timeouts (<30s), and return only the allowlisted outcome. A user UUID is
NOT a Supabase logout credential. Production credential composition is blocked.
"""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.commercial.account_entitlements import json_query
from app.commercial.draft_service import DraftService


class RevocationWorker:
    def __init__(
        self,
        connect: Callable[[], Any],
        revoke: Callable[[str], str] | None = None,
        *,
        logout: Any = None,
        verify: Callable[[dict[str, Any]], bool] | None = None,
        recover: Callable[[dict[str, Any]], str] | None = None,
    ):
        self.channel = DraftService(connect)
        self.revoke = revoke
        self.logout = logout
        self.verify = verify
        self.recover = recover

    def call(self, action: str, document: dict[str, Any]) -> dict[str, Any]:
        return self.channel._transaction(
            True,
            lambda query: json_query(
                query,
                "SELECT public.privacy_revocation_call(%s,%s::jsonb)",
                (action, json.dumps(document)),
            ),
        )

    def run_one(self) -> bool:
        task = self.call("claim", {"lease_id": str(uuid4())})
        if not task:
            return False
        try:
            if self.logout is not None:
                envelope = self.call("credential", task)
                outcome = (
                    self.logout(task, envelope)
                    if envelope
                    else "credential_unavailable"
                )
            else:
                outcome = (
                    self.revoke(task["account_id"])
                    if self.revoke
                    else "credential_unavailable"
                )
        except TimeoutError:
            outcome = "timeout"
        except Exception:  # noqa: BLE001 -- never record provider errors/credentials
            outcome = "transient"
        if outcome != "succeeded" and self.verify is not None:
            try:
                # A separate restricted authoritative observation can prove
                # absence after a lost acknowledgement. Never infer it from 401.
                if self.verify(task) is True:
                    outcome = "succeeded"
            except Exception:  # noqa: BLE001 -- observations fail closed
                outcome = (
                    outcome
                    if outcome in {"timeout", "transient"}
                    else "credential_unavailable"
                )
        if outcome != "succeeded" and self.recover is not None:
            try:
                outcome = self.recover(task)
            except Exception:  # noqa: BLE001 -- durable bounded recovery, no payload errors
                outcome = "transient"
        if outcome not in {
            "succeeded",
            "transient",
            "timeout",
            "credential_unavailable",
        }:
            outcome = "transient"
        self.call("finish", {**task, "outcome": outcome})
        return True


def configured_worker(
    connect: Callable[[], Any],
    *,
    observer_connect: Callable[[], Any] | None = None,
    recover: Callable[[dict[str, Any]], str] | None = None,
) -> RevocationWorker | None:
    """Explicit opt-in composition; missing configuration makes no Auth call."""
    from app.config import settings

    if (
        getattr(settings, "C15_REVOCATION_ENABLED", "false") != "true"
        or getattr(settings, "C15_RESTRICTIONS_REQUIRED", "false") != "true"
    ):
        return None
    import requests

    from app.cloud.supabase_config import get_supabase_settings
    from app.privacy_credentials import CredentialBox, GlobalLogout

    try:
        box = CredentialBox.configured()
    except Exception:
        if recover is None:
            raise
        return RevocationWorker(
            connect,
            verify=SessionRevocationObserver(observer_connect)
            if observer_connect
            else None,
            recover=recover,
        )
    config = get_supabase_settings().require_configured()
    session = requests.Session()
    session.trust_env = False
    return RevocationWorker(
        connect,
        recover=recover,
        verify=SessionRevocationObserver(observer_connect)
        if observer_connect
        else None,
        logout=GlobalLogout(
            box,
            config.supabase_url,
            config.anon_key,
            session.post,
        ),
    )


class SessionRevocationObserver:
    """Fixed, lease/account-bound observation, not an Auth mutation capability."""

    def __init__(self, connect: Callable[[], Any]):
        self.connect = connect

    def __call__(self, task: dict[str, Any]) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "select public.privacy_revocation_verified(%s,%s,%s)",
                (task["request_id"], task["lease_id"], task["account_id"]),
            ).fetchone()
            return bool(row and row[0] is True)
