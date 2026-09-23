from dataclasses import dataclass, field
import re
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
    resend_api_key: str = field(default="", repr=False)
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


@dataclass(frozen=True, slots=True)
class MarketingEmailSettings:
    provider_mode: str = "dry_run"
    enabled: bool = False
    resend_api_key: str = field(default="", repr=False)
    from_email: str = "updates@intervucopilot.in"
    from_name: str = "Intervu AI"
    reply_to: str = ""

    def __post_init__(self) -> None:
        address = r"[A-Za-z0-9._+-]+@intervucopilot\.in"
        if (self.provider_mode not in {"dry_run", "live"}
                or not re.fullmatch(address, self.from_email)
                or (self.reply_to and not re.fullmatch(address, self.reply_to))
                or not re.fullmatch(r"[A-Za-z0-9 ._-]{1,80}", self.from_name)
                or not isinstance(self.enabled, bool)):
            raise EmailConfigurationError("Marketing email configuration is invalid.")
        if self.provider_mode == "live" and not self.resend_api_key.strip():
            raise EmailConfigurationError("Live marketing email requires a backend Resend API key.")
        if any(ord(c) < 33 for c in self.resend_api_key):
            raise EmailConfigurationError("Marketing email credential configuration is invalid.")

    @property
    def live_delivery_requested(self) -> bool:
        return self.enabled and self.provider_mode == "live"


def load_marketing_email_settings(environment: Mapping[str, str] | None = None) -> MarketingEmailSettings:
    source = environment if environment is not None else os.environ
    enabled = source.get("MARKETING_EMAILS_ENABLED", "false").strip().lower()
    if enabled not in {"true", "false"}:
        raise EmailConfigurationError("Marketing email enable flag is invalid.")
    return MarketingEmailSettings(
        provider_mode=source.get("EMAIL_PROVIDER_MODE", "dry_run").strip(),
        enabled=enabled == "true",
        resend_api_key=source.get("RESEND_API_KEY", "").strip(),
        from_email=source.get("MARKETING_FROM_EMAIL", "updates@intervucopilot.in").strip(),
        from_name=source.get("MARKETING_FROM_NAME", "Intervu AI").strip(),
        reply_to=source.get("MARKETING_REPLY_TO", "").strip(),
    )
