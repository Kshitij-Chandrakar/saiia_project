"""Explicit disposable native C12 runner. Never accepts a DSN or credentials."""

import argparse
import sys
import types

import pytest

parser = argparse.ArgumentParser()
parser.add_argument("--pg-bin", required=True)
parser.add_argument("--regressions", action="store_true")
args = parser.parse_args()
pdf = types.ModuleType("fitz")
sys.modules["fitz"] = pdf


class Options:
    def pytest_addoption(self, parser):
        parser.addoption("--catalog-pg-bin", default=args.pg_bin)


raise SystemExit(
    pytest.main(
        [
            "backend/tests/test_billing_native.py",
            *(
                [
                    "backend/tests/test_usage_store_native.py",
                    "backend/tests/test_subscription_integration_native.py",
                    "backend/tests/test_hosted_subscription_native.py",
                    "backend/tests/test_catalog_contract.py",
                    "backend/tests/test_catalog_v3.py",
                    "backend/tests/test_allowance_periods.py",
                ]
                if args.regressions
                else []
            ),
            "-q",
            "--tb=short",
        ],
        plugins=[Options()],
    )
)
