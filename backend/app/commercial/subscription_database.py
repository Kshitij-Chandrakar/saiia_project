"""Dedicated restricted usage pool, using the existing psycopg pool convention."""

import threading
from typing import Any

from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.executor_connection import restore_executor_timeouts
from app.commercial.subscription_service import SubscriptionService


class SubscriptionDatabase:
    def __init__(self, enabled: str = "false", dsn: str = "", *, session_pooler=None) -> None:
        self._session_pooler = session_pooler
        self._enabled, self._dsn = enabled, dsn
        self._pool: Any = None
        self._service: SubscriptionService | None = None
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    @staticmethod
    def check(conn: Any) -> None:
        try:
            SubscriptionDatabase._check_permissions(conn)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            # Pool worker diagnostics must not format a driver exception/DSN.
            raise RuntimeError("subscription unavailable") from None

    @staticmethod
    def _check_permissions(conn: Any) -> None:
        row = conn.execute(
            "select session_user,current_user,current_setting('role'),rolsuper or rolbypassrls or rolcreaterole or rolcreatedb or rolreplication from pg_roles where rolname=session_user"
        ).fetchone()
        if row != ("usage_executor", "usage_executor", "none", False):
            raise RuntimeError("subscription unavailable")
        if conn.execute(
            "select exists(select 1 from pg_auth_members where member=(select oid from pg_roles where rolname=session_user))"
        ).fetchone()[0]:
            raise RuntimeError("subscription unavailable")
        tables = (
            "account_plan_bindings",
            "usage_periods",
            "usage_operations",
            "usage_events",
            "subscription_configuration",
            "subscription_payment_receipts",
            "subscription_binding_history",
            "subscription_auto_runs",
            "subscription_auto_replies",
            "interview_session_my_answers",
            "interview_answer_diagrams",
            "interview_answer_sources",
            "session_generation_turns",
            "subscription_scheduled_changes",
            "subscription_screen_threads",
            "subscription_screen_results",
            "subscription_resume_history",
            "subscription_resume_jobs",
            "subscription_resume_active_sets",
            "subscription_notes_versions",
            "subscription_relay_frames",
            "subscription_relay_connections",
            "subscription_auth_handoffs",
            "subscription_deletion_jobs",
            "subscription_handoff_limits",
        )
        if conn.execute(
            "select bool_and(not has_table_privilege(current_user,t,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')) "
            "from unnest(%s::text[]) t",
            (["public." + table for table in tables],),
        ).fetchone()[0] is not True:
            raise RuntimeError("subscription unavailable")
        signatures = (
            "public.subscription_current(uuid,boolean)",
            "public.subscription_access_check(uuid)",
            "public.subscription_relay_claim(uuid,uuid,uuid)",
            "public.subscription_relay_frame(uuid,uuid,uuid,bigint,uuid,text,bigint,text,integer)",
            "public.subscription_handoff(text,uuid,text,text,text)",
            "public.subscription_deletion_prepare(uuid,uuid)",
            "public.subscription_account_usage(uuid)",
            "public.subscription_auto_sweep(integer)",
            "public.subscription_auto_reap(uuid)",
            "public.subscription_auto_call(uuid,text,jsonb)",
            "public.subscription_auto_authorize(uuid,uuid,uuid,bigint,text)",
            "public.subscription_auto_disconnect(uuid,uuid,uuid,bigint)",
            "public.subscription_auto_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb,uuid,uuid,bigint,text)",
            "public.subscription_clipboard_save(uuid,uuid,text,text)",
            "public.subscription_clipboard_read(uuid,uuid)",
            "public.subscription_sketch_source(uuid,uuid,uuid,text)",
            "public.subscription_sketch_operation(uuid,uuid,uuid,text,uuid,text,uuid,jsonb,text,text)",
            "public.subscription_session_read(uuid,uuid)",
            "public.subscription_screen_call(uuid,text,jsonb)",
            "public.subscription_resume_call(uuid,text,jsonb)",
            "public.subscription_aux_call(uuid,text,jsonb)",
            "public.subscription_result_sweep(integer)",
            "public.subscription_answer_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb)",
        )
        if conn.execute(
            "select bool_and(has_function_privilege(current_user,s,'EXECUTE')) "
            "from unnest(%s::text[]) s",
            (list(signatures),),
        ).fetchone()[0] is not True:
            raise RuntimeError("subscription unavailable")
        conn.commit()

    @staticmethod
    def reset(conn: Any) -> None:
        try:
            SubscriptionDatabase._reset_connection(conn)
        except Exception:
            raise RuntimeError("subscription unavailable") from None

    @staticmethod
    def _reset_connection(conn: Any) -> None:
        # Never return a failed transaction or request-local setting to the pool.
        conn.rollback()
        conn.execute("RESET ALL")
        restore_executor_timeouts(conn)
        conn.commit()
        SubscriptionDatabase.check(conn)

    def start(self) -> None:
        if self._enabled != "true":
            return
        try:
            from psycopg import Connection
            from psycopg_pool import ConnectionPool

            from app.commercial.executor_connection import connection_parameters

            args = connection_parameters(
                self._dsn, "usage_executor", session_pooler=self._session_pooler
            )

            class SafeConnection(Connection):  # type: ignore[misc]
                def __repr__(self) -> str:
                    return "<subscription connection>"

                @classmethod
                def connect(cls, *a: Any, **kw: Any) -> Any:
                    try:
                        return super().connect(*a, **kw)
                    except Exception:
                        raise RuntimeError("subscription unavailable") from None

            self._pool = ConnectionPool(
                "",
                kwargs={
                    **args,
                    "connect_timeout": 3,
                    "prepare_threshold": None,
                    "options": "-c lock_timeout=5000 -c statement_timeout=10000 -c idle_in_transaction_session_timeout=15000 -c transaction_timeout=20000",
                },
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
                name="subscription-usage",
            )
            self._pool.open(wait=True, timeout=4)
            from app.answer_models import MODEL_CATALOG

            self._service = SubscriptionService(
                self.connect, model_keys=frozenset(MODEL_CATALOG)
            )
            self._stop.clear()
            self._worker = threading.Thread(
                target=self._sweep, name="subscription-recovery", daemon=True
            )
            self._worker.start()
        except Exception:
            self.close()

    def connect(self) -> Any:
        if self._pool is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            return self._pool.getconn(timeout=1)
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    def service(self) -> SubscriptionService:
        if self._service is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        return self._service

    def _sweep(self) -> None:
        while not self._stop.wait(5):
            service = self._service
            if service is None:
                return
            try:
                service._channel._transaction(
                    True,
                    lambda query: query(
                        "SELECT public.subscription_auto_sweep(50)", ()
                    ),
                )
                service._channel._transaction(
                    True,
                    lambda query: query(
                        "SELECT public.subscription_result_sweep(50)", ()
                    ),
                )
            except CatalogStoreError:
                # Pending work is durable; a later sweep retries reconciliation,
                # never provider execution or an authorization extension.
                continue

    def close(self) -> None:
        self._stop.set()
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.join(timeout=12)
        pool, self._pool = self._pool, None
        self._service = None
        if pool is not None:
            pool.close(timeout=2)
