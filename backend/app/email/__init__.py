from app.email.config import EmailConfigurationError, EmailSettings, load_email_settings
from app.email.provider import (
    BACKEND_TRANSACTIONAL_EMAIL_TYPES,
    MARKETING_EMAIL_TYPES,
    SUPABASE_AUTH_EMAIL_TYPES,
    EmailProvider,
    EmailSendRequest,
    EmailSendResult,
    EmailValidationError,
)
from app.email.service import EmailService, build_email_service

__all__ = [
    "BACKEND_TRANSACTIONAL_EMAIL_TYPES",
    "EmailConfigurationError",
    "EmailProvider",
    "EmailSendRequest",
    "EmailSendResult",
    "EmailService",
    "EmailSettings",
    "EmailValidationError",
    "MARKETING_EMAIL_TYPES",
    "SUPABASE_AUTH_EMAIL_TYPES",
    "build_email_service",
    "load_email_settings",
]
