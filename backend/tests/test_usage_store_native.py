"""Closed C13.1 actual services/native transactions. Synthetic policy/actors only."""

import argparse
import copy
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commercial.account_entitlements import AccountEntitlements, BindingProvisioner
from app.commercial.admin_access import VerifiedActor
from app.commercial.admission import AdmissionContext, ClosedAuthority, authority
from app.commercial.allowance_periods import allowance_period
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.usage_store import UsageReconciler, UsageStore
from test_catalog_store_native import MANAGER, ROOT, literal
from test_catalog_v2_native import (
    upgraded,  # noqa: F401 -- pytest fixture
)
from test_draft_api_native import create
from test_draft_service_native import (
    actor,
    database,  # noqa: F401 -- pytest fixture
    wait_blocked,
)
from test_lifecycle_api_native import (
    case,  # noqa: F401 -- pytest fixture
    install,  # noqa: F401 -- pytest fixture
)
from test_lifecycle_service_native import (
    install as f2_install,  # noqa: F401 -- pytest fixture
)
from test_pricing_native import (
    definition,
    pricing,  # noqa: F401 -- pytest fixture
    publish,
)
from test_review_service_native import (
    install as f1_install,  # noqa: F401 -- pytest fixture
)

POLICY = "synthetic.usage.v1"


def policy(action, document, snapshot):
    # Explicit test policy only, not a default production charging decision.
    if action == "reserve":
        return (
            document["policy_version"] == POLICY
            and document["operation"] == "synthetic.save"
        )
    return document.get("policy_version", POLICY) == POLICY


def failure(code, call):
    with pytest.raises(CatalogStoreError) as error:
        call()
    assert error.value.code == code
    assert str(error.value) == code.value


@pytest.fixture
def usage(pricing):  # noqa: F811 -- imported pytest fixture
    import psycopg

    db, client, app, _ = pricing
    if not db.rows("select 1 from pg_tables where tablename='usage_operations'"):
        db.run(
            "alter table auth.users add column created_at timestamptz not null default '2024-01-31T00:00:00+05:30'"
        )
        before = db.rows(
            "select canonical_json,fingerprint from catalog_offer_versions order by offer_version_id"
        )
        db.run(
            (
                ROOT / "supabase/migrations/20261023160000_account_usage_foundation.sql"
            ).read_text()
        )
        assert (
            db.rows(
                "select canonical_json,fingerprint from catalog_offer_versions order by offer_version_id"
            )
            == before
        )
        for role in ("usage_executor", "usage_binding_executor", "usage_reconciler"):
            db.run(
                "alter role " + role + " login"
            )  # Disposable provisioning, never shipped LOGIN.

    def connect(role="usage_executor", name="c131-worker"):
        return psycopg.connect(
            host="127.0.0.1",
            port=db.port,
            dbname="postgres",
            user=role,
            connect_timeout=5,
            application_name=name,
        )

    raw = definition("free")
    assert create(client, raw).status_code == 200
    result = publish(client, raw)
    offer = result["receipt"]["offer_version_id"]
    account = str(uuid4())
    db.run(f"insert into auth.users(id) values ({literal(account)})")
    now = datetime.now(timezone.utc)
    document = dict(
        binding_id=str(uuid4()),
        offer_version_id=offer,
        price_id=None,
        valid_from=(now - timedelta(days=1)).isoformat(),
        valid_until=(now + timedelta(days=1)).isoformat(),
        source_ref="synthetic.fixture",
        policy_version=POLICY,
    )
    provision = BindingProvisioner(lambda: connect("usage_binding_executor"))
    binding = provision.assign(account, document)
    store = UsageStore(connect, policy=policy)
    reconciler = UsageReconciler(lambda: connect("usage_reconciler"), policy=policy)
    return dict(
        db=db,
        client=client,
        account=account,
        actor=actor(account),
        connect=connect,
        provision=provision,
        binding=binding,
        document=document,
        store=store,
        reconciler=reconciler,
        raw=raw,
    )


def context(u, key=None, semantics="a" * 64):
    return AdmissionContext(
        u["account"],
        u.setdefault("resource", str(uuid4())),
        key or str(uuid4()),
        semantics,
        0,
        False,
        operation="synthetic.save",
    )


def reserve(u, ctx=None, units=1, meter="clipboard.new_saves", store=None):
    return (store or u["store"]).reserve(
        u["actor"],
        ctx or context(u),
        meter=meter,
        units=units,
        policy_version=POLICY,
        lease_seconds=30,
    )


def step(u, o, action, **extra):
    return u["store"].transition(
        u["actor"],
        action,
        o["operation_id"],
        fence=o["fence"],
        claim_token=o["claim_token"],
        **extra,
    )


def completed(u, o, charge=1):
    dispatched = step(u, o, "dispatch")
    assert dispatched["execution_permitted"] is True
    assert step(u, dispatched, "dispatch")["execution_permitted"] is False
    checkpoint = step(u, o, "checkpoint", result_ref=str(uuid4()))
    return step(u, checkpoint, "settle", charged=charge, policy_version=POLICY)


def counts(u):
    return u["db"].rows(
        "select (select count(*) from usage_operations) as operations,"
        "(select count(*) from usage_events) as events,(select count(*) from usage_periods) as periods"
    )[0]


def test_binding_exact_terms_and_no_self_assignment(usage):
    u = usage
    resolved = u["store"].resolve(u["actor"])
    assert resolved["binding"]["offer_version_id"] == u["document"]["offer_version_id"]
    assert resolved["snapshot"].terms.pricing_mode == "free"
    assert u["provision"].assign(u["account"], u["document"]) == u["binding"]
    changed = {**u["document"], "binding_id": str(uuid4())}
    failure(ErrorCode.CONFLICT, lambda: u["provision"].assign(u["account"], changed))
    failure(
        ErrorCode.INVALID,
        lambda: u["provision"].assign(
            u["account"], {**changed, "signup_at": "2025-01-01"}
        ),
    )
    failure(
        ErrorCode.DENIED,
        lambda: BindingProvisioner(u["connect"]).assign(u["account"], u["document"]),
    )
    db = u["db"]
    for role in ("anon", "authenticated", "service_role", "catalog_draft_executor"):
        for sql in [
            f"select public.usage_binding_call('{u['account']}','assign','{{}}')",
            f"select public.usage_call('{u['account']}','reserve','{{}}')",
            "update usage_periods set used=0",
            "delete from usage_events",
            "grant usage_executor to authenticated",
        ]:
            with pytest.raises(Exception):
                db.run("set session authorization " + role + ";" + sql)
    assert isinstance(authority, ClosedAuthority)


def test_finite_reserve_settle_release_replay(usage):
    u = usage
    ctx = context(u)
    first = reserve(u, ctx, 3)
    before = counts(u)
    assert reserve(u, ctx, 3) == first
    assert counts(u) == before
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: reserve(u, context(u, ctx.request_id, "b" * 64), 3),
    )
    second = reserve(u, units=2)
    failure(ErrorCode.EXHAUSTED, lambda: reserve(u))
    done = completed(u, first, 2)
    assert reserve(u, ctx, 3)["state"] == "settled"
    assert (
        u["store"].read(u["actor"], done["operation_id"])["result_ref"]
        == done["result_ref"]
    )
    before = counts(u)
    assert step(u, done, "settle", charged=2, policy_version=POLICY)["charged"] == 2
    assert counts(u) == before
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: step(u, done, "settle", charged=1, policy_version=POLICY),
    )
    released = step(u, second, "release", policy_version=POLICY)
    before = counts(u)
    assert step(u, released, "release", policy_version=POLICY)["state"] == "released"
    assert counts(u) == before
    assert u["reconciler"].audit(u["account"], first["period_id"]) == dict(
        consistent=True, used=2, reserved=0
    )


def test_concurrent_last_unit_and_duplicate_identity(usage):
    u = usage
    barrier = threading.Barrier(2)
    ctx = context(u)

    def same():
        barrier.wait(timeout=5)
        return reserve(u, ctx, 4)

    with ThreadPoolExecutor(2) as pool:
        a, b = [f.result(timeout=20) for f in [pool.submit(same), pool.submit(same)]]
    assert a["operation_id"] == b["operation_id"]
    assert (
        len(
            u["db"].rows(
                f"select * from usage_events where operation_id='{a['operation_id']}'"
            )
        )
        == 1
    )
    barrier = threading.Barrier(2)

    def last():
        barrier.wait(timeout=5)
        try:
            return reserve(u)["state"]
        except CatalogStoreError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = [f.result(timeout=20) for f in [pool.submit(last), pool.submit(last)]]
    assert sorted(map(str, results)) == sorted(
        map(str, ["reserved", ErrorCode.EXHAUSTED])
    )
    assert u["reconciler"].audit(u["account"], a["period_id"])["reserved"] == 5


def test_cross_account_forged_actor_revocation_and_binding_lock(usage):
    u = usage
    ctx = context(u)
    o = reserve(u, ctx)
    failure(
        ErrorCode.DENIED,
        lambda: reserve(
            {**u, "actor": VerifiedActor(MANAGER, u["actor"]._bearer)}, ctx
        ),
    )
    failure(ErrorCode.DENIED, lambda: reserve({**u, "actor": actor(MANAGER)}, ctx))
    # Revoke first, while retaining its row lock. A later independent worker
    # blocks on that exact row and must observe revocation after commit.
    conn = u["connect"]("usage_binding_executor", "c131-revoke")
    conn.execute(
        "select public.usage_binding_call(%s,%s,%s::jsonb)",
        (u["account"], "status", json.dumps(dict(expected_revision=1, active=False))),
    )
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(lambda: reserve(u, ctx))
        try:
            wait_blocked(u["db"], ["c131-worker"])
        finally:
            conn.commit()
            conn.close()
        with pytest.raises(CatalogStoreError) as error:
            future.result(timeout=15)
        assert error.value.code == ErrorCode.DENIED
    failure(ErrorCode.DENIED, lambda: u["store"].read(u["actor"], o["operation_id"]))
    u["provision"].status(u["account"], 2, active=True)
    # Other account has valid authority but cannot discover this operation.
    other = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ({literal(other)})")
    doc = {**u["document"], "binding_id": str(uuid4())}
    u["provision"].assign(other, doc)
    failure(
        ErrorCode.NOT_FOUND, lambda: u["store"].read(actor(other), o["operation_id"])
    )


def test_worker_first_revocation_waits_for_transaction(usage):
    u = usage
    conn = u["connect"]()
    conn.execute("select public.usage_account_read(%s)", (u["account"],))
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(
            lambda: BindingProvisioner(
                lambda: u["connect"]("usage_binding_executor", "c131-later-revoke")
            ).status(u["account"], 1, active=False)
        )
        try:
            wait_blocked(u["db"], ["c131-later-revoke"])
        finally:
            conn.commit()
            conn.close()
        assert future.result(timeout=15)["active"] is False
    failure(ErrorCode.DENIED, lambda: reserve(u))


def test_rollback_and_invalid_payload_zero_partial_writes(usage):
    u = usage
    before = counts(u)
    for units in (0, -1, True, 1.5, 2**63):
        failure(ErrorCode.INVALID, lambda: reserve(u, units=units))
    failure(ErrorCode.DENIED, lambda: reserve(u, meter="unknown.meter"))
    assert counts(u) == before
    # Maintenance-only fault injection after the balance/op mutation but before
    # its event insert. PostgreSQL must roll the whole command back.
    u["db"].run(
        "create function public.c131_fail() returns trigger language plpgsql as $$begin raise exception 'synthetic failure';end$$;create trigger c131_fail before insert on usage_events for each row execute function public.c131_fail()"
    )
    try:
        failure(ErrorCode.UNAVAILABLE, lambda: reserve(u))
    finally:
        u["db"].run(
            "drop trigger c131_fail on usage_events;drop function public.c131_fail()"
        )
    assert counts(u) == before


def test_crash_fencing_reconciliation_after_revocation(usage):
    u = usage
    o = reserve(u, units=3)
    step(u, o, "dispatch")
    failure(ErrorCode.CONFLICT, lambda: step(u, o, "release", policy_version=POLICY))
    u["db"].run(
        f"update usage_operations set lease_until=clock_timestamp()-interval '1 second' where operation_id='{o['operation_id']}'"
    )
    uncertain = u["reconciler"].recover(u["account"], o["operation_id"])
    assert uncertain["state"] == "uncertain" and uncertain["fence"] == 2
    before = counts(u)
    assert u["reconciler"].recover(u["account"], o["operation_id"]) == uncertain
    assert counts(u) == before
    failure(
        ErrorCode.CONFLICT, lambda: step(u, o, "checkpoint", result_ref=str(uuid4()))
    )
    u["provision"].status(u["account"], 1, active=False)
    result, evidence = str(uuid4()), str(uuid4())
    args = dict(
        fence=2, charged=0, result_ref=result, evidence=evidence, policy_version=POLICY
    )
    done = u["reconciler"].reconcile(u["account"], o["operation_id"], **args)
    assert done["charged"] == 0
    before = counts(u)
    assert u["reconciler"].reconcile(u["account"], o["operation_id"], **args) == done
    assert counts(u) == before
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: u["reconciler"].reconcile(
            u["account"], o["operation_id"], **{**args, "charged": 1}
        ),
    )
    assert u["reconciler"].audit(u["account"], o["period_id"])["reserved"] == 0


def test_settlement_race_one_event_and_dispatch_release_race(usage):
    u = usage
    o = reserve(u, units=2)
    step(u, o, "dispatch")
    o = step(u, o, "checkpoint", result_ref=str(uuid4()))
    barrier = threading.Barrier(2)

    def settle(charge):
        barrier.wait(timeout=5)
        try:
            return step(u, o, "settle", charged=charge, policy_version=POLICY)["state"]
        except CatalogStoreError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = [
            f.result(timeout=20)
            for f in [pool.submit(settle, 1), pool.submit(settle, 2)]
        ]
    assert (
        results.count("settled") == 1
        and results.count(ErrorCode.IDENTITY_CONFLICT) == 1
    )
    assert (
        u["db"].rows(
            f"select count(*) as n from usage_events where operation_id='{o['operation_id']}' and event='settle'"
        )[0]["n"]
        == 1
    )
    other = reserve(u)
    barrier = threading.Barrier(2)

    def race(action):
        barrier.wait(timeout=5)
        try:
            return step(
                u,
                other,
                action,
                **({"policy_version": POLICY} if action == "release" else {}),
            )["state"]
        except CatalogStoreError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = [
            f.result(timeout=20)
            for f in [pool.submit(race, "dispatch"), pool.submit(race, "release")]
        ]
    assert results.count(ErrorCode.CONFLICT) == 1
    assert u["reconciler"].audit(u["account"], o["period_id"])["consistent"]


def test_capacity_initial_upload_replacement_and_unlimited(usage):
    u = usage
    o = reserve(u, meter="resume.stored_files")
    failure(ErrorCode.EXHAUSTED, lambda: reserve(u, meter="resume.stored_files"))
    stored = completed(u, o)
    # Initial capacity does not consume the independent replacement quota.
    replacement = reserve(u, meter="resume.replacements")
    failure(ErrorCode.EXHAUSTED, lambda: reserve(u, meter="resume.replacements"))
    vacated = step(u, stored, "vacate", policy_version=POLICY)
    assert step(u, vacated, "vacate", policy_version=POLICY)["capacity_released"]
    assert reserve(u, meter="resume.stored_files")["state"] == "reserved"
    assert u["reconciler"].audit(u["account"], o["period_id"])["used"] == 0
    assert (
        u["reconciler"].audit(u["account"], replacement["period_id"])["reserved"] == 1
    )
    unmetered = reserve(u, meter="answers.completed", units=10**9)
    assert unmetered["requested"] == 10**9


def test_periods_match_python_leap_anchor_and_historical_replay(usage):
    u = usage
    db = u["db"]
    for year in (2024, 2025):
        for day in (29, 30, 31):
            signup = datetime.fromisoformat(f"{year}-01-{day}T00:00:00+05:30")
            for now in (
                datetime.fromisoformat(f"{year}-02-28T00:00:00+05:30"),
                datetime.fromisoformat(f"{year}-03-31T00:00:00+05:30"),
            ):
                for cadence in ("day", "month"):
                    expected = allowance_period(now, signup, cadence)
                    row = db.rows(
                        "select public.usage_period_bounds("
                        + literal(now.isoformat())
                        + ","
                        + literal(signup.isoformat())
                        + ","
                        + literal(cadence)
                        + ") as bounds"
                    )[0]
                    assert (
                        tuple(datetime.fromisoformat(s) for s in row["bounds"])
                        == expected
                    )
    reserve(u, meter="auto.authorized_running", units=300)
    reserve(u, meter="auto.authorized_running", units=300)
    ctx = context(u)
    old = reserve(u, ctx, meter="clipboard.new_saves")
    db.run(
        f"update usage_periods set starts_at=starts_at-interval '1 month',ends_at=ends_at-interval '1 month' where period_id='{old['period_id']}'"
    )
    assert (
        reserve(u, ctx, meter="clipboard.new_saves")["operation_id"]
        == old["operation_id"]
    )
    fresh = reserve(u, meter="clipboard.new_saves")
    assert fresh["period_id"] != old["period_id"]
    failure(ErrorCode.EXHAUSTED, lambda: reserve(u, meter="auto.authorized_running"))


def test_corrupt_terms_safe_and_no_caller_allowance_override(usage):
    u = usage
    offer = u["document"]["offer_version_id"]
    before = counts(u)
    original = u["db"].rows(
        f"select canonical_json,fingerprint from catalog_offer_versions where offer_version_id='{offer}'"
    )[0]
    raw = json.loads(original["canonical_json"])
    raw["contract_version"] = "catalog.unsupported"
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    u["db"].run(
        "alter table catalog_offer_versions disable trigger user;update catalog_offer_versions set canonical_json="
        + literal(encoded)
        + ",fingerprint="
        + literal(hashlib.sha256(encoded.encode()).hexdigest())
        + f" where offer_version_id='{offer}';alter table catalog_offer_versions enable trigger user;"
    )
    failure(ErrorCode.STORED_INVALID, lambda: reserve(u))
    assert counts(u) == before
    u["db"].run(
        "alter table catalog_offer_versions disable trigger user;update catalog_offer_versions set canonical_json="
        + literal(original["canonical_json"])
        + ",fingerprint="
        + literal(original["fingerprint"])
        + f" where offer_version_id='{offer}';alter table catalog_offer_versions enable trigger user;"
    )
    conn = u["connect"]()
    try:
        with pytest.raises(Exception):
            conn.execute(
                "select public.usage_call(%s,%s,%s::jsonb)",
                (u["account"], "reserve", json.dumps(dict(allowance=999))),
            )
    finally:
        conn.rollback()
        conn.close()
    assert counts(u) == before


def test_lost_commit_recovery_and_closed_construction(usage):
    u = usage

    class LostCommit:
        def __init__(self):
            self.conn = u["connect"]()

        def __getattr__(self, key):
            return getattr(self.conn, key)

        def commit(self):
            self.conn.commit()
            raise OSError("synthetic response lost")

    broken = UsageStore(LostCommit, policy=policy)
    ctx = context(u)
    failure(ErrorCode.UNCERTAIN, lambda: reserve(u, ctx, store=broken))
    before = counts(u)
    o = reserve(u, ctx)
    assert counts(u) == before and o["state"] == "reserved"
    completed(u, o)
    assert reserve(u, ctx)["state"] == "settled"
    recovery = AdmissionContext(
        u["account"],
        ctx.session_id,
        ctx.request_id,
        ctx.semantics_hash,
        0,
        True,
        operation=ctx.operation,
    )
    failure(ErrorCode.INVALID, lambda: reserve(u, recovery))
    failure(ErrorCode.UNAVAILABLE, lambda: reserve(u, store=UsageStore(u["connect"])))

    def forbidden():
        raise AssertionError("Construction must not connect")

    UsageStore(forbidden)
    AccountEntitlements(forbidden)
    BindingProvisioner(forbidden)
    UsageReconciler(forbidden)
    failure(
        ErrorCode.UNAVAILABLE,
        lambda: UsageStore(policy=policy).read(u["actor"], o["operation_id"]),
    )

    def unavailable():
        raise OSError("synthetic private connection detail")

    failure(
        ErrorCode.UNAVAILABLE,
        lambda: UsageStore(unavailable, policy=policy).read(
            u["actor"], o["operation_id"]
        ),
    )


def test_uncertain_release_and_audited_aggregate_repair(usage):
    u = usage
    o = reserve(u, units=2)
    step(u, o, "dispatch")
    pending = step(u, o, "uncertain")
    evidence = str(uuid4())
    kwargs = dict(fence=pending["fence"], evidence=evidence, policy_version=POLICY)
    released = u["reconciler"].release_uncertain(
        u["account"], o["operation_id"], **kwargs
    )
    assert released["state"] == "released" and released["charged"] is None
    before = counts(u)
    assert (
        u["reconciler"].release_uncertain(u["account"], o["operation_id"], **kwargs)
        == released
    )
    assert counts(u) == before
    assert u["reconciler"].audit(u["account"], o["period_id"])["reserved"] == 0
    # Owner-only aggregate drift injection; ordinary application roles cannot do this.
    u["db"].run(f"update usage_periods set used=1 where period_id='{o['period_id']}'")
    failure(
        ErrorCode.INVALID, lambda: u["reconciler"].audit(u["account"], o["period_id"])
    )
    fixed = u["reconciler"].rebuild(u["account"], o["period_id"])
    assert fixed == dict(consistent=True, repaired=True, used=0, reserved=0)
    before = counts(u)
    assert u["reconciler"].rebuild(u["account"], o["period_id"])["consistent"]
    assert counts(u) == before


def test_zero_missing_denied_and_approved_paid_bindings(usage):
    u = usage
    for code in ("plus", "pro"):
        raw = definition(code)
        assert create(u["client"], raw).status_code == 200
        offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
        account = str(uuid4())
        u["db"].run(f"insert into auth.users(id) values ('{account}')")
        doc = {
            **u["document"],
            "binding_id": str(uuid4()),
            "offer_version_id": offer,
            "price_id": next(
                p["price_id"]
                for p in raw["terms"]["prices"]
                if p["billing"]["unit"] == "year"
            ),
        }
        wrong = {**doc, "price_id": str(uuid4())}
        failure(ErrorCode.INVALID, lambda: u["provision"].assign(account, wrong))
        u["provision"].assign(account, doc)
        paid = {
            **u,
            "account": account,
            "actor": actor(account),
            "resource": str(uuid4()),
        }
        allowance = 10 if code == "plus" else 100000
        o = reserve(paid, units=allowance)
        period = u["db"].rows(
            f"select starts_at,ends_at from usage_periods where period_id='{o['period_id']}'"
        )[0]
        if code == "plus":
            assert datetime.fromisoformat(period["ends_at"]) - datetime.fromisoformat(
                period["starts_at"]
            ) <= timedelta(days=31)
        else:
            # Pro has explicit unlimited usage with no reset, not an annual pool.
            assert period["ends_at"] == "infinity"
        if code == "plus":
            failure(ErrorCode.EXHAUSTED, lambda: reserve(paid))
        else:
            assert reserve(paid)["state"] == "reserved"
        snapshot = u["store"].resolve(actor(account))["snapshot"]
        assert sorted(p.amount_minor for p in snapshot.terms.prices) == (
            [39900, 299900] if code == "plus" else [89900, 649900]
        )
        assert u["reconciler"].audit(account, o["period_id"])[
            "reserved"
        ] == allowance + (1 if code == "pro" else 0)
    # A zero allowance is representable and denies work; absence is not unlimited.
    raw = definition("free")
    next(a for a in raw["terms"]["allowances"] if a["meter"] == "clipboard.new_saves")[
        "amount"
    ] = "0"
    assert create(u["client"], raw).status_code == 200
    offer = publish(u["client"], raw)["receipt"]["offer_version_id"]
    account = str(uuid4())
    u["db"].run(f"insert into auth.users(id) values ('{account}')")
    u["provision"].assign(
        account,
        {**u["document"], "binding_id": str(uuid4()), "offer_version_id": offer},
    )
    zero = {**u, "account": account, "actor": actor(account), "resource": str(uuid4())}
    before = counts(u)
    failure(ErrorCode.EXHAUSTED, lambda: reserve(zero))
    failure(ErrorCode.DENIED, lambda: reserve(zero, meter="not.registered"))
    assert counts(u) == before
    failure(ErrorCode.DENIED, lambda: u["store"].resolve(actor(str(uuid4()))))


def test_expiry_stale_claim_policy_failure_and_terminal_immutability(usage):
    u = usage
    o = reserve(u)
    failure(
        ErrorCode.DENIED, lambda: step(u, o, "release", policy_version="wrong.policy")
    )
    before = counts(u)
    failing = UsageStore(
        u["connect"],
        policy=lambda *args: (_ for _ in ()).throw(RuntimeError("private detail")),
    )
    failure(ErrorCode.UNAVAILABLE, lambda: reserve(u, store=failing))
    assert counts(u) == before
    bad = AdmissionContext(
        u["account"],
        context(u).session_id,
        None,
        "a" * 64,
        0,
        False,
        operation="synthetic.save",
    )
    failure(ErrorCode.INVALID, lambda: reserve(u, bad))
    # Expiry removes access to new work and saved/replayed results alike.
    u["db"].run(
        f"update account_plan_bindings set valid_until=clock_timestamp()-interval '1 second' where account_id='{u['account']}'"
    )
    failure(ErrorCode.DENIED, lambda: u["store"].read(u["actor"], o["operation_id"]))
    failure(ErrorCode.DENIED, lambda: reserve(u))
    u["db"].run(
        f"update usage_operations set lease_until=clock_timestamp()-interval '1 second' where operation_id='{o['operation_id']}'"
    )
    pending = u["reconciler"].recover(u["account"], o["operation_id"])
    assert pending["state"] == "uncertain"
    u["reconciler"].release_uncertain(
        u["account"],
        o["operation_id"],
        fence=pending["fence"],
        evidence=str(uuid4()),
        policy_version=POLICY,
    )
    for table in ("catalog_offer_versions", "catalog_price_versions", "usage_events"):
        with pytest.raises(Exception):
            u["db"].run("set session authorization usage_executor;delete from " + table)


def test_bound_history_survives_offer_replacement_and_retirement(usage):
    from test_lifecycle_api_native import write_headers

    u = usage
    accepted = u["store"].resolve(u["actor"])["snapshot"]
    successor = copy.deepcopy(u["raw"])
    successor["draft_id"] = str(uuid4())
    successor["terms"]["name"] = "Synthetic successor"
    next(
        a
        for a in successor["terms"]["allowances"]
        if a["meter"] == "clipboard.new_saves"
    )["amount"] = "6"
    assert create(u["client"], successor).status_code == 200
    replaced = publish(u["client"], successor, "replace")
    assert (
        u["store"].resolve(u["actor"])["snapshot"].fingerprint == accepted.fingerprint
    )
    current = replaced["receipt"]["offer_version_id"]
    retired = u["client"].post(
        "/api/admin/catalog/offers/" + current + "/retire",
        json={"reason": "Synthetic bound history verification"},
        headers=write_headers(revision=replaced["current"]["revision"]),
    )
    assert retired.status_code == 200
    assert (
        u["store"].resolve(u["actor"])["snapshot"].canonical_json()
        == accepted.canonical_json()
    )
    reserve(u, units=5)
    failure(ErrorCode.EXHAUSTED, lambda: reserve(u))


def test_checkpoint_save_only_recovery_and_settlement_rollback(usage):
    u = usage
    o = reserve(u)
    step(u, o, "dispatch")
    result = str(uuid4())
    checkpoint = step(u, o, "checkpoint", result_ref=result)
    read = u["store"].read(u["actor"], o["operation_id"])
    assert read["result_ref"] == result and read["execution_permitted"] is False
    before = counts(u)
    u["db"].run(
        "create function public.c131_fail_settle() returns trigger language plpgsql as $$begin if new.event='settle' then raise exception 'synthetic failure';end if;return new;end$$;create trigger c131_fail_settle before insert on usage_events for each row execute function public.c131_fail_settle()"
    )
    try:
        failure(
            ErrorCode.UNAVAILABLE,
            lambda: step(u, checkpoint, "settle", charged=1, policy_version=POLICY),
        )
    finally:
        u["db"].run(
            "drop trigger c131_fail_settle on usage_events;drop function public.c131_fail_settle()"
        )
    assert counts(u) == before
    assert u["store"].read(u["actor"], o["operation_id"])["state"] == "checkpointed"
    assert u["reconciler"].audit(u["account"], o["period_id"])["reserved"] == 1
    u["db"].run(
        f"update usage_operations set lease_until=clock_timestamp()-interval '1 second' where operation_id='{o['operation_id']}'"
    )
    recovered = u["reconciler"].recover(u["account"], o["operation_id"])
    args = dict(
        fence=recovered["fence"],
        charged=1,
        result_ref=result,
        evidence=str(uuid4()),
        policy_version=POLICY,
    )
    failure(
        ErrorCode.IDENTITY_CONFLICT,
        lambda: u["reconciler"].reconcile(
            u["account"], o["operation_id"], **{**args, "result_ref": str(uuid4())}
        ),
    )
    done = u["reconciler"].reconcile(u["account"], o["operation_id"], **args)
    assert done["result_ref"] == result and done["execution_permitted"] is False


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
