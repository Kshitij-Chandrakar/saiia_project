"""Versioned campaigns on existing marketing rendering, events and opt-out tokens."""

import json
import logging

from psycopg import Error as DatabaseError

from app.email.config import load_marketing_email_settings
from app.email.delivery import verified_event
from app.email.event_store import (
    OutboundEmailEventService,
    SupabaseOutboundEmailEventClient,
)
from app.email.marketing import MarketingEmailService, ResendMarketingProvider
from app.email.unsubscribe import MarketingUnsubscribeService


class CampaignEvents(SupabaseOutboundEmailEventClient):
    def __init__(self, dispatcher, task):
        self.dispatcher, self.task = dispatcher, task

    def _rpc(self, name, payload):
        return self.dispatcher.mail(self.task, name, payload)


class CampaignTokens:
    def __init__(self, dispatcher, task):
        self.dispatcher, self.task = dispatcher, task

    def get_marketing_opt_in(self, *, user_id):
        return self.dispatcher.mail(self.task, "allowed", {"p_user_id": user_id})[
            "allowed"
        ]

    def insert_token(self, *, user_id, **document):
        self.dispatcher.mail(self.task, "token", {"p_user_id": user_id, **document})


class CampaignDispatcher:
    def __init__(self, connect, *, settings=None, provider=None):
        self.connect = connect
        self.settings = settings or load_marketing_email_settings()
        self.provider = provider or ResendMarketingProvider(self.settings)

    def call(self, action, document):
        with self.connect() as c:
            return c.execute(
                "select public.administration_campaign_work(%s,%s::jsonb)",
                (action, json.dumps(document)),
            ).fetchone()[0]

    def mail(self, task, action, document):
        with self.connect() as c:
            return c.execute(
                "select public.administration_mail(%s,%s,%s,%s::jsonb)",
                (task["id"], task["lease"], action, json.dumps(document)),
            ).fetchone()[0]

    def run_one(self):
        if not self.settings.live_delivery_requested:
            return False
        task = self.call("claim", {})
        if not task:
            return False
        if task.get("skipped"):
            return True
        identity = {"id": task["id"], "lease": task["lease"]}
        state, event_id, message_id = "unknown", None, None
        try:
            service = MarketingEmailService(
                event_store=OutboundEmailEventService(
                    client=CampaignEvents(self, task)
                ),
                unsubscribe_service=MarketingUnsubscribeService(
                    client=CampaignTokens(self, task)
                ),
                settings=self.settings,
                provider=self.provider,
            )
            event = service.send_marketing_email(
                user_id=task["account_id"],
                recipient_email=task["email"],
                campaign_key=task["campaign_id"],
                template_key="admin_campaign_v1",
                idempotency_key="admin-campaign:" + task["id"],
                subject=task["subject"],
                body=task["body"],
            )
            event_id, message_id = event.id, event.provider_message_id
            state = (
                "skipped"
                if event.status == "canceled"
                else "accepted"
                if event.status == "sent"
                else "unknown"
            )
        except Exception:  # noqa: BLE001 -- untrusted provider errors contain recipient/content
            logging.getLogger(__name__).warning("Campaign outcome unknown")
        self.call(
            "finish",
            {
                **identity,
                "state": state,
                "event_id": event_id,
                "message_id": message_id,
            },
        )
        return True

    def delivery(self, raw, headers, secret, scope):
        document = verified_event(raw, headers, secret, scope)
        with self.connect() as c:
            return c.execute(
                "select public.administration_campaign_callback(%s::jsonb)",
                (json.dumps(document),),
            ).fetchone()[0]


class CampaignUnsubscribe:
    def __init__(self, connect):
        self.connect = connect

    def consume_token(self, *, token_hash):
        from app.email.unsubscribe import MarketingUnsubscribeStorageError

        try:
            with self.connect() as connection:
                return connection.execute(
                    "select public.administration_unsubscribe(%s)", (token_hash,)
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError):
            raise MarketingUnsubscribeStorageError(
                "Preference storage unavailable"
            ) from None
