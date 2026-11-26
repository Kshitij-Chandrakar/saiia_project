"""Standalone local infrastructure; never disables pytest's offline guard."""

import inspect
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


@contextmanager
def local_runtime(pg_bin, *, billing_email=False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from answer_quality_baseline import offline

    fixtures_stack = ExitStack()
    monkeypatch = pytest.MonkeyPatch()
    try:
        with offline(capture_boundaries=False):
            import test_billing_native as fixtures

            functions = {
                name: getattr(fixtures, name)
                for name in (
                    "database",
                    "f1_install",
                    "f2_install",
                    "install",
                    "case",
                    "upgraded",
                    "pricing",
                    "usage",
                    "integration",
                    "billing",
                )
            }
            if billing_email:
                import test_billing_notifications_native as mail_fixtures

                functions["mail"] = mail_fixtures.mail
            values = {
                "monkeypatch": monkeypatch,
                "request": SimpleNamespace(
                    config=SimpleNamespace(getoption=lambda *a, **k: pg_bin)
                ),
            }

            def resolve(name):
                if name not in values:
                    function = functions[name].__wrapped__
                    arguments = {
                        parameter: resolve(parameter)
                        for parameter in inspect.signature(function).parameters
                    }
                    values[name] = (
                        fixtures_stack.enter_context(
                            contextmanager(function)(**arguments)
                        )
                        if inspect.isgeneratorfunction(function)
                        else function(**arguments)
                    )
                return values[name]

            runtime = resolve("mail" if billing_email else "billing")
        yield runtime
    finally:
        with offline(capture_boundaries=False):
            fixtures_stack.close()
            monkeypatch.undo()
