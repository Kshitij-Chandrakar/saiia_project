from dataclasses import dataclass
import logging
from typing import Any, NoReturn

import requests

from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings

logger = logging.getLogger("supabase_profile_bootstrap")


class SupabaseProfileBootstrapError(RuntimeError):
    """Raised when Supabase profile bootstrap cannot complete."""


@dataclass(frozen=True)
class ProfileBootstrapResult:
    user_id: str
    profile_exists: bool
    profile_created: bool
    settings_exists: bool
    settings_created: bool
    next_step: str


class SupabaseRestClient:
    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            logger.error(
                "Supabase profile bootstrap is misconfigured: SUPABASE_SERVICE_ROLE_KEY matches SUPABASE_ANON_KEY."
            )
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        self._base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self._service_role_key = settings.service_role_key
        self._session = requests.Session()
        self._headers = {
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _safe_response_body(self, response: requests.Response) -> str:
        body = response.text[:500]
        service_role_key = getattr(self, "_service_role_key", "")
        if service_role_key:
            body = body.replace(service_role_key, "[redacted]")
        return body

    def _log_failure(self, table: str, operation: str, response: requests.Response) -> None:
        logger.error(
            "Supabase REST failure during profile bootstrap: table=%s operation=%s status=%s body=%s",
            table,
            operation,
            response.status_code,
            self._safe_response_body(response),
        )

    def _raise_for_response(self, table: str, operation: str, response: requests.Response) -> NoReturn:
        self._log_failure(table, operation, response)
        raise SupabaseProfileBootstrapError("Supabase profile bootstrap failed.")

    def _raise_for_request_error(self, table: str, operation: str, exc: requests.RequestException) -> NoReturn:
        logger.error(
            "Supabase REST failure during profile bootstrap: table=%s operation=%s status=request_error body=%s",
            table,
            operation,
            str(exc)[:500],
        )
        raise SupabaseProfileBootstrapError("Supabase profile bootstrap failed.") from exc

    def row_exists(self, table: str, user_id: str) -> bool:
        try:
            response = self._session.get(
                f"{self._base_url}/{table}",
                headers=self._headers,
                params={"user_id": f"eq.{user_id}", "select": "id", "limit": "1"},
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_for_request_error(table, "select", exc)
        if response.status_code != 200:
            self._raise_for_response(table, "select", response)
        data = response.json()
        return isinstance(data, list) and bool(data)

    def insert_user_row(self, table: str, user_id: str) -> bool:
        try:
            response = self._session.post(
                f"{self._base_url}/{table}",
                headers={**self._headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
                params={"on_conflict": "user_id"},
                json={"user_id": user_id},
                timeout=10,
            )
        except requests.RequestException as exc:
            self._raise_for_request_error(table, "upsert", exc)
        if response.status_code in {200, 201}:
            data = response.json()
            return isinstance(data, list) and bool(data)
        if response.status_code == 409:
            return False
        self._raise_for_response(table, "upsert", response)


def _ensure_user_row(client: Any, table: str, user_id: str) -> tuple[bool, bool]:
    if client.row_exists(table, user_id):
        return True, False
    created = client.insert_user_row(table, user_id)
    if not created and not client.row_exists(table, user_id):
        raise SupabaseProfileBootstrapError("Supabase profile bootstrap failed.")
    return True, created


def bootstrap_authenticated_profile(user_id: str, client: Any | None = None) -> ProfileBootstrapResult:
    rest_client = client or SupabaseRestClient()
    profile_exists, profile_created = _ensure_user_row(rest_client, "profiles", user_id)
    settings_exists, settings_created = _ensure_user_row(rest_client, "user_settings", user_id)
    return ProfileBootstrapResult(
        user_id=user_id,
        profile_exists=profile_exists,
        profile_created=profile_created,
        settings_exists=settings_exists,
        settings_created=settings_created,
        next_step="profile_setup",
    )
