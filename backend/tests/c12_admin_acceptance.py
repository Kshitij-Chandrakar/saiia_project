"""Existing C12 admin acceptance matrix, isolated PostgreSQL and substitutes only."""

import argparse

import pytest

SCENARIOS = (
    "test_admin_denial_is_durable_and_inspection_is_local",
    "test_admin_confirmation_tamper_stale_and_duplicate",
    "test_admin_worker_failure_and_revocation_audit",
    "test_admin_notification_retry_and_unknown_refusal",
    "test_cross_account_and_forged_admin_role_denied",
    "test_unknown_notification_retry_refused_and_closed_tables",
    "test_pending_cancel_never_confirms_email",
)


class RequiredCalls:
    def __init__(self):
        self.selected = set()
        self.passed = set()

    def pytest_collection_modifyitems(self, items):
        self.selected = {item.nodeid for item in items}

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.passed:
            self.passed.add(report.nodeid)

    def exit_code(self, code):
        return int(code) if code else int(not self.selected or self.selected != self.passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    args = parser.parse_args()

    class Options:
        def pytest_addoption(self, parser):
            parser.addoption("--catalog-pg-bin", default=args.pg_bin)

    required = RequiredCalls()
    raise SystemExit(required.exit_code(
        pytest.main(
            [
                *[
                    "backend/tests/test_billing_notifications_native.py::" + name
                    for name in SCENARIOS
                ],
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ],
            plugins=[Options(), required],
        )
    ))
