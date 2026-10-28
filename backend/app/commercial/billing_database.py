"""Default-off restricted billing pool. No enablement is implied by credentials."""

import logging

from app.commercial.billing_service import BillingService
from app.commercial.razorpay import RazorpaySubscriptions
from app.commercial.subscription_database import SubscriptionDatabase

logger = logging.getLogger(__name__)


class BillingDatabase(SubscriptionDatabase):
    def __init__(self, settings):
        super().__init__("false", settings.BILLING_DSN)
        self.settings = settings
        self.billing = None
        self.notifications = None
        self.admin = None

    @staticmethod
    def check(conn):
        try:
            BillingDatabase._check_permissions(conn)
        except Exception:
            logger.exception("billing operation unavailable", exc_info=False)
            conn.rollback()
            raise RuntimeError("billing unavailable") from None

    @staticmethod
    def reset(conn):
        try:
            conn.rollback()
            conn.execute("RESET ALL")
            conn.execute("SET lock_timeout=5000")
            conn.execute("SET statement_timeout=10000")
            conn.execute("SET idle_in_transaction_session_timeout=15000")
            conn.execute("SET transaction_timeout=20000")
            conn.commit()
            BillingDatabase.check(conn)
        except Exception:
            logger.exception("billing operation unavailable", exc_info=False)
            raise RuntimeError("billing unavailable") from None

    @staticmethod
    def _check_permissions(conn):
        row = conn.execute(
            "select session_user,current_user,current_setting('role'),rolsuper or rolbypassrls or rolcreaterole or rolcreatedb or rolreplication from pg_roles where rolname=session_user"
        ).fetchone()
        if row != ("usage_binding_executor", "usage_binding_executor", "none", False):
            raise RuntimeError("billing unavailable")
        if conn.execute(
            "select exists(select 1 from pg_auth_members where member=(select oid from pg_roles where rolname=session_user))"
        ).fetchone()[0]:
            raise RuntimeError("billing unavailable")
        for table in (
            "billing_operations",
            "billing_payable_quotes",
            "billing_evidence",
            "billing_webhook_events",
            "account_plan_bindings",
        ):
            if conn.execute(
                "select has_table_privilege(current_user,%s,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')",
                ("public." + table,),
            ).fetchone()[0]:
                raise RuntimeError("billing unavailable")
        for function in (
            "billing_call(uuid,text,uuid,jsonb)",
            "billing_pending()",
            "billing_lookup(text)",
            "billing_event(text,text,text,text)",
            "billing_current(uuid)",
        ):
            if not conn.execute(
                "select has_function_privilege(current_user,%s,'EXECUTE')",
                ("public." + function,),
            ).fetchone()[0]:
                raise RuntimeError("billing unavailable")
        conn.commit()

    def start(self):
        s = self.settings
        if (
            s.BILLING_ENABLED != "true"
            or s.BILLING_RENEWAL != "automatic"
            or not s.BILLING_TOTAL_POLICY_REF
        ):
            return
        try:
            from psycopg.conninfo import conninfo_to_dict
            from psycopg_pool import ConnectionPool

            provider = RazorpaySubscriptions(
                s.RAZORPAY_TEST_KEY_ID, s.RAZORPAY_TEST_KEY_SECRET
            )
            args = conninfo_to_dict(self._dsn)
            local = args.get("host") in ("localhost", "127.0.0.1", "::1")
            if (
                set(args)
                - {
                    "host",
                    "port",
                    "dbname",
                    "user",
                    "password",
                    "sslmode",
                    "sslrootcert",
                }
                or args.get("user") != "usage_binding_executor"
                or not args.get("host")
                or not args.get("dbname")
                or args.get("sslmode")
                not in ({"disable", "verify-full"} if local else {"verify-full"})
                or (not local and not args.get("password"))
                or "," in args["host"]
            ):
                raise ValueError()
            # Reuse redacted connection implementation; driver exception text
            # must never put DSNs/credentials into pool diagnostics.
            from psycopg import Connection

            class SafeConnection(Connection):
                def __repr__(self):
                    return "<billing connection>"

                @classmethod
                def connect(cls, *a, **kw):
                    try:
                        return super().connect(*a, **kw)
                    except Exception:
                        logger.exception(
                            "billing operation unavailable", exc_info=False
                        )
                        raise RuntimeError("billing unavailable") from None

            self._pool = ConnectionPool(
                "",
                kwargs={**args, "connect_timeout": 3, "prepare_threshold": None},
                connection_class=SafeConnection,
                close_returns=True,
                open=False,
                min_size=1,
                max_size=4,
                max_waiting=8,
                timeout=1,
                reconnect_timeout=3,
                configure=self.check,
                check=self.check,
                reset=self.reset,
                name="billing",
            )
            self._pool.open(wait=True, timeout=4)
            import json

            from app.answer_models import MODEL_CATALOG

            self.billing = BillingService(
                self.connect,
                provider,
                merchant=s.RAZORPAY_TEST_ACCOUNT_ID,
                webhook_secrets=tuple(
                    x
                    for x in (
                        s.RAZORPAY_TEST_WEBHOOK_SECRET,
                        s.RAZORPAY_TEST_PREVIOUS_WEBHOOK_SECRET,
                    )
                    if x
                ),
                renewal=s.BILLING_RENEWAL,
                enabled=True,
                total_policy_ref=s.BILLING_TOTAL_POLICY_REF,
                plan_mappings=json.loads(s.RAZORPAY_TEST_PLAN_MAPPINGS),
                model_keys=frozenset(MODEL_CATALOG),
            )
            if any(
                getattr(s, name, "false") == "true"
                for name in ("BILLING_NOTIFICATIONS_ENABLED", "BILLING_ADMIN_ENABLED")
            ):
                connection = self.connect()
                try:
                    ready = connection.execute(
                        "select to_regprocedure('public.billing_notification_call(text,uuid,jsonb)'),to_regprocedure('public.billing_admin_call(uuid,text,uuid,jsonb)'),to_regprocedure('public.billing_delivery_call(text,jsonb)')"
                    ).fetchone()
                    if not all(ready):
                        raise RuntimeError("billing operations migration unavailable")
                finally:
                    connection.rollback()
                    connection.close()
            if getattr(s, "BILLING_NOTIFICATIONS_ENABLED", "false") == "true":
                from app.email.billing import BillingNotifications

                self.notifications = BillingNotifications(self.connect)
            if getattr(s, "BILLING_ADMIN_ENABLED", "false") == "true":
                from app.commercial.billing_admin import BillingAdmin

                self.admin = BillingAdmin(
                    self.connect, self.billing, self.notifications
                )
            self._stop.clear()
            import threading

            self._worker = threading.Thread(
                target=self._sweep, name="billing-recovery", daemon=True
            )
            self._worker.start()
        except Exception:
            logger.exception("billing operation unavailable", exc_info=False)
            self.close()

    def _sweep(self):
        while not self._stop.wait(30):
            for service, action in (
                (self.billing, "sweep"),
                (self.admin, "run"),
                (self.notifications, "run"),
            ):
                if service:
                    try:
                        getattr(service, action)()
                    except Exception:
                        logger.exception(
                            "billing operation unavailable", exc_info=False
                        )
                        # Each durable queue recovers independently.

    def close(self):
        super().close()
        self.billing = None
        self.notifications = None
        self.admin = None
