"""Shared presentation for verified payment/renewal receipts; no billing logic."""

import re
from html import escape
from urllib.parse import urlsplit

from app.email.config import EmailBrandSettings, load_email_brand_settings
from app.email.provider import EmailValidationError

VARIANTS = {
    "billing_payment": (
        "Payment received",
        "Your payment has been verified and your plan is ready to use.",
        "payment-success-20261027-v1.jpg",
        "Intervucopilot mascot celebrating beside a receipt and checkmark",
    ),
    "billing_renewal": (
        "Your subscription is renewed",
        "Your renewal payment has been verified. Your plan continues for the new paid period.",
        "renewal-success-20261027-v1.jpg",
        "Intervucopilot mascot beside a calendar with renewal arrows and a checkmark",
    ),
}


def safe_base(value, *, origin=False):
    """Only configured HTTPS references, no credentials, queries or fragments."""
    if not value:
        return ""
    if any(ord(character) < 33 or character in "\"'<>\\" for character in value):
        raise EmailValidationError("Invalid billing email brand URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", parsed.netloc)
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9/_-]*|", parsed.path)
        or (origin and parsed.path not in ("", "/"))
    ):
        raise EmailValidationError("Invalid billing email brand URL")
    return value.rstrip("/")


def receipt_content(kind, plan, amount, interval, period_end, brand=None):
    brand = brand if brand is not None else load_email_brand_settings()
    if not isinstance(brand, EmailBrandSettings):
        raise EmailValidationError("Invalid billing brand settings")
    asset_base = safe_base(brand.asset_base_url)
    website = safe_base(brand.website_origin, origin=True)
    account_url = website + "/auth/dashboard" if website else ""
    heading, intro, hero, alt = VARIANTS[kind]
    preheader = f"{heading}. {plan} · {amount}."
    rows = [
        ("Plan", plan),
        ("Billing interval", "Monthly" if interval == "month" else "Yearly"),
        ("Confirmed total", amount),
    ]
    if period_end:
        rows.append(("Paid access through", period_end))
    period_copy = (
        f"Your paid access continues through {period_end}."
        if period_end
        else "Your account shows your current verified access period."
    )
    invoice_note = "This payment receipt is not a GST tax invoice."
    footer = "This is an automated billing email. Please do not reply to this message."
    text = "Intervucopilot\n\n" + heading + "\n\n" + intro + "\n" + period_copy + "\n\n"
    text += "\n".join(f"{label}: {value}" for label, value in rows)
    # Existing C10 plain-text contracts allow server-owned relative app paths,
    # not arbitrary absolute URLs. Keep that boundary unchanged.
    if account_url:
        text += "\n\nView your account: /auth/dashboard"
    text += "\n\n" + invoice_note + "\n\n" + footer
    mascot = (
        f'<td width="58" valign="middle"><img src="{escape(asset_base + "/mascot-20261027-v1.png", quote=True)}" width="48" height="32" alt="Intervucopilot mascot" style="display:block;border:0;width:48px;height:32px;"></td>'
        if asset_base
        else ""
    )
    hero_panel = (
        '<tr><td class="hero-pad" style="padding:4px 28px 0;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f7ff;border:1px solid #dbeafe;border-radius:22px;overflow:hidden;">'
        f'<tr><td><img src="{escape(asset_base + "/" + hero, quote=True)}" width="540" height="270" alt="{escape(alt, quote=True)}" style="display:block;width:100%;max-width:540px;height:auto;border:0;color:#334155;font-size:13px;line-height:20px;"></td></tr></table></td></tr>'
        if asset_base
        else ""
    )
    summary = "".join(
        '<tr><td class="detail-label" width="44%" valign="top" style="padding:12px 0;border-bottom:1px solid #e3ecfa;font-size:14px;line-height:22px;color:#475569;">'
        + escape(label)
        + '</td><td class="detail-value" valign="top" align="right" style="padding:12px 0 12px 16px;border-bottom:1px solid #e3ecfa;font-size:14px;line-height:22px;font-weight:700;color:#0f172a;overflow-wrap:anywhere;word-break:break-word;">'
        + escape(value)
        + "</td></tr>"
        for label, value in rows
    )
    cta = (
        '<tr><td align="center" style="padding:26px 0 8px;"><table role="presentation" cellspacing="0" cellpadding="0"><tr><td bgcolor="#0f172a" style="border-radius:999px;background:#0f172a;">'
        f'<a href="{escape(account_url, quote=True)}" style="display:inline-block;padding:18px 36px;border:1px solid #0f172a;border-radius:999px;font-size:15px;line-height:20px;font-weight:700;color:#ffffff;text-decoration:none;">View your account</a>'
        "</td></tr></table></td></tr>"
        if account_url
        else ""
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(heading)}</title>
<style>@media only screen and (max-width:480px){{.outer-pad{{padding:18px 10px!important}}.content-pad{{padding-left:24px!important;padding-right:24px!important}}.hero-pad{{padding-left:16px!important;padding-right:16px!important}}.receipt-heading{{font-size:30px!important;line-height:36px!important}}.wordmark{{font-size:21px!important}}.detail-label{{width:40%!important}}.detail-value{{font-size:13px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#eef4ff;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
<div style="display:none;font-size:1px;line-height:1px;color:#eef4ff;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;">{escape(preheader)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#eef4ff" style="background:#eef4ff;"><tr><td class="outer-pad" align="center" style="padding:34px 12px;">
<!--[if mso]><table role="presentation" width="600" cellspacing="0" cellpadding="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#ffffff" style="max-width:600px;background:#ffffff;border:1px solid #dbeafe;border-radius:28px;overflow:hidden;box-shadow:0 18px 48px rgba(15,23,42,0.08);">
<tr><td class="content-pad" style="padding:28px 34px 22px;"><table role="presentation" cellspacing="0" cellpadding="0"><tr>{mascot}<td valign="middle" class="wordmark" style="font-size:23px;line-height:30px;font-weight:800;letter-spacing:-0.5px;color:#08111f;">Intervucopilot</td></tr></table></td></tr>
{hero_panel}
<tr><td class="content-pad" style="padding:32px 38px 22px;">
<h1 class="receipt-heading" style="margin:0 0 16px;font-size:38px;line-height:44px;font-weight:800;letter-spacing:-1px;color:#0f172a;">{escape(heading)}</h1>
<p style="margin:0 0 10px;font-size:16px;line-height:26px;color:#334155;">{escape(intro)}</p>
<p style="margin:0;font-size:15px;line-height:25px;color:#475569;">{escape(period_copy)}</p></td></tr>
<tr><td class="content-pad" style="padding:0 38px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #dbeafe;background:#f8fbff;border-radius:20px;"><tr><td style="padding:10px 20px 14px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{summary}</table></td></tr></table></td></tr>
<tr><td class="content-pad" style="padding:0 38px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{cta}</table></td></tr>
<tr><td class="content-pad" style="padding:20px 38px 28px;"><p style="margin:0;font-size:12px;line-height:20px;color:#52627a;">{escape(invoice_note)}</p></td></tr>
<tr><td class="content-pad" style="padding:0 38px 30px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-top:1px solid #dce5f3;"><tr><td style="padding-top:20px;"><p style="margin:0 0 6px;font-size:12px;line-height:20px;color:#52627a;">Intervucopilot</p><p style="margin:0;font-size:12px;line-height:20px;color:#52627a;">{escape(footer)}</p></td></tr></table></td></tr>
</table><!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>"""
    return text, html
