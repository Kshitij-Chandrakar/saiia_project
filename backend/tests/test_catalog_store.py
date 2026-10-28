"""Pure validation/fault supplements; native coverage is in the adjacent runner."""

import importlib
import json
import os
import sys

import pytest
from app.commercial import catalog_contract as c
from app.commercial import catalog_store as s
from test_catalog_contract import DRAFT, OFFER, document


def draft():
    return dict(document(), state="draft")


def envelope(value=None):
    data = c.CatalogDraft.model_validate(draft() if value is None else value)
    return dict(
        storage_version="catalog.store.v1",
        draft_id=data.draft_id,
        plan_id=data.plan.plan_id,
        revision=str(data.revision),
        document=data.model_dump(mode="json"),
    )


def test_import_construction_closed_and_no_config(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected application environment/network access")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    original = os.getenv

    def environment(name, *args):
        if name.startswith("PYDANTIC_"):
            return original(name, *args)
        forbidden()

    monkeypatch.setattr(os, "getenv", environment)
    # Execute the same source freshly without replacing exception classes already
    # held by other modules collected in this pytest process.
    spec = importlib.util.spec_from_file_location(
        "catalog_store_import_acceptance", s.__file__
    )
    isolated = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, isolated)
    spec.loader.exec_module(isolated)
    store = isolated.CatalogStore()
    with pytest.raises(isolated.CatalogStoreError) as caught:
        store.load_draft(DRAFT)
    assert caught.value.code == isolated.ErrorCode.UNAVAILABLE
    assert "settings" not in isolated.__dict__


@pytest.mark.parametrize(
    "code,expected",
    [
        ("P0002", "catalog_not_found"),
        ("40001", "catalog_revision_conflict"),
        ("23505", "catalog_revision_conflict"),
        ("42501", "catalog_permission_denied"),
        ("23514", "catalog_invalid_data"),
        ("22003", "catalog_invalid_data"),
        ("55000", "catalog_invalid_data"),
        ("57014", "catalog_database_unavailable"),
        ("42P01", "catalog_database_unavailable"),
        ("08006", "catalog_write_uncertain"),
        (None, "catalog_write_uncertain"),
    ],
)
def test_safe_database_outcomes_no_retry(code, expected):
    calls = []

    def rpc(name, payload):
        calls.append(name)
        raise s.RpcFailure(code)

    with pytest.raises(s.CatalogStoreError) as caught:
        s.CatalogStore(rpc).save_draft(draft(), expected_revision=0, reason="synthetic")
    assert str(caught.value) == expected
    assert len(calls) == 1


def test_undispatched_and_unknown_transport_errors():
    def refused(*args):
        raise s.RpcFailure(dispatched=False)

    def unknown(*args):
        raise RuntimeError("PRIVATE SQL CREDENTIAL PAYLOAD")

    for rpc, expected in [
        (refused, s.ErrorCode.UNAVAILABLE),
        (unknown, s.ErrorCode.UNCERTAIN),
    ]:
        with pytest.raises(s.CatalogStoreError) as caught:
            s.CatalogStore(rpc).save_draft(
                draft(), expected_revision=0, reason="synthetic"
            )
        assert caught.value.code == expected
        assert "PRIVATE" not in str(caught.value)
    with pytest.raises(s.CatalogStoreError) as caught:
        s.CatalogStore(unknown).load_draft(DRAFT)
    assert caught.value.code == s.ErrorCode.UNAVAILABLE


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(revision=True),
        lambda x: x.update(state="published"),
        lambda x: x["terms"].update(
            entitlements=[dict(feature="mock.interviews", allowed=True)]
        ),
        lambda x: x.update(actor="forged"),
    ],
)
def test_invalid_input_never_calls_transport(change):
    calls = []
    value = draft()
    change(value)
    with pytest.raises(s.CatalogStoreError) as caught:
        s.CatalogStore(lambda *a: calls.append(a)).save_draft(
            value, expected_revision=0, reason="test"
        )
    assert caught.value.code == s.ErrorCode.INVALID
    assert not calls


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(storage_version="future.v2"),
        lambda x: x.update(revision="2"),
        lambda x: x.update(plan_id=OFFER),
        lambda x: x["document"].update(contract_version="future.v2"),
        lambda x: x.update(private_extra="PRIVATE"),
    ],
)
def test_bad_stored_envelope_safe_and_bad_write_ack_uncertain(change):
    row = envelope()
    change(row)
    store = s.CatalogStore(lambda *args: row)
    with pytest.raises(s.CatalogStoreError) as caught:
        store.load_draft(DRAFT)
    assert caught.value.code == s.ErrorCode.STORED_INVALID
    with pytest.raises(s.CatalogStoreError) as caught:
        store.save_draft(draft(), expected_revision=0, reason="test")
    assert caught.value.code == s.ErrorCode.UNCERTAIN


def test_snapshot_read_integrity_and_recompute():
    snapshot = c.create_snapshot(document(), offer_version_id=OFFER, version=1)
    row = dict(
        storage_version="catalog.store.v1",
        offer_version_id=OFFER,
        plan_id=snapshot.plan.plan_id,
        version="1",
        source_draft_id=DRAFT,
        source_revision="1",
        canonical_json=snapshot.canonical_json(),
        fingerprint=snapshot.fingerprint,
        prices=[p.model_dump(mode="json") for p in snapshot.terms.prices],
    )
    assert (
        s.CatalogStore(lambda *a: row).load_snapshot(OFFER).fingerprint
        == snapshot.fingerprint
    )
    for key, value in [
        ("fingerprint", "0" * 64),
        ("prices", []),
        ("storage_version", "future.v2"),
        ("canonical_json", json.dumps(json.loads(snapshot.canonical_json()), indent=2)),
        ("canonical_json", '{"PRIVATE":true}'),
    ]:
        bad = dict(row)
        bad[key] = value
        with pytest.raises(s.CatalogStoreError) as caught:
            s.CatalogStore(lambda *a: bad).load_snapshot(OFFER)
        assert caught.value.code == s.ErrorCode.STORED_INVALID
