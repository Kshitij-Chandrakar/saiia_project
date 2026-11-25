"""No remote parameters: the staging application harness on disposable PostgreSQL."""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import jwt
import psycopg
import smoke_staging_session_pooler  # disables dotenv before application imports
from app.commercial.executor_connection import EXECUTORS
from staging_application_acceptance import ApplicationAcceptance
from test_catalog_store_native import ROOT, Native


class NativeAuth:
    key = "local-only-application-jwt-key-at-least-32-bytes"

    def __init__(self, db):
        self.db, self.subjects = db, {}
        fixture = self

        class Probe(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/rest/v1/rpc/subscription_admin_self_probe":
                    self.send_error(404)
                    return
                token = self.headers["Authorization"].split(" ")[1]
                subject = jwt.decode(
                    token, fixture.key, algorithms=["HS256"], audience="authenticated"
                )["sub"]
                with psycopg.connect(
                    host="127.0.0.1",
                    port=fixture.db.port,
                    dbname="postgres",
                    user="authenticator",
                ) as conn:
                    conn.execute("SET LOCAL ROLE authenticated")
                    conn.execute(
                        "SELECT set_config('request.jwt.claim.sub',%s,true)", (subject,)
                    )
                    data = conn.execute(
                        "SELECT subscription_admin_self_probe()"
                    ).fetchone()[0]
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Probe)
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def connect(self):
        return psycopg.connect(
            host="127.0.0.1",
            port=self.db.port,
            dbname="postgres",
            user="catalog_test_owner",
            autocommit=True,
        )

    def preflight(self):
        pass

    def create(self, name, _password, _run):
        subject = str(uuid4())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO auth.users(id,email,email_confirmed_at) VALUES(%s,%s,clock_timestamp())",
                (subject, "c132-staging-" + name + "@acceptance.invalid"),
            )
        self.subjects[name] = subject
        return subject

    def sign_in(self, name, _password):
        return jwt.encode(
            {
                "sub": self.subjects[name],
                "aud": "authenticated",
                "role": "authenticated",
                "iss": "https://synthetic.invalid/auth/v1",
                "exp": int(time.time()) + 3600,
            },
            self.key,
            algorithm="HS256",
        )

    def sign_out(self, _token):
        pass

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def check(pg_bin, fault_worker=False):
    assert smoke_staging_session_pooler.DEADLINE.tzinfo is not None
    db = Native(pg_bin)
    owner = auth = None
    try:
        # The accepted platform-interface fixture, only in a fresh loopback cluster.
        db.run("""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;grant authenticated to authenticator;
        create schema auth;create schema storage;create schema extensions;
        create table auth.users(id uuid primary key,created_at timestamptz default now(),email_confirmed_at timestamptz,email text);
        create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        create function auth.role() returns text language sql stable as $$select current_setting('request.jwt.claim.role',true)$$;
        create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
        create table storage.objects(id uuid primary key,bucket_id text,name text);
        alter table storage.objects enable row level security;
        create function storage.foldername(text) returns text[] language sql as $$select string_to_array($1,'/')$$;
        grant usage on schema auth,storage,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        """)
        db.run(
            (
                ROOT
                / "docs/sql/C11_C13_STAGING_cfmvqbjmnwklxqlpelxe_APPLICATION_PENDING_APPROVAL.sql"
            ).read_text()
        )
        for role in EXECUTORS:
            db.run("ALTER ROLE " + role + " LOGIN")
        auth = NativeAuth(db)
        from app.auth import supabase_auth

        supabase_auth.get_auth_verification_config = (
            lambda: supabase_auth.AuthVerificationConfig(
                "legacy_secret",
                auth.key,
                "https://synthetic.invalid/auth/v1",
                "authenticated",
            )
        )
        owner = auth.connect()
        path = ROOT / (
            "tmp/c132-application-native-failure-state.json"
            if fault_worker
            else "tmp/c132-application-native-state.json"
        )
        if path.exists():
            path.replace(path.with_name("c132-application-native-previous.json"))
        application = ApplicationAcceptance(
            Path("unused-local-ca"),
            uuid4(),
            "synthetic-public-key",
            "",
            auth=auth,
            local_port=db.port,
            evidence=path,
        )
        application.auth_preflight()
        if fault_worker:
            from staging_application_acceptance import AcceptanceFailure

            def fail_worker(_):
                raise AcceptanceFailure("synthetic_worker_startup_failure")

            application.start_worker = fail_worker
            try:
                application(owner, {})
            except AcceptanceFailure as error:
                assert str(error) == "synthetic_worker_startup_failure"
            else:
                raise AssertionError("fault did not run")
            assert (
                application.state["failure"]["stage"] == "start_two_application_workers"
            )
            assert (
                application.state["workers_stopped"]
                and not application.state["cleanup_errors"]
            )
            assert (
                owner.execute(
                    "SELECT count(*) FROM subscription_admin_permissions WHERE active"
                ).fetchone()[0]
                == 0
            )
            print(
                "PASS: injected worker-startup failure revoked admin/configuration and completed application cleanup"
            )
            return
        result = application(owner, {})
        assert len(result["passed"]) == 11 and result["workers_stopped"]
        assert not result["cleanup_errors"]
        assert (
            owner.execute(
                "SELECT count(*) FROM subscription_admin_permissions WHERE active"
            ).fetchone()[0]
            == 0
        )
        assert (
            owner.execute("SELECT count(*) FROM subscription_configuration").fetchone()[
                0
            ]
            == 0
        )
        print(
            "PASS: actual two-worker application harness; catalog/JWT/ownership/upgrade/quotas/replay/worker-death recovery and fixture cleanup"
        )
    finally:
        if auth is not None:
            auth.close()
        if owner is not None:
            owner.close()
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--fault-worker-startup", action="store_true")
    args = parser.parse_args()
    check(args.pg_bin, args.fault_worker_startup)
