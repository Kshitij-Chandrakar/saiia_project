"""Caller-only admin verification and internal validation, never catalog writes."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

import requests
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request

from app.auth.supabase_auth import _bearer_token_from_request, get_current_user
from app.cloud.supabase_config import get_supabase_settings
from app.commercial import catalog_contract as c
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, RpcFailure

PROBE_RPC = "subscription_admin_self_probe"
MANAGE = "subscriptions.manage"
_ID = TypeAdapter(c.Identifier)
_REVISION = TypeAdapter(c.Positive)


class AdminAccess(c.FrozenDocument):
    permissions: tuple[Literal["subscriptions.manage"], ...] = ()


@dataclass(frozen=True)
class VerifiedActor:
    """Server context only; Python construction itself is not an auth boundary."""

    subject_id: str
    _bearer: str = field(repr=False, compare=False)


def verified_actor(request: Request) -> VerifiedActor:
    user = get_current_user(request)
    try:
        subject = _ID.validate_python(user.user_id, strict=True)
    except ValidationError:
        raise HTTPException(
            401,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return VerifiedActor(subject, _bearer_token_from_request(request))


class ReadOnlyProbeRpc:
    """Original verified bearer + public key; never service-key/actor substitution.

    Constructor performs no I/O. Allowlist cannot call any catalog adapter RPC.
    """

    def __init__(self, url: str, anon_key: str, actor: VerifiedActor):
        try:
            parsed = urlsplit(url)
            parsed.port
        except (ValueError, TypeError):
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and not local)
            or not anon_key
            or anon_key.startswith("sb_secret_")
        ):
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        self._url = url.rstrip("/") + "/rest/v1/rpc/" + PROBE_RPC
        self._key = anon_key
        self._actor = actor

    def __call__(self, name: str, params: dict[str, object]) -> object:
        if name != PROBE_RPC or params != {}:
            raise RpcFailure("42501", dispatched=False)
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.post(
                    self._url,
                    json={},
                    headers={
                        "apikey": self._key,
                        "Authorization": "Bearer " + self._actor._bearer,
                        "Accept": "application/json",
                        "Cache-Control": "no-store",
                    },
                    timeout=(3, 5),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if response.status_code != 200:
                        raise CatalogStoreError(ErrorCode.UNAVAILABLE)
                    content = bytearray()
                    for chunk in response.iter_content(4096):
                        content.extend(chunk)
                        if len(content) > 8192:
                            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
                    return json.loads(content)
        except (requests.RequestException, ValueError):
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None


def probe_transport(actor: VerifiedActor) -> ReadOnlyProbeRpc:
    """Lazy configured read-only composition, no cache or permission fallback."""
    config = get_supabase_settings()
    if (
        not config.cloud_enabled
        or not config.supabase_url
        or not config.anon_key
        or config.anon_key == config.service_role_key
    ):
        raise CatalogStoreError(ErrorCode.UNAVAILABLE)
    return ReadOnlyProbeRpc(config.supabase_url, config.anon_key, actor)


class AdminBoundary:
    def __init__(
        self, actor: VerifiedActor, rpc: Callable[[str, dict[str, object]], object]
    ):
        self.actor = actor
        self._rpc = rpc

    def access(self) -> AdminAccess:
        try:
            row = self._rpc(PROBE_RPC, {})
            if (
                not isinstance(row, dict)
                or set(row)
                != {
                    "contract_version",
                    "subject_id",
                    "permissions",
                    "permission_revision",
                }
                or row["contract_version"] != "admin.access.v1"
                or row["subject_id"] != self.actor.subject_id
            ):
                raise ValueError
            result = AdminAccess(permissions=row["permissions"])
            if result.permissions == (MANAGE,):
                _REVISION.validate_python(row["permission_revision"], strict=True)
            elif result.permissions or row["permission_revision"] is not None:
                raise ValueError
            return result
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    def validate_draft(
        self, payload: object, *, model_keys: frozenset[str] = frozenset()
    ) -> c.ValidationReport:
        """Internal only. Fresh read gate; bounded JSON work; zero persistence."""
        if MANAGE not in self.access().permissions:
            raise CatalogStoreError(ErrorCode.DENIED)
        return validate_bounded_draft(payload, model_keys=model_keys)


def bounded_json(payload: object) -> object:
    """Shared pure validation bounds; supplies no authorization."""
    try:
        data = (
            payload.model_dump(mode="json")
            if isinstance(payload, c.CatalogDraft)
            else payload
        )
        pending = [(data, 0)]
        nodes = 0
        text_bytes = 0
        while pending:
            value, depth = pending.pop()
            nodes += 1
            if nodes > 4096 or depth > 32:
                raise ValueError
            if isinstance(value, dict):
                if len(value) > 4096 or any(type(k) is not str for k in value):
                    raise ValueError
                text_bytes += sum(len(k.encode("utf-8")) for k in value)
                pending.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, (list, tuple)):
                if len(value) > 4096:
                    raise ValueError
                pending.extend((v, depth + 1) for v in value)
            elif isinstance(value, str):
                if len(value) > 131072:
                    raise ValueError
                text_bytes += len(value.encode("utf-8"))
            if text_bytes > 131072:
                raise ValueError
        if len(json.dumps(data, allow_nan=False).encode("utf-8")) > 131072:
            raise ValueError
        return data
    except (ValueError, TypeError, RecursionError):
        raise CatalogStoreError(ErrorCode.INVALID) from None


def validate_bounded_draft(
    payload: object, *, model_keys: frozenset[str] = frozenset()
) -> c.ValidationReport:
    return c.validate_draft(bounded_json(payload), model_keys=model_keys)


def http_error(error: CatalogStoreError) -> HTTPException:
    """Only stable catalog codes, never original exceptions/SQL/payloads."""
    status = {
        ErrorCode.DENIED: 403,
        ErrorCode.INVALID: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.IDENTITY_CONFLICT: 409,
        ErrorCode.REVIEW_STALE: 409,
        ErrorCode.NOT_PUBLISHABLE: 409,
    }.get(error.code, 503)
    return HTTPException(status, detail={"code": error.code.value})
