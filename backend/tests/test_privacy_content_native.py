"""Disposable PostgreSQL, real transactions, fake object boundary only."""
# ruff: noqa: F811 -- imported native pytest fixtures are injection points

import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from app.privacy_content import ContentBlocked, ContentEngine, Limits, owned_key
from test_privacy_native import (  # noqa: F401
    case,
    database,
    f1_install,
    f2_install,
    install,
    integration,
    pricing,
    privacy,
    upgraded,
    usage,
)

SUPPORTED_AUTH_PACKAGE = True


class Storage:
    def __init__(self):
        self.items = {}
        self.error = None
        self.crash_after_remove = False

    def stat(self, bucket, key):
        if self.error:
            raise self.error
        data = self.items.get((bucket, key))
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def read(self, bucket, key, version):
        assert self.stat(bucket, key) == version
        data = self.items[(bucket, key)]
        for offset in range(0, len(data), 64):
            yield data[offset : offset + 64]

    def put(self, bucket, key, source):
        self.items[bucket, key] = source.read()

    def remove(self, bucket, key):
        self.items.pop((bucket, key), None)
        if self.crash_after_remove:
            self.crash_after_remove = False
            raise TimeoutError()


@pytest.fixture
def content(privacy, request):
    u, service, actor, document = privacy
    db = u["db"]
    if not db.rows("select 1 from pg_tables where tablename='privacy_content_jobs'"):
        db.run(
            (
                Path(__file__).parents[2]
                / "supabase/migrations/20261030120000_privacy_content_jobs.sql"
            ).read_text()
        )

    if not db.rows(
        "select 1 from information_schema.columns where table_name='privacy_export_proofs' and column_name='operation_scope'"
    ):
        db.run(
            (
                Path(__file__).parents[2]
                / "supabase/migrations/20261101040000_privacy_scoped_proofs.sql"
            ).read_text(encoding="utf8")
        )

    def connect():
        return psycopg.connect(
            host="127.0.0.1", port=db.port, user="catalog_test_owner", dbname="postgres"
        )

    storage = Storage()
    engine = ContentEngine(connect, storage, local_rehearsal=True)
    if request.config.getoption("--c15-content-capture", default=False):
        evidence = (
            Path(__file__).parents[2]
            / request.config.getoption(
                "--c15-evidence-dir", default="docs/evidence/c15-export-cleanup"
            )
            / "native-runtime.json"
        )
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with engine.transaction() as c:
            columns = engine.columns(c)
            record = {
                "cluster_directory": str(db.directory),
                "port": db.port,
                "version": c.execute("select version()").fetchone()[0],
                "unclassified_tables": engine.coverage(columns),
                "tables": sorted(columns),
                "network": "127.0.0.1 only",
                "external_boundaries": "in-memory synthetic Storage/mailbox; no real Auth engine",
            }
        evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
    yield u, engine, storage, service, actor, document
    # Each test's worker queue is isolated, even after deliberately abandoned
    # leases or interrupted requests. This is the disposable cluster only.
    with engine.transaction() as c:
        for table in ("privacy_content_objects", "privacy_export_rows"):
            c.execute(
                psycopg.sql.SQL(
                    "delete from {} where job_id in (select id from privacy_content_jobs where account_id=%s)"
                ).format(psycopg.sql.Identifier(table)),
                (u["account"],),
            )
        c.execute(
            "delete from privacy_erased_session_keys where account_id=%s",
            (u["account"],),
        )
        c.execute(
            "delete from privacy_erased_sessions where account_id=%s", (u["account"],)
        )
        c.execute(
            "update privacy_followup_tasks set state='blocked' where kind='personal_cleanup' and request_id in (select request_id from privacy_deletion_requests where account_id=%s)",
            (u["account"],),
        )
        if c.execute(
            "select to_regclass('public.privacy_auto_reply_payloads') is not null"
        ).fetchone()[0]:
            # New erasure markers retain their request/job evidence. Preserve
            # that FK rather than bypass its guard to isolate a synthetic queue.
            c.execute(
                "update privacy_content_jobs j set state='blocked',lease_id=null where account_id=%s and exists(select 1 from privacy_auto_reply_payloads p where p.erasure_job=j.id)",
                (u["account"],),
            )
            c.execute(
                "delete from privacy_content_jobs j where account_id=%s and not exists(select 1 from privacy_auto_reply_payloads p where p.erasure_job=j.id)",
                (u["account"],),
            )
        else:
            c.execute(
                "delete from privacy_content_jobs where account_id=%s", (u["account"],)
            )
        c.execute(
            "delete from privacy_export_proofs where account_id=%s", (u["account"],)
        )
        c.execute(
            "delete from privacy_export_otp_sends where account_id=%s", (u["account"],)
        )


def test_default_closed(content):
    _, e, _, *_ = content
    with pytest.raises(ContentBlocked, match="activation_disabled"):
        ContentEngine(e.connect, e.storage)


def test_export_native_isolation_expiry_and_single_use(content):
    u, e, storage, *_ = content
    account = u["account"]
    job = str(uuid4())
    e.request(account, job)
    assert e.run_one()
    assert e.status(account, job)["state"] == "ready"
    with pytest.raises(ContentBlocked):
        e.status(str(uuid4()), job)
    token = e.authorize(account, job)
    archive = b"".join(e.download(account, job, token))
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert "manifest.json" in z.namelist()
        assert all(".." not in name for name in z.namelist())
        assert "numeric embeddings" in z.read("manifest.json").decode()
    with pytest.raises(ContentBlocked):
        b"".join(e.download(account, job, token))
    u["db"].run(
        f"update privacy_content_jobs set expires_at=clock_timestamp()-interval '1 second' where id='{job}'"
    )
    assert e.status(account, job)["state"] == "expired"
    with pytest.raises(ContentBlocked):
        e.authorize(account, job)
    storage.crash_after_remove = True
    with pytest.raises(TimeoutError):
        e.expire_one()
    assert e.expire_one()
    assert not storage.items


@pytest.mark.parametrize(
    "key",
    [
        "../x/y",
        "a/b/c",
        "{account}/../x",
        "{account}/x/../../a",
        "{account}/x/a\\b",
        "{account}//x",
    ],
)
def test_owned_keys(content, key):
    u, *_ = content
    with pytest.raises(ContentBlocked):
        owned_key(u["account"], key.format(account=u["account"]))


def test_unknown_table_blocks_export_instead_of_omission(content):
    u, e, *_ = content
    with e.transaction() as c:
        c.execute(
            "create table public.synthetic_unknown_content(user_id uuid, secret text)"
        )
    try:
        with pytest.raises(ContentBlocked, match="synthetic_unknown_content"):
            e.request(u["account"], str(uuid4()))
    finally:
        with e.transaction() as c:
            c.execute("drop table public.synthetic_unknown_content")


def test_limits_are_configurable_and_never_truncate(content):
    u, e, *_ = content
    e.limits = Limits(max_bytes=1, max_entries=1)
    job = str(uuid4())
    # Fixture may contain no exported row; manifest itself still must fit.
    try:
        e.request(u["account"], job)
    except ContentBlocked as exc:
        assert "limit" in str(exc)
    else:
        e.run_one()
        assert e.status(u["account"], job)["state"] == "blocked"


def test_delete_invalidates_export_without_provider_call(content):
    u, e, _storage, service, actor, doc = content
    job = str(uuid4())
    e.request(u["account"], job)
    e.run_one()
    token = e.authorize(u["account"], job)
    service.call(actor, "challenge", doc)
    service.call(actor, "confirm", {**doc, "confirmation_text": "delete"})
    with pytest.raises(ContentBlocked, match="restricted"):
        b"".join(e.download(u["account"], job, token))
    e.request(u["account"], doc["request_id"], "account")
    e.run_one()
    status = e.status(u["account"], doc["request_id"])
    assert status["state"] == "primary_verified"
    assert status["blockers"] == []
    assert status["progress"]["retained_exceptions"]
    assert u["db"].rows("select count(*) n from privacy_email_suppression") == [
        {"n": 1}
    ]


def test_stale_worker_cannot_publish(content):
    u, e, *_ = content
    job = str(uuid4())
    e.request(u["account"], job)
    first = e.claim()
    u["db"].run(
        f"update privacy_content_jobs set lease_until=clock_timestamp()-interval '1 second' where id='{job}'"
    )
    second = e.claim()
    assert first["lease"] != second["lease"]
    with pytest.raises(ContentBlocked, match="stale_worker"):
        e.build(first)
    e.build(second)
    assert e.status(u["account"], job)["state"] == "ready"


def seed(content):
    u, e, storage, *_ = content
    account, resume, session = u["account"], str(uuid4()), str(uuid4())
    key = f"{account}/{resume}/original.pdf"
    with e.transaction() as c:
        c.execute(
            "insert into profiles(user_id,full_name) values(%s,'Synthetic private name')",
            (account,),
        )
        c.execute(
            "insert into resumes(id,user_id,storage_path,original_filename,confirmed_profile) values(%s,%s,%s,'../../collision.pdf',%s::jsonb)",
            (
                resume,
                account,
                key,
                json.dumps(
                    {"full_name": "Synthetic", "internal_prompt": "DO_NOT_EXPORT"}
                ),
            ),
        )
        for _ in range(2):
            c.execute(
                "insert into resume_chunks(user_id,resume_id,chunk_text,embedding,generation_id) values(%s,%s,'synthetic chunk','[0.123]',%s)",
                (account, resume, str(uuid4())),
            )
        c.execute(
            "insert into interview_sessions(id,user_id,selected_resume_id,title) values(%s,%s,%s,'Synthetic session')",
            (session, account, resume),
        )
        c.execute(
            "insert into interview_session_my_answers(user_id,session_id,body,position) values(%s,%s,'Synthetic saved answer',1)",
            (account, session),
        )
    storage.items["resumes", key] = b"%PDF synthetic only"
    return resume, session, key


def test_populated_export_and_resume_versions(content):
    u, e, storage, *_ = content
    _resume, _session, key = seed(content)
    job = str(uuid4())
    e.request(u["account"], job)
    e.run_one()
    data = b"".join(e.download(u["account"], job, e.authorize(u["account"], job)))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        payload = b"\n".join(
            archive.read(n) for n in archive.namelist() if n.endswith(".json")
        ).decode()
        assert "Synthetic private name" in payload
        assert "Synthetic saved answer" in payload
        assert "DO_NOT_EXPORT" not in payload
        assert "0.123" not in payload
        assert len([n for n in archive.namelist() if "/resume_chunks/" in n]) == 2
        assert archive.read("files/resume-0.bin") == storage.items["resumes", key]


def test_session_cleanup_preserves_reusable_data_and_fences_late_insert(content):
    u, e, storage, *_ = content
    resume, session, key = seed(content)
    job = str(uuid4())
    e.request(u["account"], job, "session", session)
    e.run_one()
    with e.transaction() as c:
        c.execute("select count(*) from resumes where id=%s", (resume,))
        assert c.fetchone()[0] == 1
        c.execute("select count(*) from resume_chunks where resume_id=%s", (resume,))
        assert c.fetchone()[0] == 2
        c.execute(
            "select count(*) from interview_session_my_answers where session_id=%s",
            (session,),
        )
        assert c.fetchone()[0] == 0
    assert ("resumes", key) in storage.items
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "insert into interview_sessions(id,user_id,title) values(%s,%s,'late')",
            (session, u["account"]),
        )


def test_archive_file_change_blocks_publication(content):
    u, e, storage, *_ = content
    _, _, key = seed(content)
    job = str(uuid4())
    e.request(u["account"], job)
    storage.items["resumes", key] = b"changed after cutoff"
    e.run_one()
    assert e.status(u["account"], job)["state"] == "blocked"
    assert not any(bucket == "exports" for bucket, _ in storage.items)


def test_concurrent_claims_and_request_replay(content):
    u, e, *_ = content
    job = str(uuid4())
    e.request(u["account"], job)
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: e.request(u["account"], job), range(2))) == [
            job,
            job,
        ]
        claims = list(pool.map(lambda _: e.claim(), range(2)))
    assert sum(item is not None for item in claims) == 1


def test_native_account_lock_serializes_request_and_writer(content):
    u, e, *_ = content
    writer = e.connect()
    try:
        writer.execute(
            "select id from auth.users where id=%s for no key update", (u["account"],)
        )
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(e.request, u["account"], str(uuid4()), "history")
            # Native pg_locks proves the operation is actually waiting.
            for _ in range(200):
                with e.connect() as observer:
                    waiting = observer.execute(
                        "select count(*) from pg_stat_activity where wait_event_type='Lock' and pid<>pg_backend_pid()"
                    ).fetchone()[0]
                if waiting:
                    break
            assert waiting
            writer.commit()
            pending.result(timeout=10)
    finally:
        writer.close()


def test_wrong_subject_scope_denied(content):
    _u, e, *_ = content
    _, session, _ = seed(content)
    with pytest.raises(ContentBlocked):
        e.request(str(uuid4()), str(uuid4()), "session", session)


def test_export_otp_is_separate_single_use_and_typed_afterward(content):
    from app.auth.supabase_auth import CurrentUser
    from app.privacy_credentials import CredentialBox

    u, e, *_ = content
    user = CurrentUser(
        u["account"],
        u["account"] + "@example.invalid",
        "authenticated",
        {"session_id": str(uuid4()), "app_metadata": {"providers": ["google"]}},
    )
    box = CredentialBox({"synthetic": b"1" * 32}, "synthetic")
    mailbox = []
    job = str(uuid4())
    e.proof(user, job, "begin")
    e.proof(
        user, job, "otp_start", box=box, sender=lambda email, code: mailbox.append(code)
    )
    with pytest.raises(ContentBlocked, match="rate_limited"):
        e.proof(user, job, "otp_start", box=box, sender=lambda *_: None)
    with pytest.raises(ContentBlocked, match="rejected"):
        e.proof(
            user,
            job,
            "otp_verify",
            box=box,
            code="00000000" if mailbox[0] != "00000000" else "11111111",
        )
    e.proof(user, job, "otp_verify", box=box, code=mailbox[0])
    with e.transaction() as c:
        c.execute("select count(*) from privacy_content_jobs where id=%s", (job,))
        assert c.fetchone()[0] == 0  # Verification never requests export itself.
    with pytest.raises(ContentBlocked):
        e.proof(user, job, "otp_verify", box=box, code=mailbox[0])
    e.proof(user, job, "confirm", box=box)
    e.proof(user, job, "confirm", box=box)  # uncertain response recovery
    assert e.status(u["account"], job)["state"] == "pending"
    other = CurrentUser(
        user.user_id, user.email, user.role, {**user.claims, "session_id": str(uuid4())}
    )
    with pytest.raises(ContentBlocked):
        e.download_presence(other, job, box)


def test_api_auth_body_and_download_boundary(content):
    u, e, _storage, _service, actor, _doc = content
    client = u["client"]
    client.app.state.privacy_content_local = e
    headers = {"Authorization": "Bearer " + actor._bearer}
    job = str(uuid4())
    try:
        assert (
            client.post(
                "/api/privacy/content/begin", json={"request_id": job}
            ).status_code
            != 200
        )
        assert (
            client.post(
                "/api/privacy/content/begin",
                json={"request_id": job, "account_id": u["account"]},
                headers=headers,
            ).status_code
            != 200
        )
        assert (
            client.post(
                "/api/privacy/content/begin", json={"request_id": job}, headers=headers
            ).status_code
            == 200
        )
        u["db"].run(
            f"update privacy_export_proofs set started_at=clock_timestamp()-interval '2 seconds' where request_id='{job}'"
        )
        assert (
            client.post(
                "/api/privacy/content/confirm",
                json={"request_id": job, "confirmation_text": "delete"},
                headers=headers,
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/privacy/content/confirm",
                json={"request_id": job, "confirmation_text": "export"},
                headers=headers,
            ).status_code
            == 200
        )
        e.run_one()
        cap = client.post(
            "/api/privacy/content/authorize", json={"request_id": job}, headers=headers
        ).json()["capability"]
        response = client.post(
            "/api/privacy/content/download",
            json={"request_id": job, "capability": cap},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert (
            client.post(
                "/api/privacy/content/download",
                json={"request_id": job, "capability": cap},
                headers=headers,
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/privacy/content/status?capability=forbidden",
                json={"request_id": job},
                headers=headers,
            ).status_code
            == 404
        )
    finally:
        del client.app.state.privacy_content_local


def test_download_stops_after_restriction_without_recalling_delivered_bytes(content):
    u, e, _, service, actor, doc = content
    job = str(uuid4())
    e.request(u["account"], job)
    e.build(e.claim())
    stream = e.download(u["account"], job, e.authorize(u["account"], job))
    delivered = next(stream)
    assert delivered
    service.call(actor, "challenge", doc)
    service.call(actor, "confirm", {**doc, "confirmation_text": "delete"})
    with pytest.raises(ContentBlocked):
        next(stream)
    assert delivered  # Existing bytes still exist at the receiver.


@pytest.mark.parametrize("failure", [PermissionError, ConnectionError])
def test_storage_forbidden_or_unavailable_is_not_absence(content, failure):
    u, e, storage, *_ = content
    seed(content)
    job = str(uuid4())
    e.request(u["account"], job)
    storage.error = failure()
    e.run_one()
    state = e.status(u["account"], job)["state"]
    assert state == ("blocked" if failure is PermissionError else "pending")
    assert not any(bucket == "exports" for bucket, _ in storage.items)


def test_account_cleanup_removes_soft_deleted_resume_and_all_generations(content):
    u, e, storage, service, actor, document = content
    resume, _session, key = seed(content)
    with e.transaction() as c:
        c.execute(
            "update resumes set status='deleted',is_active=false where id=%s", (resume,)
        )
    service.call(actor, "challenge", document)
    service.call(actor, "confirm", {**document, "confirmation_text": "delete"})
    assert e.queue_accepted()
    assert not e.queue_accepted()
    e.run_one()
    state = e.status(u["account"], document["request_id"])
    assert state["state"] == "primary_verified"
    assert state["progress"]["retained_exceptions"]
    receipt_status = service.status(
        {"request_id": document["request_id"], "status_hash": document["status_hash"]}
    )
    assert receipt_status["state"] == "accepted_restricted"
    assert receipt_status["cleanup_state"] == "primary_verified"
    assert receipt_status["primary_content_verified"] is True
    assert receipt_status["retention_obligations"] == "pending"
    assert receipt_status["content_erased"] is False
    with e.transaction() as c:
        c.execute("select count(*) from resume_chunks where resume_id=%s", (resume,))
        assert c.fetchone()[0] == 0
        c.execute("select count(*) from resumes where id=%s", (resume,))
        assert c.fetchone()[0] == 0
        c.execute("select count(*) from profiles where user_id=%s", (u["account"],))
        assert c.fetchone()[0] == 0
        c.execute(
            "select count(*) from account_plan_bindings where account_id=%s",
            (u["account"],),
        )
        assert c.fetchone()[0] == 1
    assert ("resumes", key) not in storage.items


def test_history_cutoff_preserves_new_session_and_old_scope_stays_fenced(content):
    u, e, *_ = content
    _resume, old, _key = seed(content)
    job, new = str(uuid4()), str(uuid4())
    with e.transaction() as c:
        c.execute(
            "update interview_sessions set status='ended',ended_at=clock_timestamp() where id=%s",
            (old,),
        )
    e.request(u["account"], job, "history")
    with e.transaction() as c:
        c.execute(
            "insert into interview_sessions(id,user_id,title) values(%s,%s,'new session')",
            (new, u["account"]),
        )
    e.run_one()
    with e.transaction() as c:
        c.execute("select id from interview_sessions where user_id=%s", (u["account"],))
        assert [str(row[0]) for row in c.fetchall()] == [new]
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "insert into interview_sessions(id,user_id,title,created_at) values(%s,%s,'late old session',clock_timestamp()-interval '1 day')",
            (old, u["account"]),
        )


def test_wrong_account_export_proof_and_expired_code(content):
    from app.auth.supabase_auth import CurrentUser

    u, e, *_ = content
    user = CurrentUser(
        u["account"],
        u["account"] + "@example.invalid",
        "authenticated",
        {"session_id": str(uuid4())},
    )
    job = str(uuid4())
    e.proof(user, job, "begin")
    with e.transaction() as c:
        c.execute(
            "update privacy_export_proofs set expires_at=clock_timestamp()-interval '1 second' where request_id=%s",
            (job,),
        )
    with pytest.raises(ContentBlocked, match="expired"):
        e.proof(user, job, "otp_verify")


def test_indirect_unclassified_child_blocks_export(content):
    u, e, *_ = content
    with e.transaction() as c:
        c.execute(
            "create table public.synthetic_indirect_payload(session_id uuid references interview_sessions(id),body text)"
        )
    try:
        with pytest.raises(ContentBlocked, match="synthetic_indirect_payload"):
            e.request(u["account"], str(uuid4()))
    finally:
        with e.transaction() as c:
            c.execute("drop table public.synthetic_indirect_payload")


def test_session_request_key_cannot_recreate_erased_session(content):
    u, e, *_ = content
    _resume, session, _key = seed(content)
    key = str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into interview_session_idempotency_keys(user_id,idempotency_key,request_hash,status,interview_session_id) values(%s,%s,'synthetic','completed',%s)",
            (u["account"], key, session),
        )
    job = str(uuid4())
    e.request(u["account"], job, "session", session)
    e.run_one()
    with pytest.raises(psycopg.Error), e.transaction() as c:
        c.execute(
            "insert into interview_session_idempotency_keys(user_id,idempotency_key,request_hash) values(%s,%s,'synthetic')",
            (u["account"], key),
        )
    with e.transaction() as c:
        c.execute(
            "select count(*) from privacy_erased_session_keys where account_id=%s",
            (u["account"],),
        )
        assert c.fetchone()[0] == 1


def test_mailbox_download_can_be_reverified_without_new_export(content):
    from app.auth.supabase_auth import CurrentUser
    from app.privacy_credentials import CredentialBox

    u, e, *_ = content
    user = CurrentUser(
        u["account"],
        u["account"] + "@example.invalid",
        "authenticated",
        {"session_id": str(uuid4()), "app_metadata": {"providers": ["google"]}},
    )
    box = CredentialBox({"synthetic": b"1" * 32}, "synthetic")
    mailbox = []
    job = str(uuid4())
    e.proof(user, job, "begin")
    e.proof(
        user, job, "otp_start", box=box, sender=lambda email, code: mailbox.append(code)
    )
    e.proof(user, job, "otp_verify", box=box, code=mailbox[-1])
    e.proof(user, job, "confirm", box=box)
    e.run_one()
    with e.transaction() as c:
        c.execute(
            "update privacy_export_proofs set expires_at=clock_timestamp()-interval '1 second',sent_at=clock_timestamp()-interval '61 seconds' where request_id=%s",
            (job,),
        )
    with pytest.raises(ContentBlocked):
        e.download_presence(user, job, box)
    e.proof(user, job, "download_begin")
    e.proof(
        user, job, "otp_start", box=box, sender=lambda email, code: mailbox.append(code)
    )
    e.proof(user, job, "otp_verify", box=box, code=mailbox[-1])
    e.proof(user, job, "confirm", box=box)
    e.download_presence(user, job, box)
    assert e.status(u["account"], job)["state"] == "ready"


def test_late_artifact_put_is_reconciled_again_after_expiry(content):
    u, e, storage, *_ = content
    job = str(uuid4())
    e.request(u["account"], job)
    e.run_one()
    with e.transaction() as c:
        key = c.execute(
            "select artifact_key from privacy_content_jobs where id=%s", (job,)
        ).fetchone()[0]
        c.execute(
            "update privacy_content_jobs set expires_at=clock_timestamp()-interval '1 second' where id=%s",
            (job,),
        )
    e.expire_one()
    storage.items["exports", key] = b"late uncertain put"
    with e.transaction() as c:
        c.execute(
            "update privacy_content_jobs set retry_at=clock_timestamp() where id=%s",
            (job,),
        )
    e.expire_one()
    assert ("exports", key) not in storage.items
    with pytest.raises(ContentBlocked):
        e.authorize(u["account"], job)


def test_sensitive_nested_settings_blocks_instead_of_silent_omission(content):
    u, e, *_ = content
    with e.transaction() as c:
        c.execute(
            'insert into user_settings(user_id,overlay_settings) values(%s,\'{"access_token":"sensitive"}\')',
            (u["account"],),
        )
    with pytest.raises(ContentBlocked, match="settings_sensitive_field"):
        e.request(u["account"], str(uuid4()))


def test_two_populated_accounts_export_only_their_own_fields(content):
    u, e, *_ = content
    seed(content)
    other = str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
        c.execute(
            "insert into profiles(user_id,full_name) values(%s,'OTHER_ACCOUNT_PRIVATE_SENTINEL')",
            (other,),
        )
    job = str(uuid4())
    e.request(u["account"], job)
    e.run_one()
    with zipfile.ZipFile(
        io.BytesIO(
            b"".join(e.download(u["account"], job, e.authorize(u["account"], job)))
        )
    ) as z:
        assert all(
            b"OTHER_ACCOUNT_PRIVATE_SENTINEL" not in z.read(name)
            for name in z.namelist()
        )
    with pytest.raises(ContentBlocked):
        e.authorize(other, job)


def test_corrupt_nested_parent_is_not_export_authority(content):
    u, e, *_ = content
    other, session = str(uuid4()), str(uuid4())
    with e.transaction() as c:
        c.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (other, other + "@example.invalid"),
        )
        c.execute(
            "insert into interview_sessions(id,user_id,title) values(%s,%s,'other session')",
            (session, other),
        )
        c.execute(
            "insert into interview_session_my_answers(user_id,session_id,body,position) values(%s,%s,'inconsistent ownership',1)",
            (u["account"], session),
        )
    with pytest.raises(ContentBlocked, match="nested_resource_owner_mismatch"):
        e.request(u["account"], str(uuid4()))


def test_nested_screen_projection_keeps_visible_items_only():
    from app.privacy_registry import project_result

    value = {
        "outcome": "answered",
        "items": [
            {
                "question": "Q",
                "answer": "A",
                "code": "print(1)",
                "internal_prompt": "never export",
            }
        ],
        "evidenceDelta": {
            "text": "visible extracted text",
            "imageHashes": ["internal digest"],
        },
        "claim_token": "never export",
    }
    result = project_result(value)
    assert result["items"] == [{"question": "Q", "answer": "A", "code": "print(1)"}]
    assert result["evidenceDelta"] == {"text": "visible extracted text"}
    assert "claim_token" not in result


def test_scoped_proof_cannot_change_target_or_authorize_export(content):
    from app.auth.supabase_auth import CurrentUser
    from app.privacy_credentials import CredentialBox

    u, e, *_ = content
    _, session, _ = seed(content)
    user = CurrentUser(
        u["account"],
        u["account"] + "@example.invalid",
        "authenticated",
        claims={"session_id": str(uuid4()), "app_metadata": {"providers": ["google"]}},
    )
    box = CredentialBox({"local": b"m" * 32}, "local")
    job = str(uuid4())
    mail = []
    begun = e.proof(user, job, "begin", operation_scope="session", resource=session)
    assert type(begun["not_before"]) is int
    with pytest.raises(ContentBlocked, match="proof_scope_mismatch"):
        e.proof(user, job, "begin", operation_scope="history")
    e.proof(
        user,
        job,
        "otp_start",
        box=box,
        sender=lambda _, code: mail.append(code),
        operation_scope="session",
        resource=session,
    )
    with pytest.raises(ContentBlocked, match="proof_scope_mismatch"):
        e.proof(user, job, "otp_verify", box=box, code=mail[0])
    e.proof(
        user,
        job,
        "otp_verify",
        box=box,
        code=mail[0],
        operation_scope="session",
        resource=session,
    )
    e.proof(user, job, "confirm", box=box, operation_scope="session", resource=session)
    with e.transaction() as c:
        assert c.execute(
            "select kind,resource_id from privacy_content_jobs where id=%s", (job,)
        ).fetchone() == ("session", UUID(str(session)))
    assert (
        e.proof(
            user, job, "confirm", box=box, operation_scope="session", resource=session
        )["state"]
        == "requested"
    )
    with pytest.raises(ContentBlocked):
        e.authorize(u["account"], job)


def test_retained_blockers_require_this_subjects_records(content):
    u, e, *_ = content
    with e.transaction() as c:
        columns = e.columns(c)
        exceptions = {}
        own = e.retained_blockers(c, columns, u["account"], exceptions)
        foreign = e.retained_blockers(c, columns, str(uuid4()))
    assert exceptions["account_plan_bindings"] == "usage_recovery"
    assert not any(value.startswith("account_plan_bindings:") for value in own)
    assert not any(value.startswith("account_plan_bindings:") for value in foreign)
    assert not any(value.startswith("billing_evidence:") for value in own)
    assert not any(value.startswith("subscription_payment_receipts:") for value in own)


def test_unknown_private_binding_snapshot_is_not_a_minimized_envelope(content):
    u, e, *_ = content
    with e.transaction() as c:
        c.execute(
            "insert into subscription_binding_history(account_id,revision,document) values(%s,100000,%s::jsonb)",
            (u["account"], json.dumps({"unclassified_private": "SYNTHETIC_PRIVATE"})),
        )
        result = e.retained_blockers(c, e.columns(c), u["account"])
    assert (
        "subscription_binding_history:retained_payload_minimization_not_verified"
        in result
    )
