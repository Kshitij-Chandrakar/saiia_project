"""Explicit isolated runner; no DSN, credentials or external provider transport."""

import argparse

import pytest

parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True)
args = parser.parse_args()


class Options:
    def pytest_addoption(self, parser):
        parser.addoption("--catalog-pg-bin", default=args.pg_bin)


raise SystemExit(
    pytest.main(
        [
            "backend/tests/test_billing_notifications_native.py",
            "backend/tests/test_billing_native.py",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ],
        plugins=[Options()],
    )
)
