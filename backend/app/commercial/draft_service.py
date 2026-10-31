"""Closed validated draft service. No routes, configuration or connection factory.

The injected psycopg3-compatible factory is trusted infrastructure, not input.
It must yield a fresh connection authenticated AS catalog_draft_executor (not a
SET ROLE from PostgREST). No login/member or production factory is provisioned.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import TypeAdapter, ValidationError

from app.auth.supabase_auth import (
    SupabaseAuthConfigurationError,
    SupabaseAuthError,
    verify_supabase_token,
)
from app.commercial import catalog_contract as c
from app.commercial.admin_access import VerifiedActor, validate_bounded_draft
from app.commercial.catalog_store import (
    CatalogStore,
    CatalogStoreError,
    ErrorCode,
    RpcFailure,
    _error,
    _input,
)

_Result = TypeVar("_Result")
Query = Callable[[str, tuple[Any, ...]], Any]

_ID = TypeAdapter(c.Identifier)
_QUANTITY = TypeAdapter(c.Quantity)
_REASON = TypeAdapter(c.Text)


class DraftService:
    def __init__(
        self,
        connect: Callable[[], Any] | None = None,
        *,
        model_keys: frozenset[str] = frozenset(),
    ):
        # Reuse adapter's trusted registry type validation; never connect here.
        CatalogStore(model_keys=model_keys)
        self._connect = connect
        self._models = model_keys

    def _actor(self, actor: VerifiedActor) -> str:
        # A Python dataclass alone is forgeable. Verify retained bearer again at
        # this closed channel; no role/actor argument in customer draft payloads.
        try:
            if type(actor) is not VerifiedActor:
                raise SupabaseAuthError()
            user = verify_supabase_token(actor._bearer)
            subject = _ID.validate_python(user.user_id, strict=True)
            if user.role != "authenticated" or subject != actor.subject_id:
                raise SupabaseAuthError()
            return subject
        except SupabaseAuthConfigurationError:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None
        except (SupabaseAuthError, ValidationError, ValueError, TypeError):
            raise CatalogStoreError(ErrorCode.DENIED) from None
        except Exception:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE) from None

    def _transaction(self, write: bool, work: Callable[[Query], _Result]) -> _Result:
        """Shared closed-channel transaction/outcome boundary; never retries."""
        if self._connect is None:
            raise CatalogStoreError(ErrorCode.UNAVAILABLE)
        connection = None
        dispatched = False
        try:
            connection = self._connect()
            if connection.autocommit or connection.info.transaction_status != 0:
                raise CatalogStoreError(ErrorCode.UNAVAILABLE)
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                cursor.execute("SET LOCAL statement_timeout = '10s'")

                def query(sql: str, params: tuple[Any, ...]) -> Any:
                    nonlocal dispatched
                    dispatched = True
                    try:
                        cursor.execute(sql, params)
                        return cursor.fetchone()[0]
                    except Exception as exc:
                        raise RpcFailure(
                            getattr(exc, "sqlstate", None)
                            or getattr(exc, "pgcode", None)
                        ) from None

                result = work(query)
            connection.commit()
            return result
        except CatalogStoreError:
            raise
        except Exception as exc:
            failure = (
                exc
                if isinstance(exc, RpcFailure)
                else RpcFailure(
                    getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None),
                    dispatched=dispatched,
                )
            )
            raise CatalogStoreError(_error(failure, write)) from None
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
                try:
                    connection.close()
                except Exception:
                    pass

    def _run(
        self,
        subject: str,
        operation: str,
        key: str | None,
        work: Callable[[CatalogStore], c.CatalogDraft],
    ) -> c.CatalogDraft:
        write = operation != "draft.read"

        def transaction(query: Query) -> c.CatalogDraft:
            def rpc(name: str, params: dict[str, object]) -> object:
                expected = (
                    "catalog_adapter_save_draft"
                    if write
                    else "catalog_adapter_load_draft"
                )
                if name != expected:
                    raise RpcFailure("42501", dispatched=False)
                return query(
                    "SELECT public.catalog_draft_service_call(%s,%s,%s,%s,%s,%s::jsonb,%s)",
                    (
                        subject,
                        operation,
                        params["p_id"],
                        key,
                        params.get("p_expected"),
                        (
                            json.dumps(params["p_document"], allow_nan=False)
                            if write
                            else None
                        ),
                        params.get("p_reason"),
                    ),
                )

            return work(CatalogStore(rpc, model_keys=self._models))

        return self._transaction(write, transaction)

    def retrieve(self, actor: VerifiedActor, draft_id: object) -> c.CatalogDraft:
        subject = self._actor(actor)
        identifier = _input(_ID, draft_id)
        return self._run(
            subject, "draft.read", None, lambda store: store.load_draft(identifier)
        )

    def preview(self, actor: VerifiedActor, draft_id: object) -> c.ValidationReport:
        # Authorizes the actual read; preview is pure and creates no archive.
        draft = self.retrieve(actor, draft_id)
        return validate_bounded_draft(draft, model_keys=self._models)

    def create(
        self,
        actor: VerifiedActor,
        payload: object,
        *,
        request_id: object,
        reason: object,
    ) -> c.CatalogDraft:
        return self._save(
            actor, payload, expected_revision=0, request_id=request_id, reason=reason
        )

    def edit(
        self,
        actor: VerifiedActor,
        payload: object,
        *,
        expected_revision: object,
        request_id: object,
        reason: object,
    ) -> c.CatalogDraft:
        expected = _input(_QUANTITY, expected_revision)
        if expected == 0:
            raise CatalogStoreError(ErrorCode.INVALID)
        return self._save(
            actor,
            payload,
            expected_revision=expected,
            request_id=request_id,
            reason=reason,
        )

    def _save(
        self,
        actor: VerifiedActor,
        payload: object,
        *,
        expected_revision: int,
        request_id: object,
        reason: object,
    ) -> c.CatalogDraft:
        subject = self._actor(actor)
        key = _input(_ID, request_id)
        reason = _input(_REASON, reason)
        report = validate_bounded_draft(payload, model_keys=self._models)
        if (
            not report.valid
            or report.draft is None
            or report.draft.state != "draft"
            or report.draft.revision != expected_revision + 1
        ):
            raise CatalogStoreError(ErrorCode.INVALID)
        # B defines these collections as sets, not ordered commercial rules.
        # Reuse its canonical normalization (including explicit denied features).
        data = report.draft.model_dump(mode="python")
        data["terms"] = c._normalized(report.draft.terms)
        draft = c.CatalogDraft.model_validate(data)
        operation = "draft.create" if expected_revision == 0 else "draft.edit"
        return self._run(
            subject,
            operation,
            key,
            lambda store: store.save_draft(
                draft, expected_revision=expected_revision, reason=reason
            ),
        )
