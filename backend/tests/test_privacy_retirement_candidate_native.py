"""Candidate retirement, disposable synthetic data only; no normal loader."""

# ruff: noqa: F401,F811 -- imported native fixture dependencies
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from app.privacy_content import ContentBlocked
from test_privacy_completion_native import (
    ROOT,
    accept,
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
from test_privacy_preparation_native import prepare


@pytest.fixture
def candidate(remaining):
    _u, e, *_ = remaining
    # Create synthetic legacy bytes through the original writer before installing
    # the forward format. This fixture intentionally tests retirement rather than
    # borrowing the earlier stage's unchanged-legacy teardown invariant.
    _, legacy = start(remaining)
    stop(remaining, legacy)
    with e.connect() as c:
        for name in (
            "20261031100000_privacy_retirement_preparation.sql",
            "20261031120000_privacy_auto_credentials.sql",
        ):
            c.execute((ROOT / "supabase/migrations" / name).read_text(encoding="utf8"))
        c.execute(
            "alter role privacy_cleanup_executor login;alter role privacy_preparation_executor login"
        )
    e.credential_connect = lambda: restricted(remaining, "privacy_cleanup_executor")
    yield remaining
    e.credential_connect = None


def test_candidate_restricted_atomic_retirement_and_replay(candidate):
    complete = candidate
    u, e, *_ = complete
    unit = prepare(complete, days=91)
    redaction_job = erase(complete)
    with e.connect() as c:
        c.execute(
            (ROOT / "docs/sql/C15_LEGACY_REPLY_RETIREMENT_CANDIDATE.sql").read_text(
                encoding="utf8"
            )
        )
        c.execute("alter role privacy_retirement_executor login")
        legacy = c.execute(
            "select r.run_id,count(a.*) from subscription_auto_runs r join subscription_auto_replies a using(run_id) where r.account_id=%s and not r.active group by r.run_id",
            (u["account"],),
        ).fetchone()
        assert legacy and legacy[1] > 0
        run, count = legacy
        c.execute(
            "insert into privacy_legacy_reply_retirements(run_id,account_id,request_id,accepted_at,eligible_at,expected_count) select %s,account_id,request_id,accepted_at,accepted_at+interval '90 days',%s from privacy_deletion_requests where account_id=%s",
            (run, count, u["account"]),
        )
        from app.privacy_schema import validate_schema

        validate_schema(c.cursor(), require_full=False)
        before = c.execute(
            "select sum(used),sum(reserved) from usage_periods"
        ).fetchone()

    with e.connect() as c:
        accepted = c.execute(
            "select accepted_at from privacy_deletion_requests where account_id=%s",
            (u["account"],),
        ).fetchone()[0]
        c.execute(
            "update privacy_deletion_requests set accepted_at=clock_timestamp() where account_id=%s",
            (u["account"],),
        )
        accounting_projection = c.execute(
            "select run_id,sequence,action,request_fence,document-'owner_token' from subscription_auto_replies order by run_id,sequence"
        ).fetchall()

    def redact():
        with restricted(complete, "privacy_cleanup_executor") as c:
            return c.execute(
                "select privacy_redact_legacy_auto(%s,%s)",
                (redaction_job["id"], redaction_job["lease"]),
            ).fetchone()[0]

    # A pre-commit crash leaves credential removal and its attestation atomic.
    with (
        pytest.raises(RuntimeError),
        restricted(complete, "privacy_cleanup_executor") as c,
    ):
        assert (
            c.execute(
                "select privacy_redact_legacy_auto(%s,%s)",
                (redaction_job["id"], redaction_job["lease"]),
            ).fetchone()[0]
            > 0
        )
        raise RuntimeError("synthetic_redaction_crash_before_commit")
    with ThreadPoolExecutor(max_workers=2) as pool:
        redacted = list(pool.map(lambda _: redact(), range(2)))
    assert sorted(redacted) == [0, 1]
    assert redact() == 0
    with (
        pytest.raises(psycopg.Error),
        restricted(complete, "privacy_cleanup_executor") as c,
    ):
        c.execute(
            "select privacy_redact_legacy_auto(%s,%s)",
            (redaction_job["id"], str(uuid4())),
        )
    with e.connect() as c:
        after_projection = c.execute(
            "select run_id,sequence,action,request_fence,document-'owner_token' from subscription_auto_replies order by run_id,sequence"
        ).fetchall()
        facts_unchanged = accounting_projection == after_projection
        assert facts_unchanged
        assert (
            c.execute(
                "select count(*) from subscription_auto_replies a join subscription_auto_runs r using(run_id) where r.account_id=%s and a.document ? 'owner_token'",
                (u["account"],),
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from privacy_legacy_redaction_permits"
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute(
                "select count(*) from privacy_legacy_redaction_attestations"
            ).fetchone()[0]
            == 1
        )
        c.execute(
            "update privacy_deletion_requests set accepted_at=%s where account_id=%s",
            (accepted, u["account"]),
        )
    # There is no general JSON edit even for the database fixture owner.
    with pytest.raises(psycopg.Error), e.connect() as c:
        c.execute(
            "update subscription_auto_replies set document=jsonb_set(document,'{fence}','999') where run_id=%s",
            (run,),
        )

    def execute():
        with restricted(complete, "privacy_retirement_executor") as c:
            return c.execute(
                "select privacy_retire_legacy_replies(%s,1)", (run,)
            ).fetchone()[0]

    with pytest.raises(psycopg.Error):
        execute()  # Candidate defaults unavailable, even to intended executor.
    for role in [
        "usage_executor",
        "privacy_cleanup_executor",
        "privacy_preparation_executor",
        "privacy_retirement_executor",
    ]:
        for statement in [
            "select * from privacy_retirement_permits",
            "delete from subscription_auto_replies",
            "update subscription_auto_replies set document='{}'",
            "truncate subscription_auto_replies",
        ]:
            with pytest.raises(psycopg.Error), restricted(complete, role) as c:
                c.execute(statement)
    with e.connect() as c:
        c.execute(
            "update privacy_legacy_reply_retirements set enabled=true,eligible_at=clock_timestamp()+interval '1 day' where run_id=%s",
            (run,),
        )
    with pytest.raises(psycopg.Error):
        execute()  # Wrong clock/future clock cannot be operator-approved away.
    with e.connect() as c:
        c.execute(
            "update privacy_legacy_reply_retirements set eligible_at=accepted_at+interval '90 days' where run_id=%s",
            (run,),
        )
        c.execute(
            "update privacy_legacy_reply_retirements set expected_count=expected_count+1 where run_id=%s",
            (run,),
        )
    with pytest.raises(psycopg.Error):
        execute()
    with e.connect() as c:
        c.execute(
            "update privacy_legacy_reply_retirements set expected_count=expected_count-1 where run_id=%s",
            (run,),
        )
        # Existing shared/global catalog remains outside candidate authority.
        catalog_before = c.execute(
            "select sha256(convert_to(jsonb_agg(to_jsonb(p) order by plan_id)::text,'UTF8')) from catalog_plans p"
        ).fetchone()[0]
    with restricted(complete, "privacy_retirement_executor") as c:
        identity = c.execute(
            "select rolsuper,rolbypassrls,rolinherit from pg_roles where rolname=current_user"
        ).fetchone()
        assert identity == (False, False, False)
        with pytest.raises(psycopg.Error):
            c.execute("set role privacy_retirement_owner")
    with e.connect() as c:
        c.execute(
            "insert into privacy_retirement_holds(unit_id,reason,review_at,active,revision) values(%s,'security',clock_timestamp()+interval '1 day',true,1)",
            (unit,),
        )
    with pytest.raises(psycopg.Error):
        execute()
    with e.connect() as c:
        c.execute(
            "update privacy_retirement_holds set active=false where unit_id=%s", (unit,)
        )
    # A worker death before DB commit retires nothing, including its attestation.
    with (
        pytest.raises(RuntimeError),
        restricted(complete, "privacy_retirement_executor") as c,
    ):
        assert (
            c.execute("select privacy_retire_legacy_replies(%s,1)", (run,)).fetchone()[
                0
            ]
            == count
        )
        raise RuntimeError("synthetic_worker_crash_before_commit")
    with e.connect() as c:
        assert (
            c.execute(
                "select count(*) from subscription_auto_replies where run_id=%s", (run,)
            ).fetchone()[0]
            == count
        )
        assert (
            c.execute("select count(*) from privacy_retirement_permits").fetchone()[0]
            == 0
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(), range(2)))
    assert sorted(results) == [0, count]
    assert execute() == 0
    from app.privacy_retirement import RetirementCandidateWorker

    worker = RetirementCandidateWorker(
        lambda: restricted(complete, "privacy_retirement_executor"),
        local_candidate=True,
    )
    assert worker.retire_replies(run, 1) == {
        "state": "already_retired",
        "removed": 0,
        "full_account_erasure": False,
    }
    with pytest.raises(ContentBlocked):
        RetirementCandidateWorker(
            lambda: restricted(complete, "privacy_retirement_executor")
        )

    with e.connect() as c:
        assert (
            c.execute(
                "select count(*) from subscription_auto_replies where run_id=%s", (run,)
            ).fetchone()[0]
            == 0
        )
        assert (
            c.execute("select count(*) from privacy_retirement_permits").fetchone()[0]
            == 0
        )
        assert (
            c.execute("select sum(used),sum(reserved) from usage_periods").fetchone()
            == before
        )
        assert (
            c.execute(
                "select sha256(convert_to(jsonb_agg(to_jsonb(p) order by plan_id)::text,'UTF8')) from catalog_plans p"
            ).fetchone()[0]
            == catalog_before
        )
        assert (
            c.execute(
                "select count from privacy_legacy_retirement_attestations"
            ).fetchone()[0]
            == count
        )
        assert (
            c.execute("select count(*) from privacy_email_suppression").fetchone()[0]
            > 0
        )

    # A distinct security unit uses 180 days, never the usage deadline.
    with e.connect() as c:
        request = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (u["account"],),
        ).fetchone()[0]
        c.execute(
            "update privacy_followup_tasks set state='blocked',lease_id=null,lease_until=null where request_id=%s",
            (request,),
        )
    with restricted(complete, "privacy_preparation_executor") as c:
        security_count = c.execute(
            "select privacy_prepare_legacy_security(%s)", (request,)
        ).fetchone()[0]
    assert security_count > 0
    with e.connect() as c:
        c.execute(
            "update privacy_legacy_audit_retirements set enabled=true where request_id=%s",
            (request,),
        )
    with (
        pytest.raises(psycopg.Error),
        restricted(complete, "privacy_retirement_executor") as c,
    ):
        c.execute("select privacy_retire_legacy_security(%s,1)", (request,))
    with e.connect() as c:
        c.execute(
            "update privacy_deletion_requests set accepted_at=clock_timestamp()-interval '181 days' where request_id=%s",
            (request,),
        )
        c.execute(
            "update privacy_legacy_audit_retirements set accepted_at=r.accepted_at,eligible_at=r.accepted_at+interval '180 days' from privacy_deletion_requests r where privacy_legacy_audit_retirements.request_id=r.request_id and r.request_id=%s",
            (request,),
        )
    with restricted(complete, "privacy_retirement_executor") as c:
        assert (
            c.execute(
                "select privacy_retire_legacy_security(%s,1)", (request,)
            ).fetchone()[0]
            == security_count
        )
    with restricted(complete, "privacy_retirement_executor") as c:
        assert (
            c.execute(
                "select privacy_retire_legacy_security(%s,1)", (request,)
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(psycopg.Error), e.connect() as c:
        c.execute(
            "insert into privacy_lifecycle_audit(request_id,action) values(%s,'deletion.challenge')",
            (request,),
        )
    with e.connect() as c:
        # Restoration does not recreate an already-retired same-clock audit copy.
        assert (
            c.execute(
                "insert into privacy_lifecycle_audit(request_id,action) values(%s,'restore.restriction_replayed')",
                (request,),
            ).rowcount
            == 0
        )
        assert (
            c.execute(
                "select count(*) from privacy_security_retirement_permits"
            ).fetchone()[0]
            == 0
        )
