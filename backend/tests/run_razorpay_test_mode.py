"""Explicit standalone acceptance entry; never imports pytest conftest."""

import argparse
import json
import os
import sys
import types
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True)
parser.add_argument("--preflight-only", action="store_true")
parser.add_argument("--cleanup-only", action="store_true")
parser.add_argument("--session-dir", type=Path, default=Path("tmp/c12-rzp-test-01"))
args = parser.parse_args()
os.environ["BILLING_ENABLED"] = "false"
names = (
    "RAZORPAY_TEST_KEY_ID",
    "RAZORPAY_TEST_KEY_SECRET",
    "RAZORPAY_TEST_ACCOUNT_ID",
    "RAZORPAY_TEST_WEBHOOK_SECRET",
)
credentials = {name: os.environ.pop(name, "") for name in names}
sys.modules["fitz"] = types.ModuleType("fitz")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from razorpay_local_runtime import local_runtime

session_dir = args.session_dir.resolve()
assert session_dir.parent == (
    Path.cwd() / "tmp"
).resolve() and session_dir.name.startswith("c12-rzp-test-")
manifest = session_dir / "preflight.json"
try:
    if args.cleanup_only:
        from razorpay_test_mode_execution import cleanup_only

        cleanup_only(credentials, session_dir, pg_bin=args.pg_bin)
    else:
        with local_runtime(args.pg_bin) as runtime:
            from razorpay_test_mode_runtime import preflight

            preflight(runtime, session_dir)
            if not args.preflight_only:
                from razorpay_test_mode_execution import execute

                execute(runtime, credentials, session_dir)
finally:
    credentials.clear()
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["database_disposed"] = not Path(data["database_directory"]).exists()
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
