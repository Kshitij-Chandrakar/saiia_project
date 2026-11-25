"""Failure injection for the single-process credential lifecycle; no network."""

from copy import deepcopy
from contextlib import nullcontext

import pytest
import run_staging_session_workflow as workflow

real_project_ownership = workflow.project_ownership


@pytest.fixture(autouse=True)
def isolated_project_ownership(monkeypatch):
    monkeypatch.setattr(workflow, "project_ownership", lambda _: nullcontext(lambda: None))


class Owner:
    closed = False

    def close(self):
        self.closed = True


def clean_state():
    return {
        "roles": [
            {
                "name": role,
                "login": False,
                "password_cleared": True,
                "expired": True,
                "elevated": False,
                "member": False,
            }
            for role in workflow.ROLES
        ],
        "executor_sessions": 0,
    }


@pytest.fixture
def local(monkeypatch):
    events = []
    owner = Owner()
    state = clean_state()
    monkeypatch.setattr(workflow, "require_intake", lambda: None)
    monkeypatch.setattr(workflow, "require_cleanup_window", lambda: None)
    monkeypatch.setattr(workflow, "read_state", lambda _: deepcopy(state))

    def provision(_conn, passwords):
        assert len(set(passwords.values())) == 5
        assert all(len(x) >= 64 for x in passwords.values())
        events.append("provision")

    def cleanup(_conn):
        events.append("cleanup")
        return clean_state()

    monkeypatch.setattr(workflow, "provision", provision)
    monkeypatch.setattr(workflow, "cleanup", cleanup)
    return owner, events, state


def test_success_has_one_owner_connection_and_automatic_cleanup(local, capsys):
    owner, events, _ = local
    connections = []
    credentials = []

    def factory():
        connections.append(True)
        return owner

    def smoke(role, password):
        credentials.append(password)
        events.append(role)

    result = workflow.execute_workflow(factory, smoke)
    assert len(connections) == 1 and len(set(credentials)) == 5
    assert events == ["provision", *workflow.ROLES, "cleanup"]
    assert result["cleanup_verified"] and result["error"] is None and owner.closed
    output = capsys.readouterr().out
    assert all(secret not in output for secret in credentials)


def test_smoke_failure_stops_remaining_intake_and_cleans(local):
    owner, events, _ = local

    def fail(role, _password):
        events.append(role)
        raise RuntimeError("synthetic-secret-that-must-not-escape")

    result = workflow.execute_workflow(lambda: owner, fail)
    assert events == ["provision", workflow.ROLES[0], "cleanup"]
    assert result["cleanup_verified"] and result["error"] == "RuntimeError"
    assert result["smoke_passed"] == [] and owner.closed


def test_provision_failure_still_attempts_cleanup(local, monkeypatch):
    owner, events, _ = local

    def fail(*_):
        raise RuntimeError("synthetic interrupted provision")

    monkeypatch.setattr(workflow, "provision", fail)
    result = workflow.execute_workflow(lambda: owner, fail)
    assert events == ["cleanup"] and result["cleanup_verified"]
    assert not result["provisioned"]


def test_named_session_failure_is_recorded_without_skipping_cleanup(local):
    owner, events, _ = local

    def fail(*_):
        workflow.smoke.verify_session(False, "reset_timeout_statement")

    result = workflow.execute_workflow(lambda: owner, fail)
    assert result["failure_check"] == "reset_timeout_statement"
    assert result["error"] == "SessionCheckFailure"
    assert result["cleanup_verified"] and events[-1] == "cleanup"


def test_cleanup_failure_is_explicit_and_closes_owner(local, monkeypatch, capsys):
    owner, _, _ = local

    def fail(*_):
        raise RuntimeError("private-value-must-not-appear")

    monkeypatch.setattr(workflow, "cleanup", fail)
    result = workflow.execute_workflow(lambda: owner, lambda *_: None)
    assert not result["cleanup_verified"] and result["cleanup_error"] == "RuntimeError"
    output = capsys.readouterr().out
    assert "CLEANUP FAILED" in output and "--cleanup-only" in output
    assert "private-value" not in output and owner.closed


def test_interrupted_prior_state_recovered_before_provision(local):
    owner, events, state = local
    state["roles"][0]["password_cleared"] = False
    result = workflow.execute_workflow(lambda: owner, lambda *_: None)
    assert events == ["cleanup", "provision", "cleanup"]
    assert result["cleanup_verified"]


def test_cleanup_only_never_generates_or_provisions(local, monkeypatch):
    owner, events, _ = local

    def forbidden(*_):
        raise AssertionError("no password generation or smoke")

    monkeypatch.setattr(workflow.secrets, "token_urlsafe", forbidden)
    result = workflow.execute_workflow(lambda: owner, forbidden, cleanup_only=True)
    assert events == ["cleanup"] and result["cleanup_verified"]


def test_simultaneous_workflow_is_rejected_before_auth(monkeypatch, tmp_path):
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    with workflow.single_workflow(), pytest.raises(OSError), workflow.single_workflow():
        raise AssertionError("second workflow admitted")
    with workflow.single_workflow():
        pass


def test_staging_scope_does_not_expand_to_privacy_or_admin_executors():
    assert workflow.ROLES == (
        "catalog_draft_executor",
        "catalog_public_reader",
        "usage_binding_executor",
        "usage_executor",
        "usage_reconciler",
    )


@pytest.mark.parametrize("acquired", [False, True])
def test_project_lock_precedes_inspection_and_survives_owner_reconnect(local, monkeypatch, acquired):
    owner, events, _ = local
    class Guard:
        closed = False
        def execute(self, query, params=()):
            assert not self.closed
            return type("Row", (), {"fetchone": lambda _: (acquired,)})()
        def close(self):
            self.closed = True
    guard = Guard()
    connections = [guard, owner]
    monkeypatch.setattr(workflow, "project_ownership", real_project_ownership)
    monkeypatch.setattr(workflow, "require_cleanup_window", lambda: None)
    def factory():
        assert connections
        return connections.pop(0)
    result = workflow.execute_workflow(factory, lambda *_: None, cleanup_only=True)
    assert guard.closed
    if acquired:
        assert events == ["cleanup"] and result["cleanup_verified"]
    else:
        assert events == [] and not result["provisioned"] and not result["cleanup_verified"]
        assert connections == [owner]


def test_rejected_application_baseline_does_not_run_fixture_cleanup(monkeypatch):
    from staging_application_acceptance import ApplicationAcceptance, AcceptanceFailure
    app = object.__new__(ApplicationAcceptance)
    app.state = {}
    app.stage = lambda name: app.state.update(stage=name)
    app.query = lambda *_: type("Row", (), {"fetchone": lambda _: (1, 0, 0, 0)})()
    app.fixtures = lambda: pytest.fail("baseline rejection must precede fixture writes")
    app.cleanup = lambda: pytest.fail("baseline rejection must not write cleanup")
    with pytest.raises(AcceptanceFailure, match="baseline_not_empty"):
        app(object(), {})


def test_launcher_cutoff_stops_owned_grandchild(tmp_path):
    import json
    import os
    import shutil
    import socket
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell required for actual process-tree containment")
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    (tmp_path / "tmp").mkdir()
    ca = tmp_path / "ca.crt"
    ca.touch()
    source = Path(workflow.__file__).with_name("start_staging_session_smoke.ps1").read_text()
    until = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    launcher = tests / "start_staging_session_smoke.ps1"
    launcher.write_text(source.replace("2026-10-26T13:08:53Z", until))
    info = tmp_path / "child.json"
    child = ("import socket,time,json;from pathlib import Path;"
             "s=socket.socket();s.bind(('127.0.0.1',0));s.listen();"
             f"Path({str(info)!r}).write_text(json.dumps(s.getsockname()[1]));time.sleep(20)")
    (tests / "run_staging_session_workflow.py").write_text(
        "import os,sys,time,subprocess;from pathlib import Path\n"
        "if os.name!='nt' and os.getpgrp()!=os.getpid():os.setsid()\n"
        "gate=Path(sys.argv[sys.argv.index('--launcher-gate')+1])\n"
        "while not gate.exists():time.sleep(.01)\n"
        f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
        "time.sleep(30)\n"
    )
    result = subprocess.run([powershell, "-NoProfile", "-File", str(launcher), "-Ca", str(ca), "-Python", sys.executable, "-Application"],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode != 0 and "OWNED PROCESS TREE STOPPED" in result.stdout
    assert "Cleanup unverified" in result.stdout + result.stderr
    assert info.exists(), "fixture must start a real child before cutoff"
    port = json.loads(info.read_text())
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_worker_stop_escalates_and_missing_audit_periods_cannot_pass():
    import subprocess
    from staging_application_acceptance import ApplicationAcceptance, AcceptanceFailure
    events = []
    class Worker:
        stdout = None
        killed = False
        def poll(self):
            return 0 if self.killed else None
        def terminate(self):
            events.append("terminate")
        def kill(self):
            self.killed = True
            events.append("kill")
        def wait(self, timeout):
            events.append(timeout)
            if not self.killed:
                raise subprocess.TimeoutExpired("synthetic-worker", timeout)
    ApplicationAcceptance.stop_worker(Worker())
    assert events == ["terminate", 8, "kill", 5]
    app = object.__new__(ApplicationAcceptance)
    app.state = {"accounts": {"free": "synthetic-account"}}
    app.stage = lambda _: None
    app.query = lambda *_: type("Rows", (), {"fetchall": lambda _: []})()
    app.passed = lambda _: pytest.fail("empty reconciliation cannot establish coverage")
    with pytest.raises(AcceptanceFailure, match="missing_fixture_usage_periods"):
        app.audit()


def test_expired_window_blocks_intake_and_remote_cleanup(monkeypatch):
    class ExpiredClock:
        @staticmethod
        def now(_zone):
            return workflow.smoke.DEADLINE

    monkeypatch.setattr(workflow, "datetime", ExpiredClock)
    with pytest.raises(RuntimeError):
        workflow.require_intake()
    with pytest.raises(RuntimeError):
        workflow.require_cleanup_window()


@pytest.mark.parametrize("fail", [False, True])
def test_cli_prompts_once_and_persists_only_safe_result(
    local, monkeypatch, tmp_path, capsys, fail
):
    import json
    import ssl
    import sys

    owner, _, _ = local
    prompts, supplied = [], []
    password = "synthetic-hidden-owner-secret"
    ca = tmp_path / "ca.crt"
    ca.touch()
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["workflow", "--ca", str(ca)])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(ssl, "create_default_context", lambda **_: None)
    monkeypatch.setattr(
        workflow.getpass, "getpass", lambda prompt: prompts.append(prompt) or password
    )
    monkeypatch.setattr(
        workflow, "connect_owner", lambda secret, _: supplied.append(secret) or owner
    )

    def smoke(*_):
        if fail:
            raise RuntimeError("private-error-with-secret-" + password)

    monkeypatch.setattr(workflow.smoke, "run_role_smoke", smoke)
    assert workflow.main() == int(fail)
    assert len(prompts) == 1 and supplied == [password]
    text = (tmp_path / "tmp/c132-single-prompt-result.json").read_text()
    result = json.loads(text)
    assert result["cleanup_verified"]
    assert result["failed_stage"] == ("SMOKE_" + workflow.ROLES[0] if fail else None)
    assert password not in text + capsys.readouterr().out
    assert (tmp_path / f"tmp/c132-session-{result['run_id']}.json").read_text() == text


@pytest.mark.parametrize(
    "message,expected",
    [
        ("password authentication failed for user secret", "authentication_rejected"),
        ("Tenant or user not found: secret", "pooler_route_rejected"),
        ("SSL error: certificate verify failed secret", "tls_certificate_rejected"),
        ("connection timeout expired secret", "connection_timeout"),
        ("unrecognized private message secret", "unclassified_OperationalError"),
    ],
)
def test_connection_diagnostics_redact_driver_values(message, expected):
    assert workflow.safe_cause(workflow.OperationalError(message)) == expected


def test_initial_connection_failure_never_provisions_and_records_cleanup_failure(
    monkeypatch,
):
    monkeypatch.setattr(workflow, "require_cleanup_window", lambda: None)
    attempts = []

    def fail():
        attempts.append(True)
        raise workflow.MaintenanceConnectionFailure("authentication_rejected")

    result = workflow.execute_workflow(fail, lambda *_: pytest.fail("no smoke"))
    assert len(attempts) == 2  # Initial connection, then cleanup-only attempt.
    assert result["failed_stage"] == "CONNECT_STAGING_MAINTENANCE"
    assert result["cause"] == result["cleanup_cause"] == "authentication_rejected"
    assert not result["provisioned"] and not result["cleanup_verified"]


@pytest.mark.parametrize(
    "scenario",
    ["success", "smoke_failure", "cleanup_failure", "wrong_run", "missing_result"],
)
def test_actual_powershell_launcher_local_orchestration(tmp_path, scenario):
    """Run the real launcher with a disposable no-network child executable script."""
    import json
    import os
    import shutil
    import subprocess
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell is required for the actual launcher check")
    fixture_tests = tmp_path / "backend/tests"
    fixture_tests.mkdir(parents=True)
    (tmp_path / "tmp").mkdir()
    source = (
        Path(workflow.__file__).with_name("start_staging_session_smoke.ps1").read_text()
    )
    # Only the copied offline fixture gets a relative deadline; real cutoff unchanged.
    future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    launcher = fixture_tests / "start_staging_session_smoke.ps1"
    launcher.write_text(source.replace("2026-10-26T13:08:53Z", future))
    result = {
        "target": workflow.STAGING_PROJECT,
        "cleanup_verified": scenario != "cleanup_failure",
        "failed_stage": None if scenario == "success" else "SMOKE_usage_executor",
        "cause": None if scenario == "success" else "unclassified_PoolTimeout",
        "cleanup_cause": (
            "authentication_rejected" if scenario == "cleanup_failure" else None
        ),
        "error": None if scenario == "success" else "PoolTimeout",
    }
    stub = (
        "import json,os,sys,time\nfrom pathlib import Path\n"
        "if os.name!='nt' and os.getpgrp()!=os.getpid():os.setsid()\n"
        "gate=Path(sys.argv[sys.argv.index('--launcher-gate')+1])\n"
        "while not gate.exists():time.sleep(.01)\n"
        "paths=os.environ['PYTHONPATH'].split(os.pathsep)\n"
        "assert len(paths)==3 and str(Path(__file__).parents[1]) in paths\n"
        "assert str(Path(__file__).parent) in paths\n"
        "assert Path(paths[-1]).name=='c113c-db-driver'\n"
        "run=sys.argv[sys.argv.index('--run-id')+1]\n"
        f"result=json.loads({json.dumps(result)!r})\n"
        f"result['run_id']='wrong' if {scenario!r}=='wrong_run' else run\n"
        f"if {scenario!r}!='missing_result':\n"
        "    (Path(__file__).parents[2]/('tmp/c132-session-'+run+'.json')).write_text(json.dumps(result))\n"
        f"sys.exit(0 if {scenario!r}=='success' else 1)\n"
    )
    (fixture_tests / "run_staging_session_workflow.py").write_text(stub)
    ca = tmp_path / "ca placeholder.crt"
    ca.touch()
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(launcher),
            "-Ca",
            str(ca),
            "-Python",
            sys.executable,
        ],
        capture_output=True,
        env={key: value for key, value in os.environ.items() if key != "TEMP"},
        check=False,
        text=True,
        timeout=30,
    )
    output = completed.stdout + completed.stderr
    assert (completed.returncode == 0) == (scenario == "success"), output
    expected = {
        "success": "COMPLETE: requested workflow passed",
        "smoke_failure": "Workflow failed at SMOKE_usage_executor",
        "cleanup_failure": "Cleanup not verified; cause=authentication_rejected",
        "wrong_run": "Result identity mismatch",
        "missing_result": "No result for this invocation",
    }[scenario]
    assert expected in output, output
    if scenario == "success":
        assert "failed_stage=NONE; cause=NONE" in output


@pytest.mark.parametrize("fail", [False, True])
def test_application_hook_uses_generated_credentials_skips_smoke_and_cleans(
    local, fail
):
    owner, events, _ = local

    def no_smoke(*_):
        pytest.fail("accepted connection smoke must not be repeated")

    def application(conn, credentials):
        assert conn is owner and len(set(credentials.values())) == 5
        events.append("application")
        if fail:
            raise RuntimeError("synthetic application interruption")
        return {"passed": ["application"]}

    application.auth_preflight = lambda: None

    result = workflow.execute_workflow(lambda: owner, no_smoke, application=application)
    assert result["smoke_passed"] == []
    assert events == ["provision", "application", "cleanup"]
    assert result["cleanup_verified"]
    assert result["failed_stage"] == ("APPLICATION_ACCEPTANCE" if fail else None)


@pytest.mark.parametrize("owned", [False, True])
def test_auth_lost_creation_ack_is_read_back_never_created_twice(owned):
    import requests
    from staging_application_acceptance import AcceptanceFailure, StagingAuth

    client = StagingAuth.__new__(StagingAuth)
    calls = []
    user = {
        "id": "10000000-0000-4000-8000-000000000001",
        "email": "c132-staging-free@acceptance.invalid",
        "email_confirmed_at": "synthetic-confirmed",
        "user_metadata": {
            "c132_acceptance_run": "owned-run" if owned else "unrelated-run"
        },
    }

    def request(method, path, **_):
        calls.append((method, path))
        if method == "POST":
            raise requests.Timeout("synthetic-secret-never-printed")
        return {"users": [user]} if "?" in path else user

    client.request = request
    if owned:
        assert client.create("free", "synthetic-password", "owned-run") == user["id"]
    else:
        with pytest.raises(
            AcceptanceFailure, match="auth_creation_uncertain_stop_no_recreate"
        ):
            client.create("free", "synthetic-password", "owned-run")
    assert sum(method == "POST" for method, _ in calls) == 1


def test_application_auth_preflight_failure_never_provisions_but_verifies_cleanup(
    local,
):
    from types import SimpleNamespace

    from staging_application_acceptance import AcceptanceFailure

    owner, events, _ = local

    def rejected():
        raise AcceptanceFailure("auth_settings_status_401")

    application = SimpleNamespace(auth_preflight=rejected)
    result = workflow.execute_workflow(lambda: owner, None, application=application)
    assert events == ["cleanup"] and result["cleanup_verified"]
    assert result["failed_stage"] == "APPLICATION_AUTH_PREFLIGHT_READ_ONLY"
    assert result["failure_check"] == "auth_settings_status_401"
    assert not result["provisioned"]


@pytest.mark.parametrize(
    "fault", [None, "modern", "project", "role", "expired", "malformed"]
)
def test_staging_auth_key_precheck_is_private_and_still_requires_server_auth(fault):
    import base64
    import json
    import time

    from staging_application_acceptance import (
        STAGING_PROJECT,
        AcceptanceFailure,
        StagingAuth,
    )

    def key(role):
        claims = {"ref": STAGING_PROJECT, "role": role, "exp": int(time.time()) + 600}
        if role == "anon":
            if fault == "project":
                claims["ref"] = "wrong-project"
            elif fault == "role":
                claims["role"] = "service_role"
            elif fault == "expired":
                claims["exp"] = 1
        payload = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        )
        return "synthetic." + payload + ".not-a-valid-signature"

    client = StagingAuth(key("anon"), key("service_role"))
    if fault == "modern":
        client.anon = "sb_publishable_SYNTHETIC_NEVER_LOG"
    elif fault == "malformed":
        client.anon = "bad.%%%.signature"
    calls = []
    client.request = lambda method, path, **kw: calls.append(path) or {"users": []}
    try:
        if fault:
            with pytest.raises(AcceptanceFailure) as caught:
                client.preflight()
            assert client.anon not in str(caught.value)
            assert calls == []
        else:
            client.preflight()
            assert calls == ["settings", "admin/users?page=1&per_page=1000"]
    finally:
        client.close()
