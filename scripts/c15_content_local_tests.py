"""Explicit disposable test runner. No DSN, dotenv or provider configuration."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pytest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument(
        "--suite", default="backend/tests/test_privacy_content_native.py"
    )
    parser.add_argument("--evidence-dir", default="docs/evidence/c15-export-cleanup")
    parser.add_argument("--prepare-fields", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root / args.suite).resolve().is_relative_to(root / "backend/tests"):
        parser.error("suite must remain within backend/tests")
    if not (root / args.evidence_dir).resolve().is_relative_to(root / "docs/evidence"):
        parser.error("evidence must remain within docs/evidence")
    sys.path[:0] = [str(root / "backend"), str(root / "backend/tests")]
    results = []

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)
            parser.addoption(
                "--c15-content-capture", default=args.capture, action="store_true"
            )
            parser.addoption("--c15-evidence-dir", default=args.evidence_dir)
            parser.addoption(
                "--c15-prepare-fields", default=args.prepare_fields, action="store_true"
            )

        def pytest_runtest_logreport(self, report):
            if report.when == "call":
                results.append(
                    {
                        "test": report.nodeid,
                        "outcome": report.outcome,
                        "seconds": round(report.duration, 3),
                    }
                )

        def pytest_sessionfinish(self, session, exitstatus):
            if args.capture:
                path = root / args.evidence_dir / "tests.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "exit_status": int(exitstatus),
                            "python": sys.version,
                            "results": results,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

    # Separate concurrent runs from pytest's global numbered-temp pruning.
    # This newly owned root contains no historical evidence or device data.
    with tempfile.TemporaryDirectory(prefix="c15-native-") as owned:
        assert Path(owned).resolve().parent == Path(tempfile.gettempdir()).resolve()
        return pytest.main(
            [
                str(root / args.suite),
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                owned,
            ],
            plugins=[Options()],
        )


if __name__ == "__main__":
    raise SystemExit(main())
