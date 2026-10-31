"""F2 actual Python service / restricted LOGIN / disposable native PostgreSQL.

Only synthetic offers and authority; no production composition or live calls.
Explicit --pg-bin required. Owner connections are maintenance/fault fixtures only.
"""

import argparse
import copy
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commercial.lifecycle_service import LifecycleService
from app.commercial.review_contract import ReviewIntent
from app.commercial.review_service import ReviewService
from app.commercial.catalog_store import CatalogStoreError, ErrorCode, RpcFailure
from app.commercial.admin_access import VerifiedActor
from test_catalog_store_native import ROOT, MANAGER, ORDINARY, literal
from test_draft_service_native import (
    database,
    case as draft_case,
    actor,
    failure,
    wait_blocked,
)
from test_review_service_native import (
    install as f1_install,
    case as review_case,
    create,
)

SIGNATURE = "public.catalog_lifecycle_service_call(uuid,text,jsonb,jsonb)"


@pytest.fixture(autouse=True)
def no_http_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No provider, payment or HTTP effects permitted")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("httpx.Client.request", forbidden)


@pytest.fixture(scope="module", autouse=True)
def install(database, f1_install):
    from app.commercial import catalog_contract as c
    from test_catalog_contract import document

    # Pre-F2 hidden/retired archives exercise the additive visibility backfill.
    legacy = []
    for retired in [False, True]:
        raw = document()
        raw.update(draft_id=str(uuid4()), state="draft")
        raw["plan"] = dict(plan_id=str(uuid4()), code="legacy-" + uuid4().hex)
        raw["terms"]["prices"][0]["price_id"] = str(uuid4())
        draft = c.CatalogDraft.model_validate(raw)
        data = draft.model_dump(mode="python")
        data["terms"] = c._normalized(draft.terms).model_dump(mode="python")
        draft = c.CatalogDraft.model_validate(data)
        source = draft.model_dump(mode="python")
        source["state"] = "previewed"
        snap = c.create_snapshot(source, offer_version_id=str(uuid4()), version=1)
        database.run(
            f"""insert into catalog_plans values({literal(draft.plan.plan_id)},{literal(draft.plan.code)});
        insert into catalog_drafts values({literal(draft.draft_id)},{literal(draft.plan.plan_id)},1,{literal(draft.model_dump(mode='json'))});
        insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json)
        values({literal(snap.offer_version_id)},{literal(snap.plan.plan_id)},1,{literal(draft.draft_id)},1,{literal(snap.canonical_json())});"""
        )
        if retired:
            database.run(
                f"""update catalog_visibility set state='retired',revision=2 where offer_version_id={literal(snap.offer_version_id)};
            insert into catalog_admin_actions(actor_subject,permission_revision,operation,resource_id,resulting_revision,reason)
            values({literal(MANAGER)},1,'offer.retire',{literal(snap.offer_version_id)},2,'synthetic historical audit');"""
            )
        legacy.append((snap.offer_version_id, snap.plan.plan_id, retired))
    database.run(
        (
            ROOT
            / "supabase/migrations/20261022220000_catalog_lifecycle_transactions.sql"
        ).read_text()
    )
    for offer_id, plan_id, retired in legacy:
        assert database.rows(
            f"select plan_id::text,(retired_at is not null) as retired from catalog_visibility where offer_version_id={literal(offer_id)}"
        ) == [dict(plan_id=plan_id, retired=retired)]
        if retired:
            assert database.rows(
                f"select v.retired_at=a.recorded_at as exact from catalog_visibility v join catalog_admin_actions a on a.resource_id=v.offer_version_id and a.resulting_revision=v.revision where v.offer_version_id={literal(offer_id)}"
            ) == [{"exact": True}]
    assert database.rows(
        f"select has_function_privilege('catalog_draft_executor','{SIGNATURE}','EXECUTE') as allowed"
    ) == [{"allowed": False}]
    database.run(f"grant execute on function {SIGNATURE} to catalog_draft_executor")


@pytest.fixture
def case(review_case, install):
    db, ds, raw, rs, basis, state, resolver = review_case
    receipt = create(rs, basis).receipt
    return (
        db,
        ds,
        raw,
        rs,
        receipt,
        state,
        resolver,
        LifecycleService(db.connect, resolver=resolver),
    )


def publish(s, receipt, key=None, action="publish"):
    return s.publish(
        actor(),
        receipt.review_id,
        expected_revision=receipt.basis.revision,
        request_id=key or str(uuid4()),
        reason="synthetic publish",
        action=action,
    )


def counts(db):
    return db.rows("""select (select count(*) from catalog_offer_versions) offers,
    (select count(*) from catalog_price_versions) prices,
    (select count(*) from catalog_publications) consumed,
    (select count(*) from catalog_admin_actions) audits,
    (select count(*) from catalog_lifecycle_requests) requests,
    (select revision from catalog_public_state) epoch,
    (select count(*) from catalog_draft_revisions) revisions""")[0]


def retire(s, result, key=None, expected=None):
    return s.retire(
        actor(),
        result.receipt.offer_version_id,
        expected_revision=expected or result.current.revision,
        request_id=key or str(uuid4()),
        reason="synthetic retire",
    )


def test_publish_retire_and_historical_replay(case):
    db, ds, raw, rs, r, state, resolver, s = case
    before = counts(db)
    key = str(uuid4())
    result = publish(s, r, key)
    assert result.current.state == "visible" and not result.publication_enabled
    assert result.current.revision == 2
    assert rs.retrieve(actor(), r.review_id).consumption_state == "not_checked"
    assert publish(s, r, key) == result
    after = counts(db)
    assert {k: after[k] - before[k] for k in before} == dict(
        offers=1, prices=1, consumed=1, audits=2, requests=1, epoch=1, revisions=1
    )
    terms = db.rows(
        f"select canonical_json,fingerprint from catalog_offer_versions where offer_version_id={literal(result.receipt.offer_version_id)}"
    )
    rk = str(uuid4())
    retired = retire(s, result, rk)
    assert retired.current.state == "retired" and retired.current.retired_at
    assert retire(s, result, rk) == retired
    replay = publish(s, r, key)
    assert replay.receipt == result.receipt and replay.current.state == "retired"
    assert replay.current_catalog_revision == result.current_catalog_revision + 1
    assert (
        db.rows(
            f"select canonical_json,fingerprint from catalog_offer_versions where offer_version_id={literal(result.receipt.offer_version_id)}"
        )
        == terms
    )
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))
    failure(ErrorCode.CONFLICT, lambda: retire(s, retired))
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: s.publish(
            actor(), r.review_id, expected_revision=1, request_id=key, reason="changed"
        ),
    )
    failure(
        ErrorCode.CONFLICT,
        lambda: ds.edit(
            actor(),
            dict(raw, revision=3),
            expected_revision=2,
            request_id=str(uuid4()),
            reason="terminal",
        ),
    )


def test_closed_authority_stale_source_and_permissions(case):
    db, ds, raw, rs, r, state, resolver, s = case
    before = counts(db)
    failure(ErrorCode.UNAVAILABLE, lambda: publish(LifecycleService(db.connect), r))
    failure(
        ErrorCode.DENIED,
        lambda: s.publish(
            actor(ORDINARY),
            r.review_id,
            expected_revision=1,
            request_id=str(uuid4()),
            reason="bad",
        ),
    )
    failure(
        ErrorCode.DENIED,
        lambda: s.publish(
            VerifiedActor(MANAGER, actor(ORDINARY)._bearer),
            r.review_id,
            expected_revision=1,
            request_id=str(uuid4()),
            reason="bad",
        ),
    )
    state["authority"] = state["authority"].model_copy(update={"approval_revision": 2})
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))
    assert counts(db) == before
    ds.edit(
        actor(),
        dict(raw, revision=2),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="changed",
    )
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))


def test_concurrent_duplicate_and_conflicting_keys(case):
    db, ds, raw, rs, r, state, resolver, s = case
    key = str(uuid4())
    before = counts(db)
    hold = db.barrier(
        f"select 1 from catalog_plans where plan_id={literal(raw['plan']['plan_id'])} for update;"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                publish,
                LifecycleService(
                    lambda i=i: db.connect(f"f2-dupe-{i}"), resolver=resolver
                ),
                r,
                key,
            )
            for i in range(2)
        ]
        try:
            wait_blocked(db, ["f2-dupe-0", "f2-dupe-1"])
        finally:
            db.release(hold)
        a, b = [f.result(timeout=15) for f in futures]
    assert a == b
    assert counts(db)["consumed"] == before["consumed"] + 1
    assert counts(db)["epoch"] == before["epoch"] + 1


def test_edit_first_invalidates_review(case):
    db, ds, raw, rs, r, state, resolver, s = case
    entered, go = threading.Event(), threading.Event()

    def pause(q, subject, draft):
        entered.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    before = counts(db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        f = pool.submit(publish, LifecycleService(db.connect, resolver=pause), r)
        assert entered.wait(10)
        try:
            ds.edit(
                actor(),
                dict(raw, revision=2),
                expected_revision=1,
                request_id=str(uuid4()),
                reason="wins",
            )
        finally:
            go.set()
        failure(ErrorCode.CONFLICT, lambda: f.result(timeout=15))
    after = counts(db)
    for k in ["offers", "prices", "consumed", "epoch"]:
        assert after[k] == before[k]


def test_publish_first_freezes_source(case):
    db, ds, raw, rs, r, state, resolver, s = case
    entered, go = threading.Event(), threading.Event()

    class Pause(LifecycleService):
        def _basis(self, *args):
            value = super()._basis(*args)
            entered.set()
            assert go.wait(10)
            return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        pub = pool.submit(publish, Pause(db.connect, resolver=resolver), r)
        assert entered.wait(10)
        editor = type(ds)(lambda: db.connect("f2-edit-loses"))
        edit = pool.submit(
            lambda: editor.edit(
                actor(),
                dict(raw, revision=2),
                expected_revision=1,
                request_id=str(uuid4()),
                reason="loses",
            )
        )
        try:
            wait_blocked(db, ["f2-edit-loses"])
        finally:
            go.set()
        assert pub.result(timeout=15).current.state == "visible"
        failure(ErrorCode.CONFLICT, lambda: edit.result(timeout=15))


@pytest.mark.parametrize("committed", [True, False])
def test_uncertain_commit_same_key_recovery(case, committed):
    db, ds, raw, rs, r, state, resolver, s = case
    before = counts(db)
    key = str(uuid4())

    class Lost:
        def __init__(self):
            self.conn = db.connect()

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            if committed:
                self.conn.commit()
            else:
                self.conn.rollback()
            raise OSError("synthetic lost acknowledgment")

    failure(
        ErrorCode.UNCERTAIN,
        lambda: publish(LifecycleService(Lost, resolver=resolver), r, key),
    )
    answer = publish(s, r, key)
    assert publish(s, r, key) == answer
    after = counts(db)
    assert after["consumed"] == before["consumed"] + 1
    assert after["epoch"] == before["epoch"] + 1


@pytest.mark.parametrize(
    "operation", ["snapshot.archive", "offer.publish", "offer.retire"]
)
def test_audit_failure_rolls_back_everything(case, operation):
    db, ds, raw, rs, r, state, resolver, s = case
    existing = publish(s, r) if operation == "offer.retire" else None
    before = counts(db)
    db.run(
        f"""create function f2_fail_audit() returns trigger language plpgsql as $$
    begin if new.operation={literal(operation)} then raise exception 'synthetic failure'; end if; return new; end; $$;
    create trigger f2_fail before insert on catalog_admin_actions for each row execute function f2_fail_audit();"""
    )
    try:
        with pytest.raises(CatalogStoreError):
            retire(s, existing) if existing else publish(s, r)
        assert counts(db) == before
    finally:
        db.run(
            "drop trigger f2_fail on catalog_admin_actions; drop function f2_fail_audit();"
        )
    result = retire(s, existing) if existing else publish(s, r)
    assert result.current.state == ("retired" if existing else "visible")


def test_replacement_and_fresh_head_precondition(case):
    db, ds, raw, rs, r, state, resolver, s = case
    old = publish(s, r)
    immutable = db.rows(
        f"select canonical_json,fingerprint from catalog_offer_versions where offer_version_id={literal(old.receipt.offer_version_id)}"
    )
    new = copy.deepcopy(raw)
    new["draft_id"] = str(uuid4())
    new["terms"]["prices"][0]["price_id"] = str(uuid4())
    ds.create(actor(), new, request_id=str(uuid4()), reason="successor")
    basis = rs.basis(
        actor(),
        new["draft_id"],
        expected_revision=1,
        intent=ReviewIntent(action="replace", valid_from=r.basis.intent.valid_from),
    )
    reviewed = create(rs, basis).receipt
    before = counts(db)
    failure(ErrorCode.CONFLICT, lambda: publish(s, reviewed))
    replacement = publish(s, reviewed, action="replace")
    assert replacement.current.state == "visible"
    assert counts(db)["epoch"] == before["epoch"] + 1
    assert db.rows(
        f"select state from catalog_visibility where offer_version_id={literal(old.receipt.offer_version_id)}"
    ) == [{"state": "retired"}]
    assert (
        db.rows(
            f"select canonical_json,fingerprint from catalog_offer_versions where offer_version_id={literal(old.receipt.offer_version_id)}"
        )
        == immutable
    )
    assert db.rows(
        f"select count(*) as n from catalog_visibility where plan_id={literal(raw['plan']['plan_id'])} and state='visible'"
    ) == [{"n": 1}]


@pytest.mark.parametrize("revoke_first", [True, False])
def test_revocation_order_and_replay_denial(case, revoke_first):
    db, ds, raw, rs, r, state, resolver, s = case
    key = str(uuid4())
    if revoke_first:
        hold = db.barrier(
            f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)};"
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            f = pool.submit(
                publish,
                LifecycleService(lambda: db.connect("f2-revoked"), resolver=resolver),
                r,
                key,
            )
            try:
                wait_blocked(db, ["f2-revoked"])
            finally:
                db.release(hold)
            failure(ErrorCode.DENIED, lambda: f.result(timeout=15))
        return
    entered, go = threading.Event(), threading.Event()

    def pause(q, subject, draft):
        entered.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    def revoke():
        db.run(
            f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)};",
            app="f2-revoker",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f = pool.submit(publish, LifecycleService(db.connect, resolver=pause), r, key)
        assert entered.wait(10)
        rev = pool.submit(revoke)
        try:
            wait_blocked(db, ["f2-revoker"])
        finally:
            go.set()
        result = f.result(timeout=15)
        rev.result(timeout=15)
    failure(ErrorCode.DENIED, lambda: publish(s, r, key))
    failure(ErrorCode.DENIED, lambda: retire(s, result))


def test_retirement_without_policy_authority(case):
    db, ds, raw, rs, r, state, resolver, s = case
    result = publish(s, r)
    retired = retire(LifecycleService(db.connect), result)
    assert retired.current.state == "retired"
    db.run(
        f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)}"
    )
    failure(ErrorCode.DENIED, lambda: retire(s, result, retired.receipt.request_id))


@pytest.mark.parametrize(
    "field,value",
    [
        ("terms_fingerprint", "b" * 64),
        ("validation_policy_version", "future.v2"),
        ("contract_version", "future.v2"),
        ("source_hash", "b" * 64),
    ],
)
def test_corrupt_receipt_rejected(case, field, value):
    db, ds, raw, rs, r, state, resolver, s = case
    before = counts(db)
    # Privileged fault injection only; ordinary roles cannot alter metadata.
    # Schema-version CHECKs deliberately need maintenance disabling to inject.
    if field in ("validation_policy_version", "contract_version"):
        with pytest.raises(RpcFailure) as error:
            db.run(
                f"alter table catalog_publication_reviews disable trigger immutable_rows; update catalog_publication_reviews set metadata=jsonb_set(metadata,'{{{field}}}',to_jsonb({literal(value)}::text)) where review_id={literal(r.review_id)};"
            )
        assert error.value.sqlstate == "23514"
        # Constraints cannot store this unsupported version at all.
        db.run("alter table catalog_publication_reviews enable trigger immutable_rows")
        return
    db.run(f"""alter table catalog_publication_reviews disable trigger immutable_rows;
    update catalog_publication_reviews set metadata=jsonb_set(metadata,'{{{field}}}',to_jsonb({literal(value)}::text)) where review_id={literal(r.review_id)};
    update catalog_publication_reviews set metadata_hash=encode(sha256(convert_to(metadata::text,'UTF8')),'hex') where review_id={literal(r.review_id)};
    alter table catalog_publication_reviews enable trigger immutable_rows;""")
    failure(ErrorCode.STORED_INVALID, lambda: publish(s, r))
    assert counts(db) == before


def test_incomplete_and_expired_receipt(case):
    from datetime import datetime, timedelta, timezone

    db, ds, raw, rs, r, state, resolver, s = case
    before = counts(db)
    state["authority"] = state["authority"].model_copy(
        update={"valid_until": datetime.now(timezone.utc) - timedelta(hours=1)}
    )
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))
    assert counts(db) == before
    ds.edit(
        actor(),
        dict(raw, revision=2, terms={}),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="incomplete",
    )
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))


def test_immutable_history_and_role_denials(case):
    db, ds, raw, rs, r, state, resolver, s = case
    result = publish(s, r)
    oid = literal(result.receipt.offer_version_id)
    for role in ["anon", "authenticated", "service_role", "catalog_draft_executor"]:
        for sql in [
            "delete from catalog_publications",
            "update catalog_offer_versions set canonical_json='{}'",
            "delete from catalog_plans",
            "truncate catalog_publication_reviews cascade",
            "update subscription_admin_permissions set active=true",
            f"insert into catalog_visibility(offer_version_id,plan_id) values({oid},{literal(raw['plan']['plan_id'])}) on conflict(offer_version_id) do update set state='visible'",
        ]:
            with pytest.raises(RpcFailure) as error:
                db.run(f"set role {role}; {sql}")
            assert error.value.sqlstate == "42501"
        if role != "catalog_draft_executor":
            assert db.rows(
                f"select has_function_privilege('{role}','{SIGNATURE}','EXECUTE') as allowed"
            ) == [{"allowed": False}]
    with db.connect() as conn:
        assert conn.execute(
            "select rolsuper,rolbypassrls from pg_roles where rolname=current_user"
        ).fetchone() == (False, False)
    # Even privileged ordinary DML meets immutable triggers. A maintenance owner
    # can disable triggers/alter schema; that power is outside application guarantees.
    for sql in [
        "update catalog_price_versions set document=document",
        "delete from catalog_publications",
        "update catalog_offer_versions set canonical_json=canonical_json",
    ]:
        with pytest.raises(RpcFailure) as error:
            db.run(sql)
        assert error.value.sqlstate == "55000"


def test_constructor_and_invalid_payload_no_writes(case):
    db, ds, raw, rs, r, state, resolver, s = case
    called = []
    LifecycleService(lambda: called.append(1))
    assert not called
    before = counts(db)
    failure(
        ErrorCode.INVALID,
        lambda: s.publish(
            actor(),
            {"actor": MANAGER},
            expected_revision=1,
            request_id=str(uuid4()),
            reason="bad",
        ),
    )
    failure(
        ErrorCode.INVALID,
        lambda: s.publish(
            actor(),
            r.review_id,
            expected_revision=0,
            request_id=str(uuid4()),
            reason="bad",
        ),
    )
    assert counts(db) == before


def successor(db, ds, raw, rs, r):
    new = copy.deepcopy(raw)
    new["draft_id"] = str(uuid4())
    new["terms"]["prices"][0]["price_id"] = str(uuid4())
    ds.create(actor(), new, request_id=str(uuid4()), reason="synthetic successor")
    basis = rs.basis(
        actor(),
        new["draft_id"],
        expected_revision=1,
        intent=ReviewIntent(action="replace", valid_from=r.basis.intent.valid_from),
    )
    return create(rs, basis).receipt


@pytest.mark.parametrize("retire_first", [True, False])
def test_replace_retire_race(case, retire_first):
    db, ds, raw, rs, r, state, resolver, s = case
    current = publish(s, r)
    next_review = successor(db, ds, raw, rs, r)
    entered, go = threading.Event(), threading.Event()

    def pause(q, subject, draft):
        entered.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    class Locked(LifecycleService):
        def _basis(self, *args):
            value = super()._basis(*args)
            entered.set()
            assert go.wait(10)
            return value

    publisher = (
        LifecycleService(db.connect, resolver=pause)
        if retire_first
        else Locked(db.connect, resolver=resolver)
    )
    before = counts(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pub = pool.submit(publish, publisher, next_review, None, "replace")
        assert entered.wait(10)
        if retire_first:
            try:
                retire(s, current)
            finally:
                go.set()
            failure(ErrorCode.CONFLICT, lambda: pub.result(timeout=15))
        else:
            retiring = LifecycleService(lambda: db.connect("f2-retire-loses"))
            loser = pool.submit(retire, retiring, current)
            try:
                wait_blocked(db, ["f2-retire-loses"])
            finally:
                go.set()
            assert pub.result(timeout=15).current.state == "visible"
            failure(ErrorCode.CONFLICT, lambda: loser.result(timeout=15))
    assert counts(db)["epoch"] == before["epoch"] + 1


def test_hidden_archive_reuse_and_stale_retirement(case):
    from app.commercial import catalog_contract as c

    db, ds, raw, rs, r, state, resolver, s = case
    # Isolated maintenance creates an exact validated hidden archive. It does not
    # grant the older archive path to the application principal.
    source = ds.retrieve(actor(), raw["draft_id"]).model_dump(mode="python")
    source["state"] = "previewed"
    snap = c.create_snapshot(source, offer_version_id=str(uuid4()), version=1)
    db.run(
        f"""insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json)
    values({literal(snap.offer_version_id)},{literal(snap.plan.plan_id)},1,{literal(raw['draft_id'])},1,{literal(snap.canonical_json())});"""
    )
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))
    basis = rs.basis(
        actor(), raw["draft_id"], expected_revision=1, intent=r.basis.intent
    )
    assert basis.archived_offer.offer_version_id == snap.offer_version_id
    reviewed = create(rs, basis).receipt
    before = counts(db)
    result = publish(s, reviewed)
    assert result.receipt.offer_version_id == snap.offer_version_id
    assert counts(db)["offers"] == before["offers"]
    assert counts(db)["audits"] == before["audits"] + 1
    failure(ErrorCode.CONFLICT, lambda: retire(s, result, expected=1))


def test_different_keys_one_consumption(case):
    db, ds, raw, rs, r, state, resolver, s = case
    other_review = create(rs, r.basis).receipt
    hold = db.barrier(
        f"select 1 from catalog_plans where plan_id={literal(raw['plan']['plan_id'])} for no key update;"
    )
    before = counts(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                publish,
                LifecycleService(
                    lambda i=i: db.connect(f"f2-keys-{i}"), resolver=resolver
                ),
                rr,
            )
            for i, rr in enumerate([r, other_review])
        ]
        try:
            wait_blocked(db, ["f2-keys-0", "f2-keys-1"])
        finally:
            db.release(hold)
        won, lost = 0, 0
        for f in futures:
            try:
                f.result(timeout=15)
                won += 1
            except CatalogStoreError as exc:
                assert exc.code == ErrorCode.CONFLICT
                lost += 1
    assert (won, lost) == (1, 1)
    assert counts(db)["consumed"] == before["consumed"] + 1
    assert counts(db)["epoch"] == before["epoch"] + 1


def test_retirement_transaction_failure_and_request_conflict(case):
    db, ds, raw, rs, r, state, resolver, s = case
    result = publish(s, r)
    before = counts(db)
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: retire(s, result, result.receipt.request_id),
    )
    assert counts(db) == before


@pytest.mark.parametrize("retire_first", [True, False])
def test_publish_retire_same_hidden_archive(case, retire_first):
    from app.commercial import catalog_contract as c

    db, ds, raw, rs, r, state, resolver, s = case
    source = ds.retrieve(actor(), raw["draft_id"]).model_dump(mode="python")
    source["state"] = "previewed"
    snap = c.create_snapshot(source, offer_version_id=str(uuid4()), version=1)
    db.run(
        f"""insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json)
    values({literal(snap.offer_version_id)},{literal(snap.plan.plan_id)},1,{literal(raw['draft_id'])},1,{literal(snap.canonical_json())});"""
    )
    reviewed = create(
        rs,
        rs.basis(actor(), raw["draft_id"], expected_revision=1, intent=r.basis.intent),
    ).receipt
    entered, go = threading.Event(), threading.Event()

    def pause(q, subject, draft):
        entered.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    class Locked(LifecycleService):
        def _basis(self, *args):
            value = super()._basis(*args)
            entered.set()
            assert go.wait(10)
            return value

    def retire_hidden():
        return LifecycleService(lambda: db.connect("f2-hidden-retire")).retire(
            actor(),
            snap.offer_version_id,
            expected_revision=1,
            request_id=str(uuid4()),
            reason="synthetic hidden retire",
        )

    publisher = (
        LifecycleService(db.connect, resolver=pause)
        if retire_first
        else Locked(db.connect, resolver=resolver)
    )
    before = counts(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pub = pool.submit(publish, publisher, reviewed)
        assert entered.wait(10)
        if retire_first:
            try:
                assert retire_hidden().current.state == "retired"
            finally:
                go.set()
            failure(ErrorCode.CONFLICT, lambda: pub.result(timeout=15))
        else:
            retirement = pool.submit(retire_hidden)
            try:
                wait_blocked(db, ["f2-hidden-retire"])
            finally:
                go.set()
            assert pub.result(timeout=15).current.state == "visible"
            failure(ErrorCode.CONFLICT, lambda: retirement.result(timeout=15))
    assert counts(db)["epoch"] == before["epoch"] + 1
    assert counts(db)["consumed"] == before["consumed"] + (0 if retire_first else 1)


def test_same_plan_other_draft_edit_does_not_deadlock(case):
    db, ds, raw, rs, r, state, resolver, s = case
    other = copy.deepcopy(raw)
    other["draft_id"] = str(uuid4())
    other["terms"]["prices"][0]["price_id"] = str(uuid4())
    ds.create(actor(), other, request_id=str(uuid4()), reason="same plan")
    entered, go = threading.Event(), threading.Event()

    class Locked(LifecycleService):
        def _basis(self, *args):
            result = super()._basis(*args)
            entered.set()
            assert go.wait(10)
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        pub = pool.submit(publish, Locked(db.connect, resolver=resolver), r)
        assert entered.wait(10)
        try:
            edit = pool.submit(
                lambda: ds.edit(
                    actor(),
                    dict(other, revision=2),
                    expected_revision=1,
                    request_id=str(uuid4()),
                    reason="independent source",
                )
            )
            # Must commit while publication still holds its plan lock. No race
            # sleeps, weakened lock budgets or deadlock retries.
            assert edit.result(timeout=5).revision == 2
        finally:
            go.set()
        assert pub.result(timeout=15).current.state == "visible"


def test_expired_historical_receipt_has_no_effects(case):
    db, ds, raw, rs, r, state, resolver, s = case
    rid = literal(r.review_id)
    before = counts(db)
    # Maintenance constructs a historical receipt, not a production expiry rule.
    db.run(f"""alter table catalog_publication_reviews disable trigger immutable_rows;
    update catalog_publication_reviews set recorded_at=clock_timestamp()-interval '2 days',
    metadata=jsonb_set(jsonb_set(metadata,'{{authority,valid_from}}',to_jsonb((clock_timestamp()-interval '3 days')::text)),
    '{{authority,valid_until}}',to_jsonb((clock_timestamp()-interval '1 day')::text)) where review_id={rid};
    update catalog_publication_reviews set metadata_hash=encode(sha256(convert_to(metadata::text,'UTF8')),'hex') where review_id={rid};
    alter table catalog_publication_reviews enable trigger immutable_rows;""")
    failure(ErrorCode.CONFLICT, lambda: publish(s, r))
    assert counts(db) == before
    failure(
        ErrorCode.NOT_FOUND,
        lambda: s.retire(
            actor(),
            str(uuid4()),
            expected_revision=1,
            request_id=str(uuid4()),
            reason="missing",
        ),
    )
    assert counts(db) == before


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )
