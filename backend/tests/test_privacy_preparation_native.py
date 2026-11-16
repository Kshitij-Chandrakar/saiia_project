"""Forward-only preparation/separation; native DB, synthetic/fake boundaries."""

# ruff: noqa: F401,F811 -- imported native pytest fixtures
import hashlib
import json
import secrets
import shutil
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.privacy_content import ContentBlocked
from app.privacy_restore import RestoreGate, RestoreJournal
from app.privacy_schema import MANIFEST, candidate_manifest, validate_schema
from test_draft_service_native import actor
from test_privacy_remaining_native import (
    Storage,
    accept,
    case,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    privacy,
    remaining,
    security_email,
    seed,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True
ROOT = Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def owned_temporary_journals(tmp_path):
    owned = tmp_path.resolve()
    assert owned.is_relative_to(
        Path(tempfile.gettempdir()).resolve()
    ) and owned.name.startswith("test_")
    yield
    shutil.rmtree(owned)


def call(e, statement, parameters=()):
    with e.connect() as c:
        c.execute("set session authorization privacy_preparation_executor")
        c.commit()
        return c.execute(statement, parameters).fetchone()[0]


def start(data):
    u, *_ = data
    doc = {"run_id": str(uuid4()), "request_id": str(uuid4())}
    return doc, u["subscription"].auto(u["actor"], "start", doc)


def stop(data, row):
    u, *_ = data
    return u["subscription"].auto(
        u["actor"],
        "stop",
        {
            "run_id": row["run_id"],
            "owner_token": row["owner_token"],
            "fence": row["fence"],
            "sequence": row["sequence"] + 1,
        },
    )


@pytest.fixture
def prepared(remaining, request):
    u, e, *_ = remaining
    if not u["db"].rows(
        "select 1 from pg_tables where tablename='privacy_auto_reply_payloads'"
    ):
        doc, legacy = start(remaining)
        stop(remaining, legacy)
        with e.transaction() as c:
            before = c.execute(
                "select sha256(convert_to(jsonb_agg(to_jsonb(a) order by run_id,sequence)::text,'UTF8')) from subscription_auto_replies a"
            ).fetchone()[0]
        try:
            with e.connect() as connection:
                connection.execute(
                    (
                        ROOT
                        / "supabase/migrations/20261031100000_privacy_retirement_preparation.sql"
                    ).read_text(encoding="utf-8")
                )
        except psycopg.Error as error:
            # Migration text contains schema constants, never customer payload.
            raise AssertionError(
                (
                    error.diag.message_primary,
                    error.diag.context,
                    error.diag.statement_position,
                )
            ) from None
        with e.transaction() as c:
            after = c.execute(
                "select sha256(convert_to(jsonb_agg(to_jsonb(a) order by run_id,sequence)::text,'UTF8')) from subscription_auto_replies a"
            ).fetchone()[0]
        unchanged = before == after
        assert unchanged
        u["db"].legacy = (doc, legacy)
    if not u["db"].rows(
        "select 1 from information_schema.columns where table_name='subscription_auto_runs' and column_name='owner_verifier'"
    ):
        with e.connect() as connection:
            connection.execute(
                (
                    ROOT
                    / "supabase/migrations/20261031120000_privacy_auto_credentials.sql"
                ).read_text(encoding="utf-8")
            )
            # Disposable connections only, never production role provisioning.
            connection.execute(
                "alter role privacy_cleanup_executor login;alter role privacy_preparation_executor login"
            )
    e.credential_connect = lambda: psycopg.connect(
        host="127.0.0.1",
        port=u["db"].port,
        user="privacy_cleanup_executor",
        dbname="postgres",
    )
    if request.config.getoption("--c15-prepare-fields", default=False):
        with e.transaction() as c:
            manifest = candidate_manifest(c)
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with e.transaction() as c:
        catalog_before = [
            c.execute(
                "select sha256(convert_to(coalesce(jsonb_agg(to_jsonb(v) order by to_jsonb(v)::text),'[]')::text,'UTF8')) from "
                + table
                + " v"
            ).fetchone()[0]
            for table in (
                "catalog_plans",
                "catalog_offer_versions",
                "catalog_price_versions",
            )
        ]
        legacy_before = c.execute(
            "select sha256(convert_to(coalesce(jsonb_agg(to_jsonb(v) order by run_id,sequence),'[]')::text,'UTF8')) from subscription_auto_replies v where not document ? 'format_version'"
        ).fetchone()[0]
    yield remaining
    with e.transaction() as c:
        catalog_after = [
            c.execute(
                "select sha256(convert_to(coalesce(jsonb_agg(to_jsonb(v) order by to_jsonb(v)::text),'[]')::text,'UTF8')) from "
                + table
                + " v"
            ).fetchone()[0]
            for table in (
                "catalog_plans",
                "catalog_offer_versions",
                "catalog_price_versions",
            )
        ]
        legacy_after = c.execute(
            "select sha256(convert_to(coalesce(jsonb_agg(to_jsonb(v) order by run_id,sequence),'[]')::text,'UTF8')) from subscription_auto_replies v where not document ? 'format_version'"
        ).fetchone()[0]
    intact = catalog_before == catalog_after and legacy_before == legacy_after
    assert intact


def prepare(data, category="usage_recovery", days=91):
    u, e, *_ = data
    accept(data, days)
    with e.transaction() as c:
        c.execute("update privacy_retirement_configuration set enabled=true")
        req = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (u["account"],),
        ).fetchone()[0]
    unit = call(
        e, "select privacy_retirement_prepare(%s,%s,%s)", (u["account"], req, category)
    )
    return unit


def reason(data, unit):
    with data[1].transaction() as c:
        return c.execute("select privacy_retirement_reason(%s)", (unit,)).fetchone()[0]


def erase(data):
    _u, e, *_ = data
    assert e.queue_accepted()
    job = e.claim()
    assert job["kind"] == "account"
    with e.transaction() as c:
        c.execute("select privacy_auto_payload_erase(%s,%s)", (job["id"], job["lease"]))
    return job


def test_forward_writer_and_legacy_replay_equivalence(prepared):
    u, e, *_ = prepared
    legacy_doc, legacy = u["db"].legacy
    replay = u["subscription"].auto(u["actor"], "start", legacy_doc)
    same = replay == legacy
    assert same
    doc, row = start(prepared)
    duplicate = u["subscription"].auto(u["actor"], "start", doc)
    assert duplicate == row
    with e.transaction() as c:
        assert c.execute(
            "select document from subscription_auto_replies where run_id=%s",
            (row["run_id"],),
        ).fetchone()[0] == {"format_version": 2}
        assert (
            c.execute(
                "select count(*) from privacy_auto_reply_payloads where run_id=%s and response ? %s",
                (row["run_id"], "owner_token"),
            ).fetchone()[0]
            == 1
        )
    stop(prepared, row)


def test_existing_auto_regression_new_format(prepared):
    u, e, *_ = prepared
    _doc, row = start(prepared)
    with pytest.raises(CatalogStoreError) as error:
        start(prepared)
    assert error.value.code == ErrorCode.CONFLICT
    stopped = stop(prepared, row)
    replay = stop(prepared, row)
    equivalent = stopped == replay
    assert equivalent
    status = u["subscription"].auto(u["actor"], "status", {"run_id": row["run_id"]})
    assert not status["active"] and "owner_token" not in status
    other = str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
        charge = c.execute(
            "select charged,requested,state from usage_operations where resource_id=%s",
            (row["run_id"],),
        ).fetchone()
        assert charge[2] == "settled" and 0 <= charge[0] <= charge[1]
    u["subscription"].current(actor(other), bootstrap=True)
    with pytest.raises(CatalogStoreError):
        u["subscription"].auto(
            actor(other),
            "stop",
            {
                "run_id": row["run_id"],
                "owner_token": row["owner_token"],
                "fence": row["fence"],
                "sequence": 1,
            },
        )


def test_role_denial_and_default_closed_preparation(prepared):
    u, e, *_ = prepared
    with e.transaction() as c:
        c.execute("update privacy_retirement_configuration set enabled=false")
    with pytest.raises(psycopg.Error):
        call(
            e,
            "select privacy_retirement_prepare(%s,null,%s)",
            (u["account"], "usage_recovery"),
        )
    for role in [
        "anon",
        "authenticated",
        "service_role",
        "usage_executor",
        "privacy_preparation_executor",
    ]:
        with pytest.raises(psycopg.Error), e.connect() as c:
            c.execute("set session authorization " + role)
            c.commit()
            c.execute("update privacy_retirement_configuration set enabled=true")
        with pytest.raises(psycopg.Error), e.connect() as c:
            c.execute("set session authorization " + role)
            c.commit()
            c.execute("select response from privacy_auto_reply_payloads")


def test_new_format_duplicate_writes_are_atomic_and_account_isolated(prepared):
    u, e, *_ = prepared
    doc = {"run_id": str(uuid4()), "request_id": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(
            pool.map(
                lambda _: u["subscription"].auto(u["actor"], "start", doc), range(2)
            )
        )
    assert rows[0] == rows[1]
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from subscription_auto_replies where run_id=%s",
                (doc["run_id"],),
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from usage_operations where resource_id=%s",
                (doc["run_id"],),
            ).fetchone()[0]
            == 1
        )
    other = str(uuid4())
    with e.connect() as c:
        c.execute("set session authorization usage_executor")
        c.commit()
        with pytest.raises(psycopg.Error):
            c.execute("select privacy_auto_reply_read(%s,%s,0)", (other, doc["run_id"]))
    stop(prepared, rows[0])


def test_expired_new_reply_never_reexecutes(prepared):
    u, e, *_ = prepared
    doc, row = start(prepared)
    stop(prepared, row)
    with e.transaction() as c:
        before = c.execute(
            "select count(*) from usage_operations where resource_id=%s",
            (row["run_id"],),
        ).fetchone()[0]
    with pytest.raises(CatalogStoreError) as error:
        u["subscription"].auto(u["actor"], "start", doc)
    assert error.value.code == ErrorCode.AUTO_REPLY_EXPIRED
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from usage_operations where resource_id=%s",
                (row["run_id"],),
            ).fetchone()[0]
            == before
        )


@pytest.mark.parametrize(
    "age,expected", [(89, "not_due"), (91, "eligible_preparation_only")]
)
def test_usage_unit_clock_and_private_erasure(prepared, age, expected):
    _doc, row = start(prepared)
    stop(prepared, row)
    unit = prepare(prepared, days=age)
    assert reason(prepared, unit) == "private_payload_present"
    erase(prepared)
    assert reason(prepared, unit) == expected


@pytest.mark.parametrize(
    "age,expected", [(179, "not_due"), (181, "eligible_preparation_only")]
)
def test_security_unit_exact_clock(prepared, age, expected):
    security_email(prepared)
    accept(prepared, age)
    from app.privacy_remaining import Minimizer

    Minimizer(prepared[1]).run(prepared[0]["account"])
    with prepared[1].transaction() as c:
        c.execute("update privacy_retirement_configuration set enabled=true")
        req = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (prepared[0]["account"],),
        ).fetchone()[0]
    unit = call(
        prepared[1],
        "select privacy_retirement_prepare(%s,%s,'security_audit')",
        (prepared[0]["account"], req),
    )
    assert reason(prepared, unit) == expected


def test_hold_revision_reporting_and_no_retirement_capability(prepared):
    _doc, row = start(prepared)
    stop(prepared, row)
    unit = prepare(prepared)
    erase(prepared)
    e = prepared[1]
    assert (
        call(
            e,
            "select privacy_retirement_hold(%s,1,'operational',clock_timestamp()+interval '1 day',true)",
            (unit,),
        )
        == 2
    )
    assert reason(prepared, unit) == "hold"
    with pytest.raises(psycopg.Error):
        call(
            e,
            "select privacy_retirement_hold(%s,1,'security',clock_timestamp()+interval '1 day',false)",
            (unit,),
        )
    assert (
        call(
            e,
            "select privacy_retirement_hold(%s,2,'operational',clock_timestamp()+interval '1 day',false)",
            (unit,),
        )
        == 3
    )
    assert reason(prepared, unit) == "eligible_preparation_only"
    report = call(e, "select privacy_retirement_report(100)")
    assert report["execution_enabled"] is False and "counts" in report
    assert not any(
        key in json.dumps(report)
        for key in ["owner_token", "account_id", "unit_id", "response"]
    )
    with e.transaction() as c:
        assert (
            c.execute(
                "select count(*) from privacy_retirement_preparation_events where unit_id=%s",
                (unit,),
            ).fetchone()[0]
            == 3
        )
        assert not c.execute(
            "select has_table_privilege('privacy_preparation_executor','subscription_auto_replies','DELETE')"
        ).fetchone()[0]


@pytest.mark.parametrize("category", ["financial", "shared", "unclassified"])
def test_unsupported_classes_stay_blocked(prepared, category):
    unit = prepare(prepared, category)
    assert reason(prepared, unit) == "unsupported_category"


def test_missing_clock_wrong_owner_schema_drift_and_legacy_guards(prepared):
    u, e, *_ = prepared
    with e.transaction() as c:
        c.execute("update privacy_retirement_configuration set enabled=true")
    unit = call(
        e,
        "select privacy_retirement_prepare(%s,null,'usage_recovery')",
        (u["account"],),
    )
    assert reason(prepared, unit) == "missing_clock"
    with e.transaction() as c:
        validate_schema(c, require_full=True)
        c.execute(
            "alter table privacy_auto_reply_payloads add column unclassified_private text"
        )
        with pytest.raises(ContentBlocked):
            validate_schema(c)
        c.execute(
            "alter table privacy_auto_reply_payloads drop column unclassified_private"
        )
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute("update subscription_auto_replies set document='{}'")
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute("truncate subscription_auto_replies")


def test_active_retention_lease_and_hold_review_never_expires_automatically(
    prepared,
):
    from app.privacy_remaining import Minimizer
    from test_privacy_remaining_native import retention

    security_email(prepared)
    accept(prepared, 181)
    Minimizer(prepared[1]).run(prepared[0]["account"])
    e = prepared[1]
    with e.transaction() as c:
        c.execute("update privacy_retirement_configuration set enabled=true")
        req = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (prepared[0]["account"],),
        ).fetchone()[0]
    unit = call(
        e,
        "select privacy_retirement_prepare(%s,%s,'security_audit')",
        (prepared[0]["account"], req),
    )
    worker = retention(prepared)
    for _ in range(100):
        # Claims are global, not account-targeted. Earlier eligible fixtures
        # must not be mistaken for this unit's active member.
        assert worker.call("claim", str(uuid4()))
        with e.transaction() as c:
            claimed = c.execute(
                "select state='leased' from privacy_minimized_records where account_id=%s",
                (prepared[0]["account"],),
            ).fetchone()[0]
        if claimed:
            break
    else:
        raise AssertionError("synthetic member was not claimed")
    assert reason(prepared, unit) == "active_writer"
    call(
        e,
        "select privacy_retirement_hold(%s,1,'operational',clock_timestamp()+interval '1 day',true)",
        (unit,),
    )
    with e.transaction() as c:
        c.execute(
            "update privacy_retirement_holds set review_at=clock_timestamp()-interval '1 second' where unit_id=%s",
            (unit,),
        )
    assert reason(prepared, unit) == "hold_review_due"


@pytest.mark.parametrize(
    "sqlstate,expected",
    [
        ("P1001", "auto_reply_erased"),
        ("P1002", "auto_reply_expired"),
        ("P1003", "auto_reply_corrupt"),
        ("P1004", "auto_reply_version_unsupported"),
        ("P1005", "auto_reply_unavailable"),
    ],
)
def test_safe_outcome_mapping(sqlstate, expected):
    from app.commercial.catalog_store import RpcFailure, _error

    assert _error(RpcFailure(sqlstate), True).value == expected


def test_scope_lease_idempotency_and_restore_denial(prepared, tmp_path):
    u, e, *_ = prepared
    doc, row = start(prepared)
    stop(prepared, row)
    prepare(prepared)
    job = erase(prepared)
    with e.transaction() as c:
        assert (
            c.execute(
                "select privacy_auto_payload_erase(%s,%s)", (job["id"], job["lease"])
            ).fetchone()[0]
            == 0
        )
        assert c.execute(
            "select state,response,private_checksum from privacy_auto_reply_payloads where run_id=%s and sequence=0",
            (row["run_id"],),
        ).fetchone() == ("erased", None, None)
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute("select privacy_auto_payload_erase(%s,%s)", (job["id"], str(uuid4())))
    with pytest.raises(CatalogStoreError) as error:
        u["subscription"].auto(u["actor"], "start", doc)
    assert error.value.code == ErrorCode.DENIED
    journal = RestoreJournal(tmp_path / "independent", {"v1": b"x" * 32}, "v1")
    head = RestoreGate(e).publish(u["account"], journal, journal.initialize())
    RestoreGate(e).apply(journal, head)
    with pytest.raises(CatalogStoreError):
        u["subscription"].auto(u["actor"], "start", doc)
    with e.transaction() as c:
        c.execute("update privacy_restore_state set required=false")


@pytest.mark.parametrize(
    "state,version,expected",
    [
        ("erased", 2, "P1001"),
        ("available", 99, "P1004"),
        ("available", 2, "P1003"),
        ("missing", 2, "P1005"),
    ],
)
def test_native_decoder_unavailable_outcomes_without_mutating_history(
    prepared, state, version, expected
):
    _doc, row = start(prepared)
    u, e, *_ = prepared
    private = {
        "run_id": None if state == "missing" else row["run_id"],
        "sequence": 0,
        "account_id": u["account"],
        "format_version": version,
        "state": state,
        "response": {},
        "private_checksum": "\\x00",
    }
    with pytest.raises(psycopg.Error) as error, e.transaction() as c:
        # Composite input is decoded, not inserted into a protected table.
        c.execute(
            "select privacy_auto_payload_decode(jsonb_populate_record(null::privacy_auto_reply_payloads,%s::jsonb),r,0) from subscription_auto_runs r where r.run_id=%s",
            (json.dumps(private), row["run_id"]),
        )
    assert error.value.sqlstate == expected
    stop(prepared, row)


def test_wrong_clock_ownership_mixed_class_and_dependency_gap(prepared):
    _doc, row = start(prepared)
    stop(prepared, row)
    unit = prepare(prepared)
    erase(prepared)
    u, e, *_ = prepared
    with e.transaction() as c:
        request = c.execute(
            "select request_id from privacy_deletion_requests where account_id=%s",
            (u["account"],),
        ).fetchone()[0]
        other = str(uuid4())
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
    with pytest.raises(psycopg.Error):
        call(
            e,
            "select privacy_retirement_prepare(%s,%s,'usage_recovery')",
            (other, request),
        )
    with e.transaction() as c:
        c.execute(
            "update privacy_retirement_units set category='security_audit',eligible_at=confirmation_at+interval '180 days' where unit_id=%s",
            (unit,),
        )
    assert reason(prepared, unit) == "mixed_class"
    with e.transaction() as c:
        c.execute(
            "update privacy_retirement_units set category='usage_recovery',eligible_at=confirmation_at+interval '1 day' where unit_id=%s",
            (unit,),
        )
    assert reason(prepared, unit) == "clock_mismatch"
    with e.transaction() as c:
        c.execute(
            "update privacy_retirement_units set eligible_at=confirmation_at+interval '90 days' where unit_id=%s",
            (unit,),
        )
        c.execute(
            "create table synthetic_reply_dependency(run_id uuid,sequence bigint,foreign key(run_id,sequence) references subscription_auto_replies)"
        )
    try:
        assert reason(prepared, unit) == "dependency_gap"
    finally:
        with e.transaction() as c:
            c.execute("drop table synthetic_reply_dependency")


def test_sidecar_cleanup_recovers_after_commit_and_keeps_immutable_bytes(prepared):
    _doc, row = start(prepared)
    stop(prepared, row)
    prepare(prepared)
    e = prepared[1]
    with e.transaction() as c:
        before = c.execute(
            "select document from subscription_auto_replies where run_id=%s order by sequence",
            (row["run_id"],),
        ).fetchall()
    job = erase(prepared)
    with e.transaction() as c:
        c.execute(
            "update privacy_content_jobs set lease_until=clock_timestamp()-interval '1 second' where id=%s",
            (job["id"],),
        )
    replacement = e.claim()
    assert replacement["id"] == job["id"] and replacement["lease"] != job["lease"]
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute("select privacy_auto_payload_erase(%s,%s)", (job["id"], job["lease"]))
    with e.transaction() as c:
        assert (
            c.execute(
                "select privacy_auto_payload_erase(%s,%s)",
                (replacement["id"], replacement["lease"]),
            ).fetchone()[0]
            == 0
        )
        after = c.execute(
            "select document from subscription_auto_replies where run_id=%s order by sequence",
            (row["run_id"],),
        ).fetchall()
    unchanged = before == after
    assert unchanged


def test_erasure_quarantines_cross_account_corrupt_sidecar(prepared):
    _doc, row = start(prepared)
    stop(prepared, row)
    unit = prepare(prepared)
    assert unit
    u, e, *_ = prepared
    assert e.queue_accepted()
    job = e.claim()

    class RollbackFixture(Exception):
        pass

    with pytest.raises(RollbackFixture), e.transaction() as c:
        # Malformed new fixture input is rolled back, never a legacy rewrite.
        other, foreign = str(uuid4()), str(uuid4())
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
        c.execute(
            "insert into subscription_auto_runs(run_id,account_id,request_id,semantic_hash,active) values(%s,%s,%s,%s,false)",
            (foreign, other, str(uuid4()), "a" * 64),
        )
        c.execute(
            "insert into privacy_auto_reply_payloads(run_id,sequence,account_id,response,private_checksum) values(%s,9999,%s,'{}',decode('00','hex'))",
            (foreign, u["account"]),
        )
        with pytest.raises(psycopg.Error) as error, c.connection.transaction():
            c.execute(
                "select privacy_auto_payload_erase(%s,%s)", (job["id"], job["lease"])
            )
        assert error.value.sqlstate == "42501"
        raise RollbackFixture()


def test_cold_restore_of_erased_sidecar_remains_denied(prepared, tmp_path):
    u, e, _storage, *_ = prepared
    _doc, row = start(prepared)
    db = u["db"]
    clone = db.directory / "sidecar-restore"
    db.command("pg_ctl", ["-D", str(db.directory / "data"), "-m", "fast", "-w", "stop"])
    try:
        shutil.copytree(db.directory / "data", clone)
    finally:
        db.command(
            "pg_ctl",
            [
                "-D",
                str(db.directory / "data"),
                "-l",
                str(db.directory / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {db.port}",
                "-w",
                "start",
            ],
        )
    prepare(prepared)
    erase(prepared)
    journal = RestoreJournal(
        tmp_path / "outside-snapshot", {"v1": secrets.token_bytes(32)}, "v1"
    )
    head = RestoreGate(e).publish(u["account"], journal, journal.initialize())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    started = False
    try:
        db.command(
            "pg_ctl",
            [
                "-D",
                str(clone),
                "-l",
                str(db.directory / "sidecar-restore.log"),
                "-o",
                f"-h 127.0.0.1 -p {port}",
                "-w",
                "start",
            ],
        )
        started = True

        def connect():
            return psycopg.connect(
                host="127.0.0.1",
                port=port,
                user="catalog_test_owner",
                dbname="postgres",
            )

        from app.privacy_content import ContentEngine

        restored = ContentEngine(
            connect,
            Storage(),
            local_rehearsal=True,
            credential_connect=lambda: psycopg.connect(
                host="127.0.0.1",
                port=port,
                user="privacy_cleanup_executor",
                dbname="postgres",
            ),
        )
        RestoreGate(restored).apply(journal, head)
        with restored.transaction() as c:
            assert (
                c.execute(
                    "select state from privacy_auto_reply_payloads where run_id=%s and sequence=0",
                    (row["run_id"],),
                ).fetchone()[0]
                == "available"
            )
            fingerprint = c.execute(
                "select semantic_hash from subscription_auto_runs where run_id=%s",
                (row["run_id"],),
            ).fetchone()[0]
        with pytest.raises(psycopg.Error) as error, connect() as connection:
            connection.execute("set session authorization usage_executor")
            connection.commit()
            connection.execute(
                "select subscription_auto_call(%s,'start',%s::jsonb)",
                (
                    u["account"],
                    json.dumps(
                        {
                            "run_id": row["run_id"],
                            "request_id": _doc["request_id"],
                            "semantic_hash": fingerprint,
                        }
                    ),
                ),
            )
        assert error.value.sqlstate == "42501"
        assert restored.queue_accepted()
        assert restored.run_one()
        with restored.transaction() as c:
            assert c.execute(
                "select state,response from privacy_auto_reply_payloads where run_id=%s and sequence=0",
                (row["run_id"],),
            ).fetchone() == ("erased", None)
            assert c.execute(
                "select active,owner_token,owner_verifier from subscription_auto_runs where run_id=%s",
                (row["run_id"],),
            ).fetchone() == (False, None, None)
    finally:
        if started:
            db.command("pg_ctl", ["-D", str(clone), "-m", "fast", "-w", "stop"])
