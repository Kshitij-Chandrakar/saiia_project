from dataclasses import dataclass
import os
from typing import Mapping


class EmailConfigurationError(RuntimeError):
    """Raised when a requested email delivery mode is not available safely."""


def _env_bool(environment: Mapping[str, str], name: str, default: bool) -> bool:
    value = environment.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class EmailSettings:
    """Backend email settings with an offline dry-run default."""

    enabled: bool = False
    dry_run: bool = True
    provider: str = "resend"
    resend_api_key: str = ""
    from_email: str = ""
    reply_to: str = ""

    @property
    def live_delivery_requested(self) -> bool:
        return self.enabled and not self.dry_run


def load_email_settings(environment: Mapping[str, str] | None = None) -> EmailSettings:
    """Load email settings without requiring credentials for dry-run mode."""

    source = environment if environment is not None else os.environ
    return EmailSettings(
        enabled=_env_bool(source, "EMAIL_ENABLED", False),
        dry_run=_env_bool(source, "EMAIL_DRY_RUN", True),
        provider=source.get("EMAIL_PROVIDER", "resend").strip().lower() or "resend",
        resend_api_key=source.get("RESEND_API_KEY", "").strip(),
        from_email=source.get("EMAIL_FROM", "").strip(),
        reply_to=source.get("EMAIL_REPLY_TO", "").strip(),
    )
