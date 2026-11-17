"""Admin authority/dispatch restore fence on the existing independent checkpoint interface.

Local files rehearse the contract; deployment must supply an independent witness
and fence source writers before authorizing a new generation.
"""

import hashlib
import json
from contextlib import contextmanager
from uuid import UUID, uuid4

from app.privacy_content import ContentBlocked


def digest(state):
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class AdministrationRestore:
    def __init__(self, connect, journal, store, generation, snapshot):
        self.connect, self.journal, self.store = connect, journal, store
        self.generation, self.snapshot = str(UUID(generation)), str(UUID(snapshot))
        self.boot_verified = False

    @contextmanager
    def serialized(self):
        with self.connect() as connection:
            connection.execute("select public.administration_restore('lock','{}')")
            try:
                yield connection
            finally:
                connection.rollback()
                connection.execute(
                    "select public.administration_restore('unlock','{}')"
                )

    def capture(self, connection):
        return connection.execute(
            "select public.administration_restore('capture','{}')"
        ).fetchone()[0]

    def initialize_source(self):
        # Explicit isolated/operator setup only; normal startup never initializes evidence.
        head = self.journal.initialize()
        self.store.initialize(head)
        with self.store.locked() as local, self.serialized() as database:
            record = self.store.read(local)
            state = self.capture(database)
            self._publish(local, record, state, ready=True)
        self.boot_verified = True

    def _publish(self, local, record, state, *, ready):
        head = self.journal.append(
            {
                "kind": "administration",
                "event_id": str(uuid4()),
                "environment": self.store.environment,
                "dataset": self.store.dataset,
                "generation": self.generation,
                "snapshot": self.snapshot,
                "state": state,
            },
            record["head"],
        )
        record.update(
            head=head,
            sequence=record["sequence"] + 1,
            generation=self.generation,
            snapshot=self.snapshot,
            ready=ready,
            state_hash=digest(state),
            database_revision=int(state["revision"]),
            sealed_head=head,
            source_sealed=False,
        )
        self.store.write(local, record)

    def acknowledge_tail(self, local, record, state):
        actual = hashlib.sha256(self.journal.path.read_bytes()).hexdigest()
        if actual == record["head"]:
            self.journal.read(actual)
            return False
        lines = self.journal.path.read_bytes().splitlines(keepends=True)
        if record["head"] not in [
            hashlib.sha256(b"".join(lines[:n])).hexdigest()
            for n in range(1, len(lines) + 1)
        ]:
            raise ContentBlocked("checkpoint_journal_mismatch")
        tail = self.journal.read(actual)[-1]
        if (
            any(
                tail.get(name) != expected
                for name, expected in [
                    ("kind", "administration"),
                    ("environment", self.store.environment),
                    ("dataset", self.store.dataset),
                    ("generation", self.generation),
                    ("snapshot", self.snapshot),
                ]
            )
            or digest(tail["state"]) != digest(state)
            or int(state["revision"]) < record["database_revision"]
        ):
            raise ContentBlocked("checkpoint_coverage")
        record.update(
            head=actual,
            sequence=record["sequence"] + 1,
            ready=True,
            state_hash=digest(state),
            database_revision=int(state["revision"]),
            sealed_head=actual,
            source_sealed=False,
        )
        self.store.write(local, record)
        return True

    def start(self):
        with self.store.locked() as local, self.serialized() as database:
            record = self.store.read(local)
            if (
                not record["ready"]
                or record["generation"] != self.generation
                or record["snapshot"] != self.snapshot
            ):
                raise ContentBlocked("administration_restore_quarantined")
            state = self.capture(database)
            self.acknowledge_tail(local, record, state)
            if record.get("state_hash") != digest(state):
                raise ContentBlocked("administration_restore_quarantined")
        self.boot_verified = True

    def publish(self):
        if not self.boot_verified:
            raise ContentBlocked("administration_source_unverified")
        with self.store.locked() as local, self.serialized() as database:
            record = self.store.read(local)
            if (
                record["generation"] != self.generation
                or record["snapshot"] != self.snapshot
            ):
                raise ContentBlocked("checkpoint_superseded")
            state = self.capture(database)
            if int(state["revision"]) < record["database_revision"]:
                raise ContentBlocked("administration_restore_rollback")
            actual = hashlib.sha256(self.journal.path.read_bytes()).hexdigest()
            recovered = actual != record["head"]
            if actual != record["head"]:
                # Recover an append lost before witness acknowledgement only on the
                # already verified live source, with the witnessed prefix intact.
                lines = self.journal.path.read_bytes().splitlines(keepends=True)
                if record["head"] not in [
                    hashlib.sha256(b"".join(lines[:n])).hexdigest()
                    for n in range(1, len(lines) + 1)
                ]:
                    raise ContentBlocked("checkpoint_journal_mismatch")
                tail = self.journal.read(actual)[-1]
                if (
                    tail.get("kind") != "administration"
                    or tail.get("environment") != self.store.environment
                    or tail.get("dataset") != self.store.dataset
                    or int(tail["state"]["revision"]) > int(state["revision"])
                ):
                    raise ContentBlocked("checkpoint_coverage")
                record["head"] = actual
            if record.get("state_hash") != digest(state) or recovered:
                self._publish(local, record, state, ready=True)
            else:
                self.store.write(local, record)

    def seal_source(self):
        self.publish()
        with self.store.locked() as local, self.serialized() as database:
            record = self.store.read(local)
            if record.get("state_hash") != digest(self.capture(database)):
                raise ContentBlocked("administration_source_unsealed")
            record.update(ready=False, sealed_head=record["head"], source_sealed=True)
            self.store.write(local, record)
        self.boot_verified = False

    def reconcile(self):
        self.boot_verified = False
        with self.store.locked() as local, self.serialized() as database:
            record = self.store.read(local)
            if (
                record["generation"] != self.generation
                or record["snapshot"] != self.snapshot
                or record.get("sealed_head") != record["head"]
                or record.get("source_sealed") is not True
            ):
                raise ContentBlocked("administration_source_unsealed")
            state = self.capture(database)
            if self.acknowledge_tail(local, record, state):
                self.boot_verified = True
                return
            entries = self.journal.read(record["head"])
            event = entries[-1]
            if (
                event.get("kind") != "administration"
                or event.get("environment") != self.store.environment
                or event.get("dataset") != self.store.dataset
                or digest(event["state"]) != record["state_hash"]
            ):
                raise ContentBlocked("administration_restore_evidence")
            database.execute(
                "select public.administration_restore('replay',%s::jsonb)",
                (json.dumps(event["state"]),),
            )
            state = self.capture(database)
            database.commit()
            self._publish(local, record, state, ready=True)
        self.boot_verified = True

    def ready(self):
        if not self.boot_verified:
            return False
        try:
            with self.store.locked() as local, self.serialized() as database:
                record = self.store.read(local)
                state = self.capture(database)
                self.journal.read(record["head"])
                return (
                    record["ready"]
                    and record["generation"] == self.generation
                    and record["snapshot"] == self.snapshot
                    and int(state["revision"]) >= record["database_revision"]
                    and (
                        int(state["revision"]) > record["database_revision"]
                        or digest(state) == record["state_hash"]
                    )
                )
        except Exception:  # noqa: BLE001 -- only a safe readiness bit crosses this boundary
            return False
