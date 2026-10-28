"""Opt-in backend-only direct SQL pool; no imports/connections to a DB on import."""

from __future__ import annotations

from typing import Any

from app.commercial.catalog_store import CatalogStoreError, ErrorCode
from app.commercial.draft_service import DraftService
from app.commercial.executor_connection import restore_executor_timeouts
from app.commercial.lifecycle_service import LifecycleService
from app.commercial.review_service import Resolver

SIGNATURE = "public.catalog_draft_service_call(uuid,text,uuid,uuid,bigint,jsonb,text)"
LIFECYCLE_SIGNATURES = (
    "public.catalog_review_service_call(uuid,text,uuid,uuid,jsonb,jsonb)",
    "public.catalog_lifecycle_service_call(uuid,text,jsonb,jsonb)",
    "public.catalog_lifecycle_read_call(uuid,text,uuid)",
)
LIFECYCLE_TABLES = (
    "catalog_publication_reviews",
    "catalog_lifecycle_requests",
    "catalog_publications",
    "catalog_public_state",
)
TABLES = (
    "subscription_admin_permissions",
    "catalog_plans",
    "catalog_drafts",
    "catalog_draft_revisions",
    "catalog_offer_versions",
    "catalog_price_versions",
    "catalog_visibility",
    "catalog_admin_actions",
    "catalog_draft_requests",
)


class CatalogDatabase:
    def __init__(
        self,
        enabled: str = "false",
        dsn: str = "",
        *,
        lifecycle_enabled: str = "false",
        resolver: Resolver | None = None,
        public_only: bool = False,
        session_pooler=None,
    ):
        self._session_pooler = session_pooler
        self._public_only = public_only
        self._enabled = enabled
        self._dsn = dsn
        self._pool: Any = None
        self._service: DraftService | None = None
        self._lifecycle_enabled = lifecycle_enabled == "true"
        # Trusted injection only. No production resolver or environment fallback.
        from app.commercial.publication_policy import resolve_policy
        self._resolver = resolver if resolver is not None else resolve_policy
        self._lifecycle: LifecycleService | None = None

    def start(self) -> None:
        # Failed opt-in configuration denies catalog access, not local app startup.
        if self._enabled != "true":
            return
        try:
            from psycopg import Connection, OperationalError
            from psycopg_pool import ConnectionPool

            from app.commercial.executor_connection import connection_parameters

            params = connection_parameters(
                self._dsn,
                "catalog_public_reader" if self._public_only else "catalog_draft_executor",
                session_pooler=self._session_pooler,
            )

            class SafeConnection(Connection):
                def __repr__(self) -> str:
                    return "<catalog database connection>"

                @classmethod
                def connect(cls, *args: Any, **kwargs: Any) -> Any:
                    try:
                        return super().connect(*args, **kwargs)
                    except Exception:
                        # Pool worker logs must not serialize original DSNs/errors.
                        raise OperationalError("catalog database unavailable") from None

            self._pool = ConnectionPool(
                "",
                kwargs={
                    **params,
                    "connect_timeout": 3,
                    "prepare_threshold": None,
                    "application_name": "catalog-drafts",
                    "tcp_user_timeout": 10000,
                    "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000 -c transaction_timeout=20000",
                },
                connection_class=SafeConnection,
                open=False,
                close_returns=True,
                min_size=1,
                max_size=4,
                timeout=1,
                max_waiting=8,
                reconnect_timeout=3,
                num_workers=1,
                name="catalog-drafts",
                configure=lambda conn: self._check(
                    conn, lifecycle=self._lifecycle_enabled, public_only=self._public_only
                ),
                check=lambda conn: self._check(conn, lifecycle=self._lifecycle_enabled, public_only=self._public_only),
                reset=lambda conn: self._reset(conn, lifecycle=self._lifecycle_enabled, public_only=self._public_only),
            )
            self._pool.open(wait=True, timeout=4)
            if self._public_only:
                return
            from app.answer_models import MODEL_CATALOG

            self._service = DraftService(
                self.connect, model_keys=frozenset(MODEL_CATALOG)
            )
            if self._lifecycle_enabled:
                self._lifecycle = LifecycleService(
                    self.connect, resolver=self._resolver
                )
        except Exception:
            self.close()

    @staticmethod
    def _check(conn: Any, *, lifecycle: bool = False, public_only: bool = False) -> None:
        try:
            if conn.info.server_version < 170000:
                raise ValueError  # Native transaction_timeout bounds whole transactions.
            row = conn.execute(
                "SELECT session_user,current_user,current_setting('role'),"
                "coalesce(current_setting('catalog.draft_actor',true),''),"
                "rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication "
                "FROM pg_roles WHERE rolname=session_user"
            ).fetchone()
            role = "catalog_public_reader" if public_only else "catalog_draft_executor"
            if row != (
                role,
                role,
                "none",
                "",
                False,
            ):
                raise ValueError
            if not conn.execute(
                "SELECT has_function_privilege(current_user,%s,'EXECUTE')", ("public.catalog_public_read()" if public_only else SIGNATURE,)
            ).fetchone()[0]:
                raise ValueError
            if lifecycle:
                for signature in LIFECYCLE_SIGNATURES:
                    if not conn.execute(
                        "SELECT has_function_privilege(current_user,%s,'EXECUTE')",
                        (signature,),
                    ).fetchone()[0]:
                        raise ValueError
            if conn.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=session_user)"
            ).fetchone()[0]:
                raise ValueError
            if conn.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='public' AND left(p.proname,8)='catalog_' "
                "AND NOT EXISTS(SELECT 1 FROM unnest(%s::text[]) s WHERE p.oid=to_regprocedure(s)) "
                "AND has_function_privilege(current_user,p.oid,'EXECUTE'))",
                (["public.catalog_public_read()"] if public_only else [SIGNATURE, *LIFECYCLE_SIGNATURES, "public.catalog_policy_resolve(uuid,text,text)"],),
            ).fetchone()[0]:
                raise ValueError
            # Detect missing schema and accidental direct ACL/owner privileges.
            if conn.execute(
                "SELECT bool_and(NOT has_table_privilege(current_user,t,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')) FROM unnest(%s::text[]) t",
                (["public." + table for table in TABLES],),
            ).fetchone()[0] is not True:
                raise ValueError
            if conn.execute(
                "SELECT bool_and(CASE WHEN to_regclass(t) IS NULL THEN %s ELSE NOT has_table_privilege(current_user,t,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE') END) FROM unnest(%s::text[]) t",
                (not lifecycle, ["public." + table for table in LIFECYCLE_TABLES]),
            ).fetchone()[0] is not True:
                raise ValueError
            if conn.execute("SELECT to_regclass('public.catalog_publication_policies')").fetchone()[0] and conn.execute("SELECT has_table_privilege(current_user,'public.catalog_publication_policies','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')").fetchone()[0]:
                raise ValueError
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise RuntimeError("catalog database unavailable") from None

    @staticmethod
    def _reset(conn: Any, *, lifecycle: bool = False, public_only: bool = False) -> None:
        try:
            conn.rollback()
            conn.execute("RESET ALL")
            restore_executor_timeouts(conn)
            conn.commit()
            CatalogDatabase._check(conn, lifecycle=lifecycle, public_only=public_only)
        except Exception:
            # Pool discards connections whose reset fails; never reuse dirty state.
            raise RuntimeError("catalog database unavailable") from None

    def connect(self) -> Any:
        if self._pool is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        try:
            return self._pool.getconn(timeout=1)
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    def service(self) -> DraftService:
        if self._service is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        return self._service

    def lifecycle_service(self) -> LifecycleService:
        if self._lifecycle is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        return self._lifecycle

    def close(self) -> None:
        self._service = None
        self._lifecycle = None
        pool, self._pool = self._pool, None
        if pool is not None:
            try:
                pool.close(timeout=2)
            except Exception:
                pass
