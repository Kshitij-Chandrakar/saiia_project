import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from dotenv import load_dotenv

load_dotenv()


CLOUD_MODE_ENV: Final = "SAIIA_CLOUD_MODE"

SUPABASE_REQUIRED_ENV_VARS: Final[tuple[str, ...]] = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET_OR_JWKS_CONFIG",
    "SUPABASE_RESUME_BUCKET",
    "SUPABASE_EXPORT_BUCKET",
)

_CLOUD_MODE_VALUES: Final = {"cloud", "supabase", "enabled", "true", "1"}
_LOCAL_MODE_VALUES: Final = {"", "local", "local-only", "desktop", "false", "0"}


class SupabaseConfigurationError(RuntimeError):
    """Raised when cloud mode is requested without required backend config."""


@dataclass(frozen=True, repr=False)
class SupabaseSettings:
    mode: str
    supabase_url: str
    anon_key: str
    service_role_key: str
    jwt_secret_or_jwks_config: str
    resume_bucket: str
    export_bucket: str
    missing_required: tuple[str, ...]

    @property
    def cloud_enabled(self) -> bool:
        return self.mode == "cloud"

    @property
    def configured(self) -> bool:
        return self.cloud_enabled and not self.missing_required

    def redacted_state(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "cloud_enabled": self.cloud_enabled,
            "configured": self.configured,
            "missing_required": list(self.missing_required),
            "supabase_url_configured": bool(self.supabase_url),
            "anon_key_configured": bool(self.anon_key),
            "service_role_key_configured": bool(self.service_role_key),
            "jwt_secret_or_jwks_config_configured": bool(self.jwt_secret_or_jwks_config),
            "resume_bucket_configured": bool(self.resume_bucket),
            "export_bucket_configured": bool(self.export_bucket),
        }

    def require_configured(self) -> "SupabaseSettings":
        if self.configured:
            return self
        missing = ", ".join(self.missing_required) or "cloud mode is disabled"
        raise SupabaseConfigurationError(f"Supabase cloud configuration is not ready: {missing}")


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _resolve_mode(values: dict[str, str]) -> str:
    requested_mode = _env(CLOUD_MODE_ENV).lower()
    if requested_mode in _CLOUD_MODE_VALUES:
        return "cloud"
    if requested_mode in _LOCAL_MODE_VALUES and not any(values.values()):
        return "local"
    if requested_mode not in _LOCAL_MODE_VALUES:
        return "cloud"
    return "cloud"


@lru_cache(maxsize=1)
def get_supabase_settings() -> SupabaseSettings:
    values = {name: _env(name) for name in SUPABASE_REQUIRED_ENV_VARS}
    mode = _resolve_mode(values)
    missing_required = (
        tuple(name for name, value in values.items() if not value)
        if mode == "cloud"
        else ()
    )
    return SupabaseSettings(
        mode=mode,
        supabase_url=values["SUPABASE_URL"],
        anon_key=values["SUPABASE_ANON_KEY"],
        service_role_key=values["SUPABASE_SERVICE_ROLE_KEY"],
        jwt_secret_or_jwks_config=values["SUPABASE_JWT_SECRET_OR_JWKS_CONFIG"],
        resume_bucket=values["SUPABASE_RESUME_BUCKET"],
        export_bucket=values["SUPABASE_EXPORT_BUCKET"],
        missing_required=missing_required,
    )


def get_supabase_config_state() -> dict[str, object]:
    """Return safe cloud configuration state without exposing secret values."""
    return get_supabase_settings().redacted_state()
