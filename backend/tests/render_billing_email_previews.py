"""Render synthetic previews only; no provider/configuration is instantiated."""

import argparse
import shutil
from pathlib import Path

from app.email.billing import SUBJECTS, render_billing_email
from app.email.config import EmailBrandSettings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", default="tmp/c12-billing-email-admin/previews")
args = parser.parse_args()
directory = Path(args.output)
directory.mkdir(parents=True, exist_ok=True)
assets = directory / "assets"
assets.mkdir(exist_ok=True)
for image in ("mascot.png", "payment-success.jpg", "renewal-success.jpg"):
    shutil.copyfile(
        Path("frontend/public/email-assets/billing") / image,
        assets / image.replace(".", "-20261027-v1."),
    )
for kind in SUBJECTS:
    preview = render_billing_email(
        kind,
        {
            "plan": "Plus",
            "currency": "INR",
            "amount_minor": "47082",
            "interval": "month",
            "period_end": "2026-11-26T00:00:00+05:30",
        },
        brand=EmailBrandSettings(
            asset_base_url="https://preview.invalid/billing",
            website_origin="https://preview.invalid",
        ),
    )
    # Preview-only local references; production never emits these fixture URLs.
    html = preview.html.replace("https://preview.invalid/billing/", "assets/")
    html = html.replace(
        "https://preview.invalid/auth/dashboard", "http://localhost:5173/auth/dashboard"
    )
    body_start = html.index(">", html.index("<body")) + 1
    label = '<p style="margin:0;padding:12px;text-align:center;font:12px Arial;color:#334155;background:#eef4ff;">SYNTHETIC C12 TEST · Local preview only. No new Razorpay payment.</p>'
    html = html[:body_start] + label + html[body_start:]
    (directory / (kind + ".html")).write_text(html, encoding="utf-8")
    if kind in ("billing_payment", "billing_renewal"):
        (directory / (kind + "-images-blocked.html")).write_text(
            html.replace('src="assets/', 'src="images-disabled/'), encoding="utf-8"
        )
    (directory / (kind + ".txt")).write_text(
        "SYNTHETIC C12 TEST · Local preview only.\n\n" + preview.text, encoding="utf-8"
    )
print("Four synthetic HTML/plain-text email previews rendered; no messages sent.")
