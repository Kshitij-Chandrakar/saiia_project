"""Owned actual-engine C15.5 acceptance. Never loads operational configuration."""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests
from c15_actual_engines import ROOT, Rehearsal, docker


class Local(Rehearsal):
    def setup(self):
        super().setup()
        base = self.runner
        if (
            base
            != "sha256:a8dc26bd1c55ecdebacdf174c8882f2043133bff952e5b996ec8903003e80204"
        ):
            raise RuntimeError("rehearsal base identity changed")
        self.runner = json.loads(
            docker("image", "inspect", "c15-admin-runner:20261103").stdout
        )[0]["Id"]
        self.save(
            "admin-runner-image.json",
            {
                "image_id": self.runner,
                "base_image_id": base,
                "added_project_dependency": "svix==2.9.1",
                "setup_traffic": "official PyPI package downloads only; no provider/customer traffic",
            },
        )

    def auth(self, path, method="POST", body=None, token=None):
        return self.http.request(
            method,
            self.url("auth") + path,
            json=body,
            headers={
                "Authorization": "Bearer " + (token or self.service),
                "apikey": self.anon,
            },
            timeout=10,
        )


def verify_totp(r, user):
    import base64
    import hashlib
    import hmac
    import struct
    import time

    factor = r.check(
        r.auth(
            "/factors",
            body={"factor_type": "totp", "friendly_name": "synthetic-admin"},
            token=user["access_token"],
        ),
        200,
        "admin_factor",
    )
    challenge = r.check(
        r.auth(
            "/factors/" + factor["id"] + "/challenge",
            body={},
            token=user["access_token"],
        ),
        200,
        "admin_challenge",
    )
    secret = factor["totp"]["secret"]
    secret += "=" * ((-len(secret)) % 8)
    raw = hmac.new(
        base64.b32decode(secret),
        struct.pack(">Q", int(time.time()) // 30),
        hashlib.sha1,
    ).digest()
    off = raw[-1] & 15
    code = f"{(struct.unpack('>I', raw[off : off + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"
    result = r.check(
        r.auth(
            "/factors/" + factor["id"] + "/verify",
            body={"challenge_id": challenge["id"], "code": code},
            token=user["access_token"],
        ),
        200,
        "admin_verify",
    )
    result["fixture_totp_secret"] = factor["totp"]["secret"]
    return result


def normal_application(r):
    import socket
    import subprocess
    import threading
    import time

    def port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    name = r.name + "-application-relay"
    r.created.append(name)
    args = [
        "create",
        "--name",
        name,
        "--label",
        "c15.rehearsal=" + r.name,
        "--network",
        r.name,
        "-v",
        str(ROOT) + ":/repo:ro",
    ]
    for service, inside_port in {
        "db": 15432,
        "auth": 19999,
        "storage": 15000,
        "rest": 13000,
        "mail": 18025,
        "smtp": 11025,
    }.items():
        r.ports[service] = port()
        args += ["-p", f"127.0.0.1:{r.ports[service]}:{inside_port}"]
    docker(*args, r.runner, "python", "/repo/scripts/c15_loopback_proxy.py")
    docker("network", "connect", "bridge", name)
    docker("start", name)
    r.wait("auth", "/health")
    users = [r.user() for _ in range(3)]
    users[0]["proof"] = verify_totp(r, users[0])
    users[1]["proof"] = verify_totp(r, users[1])
    users[2]["proof"] = verify_totp(r, users[2])
    with r.connect() as c:
        for user, role in zip(users[:2], ("super_admin", "admin")):
            c.execute(
                "insert into administration.memberships(subject,role,status,revision) values(%s,%s,'active',1)",
                (user["id"], role),
            )
    # Explicit preparation of an independently mounted local witness; never startup auto-initialization.
    import base64
    import secrets
    import tempfile

    sys.path.insert(0, str(ROOT / "backend"))
    from app.admin_restore import AdministrationRestore
    from app.privacy_checkpoint import LocalCheckpointStore
    from app.privacy_restore import RestoreJournal

    restore_temporary = tempfile.TemporaryDirectory(
        prefix="c15-admin-owned-checkpoint-"
    )
    restore_root = Path(restore_temporary.name)
    key = secrets.token_bytes(32)
    restore_profile = {
        **{
            name: str(uuid4())
            for name in ("environment", "dataset", "generation", "snapshot")
        },
        "key": base64.b64encode(key).decode(),
        "journal": str(restore_root / "journal"),
        "checkpoint": str(restore_root / "checkpoint.sqlite"),
        "witness": str(restore_root / "independent.sqlite"),
    }
    restore_dsn = f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=admin_restore_executor password={r.password} sslmode=disable"
    from app.commercial.executor_connection import connect_executor

    authority_restore = AdministrationRestore(
        lambda: connect_executor(restore_dsn, "admin_restore_executor"),
        RestoreJournal(restore_profile["journal"], {"v1": key}, "v1"),
        LocalCheckpointStore(
            restore_profile["checkpoint"],
            restore_profile["witness"],
            key,
            restore_profile["environment"],
            restore_profile["dataset"],
        ),
        restore_profile["generation"],
        restore_profile["snapshot"],
    )
    authority_restore.initialize_source()
    # Same fixed production connection checks; only the owned loopback DSN varies.
    os.environ.update(
        ADMIN_RESTORE_DSN=restore_dsn,
        ADMIN_RESTORE_CHECKPOINT=json.dumps(restore_profile),
        ADMIN_CONSOLE_ENABLED="true",
        ADMIN_CONSOLE_DSN=f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=admin_executor password={r.password} sslmode=disable",
        ADMIN_RETENTION_DSN=f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=admin_retention_executor password={r.password} sslmode=disable",
        ADMIN_DISPATCH_DSN=f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=admin_dispatch_executor password={r.password} sslmode=disable",
        SUBSCRIPTIONS_ENABLED="false",
        C15_RESTRICTIONS_REQUIRED="false",
        C15_RUNTIME_ENABLED="false",
        C15_RUNTIME_LOCAL_REHEARSAL="true",
        C15_RESTORE_BOOT_REQUIRED="false",
        SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=json.dumps(
            {"jwt_secret": r.secret, "issuer": "http://auth:9999/auth/v1"}
        ),
        PYTHON_DOTENV_DISABLED="1",
    )
    sys.path.insert(0, str(ROOT / "backend"))
    import psycopg
    from app.config import settings
    from c15_admin_business_acceptance import seed_billing

    with r.connect() as fixture:
        for role in ("usage_executor", "usage_binding_executor"):
            fixture.execute(
                psycopg.sql.SQL("alter role {} login password {}").format(
                    psycopg.sql.Identifier(role), psycopg.sql.Literal(r.password)
                )
            )
    fake_billing, billing_operation, paid_until = seed_billing(r, users[2]["id"])
    from app.commercial import billing_database as billing_module

    original_provider = billing_module.RazorpaySubscriptions
    billing_module.RazorpaySubscriptions = lambda *_: fake_billing.provider
    settings.SUBSCRIPTIONS_ENABLED = "true"
    settings.SUBSCRIPTIONS_DSN = f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=usage_executor password={r.password} sslmode=disable"
    settings.BILLING_ENABLED = "true"
    settings.BILLING_RENEWAL = "automatic"
    settings.BILLING_TOTAL_POLICY_REF = "synthetic.normal-wiring"
    settings.BILLING_DSN = f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user=usage_binding_executor password={r.password} sslmode=disable"
    settings.RAZORPAY_TEST_ACCOUNT_ID = "acc_synthetic"
    settings.RAZORPAY_TEST_WEBHOOK_SECRET = "synthetic-unused-local-test"
    settings.C15_RUNTIME_LOCAL_REHEARSAL = "true"
    settings.ADMIN_LOCAL_SMTP_PORT = r.ports["smtp"]
    os.environ.update(
        MARKETING_EMAILS_ENABLED="true",
        EMAIL_PROVIDER_MODE="live",
        RESEND_API_KEY="synthetic-unused-catcher",
    )
    settings.GRPC_REALTIME_ENABLED = True
    settings.GRPC_REALTIME_HOST = "127.0.0.1"
    settings.GRPC_REALTIME_PORT = port()
    settings.GRPC_STT_ENABLED = False
    settings.GRPC_ANSWER_STREAM_ENABLED = False
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        for user, role in zip(users, ("super_admin", "admin", None)):
            headers = {"Authorization": "Bearer " + user["access_token"]}
            response = client.get("/api/admin/me", headers=headers)
            assert response.status_code == (200 if role else 404)
            if role:
                assert response.json()["role"] == role
            if role == "super_admin":
                assert (
                    client.get("/api/admin/memberships", headers=headers).status_code
                    == 200
                )
        h = {"Authorization": "Bearer " + users[1]["access_token"]}
        denied = client.get("/api/admin/memberships", headers=h)
        assert denied.status_code == 404
        assert denied.headers["cache-control"] == "no-store"
        assert (
            client.get("/api/admin/users/" + users[0]["id"], headers=h).status_code
            == 404
        )
        assert client.get("/api/admin/unknown", headers=h).status_code == 404
        assert client.get("/api/admin/users/?after=bad", headers=h).status_code == 404
        r.save(
            "normal-pools.json",
            {
                "subscriptions_composed": app.state.subscriptions._service is not None,
                "billing_composed": app.state.billing is not None,
                "billing_enabled": (
                    app.state.billing.enabled if app.state.billing else False
                ),
                "dispatcher_billing_composed": app.state.administration.dispatcher.billing
                is not None,
                "admin_worker_alive": app.state.administration.thread.is_alive(),
                "restore_ready": app.state.administration.restore.ready(),
            },
        )
        assert app.state.billing is not None, "normal billing pool unavailable"
        proof_headers = {"Authorization": "Bearer " + users[0]["proof"]["access_token"]}
        cancel_review = client.post(
            "/api/admin/cancellations/review",
            headers=proof_headers,
            json={
                "target": users[2]["id"],
                "billing_id": billing_operation,
                "operation_id": str(uuid4()),
                "reason": "support",
            },
        )
        assert cancel_review.status_code == 200, cancel_review.status_code
        cancel = client.post(
            "/api/admin/cancellations/confirm",
            headers=proof_headers,
            json={"review_id": cancel_review.json()["review_id"], "confirm": True},
        )
        assert cancel.status_code == 200, cancel.status_code
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            outcome = client.get(
                "/api/admin/cancellations/" + cancel.json()["operation_id"],
                headers=proof_headers,
            )
            if outcome.status_code == 200 and outcome.json()["state"] == "confirmed":
                break
            time.sleep(0.1)
        else:
            with r.connect() as fixture:
                state = fixture.execute(
                    "select state,attempts,dispatched from administration.commands where id=%s",
                    (cancel.json()["operation_id"],),
                ).fetchone()
            r.save(
                "normal-cancellation-failure.json",
                {
                    "state": state,
                    "worker_alive": app.state.administration.thread.is_alive(),
                    "restore_ready": app.state.administration.restore.ready(),
                },
            )
            raise AssertionError(
                "normal cancellation worker did not confirm fake-provider result"
            )
        with r.connect() as fixture:
            assert (
                fixture.execute(
                    "select valid_until from account_plan_bindings where account_id=%s",
                    (users[2]["id"],),
                ).fetchone()[0]
                == paid_until
            )
        r.save(
            "normal-cancellation-worker.json",
            {
                "actual_main_billing_pool": True,
                "restricted_dispatcher": True,
                "fake_provider_only": True,
                "confirmed": True,
                "paid_expiry_preserved": True,
            },
        )
        with r.connect() as fixture:
            fixture.execute(
                "insert into user_settings(user_id,marketing_email_opt_in) values(%s,true) on conflict(user_id) do update set marketing_email_opt_in=true",
                (users[2]["id"],),
            )
        campaign = str(uuid4())
        for action, document in [
            (
                "save",
                {
                    "campaign_id": campaign,
                    "revision": "0",
                    "name": "Synthetic normal worker",
                    "subject": "Synthetic normal main campaign",
                    "body": "Synthetic locally captured message.",
                },
            ),
            ("preview", {"campaign_id": campaign}),
        ]:
            response = client.post(
                "/api/admin/campaigns/" + action, headers=proof_headers, json=document
            )
            assert response.status_code == 200, (action, response.status_code)
        audience = client.post(
            "/api/admin/campaigns/audience",
            headers=proof_headers,
            json={"campaign_id": campaign, "revision": "1"},
        )
        assert audience.status_code == 200, audience.status_code
        queued = client.post(
            "/api/admin/campaigns/confirm",
            headers=proof_headers,
            json={
                "review_id": audience.json()["review_id"],
                "operation_id": str(uuid4()),
                "confirm": True,
            },
        )
        assert queued.status_code == 200, queued.status_code
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = client.post(
                "/api/admin/campaigns/read",
                headers=proof_headers,
                json={"campaign_id": campaign},
            )
            if status.status_code == 200 and status.json()["state"] == "complete":
                break
            time.sleep(0.1)
        else:
            raise AssertionError("normal campaign worker did not finish")
        assert status.json()["results"].get("accepted", 0) >= 1, status.json()[
            "results"
        ]
        messages = r.http.get(r.url("mail") + "/api/v1/messages", timeout=5).json()[
            "messages"
        ]
        assert any(
            message["Subject"] == "Synthetic normal main campaign"
            for message in messages
        )
        r.save(
            "normal-campaign-worker.json",
            {
                "actual_main_lifespan": True,
                "durable_dispatcher": True,
                "actual_mailpit": True,
                "provider_acceptance_not_delivery": True,
                "real_emails": False,
            },
        )
        import grpc
        from app.grpc_generated import interview_realtime_pb2 as pb
        from app.grpc_generated import interview_realtime_pb2_grpc as rpc

        channel = grpc.insecure_channel("127.0.0.1:" + str(settings.GRPC_REALTIME_PORT))
        try:
            grpc.channel_ready_future(channel).result(timeout=8)
            rpc.InterviewRealtimeServiceStub(channel).CheckHealth(pb.Empty(), timeout=5)
        finally:
            channel.close()
    r.save(
        "normal-application.json",
        {
            "actual_main_lifespan": True,
            "restricted_admin_runtime_principal": True,
            "grpc_health_rpc": True,
            "actual_auth_jwt": True,
            "customer_and_staff_denials": True,
            "external_ai_payment_calls": False,
            "scope": "authority and read projections only; not staff-restriction/worker acceptance",
        },
    )
    import uvicorn

    application_port, browser_port = port(), port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=application_port,
            log_level="error",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    vite = None
    try:
        deadline = time.monotonic() + 30
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("normal_browser_backend_failed")
        environment = {
            **os.environ,
            "C15_ADMIN_BACKEND": f"http://127.0.0.1:{application_port}",
            "C15_ADMIN_AUTH": r.url("auth"),
            "C15_ADMIN_PORT": str(browser_port),
            "C15_ADMIN_BROWSER": f"http://127.0.0.1:{browser_port}",
            "C15_ADMIN_FIXTURES": json.dumps(
                {
                    "users": [
                        {
                            "email": u["email"],
                            "user_id": u["id"],
                            "factor_secret": u.get("proof", {}).get(
                                "fixture_totp_secret"
                            ),
                        }
                        for u in users
                    ],
                    "password": r.password,
                }
            ),
            "C15_ADMIN_EVIDENCE": str(r.out),
            "VITE_SUPABASE_URL": f"http://127.0.0.1:{browser_port}",
            "VITE_SUPABASE_ANON_KEY": r.anon,
            "VITE_BACKEND_URL": f"http://127.0.0.1:{browser_port}",
        }
        vite = subprocess.Popen(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--config",
                "tests/c15-admin/actual.vite.config.js",
            ],
            cwd=ROOT / "frontend",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 30
        last_readiness_error = None
        while time.monotonic() < deadline:
            try:
                if (
                    r.http.get(
                        f"http://127.0.0.1:{browser_port}/auth/login", timeout=1
                    ).status_code
                    == 200
                ):
                    break
            except requests.RequestException as error:
                last_readiness_error = type(error).__name__
            if vite.poll() is not None:
                raise RuntimeError("normal_browser_vite_failed")
            time.sleep(0.1)
        else:
            raise RuntimeError(
                "normal_browser_vite_timeout:" + str(last_readiness_error)
            )
        outcome = subprocess.run(
            ["node", "tests/c15-admin/actual.run.mjs"],
            cwd=ROOT / "frontend",
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if outcome.returncode:
            # Only named safe scenario categories; no browser request/credential traces.
            r.save(
                "browser-failure.json",
                {"category": "admin_browser_failed", "exit_code": outcome.returncode},
            )
            import re

            print(re.findall(r"admin_browser_failed:[a-z_]+:[0-9]+", outcome.stderr))
            raise RuntimeError("admin_browser_failed")
        vite.terminate()
        vite.wait(timeout=15)
        environment["C15_ADMIN_FULL_APP"] = "true"
        vite = subprocess.Popen(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--config",
                "tests/c15-admin/actual.vite.config.js",
            ],
            cwd=ROOT / "frontend",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                if (
                    r.http.get(
                        environment["C15_ADMIN_BROWSER"] + "/src/main.jsx", timeout=2
                    ).status_code
                    == 200
                ):
                    break
            except requests.RequestException as error:
                r.save("normal-vite-wait.json", {"category": type(error).__name__})
            time.sleep(0.1)
        full_result = subprocess.run(
            ["node", "tests/c15-admin/actual.run.mjs"],
            cwd=ROOT / "frontend",
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if full_result.returncode:
            r.save(
                "full-browser-failure.json",
                {
                    "category": "normal_app_browser_failed",
                    "exit_code": full_result.returncode,
                },
            )
            raise RuntimeError("normal_app_browser_failed")
    finally:
        if vite is not None:
            vite.terminate()
            vite.wait(timeout=15)
        server.should_exit = True
        thread.join(timeout=20)
        billing_module.RazorpaySubscriptions = original_provider
        restore_temporary.cleanup()
        r.save(
            "admin-checkpoint-cleanup.json",
            {
                "owned_directory_removed": not restore_root.exists(),
                "ephemeral_key_persisted": False,
            },
        )
        if thread.is_alive():
            raise RuntimeError("owned_application_shutdown_failed")
        listeners = []
        for value in (application_port, browser_port, settings.GRPC_REALTIME_PORT):
            with socket.socket() as listener:
                listener.settimeout(1)
                if listener.connect_ex(("127.0.0.1", value)) == 0:
                    listeners.append(value)
        r.save(
            "application-cleanup.json", {"owned_application_listeners_open": listeners}
        )
        if listeners:
            raise RuntimeError("owned_application_listener_open")


def inside(evidence, phase):
    import psycopg

    r = Local(evidence, internal=True)
    if phase == "install":
        r.install()
        return
    r.wait("auth", "/health")
    people = [r.user() for _ in range(5)]
    for user in people[:2]:
        verify_totp(r, user)
    s1, s2, admin, customer, other = [u["id"] for u in people]
    # Owner installs fixtures only. Runtime assertions use independent LOGINs.
    with r.connect() as c:
        c.execute("update administration.configuration set bootstrap_subject=%s", (s1,))
        for role in (
            "admin_executor",
            "admin_bootstrap_executor",
            "admin_retention_executor",
            "admin_dispatch_executor",
            "admin_restore_executor",
        ):
            c.execute(
                psycopg.sql.SQL("alter role {} login password {}").format(
                    psycopg.sql.Identifier(role), psycopg.sql.Literal(r.password)
                )
            )

    def call(actor, action, doc=None, session=None, presence=None):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_call(%s,%s,%s,%s,%s::jsonb)",
                (actor, session, presence, action, json.dumps(doc or {})),
            ).fetchone()[0]

    with r.connect("admin_bootstrap_executor") as c:
        assert (
            c.execute(
                "select public.administration_bootstrap(%s,%s,%s)",
                (s2, people[1]["email"], uuid4()),
            ).fetchone()[0]["error"]
            == "bootstrap_denied"
        )
        assert (
            c.execute(
                "select public.administration_bootstrap(%s,%s,%s)",
                (s1, people[0]["email"], uuid4()),
            ).fetchone()[0]["state"]
            == "confirmed"
        )
    assert call(s1, "me")["error"] == "unavailable"
    with r.connect() as c:
        c.execute("update administration.configuration set enabled=true")
        c.execute(
            "insert into administration.memberships(subject,role,status,revision) values(%s,'super_admin','active',1),(%s,'admin','active',1)",
            (s2, admin),
        )
    assert call(s1, "me")["role"] == "super_admin"
    assert call(admin, "me")["role"] == "admin"
    assert call(customer, "me")["error"] == "not_found"
    for op in ("audit", "memberships", "membership.review"):
        assert call(admin, op)["error"] == "not_found"
    assert call(s1, "me")["recovery_available"] is False
    results = [
        {
            "scenario": "actual_password_identities_and_live_two_role_authority",
            "passed": True,
        }
    ]
    for role in (
        "admin_executor",
        "admin_bootstrap_executor",
        "admin_retention_executor",
        "admin_dispatch_executor",
    ):
        with r.connect(role) as c:
            assert c.execute(
                "select session_user,current_user,current_setting('role'),rolsuper,rolbypassrls,rolinherit from pg_roles where rolname=session_user"
            ).fetchone() == (role, role, "none", False, False, False)
            assert not c.execute(
                "select exists(select 1 from pg_auth_members where member=(select oid from pg_roles where rolname=session_user))"
            ).fetchone()[0]
        for sql in (
            "select * from administration.memberships",
            "delete from administration.audit",
            "truncate administration.audit",
            "update administration.configuration set enabled=true",
            "set role postgres",
        ):
            try:
                with r.connect(role) as c:
                    c.execute(sql)
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("runtime_privilege_broadened")
    for role in ("anon", "authenticated", "service_role"):
        assert not r.sql(
            "select has_function_privilege(%s,'public.administration_call(uuid,uuid,timestamptz,text,jsonb)','execute')",
            (role,),
        )[0][0]
    for sql in (
        "update administration.audit set outcome='modified'",
        "delete from administration.audit",
        "truncate administration.audit, administration.audit_references",
    ):
        try:
            with r.connect() as c:
                c.execute(sql)
        except psycopg.Error as error:
            assert error.sqlstate == "55000"
        else:
            raise AssertionError("immutable_audit_guard_missing")
    results.append(
        {
            "scenario": "restricted_principals_direct_dml_role_escalation_denial",
            "passed": True,
        }
    )
    now = datetime.now(timezone.utc)

    def review(actor, target, role="admin", status="active", op=None, session=None):
        session = session or str(uuid4())
        doc = {
            "target": target,
            "role": role,
            "status": status,
            "reason": "membership",
            "operation_id": str(op or uuid4()),
        }
        return call(actor, "membership.review", doc, session, now), session

    v, session = review(s1, customer)
    assert "review_id" in v
    assert (
        call(
            s1,
            "membership.confirm",
            {"review_id": v["review_id"], "confirm": True},
            str(uuid4()),
            now,
        )["error"]
        == "conflict"
    )

    def consume():
        return call(
            s1,
            "membership.confirm",
            {"review_id": v["review_id"], "confirm": True},
            session,
            now,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: consume(), range(2)))
    assert replies[0] == replies[1] and replies[0]["state"] == "confirmed"
    assert call(customer, "me")["role"] == "admin"
    assert call(admin, "receipt", {"id": v["operation_id"]})["error"] == "not_found"
    a, sa = review(s1, s2)
    b, sb = review(s2, s1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(
            call,
            s1,
            "membership.confirm",
            {"review_id": a["review_id"], "confirm": True},
            sa,
            now,
        )
        two = pool.submit(
            call,
            s2,
            "membership.confirm",
            {"review_id": b["review_id"], "confirm": True},
            sb,
            now,
        )
        outcomes = [one.result(), two.result()]
    assert sum(x.get("state") == "confirmed" for x in outcomes) == 1
    remaining = [x for x in (s1, s2) if call(x, "me").get("role") == "super_admin"]
    assert len(remaining) == 1
    last = remaining[0]
    v, session = review(last, last, status="suspended")
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": v["review_id"], "confirm": True},
            session,
            now,
        )["error"]
        == "last_super_admin"
    )
    expired, expired_session = review(last, admin)
    with r.connect() as c:
        c.execute(
            "update administration.reviews set expires_at=clock_timestamp()-interval '1 second' where id=%s",
            (expired["review_id"],),
        )
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": expired["review_id"], "confirm": True},
            expired_session,
            now,
        )["error"]
        == "conflict"
    )
    stale, stale_session = review(last, admin)
    own, own_session = review(last, last, role="super_admin")
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": own["review_id"], "confirm": True},
            own_session,
            now,
        )["state"]
        == "confirmed"
    )
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": stale["review_id"], "confirm": True},
            stale_session,
            now,
        )["error"]
        == "conflict"
    )
    results.append(
        {
            "scenario": "concurrent_confirmation_replay_actor_session_binding_last_super_admin",
            "passed": True,
        }
    )
    # No untrusted role claim is read; old commercial permission cannot regain access.
    with r.connect() as c:
        c.execute(
            "insert into public.subscription_admin_permissions(subject_id,permission,revision,active,approved_by,reason) values(%s,'subscriptions.manage',1,true,%s,'synthetic')",
            (other, other),
        )
        assert (
            c.execute(
                "select administration.permission(%s,'subscriptions.manage')", (other,)
            ).fetchone()[0]
            is False
        )
        assert (
            c.execute(
                "select administration.permission(%s,'billing.manage')", (last,)
            ).fetchone()[0]
            is False
        )
        c.execute("update administration.configuration set enabled=false")
        assert (
            c.execute(
                "select administration.permission(%s,'subscriptions.manage')", (other,)
            ).fetchone()[0]
            is False
        )
        c.execute("update administration.configuration set enabled=true")
    results.append(
        {
            "scenario": "legacy_grants_not_alternate_authority_and_no_blanket_billing_manage",
            "passed": True,
        }
    )
    for subject, expected in (
        (last, ["subscriptions.manage"]),
        (admin, []),
        (other, []),
    ):
        identity = next(user for user in people if user["id"] == subject)
        response = r.http.post(
            r.url("rest") + "/rpc/subscription_admin_self_probe",
            json={},
            headers={
                "Authorization": "Bearer " + identity["access_token"],
                "apikey": r.anon,
            },
            timeout=10,
        )
        assert response.status_code == 200
        assert response.json()["permissions"] == expected
    results.append(
        {
            "scenario": "actual_postgrest_catalog_probe_super_only_and_legacy_grant_denial",
            "passed": True,
        }
    )
    with r.connect("admin_executor") as c:
        directory = c.execute(
            "select public.administration_read(%s,'users')", (admin,)
        ).fetchone()[0]
        assert {str(x["user_id"]) for x in directory["items"]} == {other}
        for staff in (s1, s2, admin, customer):
            assert (
                c.execute(
                    "select public.administration_read(%s,'user',%s)", (admin, staff)
                ).fetchone()[0]["error"]
                == "not_found"
            )
        for item in directory["items"]:
            assert set(item) == {
                "user_id",
                "email",
                "registered_at",
                "email_verified",
                "deletion_restricted",
                "data_as_of",
            }
    results.append(
        {
            "scenario": "database_customer_directory_staff_exclusion_and_exact_allowlist",
            "passed": True,
        }
    )
    # Real GoTrue-signed tokens through the actual route and verifier, no endpoint interception.
    import socket
    import threading

    import jwt
    from c15_loopback_proxy import serve

    threading.Thread(target=serve, args=(15432, ("db", 5432)), daemon=True).start()
    # Wait on the actual local listener, not an arbitrary startup delay.
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", 15432), timeout=1):
                break
        except OSError:
            continue
    else:
        raise RuntimeError("local_database_relay_unavailable")
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1",
        ADMIN_CONSOLE_ENABLED="true",
        ADMIN_CONSOLE_DSN=f"host=127.0.0.1 port=15432 dbname=postgres user=admin_executor password={r.password} sslmode=disable",
        ADMIN_RETENTION_DSN=f"host=127.0.0.1 port=15432 dbname=postgres user=admin_retention_executor password={r.password} sslmode=disable",
        ADMIN_DISPATCH_DSN=f"host=127.0.0.1 port=15432 dbname=postgres user=admin_dispatch_executor password={r.password} sslmode=disable",
        SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=json.dumps(
            {
                "jwt_secret": r.secret,
                "issuer": jwt.decode(
                    people[2]["access_token"], options={"verify_signature": False}
                )["iss"],
            }
        ),
        SUBSCRIPTIONS_ENABLED="false",
        C15_RESTRICTIONS_REQUIRED="false",
        GRPC_REALTIME_ENABLED="false",
    )
    sys.path.insert(0, str(ROOT / "backend"))
    import base64
    import secrets
    import tempfile

    from app.admin_restore import AdministrationRestore
    from app.administration import configured, router
    from app.config import settings
    from app.privacy_checkpoint import LocalCheckpointStore
    from app.privacy_restore import RestoreJournal
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    checkpoint_directory = tempfile.TemporaryDirectory(prefix="owned-admin-checkpoint-")
    checkpoint_path = Path(checkpoint_directory.name)
    key = secrets.token_bytes(32)
    profile = {
        **{
            name: str(uuid4())
            for name in ("environment", "dataset", "generation", "snapshot")
        },
        "key": base64.b64encode(key).decode(),
        "journal": str(checkpoint_path / "journal"),
        "checkpoint": str(checkpoint_path / "checkpoint.sqlite"),
        "witness": str(checkpoint_path / "witness.sqlite"),
    }
    AdministrationRestore(
        lambda: r.connect("admin_restore_executor"),
        RestoreJournal(profile["journal"], {"v1": key}, "v1"),
        LocalCheckpointStore(
            profile["checkpoint"],
            profile["witness"],
            key,
            profile["environment"],
            profile["dataset"],
        ),
        profile["generation"],
        profile["snapshot"],
    ).initialize_source()
    settings.ADMIN_RESTORE_DSN = f"host=127.0.0.1 port=15432 dbname=postgres user=admin_restore_executor password={r.password} sslmode=disable"
    settings.ADMIN_RESTORE_CHECKPOINT = json.dumps(profile)
    settings.C15_RUNTIME_LOCAL_REHEARSAL = "true"
    app = FastAPI()
    app.include_router(router)
    app.state.administration = configured(settings)
    with TestClient(app) as client:
        h = {"Authorization": "Bearer " + people[2]["access_token"]}
        response = client.get("/api/admin/me", headers=h)
        assert response.status_code == 200, response.status_code
        assert response.json()["role"] == "admin"
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/admin/audit", headers=h).status_code == 404
        assert client.get("/api/admin/memberships", headers=h).status_code == 404
        assert client.get("/api/admin/users/" + s1, headers=h).status_code == 404
        assert len(client.get("/api/admin/users", headers=h).json()["items"]) == 1
        assert client.get("/api/admin/users?search=", headers=h).status_code == 400
        assert client.post(
            "/api/admin/memberships/review", json={}, headers=h
        ).status_code in (403, 404)
        assert client.get("/api/admin/me").status_code == 401
    results.append(
        {
            "scenario": "actual_auth_signed_jwt_http_no_store_and_negative_access",
            "passed": True,
        }
    )
    r.totp()
    results.append(
        {
            "scenario": "actual_auth_totp_and_refresh_only_presence_regression",
            "passed": True,
        }
    )
    protected = r.user()
    verified = verify_totp(r, protected)
    v, sid = review(last, protected["id"], role="super_admin")
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": v["review_id"], "confirm": True},
            sid,
            now,
        )["state"]
        == "confirmed"
    )
    document = {
        "target": other,
        "role": "admin",
        "status": "active",
        "reason": "membership",
        "operation_id": str(uuid4()),
    }
    with TestClient(app) as client:
        h = {"Authorization": "Bearer " + protected["access_token"]}
        assert (
            client.post(
                "/api/admin/memberships/review", json=document, headers=h
            ).status_code
            == 403
        )
        h = {"Authorization": "Bearer " + verified["access_token"]}
        response = client.post(
            "/api/admin/memberships/review", json=document, headers=h
        )
        assert response.status_code == 200
        doc = {"review_id": response.json()["review_id"], "confirm": True}
        one = client.post("/api/admin/memberships/confirm", json=doc, headers=h)
        two = client.post("/api/admin/memberships/confirm", json=doc, headers=h)
        assert one.status_code == two.status_code == 200 and one.json() == two.json()
        coupon_id = str(uuid4())
        coupon_document = {
            "code": "LOCAL_ONLY",
            "expected": "0",
            "operation_id": str(uuid4()),
            "source_discount_id": None,
        }
        assert (
            client.post(
                "/api/admin/coupons/" + coupon_id,
                json={**coupon_document, "operation_id": {}},
                headers=h,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/admin/users/search",
                json={"search": "synthetic@example.invalid", "after": []},
                headers=h,
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/api/admin/coupons",
                headers={"Authorization": "Bearer " + people[2]["access_token"]},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/admin/coupons/" + coupon_id,
                json={**coupon_document, "eligibility": "invented"},
                headers=h,
            ).status_code
            == 400
        )
        first = client.post(
            "/api/admin/coupons/" + coupon_id, json=coupon_document, headers=h
        )
        replay = client.post(
            "/api/admin/coupons/" + coupon_id, json=coupon_document, headers=h
        )
        assert (
            first.status_code == replay.status_code == 200
            and first.json() == replay.json()
        )
        assert first.json()["redemption_available"] is False
        configuration = client.get("/api/admin/coupons", headers=h).json()["items"][0]
        for field in (
            "eligibility",
            "stacking",
            "redemption_limits",
            "timing_duration",
            "quote_provider_policy",
        ):
            assert configuration[field] is None
        assert (
            client.post(
                "/api/admin/coupons/" + coupon_id + "/redeem", json={}, headers=h
            ).status_code
            == 404
        )
        refresh = r.check(
            r.auth(
                "/token?grant_type=refresh_token",
                body={"refresh_token": verified["refresh_token"]},
            ),
            200,
            "admin_refresh",
        )
        assert (
            client.post(
                "/api/admin/memberships/review",
                json={**document, "operation_id": str(uuid4())},
                headers={"Authorization": "Bearer " + refresh["access_token"]},
            ).status_code
            == 403
        )
    results.append(
        {
            "scenario": "actual_auth_totp_bound_membership_http_confirm_replay_and_refresh_denial",
            "passed": True,
        }
    )
    results.append(
        {
            "scenario": "inert_coupon_super_only_unset_terms_replay_and_redemption_denial",
            "passed": True,
        }
    )
    r.check(
        r.auth(
            "/admin/users/" + protected["id"], method="PUT", body={"ban_duration": "1h"}
        ),
        200,
        "synthetic_ineligible_staff_fixture",
    )
    revocation, sid = review(
        last, protected["id"], role="super_admin", status="revoked"
    )
    assert (
        call(
            last,
            "membership.confirm",
            {"review_id": revocation["review_id"], "confirm": True},
            sid,
            now,
        )["state"]
        == "confirmed"
    )
    assert call(last, "me")["role"] == "super_admin"
    assert call(protected["id"], "me")["error"] == "not_found"
    results.append(
        {
            "scenario": "ineligible_staff_membership_revocation_preserves_usable_super_admin",
            "passed": True,
        }
    )
    from c15_admin_access_acceptance import verify_access

    verify_access(
        r, last, admin, customer, other, results, app.state.administration.restore
    )
    from c15_admin_business_acceptance import (
        verify_admin_account_cleanup,
        verify_admin_restore,
        verify_campaign,
        verify_cancellation,
        verify_export_registry,
        verify_lifecycle,
        verify_metrics,
        verify_population,
        verify_successor,
    )

    from c15_admin_review_acceptance import verify_review_fixes

    verify_review_fixes(r, last, results)
    verify_metrics(r, last, results)
    verify_successor(r, last, results)
    verify_campaign(r, last, results)
    verify_cancellation(r, last, results)
    verify_population(r, last, results)
    verify_lifecycle(r, last, results)
    verify_export_registry(r, results)
    verify_admin_restore(r, last, results)
    verify_admin_account_cleanup(r, results)
    r.save(
        "authority-results.json",
        {
            "results": results,
            "scope": "actual Auth password identities and native PostgreSQL; not full C15.5 acceptance",
        },
    )
    checkpoint_directory.cleanup()
    print("PASS", len(results), "authority scenario groups", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inside", action="store_true")
    p.add_argument(
        "--backend-only",
        action="store_true",
        help="Run engine/native scenarios without the dependent UI slice",
    )
    p.add_argument("--phase", choices=("install", "tests"), default="tests")
    p.add_argument("--evidence-dir", type=Path, required=True)
    args = p.parse_args()
    if args.inside:
        inside(args.evidence_dir, args.phase)
        return
    # Do not import operational dotenv or inherit hosted service configuration.
    keep = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "APPDATA",
            "LOCALAPPDATA",
            "USERPROFILE",
            "COMSPEC",
        }
    }
    os.environ.clear()
    os.environ.update(keep, PYTHON_DOTENV_DISABLED="1")
    evidence = args.evidence_dir.resolve()
    assert evidence.is_relative_to(ROOT / "docs/evidence") and not evidence.exists()
    r = Local(evidence)
    import hashlib

    source_paths = [
        "backend/app/auth/supabase_auth.py",
        "backend/app/grpc_cloud_context.py",
        "backend/app/grpc_server.py",
        "backend/app/privacy_content.py",
        "backend/app/privacy_runtime_operations.json",
        "backend/tests/test_admin_grpc_access.py",
        "backend/tests/test_grpc_cloud_context.py",
        "backend/app/administration.py",
        "backend/app/main.py",
        "backend/app/config.py",
        "backend/app/commercial/admin_access.py",
        "backend/app/commercial/boundary.py",
        "backend/app/commercial/executor_connection.py",
        "scripts/c15_admin_acceptance.py",
        "supabase/migrations/20261102050000_admin_authority.sql",
        "supabase/migrations/20261102060000_admin_compatibility.sql",
        "supabase/migrations/20261102070000_admin_metadata.sql",
        "supabase/migrations/20261102080000_admin_coupon_drafts.sql",
        "supabase/migrations/20261103010000_admin_customer_access.sql",
        "supabase/migrations/20261103020000_admin_privacy_retries.sql",
        "supabase/migrations/20261103030000_admin_retention.sql",
        "supabase/migrations/20261103040000_admin_cancellation.sql",
        "supabase/migrations/20261103050000_admin_campaigns.sql",
        "supabase/migrations/20261103060000_admin_successor.sql",
        "supabase/migrations/20261103070000_admin_metadata_detail.sql",
        "supabase/migrations/20261103080000_admin_telemetry.sql",
        "supabase/migrations/20261103090000_admin_lifecycle.sql",
        "supabase/migrations/20261103100000_admin_privacy_registry.sql",
        "supabase/migrations/20261103110000_admin_export_operations.sql",
        "supabase/migrations/20261103120000_admin_restore.sql",
        "supabase/migrations/20261103130000_admin_population.sql",
        "backend/app/admin_campaigns.py",
        "backend/app/admin_dispatch.py",
        "scripts/c15_admin_access_acceptance.py",
        "frontend/src/App.jsx",
        "frontend/src/auth/AdminConsole.jsx",
        "frontend/src/auth/admin-console.css",
        "frontend/tests/c15-admin/actual.jsx",
        "frontend/tests/c15-admin/actual.run.mjs",
        "frontend/tests/c15-admin/actual.vite.config.js",
        "backend/app/admin_fields.json",
        "backend/app/admin_registry.py",
        "backend/app/admin_restore.py",
        "backend/app/admin_telemetry.py",
        "backend/tests/test_admin_telemetry.py",
        "scripts/c15_admin_business_acceptance.py",
        "scripts/c15_admin_review_acceptance.py",
        "scripts/c15_admin_rehearsal.Dockerfile",
        "backend/app/answer_generation.py",
        "backend/app/answer_streaming.py",
        "backend/app/nlp/answer_generator.py",
        "backend/app/cloud/interview_notes.py",
        "backend/app/cloud/interview_ask_ai.py",
        "backend/app/services/resume_gpt_parser_service.py",
        "backend/app/services/screen_context_service.py",
        "backend/app/services/screen_vision_service.py",
        "backend/app/services/openai_stt_service.py",
        "backend/app/services/groq_stt_service.py",
        "backend/app/services/assemblyai_stt_service.py",
        "backend/app/services/assemblyai_streaming.py",
        "backend/app/services/affinda_resume_parser.py",
        "backend/app/api/email_unsubscribe.py",
        "backend/app/email/marketing.py",
        "backend/app/commercial/billing_service.py",
        "frontend/src/auth/AdminCampaigns.jsx",
        "frontend/src/auth/AdminOverview.jsx",
        "frontend/src/auth/AdminSuccessor.jsx",
        "frontend/src/auth/authApi.js",
    ]
    frontend_missing = [
        name
        for name in source_paths
        if name.startswith("frontend/") and not (ROOT / name).is_file()
    ]
    backend_only = args.backend_only or bool(frontend_missing)
    if backend_only:
        r.save(
            "browser-skipped.json",
            {"reason": "backend_only_review_slice", "missing_inputs": frontend_missing},
        )
        source_paths = [
            name for name in source_paths if not name.startswith("frontend/")
        ]
    r.save(
        "source-inputs.json",
        {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in source_paths
        },
    )
    try:
        r.setup()
        for phase in ("install", "tests"):
            if phase == "tests":
                docker("rm", "-f", r.name + "-auth")
                r.created.remove(r.name + "-auth")
                r.auth_env.update(
                    GOTRUE_HOOK_BEFORE_USER_CREATED_ENABLED="true",
                    GOTRUE_HOOK_BEFORE_USER_CREATED_URI="pg-functions://postgres/public/privacy_auth_before_create",
                    GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED="true",
                    GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI="pg-functions://postgres/public/privacy_auth_token",
                )
                r.run("auth", r.auth_env, container_port=9999)
            name = r.name + "-admin-" + phase
            r.created.append(name)
            output = docker(
                "run",
                "--name",
                name,
                "--label",
                "c15.rehearsal=" + r.name,
                "--network",
                r.name,
                "-e",
                "C15_ISOLATED_CONFIG="
                + json.dumps(
                    {"secret": r.secret, "password": r.password, "name": r.name}
                ),
                "-e",
                "PYTHON_DOTENV_DISABLED=1",
                "-v",
                str(ROOT) + ":/repo:ro",
                "-v",
                str(evidence) + ":/evidence",
                r.runner,
                "python",
                "/repo/scripts/c15_admin_acceptance.py",
                "--inside",
                "--phase",
                phase,
                "--evidence-dir",
                "/evidence",
                check=False,
            )
            # Never persist tracebacks containing local ephemeral secrets or identities.
            print(output.stdout[-2000:])
            if output.returncode:
                import re

                frames = re.findall(r'File "([^"]+)", line (\d+)', output.stderr)
                r.save(
                    "failure.json",
                    {
                        "type": "isolated_acceptance_failed",
                        "frames": frames,
                        "sql_errors": "see safe migration-failure if present",
                    },
                )
                print(
                    output.stderr[-1800:]
                    .replace(r.password, "[REDACTED]")
                    .replace(r.secret, "[REDACTED]")
                )
                raise RuntimeError("isolated_acceptance_failed")
        if not backend_only:
            normal_application(r)
    finally:
        r.cleanup()


if __name__ == "__main__":
    main()
