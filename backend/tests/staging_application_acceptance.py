"""Approved staging application scenarios; reuses the existing worker and services.

No schema installer, provider/payment client or synthetic JWT signer in this
controller. Local tests inject disposable Auth/connection boundaries explicitly.
"""

import asyncio
import base64
import json
import os
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import requests
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_database import CatalogDatabase
from app.commercial.executor_connection import (
    STAGING_PROJECT,
    STAGING_SESSION_HOST,
    SessionPooler,
    connect_executor,
)
from app.commercial.subscription_service import VerifiedPaymentService
from psycopg import Error as DatabaseError
from psycopg.conninfo import make_conninfo
from websockets.exceptions import WebSocketException

ROOT = Path(__file__).resolve().parents[2]
URL = "https://" + STAGING_PROJECT + ".supabase.co"
NAMES = ("admin", "free", "plus", "pro")
FAILURES = (
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    AssertionError,
    DatabaseError,
    subprocess.SubprocessError,
    WebSocketException,
    ImportError,
    LookupError,
    AttributeError,
)


class AcceptanceFailure(RuntimeError):
    def __init__(self, check):
        self.safe_check = (
            check
            if len(check) <= 200
            and all(c.isascii() and (c.isalnum() or c in "_:-") for c in check)
            else "redacted_acceptance_check"
        )
        super().__init__(self.safe_check)


def expect(condition, name):
    if not condition:
        raise AcceptanceFailure(name)


class StagingAuth:
    def __init__(self, anon, service):
        self.anon, self.service = anon, service
        self.http = requests.Session()
        self.http.trust_env = False

    def request(self, method, path, *, admin=False, token=None, body=None):
        from run_staging_session_workflow import require_cleanup_window

        require_cleanup_window()
        key = self.service if admin else self.anon
        response = self.http.request(
            method,
            URL + "/auth/v1/" + path,
            headers={"apikey": key, "Authorization": "Bearer " + (token or key)},
            json=body,
            timeout=(3, 12),
            allow_redirects=False,
        )
        expect(
            response.status_code in (200, 201, 204),
            "auth_"
            + path.split("?")[0].replace("/", "_")
            + "_status_"
            + str(response.status_code),
        )
        return response.json() if response.content else {}

    def preflight(self):
        # Unverified claims only reject obvious input mistakes. Supabase still
        # authenticates both keys; this never grants authority from decoded data.
        for key, role in ((self.anon, "anon"), (self.service, "service_role")):
            expect(
                isinstance(key, str)
                and key.count(".") == 2
                and not any(c.isspace() for c in key),
                role + "_key_requires_legacy_jwt_from_staging_dashboard",
            )
            try:
                payload = key.split(".")[1]
                claims = json.loads(
                    base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
                )
                valid = (
                    isinstance(claims, dict)
                    and claims.get("ref") == STAGING_PROJECT
                    and claims.get("role") == role
                    and isinstance(claims.get("exp"), (int, float))
                    and claims["exp"] > time.time()
                )
            except (ValueError, TypeError, UnicodeError):
                valid = False
            expect(valid, role + "_key_wrong_project_role_expiry_or_format")
        self.request("GET", "settings")
        users = self.request("GET", "admin/users?page=1&per_page=1000", admin=True)[
            "users"
        ]
        expect(len(users) < 1000, "auth_inventory_requires_review")
        expect(not users, "staging_auth_not_empty_stop_review")
        addresses = {"c132-staging-" + name + "@acceptance.invalid" for name in NAMES}
        expect(
            not any(u.get("email") in addresses for u in users),
            "existing_synthetic_identity_stop_inspect_manifest",
        )

    def create(self, name, password, run):
        email = "c132-staging-" + name + "@acceptance.invalid"
        try:
            user = self.request(
                "POST",
                "admin/users",
                admin=True,
                body={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"c132_acceptance_run": run},
                },
            )
        except (requests.RequestException, AcceptanceFailure):
            # An acknowledgement can be lost after Auth commits. Read back the
            # exact owned intent; never issue a second create or reset a password.
            users = self.request("GET", "admin/users?page=1&per_page=1000", admin=True)[
                "users"
            ]
            owned = [
                u
                for u in users
                if u.get("email") == email
                and u.get("user_metadata", {}).get("c132_acceptance_run") == run
            ]
            expect(len(owned) == 1, "auth_creation_uncertain_stop_no_recreate")
            user = owned[0]
        expect(
            user.get("email") == email and user.get("email_confirmed_at"),
            "auth_creation_readback",
        )
        read = self.request("GET", "admin/users/" + user["id"], admin=True)
        expect(
            read["id"] == user["id"] and read["email"] == email,
            "auth_identity_readback",
        )
        return user["id"]

    def sign_in(self, name, password):
        return self.request(
            "POST",
            "token?grant_type=password",
            body={
                "email": "c132-staging-" + name + "@acceptance.invalid",
                "password": password,
            },
        )["access_token"]

    def sign_out(self, token):
        self.request("POST", "logout?scope=global", token=token)

    def close(self):
        self.anon = self.service = ""
        self.http.close()


class ApplicationAcceptance:
    def __init__(
        self, ca, run_id, anon, service, *, auth=None, local_port=None, evidence=None
    ):
        self.ca, self.run = Path(ca), str(run_id)
        self.anon = anon
        self.auth = auth or StagingAuth(anon, service)
        if local_port is None:
            os.environ.update(
                SAIIA_CLOUD_MODE="cloud",
                SUPABASE_URL=URL,
                SUPABASE_ANON_KEY=anon,
                SUPABASE_JWT_SECRET_OR_JWKS_CONFIG=URL
                + "/auth/v1/.well-known/jwks.json",
            )
            from app.auth.supabase_auth import get_auth_verification_config
            from app.cloud.supabase_config import get_supabase_settings

            get_supabase_settings.cache_clear()
            get_auth_verification_config.cache_clear()
        self.local_port = local_port  # Test injection only; CLI never supplies it.
        self.path = evidence or ROOT / "tmp/c132-staging-application-state.json"
        expect(
            not self.path.exists(),
            "prior_application_manifest_requires_recovery_review",
        )
        self.state = {
            "target": STAGING_PROJECT,
            "run_id": self.run,
            "stage": "prepared",
            "accounts": {},
            "sessions": {},
            "drafts": {},
            "offers": {},
            "passed": [],
            "cleanup_errors": [],
            "workers_stopped": False,
            "auth_sessions_signed_out": [],
            "policy_id": str(uuid4()),
            "screen_failure_id": str(uuid4()),
            "manual_recovery_id": str(uuid4()),
        }
        self.tokens, self.workers, self.passwords = {}, [], {}
        self.owner = None
        self.pool = None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Only non-secret IDs, checkpoints and assertions. Atomic file replacement.
        temporary = self.path.with_suffix(".next")
        temporary.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def stage(self, name):
        if not self.local_port:
            from run_staging_session_workflow import require_intake

            require_intake()
        self.state["stage"] = name
        self.save()
        print("APPLICATION: " + name, flush=True)

    def passed(self, name):
        self.state["passed"].append(name)
        self.save()

    def auth_preflight(self):
        self.auth.preflight()

    def clear_secrets(self):
        self.tokens.clear()
        self.passwords.clear()
        self.anon = ""
        self.auth.close()

    def dsn(self, role):
        if self.local_port:
            return make_conninfo(
                host="127.0.0.1",
                port=self.local_port,
                dbname="postgres",
                user=role,
                sslmode="disable",
            )
        return make_conninfo(
            host=STAGING_SESSION_HOST,
            port=5432,
            dbname="postgres",
            user=role + "." + STAGING_PROJECT,
            password=self.passwords[role],
            sslmode="verify-full",
            sslrootcert=str(self.ca.resolve()),
        )

    @property
    def target(self):
        return None if self.local_port else SessionPooler(STAGING_SESSION_HOST)

    def connect(self, role):
        return connect_executor(self.dsn(role), role, session_pooler=self.target)

    def query(self, sql, params=()):
        return self.owner.execute(sql, params)

    def http(
        self,
        worker,
        method,
        path,
        *,
        name="admin",
        expected=200,
        key=None,
        revision=None,
        body=None,
        token=None,
        files=None,
        data=None,
    ):
        headers = {}
        bearer = self.tokens.get(name) if token is None else token
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        if key:
            headers["Idempotency-Key"] = key
        if revision:
            headers["If-Match"] = '"' + str(revision) + '"'
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(
                method,
                f"http://127.0.0.1:{worker}/" + path.lstrip("/"),
                headers=headers,
                json=body,
                files=files,
                data=data,
                timeout=(2, 20),
                allow_redirects=False,
            )
        expect(
            response.status_code == expected,
            method
            + "_"
            + path.split("/")[-1]
            + "_expected_"
            + str(expected)
            + "_got_"
            + str(response.status_code),
        )
        return response

    def start_worker(self, port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Never terminate another listener.
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "PYTHONPATH",
                "PYTHONUTF8",
            }
        }
        env["PYTHON_DOTENV_DISABLED"] = "1"
        worker = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("hosted_subscription_worker.py")),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        self.workers.append(worker)
        config = {"host": "127.0.0.1", "http_port": port, "application": True}
        config["screen_failure_id"] = self.state["screen_failure_id"]
        config["manual_recovery_id"] = self.state["manual_recovery_id"]
        config["answers"] = True
        if self.local_port:
            config.update(
                pg_port=self.local_port,
                jwt_key=self.auth.key,
                local_auth_url=self.auth.url,
                anon_key=self.anon,
                local_blob_root=str(self.auth.db.directory / "acceptance_objects"),
            )
        else:
            config["staging"] = {
                "project": STAGING_PROJECT,
                "host": STAGING_SESSION_HOST,
                "ca": str(self.ca.resolve()),
                "anon_key": self.anon,
                "service_key": self.auth.service,
                "passwords": {
                    r: self.passwords[r]
                    for r in (
                        "usage_executor",
                        "catalog_draft_executor",
                        "catalog_public_reader",
                    )
                },
            }
        worker.stdin.write(json.dumps(config) + "\n")
        worker.stdin.flush()
        worker.stdin.close()
        config.clear()
        result = queue.Queue()
        reader = threading.Thread(
            target=lambda: result.put(worker.stdout.readline()), daemon=True
        )
        reader.start()
        try:
            line = result.get(timeout=40)
        except queue.Empty:
            raise AcceptanceFailure("worker_readiness_timeout") from None
        expect(
            line.strip() == '{"ready": true}',
            "worker_startup_failed_raw_details_suppressed",
        )
        self.state.setdefault("worker_pids", []).append(worker.pid)
        self.save()
        return worker

    def fixtures(self):
        self.stage("auth_identities_and_admin_grant")
        self.state["signup_cutoff"] = (
            self.query("SELECT clock_timestamp()").fetchone()[0].isoformat()
        )
        self.save()
        for name in NAMES:
            # Address/run intent exists before the non-transactional Auth request.
            self.state["pending_auth_name"] = name
            self.save()
            password = secrets.token_urlsafe(48)
            subject = self.auth.create(name, password, self.run)
            self.state["accounts"][name] = subject
            self.save()
            self.tokens[name] = self.auth.sign_in(name, password)
            del password
        self.state.pop("pending_auth_name", None)
        admin = self.state["accounts"]["admin"]
        with self.owner.transaction():
            self.query(
                "SELECT set_config('catalog.maintenance_approver',%s,true)", (admin,)
            )
            self.query(
                "INSERT INTO subscription_admin_permissions(subject_id,permission,revision,active,approved_by,reason) VALUES(%s,'subscriptions.manage',1,true,%s,'C13.2 disposable staging acceptance')",
                (admin, admin),
            )
        self.pool = CatalogDatabase(
            "true",
            self.dsn("catalog_draft_executor"),
            lifecycle_enabled="true",
            session_pooler=self.target,
        )
        self.pool.start()
        self.pool.service()  # Exact existing startup identity/ACL checks stay enabled.
        now = self.query("SELECT clock_timestamp()").fetchone()[0]
        from run_staging_session_workflow import smoke

        until = (
            min(now + timedelta(hours=24), smoke.DEADLINE)
            if not self.local_port
            else now + timedelta(hours=1)
        )
        policy = {
            "version": "1",
            "reviewer_rule_ref": "current_subscription_admin",
            "model_registry_version": "synthetic.models.v1",
            "valid_from": now.isoformat(),
            "valid_until": until.isoformat(),
            "allowed_refs": [
                "synthetic.storage",
                "synthetic.tax",
                "synthetic.rounding",
            ],
        }
        self.query(
            "INSERT INTO catalog_publication_policies VALUES(%s,'synthetic.lifecycle','synthetic.migration',1,true,%s::jsonb)",
            (self.state["policy_id"], json.dumps(policy)),
        )

    def catalog(self):
        from app.commercial.catalog_contract import CatalogDraft, _normalized
        from test_pricing_native import definition

        self.stage("catalog_create_save_reopen_review_publish")
        for name in ("free", "plus", "pro"):
            raw = definition(name)
            raw["plan"]["code"] = "c132-staging-" + name
            # Approved terms/prices unchanged; stable fixture plan codes identify staging.
            raw["internal_notes"] = "Disposable staging acceptance " + self.run
            raw = CatalogDraft.model_validate(raw).model_dump(mode="json")
            raw["terms"] = _normalized(
                CatalogDraft.model_validate(raw).terms
            ).model_dump(mode="json")
            keys = {
                step: str(uuid4()) for step in ("create", "review", "publish", "retire")
            }
            self.state["drafts"][name] = {"document": raw, "keys": keys}
            self.save()
            base = "/api/admin/catalog/drafts/" + raw["draft_id"]
            self.http(
                18765,
                "POST",
                "/api/admin/catalog/plans/" + raw["plan"]["plan_id"] + "/drafts",
                key=keys["create"],
                body={"document": raw, "reason": "Disposable staging create"},
            )
            saved = self.http(18766, "GET", base).json()
            self.state["drafts"][name]["reopened"] = saved
            self.save()
            expect(saved == raw, "catalog_reopen_exact_values")
            basis = self.http(
                18765,
                "POST",
                base + "/preview",
                body={
                    "scope": "publication_review",
                    "expected_revision": "1",
                    "contract_version": raw["contract_version"],
                    "intent": {
                        "action": "publish",
                        "valid_from": self.state["signup_cutoff"],
                    },
                },
            ).json()["basis"]
            self.state["drafts"][name]["basis"] = basis
            self.save()
            review = self.http(
                18765,
                "POST",
                base + "/publication-reviews",
                key=keys["review"],
                revision=1,
                body={
                    "basis": basis,
                    "confirmed": True,
                    "reason": "Disposable exact revision review",
                },
            ).json()
            self.state["drafts"][name]["review_id"] = review["receipt"]["review_id"]
            self.save()
            body = {
                "review_id": review["receipt"]["review_id"],
                "reason": "Disposable staging publication",
            }
            published = self.http(
                18765,
                "POST",
                base + "/publish",
                key=keys["publish"],
                revision=1,
                body=body,
            ).json()
            replay = self.http(
                18766,
                "POST",
                base + "/publish",
                key=keys["publish"],
                revision=1,
                body=body,
            ).json()
            expect(
                published["receipt"] == replay["receipt"], "publication_same_key_replay"
            )
            self.state["offers"][name] = published
            self.save()
        free = self.state["offers"]["free"]["receipt"]["offer_version_id"]
        self.query(
            "INSERT INTO subscription_configuration SELECT true,offer_version_id,fingerprint,%s,'subscriptions.approved.2026-10-24' FROM catalog_offer_versions WHERE offer_version_id=%s",
            (self.state["signup_cutoff"], free),
        )
        catalog = self.http(18766, "GET", "/api/catalog", name=None).json()
        expect(
            len(catalog["offers"]) == 3
            and all(not o["purchasable"] for o in catalog["offers"]),
            "three_public_offers_checkout_disabled",
        )
        self.passed(
            "catalog_save_reopen_exact_review_publication_replay_public_projection"
        )

    def identity_and_plans(self):
        self.stage("real_jwt_ownership_bootstrap_plan_transitions")
        config = self.query("SELECT * FROM subscription_configuration").fetchone()
        expect(config is not None, "test_configuration_present")
        try:
            self.query(
                "DELETE FROM subscription_configuration WHERE free_offer_id=%s",
                (self.state["offers"]["free"]["receipt"]["offer_version_id"],),
            )
            self.http(
                18765, "GET", "/api/account/subscription", name="admin", expected=503
            )
        finally:
            self.query(
                "INSERT INTO subscription_configuration VALUES(%s,%s,%s,%s,%s)", config
            )
        for name in NAMES:
            first = self.http(18765, "GET", "/api/account/subscription", name=name)
            expect(
                first.headers.get("cache-control") == "no-store",
                "private_cache_headers",
            )
            again = self.http(
                18766, "GET", "/api/account/subscription", name=name
            ).json()
            expect(
                first.json()["plan"] == again["plan"]
                and again["plan"]["name"] == "Free",
                "verified_free_bootstrap_idempotent",
            )
            session = str(uuid4())
            self.state["sessions"][name] = session
            self.save()
            self.query(
                "INSERT INTO interview_sessions(id,user_id) VALUES(%s,%s)",
                (session, self.state["accounts"][name]),
            )
        for token in ("", "invalid", self.tokens["free"][:-8] + "invalidx"):
            self.http(
                18765, "GET", "/api/account/subscription", token=token, expected=401
            )
        import jwt
        from cryptography.hazmat.primitives.asymmetric import ec

        foreign = jwt.encode(
            {
                "sub": self.state["accounts"]["free"],
                "role": "authenticated",
                "aud": "authenticated",
                "iss": "https://wrong-project.invalid/auth/v1",
                "exp": int(time.time()) + 600,
            },
            ec.generate_private_key(ec.SECP256R1()),
            algorithm="ES256",
            headers={"kid": str(uuid4())},
        )
        self.http(
            18766, "GET", "/api/account/subscription", token=foreign, expected=401
        )
        self.http(
            18765,
            "POST",
            "/api/account/subscription",
            name="free",
            body={"offer_version_id": str(uuid4())},
            expected=404,
        )
        expect(
            self.http(18765, "GET", "/api/commercial/admin/me", name="free").json()[
                "permissions"
            ]
            == [],
            "ordinary_permission_probe_empty",
        )
        expect(
            self.http(18765, "GET", "/api/commercial/admin/me").json()["permissions"]
            == ["subscriptions.manage"],
            "admin_permission_probe",
        )
        draft = self.state["drafts"]["free"]["document"]
        self.http(
            18766,
            "GET",
            "/api/admin/catalog/drafts/" + draft["draft_id"],
            name="free",
            expected=403,
        )
        path = (
            "/api/interview-sessions/" + self.state["sessions"]["plus"] + "/my-answers"
        )
        self.http(18765, "GET", path, name="free", expected=404)
        self.http(
            18765,
            "POST",
            path,
            name="free",
            key=str(uuid4()),
            body={"body": "Synthetic denied save"},
            expected=404,
        )
        # Save one unit before upgrading Plus, then verify it is not reset.
        self.clipboard("plus", "before-upgrade", "Synthetic retained save")
        self.http(
            18765,
            "POST",
            "/api/interview-sessions/" + self.state["sessions"]["free"] + "/my-answers",
            name="free",
            key=str(uuid4()),
            body={
                "body": "Synthetic forged identity",
                "user_id": self.state["accounts"]["pro"],
            },
            expected=422,
        )
        from app.answer_models import MODEL_CATALOG

        for name in ("plus", "pro"):
            raw = self.state["drafts"][name]["document"]
            now = self.query("SELECT clock_timestamp()").fetchone()[0]
            event = {
                "account_id": self.state["accounts"][name],
                "event_id": str(uuid4()),
                "offer_version_id": self.state["offers"][name]["receipt"][
                    "offer_version_id"
                ],
                "price_id": raw["terms"]["prices"][0]["price_id"],
                "paid_until": (now + timedelta(seconds=120)).isoformat(),
            }
            self.state.setdefault("payment_events", {})[name] = event
            self.save()

            def verify(evidence, exact=event):
                expect(
                    evidence == exact["event_id"], "synthetic_payment_evidence_denied"
                )
                return exact

            paid = VerifiedPaymentService(
                lambda: self.connect("usage_binding_executor"),
                verify=verify,
                model_keys=frozenset(MODEL_CATALOG),
            )
            expect(
                paid.apply(event["event_id"]) == paid.apply(event["event_id"]),
                "paid_event_idempotent",
            )
            current = self.http(
                18766, "GET", "/api/account/subscription", name=name
            ).json()
            expect(current["plan"]["name"].lower() == name, "trusted_paid_transition")
            if name == "plus":
                scheduled = {
                    "account_id": event["account_id"],
                    "event_id": str(uuid4()),
                    "kind": "cancel",
                    "expected_revision": current["plan"]["revision"],
                }
                self.state["cancel_event"] = scheduled
                self.save()
                cancelling = VerifiedPaymentService(
                    lambda: self.connect("usage_binding_executor"),
                    verify=lambda proof, exact=scheduled: (
                        exact if proof == exact["event_id"] else {}
                    ),
                    model_keys=frozenset(MODEL_CATALOG),
                )
                expect(
                    cancelling.schedule(scheduled["event_id"])
                    == cancelling.schedule(scheduled["event_id"]),
                    "cancellation_schedule_replay",
                )
        plus = self.http(18765, "GET", "/api/account/subscription", name="plus").json()
        balance = next(r for r in plus["usage"] if r["meter"] == "clipboard.new_saves")
        expect(
            balance["used"] == "1" and balance["allowance"] == "10",
            "upgrade_preserves_consumed_usage",
        )
        for name in ("free", "plus", "pro"):
            current = self.http(
                18765, "GET", "/api/account/subscription", name=name
            ).json()
            gates = {e["feature"]: e["allowed"] for e in current["features"]}
            expected = {
                e["feature"]: e["allowed"]
                for e in self.state["drafts"][name]["document"]["terms"]["entitlements"]
            }
            expect(gates == expected, "exact_registered_feature_matrix_" + name)
            expect(
                current["plan"]["offer_version_id"]
                == self.state["offers"][name]["receipt"]["offer_version_id"],
                "immutable_offer_identity_" + name,
            )
            expect(
                gates["answers.generate"] and gates["sessions.history"],
                "approved_unlimited_features",
            )
            auto = next(
                r for r in current["usage"] if r["meter"] == "auto.authorized_running"
            )
            expect(
                auto["mode"] == ("unlimited" if name == "pro" else "limited"),
                "finite_unlimited_auto",
            )
        self.passed(
            "jwt_auth_admin_ownership_free_bootstrap_trusted_paid_upgrade_usage_preserved"
        )

        for i in range(12):
            self.clipboard(
                "pro", "unlimited-" + str(i), "Synthetic unlimited save " + str(i)
            )
        self.passed("pro_unlimited_clipboard_exceeds_finite_plus_allowance")

    def fail_closed(self):
        self.stage("missing_configuration_and_feature_exclusions_fail_closed")
        from app.answer_models import MODEL_CATALOG
        from app.commercial.catalog_store import CatalogStoreError, ErrorCode
        from app.commercial.subscription_service import SubscriptionService

        service = SubscriptionService(
            lambda: self.connect("usage_executor"), model_keys=frozenset(MODEL_CATALOG)
        )
        for name in ("free", "plus", "pro"):
            actor = VerifiedActor(self.state["accounts"][name], self.tokens[name])
            for entitlement in self.state["drafts"][name]["document"]["terms"][
                "entitlements"
            ]:
                feature = entitlement["feature"]
                if not entitlement["allowed"]:
                    try:
                        service.require_feature(actor, feature)
                    except CatalogStoreError as error:
                        expect(
                            error.code == ErrorCode.DENIED, "feature_exclusion_denied"
                        )
                    else:
                        raise AcceptanceFailure("free_exclusion_not_enforced")
                else:
                    service.require_feature(actor, feature)
        self.passed("registered_feature_exclusions_missing_configuration_fails_closed")

    def transitions(self):
        self.stage("real_clock_paid_expiry_cancellation_and_scheduled_downgrade")
        from app.answer_models import MODEL_CATALOG
        from app.commercial.subscription_service import VerifiedPaymentService

        def wait_until(value):
            until = datetime.fromisoformat(value)
            deadline = time.monotonic() + 135
            while self.query("SELECT clock_timestamp()<%s", (until,)).fetchone()[0]:
                expect(time.monotonic() < deadline, "paid_period_wait_bounded")
                if not self.local_port:
                    from run_staging_session_workflow import require_intake

                    require_intake()
                time.sleep(0.2)

        for name in ("plus", "pro"):
            wait_until(self.state["payment_events"][name]["paid_until"])
            current = self.http(
                18766, "GET", "/api/account/subscription", name=name
            ).json()
            expect(
                current["plan"]["name"] == "Free"
                and current["plan"]["valid_until"] is None,
                "paid_expiry_or_cancellation_free",
            )
            saved = self.http(
                18766,
                "GET",
                "/api/interview-sessions/"
                + self.state["sessions"][name]
                + "/my-answers",
                name=name,
            ).json()["items"]
            expect(
                len(saved) == (1 if name == "plus" else 12),
                "saved_data_retained_after_expiry",
            )
        now = self.query("SELECT clock_timestamp()").fetchone()[0]
        pro = self.state["drafts"]["pro"]["document"]
        event = {
            "account_id": self.state["accounts"]["pro"],
            "event_id": str(uuid4()),
            "offer_version_id": self.state["offers"]["pro"]["receipt"][
                "offer_version_id"
            ],
            "price_id": pro["terms"]["prices"][0]["price_id"],
            "paid_until": (now + timedelta(seconds=15)).isoformat(),
        }
        self.state["downgrade_payment"] = event
        self.save()
        service = VerifiedPaymentService(
            lambda: self.connect("usage_binding_executor"),
            verify=lambda proof: event if proof == event["event_id"] else {},
            model_keys=frozenset(MODEL_CATALOG),
        )
        bound = service.apply(event["event_id"])
        change = {
            "account_id": event["account_id"],
            "event_id": str(uuid4()),
            "kind": "downgrade",
            "expected_revision": bound["revision"],
            "offer_version_id": self.state["offers"]["plus"]["receipt"][
                "offer_version_id"
            ],
            "price_id": self.state["drafts"]["plus"]["document"]["terms"]["prices"][0][
                "price_id"
            ],
            "paid_until": (now + timedelta(minutes=20)).isoformat(),
        }
        self.state["downgrade_schedule"] = change
        self.save()
        service = VerifiedPaymentService(
            lambda: self.connect("usage_binding_executor"),
            verify=lambda proof: change if proof == change["event_id"] else {},
            model_keys=frozenset(MODEL_CATALOG),
        )
        expect(
            service.schedule(change["event_id"])
            == service.schedule(change["event_id"]),
            "downgrade_schedule_retry",
        )
        expect(
            self.http(18765, "GET", "/api/account/subscription", name="pro").json()[
                "plan"
            ]["name"]
            == "Pro",
            "downgrade_not_early",
        )
        wait_until(event["paid_until"])
        current = self.http(
            18766, "GET", "/api/account/subscription", name="pro"
        ).json()
        expect(current["plan"]["name"] == "Plus", "downgrade_at_paid_end")
        balance = next(
            r for r in current["usage"] if r["meter"] == "clipboard.new_saves"
        )
        expect(
            balance["used"] == "12" and balance["allowance"] == "10",
            "downgrade_keeps_over_cap_usage",
        )
        self.clipboard(
            "pro", "downgraded-overcap", "Synthetic overcap attempt", expected=429
        )
        self.passed(
            "actual_paid_expiry_free_cancel_at_end_downgrade_at_end_usage_data_preserved"
        )

    def clipboard(self, name, label, text, *, worker=18765, expected=201):
        key = self.state.setdefault("clipboard_keys", {}).setdefault(
            name + ":" + label, str(uuid4())
        )
        self.save()
        return self.http(
            worker,
            "POST",
            "/api/interview-sessions/" + self.state["sessions"][name] + "/my-answers",
            name=name,
            expected=expected,
            key=key,
            body={"body": text},
        )

    def quota(self):
        self.stage("two_worker_last_unit_retry_conflict_durable_settlement")
        first = self.clipboard("free", "replay", "Synthetic immutable answer").json()
        expect(
            self.clipboard(
                "free", "replay", "Synthetic immutable answer", worker=18766
            ).json()
            == first,
            "clipboard_same_key_replay",
        )
        self.clipboard("free", "replay", "Conflicting synthetic body", expected=409)
        for i in range(3):
            self.clipboard("free", "initial-" + str(i), "Synthetic save " + str(i))
        # Prepare IDs BEFORE two threads touch the evidence file.
        for port in (18765, 18766):
            self.state["clipboard_keys"]["free:race-" + str(port)] = str(uuid4())
        self.save()
        gate = threading.Barrier(2)

        def race(port):
            gate.wait(timeout=5)
            key = self.state["clipboard_keys"]["free:race-" + str(port)]
            with requests.Session() as http:
                http.trust_env = False
                return http.post(
                    f"http://127.0.0.1:{port}/api/interview-sessions/{self.state['sessions']['free']}/my-answers",
                    headers={
                        "Authorization": "Bearer " + self.tokens["free"],
                        "Idempotency-Key": key,
                    },
                    json={"body": "Synthetic last unit"},
                    timeout=20,
                ).status_code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(race, (18765, 18766)))
        expect(sorted(results) == [201, 429], "two_workers_exactly_one_last_unit")
        current = self.http(
            18765, "GET", "/api/account/subscription", name="free"
        ).json()
        balance = next(
            r for r in current["usage"] if r["meter"] == "clipboard.new_saves"
        )
        expect(
            balance["used"] == "5" and balance["reserved"] == "0",
            "clipboard_exactly_five_settled",
        )
        rows = self.http(
            18766,
            "GET",
            "/api/interview-sessions/" + self.state["sessions"]["free"] + "/my-answers",
            name="free",
        ).json()["items"]
        expect(len(rows) == 5 and rows[0], "five_durable_owned_answers")
        self.state["quota_assertion"] = {
            "statuses": results,
            "used": "5",
            "reserved": "0",
            "durable_rows": len(rows),
        }
        self.passed(
            "two_worker_clipboard_exhaustion_replay_conflict_exactly_once_durable_rows"
        )

    async def relay(self):
        import websockets

        self.stage("two_worker_relay_single_owner_crash_lease_recovery")
        run = str(uuid4())
        self.state["relay_run_id"] = run
        self.save()

        async def start(port, stream):
            ws = await websockets.connect(
                f"ws://127.0.0.1:{port}/api/account/audio/stream",
                origin="https://synthetic.invalid",
                additional_headers={"Authorization": "Bearer " + self.tokens["admin"]},
                open_timeout=10,
                max_size=16384,
            )
            await ws.send(
                json.dumps(
                    {
                        "stream_id": stream,
                        "session_id": self.state["sessions"]["admin"],
                        "source": "both",
                    }
                )
            )
            return ws

        async def until(ws, key):
            for _ in range(30):
                row = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if key in row:
                    return row
                expect("error" not in row, "relay_unexpected_error")
            raise AcceptanceFailure("relay_expected_event_missing")

        first = await start(18765, run)
        try:
            await until(first, "ready")
            duplicate = await start(18766, run)
            try:
                expect(
                    (await until(duplicate, "error"))["error"]["code"]
                    == "subscription_relay_replay",
                    "relay_duplicate_fenced",
                )
            finally:
                await duplicate.close()
            competing = await start(18766, str(uuid4()))
            try:
                expect(
                    (await until(competing, "error"))["error"]["code"]
                    == "subscription_auto_busy",
                    "account_single_owner_across_workers",
                )
            finally:
                await competing.close()
            await first.send((1).to_bytes(8, "big") + bytes(3200))
            self.workers[0].kill()
            self.workers[0].wait(timeout=5)
            # Server-clock lease expires naturally. Never time-travel managed rows.
            deadline = time.monotonic() + 35
            while self.query(
                "SELECT EXISTS(SELECT FROM usage_operations WHERE resource_id=%s AND lease_until>clock_timestamp())",
                (run,),
            ).fetchone()[0]:
                expect(time.monotonic() < deadline, "worker_crash_lease_did_not_expire")
                await asyncio.sleep(0.2)
            self.http(18766, "GET", "/api/account/subscription", name="admin")
            state = self.query(
                "SELECT state FROM usage_operations WHERE resource_id=%s", (run,)
            ).fetchone()
            expect(
                state is not None and state[0] == "settled",
                "crashed_run_reconciles_settled",
            )
            self.start_worker(18765)
            recovery = await start(18765, str(uuid4()))
            try:
                await until(recovery, "ready")
                await recovery.send("stop")
            finally:
                await recovery.close()
            self.passed(
                "actual_two_workers_relay_replay_single_owner_process_death_lease_settlement_restart"
            )
        finally:
            await first.close()

    def screen(self):
        from test_screen_context import context

        self.stage("screen_failed_release_reference_replay_finite_settlement")

        def fresh(action="new", fail=False):
            body, images = context()
            body["identity"].update(
                cloudSessionId=self.state["sessions"]["free"],
                accountGeneration=0,
                threadId=str(uuid4()),
                turnId=str(uuid4()),
                operationId=self.state["screen_failure_id"] if fail else str(uuid4()),
                requestId=str(uuid4()),
            )
            body.update(
                action=action,
                contextKind="reference" if action == "reference" else "question",
            )
            self.state.setdefault("screen_operations", []).append(body["identity"])
            self.save()
            return body, images

        def post(body, images, expected=200, name="free", worker=18765):
            return self.http(
                worker,
                "POST",
                "/api/screen/analyze-context",
                name=name,
                expected=expected,
                data={"context": json.dumps(body)},
                files={k: ("synthetic.png", v, "image/png") for k, v in images.items()},
            )

        b, f = fresh(fail=True)
        expect(post(b, f).json()["outcome"] == "failed", "screen_failed_result")
        b, f = fresh("reference")
        expect(
            post(b, f).json()["outcome"] == "reference_accepted",
            "screen_reference_not_chargeable",
        )
        for number in range(5):
            b, f = fresh()
            first = post(b, f).json()
            expect(first["outcome"] == "answered", "screen_answered_saved")
            if number == 0:
                expect(
                    post(b, f, worker=18766).json() == first,
                    "screen_saved_result_replay",
                )
                post(b, f, name="admin", expected=404)
        b, f = fresh()
        post(b, f, expected=429)
        current = self.http(
            18765, "GET", "/api/account/subscription", name="free"
        ).json()
        balance = next(r for r in current["usage"] if r["meter"] == "screen.analyses")
        expect(
            balance["used"] == "5" and balance["reserved"] == "0",
            "screen_exact_charge_release",
        )
        count = self.query(
            "SELECT count(*) FROM subscription_screen_results WHERE account_id=%s AND response->>'outcome'='answered'",
            (self.state["accounts"]["free"],),
        ).fetchone()[0]
        expect(count == 5, "screen_five_durable_results")
        self.passed(
            "screen_failed_release_reference_zero_replay_cross_account_five_durable_exactly_once_exhaustion"
        )

    def resumes(self):
        self.stage("resume_initial_history_replay_failed_replacement_success_limits")

        def upload(label, expected=201, worker=18765):
            key = self.state.setdefault("resume_keys", {}).setdefault(
                label, str(uuid4())
            )
            self.save()
            response = self.http(
                worker,
                "POST",
                "/api/resumes",
                name="free",
                key=key,
                expected=expected,
                files={
                    "file": (
                        "synthetic.txt",
                        b"Synthetic candidate software experience",
                        "text/plain",
                    )
                },
            )
            if expected == 201:
                self.state.setdefault("resume_ids", {})[label] = response.json()["id"]
                self.save()
            return response

        def ready(identifier, fail=False):
            extracted = self.http(
                18765, "POST", "/api/resumes/" + identifier + "/extract", name="free"
            ).json()
            if fail:
                extracted["profile"]["professional_summary"] = "FAIL_INDEX"
            return self.http(
                18765,
                "POST",
                "/api/resumes/" + identifier + "/confirm",
                name="free",
                expected=502 if fail else 200,
                body={
                    "extraction_attempt": extracted["extraction_attempt"],
                    "profile": extracted["profile"],
                },
            )

        first = upload("initial").json()["id"]
        expect(
            upload("initial", worker=18766).json()["id"] == first,
            "resume_upload_replay",
        )
        ready(first)
        failed = upload("failed-replacement").json()["id"]
        ready(failed, fail=True)
        current = self.http(18766, "GET", "/api/resumes/current", name="free").json()
        expect(current["resume"]["id"] == first, "failed_resume_keeps_previous_usable")
        replacement = upload("successful-replacement").json()["id"]
        ready(replacement)
        self.http(
            18766,
            "GET",
            "/api/resumes/" + replacement + "/status",
            name="admin",
            expected=404,
        )
        self.http(18765, "DELETE", "/api/resumes/" + replacement, name="free")
        upload("delete-reupload-blocked", expected=429)
        current = self.http(
            18766, "GET", "/api/account/subscription", name="free"
        ).json()
        balance = next(
            r for r in current["usage"] if r["meter"] == "resume.replacements"
        )
        expect(
            balance["used"] == "1" and balance["reserved"] == "0",
            "replacement_settled_only_once",
        )
        self.passed(
            "resume_initial_separate_replay_failed_replacement_retains_previous_one_success_delete_reupload_denied"
        )

    def cleanup(self):
        errors = self.state["cleanup_errors"]

        def attempt(name, fn):
            try:
                fn()
            except FAILURES as error:
                errors.append({"stage": name, "error": type(error).__name__})

        for worker in self.workers:

            def stop(w=worker):
                if w.poll() is None:
                    w.terminate()
                w.wait(timeout=8)
                if w.stdout:
                    w.stdout.close()

            attempt("stop_worker", stop)
        self.state["workers_stopped"] = all(w.poll() is not None for w in self.workers)

        def settle_expired_runs():
            from app.answer_models import MODEL_CATALOG
            from app.commercial.subscription_service import SubscriptionService

            service = SubscriptionService(
                lambda: self.connect("usage_executor"),
                model_keys=frozenset(MODEL_CATALOG),
            )
            deadline = time.monotonic() + 20
            accounts = list(self.state["accounts"].values())
            if not accounts:
                return
            while True:
                for name, subject in self.state["accounts"].items():
                    if name in self.tokens:
                        service.current(VerifiedActor(subject, self.tokens[name]))
                outstanding = self.query(
                    "SELECT count(*) FROM usage_periods WHERE account_id=ANY(%s::uuid[]) AND reserved>0",
                    (accounts,),
                ).fetchone()[0]
                active = self.query(
                    "SELECT count(*) FROM subscription_auto_runs WHERE account_id=ANY(%s::uuid[]) AND active",
                    (accounts,),
                ).fetchone()[0]
                if outstanding == active == 0:
                    self.state["reservations_and_runs_cleared"] = True
                    return
                expect(time.monotonic() < deadline, "reservation_or_active_run_remains")
                time.sleep(0.25)

        if self.state["offers"] and len(self.state["offers"]) == 3:
            attempt("settle_expired_runs", settle_expired_runs)
        if self.pool is not None:
            actor = VerifiedActor(
                self.state["accounts"]["admin"], self.tokens.get("admin", "")
            )
            from app.commercial.catalog_store import CatalogStoreError, ErrorCode

            for name, draft in self.state["drafts"].items():
                if name not in self.state["offers"]:

                    def recover(n=name, d=draft):
                        try:
                            outcome = self.pool.lifecycle_service().operation(
                                actor, d["keys"]["publish"]
                            )
                        except CatalogStoreError as error:
                            if error.code == ErrorCode.NOT_FOUND:
                                return
                            raise
                        self.state["offers"][n] = outcome.model_dump(mode="json")
                        self.save()

                    attempt("recover_uncertain_publication_" + name, recover)
            for name, published in self.state["offers"].items():

                def retire(n=name, p=published):
                    self.pool.lifecycle_service().retire(
                        actor,
                        p["receipt"]["offer_version_id"],
                        expected_revision=int(p["current"]["revision"]),
                        request_id=self.state["drafts"][n]["keys"]["retire"],
                        reason="Disposable staging cleanup",
                    )

                attempt("retire_" + name, retire)
            attempt("close_catalog_controller", self.pool.close)

        def clear_configuration():
            free = (
                self.state["offers"]
                .get("free", {})
                .get("receipt", {})
                .get("offer_version_id")
            )
            with self.owner.transaction():
                if free:
                    self.query(
                        "DELETE FROM subscription_configuration WHERE free_offer_id=%s",
                        (free,),
                    )
                self.query(
                    "UPDATE catalog_publication_policies SET active=false,revision=revision+1 WHERE policy_id=%s AND active",
                    (self.state["policy_id"],),
                )

        attempt("disable_fixture_configuration", clear_configuration)
        admin = self.state["accounts"].get("admin")
        if admin:

            def revoke():
                with self.owner.transaction():
                    self.query(
                        "SELECT set_config('catalog.maintenance_approver',%s,true)",
                        (admin,),
                    )
                    self.query(
                        "UPDATE subscription_admin_permissions SET active=false,revision=revision+1,approved_by=%s,reason='C13.2 staging cleanup' WHERE subject_id=%s AND permission='subscriptions.manage' AND active",
                        (admin, admin),
                    )
                expect(
                    not self.query(
                        "SELECT EXISTS(SELECT FROM subscription_admin_permissions WHERE subject_id=%s AND active)",
                        (admin,),
                    ).fetchone()[0],
                    "admin_revocation_readback",
                )

            attempt("revoke_synthetic_admin", revoke)
        for name, token in self.tokens.items():

            def signout(n=name, t=token):
                self.auth.sign_out(t)
                self.state["auth_sessions_signed_out"].append(n)

            attempt("signout_" + name, signout)
        self.state["retained_history"] = (
            "Synthetic Auth identities, immutable offers, permission audit, results and usage retained; no Auth/account deletion. Access JWTs may survive until expiry."
        )
        self.save()

    def audit(self):
        from app.commercial.usage_store import UsageReconciler

        self.stage("restricted_reconciler_audit_all_fixture_periods")
        reconciler = UsageReconciler(
            lambda: self.connect("usage_reconciler"),
            policy=lambda action, _doc, _terms: action == "audit",
        )
        rows = self.query(
            "SELECT account_id,period_id,used,reserved FROM usage_periods WHERE account_id=ANY(%s::uuid[]) ORDER BY account_id,period_id",
            (list(self.state["accounts"].values()),),
        ).fetchall()
        for account, period, used, reserved in rows:
            first = reconciler.audit(str(account), str(period))
            expect(
                first == reconciler.audit(str(account), str(period)),
                "audit_replay_no_mutation",
            )
            expect(
                first["consistent"]
                and first["used"] == used
                and first["reserved"] == reserved == 0,
                "ledger_aggregate_consistent_no_reservations",
            )
        self.state["audited_periods"] = len(rows)
        self.passed(
            "restricted_reconciler_all_periods_consistent_repeated_audit_no_double_settlement"
        )

    def answers_and_shared_features(self):
        self.stage("manual_checkpoint_save_only_recovery_notes_ask_history_export")
        sid = self.state["sessions"]["admin"]
        body = {
            "question": "What is dependency injection?",
            "category": "technical",
            "source": "chat",
            "session_id": sid,
            "request_id": self.state["manual_recovery_id"],
        }
        self.http(18765, "POST", "/generate/", body=body, expected=502)
        phase = self.query(
            "SELECT state FROM session_generation_turns WHERE session_id=%s AND request_id=%s",
            (sid, body["request_id"]),
        ).fetchone()
        expect(
            phase is not None and phase[0] == "checkpoint",
            "durable_checkpoint_before_save_only_recovery",
        )
        answer = self.http(
            18766, "POST", "/generate/", body={**body, "recover_turn": True}
        ).json()
        expect(
            "18765" in answer["answer"] and "18766" not in answer["answer"],
            "recovery_reuses_original_provider_checkpoint",
        )
        expect(
            self.http(18765, "POST", "/generate/", body=body).json()["answer"]
            == answer["answer"],
            "completed_answer_replay",
        )
        self.http(18766, "POST", "/generate/", body=body, name="free", expected=404)
        before = self.query(
            "SELECT count(*) FROM interview_session_transcript_entries WHERE session_id=%s",
            (sid,),
        ).fetchone()[0]
        expect(before == 1, "one_durable_transcript_after_recovery_replay")
        notes_path = "/api/interview-sessions/" + sid + "/notes/generate"
        note_key = str(uuid4())
        self.state["notes_key"] = note_key
        self.save()
        notes = self.http(
            18765, "POST", notes_path, key=note_key, body={"force_regenerate": False}
        ).json()
        expect(
            self.http(
                18766,
                "POST",
                notes_path,
                key=note_key,
                body={"force_regenerate": False},
            ).json()
            == notes,
            "notes_durable_replay",
        )
        question = {
            "question": "How can I improve?",
            "request_id": str(uuid4()),
            "include_notes": True,
        }
        self.state["ask_request_id"] = question["request_id"]
        self.save()
        ask_path = "/api/interview-sessions/" + sid + "/ask-ai"
        asked = self.http(18765, "POST", ask_path, body=question).json()
        expect(
            self.http(18766, "POST", ask_path, body=question).json()["answer_text"]
            == asked["answer_text"],
            "ask_durable_replay",
        )
        self.http(
            18766,
            "POST",
            ask_path,
            body={**question, "question": "Different synthetic question"},
            expected=409,
        )
        self.http(18765, "GET", "/api/interview-sessions")
        self.http(
            18766, "GET", "/api/interview-sessions/" + sid + "/transcript/download"
        )
        self.http(
            18766,
            "GET",
            "/api/interview-sessions/" + sid + "/notes",
            name="free",
            expected=404,
        )
        self.passed(
            "manual_durable_checkpoint_save_only_recovery_replay_notes_ask_history_export_ownership"
        )

    def __call__(self, owner, passwords):
        self.owner, self.passwords = owner, dict(passwords)
        try:
            self.stage("read_only_application_baseline")
            baseline = self.query(
                "SELECT (SELECT count(*) FROM subscription_configuration),(SELECT count(*) FROM account_plan_bindings),(SELECT count(*) FROM catalog_offer_versions),(SELECT count(*) FROM subscription_admin_permissions WHERE active)"
            ).fetchone()
            expect(
                baseline == (0, 0, 0, 0),
                "staging_application_baseline_not_empty_stop_review",
            )
            self.fixtures()
            self.stage("start_two_application_workers")
            self.start_worker(18765)
            self.start_worker(18766)
            self.catalog()
            self.identity_and_plans()
            self.fail_closed()
            self.quota()
            self.screen()
            self.resumes()
            self.answers_and_shared_features()
            asyncio.run(self.relay())
            self.transitions()
            self.audit()
            self.state["status"] = "implemented_scenarios_passed"
        except FAILURES as error:
            self.state["status"] = "failed"
            self.state["failure"] = {
                "stage": self.state["stage"],
                "type": type(error).__name__,
                "check": (
                    str(error) if isinstance(error, AcceptanceFailure) else "redacted"
                ),
            }
            code = getattr(error, "sqlstate", None)
            if isinstance(code, str) and len(code) == 5 and code.isalnum():
                self.state["failure"]["sqlstate"] = code
            if isinstance(error, AcceptanceFailure):
                raise
            raise AcceptanceFailure(
                "application_" + self.state["stage"] + "_" + type(error).__name__
            ) from None
        finally:
            self.cleanup()
        expect(
            not self.state["cleanup_errors"], "application_cleanup_requires_recovery"
        )
        return {
            k: self.state[k]
            for k in (
                "passed",
                "workers_stopped",
                "auth_sessions_signed_out",
                "cleanup_errors",
            )
        }
