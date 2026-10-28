"""No-network Resend adapter and template contracts."""

from uuid import uuid4

import pytest
from app.email.billing import (
    ResendBillingProvider,
    SendNotAccepted,
    render_billing_email,
)
from app.email.config import EmailSettings
from app.email.provider import EmailSendRequest


class Session:
    def __init__(self, status=200, error=None):
        self.status = status
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error()
        status = self.status

        class Response:
            status_code = status

            def json(self):
                return {"id": str(uuid4())}

        return Response()


def request():
    return EmailSendRequest(
        recipient_email="synthetic@example.invalid",
        subject="Payment confirmed",
        email_type="billing_payment",
        text_body="Receipt",
        html_body="<p>Receipt</p>",
        idempotency_key="billing:synthetic",
    )


def test_default_off_dry_run_never_calls_provider():
    session = Session()
    result = ResendBillingProvider(EmailSettings(), session).send_email(request())
    assert result["state"] == "dry_run" and not session.calls


@pytest.mark.parametrize(
    "status,error,exception",
    [
        (429, None, SendNotAccepted),
        (500, None, RuntimeError),
        (200, TimeoutError, TimeoutError),
    ],
)
def test_no_automatic_network_retries(status, error, exception):
    session = Session(status, error)
    provider = ResendBillingProvider(
        EmailSettings(
            enabled=True,
            dry_run=False,
            resend_api_key="synthetic",
            from_email="billing@synthetic.invalid",
        ),
        session,
    )
    with pytest.raises(exception):
        provider.send_email(request())
    assert len(session.calls) == 1
    _, options = session.calls[0]
    assert options["headers"]["Idempotency-Key"] == "billing:synthetic"
    assert options["allow_redirects"] is False


@pytest.mark.parametrize(
    "amount,formatted",
    [
        ("47082", "470.82"),
        ("353882", "3,538.82"),
        ("106082", "1,060.82"),
        ("766882", "7,668.82"),
    ],
)
def test_exact_total_template(amount, formatted):
    template = render_billing_email(
        "billing_payment",
        {
            "plan": "Plus",
            "currency": "INR",
            "amount_minor": amount,
            "interval": "month",
            "period_end": "2026-11-26T00:00:00+05:30",
        },
    )
    assert f"INR {formatted}" in template.text and f"INR {formatted}" in template.html
