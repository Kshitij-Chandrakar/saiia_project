"""Opt-in real-provider session. All provider dispatches use the durable budget."""

import json
import hashlib
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import requests
import uvicorn
from app.commercial.billing_service import BillingService
from razorpay_bounded_provider import BoundedProvider
from razorpay_session_budget import SessionBudget
from test_billing_native import headers
from test_draft_api_native import create
from test_pricing_native import definition, publish

from scripts import c12_webhook_gateway as gateway

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def cleanup_subscriptions(provider, budget):
    provider.cleanup = True
    complete = True
    for identifier in budget.load()["resources"].get("subscriptions", []):
        try:
            state = provider.subscription(identifier)
            if state["status"] not in {"cancelled", "completed", "expired"}:
                provider.cancel(identifier)
                state = provider.subscription(identifier)
            terminal = state["status"] in {"cancelled", "completed", "expired"} or state.get("cancel_at_cycle_end") is True
            complete = complete and terminal
            budget.event("cleanup_subscription_observed", resource_id=identifier, passed=terminal)
        except Exception as error:
            complete = False
            budget.event("cleanup_subscription_unresolved", resource_id=identifier, exception_type=type(error).__name__)
    return complete


def cleanup_pending(service, budget):
    try:
        pending = service.pending()[:8]
    except Exception as error:
        budget.event("cleanup_pending_lookup_unresolved", exception_type=type(error).__name__)
        return False
    complete = True
    for operation in pending:
        try:
            recovered = service.reconcile(operation["account_id"], operation["operation_id"])
            if recovered.get("provider_id"):
                budget.resource("subscriptions", recovered["provider_id"])
            elif recovered.get("state") != "expired":
                complete = False
                budget.event("cleanup_uncertain_creation_unresolved", resource_id=operation["operation_id"], passed=False)
        except Exception as error:
            complete = False
            budget.event("cleanup_reconciliation_unresolved", resource_id=operation["operation_id"], exception_type=type(error).__name__)
    return complete


def retain_cleanup_database(db, budget):
    """Private synthetic database snapshot, never provider credentials."""
    temporary = budget.directory / ("cleanup-database-" + uuid4().hex + ".pending")
    db.command("pg_dump", ["-h", "127.0.0.1", "-p", str(db.port), "-U", "catalog_test_owner",
                           "-d", "postgres", "-Fc", "-f", str(temporary)])
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    target = budget.directory / ("cleanup-database-" + digest + ".dump")
    # Publish immutable bytes first; the atomic journal update switches the
    # pointer. A failed update leaves the previous snapshot and pointer intact.
    os.replace(temporary, target)
    with budget.locked():
        state = budget.load()
        state["cleanup_database_sha256"] = digest
        budget.save(state)


def cleanup_only(credentials, directory, *, pg_bin=None):
    budget = SessionBudget(directory)
    if budget.load()["status"] != "cleanup" or not budget.load()["start_utc"]:
        raise RuntimeError("No unfinished cleanup session; no new intake allowed")
    provider = BoundedProvider(credentials["RAZORPAY_TEST_KEY_ID"], credentials["RAZORPAY_TEST_KEY_SECRET"], budget)
    provider.cleanup = True
    if budget.load().get("cleanup_requires_reconciliation"):
        expected = budget.load().get("cleanup_database_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise RuntimeError("Verified synthetic recovery database unavailable; cleanup remains blocked")
        snapshot = directory / ("cleanup-database-" + expected + ".dump")
        if not snapshot.is_file():
            snapshot = directory / "cleanup-database.dump"  # Earlier journal format; still digest-verified.
        if not pg_bin or not expected or not snapshot.is_file() or hashlib.sha256(snapshot.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Verified synthetic recovery database unavailable; cleanup remains blocked")
        from razorpay_local_runtime import local_runtime

        with local_runtime(pg_bin) as runtime:
            db = runtime["db"]
            db.command("pg_restore", ["-h", "127.0.0.1", "-p", str(db.port), "-U", "catalog_test_owner",
                                      "-d", "postgres", "--clean", "--if-exists", "--exit-on-error", str(snapshot)])
            service = BillingService(
                lambda: runtime["connect"]("usage_binding_executor"), provider,
                merchant=credentials["RAZORPAY_TEST_ACCOUNT_ID"],
                webhook_secrets=(credentials["RAZORPAY_TEST_WEBHOOK_SECRET"],), renewal="automatic", enabled=True,
                total_policy_ref="billing.inr.gst18.v1",
            )
            reconciled = cleanup_pending(service, budget)
            retain_cleanup_database(db, budget)
            with budget.locked():
                state = budget.load()
                state["cleanup_requires_reconciliation"] = not reconciled
                budget.save(state)
    complete = cleanup_subscriptions(provider, budget) and not (
        budget.load().get("cleanup_requires_reconciliation") or budget.load().get("cleanup_processes_unresolved")
    )
    budget.close_intake("finished" if complete else "cleanup")
    if not complete:
        raise RuntimeError("Subscription cleanup remains unresolved; original budget retained")


def execute(u, credentials, directory):
    key = credentials["RAZORPAY_TEST_KEY_ID"]
    merchant = credentials["RAZORPAY_TEST_ACCOUNT_ID"]
    secret = credentials["RAZORPAY_TEST_WEBHOOK_SECRET"]
    if (
        not re.fullmatch(r"rzp_test_[A-Za-z0-9]+", key)
        or not credentials["RAZORPAY_TEST_KEY_SECRET"]
        or not re.fullmatch(r"acc_[A-Za-z0-9]+", merchant)
        or len(secret) < 32
    ):
        raise RuntimeError(
            "Dedicated test credentials unavailable; no external activity"
        )
    budget = SessionBudget(directory)
    provider = BoundedProvider(key, credentials["RAZORPAY_TEST_KEY_SECRET"], budget)
    subjects = [u["account"]] + [str(uuid4()) for _ in range(7)]
    for subject in subjects[1:]:
        u["db"].run(f"insert into auth.users(id) values ('{subject}')")
        assert (
            u["client"]
            .get("/api/account/subscription", headers=headers(subject))
            .status_code
            == 200
        )
    raw = definition("pro")
    assert create(u["client"], raw).status_code == 200
    pro_id = publish(u["client"], raw)["receipt"]["offer_version_id"]
    catalog = u["client"].get("/api/catalog").json()
    offer_ids = [u["checkout"]["offer_version_id"], pro_id]
    offers = [
        next(o for o in catalog["offers"] if o["offer_version_id"] == identifier)
        for identifier in offer_ids
    ]
    prices = [
        (offer, price, catalog["payable_prices"][price["price_id"]])
        for offer in offers
        for price in sorted(offer["prices"], key=lambda p: p["billing"]["unit"])
    ]
    children = []
    server = None
    gateway_server = None
    service = None
    website_log = None
    try:
        # Actual credential validation GET is the first external dispatch. The
        # journal commits UTC/IST start/deadline immediately before this call.
        provider._request("GET", "plans?count=1")
        subscription_access = provider._request("GET", "subscriptions?count=1")
        if not isinstance(subscription_access.get("items"), list):
            raise TypeError(
                "Subscriptions listing unavailable; no mutations or tunnel allowed"
            )
        budget.event("authentication_and_subscriptions_reads_passed", passed=True)
        audit_path = directory / "previous-session-audit.json"
        retained = {}
        if audit_path.exists():
            audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
            for identifier in audit.get("resources", {}).get("plans", []):
                plan = provider.plan(identifier)
                item = plan.get("item", {})
                if (
                    plan.get("id") != identifier
                    or plan.get("entity") != "plan"
                    or plan.get("interval") != 1
                    or item.get("currency") != "INR"
                    or type(item.get("amount")) is not int
                ):
                    raise RuntimeError("Retained provider plan binding mismatch")
                retained[(plan.get("period"), item["amount"])] = plan
            for identifier in audit.get("resources", {}).get("subscriptions", []):
                provider.subscription(identifier)
            budget.event("retained_provider_objects_inspected", passed=True)
        mappings = {}
        for offer, price, quote in prices:
            unit = price["billing"]["unit"]
            plan = retained.get(
                (
                    "monthly" if unit == "month" else "yearly",
                    int(quote["total_amount_minor"]),
                )
            )
            if plan is None:
                plan = provider.create_plan(
                    unit,
                    int(quote["total_amount_minor"]),
                    "C12 acceptance " + offer["name"] + " " + unit,
                )
            else:
                budget.resource("reused_plans", plan["id"])
            mappings[price["price_id"]] = {
                "provider_plan": plan["id"],
                "total_count": 12 if unit == "month" else 5,
            }
            provider.plan(plan["id"])
        service = BillingService(
            lambda: u["connect"]("usage_binding_executor"),
            provider,
            merchant=merchant,
            webhook_secrets=(secret,),
            renewal="automatic",
            enabled=True,
            total_policy_ref="billing.inr.gst18.v1",
            plan_mappings=mappings,
        )
        u["client"].app.state.billing = service

        class Bridge(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                pass

            def dispatch(self):
                route = urlsplit(self.path)
                if route.path == "/__c12/session" and self.command == "GET":
                    index = int(parse_qs(route.query).get("case", ["0"])[0])
                    if not 0 <= index < 8:
                        self.send_error(404)
                        return
                    offer, price, _ = prices[index % 4]
                    payload = json.dumps(
                        {
                            "session": {
                                "access_token": headers(subjects[index])[
                                    "Authorization"
                                ][7:],
                                "user": {"id": subjects[index]},
                            },
                            "offer": offer["offer_version_id"],
                            "price": price["price_id"],
                        }
                    ).encode()
                    status = 200
                elif (
                    route.path == "/api/catalog"
                    or route.path == "/api/account/subscription"
                    or route.path.startswith("/api/billing/")
                ):
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 <= length <= 131072:
                        self.send_error(413)
                        return
                    response = u["client"].request(
                        self.command,
                        self.path,
                        content=self.rfile.read(length),
                        headers={
                            k: v
                            for k, v in self.headers.items()
                            if k.lower()
                            in {"authorization", "content-type", "x-razorpay-signature"}
                        },
                    )
                    status, payload = response.status_code, response.content
                else:
                    self.send_error(404)
                    return
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = dispatch
            do_POST = dispatch

        server = ThreadingHTTPServer(("127.0.0.1", 8120), Bridge)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        gateway.UPSTREAM_PORT = 8120
        gateway_server = uvicorn.Server(
            uvicorn.Config(
                gateway.app,
                host="127.0.0.1",
                port=8121,
                access_log=False,
                log_level="error",
                limit_concurrency=16,
                backlog=16,
                timeout_keep_alive=2,
            )
        )
        threading.Thread(target=gateway_server.run, daemon=True).start()
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "COMSPEC",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
            }
        }
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        website_log = (directory / "website-process.log").open("w", encoding="utf-8")
        vite = subprocess.Popen(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--config",
                "c12.testmode.vite.config.js",
                "--host",
                "127.0.0.1",
                "--port",
                "5273",
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=clean_env,
            stdout=website_log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
        children.append(vite)
        budget.resource("processes", vite.pid)
        tool = Path(os.environ["LOCALAPPDATA"]) / "C12Tools/cloudflared.exe"
        if not tool.exists():
            budget.reserve("downloads")
            response = requests.get(
                "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
                timeout=(5, 45),
            )
            response.raise_for_status()
            if (
                not response.content.startswith(b"MZ")
                or len(response.content) > 100000000
            ):
                raise RuntimeError("Unexpected tunnel artifact")
            tool.parent.mkdir(parents=True, exist_ok=True)
            with tool.open("xb") as handle:
                handle.write(response.content)
        budget.reserve("tunnels")
        tunnel = subprocess.Popen(
            [str(tool), "tunnel", "--url", "http://127.0.0.1:8121"],
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=flags,
        )
        children.append(tunnel)
        budget.resource("processes", tunnel.pid)

        def observe_tunnel():
            logged = 0
            with (directory / "tunnel-process.log").open("w", encoding="utf-8") as log:
                for line in tunnel.stdout:
                    if logged < 1000000:
                        log.write(line)
                        log.flush()
                        logged += len(line)
                    match = re.search(r"https://([a-z0-9-]+)\.trycloudflare\.com", line)
                    if match and "|" in line and match[1] not in {"api", "www"}:
                        budget.resource("tunnel_urls", match[0])
                        (directory / "webhook-url.txt").write_text(
                            match[0] + gateway.PATH, encoding="utf-8"
                        )

        threading.Thread(target=observe_tunnel, daemon=True).start()
        (directory / "runtime-ready.json").write_text(
            json.dumps(
                {
                    "website": "http://127.0.0.1:5273",
                    "cases": 8,
                    "merchant_identity": "owner-entered; awaiting signed webhook confirmation",
                    "webhook_registration": "manual action required",
                }
            ),
            encoding="utf-8",
        )
        while (
            budget.load()["status"] == "running"
            and not (directory / "stop").exists()
            and datetime.now(timezone.utc)
            < datetime.fromisoformat(budget.load()["deadline_utc"])
        ):
            if vite.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError("Owned website or tunnel process exited")
            time.sleep(1)
    except Exception as error:
        budget.event("execution_failure", exception_type=type(error).__name__)
        raise
    finally:
        u["client"].app.state.billing = None
        budget.close_intake()
        if server is not None:
            server.shutdown()
            server.server_close()
        if gateway_server is not None:
            gateway_server.should_exit = True
        provider.cleanup = True
        cleanup_complete = cleanup_pending(service, budget) if service is not None else True
        if not cleanup_complete:
            with budget.locked():
                state = budget.load()
                state["cleanup_requires_reconciliation"] = True
                budget.save(state)
            try:
                retain_cleanup_database(u["db"], budget)
            except Exception as error:
                budget.event("cleanup_database_snapshot_unavailable", exception_type=type(error).__name__)
        cleanup_complete = cleanup_subscriptions(provider, budget) and cleanup_complete
        for process in reversed(children):
            try:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            except Exception as error:
                cleanup_complete = False
                with budget.locked():
                    state = budget.load()
                    state["cleanup_processes_unresolved"] = True
                    budget.save(state)
                budget.event("owned_process_stop_unresolved", exception_type=type(error).__name__)
            budget.event(
                "owned_process_stopped",
                resource_id=str(process.pid),
                passed=process.poll() is not None,
            )
        if website_log is not None:
            website_log.close()
        budget.event("webhook_dashboard_cleanup_requires_verification", passed=False)
        budget.close_intake("finished" if cleanup_complete else "cleanup")
