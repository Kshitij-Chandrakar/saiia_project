from dataclasses import dataclass
import re

from app.email.provider import EmailValidationError, validate_recipient_email


WELCOME_EMAIL_TYPE = "welcome"
WELCOME_TEMPLATE_VERSION = "welcome_v1"
AI_NOTES_READY_EMAIL_TYPE = "ai_notes_ready"
SESSION_SUMMARY_EMAIL_TYPE = "session_summary"
TRANSCRIPT_EXPORT_EMAIL_TYPE = "transcript_export"
AI_NOTES_READY_TEMPLATE_VERSION = "ai_notes_ready_v1"
SESSION_SUMMARY_TEMPLATE_VERSION = "session_summary_v1"
TRANSCRIPT_EXPORT_TEMPLATE_VERSION = "transcript_export_v1"
_MAX_DISPLAY_NAME_CHARS = 80
_MAX_SESSION_TITLE_CHARS = 120
_MAX_SESSION_DATE_CHARS = 40
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


def _safe_session_title(value: str | None) -> str:
    if value is None:
        return "your interview session"
    if not isinstance(value, str):
        raise EmailValidationError("Feature email session title is invalid.")
    if not value.strip():
        return "your interview session"
    title = " ".join(value.split())
    if (
        len(title) > _MAX_SESSION_TITLE_CHARS
        or _UNSAFE_TEMPLATE_VALUE.search(title)
        or any(ord(character) < 32 for character in title)
    ):
        raise EmailValidationError("Feature email session title is unsafe.")
    return title


def _safe_session_date(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EmailValidationError("Feature email session date is invalid.")
    if not value.strip():
        return None
    date = " ".join(value.split())
    if (
        len(date) > _MAX_SESSION_DATE_CHARS
        or _UNSAFE_TEMPLATE_VALUE.search(date)
        or any(ord(character) < 32 for character in date)
    ):
        raise EmailValidationError("Feature email session date is unsafe.")
    return date


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


def _render_feature_email(
    *,
    email_type: str,
    subject: str,
    display_name: str | None,
    session_title: str | None,
    session_date: str | None,
    dashboard_path: str,
    support_email: str | None,
    message: str,
) -> EmailTemplate:
    name = _safe_display_name(display_name)
    title = _safe_session_title(session_title)
    date = _safe_session_date(session_date)
    path = _safe_dashboard_path(dashboard_path)
    support = _safe_support_email(support_email)
    lines = [
        f"Hello {name},",
        "",
        message,
        "",
        f"Session: {title}",
    ]
    if date:
        lines.append(f"Session date: {date}")
    lines.extend([
        "",
        f"Open your intervuAI dashboard: {path}",
    ])
    if support:
        lines.extend(["", f"Need help? Contact {support}."])
    return EmailTemplate(
        email_type=email_type,
        subject=subject,
        text_body="\n".join(lines),
    )


def render_ai_notes_ready_email(
    *,
    display_name: str | None = None,
    session_title: str | None = None,
    session_date: str | None = None,
    dashboard_path: str = "/auth/dashboard",
    support_email: str | None = None,
) -> EmailTemplate:
    return _render_feature_email(
        email_type=AI_NOTES_READY_EMAIL_TYPE,
        subject="Your intervuAI AI notes are ready",
        display_name=display_name,
        session_title=session_title,
        session_date=session_date,
        dashboard_path=dashboard_path,
        support_email=support_email,
        message="Your AI notes are ready for review. Open your dashboard to view them and continue practicing.",
    )


def render_session_summary_email(
    *,
    display_name: str | None = None,
    session_title: str | None = None,
    session_date: str | None = None,
    dashboard_path: str = "/auth/dashboard",
    support_email: str | None = None,
) -> EmailTemplate:
    return _render_feature_email(
        email_type=SESSION_SUMMARY_EMAIL_TYPE,
        subject="Your intervuAI session summary is ready",
        display_name=display_name,
        session_title=session_title,
        session_date=session_date,
        dashboard_path=dashboard_path,
        support_email=support_email,
        message="Your session summary is ready. Open your dashboard to review the available summary.",
    )


def render_transcript_export_email(
    *,
    display_name: str | None = None,
    session_title: str | None = None,
    session_date: str | None = None,
    dashboard_path: str = "/auth/dashboard",
    support_email: str | None = None,
) -> EmailTemplate:
    return _render_feature_email(
        email_type=TRANSCRIPT_EXPORT_EMAIL_TYPE,
        subject="Your intervuAI transcript export is ready",
        display_name=display_name,
        session_title=session_title,
        session_date=session_date,
        dashboard_path=dashboard_path,
        support_email=support_email,
        message="Your transcript export is ready. Open your dashboard to view or download it; no file attachment is included in this message.",
    )
