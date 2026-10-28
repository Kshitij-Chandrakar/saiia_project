"""Pure C13.1 contracts. No SQL, accounts, environment or provider calls."""

import hashlib
import json
from uuid import uuid4

import pytest
from app.commercial import catalog_contract as c
from app.commercial.account_entitlements import BindingDocument, validated_terms
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.usage_store import UsageReconciler, UsageStore, quantity
from pydantic import ValidationError
from test_pricing_native import definition


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "1", None, 2**63])
def test_integer_base_units_are_strict(value):
    with pytest.raises(CatalogStoreError) as error:
        quantity(value)
    assert error.value.code == ErrorCode.INVALID


def test_zero_is_quantity_but_not_a_reservation():
    assert quantity(0) == 0 and quantity(2**63 - 1) == 2**63 - 1
    with pytest.raises(CatalogStoreError):
        quantity(0, positive=True)


@pytest.mark.parametrize("code", ["free", "plus", "pro"])
def test_reuse_complete_versioned_snapshot_without_canonical_changes(code):
    raw = definition(code)
    raw["state"] = "previewed"
    snap = c.create_snapshot(raw, offer_version_id=str(uuid4()), version=1)
    record = dict(
        snapshot=snap.canonical_json(),
        fingerprint=snap.fingerprint,
        offer_version_id=snap.offer_version_id,
        plan_id=snap.plan.plan_id,
        version=1,
    )
    assert validated_terms(record, frozenset()).canonical_json() == record["snapshot"]
    for broken in [
        {**record, "fingerprint": "0" * 64},
        {**record, "offer_version_id": str(uuid4())},
        {**record, "version": 2},
    ]:
        with pytest.raises(CatalogStoreError) as error:
            validated_terms(broken, frozenset())
        assert error.value.code == ErrorCode.STORED_INVALID
    future = json.loads(record["snapshot"])
    future["contract_version"] = "catalog.unknown"
    encoded = json.dumps(future, separators=(",", ":"), sort_keys=True)
    with pytest.raises(CatalogStoreError):
        validated_terms(
            {
                **record,
                "snapshot": encoded,
                "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
            },
            frozenset(),
        )


def test_binding_cannot_accept_actor_or_signup_override():
    doc = dict(
        binding_id=str(uuid4()),
        offer_version_id=str(uuid4()),
        valid_from="2026-01-01T00:00:00Z",
        valid_until="2027-01-01T00:00:00Z",
        source_ref="synthetic.fixture",
        policy_version="synthetic.usage.v1",
    )
    assert BindingDocument.model_validate(doc).price_id is None
    for override in ("actor", "permissions", "signup_at", "allowance"):
        with pytest.raises(ValidationError):
            BindingDocument.model_validate({**doc, override: "forged"})
    with pytest.raises(ValidationError):
        BindingDocument.model_validate({**doc, "valid_from": "2026-01-01T00:00:00"})


def test_constructor_is_closed_without_a_connection_or_policy():
    calls = []

    def connect():
        calls.append(1)
        raise AssertionError("Must not connect during construction")

    UsageStore(connect)
    UsageReconciler(connect)
    assert calls == []
