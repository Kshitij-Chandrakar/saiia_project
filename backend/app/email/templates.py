from dataclasses import dataclass
import re

from app.email.provider import EmailValidationError, validate_recipient_email


WELCOME_EMAIL_TYPE = "welcome"
WELCOME_TEMPLATE_VERSION = "welcome_v1"
_MAX_DISPLAY_NAME_CHARS = 80
_MAX_DASHBOARD_PATH_CHARS = 200
_UNSAFE_TEMPLATE_VALUE = re.compile(
    r"(?:https?://|bearer\s+|-----BEGIN|api[_ -]?key|access[_ -]?token|"
    r"refresh[_ -]?token|authorization|transcript|resume(?:\s+chunk)?|prompt)",
    re.IGNORECASE,
)
_SAFE_DASHBOARD_PATH = re.compile(r"/[A-Za-z0-9/_-]*$")


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    email_type: str
    subject: str
    text_body: str


def _safe_display_name(value: str | None) -> str:
    if value is None:
        return "there"
    if not isinstance(value, str):
        raise EmailValidationError("Welcome template display name is invalid.")
    if not value.strip():
        return "there"
    name = " ".join(value.split())
    if (
        len(name) > _MAX_DISPLAY_NAME_CHARS
        or _UNSAFE_TEMPLATE_VALUE.search(name)
        or any(ord(character) < 32 for character in name)
    ):
        raise EmailValidationError("Welcome template display name is unsafe.")
    return name


def _safe_dashboard_path(value: str) -> str:
    if not isinstance(value, str):
        raise EmailValidationError("Welcome template dashboard path is invalid.")
    path = value.strip()
    if (
        not path
        or len(path) > _MAX_DASHBOARD_PATH_CHARS
        or not _SAFE_DASHBOARD_PATH.fullmatch(path)
        or path.startswith("//")
    ):
        raise EmailValidationError("Welcome template dashboard path is unsafe.")
    return path


def _safe_support_email(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EmailValidationError("Welcome template support email is invalid.")
    if not value.strip():
        return None
    email = validate_recipient_email(value)
    if any(character in email for character in "?/\\#") or _UNSAFE_TEMPLATE_VALUE.search(email):
        raise EmailValidationError("Welcome template support email is unsafe.")
    return email


def render_welcome_email(
    *,
    display_name: str | None = None,
    support_email: str | None = None,
    dashboard_path: str = "/auth/dashboard",
) -> EmailTemplate:
    """Render the safe plain-text welcome template without auth-sensitive links."""

    name = _safe_display_name(display_name)
    path = _safe_dashboard_path(dashboard_path)
    support = _safe_support_email(support_email)
    lines = [
        f"Welcome to intervuAI, {name}.",
        "",
        "Your account is ready. You can create interview sessions, upload your resume or profile, and use AI Notes and Ask AI when those features are available.",
        "",
        f"Open your dashboard: {path}",
    ]
    if support:
        lines.extend(["", f"Need help? Contact {support}."])
    return EmailTemplate(
        email_type=WELCOME_EMAIL_TYPE,
        subject="Welcome to intervuAI",
        text_body="\n".join(lines),
    )
