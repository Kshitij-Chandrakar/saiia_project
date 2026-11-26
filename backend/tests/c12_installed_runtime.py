"""Isolated native backend + production packaged Electron, synthetic auth only."""

import argparse
import json
import logging
import os
import secrets
import subprocess
import threading
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from http.server import (
    BaseHTTPRequestHandler,
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from uuid import uuid4

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

import pytest
from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from razorpay_local_runtime import local_runtime
from test_billing_notifications_native import paid
from test_draft_api_native import actor, headers

ROOT = Path(__file__).resolve().parents[2]


def execute(args):
    base = ROOT / "tmp/c12-acceptance-installer/runtime"
    evidence = base / ("attempt-" + uuid4().hex)
    evidence.mkdir(parents=True)
    (base / "latest.json").write_text(json.dumps({"directory": str(evidence)}))
    nonce = secrets.token_urlsafe(32)
    state = {"unavailable": False, "hold": False, "requests": []}
    release = threading.Event()
    release.set()
    dbpath = None
    result = {"mode": "synthetic_local_only", "provider_calls": 0, "real_emails": 0}
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        with ExitStack() as stack:
            log = stack.enter_context(
                (evidence / "native.log").open("w", encoding="utf-8")
            )
            with redirect_stdout(log), redirect_stderr(log):
                u = stack.enter_context(local_runtime(args.pg_bin))
            assert type(u["provider"]).__module__ == "test_billing_native"
            dbpath = u["db"].directory
            monkey = pytest.MonkeyPatch()
            stack.callback(monkey.undo)
            from app.config import settings

            monkey.setattr(settings, "SUBSCRIPTIONS_ENABLED", "true")
            from app.api import auth as auth_api
            from app.cloud.profile_bootstrap import ProfileBootstrapResult

            monkey.setattr(
                auth_api,
                "bootstrap_authenticated_profile",
                lambda user_id: ProfileBootstrapResult(
                    user_id, True, False, True, False, "ready"
                ),
            )
            monkey.setattr(auth_api, "_trigger_welcome_email", lambda *_: None)
            second = str(uuid4())
            u["db"].run(
                f"insert into auth.users(id,email_confirmed_at) values('{second}',clock_timestamp())"
            )
            assert (
                u["client"]
                .get("/api/account/subscription", headers=headers(second))
                .status_code
                == 200
            )
            session = str(uuid4())
            u["db"].run(
                f"insert into interview_sessions(id,user_id) values('{session}','{u['account']}')"
            )
            expiry = int(time.time()) + 3600
            first_token = headers(
                u["account"], exp=expiry, email="c12-first@example.invalid"
            )["Authorization"][7:]
            second_token = headers(
                second, exp=expiry, email="c12-second@example.invalid"
            )["Authorization"][7:]

            check = u["client"].post(
                "/api/auth/profile/bootstrap",
                headers={"Authorization": "Bearer " + first_token},
            )
            if check.status_code != 200:
                raise RuntimeError(
                    "Local bootstrap failed: " + json.dumps(check.json())
                )

            class Bridge(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass

                def reply(self, status, data):
                    state["requests"].append(
                        {"path": self.path.split("?")[0], "status": status}
                    )
                    raw = json.dumps(data).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header(
                        "Access-Control-Allow-Origin", "http://127.0.0.1:5297"
                    )
                    self.send_header(
                        "Access-Control-Allow-Headers", "Authorization,Content-Type"
                    )
                    self.end_headers()
                    self.wfile.write(raw)

                def do_OPTIONS(self):
                    self.reply(200, {})

                def do_GET(self):
                    if self.path == "/api/account/subscription":
                        if state["hold"]:
                            release.wait(timeout=10)
                        if state["unavailable"]:
                            self.reply(503, {"detail": "synthetic unavailable"})
                            return
                    if self.path == "/api/resumes/current":
                        self.reply(404, {})
                        return
                    if self.path.startswith("/api/job-contexts"):
                        self.reply(200, {"items": []})
                        return
                    response = u["client"].get(
                        self.path,
                        headers={
                            "Authorization": self.headers.get("Authorization", "")
                        },
                    )
                    self.reply(response.status_code, response.json())

                def do_POST(self):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length > 16384:
                        self.reply(413, {})
                        return
                    raw = self.rfile.read(length)
                    if self.path == "/auth/v1/token?grant_type=refresh_token":
                        refresh = json.loads(raw).get("refresh_token")
                        token = (
                            first_token
                            if refresh == "synthetic-first"
                            else second_token
                            if refresh == "synthetic-second"
                            else None
                        )
                        self.reply(
                            200 if token else 401,
                            {
                                "access_token": token,
                                "refresh_token": refresh,
                                "expires_at": expiry,
                            }
                            if token
                            else {},
                        )
                        return
                    if self.path.startswith("/__c12__/"):
                        if self.headers.get("X-C12-Fixture") != nonce:
                            self.reply(403, {})
                            return
                        action = self.path.split("/")[-1]
                        if action == "paid":
                            paid(u)
                        elif action == "expire":
                            # Existing owner-only clock fixture; no production mutation endpoint.
                            u["db"].run(
                                f"update account_plan_bindings set valid_from=clock_timestamp()-interval '2 days',valid_until=clock_timestamp()-interval '1 second',revision=revision+1 where account_id='{u['account']}'"
                            )
                        elif action == "unavailable":
                            state["unavailable"] = json.loads(raw)["value"]
                        elif action == "hold":
                            state["hold"] = True
                            release.clear()
                        elif action == "release":
                            state["hold"] = False
                            release.set()
                        elif action == "free_gate":
                            for _ in range(5):
                                u["subscription"].save_clipboard(
                                    actor(u["account"]),
                                    session,
                                    str(uuid4()),
                                    "Synthetic acceptance answer",
                                )
                            try:
                                u["subscription"].save_clipboard(
                                    actor(u["account"]),
                                    session,
                                    str(uuid4()),
                                    "Beyond allowance",
                                )
                            except CatalogStoreError as error:
                                assert error.code == ErrorCode.EXHAUSTED
                                self.reply(200, {"denied": error.code.value})
                                return
                            raise AssertionError("Expected backend quota denial")
                        elif action != "status":
                            self.reply(404, {})
                            return
                        current = u["client"].get(
                            "/api/account/subscription", headers=headers(u["account"])
                        )
                        self.reply(current.status_code, current.json())
                        return
                    if self.path == "/auth/v1/logout":
                        self.reply(200, {})
                        return
                    response = u["client"].post(
                        self.path,
                        content=raw,
                        headers={
                            "Authorization": self.headers.get("Authorization", ""),
                            "Content-Type": "application/json",
                        },
                    )
                    self.reply(response.status_code, response.json())

            class Website(SimpleHTTPRequestHandler):
                def __init__(self, *a, **kw):
                    super().__init__(
                        *a,
                        directory=str(ROOT / "tmp/c12-acceptance-installer/renderer"),
                        **kw,
                    )

                def log_message(self, *_):
                    pass

                def do_GET(self):
                    if self.path.startswith("/api/"):
                        response = u["client"].get(
                            self.path,
                            headers={
                                "Authorization": self.headers.get("Authorization", "")
                            },
                        )
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(response.content)))
                        self.end_headers()
                        self.wfile.write(response.content)
                        return
                    if self.path.startswith("/auth/"):
                        self.path = "/index.html"
                    super().do_GET()

            for port, handler in ((5296, Bridge), (5297, Website)):
                service = ThreadingHTTPServer(("127.0.0.1", port), handler)
                thread = threading.Thread(target=service.serve_forever, daemon=True)
                thread.start()

                def close(service=service, thread=thread):
                    service.shutdown()
                    service.server_close()
                    thread.join(timeout=5)

                stack.callback(close)
            config = {
                "executable": str(Path(args.executable).resolve()),
                "firstToken": first_token,
                "secondToken": second_token,
                "nonce": nonce,
                "evidence": str(evidence),
                "userData": str(
                    Path(os.environ["LOCALAPPDATA"])
                    / "Intervucopilot-C12-Acceptance/UserData"
                    / ("run-" + uuid4().hex)
                ),
            }
            child_env = {
                k: v
                for k, v in os.environ.items()
                if k.upper()
                in {
                    "PATH",
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "USERPROFILE",
                    "LOCALAPPDATA",
                    "APPDATA",
                    "COMSPEC",
                }
            }
            child_env["C12_ACCEPTANCE_CONFIG"] = json.dumps(config)
            completed = subprocess.run(
                [
                    "node",
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    "--config",
                    "tests/catalog/c12-installed.playwright.config.js",
                ],
                cwd=ROOT / "frontend",
                env=child_env,
                timeout=200,
                check=False,
            )
            result.update(
                playwright_exit=completed.returncode,
                synthetic_account=u["account"],
                database={"directory": str(dbpath), "port": u["db"].port},
                payment_receipts=u["db"].rows(
                    f"select count(*) as n from subscription_payment_receipts where account_id='{u['account']}'"
                )[0]["n"],
            )
            assert completed.returncode == 0, (
                "Installed acceptance failed; inspect Playwright result"
            )
    finally:
        result["requests"] = state["requests"]
        result["database_removed"] = bool(dbpath and not dbpath.exists())
        (evidence / "execution.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--executable", required=True)
    execute(parser.parse_args())
