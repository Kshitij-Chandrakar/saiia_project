import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from app.cloud.supabase_config import get_supabase_settings


AUTH_ERROR_DETAIL = "Invalid authentication credentials."
AUTH_CONFIG_ERROR_DETAIL = "Supabase auth verification is not configured."


class SupabaseAuthConfigurationError(RuntimeError):
    """Raised when auth verification is called without usable config."""


class SupabaseAuthError(RuntimeError):
    """Raised when a bearer token cannot be trusted."""


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None = None
    role: str | None = None
    claims: dict[str, Any] | None = None


@dataclass(frozen=True)
class AuthVerificationConfig:
    mode: str
    key: str
    issuer: str | None
    audience: str | None


def _safe_claims(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key]
        for key in ("aud", "iss", "exp", "iat")
        if key in payload
    }


def _issuer_from_url(url: str) -> str | None:
    cleaned = url.strip().rstrip("/")
    return f"{cleaned}/auth/v1" if cleaned else None


def _validated_jwks_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL)
    return url.strip()


def _parse_auth_config(raw_config: str, supabase_url: str) -> AuthVerificationConfig:
    raw = raw_config.strip()
    if not raw:
        raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL)

    issuer = _issuer_from_url(supabase_url)
    audience = "authenticated"

    if raw.startswith(("http://", "https://")):
        return AuthVerificationConfig(mode="jwks_url", key=_validated_jwks_url(raw), issuer=issuer, audience=audience)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return AuthVerificationConfig(mode="legacy_secret", key=raw, issuer=issuer, audience=audience)

    if not isinstance(parsed, dict):
        raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL)

    issuer = str(parsed.get("issuer") or issuer or "").strip() or None
    audience_value = parsed.get("audience", audience)
    audience = str(audience_value).strip() if audience_value else None

    jwks_url = str(parsed.get("jwks_url") or parsed.get("jwks_uri") or "").strip()
    if jwks_url:
        return AuthVerificationConfig(mode="jwks_url", key=_validated_jwks_url(jwks_url), issuer=issuer, audience=audience)

    if isinstance(parsed.get("keys"), list):
        return AuthVerificationConfig(mode="jwks_json", key=json.dumps(parsed), issuer=issuer, audience=audience)

    secret = str(parsed.get("jwt_secret") or parsed.get("secret") or "").strip()
    if secret:
        return AuthVerificationConfig(mode="legacy_secret", key=secret, issuer=issuer, audience=audience)

    raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL)


@lru_cache(maxsize=1)
def get_auth_verification_config() -> AuthVerificationConfig:
    settings = get_supabase_settings()
    return _parse_auth_config(settings.jwt_secret_or_jwks_config, settings.supabase_url)


@lru_cache(maxsize=4)
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _decode_with_config(token: str, config: AuthVerificationConfig) -> dict[str, Any]:
    options = {"require": ["exp", "sub"]}
    decode_kwargs: dict[str, Any] = {
        "audience": config.audience,
        "issuer": config.issuer,
        "options": options,
    }

    if config.mode == "legacy_secret":
        return jwt.decode(token, config.key, algorithms=["HS256"], **decode_kwargs)

    if config.mode == "jwks_url":
        try:
            signing_key = _get_jwks_client(config.key).get_signing_key_from_jwt(token)
        except PyJWKClientConnectionError as exc:
            raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL) from exc
        except PyJWKClientError as exc:
            raise SupabaseAuthError(AUTH_ERROR_DETAIL) from exc
        return jwt.decode(token, signing_key.key, algorithms=["RS256", "ES256"], **decode_kwargs)

    if config.mode == "jwks_json":
        header = jwt.get_unverified_header(token)
        key_id = header.get("kid")
        jwk_set = jwt.PyJWKSet.from_dict(json.loads(config.key))
        for jwk in jwk_set.keys:
            if jwk.key_id == key_id:
                return jwt.decode(token, jwk.key, algorithms=["RS256", "ES256"], **decode_kwargs)
        raise SupabaseAuthError(AUTH_ERROR_DETAIL)

    raise SupabaseAuthConfigurationError(AUTH_CONFIG_ERROR_DETAIL)


def verify_supabase_token(token: str) -> CurrentUser:
    try:
        payload = _decode_with_config(token, get_auth_verification_config())
    except SupabaseAuthConfigurationError:
        raise
    except (
        DecodeError,
        ExpiredSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidSignatureError,
        InvalidTokenError,
        SupabaseAuthError,
    ) as exc:
        raise SupabaseAuthError(AUTH_ERROR_DETAIL) from exc

    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise SupabaseAuthError(AUTH_ERROR_DETAIL)

    email = payload.get("email")
    role = payload.get("role")
    return CurrentUser(
        user_id=subject,
        email=str(email).strip() if email else None,
        role=str(role).strip() if role else None,
        claims=_safe_claims(payload),
    )


def _bearer_token_from_request(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        raise SupabaseAuthError(AUTH_ERROR_DETAIL)
    return token.strip()


def get_current_user(request: Request) -> CurrentUser:
    try:
        return verify_supabase_token(_bearer_token_from_request(request))
    except SupabaseAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=AUTH_CONFIG_ERROR_DETAIL,
        ) from exc
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_ERROR_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
