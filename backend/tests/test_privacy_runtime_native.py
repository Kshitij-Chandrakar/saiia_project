"""Normal fixed-operation adapter on restricted native connections."""

# ruff: noqa: F401,F811
import json
from uuid import uuid4

import psycopg
import pytest
from app.privacy_content import ContentBlocked, ContentEngine
from app.privacy_runtime_db import RuntimeConnection
from test_privacy_completion_native import (
    ROOT,
    accept,
    case,
    complete,
    content,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    owned_temporary_journals,
    prepared,
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
from test_privacy_content_native import (
    test_export_native_isolation_expiry_and_single_use as assert_export,
)


@pytest.fixture
def runtime(complete):
    u, e, storage, *_ = complete
    with e.connect() as c:
        if (
            c.execute(
                "select to_regclass('public.privacy_runtime_operations')"
            ).fetchone()[0]
            is None
        ):
            c.execute(
                "alter table auth.users add column if not exists deleted_at timestamptz"
            )
            c.execute(
                (
                    ROOT
                    / "supabase/migrations/20261102020000_privacy_runtime_operations.sql"
                ).read_text(encoding="utf8")
            )
            c.execute(
                "alter role privacy_content_executor login;alter role privacy_restore_executor login"
            )
    engine = ContentEngine(
        lambda: RuntimeConnection(
            restricted(complete, "privacy_content_executor"), "privacy_content_executor"
        ),
        storage,
        local_rehearsal=True,
        credential_connect=e.credential_connect,
    )
    return (u, engine, storage, *complete[3:])


def test_export_normal_runtime_fixed_operations(runtime):
    assert_export(runtime)


def test_runtime_direct_capability_denial(runtime, complete):
    for role in [
        "privacy_content_executor",
        "privacy_restore_executor",
        "privacy_cleanup_executor",
        "usage_executor",
        "authenticated",
        "service_role",
    ]:
        if role in ["authenticated", "service_role"]:
            with complete[1].connect() as c:
                c.execute(
                    psycopg.sql.SQL("alter role {} login").format(
                        psycopg.sql.Identifier(role)
                    )
                )
        queries = [
            "select * from privacy_runtime_operations",
            "set role privacy_runtime_owner",
            "update privacy_runtime_operations set body='select 1'",
        ]
        if role not in ["authenticated", "service_role"]:
            queries += [
                "select * from profiles",
                "delete from profiles",
                "truncate profiles",
            ]
        for query in queries:
            with pytest.raises(psycopg.Error), restricted(complete, role) as c:
                c.execute(query)
    with (
        runtime[1].transaction() as c,
        pytest.raises(ContentBlocked, match="unregistered"),
    ):
        c.execute("select encrypted_password from auth.users")


def test_cleanup_fixed_operations_deny_forged_scope(runtime, complete):
    u, e, *_ = runtime
    _resume, _session, key = seed(complete)
    _, row = start(complete)
    stop(complete, row)
    accept(complete)
    assert e.queue_accepted()
    job = e.claim()
    assert job
    # A forged subject cannot turn another account's pending job into authority.
    with e.transaction() as c, pytest.raises(psycopg.Error):
        c.scope({"id": str(uuid4()), "lease": job["lease"]})
    e.cleanup(job)
    assert ("resumes", key) not in runtime[2].items
    with complete[1].connect() as c:
        assert (
            c.execute(
                "select count(*) from profiles where user_id=%s", (u["account"],)
            ).fetchone()[0]
            == 0
        )
        assert c.execute(
            "select owner_token,owner_verifier from subscription_auto_runs where account_id=%s",
            (u["account"],),
        ).fetchone() == (None, None)


def test_session_scope_normal_runtime(runtime, complete):
    u, engine, storage, *_ = runtime
    resume, session, key = seed(complete)
    request = str(uuid4())
    engine.request(u["account"], request, "session", session)
    assert engine.run_one()
    with complete[1].connect() as c:
        assert (
            c.execute("select count(*) from resumes where id=%s", (resume,)).fetchone()[
                0
            ]
            == 1
        )
        assert (
            c.execute(
                "select count(*) from resume_chunks where resume_id=%s", (resume,)
            ).fetchone()[0]
            == 2
        )
        assert (
            c.execute(
                "select count(*) from interview_session_my_answers where session_id=%s",
                (session,),
            ).fetchone()[0]
            == 0
        )
    assert ("resumes", key) in storage.items


def test_runtime_timestamp_wire_format():
    from app.privacy_runtime_db import decode

    assert decode("2026-11-02T01:00:00Z", 1184).utcoffset().total_seconds() == 0
    assert decode("2026-11-02T01:00:00.16145+05:30", 1184).microsecond == 161450
