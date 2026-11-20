"""Admin authority/dispatch restore fence on the existing independent checkpoint interface.

Local files rehearse the contract; deployment must supply an independent witness
and fence source writers before authorizing a new generation.
"""

import hashlib
import json
from contextlib import contextmanager
from uuid import UUID, uuid4

from app.privacy_content import ContentBlocked
from app.privacy_restore import RestoreJournal


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
        with self.serialized() as database, self.store.locked() as local:
            record = self.store.read(local)
            state = self.capture(database)
            self._publish(local, record, state, ready=True)
        self.prune_acknowledged()
        self.boot_verified = True

    def prune_acknowledged(self):
        # Only a witnessed predecessor may be removed. Never glob away another
        # publisher's unacknowledged candidate before its CAS completes.
        with self.store.locked() as local:
            current = self.store.read(local)
            if not current.get("journal_id"):
                return
            events = self._journal(current).read(current["head"])
            previous = events[1].get("previous_journal_id")
            expected = events[1]["previous_head"]
            while previous is not None:
                predecessor = dict(current, journal_id=str(UUID(previous)))
                path = self._journal(predecessor).path
                if path.is_symlink() or not path.is_file():
                    return
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ContentBlocked("checkpoint_coverage")
                ancestor = self._journal(predecessor).read(expected)
                previous = ancestor[1].get("previous_journal_id")
                expected = ancestor[1]["previous_head"]
                path.unlink()

    def _journal(self, record):
        if not record.get("journal_id"):
            return self.journal
        identity = str(UUID(record["journal_id"]))
        journal = RestoreJournal(
            self.journal.path.with_name(
                self.journal.path.name + "." + identity + ".snapshot"
            ),
            self.journal.keys,
            self.journal.current,
        )
        journal.MAX_BYTES = 128 * 1024 * 1024
        return journal

    def _state(self, record):
        events = self._journal(record).read(record["head"])
        if not record.get("journal_id"):
            return events[-1]["state"]
        first, last = events[1], events[-1]
        if (
            first.get("kind") != "administration.snapshot.v1"
            or first.get("environment") != self.store.environment
            or first.get("dataset") != self.store.dataset
            or last.get("kind") != "administration.complete.v1"
            or last.get("parts") != len(events) - 3
        ):
            raise ContentBlocked("checkpoint_coverage")
        state = dict(first["scalars"])
        state.update({name: [] for name in first["lists"]})
        for index, event in enumerate(events[2:-1]):
            if (
                event.get("part") != index
                or event.get("field") not in first["lists"]
                or not isinstance(event.get("rows"), list)
            ):
                raise ContentBlocked("checkpoint_coverage")
            state[event["field"]].extend(event["rows"])
        if digest(state) != last.get("state_hash") or digest(state) != record.get(
            "state_hash"
        ):
            raise ContentBlocked("checkpoint_coverage")
        return state

    def _pending(self, record):
        for path in self.journal.path.parent.glob(
            self.journal.path.name + ".*.snapshot"
        ):
            identity = path.name[len(self.journal.path.name) + 1 : -len(".snapshot")]
            try:
                identity = str(UUID(identity))
            except ValueError:
                continue
            if identity == record.get("journal_id") or path.is_symlink():
                continue
            head = hashlib.sha256(path.read_bytes()).hexdigest()
            candidate = dict(record, journal_id=identity, head=head)
            try:
                events = self._journal(candidate).read(head)
                first, last = events[1], events[-1]
                candidate["state_hash"] = last["state_hash"]
                state = self._state(candidate)
            except (ContentBlocked, IndexError, KeyError):
                continue
            if (
                first.get("previous_head") == record["head"]
                and first.get("generation") == self.generation
                and first.get("snapshot") == self.snapshot
            ):
                yield candidate, state

    def _publish(self, local, record, state, *, ready):
        # Each authenticated checkpoint selects one complete immutable snapshot.
        # Incomplete files cannot advance the independent witness.
        self._journal(record).read(record["head"])
        if any(
            int(pending["revision"]) > int(state["revision"])
            for _, pending in self._pending(record)
        ):
            raise ContentBlocked("administration_restore_rollback")
        updated = dict(record, journal_id=str(uuid4()))
        journal = self._journal(updated)
        head = journal.initialize()
        fields = [name for name, value in state.items() if isinstance(value, list)]
        head = journal.append(
            {
                "kind": "administration.snapshot.v1",
                "event_id": str(uuid4()),
                "environment": self.store.environment,
                "dataset": self.store.dataset,
                "generation": self.generation,
                "snapshot": self.snapshot,
                "previous_head": record["head"],
                "previous_journal_id": record.get("journal_id"),
                "scalars": {
                    name: value for name, value in state.items() if name not in fields
                },
                "lists": fields,
            },
            head,
        )
        part = 0
        for field in fields:
            rows, size = [], 0
            for row in state[field]:
                encoded = len(json.dumps(row, sort_keys=True).encode())
                if encoded > 512 * 1024:
                    raise ContentBlocked("restore_evidence_size")
                if rows and size + encoded > 512 * 1024:
                    head = journal.append(
                        {
                            "event_id": str(uuid4()),
                            "part": part,
                            "field": field,
                            "rows": rows,
                        },
                        head,
                    )
                    part += 1
                    rows, size = [], 0
                rows.append(row)
                size += encoded
            if rows:
                head = journal.append(
                    {
                        "event_id": str(uuid4()),
                        "part": part,
                        "field": field,
                        "rows": rows,
                    },
                    head,
                )
                part += 1
        head = journal.append(
            {
                "event_id": str(uuid4()),
                "kind": "administration.complete.v1",
                "parts": part,
                "state_hash": digest(state),
            },
            head,
        )
        updated.update(
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
        self._state(updated)
        self.store.write(local, updated)
        record.update(updated)

    def acknowledge_tail(self, local, record, state):
        if record.get("journal_id"):
            self._state(record)
            pending = list(self._pending(record))
            if not pending:
                return False
            for candidate, published in pending:
                if (
                    digest(published) == digest(state)
                    and int(state["revision"]) >= record["database_revision"]
                ):
                    candidate.update(
                        sequence=record["sequence"] + 1,
                        ready=True,
                        database_revision=int(state["revision"]),
                        sealed_head=candidate["head"],
                        source_sealed=False,
                    )
                    self.store.write(local, candidate)
                    record.update(candidate)
                    return True
            raise ContentBlocked("checkpoint_coverage")
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
        with self.serialized() as database, self.store.locked() as local:
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
        with self.serialized() as database, self.store.locked() as local:
            record = self.store.read(local)
            if (
                record["generation"] != self.generation
                or record["snapshot"] != self.snapshot
                or record["ready"] is not True
            ):
                raise ContentBlocked("checkpoint_superseded")
            state = self.capture(database)
            if int(state["revision"]) < record["database_revision"]:
                raise ContentBlocked("administration_restore_rollback")
            if int(state["revision"]) == record["database_revision"] and record.get(
                "state_hash"
            ) not in (None, digest(state)):
                raise ContentBlocked("administration_restore_rollback")
            if record.get("journal_id"):
                self.acknowledge_tail(local, record, state)
            actual = (
                record["head"]
                if record.get("journal_id")
                else hashlib.sha256(self.journal.path.read_bytes()).hexdigest()
            )
            if record.get("journal_id"):
                self._state(record)
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
        self.prune_acknowledged()

    def seal_source(self):
        self.publish()
        with self.serialized() as database, self.store.locked() as local:
            record = self.store.read(local)
            if record.get("state_hash") != digest(self.capture(database)):
                raise ContentBlocked("administration_source_unsealed")
            record.update(ready=False, sealed_head=record["head"], source_sealed=True)
            self.store.write(local, record)
        self.boot_verified = False

    def reconcile(self):
        self.boot_verified = False
        with self.serialized() as database, self.store.locked() as local:
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
            witnessed = self._state(record)
            if digest(witnessed) != record["state_hash"]:
                raise ContentBlocked("administration_restore_evidence")
            database.execute(
                "select public.administration_restore('replay',%s::jsonb)",
                (json.dumps(witnessed),),
            )
            state = self.capture(database)
            database.commit()
            self._publish(local, record, state, ready=True)
        self.prune_acknowledged()
        self.boot_verified = True

    def ready(self):
        if not self.boot_verified:
            return False
        try:
            with self.serialized() as database, self.store.locked() as local:
                record = self.store.read(local)
                state = self.capture(database)
                self._state(record)
                return (
                    record["ready"]
                    and not any(self._pending(record))
                    and record["generation"] == self.generation
                    and record["snapshot"] == self.snapshot
                    and int(state["revision"]) >= record["database_revision"]
                    and (
                        int(state["revision"]) > record["database_revision"]
                        or digest(state) == record["state_hash"]
                    )
                )
        except (
            Exception
        ):  # noqa: BLE001 -- only a safe readiness bit crosses this boundary
            return False
