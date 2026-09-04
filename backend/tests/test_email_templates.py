import pytest

from app.email.provider import EmailValidationError
from app.email.templates import (
    render_ai_notes_ready_email,
    render_session_summary_email,
    render_transcript_export_email,
    render_welcome_email,
)


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
    ("renderer", "email_type", "subject_fragment", "body_fragment"),
    [
        (
            render_ai_notes_ready_email,
            "ai_notes_ready",
            "AI notes are ready",
            "Your AI notes are ready for review.",
        ),
        (
            render_session_summary_email,
            "session_summary",
            "session summary is ready",
            "Your session summary is ready.",
        ),
        (
            render_transcript_export_email,
            "transcript_export",
            "transcript export is ready",
            "Your transcript export is ready.",
        ),
    ],
)
def test_feature_templates_render_safe_plain_text_without_content_payloads(
    renderer,
    email_type: str,
    subject_fragment: str,
    body_fragment: str,
) -> None:
    template = renderer(
        display_name="Chandra",
        session_title="Backend practice",
        session_date="2026-09-04",
    )

    assert template.email_type == email_type
    assert subject_fragment in template.subject
    assert body_fragment in template.text_body
    assert "Backend practice" in template.text_body
    assert "2026-09-04" in template.text_body
    assert "https://" not in template.text_body
    assert "Question text from the transcript" not in template.text_body
    assert "Raw AI notes content" not in template.text_body


def test_feature_templates_use_fallback_name_and_session_title() -> None:
    template = render_session_summary_email()

    assert "Hello there," in template.text_body
    assert "Session: your interview session" in template.text_body


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_title", "Raw transcript: question and answer content"),
        ("session_title", "Bearer secret"),
        ("session_date", "https://example.test/export?token=secret"),
        ("dashboard_path", "https://evil.example.test/export"),
        ("support_email", "support@example.com?token=secret"),
    ],
)
def test_feature_templates_reject_unsafe_variables(field: str, value: str) -> None:
    with pytest.raises(EmailValidationError):
        render_ai_notes_ready_email(**{field: value})


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
