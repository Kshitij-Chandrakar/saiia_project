"""Closed nonfinancial usage retirement in fresh disposable synthetic DBs."""

# ruff: noqa: F401,F811
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from app.privacy_retirement import RetirementCandidateWorker
from test_privacy_retirement_candidate_native import (
    ROOT,
    accept,
    candidate,
    case,
    content,
    database,
    erase,
    f1_install,
    f2_install,
    install,
    integration,
    owned_temporary_journals,
    pricing,
    privacy,
    remaining,
    restricted,
    seed,
    start,
    stop,
    upgraded,
    usage,
)


@pytest.fixture
def candidate(remaining):
    _u, e, *_ = remaining
    _, run = start(remaining)
    stop(remaining, run)
    with e.connect() as c:
        if (
            c.execute(
                "select to_regclass('public.privacy_auto_reply_payloads')"
            ).fetchone()[0]
            is None
        ):
            for migration in [
                "20261031100000_privacy_retirement_preparation.sql",
                "20261031120000_privacy_auto_credentials.sql",
            ]:
                c.execute(
                    (ROOT / "supabase/migrations" / migration).read_text(
                        encoding="utf8"
                    )
                )
            c.execute(
                "alter role privacy_cleanup_executor login;alter role privacy_preparation_executor login"
            )
    return remaining


@pytest.mark.parametrize("financial", [False, True])
def test_dependency_closed_usage_retirement(candidate, financial):
    u, e, _storage, *_ = candidate
    account = u["account"]
    other = str(uuid4())
    with e.connect() as c:
        if (
            c.execute(
                "select to_regclass('public.privacy_usage_retirements')"
            ).fetchone()[0]
            is None
        ):
            c.execute(
                (ROOT / "docs/sql/C15_LEGACY_REPLY_RETIREMENT_CANDIDATE.sql").read_text(
                    encoding="utf8"
                )
            )
            c.execute(
                (ROOT / "docs/sql/C15_USAGE_RETIREMENT_CANDIDATE.sql").read_text(
                    encoding="utf8"
                )
            )
        c.execute("alter role privacy_retirement_executor login")
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
        c.execute(
            "insert into account_plan_bindings select %s,%s,offer_version_id,price_id,signup_at,valid_from,valid_until,source_ref,policy_version,revision,active from account_plan_bindings where account_id=%s",
            (other, str(uuid4()), account),
        )
        before_other = c.execute(
            "select sha256(convert_to(to_jsonb(b)::text,'UTF8')) from account_plan_bindings b where account_id=%s",
            (other,),
        ).fetchone()[0]
    if financial:
        with e.connect() as c:
            c.execute(
                "insert into subscription_payment_receipts select %s,account_id,repeat('a',64),to_jsonb(b),clock_timestamp() from account_plan_bindings b where account_id=%s",
                (str(uuid4()), account),
            )
    accept(candidate, days=91)
    assert e.queue_accepted()
    job = e.claim()
    assert job
    e.credential_connect = lambda: restricted(candidate, "privacy_cleanup_executor")
    e.cleanup(job)
    with e.connect() as c:
        state, blockers = c.execute(
            "select state,blockers from privacy_content_jobs where id=%s", (job["id"],)
        ).fetchone()
        assert state == "primary_verified", blockers
    with restricted(candidate, "privacy_preparation_executor") as c:
        assert (
            c.execute(
                "select privacy_prepare_usage_retirement(%s)", (account,)
            ).fetchone()[0]["state"]
            == "prepared"
        )

    def retire(revision=1):
        return RetirementCandidateWorker(
            lambda: restricted(candidate, "privacy_retirement_executor"),
            local_candidate=True,
        ).retire_usage(account, revision)

    with pytest.raises(psycopg.Error):
        retire()  # defaults disabled
    for role in [
        "usage_executor",
        "privacy_cleanup_executor",
        "privacy_preparation_executor",
        "privacy_retirement_executor",
    ]:
        for query in [
            "delete from usage_events",
            "update subscription_binding_history set document='{}'",
            "truncate usage_events",
            "select * from privacy_usage_retirement_permits",
            "set role privacy_retirement_owner",
        ]:
            with pytest.raises(psycopg.Error), restricted(candidate, role) as c:
                c.execute(query)
    with e.connect() as c:
        c.execute(
            "update privacy_usage_retirements set enabled=true where account_id=%s",
            (account,),
        )
        assert (
            c.execute(
                "select sum(used) from usage_periods where account_id=%s", (account,)
            ).fetchone()[0]
            is not None
        )
    with e.connect() as c:
        c.execute("update privacy_retirement_configuration set enabled=true")
        request = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (account,),
        ).fetchone()[0]
    with restricted(candidate, "privacy_preparation_executor") as c:
        unit = c.execute(
            "select privacy_retirement_prepare(%s,%s,'usage_recovery')",
            (account, request),
        ).fetchone()[0]
        assert (
            c.execute(
                "select privacy_retirement_hold(%s,1,'security',clock_timestamp()+interval '1 day',true)",
                (unit,),
            ).fetchone()[0]
            == 2
        )
    with pytest.raises(psycopg.Error):
        retire()
    with restricted(candidate, "privacy_preparation_executor") as c:
        assert (
            c.execute(
                "select privacy_retirement_hold(%s,2,'security',clock_timestamp()+interval '1 day',false)",
                (unit,),
            ).fetchone()[0]
            == 3
        )
    with e.connect() as c:
        c.execute("alter table usage_operations add column synthetic_unclassified text")
    with pytest.raises(psycopg.Error):
        retire()
    with e.connect() as c:
        c.execute("alter table usage_operations drop column synthetic_unclassified")
    with pytest.raises(psycopg.Error):
        retire(2)
    with e.connect() as c:
        c.execute(
            "update privacy_usage_retirements set eligible_at=clock_timestamp()+interval '1 day' where account_id=%s",
            (account,),
        )
    with pytest.raises(psycopg.Error):
        retire()
    with e.connect() as c:
        c.execute(
            "update privacy_usage_retirements set eligible_at=accepted_at+interval '90 days' where account_id=%s",
            (account,),
        )
        op = c.execute(
            "select operation_id from usage_operations where account_id=%s limit 1",
            (account,),
        ).fetchone()[0]
        c.execute(
            "create table synthetic_retirement_dependency(operation_id uuid references usage_operations on delete restrict)"
        )
        c.execute("insert into synthetic_retirement_dependency values(%s)", (op,))
    with pytest.raises(psycopg.Error):
        retire()  # no RESTRICT/cascade bypass
    with e.connect() as c:
        assert (
            c.execute(
                "select count(*) from usage_events where account_id=%s", (account,)
            ).fetchone()[0]
            > 0
        )
        c.execute("drop table synthetic_retirement_dependency")
    with (
        pytest.raises(RuntimeError),
        restricted(candidate, "privacy_retirement_executor") as c,
    ):
        c.execute("select privacy_retire_usage(%s,1)", (account,))
        raise RuntimeError("synthetic_precommit_crash")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: retire(), range(2)))
    assert sorted(x["state"] for x in results) == ["already_retired", "retired"]
    assert retire()["state"] == "already_retired"
    if financial:
        with e.connect() as c:
            assert (
                c.execute(
                    "select count(*) from subscription_payment_receipts where account_id=%s",
                    (account,),
                ).fetchone()[0]
                == 1
            )
    with e.connect() as c:
        assert (
            c.execute(
                "select count(*) from usage_events where account_id=%s", (account,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from usage_operations where account_id=%s", (account,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from usage_periods where account_id=%s", (account,)
            ).fetchone()[0]
            == 0
        )
        assert c.execute(
            "select count(*) from account_plan_bindings where account_id=%s", (account,)
        ).fetchone()[0] == int(financial)
        assert (
            c.execute(
                "select count(*) from subscription_binding_history where account_id=%s",
                (account,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from subscription_auto_runs where account_id=%s",
                (account,),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select sha256(convert_to(to_jsonb(b)::text,'UTF8')) from account_plan_bindings b where account_id=%s",
                (other,),
            ).fetchone()[0]
            == before_other
        )
        assert (
            c.execute(
                "select count(*) from privacy_usage_retirement_permits"
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(psycopg.Error), restricted(candidate, "usage_executor") as c:
        c.execute("select subscription_current(%s,true)", (account,))
