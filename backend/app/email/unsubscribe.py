from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
import secrets
from typing import Any, Protocol
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter

from app.cloud.interview_sessions import _validate_supabase_url
from app.cloud.supabase_config import SupabaseConfigurationError, get_supabase_settings
from app.email.provider import validate_recipient_email


logger = logging.getLogger("marketing_unsubscribe")

MARKETING_UNSUBSCRIBE_SCOPE = "marketing"
MARKETING_UNSUBSCRIBE_TOKEN_BYTES = 32
DEFAULT_TOKEN_EXPIRY_SECONDS = 30 * 24 * 60 * 60
MAX_TOKEN_EXPIRY_SECONDS = 365 * 24 * 60 * 60
MAX_RAW_TOKEN_CHARS = 256
RAW_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,256}$")
TOKEN_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
SUPABASE_HTTP_POOL_SIZE = 10
SUPABASE_MUTATION_TIMEOUT = 8


class MarketingUnsubscribeError(RuntimeError):
    """Base error for backend-owned marketing unsubscribe operations."""


class MarketingUnsubscribeStorageError(MarketingUnsubscribeError):
    """Raised when token or preference storage is unavailable."""


class MarketingUnsubscribeValidationError(MarketingUnsubscribeError, ValueError):
    """Raised when server-side unsubscribe input is invalid."""


@dataclass(frozen=True, slots=True)
class CreatedMarketingUnsubscribeToken:
    """The raw token is returned only when a token is created."""

    raw_token: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class MarketingUnsubscribeResult:
    unsubscribed: bool


class MarketingUnsubscribeTokenClient(Protocol):
    def insert_token(
        self,
        *,
        user_id: str,
        recipient_email: str,
        token_hash: str,
        email_category: str,
        expires_at: str,
    ) -> None:
        ...

    def consume_token(self, *, token_hash: str) -> bool:
        ...

    def get_marketing_opt_in(self, *, user_id: str) -> bool:
        ...


def _normalize_user_id(user_id: str) -> str:
    try:
        return str(UUID(str(user_id).strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise MarketingUnsubscribeValidationError("User context is invalid.") from exc


def _normalize_raw_token(raw_token: str) -> str | None:
    if not isinstance(raw_token, str):
        return None
    value = raw_token.strip()
    if len(value) > MAX_RAW_TOKEN_CHARS or not RAW_TOKEN_RE.fullmatch(value):
        return None
    return value


def hash_unsubscribe_token(raw_token: str) -> str:
    normalized = _normalize_raw_token(raw_token)
    if normalized is None:
        raise MarketingUnsubscribeValidationError("Unsubscribe token is invalid.")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class SupabaseMarketingUnsubscribeTokenClient:
    """Service-role client for hash-only token and preference operations."""

    def __init__(self) -> None:
        settings = get_supabase_settings().require_configured()
        if settings.service_role_key == settings.anon_key:
            raise SupabaseConfigurationError("Supabase service-role configuration is not ready.")
        supabase_url = _validate_supabase_url(settings.supabase_url)
        self._rest_url = f"{supabase_url}/rest/v1"
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=SUPABASE_HTTP_POOL_SIZE,
            pool_maxsize=SUPABASE_HTTP_POOL_SIZE,
            pool_block=True,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._headers = {
            "apikey": settings.service_role_key,
            "Authorization": f"Bearer {settings.service_role_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _raise_response(self, operation: str, response: requests.Response) -> None:
        logger.error(
            "Marketing unsubscribe storage failure: operation=%s status=%s",
            operation,
            response.status_code,
        )
        raise MarketingUnsubscribeStorageError(
            "Marketing unsubscribe storage is temporarily unavailable."
        )

    def _raise_request(self, operation: str, error: Exception) -> None:
        logger.error(
            "Marketing unsubscribe storage failure: operation=%s error_type=%s",
            operation,
            type(error).__name__,
        )
        raise MarketingUnsubscribeStorageError(
            "Marketing unsubscribe storage is temporarily unavailable."
        ) from error

    def insert_token(
        self,
        *,
        user_id: str,
        recipient_email: str,
        token_hash: str,
        email_category: str,
        expires_at: str,
    ) -> None:
        try:
            response = self._session.post(
                f"{self._rest_url}/marketing_unsubscribe_tokens",
                headers={**self._headers, "Prefer": "return=minimal"},
                json={
                    "user_id": user_id,
                    "recipient_email": recipient_email,
                    "token_hash": token_hash,
                    "email_category": email_category,
                    "expires_at": expires_at,
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("insert_token", exc)
        if response.status_code not in {200, 201, 204}:
            self._raise_response("insert_token", response)

    def _rpc(self, function: str, payload: dict[str, object]) -> dict[str, Any]:
        try:
            response = self._session.post(
                f"{self._rest_url}/rpc/{function}",
                headers={**self._headers, "Prefer": "return=representation"},
                json=payload,
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request(function, exc)
        if response.status_code != 200:
            self._raise_response(function, response)
        try:
            data = response.json()
        except ValueError as exc:
            self._raise_request(function, exc)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise MarketingUnsubscribeStorageError(
                "Marketing unsubscribe storage is temporarily unavailable."
            )
        return data[0]

    def consume_token(self, *, token_hash: str) -> bool:
        result = self._rpc(
            "consume_marketing_unsubscribe_token",
            {"p_token_hash": token_hash},
        )
        return bool(result.get("unsubscribed"))

    def get_marketing_opt_in(self, *, user_id: str) -> bool:
        try:
            response = self._session.get(
                f"{self._rest_url}/user_settings",
                headers=self._headers,
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "marketing_email_opt_in",
                    "limit": "1",
                },
                timeout=SUPABASE_MUTATION_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._raise_request("read_marketing_opt_in", exc)
        if response.status_code != 200:
            self._raise_response("read_marketing_opt_in", response)
        try:
            data = response.json()
        except ValueError as exc:
            self._raise_request("read_marketing_opt_in", exc)
        if not isinstance(data, list) or not data:
            return False
        return bool(isinstance(data[0], dict) and data[0].get("marketing_email_opt_in"))


class MarketingUnsubscribeService:
    """Creates hash-only marketing opt-out tokens and consumes them safely."""

    def __init__(self, *, client: MarketingUnsubscribeTokenClient | None = None) -> None:
        self._client = client or SupabaseMarketingUnsubscribeTokenClient()

    def create_token(
        self,
        *,
        user_id: str,
        recipient_email: str,
        expires_in_seconds: int = DEFAULT_TOKEN_EXPIRY_SECONDS,
    ) -> CreatedMarketingUnsubscribeToken:
        normalized_user_id = _normalize_user_id(user_id)
        try:
            normalized_email = validate_recipient_email(recipient_email)
        except ValueError as exc:
            raise MarketingUnsubscribeValidationError("Recipient email is invalid.") from exc
        if (
            isinstance(expires_in_seconds, bool)
            or not isinstance(expires_in_seconds, int)
            or not 1 <= expires_in_seconds <= MAX_TOKEN_EXPIRY_SECONDS
        ):
            raise MarketingUnsubscribeValidationError("Token expiry is invalid.")

        raw_token = secrets.token_urlsafe(MARKETING_UNSUBSCRIBE_TOKEN_BYTES)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        ).isoformat().replace("+00:00", "Z")
        self._client.insert_token(
            user_id=normalized_user_id,
            recipient_email=normalized_email,
            token_hash=hash_unsubscribe_token(raw_token),
            email_category=MARKETING_UNSUBSCRIBE_SCOPE,
            expires_at=expires_at,
        )
        return CreatedMarketingUnsubscribeToken(raw_token=raw_token, expires_at=expires_at)

    def unsubscribe(self, *, raw_token: str) -> MarketingUnsubscribeResult:
        normalized = _normalize_raw_token(raw_token)
        if normalized is None:
            return MarketingUnsubscribeResult(unsubscribed=False)
        token_hash = hash_unsubscribe_token(normalized)
        return MarketingUnsubscribeResult(
            unsubscribed=self._client.consume_token(token_hash=token_hash),
        )

    def is_marketing_allowed(self, *, user_id: str) -> bool:
        return self._client.get_marketing_opt_in(user_id=_normalize_user_id(user_id))


def build_marketing_unsubscribe_service(
    client: MarketingUnsubscribeTokenClient | None = None,
) -> MarketingUnsubscribeService:
    return MarketingUnsubscribeService(client=client)
