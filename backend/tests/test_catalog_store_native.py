"""Explicit native runner; normal discovery skips without --pg-bin.

Creates/deletes only a new cluster. Never modifies retained runtime downloads.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.commercial import catalog_store as s
from test_catalog_contract import document

ROOT = Path(__file__).resolve().parents[2]
MANAGER = "10000000-0000-4000-8000-000000000001"
ORDINARY = "10000000-0000-4000-8000-000000000002"
FUNCTIONS = {
    "catalog_adapter_load_draft": "uuid",
    "catalog_adapter_save_draft": "uuid,uuid,bigint,jsonb,text",
    "catalog_adapter_load_snapshot": "uuid",
    "catalog_adapter_archive_snapshot": "uuid,bigint,uuid,bigint,text,text",
}


def literal(value):
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


class Native:
    def __init__(self, pg_bin):
        self.bin = Path(pg_bin).resolve()
        self.env = {
            k: v for k, v in os.environ.items() if not k.upper().startswith("PG")
        }
        self.env.update(
            PGOPTIONS="-c lock_timeout=10000 -c statement_timeout=15000 -c idle_in_transaction_session_timeout=20000 -c standard_conforming_strings=on",
            PGCONNECT_TIMEOUT="5",
            PGCLIENTENCODING="UTF8",
        )
        for name in ["initdb", "pg_ctl", "psql"]:
            assert self.exe(name).is_file()
        self.directory = Path(tempfile.mkdtemp(prefix="c112d-disposable-"))
        self.may_run = False
        self.clients = []
        try:
            with socket.socket() as port:
                port.bind(("127.0.0.1", 0))
                self.port = port.getsockname()[1]
            self.command(
                "initdb",
                [
                    "-D",
                    str(self.directory / "data"),
                    "-U",
                    "catalog_test_owner",
                    "-A",
                    "trust",
                    "--no-locale",
                    "-E",
                    "UTF8",
                ],
            )
            self.may_run = True
            self.command(
                "pg_ctl",
                [
                    "-D",
                    str(self.directory / "data"),
                    "-l",
                    str(self.directory / "server.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {self.port}",
                    "-w",
                    "start",
                ],
            )
            self.args = [
                str(self.exe("psql")),
                "-X",
                "-q",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=sqlstate",
                "-h",
                "127.0.0.1",
                "-p",
                str(self.port),
                "-U",
                "catalog_test_owner",
                "-d",
                "postgres",
            ]
        except BaseException:
            self.close()
            raise

    def exe(self, name):
        return self.bin / (name + (".exe" if os.name == "nt" else ""))

    def command(self, name, args):
        # Windows daemon descendants may retain captured pipe handles. File
        # logging avoids communicate() waiting for a server's pipe EOF.
        with (self.directory / "commands.log").open("ab") as log:
            result = subprocess.run(
                [str(self.exe(name)), *args],
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                timeout=30,
            )
        assert result.returncode == 0, f"disposable {name} failed"

    def run(self, sql, app="c112d-observer"):
        result = subprocess.run(
            self.args,
            input=sql,
            encoding="utf-8",
            capture_output=True,
            timeout=25,
            env={**self.env, "PGAPPNAME": app},
        )
        if result.returncode:
            match = re.search(r"ERROR:\s+([A-Z0-9]{5})", result.stderr)
            raise s.RpcFailure(match[1] if match else None)
        return result.stdout

    def rows(self, sql):
        return json.loads(
            self.run(f"select coalesce(json_agg(q),'[]') from ({sql}) q;")
        )

    def rpc(
        self,
        subject=MANAGER,
        role="authenticated",
        gateway="authenticator",
        app="c112d-rpc",
        after_commit=False,
        rollback=False,
    ):
        assert role in {"authenticated", "anon", "service_role"} and gateway in {
            "authenticator",
            "direct_login",
        }

        def call(name, params):
            # Fixture-only verified-gateway composition; no production actor input.
            assert name in FUNCTIONS and all(
                re.fullmatch(r"p_[a-z_]+", k) for k in params
            )
            args = ",".join(f"{k}=>{literal(v)}" for k, v in params.items())
            sql = f"set session authorization {gateway};set role {role};select set_config('request.jwt.claim.sub',{literal(subject)},false);select jsonb_build_object('result',public.{name}({args}));"
            if rollback:
                sql = "begin;" + sql + "select 1/0;commit;"
            output = self.run(sql, app)
            if after_commit:
                raise s.RpcFailure()
            return json.loads(output.strip().splitlines()[-1])["result"]

        return call

    def barrier(self, sql):
        process = subprocess.Popen(
            self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            env={**self.env, "PGAPPNAME": "c112d-barrier"},
        )
        self.clients.append(process)
        timer = threading.Timer(25, process.kill)
        timer.start()
        self.clients.append(timer)
        process.stdin.write("begin;" + sql + "\n\\echo C112D_READY\n")
        process.stdin.flush()
        while True:
            line = process.stdout.readline()
            assert line, "barrier session failed"
            if line.strip() == "C112D_READY":
                return process

    def release(self, process):
        process.stdin.write("commit;\n")
        process.stdin.close()
        assert process.wait(timeout=15) == 0

    def close(self):
        for client in self.clients:
            if isinstance(client, subprocess.Popen):
                if client.poll() is None:
                    client.kill()
                    client.wait(timeout=5)
            else:
                client.cancel()
        if self.may_run:
            # pg_ctl -w observes the pid-file removal, which can precede the
            # Windows process releasing inherited log handles. Join the exact
            # task-owned postmaster process, rather than retrying filesystem
            # deletion or relaxing database/concurrency timeout assertions.
            handle = None
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                assert (
                    self.directory.parent.resolve()
                    == Path(tempfile.gettempdir()).resolve()
                )
                pid_file = (
                    (self.directory / "data" / "postmaster.pid")
                    .read_text()
                    .splitlines()
                )
                assert (
                    Path(pid_file[1]).resolve() == (self.directory / "data").resolve()
                )
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.OpenProcess.argtypes = [
                    wintypes.DWORD,
                    wintypes.BOOL,
                    wintypes.DWORD,
                ]
                kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel.OpenProcess(0x00100000, False, int(pid_file[0]))
                assert handle, "cannot join disposable postmaster"
            try:
                self.command(
                    "pg_ctl",
                    ["-D", str(self.directory / "data"), "-m", "fast", "-w", "stop"],
                )
                if handle:
                    assert (
                        kernel.WaitForSingleObject(handle, 5000) == 0
                    ), "disposable postmaster did not exit"
            finally:
                if handle:
                    kernel.CloseHandle(handle)
        assert self.directory.parent.resolve() == Path(
            tempfile.gettempdir()
        ).resolve() and self.directory.name.startswith("c112d-disposable-")
        # Windows can release inherited child log handles just after the
        # postmaster exits. Bounded cleanup only; SQL/test deadlines are intact.
        import time

        for attempt in range(20):
            try:
                shutil.rmtree(self.directory)  # Only this new cluster.
                break
            except PermissionError as error:
                if os.name != "nt" or error.winerror != 32 or attempt == 19:
                    raise
                time.sleep(0.05)


@pytest.fixture(scope="module")
def native(request):
    pg_bin = request.config.getoption("--catalog-pg-bin", default=None)
    if not pg_bin:
        pytest.skip("explicit disposable native PostgreSQL runner required")
    db = Native(pg_bin)
    try:
        db.run(f"""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;create role direct_login login noinherit;
        grant anon,authenticated,service_role to authenticator;grant authenticated to direct_login;
        create schema auth;create table auth.users(id uuid primary key);
        create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        grant usage on schema auth,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        insert into auth.users values ({literal(MANAGER)}),({literal(ORDINARY)});
        """)
        for name in [
            "20261022120000_catalog_storage_foundation.sql",
            "20261022150000_catalog_adapter_primitives.sql",
            "20261022180000_subscription_admin_self_probe.sql",
            "20261022200000_catalog_draft_service.sql",
        ]:
            db.run((ROOT / "supabase/migrations" / name).read_text(encoding="utf-8"))
        for name, signature in FUNCTIONS.items():
            metadata = db.rows(
                "select proconfig,prosecdef,pg_get_userbyid(proowner) as owner "
                f"from pg_proc where oid='public.{name}({signature})'::regprocedure"
            )[0]
            assert metadata == dict(
                proconfig=["search_path=pg_catalog"],
                prosecdef=True,
                owner="catalog_test_owner",
            )
            for role in ["anon", "authenticated", "service_role"]:
                assert not db.rows(
                    f"select has_function_privilege('{role}','public.{name}({signature})','EXECUTE') as allowed"
                )[0]["allowed"]
        db.run(
            f"insert into public.subscription_admin_permissions values ({literal(MANAGER)},'subscriptions.manage',1,true,{literal(MANAGER)},'synthetic native test');"
        )
        # Isolated verification grants only; shipped SQL grants nothing.
        for name, signature in FUNCTIONS.items():
            db.run(
                f"grant execute on function public.{name}({signature}) to authenticated;"
            )
        print("native adapter database:", db.rows("select version() as version"))
        yield db
    finally:
        db.close()


@pytest.fixture
def case(native):
    raw = document()
    raw["state"] = "draft"
    raw["draft_id"] = str(uuid4())
    raw["plan"] = {"plan_id": str(uuid4()), "code": "synthetic-" + uuid4().hex}
    raw["terms"]["prices"][0]["price_id"] = str(uuid4())
    native.run(
        f"insert into public.catalog_plans values ({literal(raw['plan']['plan_id'])},{literal(raw['plan']['code'])});"
    )
    native.run(
        f"update public.subscription_admin_permissions set active=true,revision=revision+1,reason='synthetic reset' where subject_id={literal(MANAGER)};"
    )
    return native, s.CatalogStore(native.rpc()), raw


def failure(code, operation):
    with pytest.raises(s.CatalogStoreError) as caught:
        operation()
    assert caught.value.code == code and str(caught.value) == code.value


def count(db, table, field, value):
    return db.rows(
        f"select count(*)::int as n from public.{table} where {field}={literal(value)}"
    )[0]["n"]


def test_native_roundtrip_missing_and_updates(case):
    db, store, raw = case
    failure(s.ErrorCode.NOT_FOUND, lambda: store.load_draft(raw["draft_id"]))
    failure(
        s.ErrorCode.NOT_FOUND,
        lambda: store.save_draft(
            dict(raw, revision=2), expected_revision=1, reason="test"
        ),
    )
    assert store.save_draft(
        raw, expected_revision=0, reason="create"
    ) == store.load_draft(raw["draft_id"])
    raw.update(revision=2, internal_notes="synthetic edit")
    assert store.save_draft(
        raw, expected_revision=1, reason="edit"
    ) == store.load_draft(raw["draft_id"])
    failure(
        s.ErrorCode.CONFLICT,
        lambda: store.save_draft(raw, expected_revision=1, reason="stale"),
    )
    assert count(db, "catalog_admin_actions", "resource_id", raw["draft_id"]) == 2


@pytest.mark.parametrize(
    "identity",
    [
        (ORDINARY, "authenticated", "authenticator"),
        (MANAGER, "service_role", "authenticator"),
        (MANAGER, "authenticated", "direct_login"),
    ],
)
def test_native_identity_and_revocation(case, identity):
    db, store, raw = case
    denied = s.CatalogStore(db.rpc(*identity))
    failure(
        s.ErrorCode.DENIED,
        lambda: denied.save_draft(raw, expected_revision=0, reason="forged"),
    )
    assert count(db, "catalog_drafts", "draft_id", raw["draft_id"]) == 0
    store.save_draft(raw, expected_revision=0, reason="valid")
    db.run(
        f"update public.subscription_admin_permissions set active=false,revision=revision+1,reason='revoke' where subject_id={literal(MANAGER)};"
    )
    failure(
        s.ErrorCode.DENIED,
        lambda: store.save_draft(
            dict(raw, revision=2), expected_revision=1, reason="revoked"
        ),
    )
    failure(s.ErrorCode.DENIED, lambda: store.load_draft(raw["draft_id"]))
    assert count(db, "catalog_admin_actions", "resource_id", raw["draft_id"]) == 1


def test_native_conflicting_adapter_connections(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="create")
    hold = db.barrier(
        f"select 1 from public.catalog_drafts where draft_id={literal(raw['draft_id'])} for update;"
    )

    def edit(index):
        try:
            s.CatalogStore(db.rpc(app=f"c112d-edit-{index}")).save_draft(
                dict(raw, revision=2, internal_notes=f"winner-{index}"),
                expected_revision=1,
                reason="concurrent",
            )
            return "ok"
        except s.CatalogStoreError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(edit, i) for i in range(2)]
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                blocked = db.rows("""with recursive waiting(pid) as (
                  select pid from pg_stat_activity where application_name='c112d-barrier'
                  union select a.pid from pg_stat_activity a join waiting h
                    on h.pid=any(pg_blocking_pids(a.pid)))
                  select count(distinct a.pid)::int as n from pg_stat_activity a
                  join waiting w on a.pid=w.pid
                  where a.application_name in ('c112d-edit-0','c112d-edit-1')""")
                if blocked[0]["n"] == 2:
                    break
                time.sleep(0.02)
            else:
                pytest.fail(
                    "independent adapter connections did not reach lock barrier"
                )
        finally:
            db.release(hold)
        results = [job.result(timeout=15) for job in jobs]
    assert results.count("ok") == 1 and results.count(s.ErrorCode.CONFLICT) == 1
    assert store.load_draft(raw["draft_id"]).internal_notes == (
        f"winner-{results.index('ok')}"
    )
    assert count(db, "catalog_draft_revisions", "draft_id", raw["draft_id"]) == 2
    assert count(db, "catalog_admin_actions", "resource_id", raw["draft_id"]) == 2


def test_native_archive_roundtrip_immutable_hidden(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="source")
    offer = str(uuid4())
    snap = store.archive_snapshot(
        raw["draft_id"],
        expected_revision=1,
        offer_id=offer,
        version=1,
        reason="private archive",
    )
    assert snap == store.load_snapshot(offer)
    assert (
        db.rows(
            "select actor_subject from public.catalog_admin_actions "
            f"where resource_id={literal(offer)}"
        )[0]["actor_subject"]
        == MANAGER
    )
    assert (
        db.rows(
            f"select state from public.catalog_visibility where offer_version_id={literal(offer)}"
        )[0]["state"]
        == "hidden"
    )
    for sql in [
        f"update public.catalog_offer_versions set fingerprint=repeat('0',64) where offer_version_id={literal(offer)}",
        f"delete from public.catalog_price_versions where offer_version_id={literal(offer)}",
    ]:
        with pytest.raises(s.RpcFailure) as e:
            db.run(sql)
        assert e.value.sqlstate == "55000"
    assert store.load_snapshot(offer).fingerprint == snap.fingerprint


def test_native_invalid_input_and_rollback(case):
    db, store, raw = case
    failure(
        s.ErrorCode.INVALID,
        lambda: store.save_draft(
            dict(raw, actor="forged"), expected_revision=0, reason="bad"
        ),
    )
    failure(
        s.ErrorCode.INVALID,
        lambda: s.CatalogStore(db.rpc(rollback=True)).save_draft(
            raw, expected_revision=0, reason="rollback"
        ),
    )
    for table, field in [
        ("catalog_drafts", "draft_id"),
        ("catalog_draft_revisions", "draft_id"),
        ("catalog_admin_actions", "resource_id"),
    ]:
        assert count(db, table, field, raw["draft_id"]) == 0
    store.save_draft(raw, expected_revision=0, reason="source")
    offer = str(uuid4())
    real = db.rpc()

    def audit_fail(name, params):
        if name == "catalog_adapter_archive_snapshot":
            params = dict(params, p_reason="")
        return real(name, params)

    failure(
        s.ErrorCode.INVALID,
        lambda: s.CatalogStore(audit_fail).archive_snapshot(
            raw["draft_id"],
            expected_revision=1,
            offer_id=offer,
            version=1,
            reason="synthetic",
        ),
    )
    for table, field in [
        ("catalog_offer_versions", "offer_version_id"),
        ("catalog_price_versions", "offer_version_id"),
        ("catalog_admin_actions", "resource_id"),
    ]:
        assert count(db, table, field, offer) == 0


def test_native_race_between_validation_and_archive(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="source")
    real = db.rpc()
    offer = str(uuid4())

    def changed(name, params):
        if name == "catalog_adapter_archive_snapshot":
            store.save_draft(
                dict(raw, revision=2), expected_revision=1, reason="intervening edit"
            )
        return real(name, params)

    failure(
        s.ErrorCode.CONFLICT,
        lambda: s.CatalogStore(changed).archive_snapshot(
            raw["draft_id"],
            expected_revision=1,
            offer_id=offer,
            version=1,
            reason="stale source",
        ),
    )
    assert count(db, "catalog_offer_versions", "offer_version_id", offer) == 0


def test_native_corrupt_records(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="source")
    offer = str(uuid4())
    store.archive_snapshot(
        raw["draft_id"],
        expected_revision=1,
        offer_id=offer,
        version=1,
        reason="archive",
    )
    # Maintenance-only corruption injection; no application role can do this.
    db.run(
        f"alter table public.catalog_offer_versions disable trigger immutable_rows;update public.catalog_offer_versions set fingerprint=repeat('0',64) where offer_version_id={literal(offer)};alter table public.catalog_offer_versions enable trigger immutable_rows;"
    )
    failure(s.ErrorCode.STORED_INVALID, lambda: store.load_snapshot(offer))
    corrupt = store.load_draft(raw["draft_id"]).model_dump(mode="json")
    corrupt["revision"] = "2"
    corrupt["terms"] = dict(
        raw["terms"], entitlements=[dict(feature="unknown.capability", allowed=True)]
    )
    db.run(
        f"update public.catalog_drafts set revision=2,document={literal(corrupt)} where draft_id={literal(raw['draft_id'])};"
    )
    failure(s.ErrorCode.STORED_INVALID, lambda: store.load_draft(raw["draft_id"]))


def test_native_permission_outage_and_uncertain_ack(case):
    db, store, raw = case
    db.run(
        "alter table public.subscription_admin_permissions rename to c112d_permission_outage;"
    )
    try:
        failure(
            s.ErrorCode.UNAVAILABLE,
            lambda: store.save_draft(raw, expected_revision=0, reason="outage"),
        )
    finally:
        db.run(
            "alter table public.c112d_permission_outage rename to subscription_admin_permissions;"
        )
    assert count(db, "catalog_drafts", "draft_id", raw["draft_id"]) == 0
    failure(
        s.ErrorCode.UNCERTAIN,
        lambda: s.CatalogStore(db.rpc(after_commit=True)).save_draft(
            raw, expected_revision=0, reason="lost ack"
        ),
    )
    assert store.load_draft(raw["draft_id"]).revision == 1
    assert count(db, "catalog_admin_actions", "resource_id", raw["draft_id"]) == 1


def test_native_unsupported_stored_version(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="source")
    corrupt = store.load_draft(raw["draft_id"]).model_dump(mode="json")
    corrupt["revision"] = "2"
    corrupt["terms"]["prices"][0]["currency_version"] = "future.currency.v2"
    db.run(
        f"update public.catalog_drafts set revision=2,document={literal(corrupt)} "
        f"where draft_id={literal(raw['draft_id'])};"
    )
    failure(s.ErrorCode.STORED_INVALID, lambda: store.load_draft(raw["draft_id"]))


def test_native_revoke_between_read_and_archive(case):
    db, store, raw = case
    store.save_draft(raw, expected_revision=0, reason="source")
    real = db.rpc()
    offer = str(uuid4())

    def revoke(name, params):
        if name == "catalog_adapter_archive_snapshot":
            db.run(
                "update public.subscription_admin_permissions set active=false,"
                "revision=revision+1,reason='between calls' "
                f"where subject_id={literal(MANAGER)};"
            )
        return real(name, params)

    failure(
        s.ErrorCode.DENIED,
        lambda: s.CatalogStore(revoke).archive_snapshot(
            raw["draft_id"],
            expected_revision=1,
            offer_id=offer,
            version=1,
            reason="test",
        ),
    )
    assert count(db, "catalog_offer_versions", "offer_version_id", offer) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    arguments = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=arguments.pg_bin)

    raise SystemExit(
        pytest.main(
            [__file__, "-q", "-s", "-p", "no:cacheprovider", "--tb=short"],
            plugins=[Options()],
        )
    )
