"""Local-only setup boundary checks; no provider, tunnel or database calls."""

import pytest
from fastapi.testclient import TestClient

from scripts import c12_webhook_gateway as gateway


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/docs",
        "/openapi.json",
        "/api/account/subscription",
        gateway.PATH + "/",
        gateway.PATH + "?x=1",
    ],
)
def test_gateway_rejects_other_paths(path):
    with TestClient(gateway.app) as client:
        assert client.post(path, follow_redirects=False).status_code == 404


def test_gateway_preserves_raw_bytes_and_never_acknowledges_failure(monkeypatch):
    raw = b'{ "signed": true }\n'
    calls = []

    def forward(body, signature):
        calls.append((body, signature))
        return 503

    monkeypatch.setattr(gateway, "forward", forward)
    with TestClient(gateway.app) as client:
        assert client.get(gateway.PATH).status_code == 405
        assert client.post(gateway.PATH, content=raw).status_code == 400
        response = client.post(
            gateway.PATH, content=raw, headers={"X-Razorpay-Signature": "a" * 64}
        )
        assert response.status_code == 503 and "received" not in response.json()
        assert calls == [(raw, "a" * 64)]
        assert (
            client.post(
                gateway.PATH,
                content=b"x" * (gateway.LIMIT + 1),
                headers={"X-Razorpay-Signature": "a" * 64},
            ).status_code
            == 413
        )
        assert len(calls) == 1


def test_forward_fixed_loopback_destination_and_response(monkeypatch):
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def request(self, *args, **kwargs):
            calls.append((args, kwargs))

        def getresponse(self):
            return type("Response", (), {"status": 200})()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(gateway.http.client, "HTTPConnection", Connection)
    assert gateway.forward(b"raw", "b" * 64) == 200
    assert calls[0] == (("127.0.0.1", 8000), {"timeout": 30})
    assert calls[1][0] == ("POST", gateway.PATH)
    assert calls[1][1]["body"] == b"raw" and calls[-1] == "closed"


@pytest.mark.parametrize("existing", [False, True])
def test_callback_launcher_restores_python_environment_after_child_failure(tmp_path, existing):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell required for launcher environment regression")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "c12_resend_callback_acceptance.ps1"
    source = Path(__file__).resolve().parents[2] / "scripts" / launcher.name
    tests = tmp_path / "backend/tests"
    tests.mkdir(parents=True)
    marker = tmp_path / "child-ran"
    (tests / "c12_resend_callback_acceptance.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(1)\n")
    pg = tmp_path / "pgsql"
    pg.mkdir()
    (pg / "pg_ctl.exe").touch()
    tools = tmp_path / "C12Tools"
    tools.mkdir()
    (tools / "cloudflared.exe").touch()
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    # Only the copied fixture's external tool path changes; the wrapper and
    # environment-restoration logic run unchanged, with no actual tunnel tool.
    launcher.write_text(source.read_text().replace("(Join-Path $env:LOCALAPPDATA 'C12Tools\\cloudflared.exe')", quote(tools / "cloudflared.exe")))
    before = "'original-python-path'" if existing else "$null"
    dotenv = "'original-dotenv'" if existing else "$null"
    driver = tmp_path / "driver.ps1"
    driver.write_text(
        f"$env:PYTHONPATH={before}\n$env:PYTHON_DOTENV_DISABLED={dotenv}\n"
        f"try {{ & {quote(launcher)} -Python {quote(sys.executable)} -PgBin {quote(pg)} -DriverDirectory {quote(tmp_path)} -Recipient 'approved@example.org' }} catch {{ Write-Output ('FIXTURE_CAUGHT: ' + $_.Exception.Message + '; exit=' + $LASTEXITCODE) }}\n"
        f"if ($env:PYTHONPATH -cne {before} -or $env:PYTHON_DOTENV_DISABLED -cne {dotenv}) {{ throw 'Python environment leaked' }}\n"
        "Write-Output 'ENVIRONMENT_RESTORED'\n"
    )
    environment = dict(os.environ)
    if os.name == "nt":
        # The offline guard omits mixed-case Windows environment keys. Supply
        # only OS bootstrap paths, never the original operational environment.
        import ctypes
        windows = ctypes.create_unicode_buffer(32768)
        assert ctypes.windll.kernel32.GetWindowsDirectoryW(windows, len(windows))
        environment.update(SystemRoot=windows.value, SystemDrive=Path(windows.value).drive, PATHEXT=".EXE")
    result = subprocess.run([powershell, "-NoProfile", "-File", str(driver)], capture_output=True, text=True,
                            env=environment, timeout=25)
    assert marker.exists() and result.returncode == 0 and "ENVIRONMENT_RESTORED" in result.stdout, result.stdout + result.stderr
