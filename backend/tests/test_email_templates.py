import pytest

from app.email.provider import EmailValidationError
from app.email.templates import render_welcome_email


def test_welcome_template_renders_safe_plain_text_body() -> None:
    template = render_welcome_email(
        display_name="Chandra",
        support_email="support@example.com",
    )

    assert template.email_type == "welcome"
    assert template.subject == "Welcome to intervuAI"
    assert "Welcome to intervuAI, Chandra." in template.text_body
    assert "/auth/dashboard" in template.text_body
    assert "support@example.com" in template.text_body
    assert "https://" not in template.text_body
    assert "token" not in template.text_body.lower()


def test_welcome_template_uses_fallback_name() -> None:
    template = render_welcome_email()

    assert "Welcome to intervuAI, there." in template.text_body


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("display_name", "https://example.test/?token=secret"),
        ("display_name", "Bearer secret"),
        ("support_email", "support@example.com?token=secret"),
        ("dashboard_path", "https://evil.example.test"),
        ("dashboard_path", "/auth/dashboard?token=secret"),
    ],
)
def test_welcome_template_rejects_unsafe_variables(field: str, value: str) -> None:
    with pytest.raises(EmailValidationError):
        render_welcome_email(**{field: value})
