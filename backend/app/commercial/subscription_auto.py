"""Server-held Auto capability; a client ping is liveness, never elapsed time."""

import asyncio
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter

from app.commercial.account_entitlements import json_query
from app.commercial.admin_access import VerifiedActor
from app.commercial.catalog_contract import Instant
from app.commercial.subscription_service import SubscriptionService

INSTANT = TypeAdapter(Instant)


class AccountAutoLease:
    def __init__(
        self,
        service: SubscriptionService,
        actor: VerifiedActor,
        source: str,
        *,
        run_id: str | None = None
    ) -> None:
        self.service, self.actor, self.source = service, actor, source
        self.row: dict[str, Any] | None = None
        self.deadline = 0.0
        self.changed = asyncio.Event()
        self.stopped = False
        self.run_id = run_id

    def _accept(self, row: Any, began: float) -> None:
        self.row = {**(self.row or {}), **row}
        self.deadline = began + max(
            0,
            (
                INSTANT.validate_python(row["authorized_until"])
                - INSTANT.validate_python(row["server_time"])
            ).total_seconds(),
        )
        self.changed.set()

    async def start(self) -> None:
        resolved = await asyncio.to_thread(self.service.resolve, self.actor)
        if not any(
            e.feature == "assistant.auto"
            and e.allowed
            and self.source in e.audio_sources
            for e in resolved["snapshot"].terms.entitlements
        ):
            raise PermissionError("Auto source denied")
        began = asyncio.get_running_loop().time()
        key = self.run_id or str(uuid4())
        row = await asyncio.to_thread(
            self.service.auto, self.actor, "start", dict(run_id=key, request_id=key)
        )
        self._accept(row, began)
        await self.authorize()

    async def authorize(self) -> None:
        if self.row is None:
            raise PermissionError("Auto has not started")
        if self.stopped or self.remaining() <= 0:
            raise PermissionError("Auto authorization expired")
        subject = await asyncio.to_thread(self.service._channel._actor, self.actor)
        began = asyncio.get_running_loop().time()
        capability = self.row
        row = await asyncio.to_thread(
            self.service._channel._transaction,
            False,
            lambda q: json_query(
                q,
                "SELECT public.subscription_auto_authorize(%s,%s,%s,%s,%s)",
                (
                    subject,
                    capability["run_id"],
                    capability["owner_token"],
                    capability["fence"],
                    self.source,
                ),
            ),
        )
        self._accept(row, began)

    def remaining(self) -> float:
        return (
            0
            if self.stopped
            else max(0, self.deadline - asyncio.get_running_loop().time())
        )

    async def heartbeat(self) -> None:
        if self.row is None:
            raise PermissionError("Auto has not started")
        await self.authorize()
        began = asyncio.get_running_loop().time()
        capability = self.row
        row = await asyncio.to_thread(
            self.service.auto,
            self.actor,
            "renew",
            dict(
                run_id=capability["run_id"],
                owner_token=capability["owner_token"],
                fence=capability["fence"],
                sequence=capability["sequence"] + 1,
            ),
        )
        self._accept(row, began)
        if not row["active"]:
            raise PermissionError("Auto allowance exhausted")

    async def expired(self) -> None:
        while not self.stopped and self.remaining() > 0:
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), self.remaining())
            except asyncio.TimeoutError:
                break

    async def stop(self) -> None:
        self.stopped = True
        self.changed.set()
        if self.row is not None:
            capability = self.row
            await asyncio.to_thread(
                self.service._channel._transaction,
                True,
                lambda q: q(
                    "SELECT public.subscription_auto_disconnect(%s,%s,%s,%s)",
                    (
                        self.actor.subject_id,
                        capability["run_id"],
                        capability["owner_token"],
                        capability["fence"],
                    ),
                ),
            )
