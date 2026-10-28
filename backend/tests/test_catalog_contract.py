"""Synthetic domain documents only. No real offers, subjects, storage or calls."""

import copy
import importlib
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from app.commercial import catalog_contract as c
from pydantic import ValidationError

DRAFT = "00000000-0000-4000-8000-000000000001"
PLAN = "00000000-0000-4000-8000-000000000002"
PRICE = "00000000-0000-4000-8000-000000000003"
OFFER = "00000000-0000-4000-8000-000000000004"
DISCOUNT = "00000000-0000-4000-8000-000000000005"
OTHER = "00000000-0000-4000-8000-000000000006"
AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def document():
    return dict(
        draft_id=DRAFT,
        plan=dict(plan_id=PLAN, code="synthetic-test"),
        revision=1,
        state="previewed",
        internal_notes="SYNTHETIC_PRIVATE_NOTE",
        terms=dict(
            name="Synthetic contract",
            description="Test fixture only",
            subscription_policy_ref="synthetic.lifecycle.v1",
            migration_policy_ref="synthetic.migration.v1",
            prices=[
                dict(
                    price_id=PRICE,
                    currency="USD",
                    exponent=2,
                    amount_minor=1000,
                    billing=dict(unit="year", count=1),
                    tax_policy_ref="synthetic.tax.v1",
                    rounding_policy_ref="synthetic.round.v1",
                )
            ],
            entitlements=[dict(feature="answers.generate", allowed=True)],
            limits=[
                dict(
                    meter="answers.completed",
                    feature="answers.generate",
                    kind="quota",
                    unit="turn",
                    amount=73,
                    grant_kind="recurring",
                    reset=dict(
                        unit="month",
                        count=1,
                        anchor="calendar",
                        timezone="UTC",
                        policy_ref="synthetic.reset.v1",
                    ),
                    policy_ref="synthetic.answer.v1",
                )
            ],
        ),
    )


def discount(**changes):
    result = dict(
        discount_id=DISCOUNT,
        revision=1,
        kind="percentage",
        basis_points=1250,
        scope="offer",
        eligibility_policy_ref="synthetic.private-cohort.v1",
        valid_from="2026-01-01T00:00:00Z",
        valid_until="2026-02-01T00:00:00Z",
        total_redemptions=7,
        per_account_redemptions=1,
        redemption_policy_ref="synthetic.redemption.v1",
        duration="once",
        stacking=False,
        application_policy_ref="synthetic.discount.v1",
        public_label="Synthetic promotion",
    )
    result.update(changes)
    return result


def snapshot(data=None, **kwargs):
    return c.create_snapshot(
        document() if data is None else data,
        offer_version_id=OFFER,
        version=1,
        **kwargs
    )


def visibility(**kwargs):
    return c.Visibility(
        **dict(
            dict(
                offer_version_id=OFFER,
                revision=1,
                state="visible",
                valid_from="2026-01-01T00:00:00Z",
            ),
            **kwargs
        )
    )


def codes(report):
    return {issue.code for issue in report.errors}


def test_complete_and_incomplete_documents_and_lossless_roundtrip():
    data = document()
    report = c.validate_draft(data)
    assert report.valid and report.publishable
    draft = c.CatalogDraft.model_validate(data)
    assert c.validate_draft(
        c.CatalogDraft.model_validate_json(draft.model_dump_json())
    ).publishable
    assert draft.terms.prices[0].billing.unit == "year"
    assert draft.terms.limits[0].reset.unit == "month"
    wire = json.loads(draft.model_dump_json())
    assert wire["terms"]["prices"][0]["amount_minor"] == "1000"
    data["terms"] = {}
    report = c.validate_draft(data)
    assert report.valid and not report.publishable and report.pending
    with pytest.raises(c.CatalogValidationError):
        snapshot(data)


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        -1,
        c.MAX_INTEGER + 1,
        1.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("1.0"),
        "01",
        "1.0",
        "1e3",
        " unlimited",
        "-1",
        " 1",
        "1 ",
        None,
    ],
)
def test_exact_price_integer_contract(value):
    data = document()
    data["terms"]["prices"][0]["amount_minor"] = value
    report = c.validate_draft(data)
    if value is None:
        assert report.valid and not report.publishable
    else:
        assert not report.valid
        assert report.errors[0].path[-1] == "amount_minor"


@pytest.mark.parametrize("value", [0, c.MAX_INTEGER, "0", str(c.MAX_INTEGER)])
def test_valid_zero_and_representation_upper_bound(value):
    data = document()
    data["terms"]["prices"][0]["amount_minor"] = value
    data["terms"]["limits"][0]["amount"] = value
    result = snapshot(data)
    assert result.terms.prices[0].amount_minor == int(value)
    assert result.terms.limits[0].amount == int(value)


@pytest.mark.parametrize(
    "path", ["count", "exponent", "limit", "revision", "basis_points", "redemptions"]
)
@pytest.mark.parametrize("value", [True, 0.5, float("nan"), c.MAX_INTEGER + 1])
def test_other_numeric_fields_are_not_coerced(path, value):
    data = document()
    if path == "count":
        data["terms"]["prices"][0]["billing"]["count"] = value
    elif path == "exponent":
        data["terms"]["prices"][0]["exponent"] = value
    elif path == "limit":
        data["terms"]["limits"][0]["amount"] = value
    elif path == "revision":
        data["revision"] = value
    else:
        data["terms"]["discounts"] = [
            discount(
                **{("total_redemptions" if path == "redemptions" else path): value}
            )
        ]
    assert not c.validate_draft(data).valid


@pytest.mark.parametrize(
    "currency,exponent", [("JPY", 0), ("USD", 2), ("INR", 2), ("KWD", 3)]
)
def test_supported_currency_precision(currency, exponent):
    data = document()
    data["terms"]["prices"][0].update(currency=currency, exponent=exponent)
    assert c.validate_draft(data).publishable
    data["terms"]["prices"][0]["exponent"] = (exponent + 1) % 4
    assert "incompatible_currency" in codes(c.validate_draft(data))
    data["terms"]["prices"][0]["currency"] = "XXX"
    assert not c.validate_draft(data).valid


@pytest.mark.parametrize(
    "change,code",
    [
        ("unknown_feature", "unknown_feature"),
        ("unknown_meter", "unknown_meter"),
        ("unit", "incompatible_unit"),
        ("kind", "incompatible_unit"),
        ("denied", "feature_denied"),
        ("feature_duplicate", "duplicate_feature"),
        ("meter_duplicate", "duplicate_limit"),
        ("price_duplicate", "duplicate_price"),
        ("price_conflict", "duplicate_price"),
        ("reset", "incompatible_reset"),
        ("basis", "incompatible_basis"),
    ],
)
def test_registry_conflicts_and_duplicates(change, code):
    data = document()
    terms = data["terms"]
    if change == "unknown_feature":
        terms["entitlements"][0]["feature"] = "mock.interview"
    elif change == "unknown_meter":
        terms["limits"][0]["meter"] = "mock.minutes"
    elif change == "unit":
        terms["limits"][0]["unit"] = "minute"
    elif change == "kind":
        terms["limits"][0]["kind"] = "storage"
    elif change == "denied":
        terms["entitlements"][0]["allowed"] = False
    elif change == "feature_duplicate":
        terms["entitlements"].append(dict(terms["entitlements"][0], allowed=False))
    elif change == "meter_duplicate":
        terms["limits"] *= 2
    elif change == "price_duplicate":
        terms["prices"] *= 2
    elif change == "price_conflict":
        terms["prices"].append(dict(terms["prices"][0], price_id=OTHER))
    elif change == "reset":
        terms["limits"][0]["grant_kind"] = "one_time"
    elif change == "basis":
        terms["limits"][0]["basis"] = c.AUTO_BASIS
    assert code in codes(c.validate_draft(data))


def test_omitted_denied_zero_and_missing_limit_are_distinct():
    data = document()
    data["terms"]["limits"][0]["amount"] = 0
    first = snapshot(data)
    assert first.terms.limits[0].amount == 0
    assert not next(
        f for f in first.terms.entitlements if f.feature == "assistant.auto"
    ).allowed
    data["terms"]["limits"] = []
    assert not c.validate_draft(data).publishable
    data["terms"]["entitlements"][0]["allowed"] = False
    assert snapshot(data).fingerprint != first.fingerprint


def test_auto_basis_audio_sources_and_model_eligibility_are_explicit():
    data = document()
    data["terms"]["entitlements"] = [
        dict(
            feature="assistant.auto",
            allowed=True,
            audio_sources=["both", "microphone", "system"],
        )
    ]
    data["terms"]["limits"][0].update(
        meter="auto.authorized_running",
        feature="assistant.auto",
        unit="second",
        basis=c.AUTO_BASIS,
    )
    result = snapshot(data)
    public = c.public_projection(result, visibility(), at=AT)
    assert public.limits[0].unit == "second" and public.limits[0].basis == c.AUTO_BASIS
    assert len(public.limits) == 1  # Both does not create two allowance rows.
    data["terms"]["limits"][0]["basis"] = None
    assert not c.validate_draft(data).publishable
    data = document()
    data["terms"]["entitlements"][0]["model_keys"] = ["synthetic-model"]
    assert "invalid_model_eligibility" in codes(c.validate_draft(data))
    result = snapshot(data, model_keys=frozenset({"synthetic-model"}))
    assert result.terms.entitlements[0].model_keys == ("synthetic-model",)
    assert c.public_projection(result, visibility(), at=AT).purchasable is False


@pytest.mark.parametrize(
    "patch,expected",
    [
        ({"basis_points": 0}, "invalid_discount"),
        ({"basis_points": 10001}, "invalid_discount"),
        ({"amount_minor": 1}, "invalid_discount"),
        ({"valid_until": "2026-01-01T00:00:00Z"}, "invalid_discount_window"),
        ({"valid_until": "2025-01-01T00:00:00Z"}, "invalid_discount_window"),
        ({"duration": "once", "cycles": 2}, "invalid_discount_duration"),
        ({"stacking": True}, "unsupported_stacking"),
        ({"scope": "prices", "price_ids": [OTHER]}, "invalid_discount_scope"),
        ({"scope": "offer", "price_ids": [PRICE]}, "invalid_discount_scope"),
        (
            {"total_redemptions": 1, "per_account_redemptions": 2},
            "invalid_redemption_limit",
        ),
    ],
)
def test_invalid_discount_semantics(patch, expected):
    data = document()
    data["terms"]["discounts"] = [discount(**patch)]
    assert expected in codes(c.validate_draft(data))


def test_fixed_discount_currency_scope_duration_and_pending_policy():
    data = document()
    rule = discount(
        kind="fixed",
        basis_points=None,
        amount_minor=10,
        currency="USD",
        exponent=2,
        scope="prices",
        price_ids=[PRICE],
        duration="repeating",
        cycles=3,
    )
    data["terms"]["discounts"] = [rule]
    assert c.validate_draft(data).publishable
    result = snapshot(data)
    assert result.terms.prices[0].amount_minor == 1000  # No pricing calculation.
    assert result.terms.limits[0].amount == 73
    rule["currency"] = "JPY"
    rule["exponent"] = 0
    assert "incompatible_currency" in codes(c.validate_draft(data))
    rule.update(currency="USD", exponent=2, amount_minor=1001)
    assert "discount_exceeds_price" in codes(c.validate_draft(data))
    rule["amount_minor"] = 0
    assert "invalid_discount" in codes(c.validate_draft(data))
    rule["amount_minor"] = 10
    rule["stacking"] = None
    assert c.validate_draft(data).valid and not c.validate_draft(data).publishable
    rule["stacking"] = False
    rule["cycles"] = None
    assert not c.validate_draft(data).publishable


@pytest.mark.parametrize(
    "instant",
    ["2026-01-01", "2026-01-01T00:00:00", "not-a-date", 1234, datetime(2026, 1, 1)],
)
def test_timezone_ambiguity_is_rejected(instant):
    data = document()
    data["terms"]["discounts"] = [discount(valid_from=instant)]
    assert not c.validate_draft(data).valid


def test_canonical_order_default_denial_timezone_and_private_notes():
    data = document()
    data["terms"]["discounts"] = [discount()]
    data["terms"]["entitlements"].extend(
        [
            dict(feature="sessions.history", allowed=True),
            dict(feature="notes.generate", allowed=False),
        ]
    )
    a = snapshot(data)
    other = copy.deepcopy(data)
    other["internal_notes"] = "different private content"
    other["revision"] = 2
    other["draft_id"] = OTHER
    other["terms"]["entitlements"].reverse()
    other["terms"]["discounts"][0]["valid_from"] = "2025-12-31T19:00:00-05:00"
    other["terms"]["entitlements"].append(dict(feature="assistant.auto", allowed=False))
    b = snapshot(other)
    assert a.canonical_json() == b.canonical_json() and a.fingerprint == b.fingerprint
    assert "SYNTHETIC_PRIVATE_NOTE" not in a.canonical_json()
    assert len(a.fingerprint) == 64
    assert (
        c.OfferSnapshot.model_validate_json(a.canonical_json()).fingerprint
        == a.fingerprint
    )


@pytest.mark.parametrize(
    "change",
    ["name", "price", "quota", "reset", "policy", "interval", "discount", "identity"],
)
def test_contractual_changes_change_fingerprint(change):
    data = document()
    first = snapshot(data).fingerprint
    if change == "name":
        data["terms"]["name"] = "Changed synthetic name"
    elif change == "price":
        data["terms"]["prices"][0]["amount_minor"] += 1
    elif change == "quota":
        data["terms"]["limits"][0]["amount"] += 1
    elif change == "reset":
        data["terms"]["limits"][0]["reset"]["count"] = 2
    elif change == "policy":
        data["terms"]["migration_policy_ref"] = "synthetic.migration.v2"
    elif change == "interval":
        data["terms"]["prices"][0]["billing"]["unit"] = "month"
    elif change == "discount":
        data["terms"]["discounts"] = [discount()]
    elif change == "identity":
        data["plan"]["code"] = "other-synthetic"
    assert snapshot(data).fingerprint != first


def test_nested_immutability_unchecked_copy_and_supplied_fingerprint():
    data = document()
    draft = c.CatalogDraft.model_validate(data)
    first = snapshot(draft)
    before = first.canonical_json()
    data["terms"]["prices"][0]["amount_minor"] = 9
    draft.terms = c.OfferTerms.model_validate(data["terms"])
    assert first.canonical_json() == before
    with pytest.raises(ValidationError):
        first.terms.prices[0].amount_minor = 3
    with pytest.raises(TypeError):
        first.terms.prices[0] = first.terms.prices[0]
    with pytest.raises(ValidationError):
        first.version = 2
    with pytest.raises(ValidationError):
        c.OfferSnapshot.model_validate(dict(first.model_dump(), fingerprint="forged"))
    broken = first.model_copy(
        update={"terms": first.terms.model_copy(update={"name": None})}
    )
    with pytest.raises(ValidationError):
        c.public_projection(broken, visibility(), at=AT)
    draft = c.CatalogDraft.model_validate(document()).model_copy(
        update={"revision": True}
    )
    assert not c.validate_draft(draft).valid


def test_public_projection_is_allowlisted_and_never_checkout_authority():
    data = document()
    data["terms"]["discounts"] = [discount()]
    public = c.public_projection(snapshot(data), visibility(), at=AT)
    wire = public.model_dump_json()
    for private in [
        "internal_notes",
        "SYNTHETIC_PRIVATE_NOTE",
        "eligibility_policy_ref",
        "private-cohort",
        "redemption_policy_ref",
        "total_redemptions",
        "rounding_policy_ref",
        "tax_policy_ref",
        "subscription_policy_ref",
        "eligible_model_keys",
    ]:
        assert private not in wire
    assert public.purchasable is False and public.checkout_state == "unavailable"
    assert public.discounts[0].label == "Synthetic promotion"
    data["terms"]["discounts"][0]["public_label"] = None
    assert not c.public_projection(snapshot(data), visibility(), at=AT).discounts
    data["terms"]["prices"][0]["provider_secret"] = "SYNTHETIC_SECRET"
    report = c.validate_draft(data)
    assert not report.valid and "SYNTHETIC_SECRET" not in repr(report.errors)


def test_visibility_and_transition_contracts():
    first = snapshot()
    assert (
        c.public_projection(
            first, visibility(), at=datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        is None
    )
    assert (
        c.public_projection(
            first, visibility(valid_until="2026-01-02T00:00:00Z"), at=AT
        )
        is None
    )
    assert (
        c.public_projection(
            first, visibility(state="retired", retired_at="2026-01-02T00:00:00Z"), at=AT
        )
        is None
    )
    with pytest.raises(ValidationError):
        visibility(state="retired")
    with pytest.raises(ValidationError):
        visibility(valid_until="2025-01-01T00:00:00Z")
    with pytest.raises(c.CatalogValidationError):
        c.public_projection(first, visibility(offer_version_id=OTHER), at=AT)
    assert not c.transition_errors("draft", "previewed")
    assert not c.transition_errors("previewed", "published")
    assert not c.transition_errors("previewed", "draft")
    assert c.transition_errors("published", "draft")
    data = document()
    data["state"] = "draft"
    assert c.validate_draft(
        data
    ).publishable  # Complete terms, but no preview edge yet.
    with pytest.raises(c.CatalogValidationError):
        snapshot(data)
    data["state"] = "published"
    assert not c.validate_draft(data).valid


def test_registry_is_immutable_and_pure_import_reads_no_configuration(monkeypatch):
    with pytest.raises(TypeError):
        c.FEATURES["mock.interviews"] = None
    with pytest.raises(FrozenInstanceError):
        c.METERS["answers.completed"].unit = "minute"
    assert all(
        f.implemented
        and not f.grants_runtime_access
        and f.hosted_readiness == "not_verified"
        for f in c.FEATURES.values()
    )
    assert "screen.diagrams" not in c.FEATURES
    import os

    original = os.getenv

    def environment(name, *args):
        if name.startswith("PYDANTIC_"):
            return original(name, *args)
        pytest.fail("application configuration read")

    monkeypatch.setattr(os, "getenv", environment)
    importlib.reload(c)


@pytest.mark.parametrize("identifier", [True, None, "not-uuid", PLAN.replace("-", "")])
def test_invalid_stable_identifiers(identifier):
    data = document()
    data["plan"]["plan_id"] = identifier
    assert not c.validate_draft(data).valid


def test_pending_limits_and_storage_reset_contract():
    data = document()
    limit = data["terms"]["limits"][0]
    limit["grant_kind"] = None
    limit["reset"] = None
    assert c.validate_draft(data).valid and not c.validate_draft(data).publishable
    limit["grant_kind"] = "recurring"
    assert not c.validate_draft(data).publishable
    data = document()
    data["terms"]["entitlements"] = [dict(feature="resume.upload", allowed=True)]
    data["terms"]["limits"] = [
        dict(
            meter="resume.stored_files",
            feature="resume.upload",
            kind="storage",
            unit="file",
            amount=1,
            policy_ref="synthetic.storage.v1",
        )
    ]
    assert c.validate_draft(data).publishable
    data["terms"]["limits"][0]["grant_kind"] = "one_time"
    assert "incompatible_reset" in codes(c.validate_draft(data))


def test_dimensions_and_unknown_timezone():
    data = document()
    data["terms"]["limits"][0]["reset"]["timezone"] = "Not/AZone"
    assert not c.validate_draft(data).valid
    data = document()
    data["terms"]["entitlements"][0]["audio_sources"] = ["both", "both"]
    report = c.validate_draft(data)
    assert {"duplicate_dimension", "incompatible_dimension"} <= codes(report)
    data["terms"]["entitlements"] = [dict(feature="assistant.auto", allowed=True)]
    data["terms"]["limits"] = []
    assert not c.validate_draft(data).publishable


def test_discount_missing_values_duplicates_scopes_and_bounds():
    data = document()
    data["terms"]["discounts"] = [discount(basis_points=None)]
    assert c.validate_draft(data).valid and not c.validate_draft(data).publishable
    data["terms"]["discounts"] = [discount(basis_points=10000)]
    assert c.validate_draft(data).publishable
    data["terms"]["discounts"] *= 2
    assert "duplicate_discount" in codes(c.validate_draft(data))
    data["terms"]["discounts"] = [discount(scope="prices", price_ids=[])]
    assert not c.validate_draft(data).publishable
    data["terms"]["discounts"] = [discount(kind="fixed", basis_points=None)]
    assert c.validate_draft(data).valid and not c.validate_draft(data).publishable


def test_set_collections_normalize_without_changing_ordered_semantics():
    data = document()
    data["terms"]["prices"].append(
        dict(data["terms"]["prices"][0], price_id=OTHER, currency="JPY", exponent=0)
    )
    data["terms"]["limits"].append(
        dict(
            meter="answers.concurrent",
            feature="answers.generate",
            kind="concurrency",
            unit="operation",
            amount=1,
            policy_ref="synthetic.concurrent.v1",
        )
    )
    data["terms"]["discounts"] = [
        discount(scope="prices", price_ids=[PRICE, OTHER]),
        discount(discount_id=OTHER),
    ]
    first = snapshot(data)
    for key in ("prices", "limits", "discounts"):
        data["terms"][key].reverse()
    data["terms"]["discounts"][1]["price_ids"].reverse()
    assert snapshot(data).fingerprint == first.fingerprint
    data["terms"]["discounts"][1]["duration"] = "ongoing"
    assert snapshot(data).fingerprint != first.fingerprint


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "   "),
        ("description", "<script>"),
        ("subscription_policy_ref", ""),
        ("unknown", "x"),
    ],
)
def test_required_and_forbidden_text_fields(field, value):
    data = document()
    data["terms"][field] = value
    assert not c.validate_draft(data).valid
