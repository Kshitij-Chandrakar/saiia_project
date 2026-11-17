"""Presentation contracts only. No events, database or provider execution."""

from html.parser import HTMLParser

import pytest
from app.email.billing import render_billing_email
from app.email.config import EmailBrandSettings
from app.email.provider import EmailSendRequest, EmailValidationError

PAYLOAD = {
    "plan": "Plus",
    "currency": "INR",
    "amount_minor": "47082",
    "interval": "month",
    "period_end": "2026-11-26T00:00:00+05:30",
}
BRAND = EmailBrandSettings(
    asset_base_url="https://assets.example.invalid/email-assets/billing",
    website_origin="https://account.example.invalid",
)


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


@pytest.mark.parametrize(
    "kind,heading,hero",
    [
        ("billing_payment", "Payment received", "payment-success-20261027-v1.jpg"),
        (
            "billing_renewal",
            "Your subscription is renewed",
            "renewal-success-20261027-v1.jpg",
        ),
    ],
)
def test_receipt_structure_content_and_plain_text_contract(kind, heading, hero):
    rendered = render_billing_email(kind, PAYLOAD, brand=BRAND)
    elements = Elements(rendered.html)
    assert heading in rendered.html and heading in rendered.text
    for value in (
        "Plus",
        "Monthly",
        "INR 470.82",
        "26 Nov 2026",
        "not a GST tax invoice",
    ):
        assert value in rendered.html and value in rendered.text
    assert "#eef4ff" in rendered.html and "max-width:600px" in rendered.html
    assert "mso-hide:all" in rendered.html  # Preheader.
    assert all(
        attrs.get("role") == "presentation"
        for tag, attrs in elements.tags
        if tag == "table"
    )
    images = [attrs for tag, attrs in elements.tags if tag == "img"]
    assert len(images) == 2 and all(image["alt"] for image in images)
    assert images[1]["src"] == BRAND.asset_base_url + "/" + hero
    assert [attrs["href"] for tag, attrs in elements.tags if tag == "a"] == [
        "https://account.example.invalid/auth/dashboard"
    ]
    assert "/auth/dashboard" in rendered.text
    assert not any(tag in ("script", "form", "svg") for tag, _ in elements.tags)
    for forbidden in (
        "reset-password",
        "password",
        "recovery",
        "TokenHash",
        "SiteURL",
        "security-icon",
        "support@",
        "invoice-download",
        "data:image",
        "next charge",
        "invoice number",
    ):
        assert forbidden.lower() not in rendered.html.lower()
    EmailSendRequest(
        recipient_email="synthetic@example.invalid",
        email_type=kind,
        subject=rendered.subject,
        text_body=rendered.text,
        html_body=rendered.html,
        idempotency_key="billing:synthetic",
    )


def test_unconfigured_assets_and_destination_are_not_fabricated():
    rendered = render_billing_email(
        "billing_payment",
        {k: v for k, v in PAYLOAD.items() if k != "period_end"},
        brand=EmailBrandSettings(),
    )
    assert not any(tag in ("a", "img") for tag, _ in Elements(rendered.html).tags)
    assert "Paid access through" not in rendered.html
    assert "Not available" not in rendered.html
    assert "/auth/dashboard" not in rendered.text
    assert "current verified access period" in rendered.text


def test_escape_plan_and_reject_unsafe_reference_configuration():
    rendered = render_billing_email(
        "billing_payment",
        {**PAYLOAD, "plan": '<img src=x onerror="alert(1)">'},
        brand=BRAND,
    )
    assert "&lt;img" in rendered.html
    assert len([tag for tag, _ in Elements(rendered.html).tags if tag == "img"]) == 2
    for value in (
        "javascript:alert(1)",
        'https://example.invalid" onerror="x',
        "https://user:pass@example.invalid",
        "https://example.invalid?token=x",
        "https://example.invalid/#x",
        "//example.invalid",
        "http://example.invalid",
        "https://example.invalid/%0a",
        "https://example.invalid\n",
    ):
        with pytest.raises((EmailValidationError, ValueError)):
            render_billing_email(
                "billing_payment",
                PAYLOAD,
                brand=EmailBrandSettings(asset_base_url=value),
            )
        with pytest.raises((EmailValidationError, ValueError)):
            render_billing_email(
                "billing_payment",
                PAYLOAD,
                brand=EmailBrandSettings(website_origin=value),
            )


def test_financial_snapshot_dates_and_subjects_are_unchanged():
    snapshot = dict(PAYLOAD)
    payment = render_billing_email("billing_payment", snapshot, brand=BRAND)
    renewal = render_billing_email("billing_renewal", snapshot, brand=BRAND)
    assert snapshot == PAYLOAD
    assert payment.subject == "Your payment is confirmed"
    assert renewal.subject == "Your renewal payment is confirmed"
    assert "payment reference" not in payment.html.lower()
    assert "payment date" not in payment.html.lower()
    assert "period start" not in payment.html.lower()


def test_server_configuration_and_yearly_variant(monkeypatch):
    monkeypatch.setenv("EMAIL_ASSET_BASE_URL", BRAND.asset_base_url)
    monkeypatch.setenv("EMAIL_WEBSITE_ORIGIN", BRAND.website_origin)
    rendered = render_billing_email(
        "billing_renewal",
        {**PAYLOAD, "plan": "Pro", "interval": "year", "amount_minor": "766882"},
    )
    assert "Yearly" in rendered.text and "Yearly" in rendered.html
    assert "INR 7,668.82" in rendered.text and "INR 7,668.82" in rendered.html
    assert BRAND.website_origin + "/auth/dashboard" in rendered.html
    assert BRAND.asset_base_url + "/renewal-success-20261027-v1.jpg" in rendered.html
