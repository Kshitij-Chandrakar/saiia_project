import argparse, sys, copy, threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commercial.review_service import ReviewService
from app.commercial.review_contract import ReviewAuthority, ReviewIntent
from app.commercial.draft_service import DraftService
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from test_draft_service_native import database as database, actor, failure, wait_blocked
from test_draft_service_native import case as draft_case
from test_catalog_store_native import ROOT, MANAGER, ORDINARY, literal

SIGNATURE = "public.catalog_review_service_call(uuid,text,uuid,uuid,jsonb,jsonb)"


@pytest.fixture(scope="module", autouse=True)
def install(database):
    database.run(
        (
            ROOT / "supabase/migrations/20261022210000_catalog_publication_reviews.sql"
        ).read_text()
    )
    assert database.rows(
        f"select has_function_privilege('catalog_draft_executor','{SIGNATURE}','EXECUTE') as allowed"
    ) == [{"allowed": False}]
    database.run(
        f"alter role catalog_draft_executor login;grant execute on function {SIGNATURE} to catalog_draft_executor;"
    )
    import psycopg

    def connect(app="review-test"):
        return psycopg.connect(
            host="127.0.0.1",
            port=database.port,
            dbname="postgres",
            user="catalog_draft_executor",
            application_name=app,
            options="-c transaction_timeout=20000 -c idle_in_transaction_session_timeout=15000",
            connect_timeout=3,
        )

    database.connect = connect
    return database


@pytest.fixture
def case(draft_case, install):
    db, ds, raw = draft_case
    ds.create(actor(), raw, request_id=str(uuid4()), reason="synthetic")
    now = datetime.now(timezone.utc)
    authority = ReviewAuthority(
        policy_id=str(uuid4()),
        policy_version=1,
        policy_fingerprint="a" * 64,
        approval_revision=1,
        reviewer_rule_ref="synthetic.rule",
        model_registry_version="synthetic.models",
        model_keys=(),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    state = {"authority": authority}

    def resolver(query, subject, draft):
        return state["authority"]

    service = ReviewService(db.connect, resolver=resolver)
    basis = service.basis(
        actor(),
        raw["draft_id"],
        expected_revision=1,
        intent=ReviewIntent(action="publish", valid_from=now),
    )
    return db, ds, raw, service, basis, state, resolver


def count(db):
    return db.rows(
        "select (select count(*) from catalog_publication_reviews) as reviews,(select count(*) from catalog_lifecycle_requests) as requests,(select count(*) from catalog_admin_actions where operation='review.create') as audits"
    )[0]


def create(service, basis, key=None):
    return service.create(
        actor(), basis, request_id=key or str(uuid4()), reason="synthetic review"
    )


def test_roundtrip_retry_and_no_publication(case):
    db, ds, raw, s, b, state, resolver = case
    before = count(db)
    key = str(uuid4())
    a = create(s, b, key)
    assert a.state == "current" and not a.publication_enabled
    assert s.retrieve(actor(), a.receipt.review_id) == a
    assert create(s, b, key) == a
    after = count(db)
    assert all(after[k] == before[k] + 1 for k in before)
    assert db.rows("select count(*) as n from catalog_offer_versions")[0]["n"] == 0
    assert db.rows("select count(*) as n from catalog_visibility")[0]["n"] == 0
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: s.create(actor(), b, request_id=key, reason="different"),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("terms_fingerprint", "b" * 64),
        ("revision", 2),
        ("validation_policy_version", "bad"),
        ("reviewer_subject", MANAGER),
    ],
)
def test_wrong_binding(case, field, value):
    db, ds, raw, s, b, *_ = case
    before = count(db)
    data = b.model_dump(mode="json")
    data[field] = value
    with pytest.raises(CatalogStoreError):
        create(s, data)
    assert count(db) == before


def test_changed_draft_and_replay(case):
    db, ds, raw, s, b, *_ = case
    key = str(uuid4())
    r = create(s, b, key)
    ds.edit(
        actor(),
        dict(raw, revision=2, internal_notes="edited"),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="edit",
    )
    assert s.retrieve(actor(), r.receipt.review_id).state == "draft_changed"
    assert create(s, b, key).state == "draft_changed"
    failure(ErrorCode.CONFLICT, lambda: create(s, b))


def test_incomplete(case):
    db, ds, raw, s, b, *_ = case
    ds.edit(
        actor(),
        dict(raw, revision=2, terms={}),
        expected_revision=1,
        request_id=str(uuid4()),
        reason="incomplete",
    )
    failure(
        ErrorCode.INVALID,
        lambda: s.basis(actor(), raw["draft_id"], expected_revision=2, intent=b.intent),
    )


def test_denial_revocation_and_policy_failure(case):
    db, ds, raw, s, b, state, resolver = case
    r = create(s, b)
    for f in [
        lambda: s.retrieve(actor(ORDINARY), r.receipt.review_id),
        lambda: s.create(actor(ORDINARY), b, request_id=str(uuid4()), reason="bad"),
    ]:
        failure(ErrorCode.DENIED, f)
    db.run(
        f"update subscription_admin_permissions set active=false,revision=revision+1 where subject_id={literal(MANAGER)}"
    )
    failure(ErrorCode.DENIED, lambda: s.retrieve(actor(), r.receipt.review_id))
    failure(ErrorCode.DENIED, lambda: create(s, b))


def test_authority_changes_and_closed_default(case):
    db, ds, raw, s, b, state, resolver = case
    r = create(s, b)
    state["authority"] = state["authority"].model_copy(update={"approval_revision": 2})
    assert s.retrieve(actor(), r.receipt.review_id).state == "authority_changed"
    assert (
        ReviewService(db.connect).retrieve(actor(), r.receipt.review_id).state
        == "authority_unavailable"
    )
    failure(
        ErrorCode.UNAVAILABLE,
        lambda: ReviewService(db.connect).basis(
            actor(), raw["draft_id"], expected_revision=1, intent=b.intent
        ),
    )


def test_concurrent_duplicates(case):
    db, ds, raw, s, b, state, resolver = case
    key = str(uuid4())
    before = count(db)
    hold = db.barrier(
        f"select 1 from catalog_drafts where draft_id={literal(raw['draft_id'])} for update;"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                create,
                ReviewService(
                    lambda i=i: db.connect(f"review-dupe-{i}"), resolver=resolver
                ),
                b,
                key,
            )
            for i in range(2)
        ]
        try:
            wait_blocked(db, ["review-dupe-0", "review-dupe-1"])
        finally:
            db.release(hold)
        assert futures[0].result(timeout=15) == futures[1].result(timeout=15)
    assert all(count(db)[k] == before[k] + 1 for k in before)


def test_edit_during_resolution(case):
    db, ds, raw, s, b, state, resolver = case
    ready = threading.Event()
    go = threading.Event()

    def paused(q, subject, draft):
        ready.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    with ThreadPoolExecutor(max_workers=1) as pool:
        f = pool.submit(create, ReviewService(db.connect, resolver=paused), b)
        try:
            assert ready.wait(10)
            ds.edit(
                actor(),
                dict(raw, revision=2, internal_notes="race"),
                expected_revision=1,
                request_id=str(uuid4()),
                reason="edit",
            )
        finally:
            go.set()
        with pytest.raises(CatalogStoreError) as e:
            f.result(timeout=15)
        assert e.value.code == ErrorCode.CONFLICT


def test_rollback(case):
    db, ds, raw, s, b, *_ = case
    before = count(db)
    db.run(
        "create function public.fail_review_test() returns trigger language plpgsql as $$begin if new.operation='review.create' then raise exception 'synthetic' using errcode='23514';end if;return new;end$$;create trigger fail_review_test before insert on catalog_admin_actions for each row execute function public.fail_review_test();"
    )
    try:
        failure(ErrorCode.INVALID, lambda: create(s, b))
    finally:
        db.run(
            "drop trigger fail_review_test on catalog_admin_actions;drop function fail_review_test();"
        )
    assert count(db) == before


@pytest.mark.parametrize("committed", [True, False])
def test_uncertain_commit_recovery(case, committed):
    db, ds, raw, s, b, state, resolver = case
    key = str(uuid4())
    before = count(db)

    class Connection:
        def __init__(self):
            self.conn = db.connect()

        def __getattr__(self, k):
            return getattr(self.conn, k)

        def commit(self):
            if committed:
                self.conn.commit()
            raise OSError("synthetic sensitive detail")

    failure(
        ErrorCode.UNCERTAIN,
        lambda: create(ReviewService(Connection, resolver=resolver), b, key),
    )
    r = create(s, b, key)
    assert r.state == "current"
    assert all(count(db)[k] == before[k] + 1 for k in before)


def test_corrupt_receipt(case):
    db, ds, raw, s, b, *_ = case
    r = create(s, b)
    rid = literal(r.receipt.review_id)
    db.run(
        f"alter table catalog_publication_reviews disable trigger immutable_rows;update catalog_publication_reviews set metadata=jsonb_set(metadata,'{{terms_fingerprint}}',to_jsonb(repeat('b',64))) where review_id={rid};alter table catalog_publication_reviews enable trigger immutable_rows;"
    )
    failure(ErrorCode.STORED_INVALID, lambda: s.retrieve(actor(), r.receipt.review_id))


def test_expired_historical_evidence(case):
    db, ds, raw, s, b, *_ = case
    r = create(s, b)
    rid = literal(r.receipt.review_id)
    # Maintenance fixture constructs historical timestamps, without sleeping or
    # changing system time. Ordinary application roles cannot edit this history.
    db.run(
        f"alter table catalog_publication_reviews disable trigger immutable_rows;update catalog_publication_reviews set recorded_at=clock_timestamp()-interval '2 days',metadata=jsonb_set(jsonb_set(metadata,'{{authority,valid_from}}',to_jsonb((clock_timestamp()-interval '3 days')::text)),'{{authority,valid_until}}',to_jsonb((clock_timestamp()-interval '1 day')::text)) where review_id={rid};update catalog_publication_reviews set metadata_hash=encode(sha256(convert_to(metadata::text,'UTF8')),'hex') where review_id={rid};alter table catalog_publication_reviews enable trigger immutable_rows;"
    )
    assert s.retrieve(actor(), r.receipt.review_id).state == "expired"
    past = b.model_dump(mode="json")
    past["authority"]["valid_until"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    failure(ErrorCode.CONFLICT, lambda: create(s, past))


def test_review_before_revocation(case):
    db, ds, raw, s, b, state, resolver = case
    entered = threading.Event()
    go = threading.Event()

    def pause(q, subject, draft):
        entered.set()
        assert go.wait(10)
        return resolver(q, subject, draft)

    before = count(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        review = pool.submit(
            create, ReviewService(lambda: db.connect("review-first"), resolver=pause), b
        )
        assert entered.wait(10)

        def revoke():
            import psycopg

            with psycopg.connect(
                host="127.0.0.1",
                port=db.port,
                dbname="postgres",
                user="catalog_test_owner",
                application_name="review-revoke",
                connect_timeout=3,
            ) as conn:
                conn.execute("set local statement_timeout=10000")
                conn.execute(
                    "update subscription_admin_permissions set active=false,revision=revision+1 where subject_id=%s",
                    (MANAGER,),
                )

        revoke_future = pool.submit(revoke)
        try:
            wait_blocked(db, ["review-revoke"])
        finally:
            go.set()
        r = review.result(timeout=15)
        revoke_future.result(timeout=15)
    assert count(db)["reviews"] == before["reviews"] + 1
    failure(ErrorCode.DENIED, lambda: s.retrieve(actor(), r.receipt.review_id))


def test_acl_and_import_construction(case):
    db, ds, raw, s, b, *_ = case
    for role in ["anon", "authenticated", "service_role"]:
        rows = db.rows(
            f"select has_function_privilege('{role}','{SIGNATURE}','EXECUTE') as execute,has_table_privilege('{role}','catalog_publication_reviews','INSERT,UPDATE,DELETE,SELECT') as tables"
        )
        assert rows == [{"execute": False, "tables": False}]
    with db.connect() as conn:
        assert conn.execute(
            "select rolsuper,rolbypassrls from pg_roles where rolname=current_user"
        ).fetchone() == (False, False)
        with pytest.raises(Exception):
            conn.execute("delete from catalog_publication_reviews")
    called = []
    ReviewService(lambda: called.append(1))
    assert not called
    failure(
        ErrorCode.UNAVAILABLE,
        lambda: ReviewService().basis(
            actor(), b.draft_id, expected_revision=1, intent=b.intent
        ),
    )


def test_forged_actor_and_fractional_timestamps(case):
    from app.commercial.admin_access import VerifiedActor
    from app.commercial import catalog_contract as c

    db, ds, raw, service, basis, *_ = case
    failure(
        ErrorCode.DENIED,
        lambda: service.create(
            VerifiedActor(MANAGER, actor(ORDINARY)._bearer),
            basis,
            request_id=str(uuid4()),
            reason="forged",
        ),
    )
    for digits in ["1", "12", "1234", "12345", "123456"]:
        assert (
            c._instant("2026-01-01T00:00:00." + digits + "+05:30")
            .utcoffset()
            .total_seconds()
            == 0
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pg-bin", required=True)
    args = p.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )
