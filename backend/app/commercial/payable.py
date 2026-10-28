"""Approved GST-added quote. No inferred general rounding or tax jurisdiction."""

from app.commercial import catalog_contract as c

POLICY = "billing.inr.gst18.v1"


def payable(snapshot: c.OfferSnapshot, price_id: str) -> dict[str, str]:
    price = next(p for p in snapshot.terms.prices if p.price_id == price_id)
    base = int(price.amount_minor or 0)
    if price.currency != "INR" or price.exponent != 2 or base <= 0:
        raise ValueError("unsupported payable")
    tax, remainder = divmod(base * 1800, 10000)
    if remainder:
        raise ValueError("general rounding policy required")
    return {
        "contract_version": POLICY,
        "currency": "INR",
        "exponent": "2",
        "base_amount_minor": str(base),
        "tax_rate_basis_points": "1800",
        "tax_amount_minor": str(tax),
        "total_amount_minor": str(base + tax),
        "offer_version_id": snapshot.offer_version_id,
        "offer_version": str(snapshot.version),
        "offer_fingerprint": snapshot.fingerprint,
        "price_id": price_id,
        "provider_tax_mode": "total_in_plan_no_additional_tax",
    }
