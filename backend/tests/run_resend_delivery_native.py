"""Run the callback and existing email/admin regressions on disposable native PostgreSQL."""

import argparse

import pytest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--select", default="")
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    raise SystemExit(
        pytest.main(
            [
                "backend/tests/test_resend_delivery_native.py",
                "backend/tests/test_billing_notifications_native.py",
                "-k",
                args.select,
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            plugins=[Options()],
        )
    )
