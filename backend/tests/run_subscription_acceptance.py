"""Repeatable synthetic native/package acceptance, never a shared database launcher."""

import argparse
import os
import sys
import types
from pathlib import Path

import pytest

parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True)
parser.add_argument(
    "--backend",
    action="store_true",
    help="Run closed relay/privacy and usage native acceptance without opening Electron",
)
parser.add_argument(
    "--hosted",
    action="store_true",
    help="Actual packaged desktop to two isolated hosted relay workers",
)
parser.add_argument("--physical", action="store_true")
parser.add_argument("--smoke", action="store_true")
parser.add_argument("--capture-smoke", action="store_true")
parser.add_argument("--concurrency-smoke", action="store_true")
parser.add_argument("--restart-smoke", action="store_true")
parser.add_argument("--timing-smoke", action="store_true")
parser.add_argument(
    "--all",
    action="store_true",
    help="Run all native integration cases, including package acceptance",
)
args = parser.parse_args()
if args.backend and (args.physical or args.all or args.hosted):
    parser.error("--backend is separate from --physical and --all")
root = Path(__file__).resolve().parents[2]
os.chdir(root)
executable = (
    root / "tmp/c132-packaged/win-unpacked/Intervucopilot Isolated Acceptance.exe"
)
if not args.backend and not executable.is_file():
    parser.error("Run node frontend/scripts/prepare-subscription-acceptance.cjs first")
sys.path[:0] = [str(root / "backend"), str(root / "backend/tests")]
if not args.backend:
    os.environ["C132_PACKAGED_EXE"] = str(executable)
if args.hosted:
    os.environ["C132_HOSTED_ACCEPTANCE"] = "true"
if args.physical:
    marker = root / "tmp/c132-physical.stop"
    marker.unlink(missing_ok=True)
    Path(str(marker) + ".control").unlink(missing_ok=True)
    os.environ.update(
        C132_PHYSICAL_ACCEPTANCE="true",
        C132_MANUAL_STOP=str(marker),
        C132_PHYSICAL_SMOKE=str(args.smoke).lower(),
        C132_CAPTURE_SMOKE=str(args.capture_smoke).lower(),
        C132_COMPETE_SMOKE=str(args.concurrency_smoke).lower(),
        C132_RESTART_SMOKE=str(args.restart_smoke).lower(),
        C132_TIMING_SMOKE=str(args.timing_smoke).lower(),
    )
# The offline conftest clears environment at session start. Restore ONLY these
# synthetic launcher options after that boundary; never preserve provider secrets.
isolated_options = {
    key: value for key, value in os.environ.items() if key.startswith("C132_")
}
# The retained Python runtime has no working PDF binding. These tests use TXT;
# never silently emulate PDF processing.
pdf = types.ModuleType("fitz")


def no_pdf(*_, **__):
    raise AssertionError("PDF is not part of isolated packaged acceptance")


pdf.open = no_pdf
sys.modules["fitz"] = pdf


class Options:
    def pytest_addoption(self, parser):
        parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    def pytest_collection_modifyitems(self):
        os.environ.update(isolated_options)


raise SystemExit(
    pytest.main(
        [
            *(
                [
                    "backend/tests/test_hosted_subscription_native.py",
                    "backend/tests/test_usage_store_native.py",
                    "backend/tests/test_allowance_periods.py",
                ]
                if args.backend
                else ["backend/tests/test_subscription_integration_native.py"]
            ),
            "-k",
            (
                "not nonexistent"
                if args.all or args.backend
                else "account_browser_real_jwt_native_database"
            ),
            "-q",
            "-s",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ],
        plugins=[Options()],
    )
)
