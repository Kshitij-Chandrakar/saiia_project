"""Durable redacted limits for the single explicitly authorized C12 session."""

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIMITS = {
    "plans": 4,
    "subscriptions": 8,
    "cancellations": 8,
    "gets": 500,
    "tunnels": 1,
    "webhooks": 1,
    "downloads": 1,
}
IST = timezone(timedelta(hours=5, minutes=30))


class SessionBudget:
    def __init__(self, directory: Path, clock=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "session.json"
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.Lock()
        with self.locked():
            if not self.path.exists():
                self.save(
                    {
                        "scope": "C12-RZP-TEST-01",
                        "status": "preflight",
                        "start_utc": None,
                        "deadline_utc": None,
                        "counts": dict.fromkeys(LIMITS, 0),
                        "resources": {},
                        "events": [],
                    }
                )

    @contextmanager
    def locked(self):
        with self.lock, (self.directory / "budget.lock").open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state):
        temporary = self.path.with_suffix(".new")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def reserve(self, category: str, *, cleanup=False):
        """Commit an attempted operation BEFORE dispatch; never refund its count."""
        if category not in LIMITS:
            raise RuntimeError("unapproved operation")
        with self.locked():
            state = self.load()
            now = self.clock()
            if state["status"] in {"finished", "blocked"}:
                raise RuntimeError("session intake closed")
            if not state["start_utc"]:
                if cleanup:
                    raise RuntimeError("no external session to clean up")
                deadline = now + timedelta(minutes=60)
                state.update(
                    start_utc=now.isoformat(),
                    deadline_utc=deadline.isoformat(),
                    start_ist=now.astimezone(IST).isoformat(),
                    deadline_ist=deadline.astimezone(IST).isoformat(),
                    status="running",
                )
            if cleanup and category not in {"gets", "cancellations"}:
                raise RuntimeError("unapproved cleanup operation")
            if not cleanup and (
                now >= datetime.fromisoformat(state["deadline_utc"])
                or state["status"] == "cleanup"
            ):
                raise RuntimeError("session deadline/intake closed")
            if state["counts"][category] >= LIMITS[category]:
                raise RuntimeError("session operation limit reached")
            state["counts"][category] += 1
            state["events"].append(
                {
                    "at_utc": now.isoformat(),
                    "stage": "attempt",
                    "category": category,
                    "number": state["counts"][category],
                }
            )
            self.save(state)

    def event(self, stage: str, **redacted):
        # Callers supply only enums, integer HTTP status, IDs and booleans.
        allowed = {
            "http_status",
            "provider_code",
            "exception_type",
            "resource_id",
            "category",
            "passed",
        }
        if set(redacted) - allowed:
            raise RuntimeError("unapproved evidence fields")
        with self.locked():
            state = self.load()
            state["events"].append(
                {"at_utc": self.clock().isoformat(), "stage": stage, **redacted}
            )
            self.save(state)

    def resource(self, category, resource_id):
        with self.locked():
            state = self.load()
            state["resources"].setdefault(category, [])
            if resource_id not in state["resources"][category]:
                state["resources"][category].append(resource_id)
            self.save(state)

    def close_intake(self, status="cleanup"):
        if status not in {"cleanup", "finished", "blocked"}:
            raise ValueError("invalid session status")
        with self.locked():
            state = self.load()
            state["status"] = status
            self.save(state)

    def resume_after_authentication_rejection(self):
        """One corrected-pair retry in the SAME window after a proven non-mutation."""
        with self.locked():
            state = self.load()
            if (
                state["status"] != "finished"
                or state.get("authentication_retry_used")
                or state["counts"]["gets"] != 1
                or any(
                    value for name, value in state["counts"].items() if name != "gets"
                )
                or state["resources"]
                or not any(
                    event.get("stage") == "provider_http_error"
                    and event.get("http_status") == 401
                    for event in state["events"]
                )
                or self.clock() >= datetime.fromisoformat(state["deadline_utc"])
            ):
                raise RuntimeError("Session cannot safely resume authentication")
            state["authentication_retry_used"] = True
            state["status"] = "running"
            state["events"].append(
                {
                    "at_utc": self.clock().isoformat(),
                    "stage": "corrected_authentication_retry_same_window",
                }
            )
            self.save(state)
