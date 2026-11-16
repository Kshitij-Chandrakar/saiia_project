"""Actual main/gRPC/worker and SDK rehearsal; owned loopback engines only."""

import argparse
import base64
import json
import multiprocessing
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import requests
from c15_actual_engines import ROOT, Rehearsal, docker


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def witness_process(config, pipe):
    sys.path.insert(0, str(ROOT / "backend"))
    from app.privacy_checkpoint import LocalCheckpointStore
    from app.privacy_witness import local_authority

    store = LocalCheckpointStore(
        config["path"],
        config["anchor"],
        config["key"],
        config["environment"],
        config["dataset"],
    )
    server = local_authority(
        store, config["reader"], config["writer"], operator_token=config["operator"]
    )
    pipe.send(server.server_address[1])
    pipe.close()
    server.serve_forever()


class Local(Rehearsal):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    assert evidence.is_relative_to(ROOT / "docs/evidence")
    # No operational dotenv or hosted/project credentials are imported.
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
    import dotenv

    dotenv.load_dotenv = lambda *a, **k: False
    r = Local(evidence)
    gateway = server_thread = uv_server = uv_thread = vite = witness = None
    owned = None
    main_port = port()
    grpc_port = port()
    control = secrets.token_urlsafe(40)
    normal = None
    try:
        r.setup()
        config = json.dumps(
            {"secret": r.secret, "password": r.password, "name": r.name}
        )
        install = r.name + "-normal-install"
        r.created.append(install)
        installed = docker(
            "run",
            "--name",
            install,
            "--label",
            "c15.rehearsal=" + r.name,
            "--network",
            r.name,
            "-e",
            "C15_ISOLATED_CONFIG=" + config,
            "-v",
            str(ROOT) + ":/repo:ro",
            "-v",
            str(evidence) + ":/evidence",
            r.runner,
            "python",
            "/repo/scripts/c15_actual_engines.py",
            "--inside",
            "--phase",
            "install",
            "--evidence-dir",
            "/evidence",
            check=False,
        )
        if installed.returncode:
            raise RuntimeError("normal_install_failed")
        docker("rm", "-f", r.name + "-auth")
        r.created.remove(r.name + "-auth")
        r.auth_env.update(
            GOTRUE_HOOK_BEFORE_USER_CREATED_ENABLED="true",
            GOTRUE_HOOK_BEFORE_USER_CREATED_URI="pg-functions://postgres/public/privacy_auth_before_create",
            GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED="true",
            GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI="pg-functions://postgres/public/privacy_auth_token",
        )
        r.run("auth", r.auth_env, container_port=9999)
        name = r.name + "-local-proxy"
        r.created.append(name)
        routes = {
            "db": 15432,
            "auth": 19999,
            "storage": 15000,
            "rest": 13000,
            "mail": 18025,
            "smtp": 11025,
        }
        create = [
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
        for service, inside in routes.items():
            r.ports[service] = port()
            create += ["-p", "127.0.0.1:" + str(r.ports[service]) + ":" + str(inside)]
        docker(*create, r.runner, "python", "/repo/scripts/c15_loopback_proxy.py")
        docker("network", "connect", "bridge", name)
        docker("start", name)
        r.wait("auth", "/health")
        r.save(
            "normal-isolation.json",
            {
                "data_network": "owned internal network, external Google/SMTP/AI/payment disabled",
                "proxy": "fixed local engine TCP routes only",
                "bindings": json.loads(docker("inspect", name).stdout)[0]["HostConfig"][
                    "PortBindings"
                ],
            },
        )
        # One fixed gateway supplies the real SDK's standard Supabase URL and proxies
        # application HTTP to the actual main app; no Auth/Storage/privacy interception.
        users = []
        totp_code = None

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def handle_request(self):
                path = self.path
                size = int(self.headers.get("Content-Length", "0"))
                if size > 2**20:
                    self.send_error(413)
                    return
                body = self.rfile.read(size)
                if path.startswith("/__fixture/"):
                    if self.headers.get("X-C15-Control") != control:
                        self.send_error(404)
                        return
                    if path == "/__fixture/users":
                        data = {
                            "users": [
                                {"id": u["id"], "email": u["email"]} for u in users
                            ],
                            "password": r.password,
                            "anon": r.anon,
                        }
                    elif path == "/__fixture/code":
                        data = {
                            "code": r.mail_code(
                                users[json.loads(body)["index"]]["email"]
                            )
                        }
                    elif path == "/__fixture/totp":
                        data = {"code": totp_code()}
                    elif path == "/__fixture/work":
                        deadline = time.monotonic() + 20
                        while (
                            normal.sweep_lock.locked() and time.monotonic() < deadline
                        ):
                            time.sleep(0.1)
                        normal.sweep()
                        data = {"processed": True}
                    elif path == "/__fixture/scope-check":
                        with r.connect() as c:
                            data = {
                                "sessions": c.execute(
                                    "select count(*) from interview_sessions where user_id=%s",
                                    (users[0]["id"],),
                                ).fetchone()[0],
                                "profiles": c.execute(
                                    "select count(*) from profiles where user_id=%s",
                                    (users[0]["id"],),
                                ).fetchone()[0],
                            }
                    else:
                        self.send_error(404)
                        return
                    encoded = json.dumps(data).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                target = "http://127.0.0.1:" + str(main_port) + path
                for prefix, service in [
                    ("/auth/v1", "auth"),
                    ("/rest/v1", "rest"),
                    ("/storage/v1", "storage"),
                ]:
                    if path.startswith(prefix):
                        target = r.url(service) + path[len(prefix) :]
                        break
                headers = {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in {"host", "connection", "content-length"}
                }
                with r.http.request(
                    self.command,
                    target,
                    headers=headers,
                    data=body,
                    allow_redirects=False,
                    stream=True,
                    timeout=30,
                ) as response:
                    self.send_response(response.status_code)
                    for k, v in response.headers.items():
                        if k.lower() not in {
                            "content-length",
                            "transfer-encoding",
                            "connection",
                            "content-encoding",
                        }:
                            self.send_header(k, v)
                    self.end_headers()
                    for chunk in response.iter_content(65536):
                        self.wfile.write(chunk)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_request

        gateway = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        server_thread.start()
        base = "http://127.0.0.1:" + str(gateway.server_address[1])
        from c15_browser_engines import prepare_browser

        users, totp_code = prepare_browser(
            r
        )  # synthetic setup only; not request authority
        r.client.close()
        os.environ["SUPABASE_URL"] = base
        os.environ["SUPABASE_JWT_SECRET_OR_JWKS_CONFIG"] = json.dumps(
            {
                "secret": r.secret,
                "issuer": "http://auth:9999/auth/v1",
                "audience": "authenticated",
            }
        )
        sys.path.insert(0, str(ROOT / "backend"))
        from app.cloud.supabase_config import get_supabase_settings

        get_supabase_settings.cache_clear()
        from app.config import settings

        roles = [
            "privacy_content_executor",
            "privacy_restore_executor",
            "privacy_cleanup_executor",
            "privacy_identity_executor",
            "privacy_revocation_observer",
            "privacy_retention_executor",
            "usage_executor",
        ]
        with r.connect() as c:
            import psycopg

            for role in roles:
                c.execute(
                    psycopg.sql.SQL("alter role {} login password {}").format(
                        psycopg.sql.Identifier(role), psycopg.sql.Literal(r.password)
                    )
                )
        dsns = {
            role: f"host=127.0.0.1 port={r.ports['db']} dbname=postgres user={role} password={r.password} sslmode=disable"
            for role in roles
        }
        owned = Path(tempfile.mkdtemp(prefix="c15-normal-checkpoint-")).resolve()
        from app.privacy_checkpoint import LocalCheckpointStore
        from app.privacy_restore import RestoreJournal

        key = secrets.token_bytes(32)
        journal = RestoreJournal(owned / "journal", {"local": key}, "local")
        head = journal.initialize()
        env, dataset, generation, snapshot = (str(uuid4()) for _ in range(4))
        store = LocalCheckpointStore(
            owned / "head.sqlite", owned / "anchor.sqlite", key, env, dataset
        )
        store.initialize(head)
        with store.locked() as c:
            record = store.read(c)
            record.update(
                sequence=1,
                generation=generation,
                snapshot=snapshot,
                sealed_head=head,
                ready=False,
            )
            store.write(c, record)
        witness_config = {
            "path": owned / "head.sqlite",
            "anchor": owned / "anchor.sqlite",
            "key": key,
            "environment": env,
            "dataset": dataset,
            "reader": secrets.token_urlsafe(40),
            "writer": secrets.token_urlsafe(40),
            "operator": secrets.token_urlsafe(40),
        }
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(False)
        witness = context.Process(target=witness_process, args=(witness_config, send))
        witness.start()
        assert receive.poll(15)
        witness_port = receive.recv()
        receive.close()
        settings.C15_RUNTIME_ENABLED = "true"
        settings.C15_RUNTIME_LOCAL_REHEARSAL = "true"
        settings.C15_RESTORE_BOOT_REQUIRED = "true"
        settings.C15_RUNTIME_DSNS = json.dumps(dsns)
        settings.C15_RUNTIME_ENDPOINTS = json.dumps(
            {
                "storage": r.url("storage"),
                "auth": r.url("auth"),
                "standalone_auth": True,
                "service_key": r.service,
                "anon_key": r.anon,
                "smtp_host": "127.0.0.1",
                "smtp_port": r.ports["smtp"],
            }
        )
        settings.C15_RUNTIME_CHECKPOINT = json.dumps(
            {
                "journal": str(owned / "journal"),
                "journal_keys": {"local": base64.b64encode(key).decode()},
                "journal_current": "local",
                "witness_url": "http://127.0.0.1:" + str(witness_port),
                "witness_token": witness_config["writer"],
                "witness_key": base64.b64encode(key).decode(),
                "environment": env,
                "dataset": dataset,
                "generation": generation,
                "snapshot": snapshot,
            }
        )
        settings.SUBSCRIPTIONS_DSN = dsns["usage_executor"]
        settings.GRPC_REALTIME_ENABLED = True
        settings.GRPC_REALTIME_HOST = "127.0.0.1"
        settings.GRPC_REALTIME_PORT = grpc_port
        settings.GRPC_STT_ENABLED = False
        settings.GRPC_ANSWER_STREAM_ENABLED = False
        import app.main as application
        import uvicorn

        uv_server = uvicorn.Server(
            uvicorn.Config(
                application.app,
                host="127.0.0.1",
                port=main_port,
                log_level="error",
                access_log=False,
            )
        )
        uv_thread = threading.Thread(target=uv_server.run, daemon=True)
        uv_thread.start()
        deadline = time.monotonic() + 25
        while not uv_server.started and time.monotonic() < deadline:
            time.sleep(0.1)
        if not uv_server.started:
            raise RuntimeError("actual_main_startup_failed")
        normal = application.app.state.privacy_runtime
        if not normal.coordinator.ready():
            raise RuntimeError("normal_restore_not_ready")
        import grpc
        from app.grpc_generated import interview_realtime_pb2 as pb
        from app.grpc_generated import interview_realtime_pb2_grpc as rpc

        channel = grpc.insecure_channel("127.0.0.1:" + str(grpc_port))
        grpc.channel_ready_future(channel).result(timeout=8)
        rpc.InterviewRealtimeServiceStub(channel).CheckHealth(pb.Empty(), timeout=5)
        channel.close()
        r.save(
            "normal-main.json",
            {
                "actual_main_lifespan": True,
                "grpc_health_rpc": True,
                "fixture_database_authority": False,
                "runtime_principals": roles,
                "independent_local_witness_process": True,
                "production_durability_claim": False,
            },
        )
        probe = r.http.post(
            base + "/api/privacy/content/begin",
            json={"request_id": str(uuid4()), "operation_scope": "export"},
            headers={"Authorization": "Bearer " + users[0]["access_token"]},
            timeout=10,
        )
        r.save("normal-proof-probe.json", {"status": probe.status_code})
        if probe.status_code != 200:
            raise RuntimeError("normal_proof_begin_failed")
        if args.browser:
            envv = {
                **os.environ,
                "C15_GATEWAY": base,
                "C15_BROWSER_CONTROL": control,
                "C15_BROWSER_USERS": json.dumps(
                    {
                        "users": [{"id": u["id"], "email": u["email"]} for u in users],
                        "password": r.password,
                        "anon": r.anon,
                    }
                ),
                "C15_BROWSER_EVIDENCE": str(evidence),
                "VITE_SUPABASE_URL": "http://127.0.0.1:5397",
                "VITE_SUPABASE_ANON_KEY": r.anon,
                "VITE_C15_ENABLED": "true",
                "VITE_C15_EXPORT_ENABLED": "true",
            }
            vite = subprocess.Popen(
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "--config",
                    "tests/c15/actual.vite.config.js",
                ],
                cwd=ROOT / "frontend",
                env=envv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    if (
                        r.http.get(
                            "http://127.0.0.1:5397/auth/login", timeout=1
                        ).status_code
                        == 200
                    ):
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.2)
            result = subprocess.run(
                ["node", "tests/c15/actual.run.mjs"],
                cwd=ROOT / "frontend",
                env=envv,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("normal_browser_failed")
        else:
            # Real app HTTP -> real SDK-compatible proof routes -> ordinary workers.
            from fastapi.testclient import TestClient

            r.client = TestClient(
                application.app
            )  # existing running lifespan remains owned by uvicorn
            _u, _document = r.accepted_password(users[0])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            with r.connect() as c:
                done = c.execute(
                    "select count(*) from privacy_followup_tasks where kind='identity_cleanup' and state='succeeded'"
                ).fetchone()[0]
                expected = c.execute(
                    "select count(*) from privacy_deletion_requests where state='accepted_restricted'"
                ).fetchone()[0]
            if done == expected and expected > 0:
                break
            time.sleep(0.2)
        if done != expected or not expected:
            raise RuntimeError("identity_cleanup_not_verified")
        with r.connect() as c:
            states = c.execute(
                "select kind,state,count(*) from privacy_followup_tasks group by kind,state order by kind,state"
            ).fetchall()
        r.save(
            "normal-workers.json",
            {
                "identity_cleanup_verified": True,
                "eligible_accepted_requests": expected,
                "verified_identity_cleanups": done,
                "states": states,
                "logout_alone_is_cleanup": False,
            },
        )
        # Deterministic witness-loss injection on the actual normal gRPC instance.
        normal.coordinator.boot_verified = False
        with grpc.insecure_channel("127.0.0.1:" + str(grpc_port)) as protected:
            try:
                list(
                    rpc.InterviewRealtimeServiceStub(protected).StreamInterview(
                        iter([]), timeout=5
                    )
                )
            except grpc.RpcError as error:
                assert error.code() == grpc.StatusCode.UNAVAILABLE
            else:
                raise AssertionError("grpc_quarantine_bypassed")
        normal.coordinator.boot_verified = True
        # Restart the actual ASGI lifespan and all private runtime adapters.
        uv_server.should_exit = True
        uv_thread.join(timeout=40)
        assert not uv_thread.is_alive()
        uv_server = uvicorn.Server(
            uvicorn.Config(
                application.app,
                host="127.0.0.1",
                port=main_port,
                log_level="error",
                access_log=False,
            )
        )
        uv_thread = threading.Thread(target=uv_server.run, daemon=True)
        uv_thread.start()
        deadline = time.monotonic() + 30
        while not uv_server.started and time.monotonic() < deadline:
            time.sleep(0.1)
        assert (
            uv_server.started
            and application.app.state.privacy_runtime.coordinator.ready()
        )
        r.save(
            "normal-restart.json",
            {
                "actual_lifespan_restart": True,
                "checkpoint_ready_after_restart": True,
                "grpc_quarantine_denied": True,
                "grpc_quarantine_test": "deterministic witness-verification loss, actual gRPC",
            },
        )
        r.save(
            "normal-results.json",
            {
                "main_startup": "passed",
                "grpc_startup": "passed",
                "normal_workers": "passed",
                "identity_cleanup": "passed",
                "actual_auth_storage": True,
                "browser": bool(args.browser),
            },
        )
        return 0
    except Exception as error:  # noqa: BLE001 -- safe diagnostics and owned-resource cleanup
        r.save(
            "normal-failure.json",
            {
                "type": type(error).__name__,
                "category": str(error) if type(error) is RuntimeError else None,
                "frames": [
                    {
                        "file": Path(f.filename).name,
                        "line": f.lineno,
                        "function": f.name,
                    }
                    for f in traceback.extract_tb(error.__traceback__)
                ],
            },
        )
        print("normal rehearsal failed:", type(error).__name__, flush=True)
        return 1
    finally:
        if vite:
            vite.terminate()
            vite.wait(timeout=10)
        if uv_server:
            uv_server.should_exit = True
        if uv_thread:
            uv_thread.join(timeout=40)
        if gateway:
            gateway.shutdown()
            gateway.server_close()
        if witness:
            witness.terminate()
            witness.join(timeout=10)
        if owned:
            import shutil

            assert owned.parent == Path(
                tempfile.gettempdir()
            ).resolve() and owned.name.startswith("c15-normal-checkpoint-")
            shutil.rmtree(owned)
        r.cleanup()
        # Only owned ports/processes are inspected; unrelated services are untouched.
        listeners = []
        for candidate_port in [
            locals().get("main_port"),
            locals().get("grpc_port"),
            *(r.ports.values()),
        ]:
            if candidate_port:
                with socket.socket() as check:
                    check.settimeout(0.3)
                    if check.connect_ex(("127.0.0.1", int(candidate_port))) == 0:
                        listeners.append(int(candidate_port))
        r.save(
            "host-cleanup.json",
            {
                "remaining_owned_listeners": listeners,
                "asgi_thread_alive": bool(uv_thread and uv_thread.is_alive()),
                "witness_alive": bool(witness and witness.is_alive()),
                "owned_checkpoint_removed": bool(owned and not owned.exists()),
                "vite_stopped": bool(vite is None or vite.poll() is not None),
            },
        )
        assert not listeners and not (uv_thread and uv_thread.is_alive())


if __name__ == "__main__":
    raise SystemExit(main())
