"""Restricted connections and forward credential minimization; no real services."""

# ruff: noqa: F401,F811 -- imported native fixtures
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from app.commercial.catalog_store import CatalogStoreError
from app.commercial.executor_connection import check_executor_identity
from app.privacy_content import ContentBlocked
from app.privacy_schema import MANIFEST, candidate_manifest, validate_schema
from test_privacy_preparation_native import (
    Storage,
    accept,
    case,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    owned_temporary_journals,
    prepare,
    prepared,
    pricing,
    privacy,
    remaining,
    seed,
    start,
    stop,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True
ROOT = Path(__file__).parents[2]


def restricted(data, role, port=None):
    # LOGIN exists solely in this disposable fixture, never in a migration.
    return psycopg.connect(
        host="127.0.0.1", port=port or data[0]["db"].port, user=role, dbname="postgres"
    )


@pytest.fixture
def complete(prepared, request):
    u, e, *_ = prepared
    if not u["db"].rows(
        "select 1 from information_schema.columns where table_name='subscription_auto_runs' and column_name='owner_verifier'"
    ):
        with e.connect() as c:
            c.execute(
                (
                    ROOT
                    / "supabase/migrations/20261031120000_privacy_auto_credentials.sql"
                ).read_text(encoding="utf-8")
            )
            c.execute(
                "alter role privacy_cleanup_executor login;alter role privacy_preparation_executor login"
            )
    e.credential_connect = lambda: restricted(prepared, "privacy_cleanup_executor")
    if request.config.getoption("--c15-prepare-fields", default=False):
        with e.transaction() as c:
            MANIFEST.write_text(
                json.dumps(candidate_manifest(c), indent=2), encoding="utf-8"
            )
    yield prepared
    e.credential_connect = None


def erase(data):
    _u, e, *_ = data
    assert e.queue_accepted()
    job = e.claim()
    assert job["kind"] == "account"
    with restricted(data, "privacy_cleanup_executor") as c:
        check_executor_identity(c, "privacy_cleanup_executor")
        c.execute(
            "select privacy_auto_credentials_erase(%s,%s)", (job["id"], job["lease"])
        )
    return job


def test_new_parent_has_only_non_replayable_verifier_and_wire_compatibility(complete):
    u, e, *_ = complete
    doc, row = start(complete)
    with e.transaction() as c:
        assert c.execute(
            "select owner_token is null,owner_verifier=sha256(convert_to(%s,'UTF8')) from subscription_auto_runs where run_id=%s",
            (row["owner_token"], row["run_id"]),
        ).fetchone() == (True, True)
    with restricted(complete, "usage_executor") as c:
        check_executor_identity(c, "usage_executor")
        assert c.execute(
            "select subscription_auto_authorize(%s,%s,%s,%s,'microphone')",
            (u["account"], row["run_id"], row["owner_token"], row["fence"]),
        ).fetchone()[0]["authorized_until"]
    assert u["subscription"].auto(u["actor"], "start", doc) == row
    renewed = u["subscription"].auto(
        u["actor"],
        "renew",
        {
            "run_id": row["run_id"],
            "owner_token": row["owner_token"],
            "sequence": 1,
            "fence": row["fence"],
        },
    )
    assert renewed["owner_token"] == row["owner_token"]
    stopped = stop(complete, renewed)
    assert not stopped["active"]
    # Idempotent stop requires the original verifier, not a new authorization.
    assert stop(complete, renewed) == stopped
    with pytest.raises(psycopg.Error), restricted(complete, "usage_executor") as c:
        c.execute(
            "select subscription_auto_authorize(%s,%s,%s,%s,'microphone')",
            (u["account"], row["run_id"], row["owner_token"], row["fence"]),
        )

    # The first native fixture also owns the pre-migration legacy run. Erase
    # its mutable parent only under accepted account scope; compare reply bytes.
    with e.transaction() as c:
        legacy_before = c.execute(
            "select a.run_id,a.document from subscription_auto_replies a join subscription_auto_runs r using(run_id) where r.account_id=%s and not a.document ? 'format_version' order by a.run_id,a.sequence",
            (u["account"],),
        ).fetchall()
        assert legacy_before
    accept(complete)
    erase(complete)
    with e.transaction() as c:
        assert c.execute(
            "select owner_token,owner_verifier from subscription_auto_runs where account_id=%s",
            (u["account"],),
        ).fetchall() == [(None, None), (None, None)]
        assert (
            c.execute(
                "select a.run_id,a.document from subscription_auto_replies a join subscription_auto_runs r using(run_id) where r.account_id=%s and not a.document ? 'format_version' order by a.run_id,a.sequence",
                (u["account"],),
            ).fetchall()
            == legacy_before
        )


def test_concurrent_duplicates_wrong_credential_and_null_denied(complete):
    u, _e, *_ = complete
    doc, row = start(complete)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: u["subscription"].auto(u["actor"], "start", doc), range(2)
            )
        )
    assert results == [row, row]
    for token in (None, str(uuid4())):
        with pytest.raises(psycopg.Error), restricted(complete, "usage_executor") as c:
            c.execute(
                "select subscription_auto_authorize(%s,%s,%s,%s,'microphone')",
                (u["account"], row["run_id"], token, row["fence"]),
            )
    stop(complete, row)


def test_acceptance_settles_active_run_and_scoped_cleanup_erases_credentials(complete):
    u, e, *_ = complete
    doc, row = start(complete)
    accept(complete)
    with e.transaction() as c:
        assert c.execute(
            "select active from subscription_auto_runs where run_id=%s",
            (row["run_id"],),
        ).fetchone() == (False,)
        before = c.execute(
            "select document from subscription_auto_replies where run_id=%s order by sequence",
            (row["run_id"],),
        ).fetchall()
    job = erase(complete)
    with restricted(complete, "privacy_cleanup_executor") as c:
        assert (
            c.execute(
                "select privacy_auto_credentials_erase(%s,%s)",
                (job["id"], job["lease"]),
            ).fetchone()[0]
            == 0
        )
    with e.transaction() as c:
        assert c.execute(
            "select owner_token,owner_verifier from subscription_auto_runs where run_id=%s",
            (row["run_id"],),
        ).fetchone() == (None, None)
        assert c.execute(
            "select response,private_checksum from privacy_auto_reply_payloads where run_id=%s",
            (row["run_id"],),
        ).fetchone() == (None, None)
        assert (
            c.execute(
                "select document from subscription_auto_replies where run_id=%s order by sequence",
                (row["run_id"],),
            ).fetchall()
            == before
        )
    with pytest.raises(CatalogStoreError):
        u["subscription"].auto(u["actor"], "start", doc)
    with (
        pytest.raises(psycopg.Error),
        restricted(complete, "privacy_cleanup_executor") as c,
    ):
        c.execute(
            "select privacy_auto_credentials_erase(%s,%s)", (job["id"], str(uuid4()))
        )


@pytest.mark.parametrize(
    "role",
    ["usage_executor", "privacy_cleanup_executor", "privacy_preparation_executor"],
)
def test_real_restricted_connections_direct_privileges_and_set_role(complete, role):
    _u, _e, *_ = complete
    with restricted(complete, role) as c:
        check_executor_identity(c, role)
        assert c.execute(
            "select current_user,session_user,current_setting('role')"
        ).fetchone() == (role, role, "none")
        assert (
            c.execute(
                "select count(*) from pg_auth_members where member=(select oid from pg_roles where rolname=current_user)"
            ).fetchone()[0]
            == 0
        )
    for query in (
        "select response from privacy_auto_reply_payloads",
        "update privacy_auto_reply_payloads set response='{}'",
        "truncate privacy_auto_reply_payloads",
        "delete from subscription_auto_replies",
        "truncate subscription_auto_replies",
        "update privacy_retirement_configuration set enabled=true",
        "set role privacy_payload_owner",
        "set role catalog_test_owner",
    ):
        with pytest.raises(psycopg.Error), restricted(complete, role) as c:
            c.execute(query)
    # SET ROLE to self is possible in PG, but protected RPCs explicitly deny it.
    with pytest.raises(psycopg.Error), restricted(complete, role) as c:
        c.execute("set role " + role)
        if role == "privacy_preparation_executor":
            c.execute("select privacy_retirement_report(1)")
        elif role == "privacy_cleanup_executor":
            c.execute(
                "select privacy_auto_credentials_erase(%s,%s)",
                (str(uuid4()), str(uuid4())),
            )
        else:
            c.execute("select subscription_access_check(%s)", (str(uuid4()),))


def test_narrow_function_owner_search_path_and_preparation_entry(complete):
    _u, e, *_ = complete
    with e.transaction() as c:
        assert c.execute(
            "select p.prosecdef,r.rolsuper,r.rolbypassrls,r.rolcanlogin,p.proconfig from pg_proc p join pg_roles r on r.oid=p.proowner where p.oid='privacy_auto_credentials_erase(uuid,uuid)'::regprocedure"
        ).fetchone() == (True, False, False, False, ["search_path=pg_catalog"])
        assert not c.execute(
            "select has_function_privilege('privacy_preparation_executor','privacy_auto_credentials_erase(uuid,uuid)','execute')"
        ).fetchone()[0]
    with restricted(complete, "privacy_preparation_executor") as c:
        check_executor_identity(c, "privacy_preparation_executor")
        c.execute("set search_path=pg_temp")
        result = c.execute("select public.privacy_retirement_report(100)").fetchone()[0]
        assert result["execution_enabled"] is False
    with (
        pytest.raises(psycopg.Error),
        restricted(complete, "privacy_cleanup_executor") as c,
    ):
        c.execute("select privacy_retirement_report(1)")


def test_worker_uses_restricted_rpc_and_never_claims_full_erasure(complete):
    _doc, row = start(complete)
    stop(complete, row)
    accept(complete)
    e = complete[1]
    assert e.queue_accepted() and e.run_one()
    with e.transaction() as c:
        state, progress = c.execute(
            "select state,progress from privacy_content_jobs where account_id=%s and kind='account'",
            (complete[0]["account"],),
        ).fetchone()
        assert state == "primary_verified"
        assert progress["auto_reply_payloads"] == "verified_erased"
        assert "subscription_auto_replies" in progress["retained_exceptions"]
        # Verified private-sidecar absence is separate from retained immutable
        # metadata. Empty/allowlisted envelopes must not be false blockers.
        assert (
            c.execute(
                "select count(*) from privacy_auto_reply_payloads where run_id=%s and (response is not null or private_checksum is not null)",
                (row["run_id"],),
            ).fetchone()[0]
            == 0
        )
        assert c.execute(
            "select owner_verifier,owner_token from subscription_auto_runs where run_id=%s",
            (row["run_id"],),
        ).fetchone() == (None, None)
        validate_schema(c, require_full=True)


def test_missing_principal_and_cross_scope_cleanup_fail_closed(complete):
    _doc, row = start(complete)
    stop(complete, row)
    accept(complete)
    e = complete[1]
    assert e.queue_accepted()
    job = e.claim()
    e.credential_connect = None
    with pytest.raises(
        ContentBlocked, match="restricted_cleanup_principal_unavailable"
    ):
        e.cleanup(job)
    for kind in ("foreign", "stale"):
        with (
            pytest.raises(psycopg.Error),
            restricted(complete, "privacy_cleanup_executor") as c,
        ):
            c.execute(
                "select privacy_auto_credentials_erase(%s,%s)",
                (str(uuid4()) if kind == "foreign" else job["id"], str(uuid4())),
            )
    with e.transaction() as c:
        assert c.execute(
            "select state from privacy_auto_reply_payloads where run_id=%s",
            (row["run_id"],),
        ).fetchone() == ("available",)


def test_legacy_inactive_parent_is_erased_without_rewriting_reply(complete):
    # This fixture's legacy run was created before both candidate migrations.
    # Find the proven owner, never guess ownership from the current test account.
    u, e, *_ = complete
    with e.transaction() as c:
        legacy = c.execute(
            "select r.account_id,r.run_id,r.owner_token,a.document from subscription_auto_runs r join subscription_auto_replies a using(run_id) where not a.document ? 'format_version' and a.sequence=0 order by r.run_id limit 1"
        ).fetchone()
        assert legacy is not None
        owner, run, token, document = legacy
        # A previous accepted case may already have removed its parent token;
        # immutable reply bytes must still be preserved either way.
        assert document.get("owner_token") is not None
        if str(owner) != u["account"]:
            assert c.execute(
                "select active from subscription_auto_runs where run_id=%s", (run,)
            ).fetchone() == (False,)
    # Cleanup authority always derives the actual request's owner. An unrelated
    # current request cannot delete another account's legacy parent credential.
    accept(complete)
    erase(complete)
    with e.transaction() as c:
        assert (
            c.execute(
                "select document from subscription_auto_replies where run_id=%s and sequence=0",
                (run,),
            ).fetchone()[0]
            == document
        )
        after = c.execute(
            "select owner_token from subscription_auto_runs where run_id=%s", (run,)
        ).fetchone()[0]
        assert after == (None if str(owner) == u["account"] else token)


def test_stale_worker_after_credential_commit_and_retry(complete):
    _doc, row = start(complete)
    stop(complete, row)
    accept(complete)
    e = complete[1]
    job = erase(complete)
    with e.transaction() as c:
        c.execute(
            "update privacy_content_jobs set lease_until=clock_timestamp()-interval '1 second' where id=%s",
            (job["id"],),
        )
    new = e.claim()
    assert new["id"] == job["id"] and new["lease"] != job["lease"]
    with (
        pytest.raises(psycopg.Error),
        restricted(complete, "privacy_cleanup_executor") as c,
    ):
        c.execute(
            "select privacy_auto_credentials_erase(%s,%s)", (job["id"], job["lease"])
        )

    def attempt(_):
        with restricted(complete, "privacy_cleanup_executor") as c:
            return c.execute(
                "select privacy_auto_credentials_erase(%s,%s)",
                (new["id"], new["lease"]),
            ).fetchone()[0]

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(attempt, range(2))) == [0, 0]


def test_updated_schema_export_excludes_verifier_and_private_sidecars(complete):
    import io
    import zipfile

    u, e, *_ = complete
    _doc, row = start(complete)
    stop(complete, row)
    job = str(uuid4())
    e.request(u["account"], job)
    assert e.run_one()
    token = e.authorize(u["account"], job)
    archive = b"".join(e.download(u["account"], job, token))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for name in z.namelist():
            data = z.read(name)
            assert row["owner_token"].encode() not in data
            assert b"owner_verifier" not in data and b"private_checksum" not in data
    with e.transaction() as c:
        assert validate_schema(c, require_full=True)["tables"] == 80


def test_notifications_and_logging_with_final_schema(complete, caplog):
    from test_privacy_remaining_native import (
        test_event_store_logging_does_not_include_provider_error_payload,
        test_privacy_notifications_reuse_durable_contract_and_never_claim_full_erasure,
    )

    test_privacy_notifications_reuse_durable_contract_and_never_claim_full_erasure(
        complete, caplog
    )
    test_event_store_logging_does_not_include_provider_error_payload(caplog)


def test_expired_run_cannot_reauthorize_or_reserve_again(complete):
    u, e, *_ = complete
    doc, row = start(complete)
    with e.transaction() as c:
        c.execute(
            "update usage_operations set lease_until=clock_timestamp()-interval '1 second' where operation_id=(select slice_id from subscription_auto_runs where run_id=%s)",
            (row["run_id"],),
        )
        before = c.execute(
            "select count(*) from usage_operations where resource_id=%s",
            (row["run_id"],),
        ).fetchone()[0]
    with pytest.raises(psycopg.Error), restricted(complete, "usage_executor") as c:
        c.execute(
            "select subscription_auto_authorize(%s,%s,%s,%s,'microphone')",
            (u["account"], row["run_id"], row["owner_token"], row["fence"]),
        )
    with restricted(complete, "usage_executor") as c:
        assert c.execute(
            "select subscription_auto_reap(%s)", (u["account"],)
        ).fetchone()[0]
    with pytest.raises(CatalogStoreError):
        u["subscription"].auto(u["actor"], "start", doc)
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from usage_operations where resource_id=%s",
                (row["run_id"],),
            ).fetchone()[0]
            == before
        )
        c.execute(
            "alter table subscription_auto_runs add column synthetic_unclassified text"
        )
        with pytest.raises(ContentBlocked, match="unclassified_field"):
            validate_schema(c)
        c.execute(
            "alter table subscription_auto_runs drop column synthetic_unclassified"
        )
