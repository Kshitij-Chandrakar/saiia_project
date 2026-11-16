"""Loopback browser composition over the pinned isolated real engines.

No endpoint interception, production dotenv, AI/payment boot or hosted requests.
Only the gateway has a published loopback port; data/mail services stay internal.
"""

import argparse
import json
import os
import secrets
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from c15_actual_engines import ROOT, Rehearsal, docker


def prepare_browser(r):
    r.wait("auth", "/health")
    r.configure_app()
    os.environ["SUPABASE_URL"] = "http://127.0.0.1:8080"
    from app.cloud.supabase_config import get_supabase_settings

    get_supabase_settings.cache_clear()
    from app.config import settings

    # Supported local composition: commercial catalogue is not published in this
    # disposable stack. Restriction enforcement remains REQUIRED and active.
    settings.SUBSCRIPTIONS_ENABLED = "true"
    from app.api.auth import router
    from app.commercial.subscription_service import SubscriptionService

    r.app.include_router(router, prefix="/api/auth")
    r.app.state.subscriptions.service = lambda: SubscriptionService(
        lambda: r.connect("usage_executor")
    )
    from uuid import uuid4

    from app.commercial.catalog_contract import create_snapshot

    terms = json.loads(
        (ROOT / "frontend/src/auth/approvedFreeTerms.json").read_text(encoding="utf8")
    )
    terms.update(
        subscription_policy_ref="synthetic.lifecycle",
        migration_policy_ref="synthetic.migration",
    )
    for limit in terms["limits"]:
        limit["policy_ref"] = "synthetic.storage"
    plan, draft, offer = str(uuid4()), str(uuid4()), str(uuid4())
    raw = {
        "draft_id": draft,
        "plan": {"plan_id": plan, "code": "synthetic-free"},
        "revision": "1",
        "state": "previewed",
        "contract_version": "catalog.v2",
        "registry_version": "catalog.features.v2",
        "terms": terms,
        "internal_notes": "Synthetic engine browser setup",
    }
    snapshot = create_snapshot(raw, offer_version_id=offer, version=1)
    with r.connect() as c:
        c.execute(
            "insert into catalog_plans(plan_id,code) values(%s,'synthetic-free')",
            (plan,),
        )
        c.execute(
            "insert into catalog_drafts(draft_id,plan_id,revision,document) values(%s,%s,1,%s::jsonb)",
            (draft, plan, json.dumps(raw)),
        )
        c.execute(
            "insert into catalog_offer_versions(offer_version_id,plan_id,version,source_draft_id,source_revision,canonical_json,fingerprint) values(%s,%s,1,%s,1,%s,%s)",
            (offer, plan, draft, snapshot.canonical_json(), snapshot.fingerprint),
        )
        c.execute(
            "insert into subscription_configuration(singleton,free_offer_id,free_fingerprint,verification_since,policy_version) values(true,%s,%s,'2020-01-01','subscriptions.approved.2026-10-24')",
            (offer, snapshot.fingerprint),
        )
    users = [r.user(), r.user(), r.user(), r.user()]
    r.check(
        r.auth(
            "/admin/users/" + users[2]["id"],
            method="PUT",
            token=r.service,
            body={"app_metadata": {"providers": ["google"], "provider": "google"}},
        ),
        200,
        "synthetic_google_metadata",
    )
    for u in users:
        with r.connect() as c:
            c.execute(
                "insert into profiles(user_id,full_name) values(%s,'Synthetic candidate') on conflict(user_id) do nothing",
                (u["id"],),
            )
    with r.connect() as c:
        for title in ("Synthetic Session A", "Synthetic Session B"):
            c.execute(
                "insert into interview_sessions(user_id,title,status,ended_at) values(%s,%s,'abandoned',clock_timestamp())",
                (users[0]["id"], title),
            )
    import base64
    import hashlib
    import hmac
    import struct

    factor = r.check(
        r.auth(
            "/factors",
            token=users[3]["access_token"],
            body={"factor_type": "totp", "friendly_name": "Synthetic local"},
        ),
        200,
        "browser_totp_enroll",
    )
    factor_secret = factor["totp"]["secret"]

    def totp_code():
        secret = base64.b32decode(
            factor_secret + "=" * ((8 - len(factor_secret) % 8) % 8)
        )
        mac = hmac.new(
            secret, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1
        ).digest()
        offset = mac[-1] & 15
        return f"{(struct.unpack('>I', mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"

    challenge = r.check(
        r.auth(
            "/factors/" + factor["id"] + "/challenge",
            token=users[3]["access_token"],
            body={},
        ),
        200,
        "browser_totp_challenge",
    )
    r.check(
        r.auth(
            "/factors/" + factor["id"] + "/verify",
            token=users[3]["access_token"],
            body={"challenge_id": challenge["id"], "code": totp_code()},
        ),
        200,
        "browser_totp_verify",
    )
    r.check(
        r.auth(
            "/admin/users/" + users[3]["id"],
            method="PUT",
            token=r.service,
            body={"app_metadata": {"providers": ["google"], "provider": "google"}},
        ),
        200,
        "totp_google_metadata_fixture",
    )
    return users, totp_code


def serve(r):
    users, totp_code = prepare_browser(r)
    control = os.environ["C15_BROWSER_CONTROL"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def handle_request(self):
            size = int(self.headers.get("Content-Length", "0"))
            if size > 2**20:
                self.send_error(413)
                return
            body = self.rfile.read(size)
            path = urlsplit(self.path).path
            if path.startswith("/__fixture/"):
                if self.headers.get("X-C15-Control") != control:
                    self.send_error(404)
                    return
                if path == "/__fixture/users":
                    data = json.dumps(
                        {
                            "users": [
                                {"email": u["email"], "id": u["id"]} for u in users
                            ],
                            "password": r.password,
                            "anon": r.anon,
                        }
                    ).encode()
                elif path == "/__fixture/code":
                    index = json.loads(body)["index"]
                    if type(index) is not int or index not in range(len(users)):
                        self.send_error(400)
                        return
                    data = json.dumps(
                        {"code": r.mail_code(users[index]["email"])}
                    ).encode()
                elif path == "/__fixture/scope-check":
                    with r.connect() as c:
                        sessions = c.execute(
                            "select count(*) from interview_sessions where user_id=%s",
                            (users[0]["id"],),
                        ).fetchone()[0]
                        profiles = c.execute(
                            "select count(*) from profiles where user_id=%s",
                            (users[0]["id"],),
                        ).fetchone()[0]
                    data = json.dumps(
                        {"sessions": sessions, "profiles": profiles}
                    ).encode()
                elif path == "/__fixture/totp":
                    data = json.dumps({"code": totp_code()}).encode()
                elif path == "/__fixture/work":
                    done = r.engine.run_one()
                    data = json.dumps({"processed": done}).encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower()
                not in {"host", "connection", "content-length", "accept-encoding"}
            }
            target = None
            for prefix, service in [
                ("/auth/v1/", "auth"),
                ("/storage/v1/", "storage"),
                ("/rest/v1/", "rest"),
            ]:
                if path.startswith(prefix):
                    target = r.url(service) + "/" + self.path[len(prefix) :]
                    break
            try:
                if target:
                    response = r.http.request(
                        self.command,
                        target,
                        headers=headers,
                        data=body or None,
                        timeout=(3, 15),
                        allow_redirects=False,
                    )
                elif path.startswith("/api/"):
                    response = r.client.request(
                        self.command, self.path, headers=headers, content=body
                    )
                else:
                    self.send_error(404)
                    return
                data = response.content
                self.send_response(response.status_code)
                for key, value in response.headers.items():
                    if key.lower() not in {
                        "content-length",
                        "content-encoding",
                        "transfer-encoding",
                        "connection",
                    }:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:  # noqa: BLE001 -- never expose request credentials or engine errors
                self.send_error(503, "isolated boundary unavailable")

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_DELETE = handle_request
        do_OPTIONS = handle_request

    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.inside:
        serve(Rehearsal(args.evidence_dir, internal=True))
        return
    evidence = args.evidence_dir.resolve()
    assert evidence.is_relative_to(ROOT / "docs/evidence")
    r = Rehearsal(evidence)
    vite = None
    try:
        r.setup()
        config = json.dumps(
            {"secret": r.secret, "password": r.password, "name": r.name}
        )
        install = r.name + "-browser-install"
        r.created.append(install)
        result = docker(
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
        if result.returncode:
            raise RuntimeError("browser_install_failed")
        docker("rm", "-f", r.name + "-auth")
        r.created.remove(r.name + "-auth")
        r.auth_env.update(
            GOTRUE_HOOK_BEFORE_USER_CREATED_ENABLED="true",
            GOTRUE_HOOK_BEFORE_USER_CREATED_URI="pg-functions://postgres/public/privacy_auth_before_create",
            GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED="true",
            GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI="pg-functions://postgres/public/privacy_auth_token",
        )
        r.run("auth", r.auth_env, container_port=9999)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        name = r.name + "-gateway"
        control = secrets.token_urlsafe(32)
        r.created.append(name)
        docker(
            "create",
            "--name",
            name,
            "--label",
            "c15.rehearsal=" + r.name,
            "--network",
            "bridge",
            "-p",
            f"127.0.0.1:{port}:8080",
            "-e",
            "C15_ISOLATED_CONFIG=" + config,
            "-e",
            "C15_BROWSER_CONTROL=" + control,
            "-v",
            str(ROOT) + ":/repo:ro",
            "-v",
            str(evidence) + ":/evidence",
            r.runner,
            "python",
            "/repo/scripts/c15_browser_engines.py",
            "--inside",
            "--evidence-dir",
            "/evidence",
        )
        docker("network", "connect", r.name, name)
        docker("start", name)
        inspected = json.loads(docker("inspect", name).stdout)[0]
        bindings = inspected["NetworkSettings"]["Ports"]
        assert all(
            binding["HostIp"] == "127.0.0.1"
            for values in bindings.values()
            for binding in (values or [])
        )
        r.save(
            "browser-isolation.json",
            {
                "gateway_bindings": bindings,
                "data_services": "internal owned network; no SMTP relay or external provider configuration",
                "gateway": "fixed local Auth/REST/Storage/application routes only; no arbitrary upstream",
                "sdk_version": json.loads(
                    (
                        ROOT
                        / "frontend/node_modules/@supabase/supabase-js/package.json"
                    ).read_text()
                )["version"],
                "no_auth_storage_privacy_interception": True,
            },
        )
        gateway = f"http://127.0.0.1:{port}"
        import requests

        http = requests.Session()
        http.trust_env = False
        for _ in range(60):
            try:
                result = http.get(
                    gateway + "/__fixture/users",
                    headers={"X-C15-Control": control},
                    timeout=1,
                )
                if result.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            # Only exception type/frame names; never dump gateway credentials.
            log = docker("logs", name, check=False).stderr
            print("gateway failed:", log[-1500:])
            raise RuntimeError("gateway_unavailable")
        config = result.json()
        env = {
            **os.environ,
            "C15_GATEWAY": gateway,
            "C15_BROWSER_CONTROL": control,
            "C15_BROWSER_USERS": json.dumps(config),
            "VITE_SUPABASE_URL": "http://127.0.0.1:5397",
            "VITE_SUPABASE_ANON_KEY": config["anon"],
            "VITE_C15_ENABLED": "true",
            "VITE_C15_EXPORT_ENABLED": "true",
            "PYTHON_DOTENV_DISABLED": "1",
        }
        vite = subprocess.Popen(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--config",
                "tests/c15/actual.vite.config.js",
            ],
            cwd=ROOT / "frontend",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(60):
            try:
                if (
                    http.get("http://127.0.0.1:5397/auth/login", timeout=1).status_code
                    == 200
                ):
                    break
            except requests.RequestException:
                pass
            if vite.poll() is not None:
                raise RuntimeError("isolated_vite_failed")
            time.sleep(0.5)
        else:
            raise RuntimeError("isolated_vite_unavailable")
        env["C15_BROWSER_EVIDENCE"] = str(evidence)
        tested = subprocess.run(
            ["node", "tests/c15/actual.run.mjs"],
            cwd=ROOT / "frontend",
            env=env,
            timeout=240,
            check=False,
            capture_output=True,
            text=True,
        )
        print(tested.stdout)
        print(tested.stderr[:1000])
        if tested.returncode:
            raise RuntimeError("browser_acceptance_failed")
    finally:
        if vite:
            vite.terminate()
            vite.wait(timeout=15)
        r.cleanup()


if __name__ == "__main__":
    main()
