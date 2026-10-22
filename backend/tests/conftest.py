"""Portable offline test startup, installed before application collection."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_quality_baseline import offline


def pytest_sessionstart(session):
    session._answer_test_boundary = offline(capture_boundaries=False)
    session._answer_test_boundary.__enter__()


def pytest_sessionfinish(session, exitstatus):
    session._answer_test_boundary.__exit__(None, None, None)
