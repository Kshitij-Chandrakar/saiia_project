from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Literal, Mapping, Protocol


BACKEND_TRANSACTIONAL_EMAIL_TYPES = frozenset(
    {
        "welcome",
        "account_security",
        "ai_notes_ready",
        "session_summary",
        "transcript_export",
    }
)
SUPABASE_AUTH_EMAIL_TYPES = frozenset(
    {
        "auth_signup_verification",
        "auth_password_reset",
        "auth_email_change_confirmation_future",
        "auth_magic_link_future",
    }
)
MARKETING_EMAIL_TYPES = frozenset(
    {
        "marketing_promotion_future",
        "marketing_product_update_future",
    }
)
_SENSITIVE_METADATA_KEY = re.compile(
    r"(?:token|authorization|password|secret|cookie|header|prompt|transcript|resume|screenshot|audio|url)",
    re.IGNORECASE,
)
_SENSITIVE_METADATA_VALUE = re.compile(r"(?:bearer\s+|https?://|-----BEGIN)", re.IGNORECASE)
MAX_METADATA_ITEMS = 16
MAX_METADATA_VALUE_CHARS = 200
MAX_EMAIL_CHARS = 254
MAX_SUBJECT_CHARS = 200


class EmailValidationError(ValueError):
    """Raised when a transactional email request is unsafe or invalid."""


def mask_recipient_email(recipient_email: str) -> str:
    """Return a log-safe recipient representation."""

    local, separator, domain = recipient_email.partition("@")
    if not separator or not local or not domain:
        return "***"
    return f"{local[:1]}***@{domain.lower()}"


def _safe_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    if len(metadata) > MAX_METADATA_ITEMS:
        raise EmailValidationError("Email metadata has too many fields.")
    safe: dict[str, object] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or _SENSITIVE_METADATA_KEY.search(key):
            raise EmailValidationError("Email metadata contains a restricted field.")
        if not isinstance(value, (bool, int, float, str)):
            raise EmailValidationError("Email metadata must contain scalar values.")
        if isinstance(value, str):
            if len(value) > MAX_METADATA_VALUE_CHARS or _SENSITIVE_METADATA_VALUE.search(value):
                raise EmailValidationError("Email metadata contains a restricted value.")
            if any(ord(character) < 32 for character in value):
                raise EmailValidationError("Email metadata contains control characters.")
        safe[key] = value
    return safe


@dataclass(frozen=True, slots=True)
class EmailSendRequest:
    """Safe input contract for backend transactional email providers."""

    recipient_email: str
    subject: str
    email_type: str
    safe_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        recipient = self.recipient_email.strip()
        subject = self.subject.strip()
        if (
            not recipient
            or len(recipient) > MAX_EMAIL_CHARS
            or recipient.count("@") != 1
            or any(ord(character) < 33 for character in recipient)
        ):
            raise EmailValidationError("Recipient email is invalid.")
        if not subject or len(subject) > MAX_SUBJECT_CHARS or any(ord(character) < 32 for character in subject):
            raise EmailValidationError("Email subject is invalid.")
        if self.email_type not in BACKEND_TRANSACTIONAL_EMAIL_TYPES:
            raise EmailValidationError("Email type is not a backend transactional email.")
        if not isinstance(self.safe_metadata, Mapping):
            raise EmailValidationError("Email metadata is invalid.")
        object.__setattr__(self, "recipient_email", recipient)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "safe_metadata", _safe_metadata(self.safe_metadata))


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    """Provider result that contains no message body or credential data."""

    status: Literal["dry_run"]
    provider: str
    message_id: str
    dry_run: bool
    recipient_masked: str
    email_type: str
    created_at: str


class EmailProvider(Protocol):
    def send_email(self, request: EmailSendRequest) -> EmailSendResult:
        """Send or safely simulate one validated transactional email."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
