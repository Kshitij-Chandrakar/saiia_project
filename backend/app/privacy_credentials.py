"""Short-lived encrypted logout capabilities, never refresh tokens or audit data."""

import base64
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.auth.supabase_auth import SupabaseAuthError, verify_supabase_token


class CredentialUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("privacy_credential_unavailable")


class CredentialBox:
    def __init__(self, keys: dict[str, bytes], current: str):
        if current not in keys or any(
            not key.isascii() or not key.isalnum() or len(key) > 32 or len(value) != 32
            for key, value in keys.items()
        ):
            raise CredentialUnavailable()
        self._keys, self._current = keys, current

    @staticmethod
    def configured() -> "CredentialBox":
        try:
            keys = json.loads(os.environ.get("C15_REVOCATION_KEYS", "{}"))
            return CredentialBox(
                {
                    key: base64.b64decode(value, validate=True)
                    for key, value in keys.items()
                },
                os.environ.get("C15_REVOCATION_CURRENT_KEY", ""),
            )
        except Exception:  # noqa: BLE001 -- configuration never appears in errors
            raise CredentialUnavailable() from None

    @staticmethod
    def aad(subject: str, request: str, version: str, expiry: int) -> bytes:
        return json.dumps(
            ["c15.logout.global.v1", subject, request, version, expiry]
        ).encode()

    def seal(
        self, token: str, subject: str, request: str, token_expiry: int
    ) -> dict[str, Any]:
        now = int(time.time())
        expiry = min(now + 300, token_expiry)
        if expiry <= now + 30 or len(token) > 16000:
            raise CredentialUnavailable()
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(self._keys[self._current]).encrypt(
            nonce, token.encode(), self.aad(subject, request, self._current, expiry)
        )
        return {
            "key_version": self._current,
            "expires_at": expiry,
            "ciphertext": base64.b64encode(nonce + encrypted).decode(),
        }

    def open(self, envelope: dict[str, Any], subject: str, request: str) -> str:
        try:
            version, expiry = envelope["key_version"], envelope["expires_at"]
            if (
                type(expiry) is not int
                or not int(time.time()) < expiry <= time.time() + 300
            ):
                raise CredentialUnavailable()
            raw = base64.b64decode(envelope["ciphertext"], validate=True)
            return (
                AESGCM(self._keys[version])
                .decrypt(
                    raw[:12], raw[12:], self.aad(subject, request, version, expiry)
                )
                .decode()
            )
        except Exception:  # noqa: BLE001 -- no token, ciphertext or crypto diagnostics
            raise CredentialUnavailable() from None


class GlobalLogout:
    """Supported /logout?scope=global, with injected HTTP for local verification."""

    def __init__(
        self,
        box: CredentialBox,
        url: str,
        api_key: str,
        post: Any,
        *,
        local_rehearsal=False,
        standalone=False,
    ):
        parsed = urlsplit(url)
        if (
            (
                parsed.scheme != "https"
                and not (
                    local_rehearsal
                    and parsed.scheme == "http"
                    and parsed.hostname in {"localhost", "127.0.0.1", "auth"}
                )
            )
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise CredentialUnavailable()
        self.box, self.url, self.api_key, self.post = (
            box,
            url.rstrip("/")
            + (
                "/logout?scope=global"
                if local_rehearsal and standalone
                else "/auth/v1/logout?scope=global"
            ),
            api_key,
            post,
        )

    def __call__(self, task: dict[str, Any], envelope: dict[str, Any]) -> str:
        try:
            token = self.box.open(envelope, task["account_id"], task["request_id"])
            user = verify_supabase_token(token)
            if user.user_id != task["account_id"] or user.role != "authenticated":
                return "credential_unavailable"
            response = self.post(
                self.url,
                headers={"apikey": self.api_key, "Authorization": "Bearer " + token},
                timeout=(3, 10),
                allow_redirects=False,
                stream=True,
            )
            # No response body is read/logged. 401/403 cannot prove global logout.
            status = response.status_code
            if getattr(response, "close", None):
                response.close()
            if status == 204:
                return "succeeded"
            return "credential_unavailable" if status in (401, 403) else "transient"
        except requests.Timeout:
            return "timeout"
        except (CredentialUnavailable, SupabaseAuthError):
            return "credential_unavailable"
        except Exception:  # noqa: BLE001 -- provider/verification failures stay opaque
            return "transient"


class AuthSoftDeleteRecovery:
    """Private supported Auth API recovery, retaining the UUID/FK tombstone.

    This is separately injected authority, never a user token or public endpoint.
    The callbacks must call only the fixed local/approved Auth admin user path,
    with bounded timeouts, no redirects and private credentials. No request/body
    is logged. Billing-contact exceptions fail closed before any API mutation.
    """

    def __init__(self, connect, delete_user, get_user, observe):
        self.connect, self.delete_user, self.get_user, self.observe = (
            connect,
            delete_user,
            get_user,
            observe,
        )

    def __call__(self, task):
        from uuid import UUID

        account = str(UUID(task["account_id"]))
        request = str(UUID(task["request_id"]))
        lease = str(UUID(task["lease_id"]))
        try:
            with self.connect() as c:
                allowed = c.execute(
                    "select public.privacy_auth_recovery_scope(%s,%s,%s)",
                    (request, lease, account),
                ).fetchone()[0]
                if allowed is not True:
                    return "credential_unavailable"
            # Recheck accepted scope after waiting for an uncertain API outcome.
            # A genuine soft-delete state plus authoritative absence is positive
            # recovery evidence. A 401 alone is never evidence of revocation.
            state = self.get_user(account)
            if not state.get("deleted_at"):
                if self.delete_user(account) is not True:
                    return "transient"
                state = self.get_user(account)
            if (
                str(state.get("id")) != account
                or not state.get("deleted_at")
                or state.get("user_metadata")
                or state.get("app_metadata")
            ):
                return "transient"
            return "succeeded" if self.observe(task) is True else "transient"
        except requests.Timeout:
            return "timeout"
        except Exception:  # noqa: BLE001 -- never expose Auth bodies or credentials
            return "transient"


class PrivateAuthAdmin:
    """Only supported user read/soft-delete, with private caller-owned authority."""

    def __init__(
        self, base_url, service_key, *, local_rehearsal=False, standalone=False
    ):
        parsed = urlsplit(base_url)
        local = (
            local_rehearsal
            and parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "auth"}
        )
        if (
            parsed.scheme != "https"
            and not local
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or not parsed.hostname
            or not service_key
        ):
            raise CredentialUnavailable()
        self.base = (
            base_url.rstrip("/")
            + (
                ""
                if local_rehearsal and (parsed.hostname == "auth" or standalone)
                else "/auth/v1"
            )
            + "/admin/users/"
        )
        self.key = service_key
        self.http = requests.Session()
        self.http.trust_env = False

    def get_user(self, account):
        from uuid import UUID

        with self.http.get(
            self.base + str(UUID(account)),
            headers={"Authorization": "Bearer " + self.key, "apikey": self.key},
            timeout=(3, 10),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise CredentialUnavailable()
            raw = bytearray()
            for chunk in response.iter_content(4096):
                if len(raw) + len(chunk) > 65536:
                    raise CredentialUnavailable()
                raw.extend(chunk)
            return json.loads(raw)

    def soft_delete(self, account):
        from uuid import UUID

        with self.http.delete(
            self.base + str(UUID(account)),
            json={"should_soft_delete": True},
            headers={"Authorization": "Bearer " + self.key, "apikey": self.key},
            timeout=(3, 10),
            allow_redirects=False,
            stream=True,
        ) as response:
            return response.status_code == 200
