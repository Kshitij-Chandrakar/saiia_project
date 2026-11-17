"""Two-role authority: fixed operations, fresh database authority, no role claims."""

import asyncio
import json
import logging
import threading
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from starlette.concurrency import run_in_threadpool

from app.privacy_content import ContentBlocked
from app.auth.supabase_auth import get_current_user, verify_supabase_token
from app.commercial.admin_access import VerifiedActor
from app.commercial.billing_api import body
from app.commercial.executor_connection import connect_executor
from app.privacy import recent_presence

router = APIRouter(prefix="/api/admin")
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Authorization"}
OPERATIONS = {
    "me": frozenset(),
    "memberships": frozenset({"after"}),
    "audit": frozenset({"after"}),
    "receipt": frozenset({"id"}),
    "membership.review": frozenset(
        {"target", "role", "status", "reason", "operation_id"}
    ),
    "membership.confirm": frozenset({"review_id", "confirm"}),
}


class Administration:
    def __init__(self, connect, retention_connect=None, dispatch_connect=None):
        self.connect = connect
        self.retention_connect = retention_connect
        self.dispatch_connect = dispatch_connect
        self.restore = None
        self.dispatcher = None
        self.campaign_dispatcher = None
        self.stop = threading.Event()
        self.thread = None

    def record_attempt(self, document):
        with self.connect() as connection:
            connection.execute(
                "select public.administration_attempt(%s::jsonb)",
                (json.dumps(document),),
            )

    def metrics(self, user, document):
        from datetime import datetime
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        if set(document) != {"start", "end", "timezone"} or any(
            not isinstance(value, str) or len(value) > 64 for value in document.values()
        ):
            raise HTTPException(400)
        try:
            start, end = (
                datetime.fromisoformat(document[key].replace("Z", "+00:00"))
                for key in ("start", "end")
            )
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError()
            ZoneInfo(document["timezone"])
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            raise HTTPException(400) from None
        with self.connect() as connection:
            result = connection.execute(
                "select public.administration_metrics(%s,%s,%s,%s)",
                (user.user_id, start, end, document["timezone"]),
            ).fetchone()[0]
        if result.get("error"):
            raise HTTPException(400 if result["error"] == "invalid" else 404)
        return result

    def retire(self):
        if self.retention_connect is None:
            raise RuntimeError("administration retention unavailable")
        with self.retention_connect() as connection:
            connection.execute("set local statement_timeout='5s'")
            connection.execute("set local lock_timeout='1s'")
            result = connection.execute(
                "select public.administration_retention(100)"
            ).fetchone()[0]
            result["lifecycle"] = connection.execute(
                "select public.administration_lifecycle(100)"
            ).fetchone()[0]
            return result

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop.clear()

        def work():
            retention_at = 0.0
            while not self.stop.is_set():
                try:
                    if self.restore is not None:
                        if not self.restore.ready():
                            raise RuntimeError("administration restore unavailable")
                        self.restore.publish()
                    if time.monotonic() >= retention_at:
                        retention_at = time.monotonic() + 60
                        self.retire()
                    if self.dispatcher is not None:
                        self.dispatcher.run_one()
                    if self.campaign_dispatcher is not None:
                        self.campaign_dispatcher.run_one()
                except (DatabaseError, RuntimeError, OSError, ContentBlocked):
                    logging.getLogger(__name__).warning(
                        "Administration retention deferred"
                    )
                self.stop.wait(1)

        self.thread = threading.Thread(
            target=work, name="administration-retention", daemon=True
        )
        self.thread.start()

    def bind_billing(self, billing):
        from app.admin_dispatch import CancellationDispatcher

        self.dispatcher = CancellationDispatcher(self.dispatch_connect, billing)

    def bind_campaigns(self, settings):
        from app.admin_campaigns import CampaignDispatcher

        provider = None
        if settings.ADMIN_LOCAL_SMTP_PORT:
            if settings.C15_RUNTIME_LOCAL_REHEARSAL != "true":
                raise RuntimeError("local campaign capture requires isolated rehearsal")
            from app.privacy_runtime import LocalCatcher

            provider = LocalCatcher("127.0.0.1", settings.ADMIN_LOCAL_SMTP_PORT)
        self.campaign_dispatcher = CampaignDispatcher(
            self.dispatch_connect, provider=provider
        )

    def cancellation_status(self, user, operation):
        with self.connect() as c:
            result = c.execute(
                "select public.administration_cancel(%s,null,null,'status',%s::jsonb)",
                (user.user_id, json.dumps({"operation_id": str(UUID(operation))})),
            ).fetchone()[0]
        if result.get("error"):
            raise HTTPException(404)
        return result

    def successor(self, user, action, document):
        fields = {
            "offer": {"target", "confirm"},
            "accept": {"transfer_id", "confirm"},
            "status": {"transfer_id"},
        }
        if action not in fields or set(document) != fields[action]:
            raise HTTPException(400)
        try:
            UUID(document["target"] if action == "offer" else document["transfer_id"])
            if action != "status" and document["confirm"] is not True:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400) from None
        session = presence = None
        if action != "status":
            session, presence = recent_presence(user)
            if (user.claims or {}).get("aal") != "aal2":
                raise HTTPException(403)
        with self.connect() as c:
            result = c.execute(
                "select public.administration_successor(%s,%s,%s,%s,%s::jsonb)",
                (user.user_id, session, presence, action, json.dumps(document)),
            ).fetchone()[0]
        if result.get("error"):
            raise HTTPException(
                404
                if result["error"] == "not_found"
                else 403
                if result["error"] == "reauthentication_required"
                else 409
            )
        return result

    def campaign(self, user, action, document):
        allowed = {
            "list": {"after"},
            "read": {"campaign_id"},
            "preview": {"campaign_id"},
            "save": {"campaign_id", "revision", "name", "subject", "body"},
            "audience": {"campaign_id"},
            "test": {"campaign_id", "target", "operation_id"},
            "confirm": {"review_id", "operation_id", "confirm"},
        }
        if (
            action not in allowed
            or set(document) - allowed[action]
            or (action != "list" and set(document) != allowed[action])
        ):
            raise HTTPException(400)
        try:
            for key in {
                "campaign_id",
                "review_id",
                "operation_id",
                "target",
                "after",
            } & set(document):
                UUID(document[key])
            if action == "save" and (
                not isinstance(document["revision"], str)
                or not document["revision"].isdigit()
                or any(
                    not isinstance(document[k], str)
                    for k in ("name", "subject", "body")
                )
            ):
                raise ValueError()
            if action == "confirm" and document["confirm"] is not True:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400) from None
        session = presence = None
        if action in {"audience", "test", "confirm"}:
            session, presence = recent_presence(user)
            if (user.claims or {}).get("aal") != "aal2":
                raise HTTPException(403)
        try:
            with self.connect() as c:
                result = c.execute(
                    "select public.administration_campaign(%s,%s,%s,%s,%s::jsonb)",
                    (user.user_id, session, presence, action, json.dumps(document)),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError):
            raise HTTPException(503) from None
        if result.get("error"):
            raise HTTPException(
                404
                if result["error"] == "not_found"
                else 403
                if result["error"] == "reauthentication_required"
                else 409,
                detail={"code": result["error"]},
            )
        return result

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError("administration retention shutdown incomplete")

    def product_access(self, subject):
        if self.restore is not None and not self.restore.ready():
            raise HTTPException(503, detail={"code": "restore_quarantined"})
        try:
            with self.connect() as connection:
                allowed = connection.execute(
                    "select public.administration_product_access(%s)",
                    (str(UUID(subject)),),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError):
            raise HTTPException(503, detail={"code": "access_unavailable"}) from None
        if allowed is not True:
            raise HTTPException(403, detail={"code": "account_restricted"})

    def access(self, user, action, document, kind="access"):
        expected = (
            {"target", "restricted", "reason", "operation_id"}
            if action == "review"
            else {"review_id", "confirm"}
        )
        if kind == "privacy":
            expected = (
                {"task_id", "revision", "reason", "operation_id"}
                if action == "review"
                else {"review_id", "confirm"}
            )
        elif kind == "cancel":
            expected = (
                {"target", "billing_id", "reason", "operation_id"}
                if action == "review"
                else {"review_id", "confirm"}
            )
        elif kind != "access":
            raise HTTPException(404)
        try:
            if action not in {"review", "confirm"} or set(document) != expected:
                raise ValueError()
            if action == "review":
                UUID(document["task_id"] if kind == "privacy" else document["target"])
                UUID(document["operation_id"])
                if document["reason"] not in {"support", "security"}:
                    raise ValueError()
                if kind == "cancel":
                    UUID(document["billing_id"])
                if kind == "access" and type(document["restricted"]) is not bool:
                    raise ValueError()
                if kind == "privacy" and (
                    not isinstance(document["revision"], str)
                    or not document["revision"].isdigit()
                    or len(document["revision"]) > 19
                ):
                    raise ValueError()
            elif document["confirm"] is not True:
                raise ValueError()
            else:
                UUID(document["review_id"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, detail={"code": "invalid"}) from None
        session, presence = recent_presence(user)
        if (user.claims or {}).get("aal") != "aal2":
            raise HTTPException(403, detail={"code": "authenticator_required"})
        try:
            with self.connect() as connection:
                result = connection.execute(
                    {
                        "access": "select public.administration_access(%s,%s,%s,%s,%s::jsonb)",
                        "privacy": "select public.administration_privacy_retry(%s,%s,%s,%s,%s::jsonb)",
                        "cancel": "select public.administration_cancel(%s,%s,%s,%s,%s::jsonb)",
                    }[kind],
                    (user.user_id, session, presence, action, json.dumps(document)),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError):
            raise HTTPException(503, detail={"code": "access_unavailable"}) from None
        if result.get("error"):
            code = result["error"]
            raise HTTPException(
                {
                    "not_found": 404,
                    "invalid": 400,
                    "conflict": 409,
                    "retry_unavailable": 409,
                    "cancellation_unavailable": 409,
                    "reauthentication_required": 403,
                }.get(code, 503),
                detail={"code": code},
            )
        return result

    def call(self, user, action, document=None, *, step_up=False):
        doc = document or {}
        if action not in OPERATIONS or set(doc) - OPERATIONS[action]:
            raise HTTPException(400, detail={"code": "invalid"})
        if action.startswith("membership."):
            expected = OPERATIONS[action]
            try:
                if set(doc) != expected:
                    raise ValueError()
                if action == "membership.review":
                    for key in ("target", "operation_id"):
                        UUID(doc[key])
                    if (
                        doc["role"] not in {"admin", "super_admin"}
                        or doc["status"] not in {"active", "suspended", "revoked"}
                        or doc["reason"] not in {"membership", "support", "security"}
                    ):
                        raise ValueError()
                elif (
                    not isinstance(doc["review_id"], str) or doc["confirm"] is not True
                ):
                    raise ValueError()
                else:
                    UUID(doc["review_id"])
            except (ValueError, TypeError, KeyError, AttributeError):
                raise HTTPException(400, detail={"code": "invalid"}) from None
        session = presence = None
        if step_up:
            session, presence = recent_presence(user)
            if (user.claims or {}).get("aal") != "aal2":
                raise HTTPException(403, detail={"code": "authenticator_required"})
        try:
            with self.connect() as connection:
                result = connection.execute(
                    "select public.administration_call(%s,%s,%s,%s,%s::jsonb)",
                    (
                        str(UUID(user.user_id)),
                        session,
                        presence,
                        action,
                        json.dumps(doc),
                    ),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError) as error:
            logging.getLogger(__name__).warning(
                "Administration operation unavailable: sqlstate=%s",
                getattr(error, "sqlstate", None),
            )
            raise HTTPException(
                503, detail={"code": "administration_unavailable"}
            ) from None
        if result.get("error"):
            code = result["error"]
            raise HTTPException(
                {
                    "not_found": 404,
                    "conflict": 409,
                    "last_super_admin": 409,
                    "invalid": 400,
                    "reauthentication_required": 403,
                    "authenticator_not_ready": 409,
                }.get(code, 503),
                detail={"code": code},
            )
        return result

    def catalog_access(self, actor):
        if type(actor) is not VerifiedActor:
            raise HTTPException(404)
        user = verify_supabase_token(actor._bearer)
        if user.user_id != actor.subject_id:
            raise HTTPException(404)
        return self.call(user, "me")

    def coupon(self, user, action, document):
        session = presence = None
        if action == "save":
            session, presence = recent_presence(user)
            if (user.claims or {}).get("aal") != "aal2":
                raise HTTPException(403)
        try:
            with self.connect() as connection:
                result = connection.execute(
                    "select public.administration_coupon(%s,%s,%s,%s,%s::jsonb)",
                    (user.user_id, session, presence, action, json.dumps(document)),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError):
            raise HTTPException(
                503, detail={"code": "administration_unavailable"}
            ) from None
        if result.get("error"):
            code = result["error"]
            raise HTTPException(
                {
                    "not_found": 404,
                    "invalid": 400,
                    "conflict": 409,
                    "retry_unavailable": 409,
                    "reauthentication_required": 403,
                }.get(code, 503),
                detail={"code": code},
            )
        return result

    def read(self, user, kind, target=None, after=None, search=None):
        try:
            with self.connect() as connection:
                result = connection.execute(
                    "select public.administration_read(%s,%s,%s,%s,%s)",
                    (user.user_id, kind, target, after, search),
                ).fetchone()[0]
        except (DatabaseError, RuntimeError, OSError, ValueError, TypeError):
            raise HTTPException(
                503, detail={"code": "administration_unavailable"}
            ) from None
        if result.get("error"):
            raise HTTPException(404 if result["error"] == "not_found" else 503)
        if kind == "allowances":
            from app.commercial.catalog_contract import V2_METERS

            for item in result.get("items", []):
                spec = V2_METERS.get(item["meter"])
                item["unit"] = spec.unit if spec else None
        return result


def configured(settings):
    if getattr(settings, "ADMIN_CONSOLE_ENABLED", "false") != "true":
        return None
    dsn = settings.ADMIN_CONSOLE_DSN
    retention_dsn = settings.ADMIN_RETENTION_DSN
    dispatch_dsn = settings.ADMIN_DISPATCH_DSN
    service = Administration(
        lambda: connect_executor(dsn, "admin_executor"),
        lambda: connect_executor(retention_dsn, "admin_retention_executor"),
        lambda: connect_executor(dispatch_dsn, "admin_dispatch_executor"),
    )
    with service.dispatch_connect() as connection:
        if connection.execute(
            "select has_function_privilege(current_user,'public.administration_command(text,jsonb)','execute')"
        ).fetchone() != (True,):
            raise RuntimeError("administration dispatch unavailable")
    with service.retention_connect() as connection:
        if connection.execute(
            "select has_function_privilege(current_user,'public.administration_retention(integer)','execute')"
        ).fetchone() != (True,):
            raise RuntimeError("administration retention unavailable")
    import base64

    from app.admin_restore import AdministrationRestore
    from app.privacy_checkpoint import LocalCheckpointStore
    from app.privacy_restore import RestoreJournal

    profile = json.loads(settings.ADMIN_RESTORE_CHECKPOINT)
    key = base64.b64decode(profile["key"], validate=True)
    if "witness_url" in profile:
        from app.privacy_witness import HTTPCheckpointStore

        store = HTTPCheckpointStore(
            profile["witness_url"],
            profile["witness_token"],
            key,
            profile["environment"],
            profile["dataset"],
            local_rehearsal=settings.C15_RUNTIME_LOCAL_REHEARSAL == "true",
        )
    else:
        if settings.C15_RUNTIME_LOCAL_REHEARSAL != "true":
            raise RuntimeError("independent witness interface required")
        store = LocalCheckpointStore(
            profile["checkpoint"],
            profile["witness"],
            key,
            profile["environment"],
            profile["dataset"],
        )
    service.restore = AdministrationRestore(
        lambda: connect_executor(settings.ADMIN_RESTORE_DSN, "admin_restore_executor"),
        RestoreJournal(profile["journal"], {"v1": key}, "v1"),
        store,
        profile["generation"],
        profile["snapshot"],
    )
    service.restore.start()
    from app.admin_registry import validate_admin_schema

    with service.connect() as connection:
        validate_admin_schema(
            connection.execute("select public.administration_schema()").fetchone()[0]
        )
    # Startup proves the actual session principal; credentials never imply activation.
    with service.connect() as connection:
        row = connection.execute(
            "select has_function_privilege(current_user,"
            "'public.administration_call(uuid,uuid,timestamptz,text,jsonb)','execute')"
        ).fetchone()
        if row != (True,):
            raise RuntimeError("administration unavailable")
        ready = connection.execute(
            "select public.administration_call(null,null,null,'_ready','{}')"
        ).fetchone()[0]
        if ready != {"ready": True}:
            raise RuntimeError("administration cutover unavailable")
    return service


def admission(request):
    service = getattr(request.app.state, "administration", None)
    if service is None:
        raise HTTPException(404)
    if len(request.headers.getlist("authorization")) != 1:
        raise HTTPException(401)
    user = get_current_user(request)
    access = service.call(user, "me")
    return service, user, access


@router.get("/me")
async def me(request: Request):
    _, _, result = await run_in_threadpool(admission, request)
    return JSONResponse(result, headers=HEADERS)


@router.get("/{section}")
async def listing(request: Request, section: str):
    service, user, access = await run_in_threadpool(admission, request)
    if section == "campaigns":
        if set(request.query_params) - {"after"}:
            raise HTTPException(400)
        return JSONResponse(
            await run_in_threadpool(
                service.campaign, user, "list", dict(request.query_params)
            ),
            headers=HEADERS,
        )
    if section == "coupons":
        if set(request.query_params) - {"after"}:
            raise HTTPException(400)
        try:
            document = (
                {"after": str(UUID(request.query_params["after"]))}
                if "after" in request.query_params
                else {}
            )
        except ValueError:
            raise HTTPException(400) from None
        return JSONResponse(
            await run_in_threadpool(service.coupon, user, "list", document),
            headers=HEADERS,
        )
    if section == "users":
        if set(request.query_params) - {"after"}:
            raise HTTPException(400)
        after = request.query_params.get("after")
        search = None
        try:
            after = str(UUID(after)) if after else None
            if search is not None and not 1 <= len(search) <= 320:
                raise ValueError()
        except ValueError:
            raise HTTPException(400) from None
        return JSONResponse(
            await run_in_threadpool(service.read, user, "users", None, after, search),
            headers=HEADERS,
        )
    if section not in {"memberships", "audit"} or access["role"] != "super_admin":
        # Database also enforces and durably audits denied privileged operations.
        if section in {"memberships", "audit"}:
            await run_in_threadpool(service.call, user, section)
        raise HTTPException(404)
    if set(request.query_params) - {"after"}:
        raise HTTPException(400)
    doc = dict(request.query_params)
    if "after" in doc:
        try:
            doc["after"] = str(UUID(doc["after"]))
        except ValueError:
            raise HTTPException(400) from None
    result = await run_in_threadpool(service.call, user, section, doc)
    return JSONResponse(result, headers=HEADERS)


@router.post("/users/search")
async def user_search(request: Request):
    service, user, _ = await run_in_threadpool(admission, request)
    if request.url.query:
        raise HTTPException(400)
    if (
        request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 4096), timeout=10))
        if not isinstance(document, dict) or set(document) - {"search", "after"}:
            raise ValueError()
        search = document["search"]
        if not isinstance(search, str) or not 1 <= len(search) <= 320:
            raise ValueError()
        if document.get("after") is not None and not isinstance(document["after"], str):
            raise TypeError()
        after = str(UUID(document["after"])) if document.get("after") else None
    except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    return JSONResponse(
        await run_in_threadpool(service.read, user, "users", None, after, search),
        headers=HEADERS,
    )


@router.get("/users/{target}")
@router.get("/users/{target}/{section}")
async def user_detail(request: Request, target: str, section: str = "user"):
    service, user, _ = await run_in_threadpool(admission, request)
    if (
        section not in {"user", "subscription", "allowances", "privacy"}
        or request.url.query
    ):
        raise HTTPException(404)
    try:
        target = str(UUID(target))
    except ValueError:
        raise HTTPException(404) from None
    result = await run_in_threadpool(service.read, user, section, target)
    return JSONResponse(result, headers=HEADERS)


@router.post("/memberships/{action}")
async def membership(request: Request, action: str):
    service, user, access = await run_in_threadpool(admission, request)
    if access["role"] != "super_admin":
        await run_in_threadpool(service.call, user, "memberships")
        raise HTTPException(404)
    if action not in {"review", "confirm"} or request.url.query:
        raise HTTPException(404)
    if (
        request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415)
    try:
        raw = await asyncio.wait_for(body(request, 4096), timeout=10)
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise TypeError()
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    result = await run_in_threadpool(
        service.call, user, "membership." + action, document, step_up=True
    )
    return JSONResponse(result, headers=HEADERS)


@router.post("/cancellations/{action}")
@router.post("/privacy-retries/{action}")
@router.post("/access/{action}")
async def customer_access(request: Request, action: str):
    service, user, _ = await run_in_threadpool(admission, request)
    if action not in {"review", "confirm"} or request.url.query:
        raise HTTPException(404)
    if (
        request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 4096), timeout=10))
        if not isinstance(document, dict):
            raise TypeError()
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    return JSONResponse(
        await run_in_threadpool(
            service.access,
            user,
            action,
            document,
            "privacy"
            if request.url.path.startswith("/api/admin/privacy-retries/")
            else "cancel"
            if request.url.path.startswith("/api/admin/cancellations/")
            else "access",
        ),
        headers=HEADERS,
    )


@router.post("/campaigns/{action}")
async def campaign_action(request: Request, action: str):
    service, user, _ = await run_in_threadpool(admission, request)
    if request.url.query:
        raise HTTPException(400)
    if (
        request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 32768), timeout=10))
        if not isinstance(document, dict):
            raise TypeError()
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    return JSONResponse(
        await run_in_threadpool(service.campaign, user, action, document),
        headers=HEADERS,
    )


@router.post("/successor/{action}")
async def successor(request: Request, action: str):
    service = getattr(request.app.state, "administration", None)
    if service is None:
        raise HTTPException(404)
    if len(request.headers.getlist("authorization")) != 1:
        raise HTTPException(401)
    user = await run_in_threadpool(get_current_user, request)
    if action == "offer":
        access = await run_in_threadpool(service.call, user, "me")
        if access["role"] != "super_admin":
            raise HTTPException(404)
    if (
        request.url.query
        or request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
    ):
        raise HTTPException(400)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 4096), timeout=10))
        if not isinstance(document, dict):
            raise TypeError()
        result = await run_in_threadpool(service.successor, user, action, document)
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503) from None
    return JSONResponse(result, headers=HEADERS)


@router.get("/cancellations/{operation}")
async def cancellation_status(request: Request, operation: str):
    service, user, _ = await run_in_threadpool(admission, request)
    if request.url.query:
        raise HTTPException(400)
    try:
        UUID(operation)
        result = await run_in_threadpool(service.cancellation_status, user, operation)
    except ValueError:
        raise HTTPException(404) from None
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503) from None
    return JSONResponse(result, headers=HEADERS)


@router.post("/campaign-events")
async def campaign_delivery(request: Request):
    from app.config import settings

    service = getattr(request.app.state, "administration", None)
    if (
        service is None
        or service.campaign_dispatcher is None
        or not settings.ADMIN_CAMPAIGN_WEBHOOK_SECRET
    ):
        raise HTTPException(404)
    if (
        request.url.query
        or request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(400)
    if any(
        len(request.headers.getlist(k)) != 1
        for k in ("svix-id", "svix-timestamp", "svix-signature")
    ):
        raise HTTPException(400)
    try:
        raw = await asyncio.wait_for(body(request, 131072), timeout=10)
        result = await run_in_threadpool(
            service.campaign_dispatcher.delivery,
            raw,
            request.headers,
            settings.ADMIN_CAMPAIGN_WEBHOOK_SECRET,
            "admin_campaigns",
        )
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503) from None
    if not result:
        raise HTTPException(409)
    return JSONResponse({"received": True}, headers=HEADERS)


@router.post("/coupons/{coupon_id}")
async def coupon_save(request: Request, coupon_id: str):
    service, user, access = await run_in_threadpool(admission, request)
    if access["role"] != "super_admin":
        await run_in_threadpool(service.coupon, user, "list", {})
        raise HTTPException(404)
    if request.url.query:
        raise HTTPException(400)
    if (
        request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
    ):
        raise HTTPException(415)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 4096), timeout=10))
        if not isinstance(document, dict) or set(document) != {
            "code",
            "expected",
            "operation_id",
            "source_discount_id",
        }:
            raise ValueError()
        document["id"] = str(UUID(coupon_id))
        if not isinstance(document["operation_id"], str):
            raise TypeError()
        UUID(document["operation_id"])
        if document["source_discount_id"] is not None:
            if not isinstance(document["source_discount_id"], str):
                raise TypeError()
            UUID(document["source_discount_id"])
        if not isinstance(document["code"], str) or not isinstance(
            document["expected"], str
        ):
            raise TypeError()
    except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    return JSONResponse(
        await run_in_threadpool(service.coupon, user, "save", document), headers=HEADERS
    )


@router.post("/metrics")
async def metrics(request: Request):
    service, user, _ = await run_in_threadpool(admission, request)
    if (
        request.url.query
        or request.headers.get("content-type", "").split(";")[0].strip()
        != "application/json"
    ):
        raise HTTPException(400)
    try:
        document = json.loads(await asyncio.wait_for(body(request, 4096), timeout=10))
        if not isinstance(document, dict):
            raise TypeError()
        result = await run_in_threadpool(service.metrics, user, document)
    except (ValueError, TypeError, UnicodeError, asyncio.TimeoutError):
        raise HTTPException(400) from None
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503) from None
    return JSONResponse(result, headers=HEADERS)
