"""Local durable restore coordinator; no provider or deployment composition.

The witness/key/boot identity MUST be outside the restored dataset/checkpoint.
SQLite attached rollback-journal transactions provide the local atomic CAS.
Production needs an independently durable equivalent, not a copied local file.
"""

import hashlib
import hmac
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import UUID

from app.privacy_content import ContentBlocked
from app.privacy_restore import RestoreGate


class LocalCheckpointStore:
    def __init__(self, path, witness, key, environment, dataset):
        self.path, self.witness = Path(path), Path(witness)
        self.environment, self.dataset = str(UUID(environment)), str(UUID(dataset))
        if len(key) < 32 or self.path.resolve() == self.witness.resolve():
            raise ContentBlocked("checkpoint_configuration")
        self.key = key

    def signature(self, record):
        return hmac.new(
            self.key,
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()

    @contextmanager
    def locked(self, initialize=False):
        if not initialize and (not self.path.is_file() or not self.witness.is_file()):
            raise ContentBlocked("checkpoint_unavailable")
        if self.path.is_symlink() or self.witness.is_symlink():
            raise ContentBlocked("checkpoint_unavailable")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as c, c:
                c.execute("pragma journal_mode=delete")
                c.execute("pragma synchronous=full")
                c.execute("attach database ? as witness", (str(self.witness),))
                c.execute("pragma witness.journal_mode=delete")
                c.execute("pragma witness.synchronous=full")
                c.execute("begin immediate")
                yield c
        except ContentBlocked:
            raise
        except Exception:  # noqa: BLE001 -- never leak filesystem/SQLite details
            raise ContentBlocked("checkpoint_unavailable") from None

    def initialize(self, head):
        # Explicit one-time operator setup; never initialize on read or restart.
        if self.path.exists() or self.witness.exists():
            raise ContentBlocked("checkpoint_exists")
        with self.locked(initialize=True) as c:
            for schema in ("main", "witness"):
                c.execute(
                    f"create table {schema}.head(singleton integer primary key check(singleton=1),record text not null,mac text not null)"
                )
            self.write(
                c,
                {
                    "version": 1,
                    "environment": self.environment,
                    "dataset": self.dataset,
                    "sequence": 0,
                    "head": head,
                    "generation": None,
                    "snapshot": None,
                    "ready": False,
                    "sealed_head": None,
                },
            )

    def read(self, c):
        a = c.execute("select record,mac from main.head where singleton=1").fetchone()
        b = c.execute(
            "select record,mac from witness.head where singleton=1"
        ).fetchone()
        if not a or a != b:
            raise ContentBlocked("checkpoint_rollback")
        try:
            record = json.loads(a[0])
            if (
                not hmac.compare_digest(a[1], self.signature(record))
                or record["version"] != 1
                or record["environment"] != self.environment
                or record["dataset"] != self.dataset
            ):
                raise ValueError()
        except Exception:  # noqa: BLE001 -- authenticated record parsing fails closed
            raise ContentBlocked("checkpoint_authentication") from None
        return record

    def write(self, c, record):
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
        for schema in ("main", "witness"):
            c.execute(
                f"insert into {schema}.head values(1,?,?) on conflict(singleton) do update set record=excluded.record,mac=excluded.mac",
                (payload, self.signature(record)),
            )

    def authorize_restore(self, sequence, generation, snapshot):
        with self.locked() as c:
            record = self.read(c)
            if record["sequence"] != sequence or record["generation"] == str(
                UUID(generation)
            ):
                raise ContentBlocked("checkpoint_superseded")
            record.update(
                sequence=sequence + 1,
                generation=str(UUID(generation)),
                snapshot=str(UUID(snapshot)),
                ready=False,
            )
            self.write(c, record)


class RestoreCoordinator:
    def __init__(self, engine, journal, store, generation, snapshot):
        self.engine, self.journal, self.store = engine, journal, store
        self.generation, self.snapshot = str(UUID(generation)), str(UUID(snapshot))
        self.boot_verified = False

    def publish(self):
        # ponytail: one coordinator lock per dataset; shard only if measured
        # throughput requires it. Freshness is never cached across requests.
        with self.store.locked() as c:
            record = self.store.read(c)
            # Recover a journal append whose DB/checkpoint acknowledgement was
            # interrupted only if its prefix matches the trusted witness. Every
            # tail decision is republished against the authoritative live outbox.
            raw = self.journal.path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != record["head"]:
                lines = raw.splitlines(keepends=True)
                prefixes = [
                    hashlib.sha256(b"".join(lines[:n])).hexdigest()
                    for n in range(1, len(lines) + 1)
                ]
                if record["head"] not in prefixes:
                    raise ContentBlocked("checkpoint_journal_mismatch")
                events = self.journal.read(actual)
                tail = events[prefixes.index(record["head"]) + 1 :]
                with self.engine.transaction() as db:
                    for event in tail:
                        db.execute(
                            "select 1 from privacy_restore_outbox where request_id=%s",
                            (event["event_id"],),
                        )
                        if not db.fetchone():
                            raise ContentBlocked("checkpoint_coverage")
            else:
                self.journal.read(actual)
            with self.engine.transaction() as db:
                db.execute(
                    "select request_id,account_id from privacy_restore_outbox order by created_at,request_id"
                )
                pending = db.fetchall()
                self._outbox_complete(db)
            gate = RestoreGate(self.engine)
            for request, account in pending:
                with self.engine.transaction() as db:
                    db.execute(
                        "select kind from privacy_content_jobs where id=%s and kind in ('session','history')",
                        (request,),
                    )
                    scoped = bool(db.fetchone())
                actual = gate.publish(
                    account, self.journal, actual, job_id=request if scoped else None
                )
            with self.engine.transaction() as db:
                # Capture only the exact outbox set republished above. A new
                # decision remains uncovered and immediately denies readiness.
                db.execute(
                    "update privacy_restore_outbox set checkpoint=%s where request_id=any(%s::uuid[])",
                    (actual, [str(r[0]) for r in pending]),
                )
            if actual != record["head"]:
                record.update(
                    sequence=record["sequence"] + 1,
                    head=actual,
                    ready=False,
                    sealed_head=None,
                )
                self.store.write(c, record)
            return record["sequence"]

    def seal_source(self):
        """Operator cutover on the LIVE source, never the restored copy.

        Deployment must fence every old-generation ingress before this call and
        retain the independent witness. No public endpoint composes this method.
        """
        self.boot_verified = False
        with self.engine.transaction() as db:
            db.execute(
                "lock table privacy_deletion_requests,privacy_content_jobs in share mode"
            )
            self.publish()
            db.execute("update privacy_restore_state set required=true,ready=false")
        # A crash must never acknowledge a source quarantine that rolled back.
        with self.store.locked() as c:
            record = self.store.read(c)
            with self.engine.transaction() as db:
                self._outbox_complete(db)
                db.execute(
                    "select 1 from privacy_restore_outbox where checkpoint is distinct from %s limit 1",
                    (record["head"],),
                )
                if db.fetchone():
                    raise ContentBlocked("checkpoint_coverage")
                db.execute("select required,ready from privacy_restore_state")
                if db.fetchone() != (True, False):
                    raise ContentBlocked("checkpoint_source_unsealed")
            record.update(
                sequence=record["sequence"] + 1,
                sealed_head=record["head"],
                generation=self.generation,
                snapshot=self.snapshot,
                ready=False,
            )
            self.store.write(c, record)

    def reconcile(self):
        self.boot_verified = False
        # Quarantine is committed even if witness authentication fails.
        with self.engine.transaction() as db:
            db.execute(
                "update privacy_restore_state set required=true,ready=false,checkpoint=null"
            )
        with self.store.locked() as c:
            record = self.store.read(c)
            if record.get("sealed_head") != record["head"]:
                raise ContentBlocked("checkpoint_source_unsealed")
            if record["generation"] not in (None, self.generation):
                # A fresh restore requires an explicit operator-issued new boot
                # identity, not reusing a previous process's ready acknowledgement.
                raise ContentBlocked("checkpoint_generation")
            if record["snapshot"] not in (None, self.snapshot):
                raise ContentBlocked("checkpoint_snapshot")
            record.update(
                ready=False, generation=self.generation, snapshot=self.snapshot
            )
            self.store.write(c, record)
        try:
            RestoreGate(self.engine).apply(self.journal, record["head"])
            events = self.journal.read(record["head"])
            with self.engine.transaction() as db:
                db.execute(
                    "update privacy_restore_outbox set checkpoint=%s where request_id=any(%s::uuid[])",
                    (record["head"], [e["event_id"] for e in events[1:]]),
                )
            self.engine.queue_accepted()
            for _ in range(100):
                if not self.engine.run_one():
                    break
            for _ in range(100):
                if not self.engine.expire_one():
                    break
            with self.engine.transaction() as db:
                db.execute(
                    "select 1 from privacy_content_jobs where kind='account' and state<>'primary_verified' limit 1"
                )
                if db.fetchone():
                    raise ContentBlocked("restore_cleanup_pending")
                db.execute(
                    "select 1 from privacy_content_jobs where kind='export' and state in ('ready','running','pending') and account_id in (select account_id from privacy_restored_subjects) limit 1"
                )
                if db.fetchone():
                    raise ContentBlocked("restore_artifact_pending")
            with self.store.locked() as c:
                latest = self.store.read(c)
                if latest != record:
                    raise ContentBlocked("checkpoint_superseded")
                self._coverage(record["head"])
                record["ready"] = True
                self.store.write(c, record)
            self.boot_verified = True
        except Exception as error:
            with self.engine.transaction() as db:
                db.execute("update privacy_restore_state set ready=false")
            if isinstance(error, ContentBlocked):
                raise
            raise ContentBlocked("restore_reconciliation_failed") from None

    def _coverage(self, head):
        self.journal.read(head)
        with self.engine.transaction() as db:
            self._outbox_complete(db)
            db.execute(
                "select 1 from privacy_restore_outbox where checkpoint is distinct from %s limit 1",
                (head,),
            )
            if db.fetchone():
                raise ContentBlocked("checkpoint_coverage")
            db.execute("select required,ready,checkpoint from privacy_restore_state")
            if db.fetchone() != (True, True, head):
                raise ContentBlocked("checkpoint_dataset")

    @staticmethod
    def _outbox_complete(db):
        db.execute(
            "select 1 from privacy_deletion_requests r where r.state='accepted_restricted' and not exists(select 1 from privacy_restore_outbox o where o.request_id=r.request_id and o.account_id=r.account_id) union all select 1 from privacy_content_jobs j where j.kind in ('session','history') and not exists(select 1 from privacy_restore_outbox o where o.request_id=j.id and o.account_id=j.account_id) limit 1"
        )
        if db.fetchone():
            raise ContentBlocked("checkpoint_coverage")

    def ready(self):
        if not self.boot_verified:
            return False
        try:
            with self.store.locked() as c:
                r = self.store.read(c)
                if (
                    not r["ready"]
                    or r["generation"] != self.generation
                    or r["snapshot"] != self.snapshot
                ):
                    return False
                self._coverage(r["head"])
            return True
        except Exception:  # noqa: BLE001 -- health exposes no private diagnostics
            return False


class RestoreReadinessMiddleware:
    def __init__(self, app, required=False, coordinator=None):
        self.app, self.required, self.coordinator = app, required, coordinator

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        state = getattr(scope.get("app"), "state", None)
        coordinator = self.coordinator or getattr(state, "restore_coordinator", None)
        startup = self.coordinator is not None or getattr(
            state, "restore_startup_ready", False
        )
        if self.required and (
            not startup or coordinator is None or not coordinator.ready()
        ):
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1013})
            from starlette.responses import JSONResponse

            return await JSONResponse(
                {"status": "restore_quarantined"}, status_code=503
            )(scope, receive, send)
        await self.app(scope, receive, send)
