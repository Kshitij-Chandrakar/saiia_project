"""Explicit isolated actual-engine rehearsal. Never reads project dotenv/DSNs."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import smtplib
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

import jwt
import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "db": "postgres:17.11",
    "auth": "supabase/gotrue:v2.197.0",
    "mail": "axllent/mailpit:v1.27.11",
    "storage": "supabase/storage-api:v1.81.0",
    "rest": "postgrest/postgrest:v14.18",
}


def docker(*args, data=None, check=True):
    r = subprocess.run(
        ["docker", *args],
        input=data,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if check and r.returncode:
        detail = re.sub(r"password '[^']*'", "password '[REDACTED]'", r.stderr)
        detail = re.sub(r"postgres(?:ql)?://[^@]+@", "postgres://[REDACTED]@", detail)
        print(detail[:1000], flush=True)
        raise RuntimeError("docker_operation_failed:" + args[0])
    return r


class Rehearsal:
    key_lifetime_seconds = 7200

    def __init__(self, evidence, internal=False):
        self.internal = internal
        self.out = evidence
        self.out.mkdir(parents=True, exist_ok=internal)
        self.name = "c15-actual-" + uuid4().hex[:10]
        self.secret = secrets.token_urlsafe(48)
        self.password = secrets.token_urlsafe(24)
        self.results = []
        self.created = []
        self.volumes = []
        self.sql_errors = []
        self.ports = {
            "db": 5432,
            "auth": 9999,
            "storage": 5000,
            "rest": 3000,
            "mail": 8025,
            "smtp": 1025,
        }
        self.http = requests.Session()
        self.http.trust_env = False
        self.anon = self.key("anon")
        self.service = self.key("service_role")
        self.images = {}
        if internal:
            d = json.loads(os.environ["C15_ISOLATED_CONFIG"])
            self.secret, self.password, self.name = (
                d["secret"],
                d["password"],
                d["name"],
            )
            self.ports = {
                "db": 5432,
                "auth": 9999,
                "storage": 5000,
                "rest": 3000,
                "mail": 8025,
                "smtp": 1025,
            }
            self.anon = self.key("anon")
            self.service = self.key("service_role")

    def url(self, service):
        return (
            f"http://{service if self.internal else '127.0.0.1'}:{self.ports[service]}"
        )

    def key(self, role):
        return jwt.encode(
            {
                "role": role,
                "iss": "supabase",
                "iat": int(time.time()),
                "exp": int(time.time()) + self.key_lifetime_seconds,
            },
            self.secret,
            algorithm="HS256",
        )

    def save(self, name, value):
        (self.out / name).write_text(
            json.dumps(value, indent=2, default=str), encoding="utf-8"
        )

    def sql(self, statement, params=None, role="postgres"):
        with self.connect(role) as c:
            return (
                c.execute(statement, params).fetchall()
                if statement.lstrip().lower().startswith("select")
                else c.execute(statement, params)
            )

    def connect(self, role="postgres"):
        owner = self

        class SafeCursor(psycopg.Cursor):
            def execute(self, *a, **kw):
                try:
                    return super().execute(*a, **kw)
                except psycopg.Error as error:
                    match = re.search(
                        r"permission denied for (?:schema|table|function) ([A-Za-z_][A-Za-z0-9_]*)",
                        error.diag.message_primary or "",
                    )
                    owner.sql_errors.append(
                        {
                            "sqlstate": error.sqlstate,
                            "table": error.diag.table_name,
                            "column": error.diag.column_name,
                            "permission_target": match.group(1) if match else None,
                        }
                    )
                    raise

        return psycopg.connect(
            host="db" if self.internal else "127.0.0.1",
            port=self.ports["db"],
            dbname="postgres",
            user=role,
            password=self.password,
            connect_timeout=3,
            cursor_factory=SafeCursor,
        )

    def run(self, service, env, extra=(), container_port=None):
        name = self.name + "-" + service
        args = [
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "c15.rehearsal=" + self.name,
            "--network",
            self.name,
            "--network-alias",
            service,
        ]
        for k, v in env.items():
            args += ["-e", k + "=" + str(v)]
        args += list(extra) + [self.images[service]]
        self.created.append(name)
        docker(*args)

    def wait(self, service, endpoint):
        until = time.monotonic() + 60
        while time.monotonic() < until:
            try:
                if (
                    self.http.get(self.url(service) + endpoint, timeout=2).status_code
                    == 200
                ):
                    return
            except requests.RequestException:
                pass
            time.sleep(0.3)
        if self.internal:
            raise RuntimeError(service + "_startup_failed")
        logs = docker("logs", self.name + "-" + service, check=False).stderr
        logs += docker("logs", self.name + "-" + service, check=False).stdout
        for value in [self.secret, self.password, self.anon, self.service]:
            logs = logs.replace(value, "[REDACTED]")
        logs = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[EMAIL]", logs)
        (self.out / (service + "-startup.txt")).write_text(logs, encoding="utf-8")
        raise RuntimeError(service + "_startup_failed")

    def setup(self):
        for s, image in IMAGES.items():
            d = json.loads(docker("image", "inspect", image).stdout)[0]
            self.images[s] = d["RepoDigests"][0]
        self.save("images.json", self.images)
        runner = json.loads(
            docker("image", "inspect", "c15-engine-runner:20261101").stdout
        )[0]
        self.runner = runner["Id"]
        self.save(
            "runner-image.json",
            {
                "image_id": self.runner,
                "build_labels": runner["Config"].get("Labels"),
                "dockerfile_sha256": hashlib.sha256(
                    (ROOT / "scripts/c15_rehearsal.Dockerfile").read_bytes()
                ).hexdigest(),
            },
        )
        docker(
            "network",
            "create",
            "--internal",
            "--label",
            "c15.rehearsal=" + self.name,
            self.name,
        )
        for s in ("db", "storage"):
            v = self.name + "-" + s
            docker("volume", "create", "--label", "c15.rehearsal=" + self.name, v)
            self.volumes.append(v)
        self.run(
            "db",
            {"POSTGRES_PASSWORD": self.password},
            ["-v", self.name + "-db:/var/lib/postgresql/data"],
            5432,
        )
        until = time.monotonic() + 45
        while time.monotonic() < until:
            if (
                docker(
                    "exec",
                    self.name + "-db",
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                    check=False,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.2)
        bootstrap = """create role anon nologin;create role authenticated nologin;create role service_role nologin bypassrls;
        create role authenticator login noinherit;grant anon,authenticated,service_role to authenticator;
        create role supabase_auth_admin login noinherit;create schema auth authorization supabase_auth_admin;
        create schema extensions;create extension pgcrypto with schema extensions;
        grant usage on schema public,auth to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        create function auth.uid() returns uuid language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub'))::uuid$$;
        create function auth.role() returns text language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claim.role',true),''),(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role'))$$;
        """
        bootstrap += "alter function auth.uid() owner to supabase_auth_admin;alter function auth.role() owner to supabase_auth_admin;"
        bootstrap += f"alter role authenticator password '{self.password}';alter role supabase_auth_admin password '{self.password}';alter role supabase_auth_admin set search_path=auth;"
        docker(
            "exec",
            "-i",
            self.name + "-db",
            "psql",
            "-U",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            data=bootstrap,
        )
        self.run(
            "mail",
            {
                "MP_DISABLE_VERSION_CHECK": "true",
                "MP_SMTP_BIND_ADDR": "0.0.0.0:1025",
                "MP_UI_BIND_ADDR": "0.0.0.0:8025",
            },
            container_port=8025,
        )

        # Hook functions are installed after actual Auth/Storage engine migrations.
        self.auth_env = {
            "GOTRUE_API_HOST": "0.0.0.0",
            "GOTRUE_API_PORT": "9999",
            "API_EXTERNAL_URL": "http://auth:9999",
            "GOTRUE_SITE_URL": "http://127.0.0.1:5396",
            "GOTRUE_DB_DRIVER": "postgres",
            "GOTRUE_DB_DATABASE_URL": f"postgres://supabase_auth_admin:{self.password}@db:5432/postgres",
            "GOTRUE_JWT_SECRET": self.secret,
            "GOTRUE_JWT_ISSUER": "http://auth:9999/auth/v1",
            "GOTRUE_JWT_DEFAULT_GROUP_NAME": "authenticated",
            "GOTRUE_JWT_AUD": "authenticated",
            "GOTRUE_JWT_ADMIN_ROLES": "service_role",
            "GOTRUE_JWT_EXP": "3600",
            "GOTRUE_EXTERNAL_EMAIL_ENABLED": "true",
            "GOTRUE_MAILER_AUTOCONFIRM": "false",
            "GOTRUE_SMTP_HOST": "mail",
            "GOTRUE_SMTP_PORT": "1025",
            "GOTRUE_SMTP_ADMIN_EMAIL": "system@example.invalid",
            "GOTRUE_SMTP_SENDER_NAME": "C15 isolated rehearsal",
            "GOTRUE_SMTP_MAX_FREQUENCY": "1s",
            "GOTRUE_RATE_LIMIT_EMAIL_SENT": "1000",
            "GOTRUE_RATE_LIMIT_TOKEN_REFRESH": "1000",
            "GOTRUE_EXTERNAL_GOOGLE_ENABLED": "false",
            "GOTRUE_MFA_TOTP_ENROLL_ENABLED": "true",
            "GOTRUE_MFA_TOTP_VERIFY_ENABLED": "true",
            "GOTRUE_LOG_LEVEL": "error",
        }
        self.run("auth", self.auth_env, container_port=9999)
        self.run(
            "rest",
            {
                "PGRST_DB_URI": f"postgres://authenticator:{self.password}@db:5432/postgres",
                "PGRST_DB_SCHEMAS": "public,storage",
                "PGRST_DB_ANON_ROLE": "anon",
                "PGRST_JWT_SECRET": self.secret,
            },
            container_port=3000,
        )
        self.run(
            "storage",
            {
                "ANON_KEY": self.anon,
                "SERVICE_KEY": self.service,
                "POSTGREST_URL": "http://rest:3000",
                "AUTH_JWT_SECRET": self.secret,
                "DATABASE_URL": f"postgres://postgres:{self.password}@db:5432/postgres",
                "DB_INSTALL_ROLES": "true",
                "STORAGE_BACKEND": "file",
                "FILE_STORAGE_BACKEND_PATH": "/var/lib/storage",
                "TENANT_ID": "c15-local",
                "REGION": "local-test-only",
                "GLOBAL_S3_BUCKET": "c15-local",
                "FILE_SIZE_LIMIT": "10485760",
                "ENABLE_IMAGE_TRANSFORMATION": "false",
                "STORAGE_PUBLIC_URL": "http://storage:5000",
            },
            ["-v", self.name + "-storage:/var/lib/storage"],
            5000,
        )
        net = json.loads(docker("network", "inspect", self.name).stdout)[0]
        assert net["Internal"] is True and net["EnableIPv6"] is False
        inspected = []
        for name in self.created:
            cfg = json.loads(docker("inspect", name).stdout)[0]
            assert not cfg["HostConfig"]["PortBindings"]
            assert set(cfg["NetworkSettings"]["Networks"]) == {self.name}
            inspected.append(
                {
                    "name": name,
                    "published_ports": False,
                    "only_owned_internal_network": True,
                }
            )
        routes = docker("exec", self.name + "-auth", "cat", "/proc/net/route").stdout
        assert not any(
            line.split()[1] == "00000000"
            for line in routes.splitlines()[1:]
            if line.split()
        )
        self.save(
            "network-proof.json",
            {
                "services": inspected,
                "no_ipv4_default_route": True,
                "ipv6_disabled": True,
            },
        )
        self.save(
            "isolation.json",
            {
                "internal_network": True,
                "published_ports": [],
                "external_smtp": False,
                "google": False,
                "network": self.name,
            },
        )

    def install(self):
        for service, endpoint in [
            ("auth", "/health"),
            ("storage", "/status"),
            ("mail", "/api/v1/messages"),
        ]:
            self.wait(service, endpoint)
        with self.connect() as c:
            c.execute(
                "create or replace function auth.uid() returns uuid language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub'))::uuid$$;create or replace function auth.role() returns text language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claim.role',true),''),(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'role'))$$"
            )
        applied = []
        for file in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            if "20261029010000" <= file.name < "20261030120000":
                continue
            try:
                with self.connect() as c:
                    c.execute(file.read_text(encoding="utf-8"))
            except psycopg.Error as error:
                self.save(
                    "migration-failure.json",
                    {
                        "file": file.name,
                        "sqlstate": error.sqlstate,
                        "message": error.diag.message_primary,
                    },
                )
                raise RuntimeError("local_migration_failed:" + file.name) from None
            applied.append(file.name)
            if file.name.startswith("20261027010000"):
                from c15_auth_package import supported_sql

                with self.connect() as c:
                    c.execute(supported_sql(ROOT))
                applied.append("C15_SUPPORTED_AUTH_PACKAGE_PENDING.sql (generator)")
        self.save("migrations.json", applied)
        import importlib.metadata

        self.save(
            "runner-packages.json",
            {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        )
        self.save(
            "database-contract.json",
            {
                "server": self.sql("select version()")[0][0],
                "schema_migrations_applied": len(applied),
                "managed_auth": "actual Auth migrations",
                "managed_storage": "actual Storage migrations",
                "fixture_auth_helpers": "standard self-hosted request JWT GUC helpers; no Auth-table triggers",
            },
        )
        with self.connect() as c:
            c.execute("alter role usage_executor login")
            c.execute(
                psycopg.sql.SQL("alter role usage_executor password {}").format(
                    psycopg.sql.Literal(self.password)
                )
            )
            c.execute(
                "insert into privacy_matching_keys values(1,%s,true)",
                (secrets.token_bytes(32),),
            )
            c.execute("update privacy_configuration set enabled=true")
            c.execute("notify pgrst, 'reload schema'")

    def auth(self, path, method="POST", body=None, token=None):
        return self.http.request(
            method,
            "http://auth:9999" + path,
            json=body,
            headers={
                "Authorization": "Bearer " + (token or self.service),
                "apikey": self.anon,
            },
            timeout=10,
        )

    def user(self):
        email = uuid4().hex + "@example.invalid"
        r = self.auth(
            "/admin/users",
            body={"email": email, "password": self.password, "email_confirm": True},
        )
        assert r.status_code == 200, "actual_admin_fixture_creation_failed"
        u = r.json()
        session = self.login(email)
        return {"id": u["id"], "email": email, **session}

    def login(self, email):
        r = self.auth(
            "/token?grant_type=password",
            body={"email": email, "password": self.password},
        )
        if r.status_code != 200:
            self.save(
                "auth-error.json",
                {
                    "status": r.status_code,
                    "code": r.json().get("error_code"),
                    "message": "redacted",
                },
            )
        assert r.status_code == 200, "actual_password_login_failed"
        return r.json()

    def scenario(self, name, fn):
        try:
            fn()
            self.results.append(
                {
                    "scenario": name,
                    "result": "passed",
                    "boundary": "actual local engine",
                }
            )
        except Exception as error:  # noqa: BLE001 -- safe scenario categories; cleanup must always run
            self.results.append(
                {
                    "scenario": name,
                    "result": "failed",
                    "error_type": type(error).__name__,
                    "safe_category": str(error)
                    if isinstance(error, RuntimeError)
                    else None,
                    "stack": [
                        {
                            "file": Path(t.filename).name,
                            "line": t.lineno,
                            "function": t.name,
                        }
                        for t in __import__("traceback").extract_tb(error.__traceback__)
                    ],
                }
            )
            self.save("results.json", self.results)
            print(name + ": FAILED (" + type(error).__name__ + ")", flush=True)
            return False
        self.save("results.json", self.results)
        print(name + ": passed", flush=True)

    def scenarios(self):
        u = self.user()
        self.save(
            "engine-boot.json",
            {
                "auth": self.auth("/health", method="GET").json(),
                "password_signed_in": bool(u.get("access_token")),
            },
        )
        self.scenario(
            "actual_password_login_and_signed_hook_token", lambda: self.assert_claims(u)
        )
        self.configure_app()
        self.scenario("public_signup_confirmation_caught_locally", self.signup_mail)
        self.scenario("actual_totp_and_refresh_only_presence", self.totp)
        self.scenario(
            "application_mailbox_otp_binding_limits_and_typed_confirmation",
            self.mailbox,
        )
        self.scenario(
            "mailbox_expiry_resend_attempt_limits_and_session_recovery",
            self.mailbox_edges,
        )
        self.scenario(
            "separate_export_deletion_mailbox_proofs_actual_delivery",
            self.export_proofs,
        )
        self.scenario(
            "actual_storage_rls_export_expiry_and_cleanup", self.storage_export
        )
        self.scenario(
            "durable_cleanup_actual_bytes_crash_retry_and_stale_lease",
            self.durable_storage,
        )
        self.scenario(
            "actual_deletion_suppression_revocation_and_old_tokens", self.deletion
        )
        self.scenario(
            "revocation_restart_key_outage_expiry_and_uncertain_response",
            self.revocation_recovery,
        )
        self.scenario(
            "email_change_linking_and_privileged_identity_boundaries",
            self.identity_boundaries,
        )
        self.scenario(
            "suppression_dependencies_credentials_and_timeout_fail_closed",
            self.hook_failures,
        )
        self.scenario("controlled_provisioning_suppression", self.provisioning)
        self.scenario(
            "authoritative_session_absence_recovers_lost_ack",
            self.revocation_observation,
        )
        self.scenario("supported_auth_soft_delete_recovery", self.soft_delete_recovery)
        self.scenario(
            "normal_identity_cleanup_after_successful_logout",
            self.identity_cleanup_normal,
        )
        self.client.close()
        if any(x["result"] == "failed" for x in self.results):
            raise RuntimeError("actual_scenarios_failed")

    def identity_cleanup_normal(self):
        from app.email.event_store import OutboundEmailEventService
        from app.email.service import EmailService
        from app.privacy_content import ContentEngine
        from app.privacy_credentials import (
            CredentialBox,
            GlobalLogout,
            PrivateAuthAdmin,
        )
        from app.privacy_identity import IdentityCleanupWorker
        from app.privacy_notifications import PrivacyNotifier
        from app.privacy_revocation import RevocationWorker, SessionRevocationObserver
        from app.privacy_runtime import LocalCatcher, PrivateEvents
        from app.privacy_runtime_db import RuntimeConnection

        with self.connect() as c:
            for role in [
                "privacy_identity_executor",
                "privacy_content_executor",
                "privacy_revocation_observer",
            ]:
                c.execute(
                    psycopg.sql.SQL("alter role {} login password {}").format(
                        psycopg.sql.Identifier(role), psycopg.sql.Literal(self.password)
                    )
                )
            c.execute(
                "update privacy_followup_tasks set due_at=clock_timestamp()+interval '1 day' where kind in ('revoke_sessions','identity_cleanup')"
            )
        for role in [
            "privacy_identity_executor",
            "privacy_content_executor",
            "privacy_revocation_observer",
            "usage_executor",
        ]:
            for statement in [
                "select * from auth.users",
                "delete from auth.users",
                "truncate auth.users",
                "set role privacy_identity_owner",
                "select * from privacy_followup_tasks",
            ]:
                try:
                    with self.connect(role) as c:
                        c.execute(statement)
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("identity_direct_privilege_admitted")
        subject, doc = self.accepted_password()
        unaffected = self.user()
        observer = SessionRevocationObserver(
            lambda: self.connect("privacy_revocation_observer")
        )
        worker = RevocationWorker(lambda: self.connect("usage_executor"))
        task = worker.call("claim", {"lease_id": str(uuid4())})
        assert task["account_id"] == subject["id"]
        # RLS-hidden rows must never masquerade as authoritative absence.
        assert observer(task) is False
        logout = GlobalLogout(
            CredentialBox.configured(),
            self.url("auth"),
            self.anon,
            self.http.post,
            local_rehearsal=True,
            standalone=True,
        )
        assert logout(task, worker.call("credential", task)) == "succeeded"
        assert observer(task) is True
        worker.call("finish", {**task, "outcome": "succeeded"})
        admin = PrivateAuthAdmin(
            self.url("auth"), self.service, local_rehearsal=True, standalone=True
        )
        identity = IdentityCleanupWorker(
            lambda: self.connect("privacy_identity_executor"), admin
        )
        assert identity.run_one() is False  # required notice still absent
        assert admin.get_user(subject["id"])["email"] == subject["email"]
        engine = ContentEngine(
            lambda: RuntimeConnection(
                self.connect("privacy_content_executor"), "privacy_content_executor"
            ),
            self.store,
            local_rehearsal=True,
        )
        notifier = PrivacyNotifier(
            engine,
            EmailService(
                LocalCatcher("mail", 1025),
                event_store=OutboundEmailEventService(
                    client=PrivateEvents(
                        lambda: self.connect("privacy_content_executor")
                    )
                ),
            ),
        )
        assert notifier.notify(subject["id"], "accepted").event_status == "sent"

        def due():
            with self.connect() as c:
                c.execute(
                    "update privacy_followup_tasks set due_at=clock_timestamp()-interval '1 second' where request_id=%s and kind='identity_cleanup'",
                    (doc["request_id"],),
                )

        due()

        class Outage:
            def soft_delete(self, _account):
                raise requests.Timeout()

        assert IdentityCleanupWorker(
            lambda: self.connect("privacy_identity_executor"), Outage()
        ).run_one()
        assert admin.get_user(subject["id"])["email"] == subject["email"]
        due()
        live = identity.call("claim", {"lease_id": str(uuid4())})
        try:
            identity.call("verify", {**live, "account_id": unaffected["id"]})
        except psycopg.Error:
            pass
        else:
            raise AssertionError("foreign_identity_scope_admitted")
        try:
            identity.call("finish", {**live, "lease_id": str(uuid4())})
        except psycopg.Error:
            pass
        else:
            raise AssertionError("stale_identity_lease_admitted")
        identity.call("finish", live)  # no absence yet: pending, never success
        due()

        class LostAck:
            def soft_delete(self, account):
                assert account == subject["id"] and admin.soft_delete(account)
                raise requests.Timeout()

        assert IdentityCleanupWorker(
            lambda: self.connect("privacy_identity_executor"), LostAck()
        ).run_one()
        with self.connect() as c:
            checks = c.execute(
                "select deleted_at is not null,raw_user_meta_data='{}',raw_app_meta_data='{}',position('@' in email)>0,(select count(*) from auth.sessions where user_id=u.id),(select count(*) from auth.identities where user_id=u.id),(select count(*) from auth.mfa_factors where user_id=u.id) from auth.users u where id=%s",
                (subject["id"],),
            ).fetchone()
            self.save(
                "identity-absence-checks.json",
                {
                    "checks": checks,
                    "state": c.execute(
                        "select state,safe_error from privacy_followup_tasks where request_id=%s and kind='identity_cleanup'",
                        (doc["request_id"],),
                    ).fetchone(),
                },
            )
            assert (
                c.execute(
                    "select state from privacy_followup_tasks where request_id=%s and kind='identity_cleanup'",
                    (doc["request_id"],),
                ).fetchone()[0]
                == "succeeded"
            )
            assert (
                c.execute(
                    "select count(*) from auth.sessions where user_id=%s",
                    (unaffected["id"],),
                ).fetchone()[0]
                > 0
            )
        assert admin.get_user(subject["id"])["email"] != subject["email"]
        assert self.login(unaffected["email"])["access_token"]
        assert (
            self.auth(
                "/token?grant_type=password",
                body={"email": subject["email"], "password": self.password},
            ).status_code
            != 200
        )
        receipt = self.client.post(
            "/api/privacy/deletion/status",
            json={"request_id": doc["request_id"], "status_token": doc["status_token"]},
        )
        assert (
            receipt.status_code == 200
            and receipt.json()["identity_cleanup"] == "succeeded"
            and receipt.json()["content_erased"] is False
        )
        # A genuine financial linkage retains restricted contact, never product access.
        billed, billdoc = self.accepted_password()
        with self.connect() as c:
            c.execute(
                "insert into subscription_payment_receipts(event_id,account_id,semantic_hash,result) values(%s,%s,%s,'{}')",
                (str(uuid4()), billed["id"], "a" * 64),
            )
        billtask = worker.call("claim", {"lease_id": str(uuid4())})
        assert billtask["account_id"] == billed["id"]
        assert logout(billtask, worker.call("credential", billtask)) == "succeeded"
        assert observer(billtask) is True
        worker.call("finish", {**billtask, "outcome": "succeeded"})
        assert identity.run_one() is False
        with self.connect() as c:
            assert c.execute(
                "select state,safe_error from privacy_followup_tasks where request_id=%s and kind='identity_cleanup'",
                (billdoc["request_id"],),
            ).fetchone() == ("blocked", "billing_contact_required")
        assert admin.get_user(billed["id"])["email"] == billed["email"]
        self.save(
            "identity-cleanup.json",
            {
                "normal_logout_verified_separately": True,
                "active_sessions_observed_before_logout": True,
                "notice_dependency": True,
                "outage_retry": True,
                "wrong_subject_and_stale_lease_denied": True,
                "lost_ack_authoritative_absence": True,
                "unaffected_login": True,
                "private_principals": True,
                "full_erasure_claim": False,
                "direct_role_denial": True,
                "billing_contact_exception": True,
            },
        )

    def soft_delete_recovery(self):
        from app.email.event_store import (
            OutboundEmailEventService,
            SupabaseOutboundEmailEventClient,
        )
        from app.email.provider import EmailSendResult, utc_timestamp
        from app.email.service import EmailService
        from app.privacy_credentials import AuthSoftDeleteRecovery, PrivateAuthAdmin
        from app.privacy_notifications import PrivacyNotifier
        from app.privacy_revocation import RevocationWorker, SessionRevocationObserver

        u, doc = self.accepted_password()
        other = self.user()
        with self.connect() as c:
            c.execute(
                "update privacy_followup_tasks set state='blocked',lease_id=null,lease_until=null where kind='revoke_sessions' and request_id<>%s",
                (doc["request_id"],),
            )
            c.execute(
                "update privacy_revocation_credentials set expires_at=clock_timestamp()-interval '1 second' where request_id=%s",
                (doc["request_id"],),
            )
        admin = PrivateAuthAdmin(self.url("auth"), self.service, local_rehearsal=True)
        observer = SessionRevocationObserver(
            lambda: self.connect("privacy_revocation_observer")
        )
        called = []

        def lost_delete(account):
            assert account == u["id"] and admin.soft_delete(account)
            called.append(True)
            raise requests.Timeout()

        recover = AuthSoftDeleteRecovery(
            lambda: self.connect("usage_executor"),
            lost_delete,
            admin.get_user,
            observer,
        )
        worker = RevocationWorker(
            lambda: self.connect("usage_executor"), recover=recover
        )
        # Missing required notice must preserve the only destination and fail
        # closed. Real event RPCs and SMTP below then establish positive evidence.
        assert worker.run_one()
        assert not called and not admin.get_user(u["id"]).get("deleted_at")
        with self.connect() as c:
            c.execute(
                "update privacy_followup_tasks set state='pending',due_at=clock_timestamp()-interval '1 second' where request_id=%s and kind='revoke_sessions'",
                (doc["request_id"],),
            )
        rehearsal = self

        class LocalEvents(SupabaseOutboundEmailEventClient):
            def __init__(self):
                pass

            def _rpc(self, name, payload):
                response = requests.post(
                    rehearsal.url("rest") + "/rpc/" + name,
                    json=payload,
                    headers={"Authorization": "Bearer " + rehearsal.service},
                    timeout=5,
                )
                assert response.status_code == 200
                result = response.json()
                return result[0] if isinstance(result, list) else result

        class LocalMail:
            def send_email(self, message):
                assert message.recipient_email.endswith("@example.invalid")
                mail = EmailMessage()
                mail["From"], mail["To"], mail["Subject"] = (
                    "privacy@example.invalid",
                    message.recipient_email,
                    message.subject,
                )
                mail.set_content(message.text_body)
                with smtplib.SMTP("mail", 1025, timeout=3) as smtp:
                    smtp.send_message(mail)
                return EmailSendResult(
                    "sent",
                    "local_mailpit",
                    "local-notice",
                    False,
                    "***",
                    message.email_type,
                    utc_timestamp(),
                )

        notice = PrivacyNotifier(
            self.engine,
            EmailService(
                LocalMail(), event_store=OutboundEmailEventService(client=LocalEvents())
            ),
        )
        assert notice.notify(u["id"], "accepted").event_status == "sent"
        assert self.messages(u["email"])
        assert worker.run_one()
        with self.connect() as c:
            assert (
                c.execute(
                    "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
                    (doc["request_id"],),
                ).fetchone()[0]
                == "pending"
            )
            c.execute(
                "update privacy_followup_tasks set due_at=clock_timestamp()-interval '1 second' where request_id=%s and kind='revoke_sessions'",
                (doc["request_id"],),
            )
        # Restart needs no expired user token or encryption key. The supported
        # Auth tombstone plus current session absence proves prior completion.
        restarted = RevocationWorker(
            lambda: self.connect("usage_executor"), recover=recover
        )
        assert restarted.run_one()
        from app.privacy_content import ContentBlocked

        delivered = len(self.messages(u["email"]))
        try:
            notice.notify(u["id"], "accepted")
        except ContentBlocked:
            pass
        else:
            raise AssertionError("soft_deleted_notification_destination_reused")
        assert len(self.messages(u["email"])) == delivered
        with self.connect() as c:
            assert (
                c.execute(
                    "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
                    (doc["request_id"],),
                ).fetchone()[0]
                == "succeeded"
            )
            assert (
                c.execute(
                    "select count(*) from auth.sessions where user_id=%s", (u["id"],)
                ).fetchone()[0]
                == 0
            )
            assert (
                c.execute(
                    "select count(*) from auth.sessions where user_id=%s",
                    (other["id"],),
                ).fetchone()[0]
                > 0
            )
            assert (
                c.execute(
                    "select count(*) from privacy_revocation_credentials where request_id=%s",
                    (doc["request_id"],),
                ).fetchone()[0]
                == 0
            )
            assert c.execute(
                "select email<>%s and raw_user_meta_data='{}'::jsonb and raw_app_meta_data='{}'::jsonb from auth.users where id=%s",
                (u["email"], u["id"]),
            ).fetchone()[0]
        assert len(called) == 1
        assert (
            self.auth(
                "/token?grant_type=password",
                body={"email": u["email"], "password": self.password},
            ).status_code
            != 200
        )
        self.save(
            "auth-finalization.json",
            {
                "authority": "actual supported GoTrue admin soft-delete API; UUID/FK tombstone retained",
                "expired_credential_recovery": True,
                "lost_ack_restart_verified": True,
                "unaffected_sessions_preserved": True,
                "original_contact_and_auth_metadata_removed": True,
                "auth_obfuscation_is_not_anonymization": True,
                "managed_auth_audit_copy_lifecycle": "separate platform acceptance; no erasure deadline claimed",
            },
        )

    def checkpoint_services(self):
        self.configure_app()
        import multiprocessing
        import tempfile
        from typing import Any, cast

        from app.privacy_checkpoint import LocalCheckpointStore, RestoreCoordinator
        from app.privacy_content import ContentBlocked
        from app.privacy_restore import RestoreJournal
        from app.privacy_witness import HTTPCheckpointStore, local_authority

        with tempfile.TemporaryDirectory(prefix="c15-owned-authority-") as owned:
            path = Path(owned)
            key = secrets.token_bytes(32)
            environment, dataset = str(uuid4()), str(uuid4())
            journal = RestoreJournal(
                path / "independent-journal", {"v1": secrets.token_bytes(32)}, "v1"
            )
            store = LocalCheckpointStore(
                path / "independent-head",
                path / "separate-anchor",
                key,
                environment,
                dataset,
            )
            store.initialize(journal.initialize())
            generation, snapshot = str(uuid4()), str(uuid4())
            store.authorize_restore(0, generation, snapshot)
            reader, writer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            server = local_authority(store, reader, writer)
            process = cast(Any, multiprocessing.get_context("fork")).Process(
                target=server.serve_forever
            )
            process.start()
            try:
                client = HTTPCheckpointStore(
                    f"http://127.0.0.1:{server.server_port}",
                    writer,
                    key,
                    environment,
                    dataset,
                    local_rehearsal=True,
                )
                co = RestoreCoordinator(
                    self.engine, journal, client, generation, snapshot
                )
                assert not co.ready()
                co.seal_source()
                co.reconcile()
                assert co.ready()
                restarted = RestoreCoordinator(
                    self.engine, journal, client, co.generation, co.snapshot
                )
                assert not restarted.ready()
                restarted.reconcile()
                assert restarted.ready()
                # An interrupted reader/witness outage never preserves readiness.
                process.terminate()
                process.join(timeout=5)
                server.server_close()
                assert not restarted.ready()
                try:
                    restarted.reconcile()
                    raise AssertionError("missing witness released restore")
                except ContentBlocked:
                    pass
                self.save(
                    "checkpoint-services.json",
                    {
                        "postgres": "actual17.11",
                        "authority": "separate loopback process, authenticated CAS interface",
                        "empty_restore_and_restart_verified": True,
                        "missing_authority_quarantines": True,
                        "durability": "local rehearsal only; independent production placement not selected",
                    },
                )
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                server.server_close()

    def revocation_observation(self):
        from app.privacy_credentials import GlobalLogout
        from app.privacy_revocation import RevocationWorker, SessionRevocationObserver

        with self.connect() as c:
            c.execute(
                psycopg.sql.SQL(
                    "alter role privacy_revocation_observer login password {}"
                ).format(psycopg.sql.Literal(self.password))
            )
        _u, doc = self.accepted_password()
        other = self.user()
        with self.connect() as c:
            c.execute(
                "update privacy_followup_tasks set state='blocked',lease_id=null,lease_until=null where kind='revoke_sessions' and request_id<>%s",
                (doc["request_id"],),
            )
        observer = SessionRevocationObserver(
            lambda: self.connect("privacy_revocation_observer")
        )

        def lost_ack(url, **kwargs):
            response = self.http.post(
                self.url("auth") + "/logout?scope=global", **kwargs
            )
            assert response.status_code == 204
            response.close()
            raise requests.Timeout()

        worker = RevocationWorker(
            lambda: self.connect("usage_executor"),
            logout=GlobalLogout(
                self.box, "https://isolated.invalid", self.anon, lost_ack
            ),
            verify=observer,
        )
        assert worker.run_one()
        with self.connect() as c:
            assert (
                c.execute(
                    "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
                    (doc["request_id"],),
                ).fetchone()[0]
                == "succeeded"
            )
            assert (
                c.execute(
                    "select count(*) from auth.sessions where user_id=%s",
                    (other["id"],),
                ).fetchone()[0]
                > 0
            )
            assert (
                c.execute(
                    "select count(*) from privacy_revocation_credentials where request_id=%s",
                    (doc["request_id"],),
                ).fetchone()[0]
                == 0
            )
        # No current lease means even the intended observer cannot query a subject.
        try:
            observer(
                {
                    "request_id": doc["request_id"],
                    "lease_id": str(uuid4()),
                    "account_id": other["id"],
                }
            )
            raise AssertionError("unscoped observer allowed")
        except psycopg.Error as error:
            assert error.sqlstate == "42501"
        self.save(
            "revocation-observation.json",
            {
                "lost_ack_recovered_from_authoritative_zero_sessions": True,
                "other_account_sessions_preserved": True,
                "stale_wrong_subject_denied": True,
                "credential_cleared": True,
                "observation_is_not_global_jwt_invalidation": True,
            },
        )

    def provisioning(self):
        from app.privacy_content import ContentBlocked
        from app.privacy_provisioning import ProvisioningGate

        with self.connect() as c:
            for role in (
                "privacy_provisioning_executor",
                "authenticated",
                "service_role",
            ):
                c.execute(
                    psycopg.sql.SQL("alter role {} login password {}").format(
                        psycopg.sql.Identifier(role), psycopg.sql.Literal(self.password)
                    )
                )
        requests_made = []

        def create(operation, email, password):
            requests_made.append(operation)
            response = self.auth(
                "/admin/users",
                body={"email": email, "password": password, "email_confirm": True},
                token=self.service,
            )
            self.check(response, 200, "controlled_auth_create")
            return response.json()["id"]

        gate = ProvisioningGate(
            lambda: self.connect("privacy_provisioning_executor"), create
        )
        allowed = "control-" + uuid4().hex + "@example.invalid"
        assert gate.provision(str(uuid4()), allowed, self.password)
        u, _doc = self.accepted_password()
        try:
            gate.provision(str(uuid4()), u["email"], self.password)
            raise AssertionError("suppressed import allowed")
        except ContentBlocked as error:
            assert str(error) == "provisioning_denied"
        assert len(requests_made) == 1
        for role in ("usage_executor", "authenticated", "service_role"):
            try:
                with self.connect(role) as c:
                    c.execute(
                        "select public.privacy_provisioning_check(%s)", (allowed,)
                    )
                raise AssertionError("public provisioning check allowed")
            except psycopg.Error as error:
                assert error.sqlstate == "42501"

    def assert_claims(self, u):
        p = jwt.decode(
            u["access_token"],
            self.secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        assert p["sub"] == u["id"] and p.get("c15_auth_method") == "password"

    def check(self, response, status, category):
        if response.status_code != status:
            try:
                body = response.json()
            except ValueError:
                body = {}
            # Only allowlisted error classification, never message/body/URL.
            self.save(
                "error-" + category + ".json",
                {
                    "status": response.status_code,
                    "code": body.get("error_code")
                    or body.get("code")
                    or (
                        body.get("detail")
                        if isinstance(body.get("detail"), dict)
                        else {}
                    ),
                },
            )
            raise RuntimeError(category)
        return response.json() if response.content else {}

    def messages(self, email):
        records = self.http.get(self.url("mail") + "/api/v1/messages", timeout=3).json()
        return [
            self.http.get(
                self.url("mail") + "/api/v1/message/" + m["ID"], timeout=3
            ).json()
            for m in records.get("messages", records.get("Messages", []))
            if any(t.get("Address") == email for t in m.get("To", []))
        ]

    def mail_code(self, email, exclude=None):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            for m in self.messages(email):
                match = re.search(r"(?<![0-9])([0-9]{8})(?![0-9])", m.get("Text", ""))
                if match and match.group(1) != exclude:
                    return match.group(1)
            time.sleep(0.1)
        raise RuntimeError("local_code_not_received")

    def send(self, email, code):
        assert email.endswith("@example.invalid")
        m = EmailMessage()
        m["From"] = "privacy@example.invalid"
        m["To"] = email
        m["Subject"] = "C15 local application proof"
        m.set_content("Confirmation code: " + code)
        with smtplib.SMTP("mail", 1025, timeout=3) as smtp:
            smtp.send_message(m)

    def configure_app(self):
        sys.path.insert(0, str(ROOT / "backend"))
        # Prevent every operational dotenv read before importing application code.
        import dotenv

        dotenv.load_dotenv = lambda *a, **k: False
        os.environ.update(
            SUPABASE_URL=self.url("auth"),
            SUPABASE_ANON_KEY=self.anon,
            SUPABASE_SERVICE_ROLE_KEY=self.service,
            SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=json.dumps(
                {
                    "secret": self.secret,
                    "issuer": self.url("auth") + "/auth/v1",
                    "audience": "authenticated",
                }
            ),
            SUPABASE_RESUME_BUCKET="resumes",
            SUPABASE_EXPORT_BUCKET="exports",
            C15_REVOCATION_KEYS=json.dumps(
                {"local": base64.b64encode(secrets.token_bytes(32)).decode()}
            ),
            C15_REVOCATION_CURRENT_KEY="local",
        )
        from types import SimpleNamespace

        from app.config import settings
        from app.privacy import router
        from app.privacy_content import ContentEngine
        from app.privacy_content_api import router as content_router
        from app.privacy_credentials import CredentialBox
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        settings.C15_ENABLED = "true"
        settings.C15_RESTRICTIONS_REQUIRED = "true"
        settings.SUBSCRIPTIONS_ENABLED = "true"
        self.box = CredentialBox.configured()
        app = FastAPI()
        app.include_router(router)
        app.include_router(content_router)
        app.state.subscriptions = SimpleNamespace(
            connect=lambda: self.connect("usage_executor")
        )
        app.state.privacy_otp_sender = self.send
        self.store = ActualStorage(self)
        self.engine = ContentEngine(
            self.connect,
            self.store,
            local_rehearsal=True,
            credential_connect=lambda: self.connect("privacy_cleanup_executor"),
        )
        with self.connect() as c:
            c.execute("alter role privacy_cleanup_executor login")
            c.execute(
                psycopg.sql.SQL(
                    "alter role privacy_cleanup_executor password {}"
                ).format(psycopg.sql.Literal(self.password))
            )
        app.state.privacy_content_local = self.engine
        app.state.privacy_export_box = self.box
        app.state.privacy_export_sender = self.send
        self.app = app
        self.client = TestClient(app)

    def document(self):
        return {
            "request_id": str(uuid4()),
            "confirmation_token": secrets.token_urlsafe(32),
            "status_token": secrets.token_urlsafe(32),
            "policy_version": "c15.2026-10-29.v1",
            "scope": "whole_account",
        }

    def call(self, u, action, doc, **extra):
        return self.client.post(
            "/api/privacy/deletion/" + action,
            headers={"Authorization": "Bearer " + u["access_token"]},
            json={**doc, **extra},
        )

    def signup_mail(self):
        from urllib.parse import parse_qs, urlsplit

        email = uuid4().hex + "@example.invalid"
        self.check(
            self.auth(
                "/signup",
                body={"email": email, "password": self.password},
                token=self.anon,
            ),
            200,
            "signup",
        )
        until = time.monotonic() + 8
        link = None
        while time.monotonic() < until and not link:
            for m in self.messages(email):
                match = re.search(r'http[^\s<>"\)]+', m.get("Text", ""))
                if match and "token=" in match.group(0):
                    link = match.group(0)
            if not link:
                time.sleep(0.1)
        assert link, "signup_mail_not_caught"
        q = parse_qs(urlsplit(link).query)
        value = self.check(
            self.auth(
                "/verify",
                body={"type": "signup", "token_hash": q["token"][0]},
                token=self.anon,
            ),
            200,
            "signup_verify",
        )
        assert value.get("access_token")

    def totp(self):
        import hmac

        from app.auth.supabase_auth import verify_supabase_token
        from app.privacy import recent_presence
        from fastapi import HTTPException

        u = self.user()
        factor = self.check(
            self.auth(
                "/factors",
                body={"factor_type": "totp", "friendly_name": "local-rehearsal"},
                token=u["access_token"],
            ),
            200,
            "totp_enroll",
        )
        challenge = self.check(
            self.auth(
                "/factors/" + factor["id"] + "/challenge",
                body={},
                token=u["access_token"],
            ),
            200,
            "totp_challenge",
        )
        secret = factor["totp"]["secret"]
        secret += "=" * ((-len(secret)) % 8)
        raw = hmac.new(
            base64.b32decode(secret),
            struct.pack(">Q", int(time.time()) // 30),
            hashlib.sha1,
        ).digest()
        off = raw[-1] & 15
        code = (
            f"{(struct.unpack('>I', raw[off : off + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"
        )
        wrong = "000000" if code != "000000" else "111111"
        assert (
            self.auth(
                "/factors/" + factor["id"] + "/verify",
                body={"challenge_id": challenge["id"], "code": wrong},
                token=u["access_token"],
            ).status_code
            != 200
        )
        challenge = self.check(
            self.auth(
                "/factors/" + factor["id"] + "/challenge",
                body={},
                token=u["access_token"],
            ),
            200,
            "totp_second_challenge",
        )
        raw = hmac.new(
            base64.b32decode(secret),
            struct.pack(">Q", int(time.time()) // 30),
            hashlib.sha1,
        ).digest()
        off = raw[-1] & 15
        code = (
            f"{(struct.unpack('>I', raw[off : off + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"
        )
        verified = self.check(
            self.auth(
                "/factors/" + factor["id"] + "/verify",
                body={"challenge_id": challenge["id"], "code": code},
                token=u["access_token"],
            ),
            200,
            "totp_verify",
        )
        claims = verify_supabase_token(verified["access_token"])
        method, _ = recent_presence(claims)
        assert method == claims.claims["session_id"]
        assert (
            claims.claims["c15_auth_method"] == "totp"
            and claims.claims["aal"] == "aal2"
        )
        refresh = self.check(
            self.auth(
                "/token?grant_type=refresh_token",
                body={"refresh_token": verified["refresh_token"]},
            ),
            200,
            "totp_refresh",
        )
        try:
            recent_presence(verify_supabase_token(refresh["access_token"]))
        except HTTPException:
            pass
        else:
            raise RuntimeError("refresh_only_was_presence")

    def google_fixture(self):
        # Only provider metadata is a fixture; token issuance is actual Auth.
        u = self.user()
        self.check(
            self.auth(
                "/admin/users/" + u["id"],
                method="PUT",
                body={"app_metadata": {"providers": ["google"], "provider": "google"}},
            ),
            200,
            "provider_fixture",
        )
        session = self.check(
            self.auth(
                "/token?grant_type=refresh_token",
                body={"refresh_token": u["refresh_token"]},
            ),
            200,
            "fixture_refresh",
        )
        u.update(session)
        return u

    def mailbox(self):
        u = self.google_fixture()
        d = self.document()
        self.check(self.call(u, "begin", d), 200, "otp_begin")
        self.check(
            self.call(u, "confirm", d, confirmation_text="delete"), 403, "otp_no_proof"
        )
        self.check(self.call(u, "otp_start", d), 200, "otp_send")
        code = self.mail_code(u["email"])
        assert self.call(u, "otp_start", d).json()["state"] == "otp_limited"
        assert (
            self.call(
                u,
                "otp_verify",
                d,
                code="00000000" if code != "00000000" else "11111111",
            ).json()["state"]
            == "otp_rejected"
        )
        other = self.user()
        assert self.call(other, "otp_verify", d, code=code).status_code != 200
        bad = {**d, "request_id": str(uuid4())}
        assert self.call(u, "otp_verify", bad, code=code).status_code != 200

        def verify(_):
            return self.call(u, "otp_verify", d, code=code).json().get("state")

        with ThreadPoolExecutor(2) as pool:
            states = list(pool.map(verify, range(2)))
        assert states.count("awaiting_confirmation") == 1
        assert (
            self.call(u, "otp_verify", d, code=code).json()["state"] == "otp_rejected"
        )
        assert self.call(u, "otp_ready", d).json()["state"] == "awaiting_confirmation"
        assert not self.sql(
            "select 1 from subscription_deletion_jobs where account_id=%s", (u["id"],)
        )
        self.check(
            self.call(u, "confirm", d, confirmation_text="Delete"), 422, "wrong_typed"
        )
        result = self.check(
            self.call(u, "confirm", d, confirmation_text="delete"), 200, "otp_final"
        )
        assert result["state"] == "accepted_restricted" and not result["content_erased"]
        # No delivery/provider or destructive content worker is composed here.
        self.mailbox_subject = u

    def storage_export(self):
        import io
        import zipfile

        from app.privacy_content import ContentBlocked
        from app.privacy_schema import validate_schema

        u = self.user()
        other = self.user()
        key = u["id"] + "/" + str(uuid4()) + "/synthetic.txt"
        r = self.store.request(
            "POST", "/object/resumes/" + key, data=b"SYNTHETIC_C15_FILE"
        )
        self.check(r, 200, "owned_upload")
        assert (
            self.store.request(
                "GET", "/object/resumes/" + key, other["access_token"]
            ).status_code
            != 200
        )
        assert (
            self.store.request(
                "POST", "/object/resumes/" + key, other["access_token"], data=b"foreign"
            ).status_code
            != 200
        )
        with self.connect() as c:
            c.execute(
                "insert into profiles(user_id,full_name) values(%s,'Synthetic C15')",
                (u["id"],),
            )
            c.execute(
                "insert into resumes(user_id,storage_path,original_filename,mime_type,file_size) values(%s,%s,'synthetic.txt','text/plain',18)",
                (u["id"], key),
            )
            validate_schema(c.cursor(), require_full=True)
        job = str(uuid4())
        self.engine.request(u["id"], job)
        assert self.engine.run_one()
        assert self.engine.status(u["id"], job)["state"] == "ready"
        capability = self.engine.authorize(u["id"], job)
        archive = b"".join(self.engine.download(u["id"], job, capability))
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            assert any(z.read(n) == b"SYNTHETIC_C15_FILE" for n in z.namelist())
        try:
            self.engine.authorize(other["id"], job)
        except ContentBlocked:
            pass
        else:
            raise RuntimeError("foreign_export_authorized")
        artifact = self.sql(
            "select artifact_key from privacy_content_jobs where id=%s", (job,)
        )[0][0]
        direct_ready = self.store.request(
            "GET", "/object/exports/" + artifact, u["access_token"]
        ).status_code
        direct_sign = self.store.request(
            "POST",
            "/object/sign/exports/" + artifact,
            u["access_token"],
            json={"expiresIn": 3600},
        ).status_code
        with self.connect() as c:
            c.execute(
                "update privacy_content_jobs set expires_at=clock_timestamp()-interval '1 second' where id=%s",
                (job,),
            )
        direct_expired = self.store.request(
            "GET", "/object/exports/" + artifact, u["access_token"]
        ).status_code
        self.save(
            "direct-archive-boundary.json",
            {
                "ready_direct_get": direct_ready,
                "ready_direct_sign": direct_sign,
                "expired_direct_get_before_physical_cleanup": direct_expired,
                "private_archive_via_app_succeeded": True,
            },
        )
        assert direct_ready != 200 and direct_sign != 200 and direct_expired != 200, (
            "archive_direct_storage_access"
        )
        self.store.remove("exports", artifact)
        # A late backend put after manifest removal still cannot escape the job
        # namespace boundary. Its job identity remains durable.
        self.store.request(
            "POST", "/object/exports/" + artifact, data=b"SYNTHETIC_LATE_ARCHIVE"
        )
        assert (
            self.store.request(
                "GET", "/object/exports/" + artifact, u["access_token"]
            ).status_code
            != 200
        )
        self.store.remove("exports", artifact)
        try:
            self.engine.authorize(u["id"], job)
        except ContentBlocked:
            pass
        else:
            raise RuntimeError("expired_export_authorized")
        assert self.engine.expire_one()
        # Preserve existing non-C15 exports under the original ownership RLS.
        legacy = u["id"] + "/" + str(uuid4()) + "/manual.txt"
        created = self.http.post(
            self.url("storage") + "/object/exports/" + legacy,
            headers={
                "Authorization": "Bearer " + u["access_token"],
                "Content-Type": "text/plain",
            },
            data=b"SYNTHETIC_LEGACY_EXPORT",
            timeout=5,
        )
        self.check(created, 200, "legacy_export_preserved")
        assert (
            self.store.request(
                "GET", "/object/exports/" + legacy, u["access_token"]
            ).status_code
            == 200
        )
        assert (
            self.store.request(
                "GET", "/object/exports/" + legacy, other["access_token"]
            ).status_code
            != 200
        )
        self.check(
            self.store.request(
                "DELETE",
                "/object/exports",
                u["access_token"],
                json={"prefixes": [legacy]},
            ),
            200,
            "legacy_owner_delete_preserved",
        )
        self.store.remove("resumes", key)
        assert self.store.stat("resumes", key) is None
        # A denied access check is never mistaken for object absence.
        assert (
            self.store.request(
                "GET", "/object/resumes/" + key, other["access_token"]
            ).status_code
            != 200
        )

    def durable_storage(self):
        from app.privacy_content import ContentBlocked

        u = self.user()
        other = self.user()
        key = u["id"] + "/" + str(uuid4()) + "/durable.txt"
        payload = ("SYNTHETIC-DURABLE-" + uuid4().hex).encode()
        self.check(
            self.store.request("POST", "/object/resumes/" + key, data=payload),
            200,
            "durable_upload",
        )
        with self.connect() as c:
            c.execute(
                "insert into profiles(user_id,full_name) values(%s,'Synthetic durable')",
                (u["id"],),
            )
            c.execute(
                "insert into resumes(user_id,storage_path,original_filename,mime_type,file_size) values(%s,%s,'durable.txt','text/plain',%s)",
                (u["id"], key, len(payload)),
            )
            c.execute(
                "insert into profiles(user_id,full_name) values(%s,'Unaffected')",
                (other["id"],),
            )

        def physical_count():
            # Only this run's dedicated synthetic Storage volume, mounted RO.
            count = 0
            for f in Path("/storage-evidence").rglob("*"):
                if (
                    f.is_file()
                    and not f.is_symlink()
                    and f.stat().st_size == len(payload)
                ):
                    count += f.read_bytes() == payload
            return count

        before = physical_count()
        assert before == 1
        u, doc = self.accepted_password(u)
        self.engine.request(u["id"], doc["request_id"], "account")
        crashed = [False]

        def after_remove(bucket, object_key):
            if object_key == key and not crashed[0]:
                crashed[0] = True
                raise TimeoutError()

        self.store.after_remove = after_remove
        try:
            assert self.engine.run_one()
        finally:
            self.store.after_remove = None
        self.save(
            "durable-observed.json",
            {
                "remove_called": crashed[0],
                "physical_count": physical_count(),
                "status": self.engine.status(u["id"], doc["request_id"]),
                "recent_sql_categories": self.sql_errors[-12:],
            },
        )
        assert crashed[0] and physical_count() == 0
        with self.connect() as c:
            c.execute(
                "update privacy_content_jobs set retry_at=clock_timestamp() where id=%s",
                (doc["request_id"],),
            )
        old = self.engine.claim()
        assert str(old["id"]) == doc["request_id"]
        with self.connect() as c:
            c.execute(
                "update privacy_content_jobs set lease_until=clock_timestamp()-interval '1 second' where id=%s",
                (doc["request_id"],),
            )
        renewed = self.engine.claim()
        assert renewed["lease"] != old["lease"]
        try:
            with self.engine.transaction() as c:
                self.engine.live(c, old)
        except ContentBlocked:
            pass
        else:
            raise RuntimeError("stale_cleanup_worker_accepted")
        self.engine.cleanup(renewed)
        state = self.engine.status(u["id"], doc["request_id"])
        assert state["state"] == "primary_verified" and not state.get(
            "content_erased", False
        )
        assert (
            state["progress"]["retained_exceptions"]["subscription_deletion_jobs"]
            == "restore_evidence"
        )
        assert self.store.stat("resumes", key) is None and physical_count() == 0
        assert (
            self.store.request(
                "POST", "/object/resumes/" + key, data=payload
            ).status_code
            != 200
        )
        assert self.sql("select 1 from profiles where user_id=%s", (other["id"],))
        # Actual PostgREST/RLS, not an owner SELECT, denies restored/old JWT use.
        rest = self.http.get(
            self.url("rest") + "/profiles",
            headers={"Authorization": "Bearer " + u["access_token"]},
            timeout=5,
        )
        assert rest.status_code == 200 and rest.json() == []
        bootstrap = self.http.post(
            self.url("rest") + "/profiles",
            headers={"Authorization": "Bearer " + u["access_token"]},
            json={"user_id": u["id"]},
            timeout=5,
        )
        assert bootstrap.status_code != 201
        with self.connect() as c:
            exports = c.execute(
                "select public,allowed_mime_types,file_size_limit from storage.buckets where id='exports'"
            ).fetchone()
            resumes = c.execute(
                "select public,allowed_mime_types from storage.buckets where id='resumes'"
            ).fetchone()
            assert exports[0] is False and "application/zip" in exports[1]
            assert resumes[0] is False and "application/zip" not in resumes[1]
        self.save(
            "durable-storage.json",
            {
                "physical_owned_files_before": before,
                "physical_owned_files_after": physical_count(),
                "storage_success_then_lost_ack_recovered": True,
                "stale_worker_denied": True,
                "account_state": state["state"],
                "complete_erasure_claim": False,
                "unaffected_profile_preserved": True,
                "rest_rls_old_jwt_rows": 0,
                "private_exports_zip": True,
                "configured_bucket_limit_bytes": exports[2],
            },
        )

    def deletion(self):
        from app.privacy_credentials import GlobalLogout
        from app.privacy_revocation import RevocationWorker

        u = self.user()
        unaffected = self.user()
        doc = self.document()
        self.check(self.call(u, "begin", doc), 200, "password_begin")
        assert self.call(u, "challenge", doc).status_code == 403
        # Actual user presence must occur in a later Auth timestamp, not refresh.
        time.sleep(1.1)
        u.update(self.login(u["email"]))
        self.check(self.call(u, "challenge", doc), 200, "fresh_password_challenge")
        key = u["id"] + "/" + str(uuid4()) + "/owned.txt"
        self.check(
            self.store.request("POST", "/object/resumes/" + key, data=b"SYNTHETIC"),
            200,
            "before_delete_upload",
        )
        signed = self.check(
            self.store.request(
                "POST",
                "/object/sign/resumes/" + key,
                u["access_token"],
                json={"expiresIn": 3},
            ),
            200,
            "signed_url",
        )
        result = self.check(
            self.call(u, "confirm", doc, confirmation_text="delete"),
            200,
            "password_confirm",
        )
        assert not result["content_erased"] and result["cleanup_state"] == "pending"
        assert (
            self.call(u, "confirm", doc, confirmation_text="delete").json()[
                "request_id"
            ]
            == doc["request_id"]
        )
        # Same JWT remains cryptographically valid; product, REST and write gates deny.
        assert (
            self.store.request(
                "POST", "/object/resumes/" + key, u["access_token"], data=b"late"
            ).status_code
            != 200
        )
        assert (
            self.store.request(
                "GET", "/object/resumes/" + key, u["access_token"]
            ).status_code
            != 200
        )
        with self.connect("usage_executor") as c:
            try:
                with c.transaction():
                    c.execute("select subscription_access_check(%s)", (u["id"],))
            except psycopg.Error as error:
                assert error.sqlstate == "42501"
            else:
                raise RuntimeError("old_token_product_access")

        # Close the initiating ASGI client. Recovery consumes only the durable
        # encrypted envelope and a fresh worker, not browser/session state.
        from fastapi.testclient import TestClient

        self.client.close()
        self.client = TestClient(self.app)

        # Drain earlier synthetic revocation requests too through actual Auth.
        def post(_url, **kw):
            return self.http.post(self.url("auth") + "/logout?scope=global", **kw)

        logout = GlobalLogout(
            self.box, "https://local-rehearsal.invalid", self.anon, post
        )
        worker = RevocationWorker(lambda: self.connect("usage_executor"), logout=logout)
        for _ in range(20):
            if not worker.run_one():
                break
        assert not self.sql("select 1 from auth.sessions where user_id=%s", (u["id"],))
        assert not self.sql(
            "select 1 from privacy_revocation_credentials where request_id=%s",
            (doc["request_id"],),
        )
        assert (
            self.auth(
                "/token?grant_type=refresh_token",
                body={"refresh_token": u["refresh_token"]},
            ).status_code
            != 200
        )
        self.check(
            self.auth(
                "/token?grant_type=refresh_token",
                body={"refresh_token": unaffected["refresh_token"]},
            ),
            200,
            "unaffected_refresh",
        )
        status = self.check(
            self.client.post(
                "/api/privacy/deletion/status",
                json={
                    "request_id": doc["request_id"],
                    "status_token": doc["status_token"],
                },
            ),
            200,
            "scoped_status",
        )
        assert not status["content_erased"]
        # Auth admin mutation is an explicit local synthetic fixture, not Google.
        new_email = uuid4().hex + "@example.invalid"
        self.check(
            self.auth(
                "/admin/users/" + u["id"], method="PUT", body={"email": new_email}
            ),
            200,
            "restricted_admin_email_fixture",
        )
        blocked = self.auth(
            "/signup",
            body={"email": u["email"], "password": self.password},
            token=self.anon,
        )
        assert blocked.status_code in (400, 403), "direct_signup_suppression_failed"
        assert (
            self.auth(
                "/token?grant_type=password",
                body={"email": new_email, "password": self.password},
            ).status_code
            != 200
        )
        # Existing signed capabilities are independent; record the observed boundary.
        url = signed.get("signedURL", signed.get("signedUrl"))
        assert url
        first = self.http.get(self.url("storage") + url, timeout=3).status_code
        time.sleep(4)
        expired = self.http.get(self.url("storage") + url, timeout=3).status_code
        assert expired != 200
        self.save(
            "capability-observation.json",
            {
                "old_signed_url_after_restriction_status": first,
                "after_expiry_status": expired,
                "already_delivered_bytes_recallable": False,
                "jwt_global_instant_revocation_claim": False,
            },
        )
        self.store.remove("resumes", key)
        assert self.store.stat("resumes", key) is None

    def mailbox_edges(self):
        u = self.google_fixture()
        d = self.document()
        self.check(self.call(u, "begin", d), 200, "edge_begin")
        assert self.call(u, "otp_start", d).json()["state"] == "otp_sent"
        code = self.mail_code(u["email"])
        # Controlled SQL clocks accelerate application receipt windows, not Auth
        # token/signature behavior. Every token here still comes from Auth.
        with self.connect() as c:
            c.execute(
                "update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id=%s",
                (u["id"],),
            )
        assert self.call(u, "otp_start", d).json()["state"] == "otp_sent"
        next_code = self.mail_code(u["email"], exclude=code)
        assert (
            self.call(u, "otp_verify", d, code=code).json()["state"] == "otp_rejected"
        )
        different = {**u, **self.login(u["email"])}
        assert (
            jwt.decode(
                different["access_token"],
                self.secret,
                algorithms=["HS256"],
                audience="authenticated",
            )["session_id"]
            != jwt.decode(
                u["access_token"],
                self.secret,
                algorithms=["HS256"],
                audience="authenticated",
            )["session_id"]
        )
        assert self.call(different, "otp_verify", d, code=next_code).status_code == 403
        wrong = "00000000" if next_code != "00000000" else "11111111"
        for _ in range(5):
            assert (
                self.call(u, "otp_verify", d, code=wrong).json()["state"]
                == "otp_rejected"
            )
        assert (
            self.call(u, "otp_verify", d, code=next_code).json()["state"]
            == "otp_rejected"
        )
        assert (
            self.sql(
                "select attempts from privacy_email_otp where account_id=%s", (u["id"],)
            )[0][0]
            == 5
        )
        with self.connect() as c:
            c.execute(
                "update privacy_email_otp set sent_at=clock_timestamp()-interval '61 seconds' where account_id=%s",
                (u["id"],),
            )
        assert self.call(u, "otp_start", d).json()["state"] == "otp_sent"
        next_code = self.mail_code(u["email"], exclude=next_code)
        with self.connect() as c:
            c.execute(
                "update privacy_email_otp set expires_at=clock_timestamp()-interval '1 second',sent_at=clock_timestamp()-interval '61 seconds' where account_id=%s",
                (u["id"],),
            )
        assert self.call(u, "otp_verify", d, code=next_code).status_code == 403
        assert self.call(u, "otp_start", d).json()["state"] == "otp_limited"
        with self.connect() as c:
            c.execute(
                "update privacy_email_otp_limits set hour_start=clock_timestamp()-interval '2 hours',day_count=10 where account_id=%s",
                (u["id"],),
            )
        assert self.call(u, "otp_start", d).json()["state"] == "otp_limited"
        assert not self.sql(
            "select 1 from subscription_deletion_jobs where account_id=%s", (u["id"],)
        )

    def export_proofs(self):
        u = self.google_fixture()
        d = self.document()
        job = str(uuid4())
        self.check(self.call(u, "begin", d), 200, "separate_begin")
        assert self.call(u, "otp_start", d).json()["state"] == "otp_sent"
        deletion_code = self.mail_code(u["email"])

        def call(action, **kw):
            return self.client.post(
                "/api/privacy/content/" + action,
                headers={"Authorization": "Bearer " + u["access_token"]},
                json={"request_id": job, **kw},
            )

        self.check(call("begin"), 200, "export_begin")
        self.check(call("otp_start"), 200, "export_otp_send")
        export_code = self.mail_code(u["email"], exclude=deletion_code)
        assert call("otp_verify", code=deletion_code).status_code == 409
        assert (
            self.call(u, "otp_verify", d, code=export_code).json()["state"]
            == "otp_rejected"
        )
        self.check(call("otp_verify", code=export_code), 200, "export_otp_verify")
        assert not self.sql("select 1 from privacy_content_jobs where id=%s", (job,))
        assert self.call(u, "confirm", d, confirmation_text="delete").status_code == 403
        self.check(call("confirm", confirmation_text="export"), 200, "export_confirm")
        assert self.engine.run_one()
        capability = self.check(call("authorize"), 200, "export_authorize")[
            "capability"
        ]
        response = call("download", capability=capability)
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
            and response.content.startswith(b"PK")
        )
        # Stop publication/download on a later accepted deletion; do not claim
        # already delivered bytes are recalled.
        assert (
            self.call(u, "otp_verify", d, code=deletion_code).json()["state"]
            == "awaiting_confirmation"
        )
        self.check(
            self.call(u, "confirm", d, confirmation_text="delete"),
            200,
            "export_delete_confirm",
        )
        assert call("authorize").status_code == 409
        assert self.engine.expire_one()

    def accepted_password(self, u=None):
        u = u or self.user()
        d = self.document()
        self.check(self.call(u, "begin", d), 200, "recovery_begin")
        time.sleep(1.1)
        u.update(self.login(u["email"]))
        self.check(self.call(u, "challenge", d), 200, "recovery_challenge")
        self.check(
            self.call(u, "confirm", d, confirmation_text="delete"),
            200,
            "recovery_confirm",
        )
        return u, d

    def revocation_recovery(self):
        from app.privacy_credentials import (
            CredentialBox,
            CredentialUnavailable,
            GlobalLogout,
        )
        from app.privacy_revocation import RevocationWorker

        # Pause only the rehearsal's earlier queues to isolate recovery cases.
        with self.connect() as c:
            c.execute(
                "update privacy_followup_tasks set due_at=clock_timestamp()+interval '1 day' where kind='revoke_sessions' and state='pending'"
            )
        u, d = self.accepted_password()
        saved = os.environ["C15_REVOCATION_KEYS"]
        os.environ["C15_REVOCATION_KEYS"] = "{}"
        try:
            try:
                CredentialBox.configured()
            except CredentialUnavailable:
                pass
            else:
                raise RuntimeError("missing_key_not_closed")
            assert self.sql(
                "select 1 from privacy_revocation_credentials where request_id=%s",
                (d["request_id"],),
            )
        finally:
            os.environ["C15_REVOCATION_KEYS"] = saved
        seen = [False]

        def uncertain(_url, **kw):
            response = self.http.post(self.url("auth") + "/logout?scope=global", **kw)
            if not seen[0]:
                seen[0] = True
                response.close()
                raise requests.Timeout()
            return response

        worker = RevocationWorker(
            lambda: self.connect("usage_executor"),
            logout=GlobalLogout(
                CredentialBox.configured(),
                "https://local-rehearsal.invalid",
                self.anon,
                uncertain,
            ),
        )
        assert worker.run_one()
        assert not self.sql("select 1 from auth.sessions where user_id=%s", (u["id"],))
        # Worker sees uncertain delivery, not a fabricated successful receipt.
        assert (
            self.sql(
                "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
                (d["request_id"],),
            )[0][0]
            == "pending"
        )
        with self.connect() as c:
            c.execute(
                "update privacy_followup_tasks set due_at=clock_timestamp() where request_id=%s and kind='revoke_sessions'",
                (d["request_id"],),
            )
        restarted = RevocationWorker(
            lambda: self.connect("usage_executor"), logout=worker.logout
        )
        assert restarted.run_one()
        state = self.sql(
            "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
            (d["request_id"],),
        )[0][0]
        assert state in ("succeeded", "blocked")
        assert not self.sql(
            "select 1 from privacy_revocation_credentials where request_id=%s",
            (d["request_id"],),
        )
        expired, request = self.accepted_password()
        with self.connect() as c:
            c.execute(
                "update privacy_revocation_credentials set expires_at=clock_timestamp()-interval '1 second' where request_id=%s",
                (request["request_id"],),
            )
        assert restarted.run_one()
        assert (
            self.sql(
                "select state from privacy_followup_tasks where request_id=%s and kind='revoke_sessions'",
                (request["request_id"],),
            )[0][0]
            == "blocked"
        )
        assert not self.sql(
            "select 1 from privacy_revocation_credentials where request_id=%s",
            (request["request_id"],),
        )
        assert self.sql(
            "select 1 from auth.sessions where user_id=%s", (expired["id"],)
        )
        self.save(
            "revocation-recovery.json",
            {
                "uncertain_retry_terminal": state,
                "expired_credential": "blocked; no false revocation success",
                "key_outage": "no claim before restored key",
                "delivered_logout_session_absence": True,
            },
        )

    def identity_boundaries(self):
        from urllib.parse import parse_qs, urlsplit

        deleted = self.user()
        doc = self.document()
        self.check(self.call(deleted, "begin", doc), 200, "identity_begin")
        time.sleep(1.1)
        deleted.update(self.login(deleted["email"]))
        self.check(self.call(deleted, "challenge", doc), 200, "identity_challenge")
        self.check(
            self.call(deleted, "confirm", doc, confirmation_text="delete"),
            200,
            "identity_delete",
        )
        self.check(
            self.auth(
                "/admin/users/" + deleted["id"],
                method="PUT",
                body={"email": uuid4().hex + "@example.invalid"},
            ),
            200,
            "identity_email_release_fixture",
        )
        active = self.user()
        requested = self.auth(
            "/user",
            method="PUT",
            body={"email": deleted["email"]},
            token=active["access_token"],
        )
        verify_status: list[int] = []
        if requested.status_code == 200:
            until = time.monotonic() + 5
            while time.monotonic() < until and not verify_status:
                for address in [active["email"], deleted["email"]]:
                    for msg in self.messages(address):
                        for link in re.findall(r'http[^\s<>"\)]+', msg.get("Text", "")):
                            q = parse_qs(urlsplit(link.replace("&amp;", "&")).query)
                            if q.get("type") == ["email_change"]:
                                verify_status.append(
                                    self.auth(
                                        "/verify",
                                        body={
                                            "type": "email_change",
                                            "token_hash": q["token"][0],
                                        },
                                        token=self.anon,
                                    ).status_code
                                )
                if not verify_status:
                    time.sleep(0.1)
        state = self.check(
            self.auth("/admin/users/" + active["id"], method="GET"),
            200,
            "identity_inspect",
        )
        changed = state["email"] == deleted["email"]
        login = (
            self.auth(
                "/token?grant_type=password",
                body={"email": deleted["email"], "password": self.password},
            )
            if changed
            else None
        )
        if changed:
            assert login is not None
            assert login.status_code != 200
            try:
                with self.connect() as c:
                    c.execute(
                        "insert into profiles(user_id) values(%s)", (active["id"],)
                    )
            except psycopg.Error as error:
                assert error.sqlstate == "42501"
            else:
                raise RuntimeError("suppressed_email_bootstrap_allowed")
        linking = self.auth(
            "/user/identities/authorize?provider=google&redirect_to=http://127.0.0.1:5396",
            method="GET",
            token=active["access_token"],
        )
        assert linking.status_code != 200
        admin_create = self.auth(
            "/admin/users",
            body={
                "email": deleted["email"],
                "password": self.password,
                "email_confirm": True,
            },
        )
        admin_identity_created = admin_create.status_code == 200
        admin_login_blocked = None
        if admin_identity_created:
            made = admin_create.json()
            admin_login_blocked = (
                self.auth(
                    "/token?grant_type=password",
                    body={"email": deleted["email"], "password": self.password},
                ).status_code
                != 200
            )
            assert admin_login_blocked
            try:
                with self.connect() as c:
                    c.execute("insert into profiles(user_id) values(%s)", (made["id"],))
            except psycopg.Error as error:
                assert error.sqlstate == "42501"
            else:
                raise RuntimeError("privileged_import_bootstrap_allowed")
        self.save(
            "identity-boundaries.json",
            {
                "privileged_auth_identity_created": admin_identity_created,
                "privileged_import_session_and_bootstrap_blocked": admin_login_blocked,
                "email_change_request_status": requested.status_code,
                "confirmation_statuses": verify_status,
                "identity_email_committed": changed,
                "session_issuance_blocked_if_changed": login is not None
                and login.status_code != 200,
                "google_linking": "provider disabled; real Google OAuth unsupported in this rehearsal",
                "admin_email_mutation": "privileged fixture accepted; creation hook does not cover all identity mutations",
            },
        )

    def hook_failures(self):
        email = uuid4().hex + "@example.invalid"
        with self.connect() as c:
            c.execute("update privacy_matching_keys set current_key=false")
        try:
            assert (
                self.auth(
                    "/signup",
                    body={"email": email, "password": self.password},
                    token=self.anon,
                ).status_code
                != 200
            )
        finally:
            with self.connect() as c:
                c.execute(
                    "update privacy_matching_keys set current_key=true where version=1"
                )
        # Test the real engine's PostgreSQL hook caller ACL and timeout.
        with self.connect() as c:
            c.execute(
                "revoke execute on function privacy_auth_before_create(jsonb) from supabase_auth_admin"
            )
        try:
            assert (
                self.auth(
                    "/signup",
                    body={"email": email, "password": self.password},
                    token=self.anon,
                ).status_code
                != 200
            )
        finally:
            with self.connect() as c:
                c.execute(
                    "grant execute on function privacy_auth_before_create(jsonb) to supabase_auth_admin"
                )
        with self.connect() as hold:
            hold.execute("lock privacy_matching_keys in access exclusive mode")
            assert (
                self.auth(
                    "/signup",
                    body={"email": email, "password": self.password},
                    token=self.anon,
                ).status_code
                != 200
            )
        unaffected = self.user()
        assert unaffected["access_token"]

    def cleanup(self):
        failures = []
        for name in reversed(self.created):
            if docker("inspect", name, check=False).returncode != 0:
                continue
            if (
                docker(
                    "inspect",
                    "-f",
                    '{{ index .Config.Labels "c15.rehearsal" }}',
                    name,
                    check=False,
                ).stdout.strip()
                != self.name
            ):
                failures.append("ownership:" + name)
                continue
            if docker("rm", "-f", name, check=False).returncode:
                failures.append(name)
        for v in self.volumes:
            if (
                docker(
                    "volume",
                    "inspect",
                    "-f",
                    '{{ index .Labels "c15.rehearsal" }}',
                    v,
                    check=False,
                ).stdout.strip()
                != self.name
            ):
                failures.append("ownership:" + v)
                continue
            if docker("volume", "rm", v, check=False).returncode:
                failures.append(v)
        network = docker(
            "network",
            "inspect",
            "-f",
            '{{ index .Labels "c15.rehearsal" }}',
            self.name,
            check=False,
        )
        if network.returncode == 0:
            if network.stdout.strip() != self.name:
                failures.append("network_ownership")
            elif docker("network", "rm", self.name, check=False).returncode:
                failures.append(self.name)
        self.save(
            "cleanup.json",
            {
                "failures": failures,
                "remaining_containers": docker(
                    "ps", "-aq", "--filter", "label=c15.rehearsal=" + self.name
                ).stdout.splitlines(),
                "remaining_volumes": docker(
                    "volume", "ls", "-q", "--filter", "label=c15.rehearsal=" + self.name
                ).stdout.splitlines(),
                "remaining_networks": docker(
                    "network",
                    "ls",
                    "-q",
                    "--filter",
                    "label=c15.rehearsal=" + self.name,
                ).stdout.splitlines(),
                "published_ports": [],
                "ephemeral_configuration": "in memory and removed owned container environment; no secret files",
            },
        )
        self.http.close()


class ActualStorage:
    def __init__(self, rehearsal):
        from collections.abc import Callable

        self.r = rehearsal
        self.after_remove: Callable[[str, str], None] | None = None

    def request(self, method, path, token=None, **kw):
        return self.r.http.request(
            method,
            self.r.url("storage") + path,
            headers={
                "Authorization": "Bearer " + (token or self.r.service),
                "apikey": self.r.anon,
                "Content-Type": (
                    "application/zip" if "/exports/" in path else "text/plain"
                )
                if "data" in kw
                else "application/json",
            },
            timeout=10,
            **kw,
        )

    def stat(self, bucket, key):
        result = self.request("GET", "/object/" + bucket + "/" + key, stream=True)
        try:
            if result.status_code == 200:
                return result.headers.get("ETag")
            if result.status_code in (400, 404):
                body = result.json()
                if str(body.get("statusCode")) == "404" or body.get("error") in (
                    "not_found",
                    "Not Found",
                ):
                    return None
            if result.status_code in (401, 403):
                raise PermissionError()
            raise RuntimeError("actual_storage_stat_unavailable")
        finally:
            result.close()

    def read(self, bucket, key, version):
        result = self.request("GET", "/object/" + bucket + "/" + key, stream=True)
        try:
            assert result.status_code == 200 and result.headers.get("ETag") == version
            yield from result.iter_content(4096)
        finally:
            result.close()

    def put(self, bucket, key, source):
        result = self.request("POST", "/object/" + bucket + "/" + key, data=source)
        self.r.check(result, 200, "artifact_put")

    def remove(self, bucket, key):
        self.r.check(
            self.request("DELETE", "/object/" + bucket, json={"prefixes": [key]}),
            200,
            "object_remove",
        )
        if self.after_remove is not None:
            self.after_remove(bucket, key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--checkpoint-only", action="store_true")
    parser.add_argument("--identity-only", action="store_true")
    parser.add_argument("--phase", choices=["install", "test"], default="test")
    args = parser.parse_args()
    path = args.evidence_dir.resolve()
    if not args.inside:
        assert path.is_relative_to(ROOT / "docs/evidence")
    r = Rehearsal(path, internal=args.inside)
    try:
        if args.inside:
            if args.phase == "install":
                r.install()
            else:
                r.wait("auth", "/health")
                if args.identity_only:
                    r.configure_app()
                    r.scenario(
                        "normal_identity_cleanup_after_successful_logout",
                        r.identity_cleanup_normal,
                    )
                    r.client.close()
                    if any(x["result"] == "failed" for x in r.results):
                        raise RuntimeError("identity_scenario_failed")
                elif args.checkpoint_only:
                    r.scenario(
                        "actual_database_remote_checkpoint_process",
                        r.checkpoint_services,
                    )
                    if any(x["result"] == "failed" for x in r.results):
                        raise RuntimeError("checkpoint_scenario_failed")
                else:
                    r.scenarios()
        else:
            r.setup()
            config = json.dumps(
                {"secret": r.secret, "password": r.password, "name": r.name}
            )
            for phase in ["install", "test"]:
                if phase == "test":
                    docker("rm", "-f", r.name + "-auth")
                    r.created.remove(r.name + "-auth")
                    r.auth_env.update(
                        GOTRUE_HOOK_BEFORE_USER_CREATED_ENABLED="true",
                        GOTRUE_HOOK_BEFORE_USER_CREATED_URI="pg-functions://postgres/public/privacy_auth_before_create",
                        GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED="true",
                        GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI="pg-functions://postgres/public/privacy_auth_token",
                    )
                    r.run("auth", r.auth_env, container_port=9999)
                name = r.name + "-client-" + phase
                r.created.append(name)
                result = docker(
                    "run",
                    "--name",
                    name,
                    "--label",
                    "c15.rehearsal=" + r.name,
                    "--network",
                    r.name,
                    "-e",
                    "C15_ISOLATED_CONFIG=" + config,
                    "-v",
                    str(ROOT) + ":/repo:ro",
                    "-v",
                    str(path) + ":/evidence",
                    "-v",
                    r.name + "-storage:/storage-evidence:ro",
                    r.runner,
                    "python",
                    "/repo/scripts/c15_actual_engines.py",
                    "--inside",
                    "--phase",
                    phase,
                    "--evidence-dir",
                    "/evidence",
                    *(["--checkpoint-only"] if args.checkpoint_only else []),
                    *(["--identity-only"] if args.identity_only else []),
                    check=False,
                )
                print(result.stdout, flush=True)
                if result.returncode:
                    for service in ["auth", "storage"] if phase == "install" else []:
                        z = docker("logs", r.name + "-" + service, check=False)
                        log = z.stdout + z.stderr
                        for value in [r.secret, r.password, r.anon, r.service]:
                            log = log.replace(value, "[REDACTED]")
                        log = re.sub(
                            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "[EMAIL]", log
                        )
                        log = re.sub(
                            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                            "[JWT]",
                            log,
                        )
                        log = re.sub(r'(token=)[^&\s"\\]+', r"\1[REDACTED]", log)
                        (r.out / (service + "-startup.txt")).write_text(
                            log[-6000:], encoding="utf-8"
                        )
                    # No traceback/body/capabilities enter the persistent report.
                    raise RuntimeError(
                        "isolated_client_failed:" + str(result.returncode)
                    )

    except Exception as error:  # noqa: BLE001 -- safe scenario categories; cleanup must always run
        if isinstance(error, psycopg.Error):
            r.save(
                "safe-error.json",
                {"sqlstate": error.sqlstate, "message": error.diag.message_primary},
            )
        print(
            "Rehearsal failed: "
            + (str(error) if isinstance(error, RuntimeError) else type(error).__name__),
            flush=True,
        )
        return 1
    finally:
        if not args.inside:
            r.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
