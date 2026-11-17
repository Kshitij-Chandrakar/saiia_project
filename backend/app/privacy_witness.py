"""Authenticated checkpoint authority interface, independent of restored data.

The local HTTP authority is rehearsal infrastructure, not production durability.
Its database and antirollback anchor must both remain outside product snapshots.
Production placement/keys/restore exclusion still require configured acceptance.
"""

import hmac
import json
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import UUID

import requests

from app.privacy_checkpoint import LocalCheckpointStore
from app.privacy_content import ContentBlocked

ADMIN_FIELDS = {
    "journal_id": None,
    "state_hash": None,
    "database_revision": 0,
    "source_sealed": False,
}


class HTTPCheckpointStore:
    def __init__(
        self,
        url,
        token,
        verification_key,
        environment,
        dataset,
        *,
        local_rehearsal=False,
    ):
        parsed = urlsplit(url)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or not parsed.hostname
            or (
                parsed.scheme != "https"
                and not (
                    local_rehearsal
                    and parsed.scheme == "http"
                    and parsed.hostname in {"127.0.0.1", "localhost"}
                )
            )
        ):
            raise ContentBlocked("witness_configuration")
        self.url, self.token, self.key, self.environment, self.dataset = (
            url.rstrip("/"),
            token,
            verification_key,
            str(environment),
            str(dataset),
        )
        self.http = requests.Session()
        self.http.trust_env = False
        self.mutex = threading.RLock()

    signature = LocalCheckpointStore.signature
    authorize_restore = LocalCheckpointStore.authorize_restore

    def request(self, method, document=None):
        try:
            with self.http.request(
                method,
                self.url + "/checkpoint",
                json=document,
                headers={"Authorization": "Bearer " + self.token},
                timeout=(3, 10),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code != 200:
                    raise ContentBlocked("witness_unavailable")
                raw = bytearray()
                for chunk in response.iter_content(4096):
                    if len(raw) + len(chunk) > 65536:
                        raise ContentBlocked("witness_invalid")
                    raw.extend(chunk)
                value = json.loads(raw)
            record = value["record"]
            if (
                record["version"] != 1
                or record["environment"] != self.environment
                or record["dataset"] != self.dataset
                or not hmac.compare_digest(value["mac"], self.signature(record))
            ):
                raise ContentBlocked("witness_invalid")
            return record
        except ContentBlocked:
            raise
        except Exception:  # noqa: BLE001 -- no credentials/transport details
            raise ContentBlocked("witness_unavailable") from None

    @contextmanager
    def locked(self):
        with self.mutex:
            # Always fetch the independent authority; no restored local cache is
            # accepted as a current head. CAS handles other coordinator processes.
            yield {"record": self.request("GET")}

    def read(self, slot):
        return dict(slot["record"])

    def write(self, slot, record):
        value = self.request(
            "POST", {"expected": self.signature(slot["record"]), "record": record}
        )
        slot["record"] = value

    def upgrade_snapshot_schema(self):
        """Explicit operator-only compatibility step for an older authority."""
        with self.locked() as slot:
            current = self.read(slot)
            missing = ADMIN_FIELDS.keys() - current.keys()
            if missing:
                updated = dict(
                    current, **{name: ADMIN_FIELDS[name] for name in missing}
                )
                updated["sequence"] += 1
                self.write(slot, updated)


def local_authority(
    store,
    reader_token,
    coordinator_token,
    host="127.0.0.1",
    port=0,
    *,
    operator_token=None,
):
    """Owned loopback service. No initialization/mutation/public operator route."""
    if (
        host != "127.0.0.1"
        or len(reader_token) < 32
        or len(coordinator_token) < 32
        or reader_token == coordinator_token
        or (
            operator_token is not None
            and (
                len(operator_token) < 32
                or operator_token in {reader_token, coordinator_token}
            )
        )
    ):
        raise ContentBlocked("witness_configuration")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def handle_checkpoint(self):
            try:
                token = self.headers.get("Authorization", "")
                operator = operator_token is not None and hmac.compare_digest(
                    token, "Bearer " + operator_token
                )
                allowed = (
                    operator
                    or hmac.compare_digest(token, "Bearer " + coordinator_token)
                    or (
                        self.command == "GET"
                        and hmac.compare_digest(token, "Bearer " + reader_token)
                    )
                )
                if self.path != "/checkpoint" or not allowed:
                    raise ContentBlocked("witness_denied")
                with store.locked() as c:
                    current = store.read(c)
                    if self.command == "POST":
                        size = int(self.headers.get("Content-Length", "0"))
                        if not 1 <= size <= 65536:
                            raise ContentBlocked("witness_invalid")
                        document = json.loads(self.rfile.read(size))
                        record = document["record"]
                        missing = set(record) - set(current)
                        upgrade = (
                            operator
                            and missing
                            and missing <= ADMIN_FIELDS.keys()
                            and all(
                                record[name] == ADMIN_FIELDS[name] for name in missing
                            )
                            and all(
                                record[name] == value
                                for name, value in current.items()
                                if name != "sequence"
                            )
                        )
                        if (
                            set(document) != {"expected", "record"}
                            or (set(record) != set(current) and not upgrade)
                            or type(record["ready"]) is not bool
                            or not re.fullmatch(r"[0-9a-f]{64}", record["head"])
                            or (
                                record["sealed_head"] is not None
                                and not re.fullmatch(
                                    r"[0-9a-f]{64}", record["sealed_head"]
                                )
                            )
                        ):
                            raise ContentBlocked("witness_invalid")
                        for field in ("generation", "snapshot", "journal_id"):
                            if (
                                record.get(field) is not None
                                and str(UUID(record[field])) != record[field]
                            ):
                                raise ContentBlocked("witness_invalid")
                        if not operator and (
                            record["generation"],
                            record["snapshot"],
                        ) != (current["generation"], current["snapshot"]):
                            raise ContentBlocked("witness_operator_required")
                        if record["ready"] and (
                            record["sealed_head"] != record["head"]
                            or record["generation"] is None
                            or record["snapshot"] is None
                        ):
                            raise ContentBlocked("witness_invalid")

                        if (
                            not hmac.compare_digest(
                                document["expected"], store.signature(current)
                            )
                            or record["version"] != 1
                            or record["environment"] != current["environment"]
                            or record["dataset"] != current["dataset"]
                            or type(record["sequence"]) is not int
                            or record["sequence"] < current["sequence"]
                            or record["sequence"] > current["sequence"] + 1
                            or (
                                record["head"] != current["head"]
                                and record["sequence"] != current["sequence"] + 1
                            )
                        ):
                            raise ContentBlocked("witness_conflict")
                        store.write(c, record)
                        current = record
                    data = json.dumps(
                        {"record": current, "mac": store.signature(current)}
                    ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:  # noqa: BLE001 -- safe failure only, no input echoed
                self.send_response(409)
                self.send_header("Content-Length", "0")
                self.end_headers()

        do_GET = handle_checkpoint
        do_POST = handle_checkpoint

    return ThreadingHTTPServer((host, port), Handler)
