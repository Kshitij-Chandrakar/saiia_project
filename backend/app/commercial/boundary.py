"""Fail closed before routing/body parsing; unknown future routes are denied too."""

import re

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from app.config import settings

# This is a reviewed ingress allowlist, not an entitlement list. The answer
# handler still requires verified ownership and default-closed authority.
_STATIC_INGRESS = frozenset(
    {
        ("POST", "/generate/"),
        ("GET", "/api/auth/me"),
        ("GET", "/api/catalog"),
        ("GET", "/api/account/subscription"),
        ("POST", "/api/billing/checkout"),
        ("POST", "/api/billing/start"),
        ("POST", "/api/billing/verify"),
        ("POST", "/api/billing/cancel"),
        ("POST", "/api/billing/webhook"),
        ("GET", "/api/billing/status"),
        ("GET", "/api/billing/current"),
        ("GET", "/api/billing/availability"),
        ("GET", "/api/commercial/admin/me"),
    }
)


def handoff_ingress(method, path):
    return (settings.HOSTED_AUDIO_ENABLED and method == 'POST' and path in
            ('/api/auth/desktop-handoff', '/api/auth/desktop-handoff/exchange'))
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def billing_admin_ingress(method, path):
    return (
        settings.BILLING_ADMIN_ENABLED == 'true'
        and (method == 'GET' and path == '/api/admin/billing/access'
             or method in ('GET', 'POST') and re.fullmatch('/api/admin/billing/' + _UUID, path))
        or settings.BILLING_NOTIFICATIONS_ENABLED == 'true'
        and method == 'POST' and path == '/api/billing/email/events'
    )
_DRAFT_INGRESS = {
    ("POST", "/api/admin/catalog/plans/{plan_id}/drafts"),
    ("GET", "/api/admin/catalog/drafts/{draft_id}"),
    ("PATCH", "/api/admin/catalog/drafts/{draft_id}"),
    ("POST", "/api/admin/catalog/drafts/{draft_id}/preview"),
}
_LIFECYCLE_INGRESS = {
    ("POST", "/api/admin/catalog/drafts/{draft_id}/publication-reviews"),
    ("GET", "/api/admin/catalog/publication-reviews/{review_id}"),
    ("POST", "/api/admin/catalog/drafts/{draft_id}/publish"),
    ("POST", "/api/admin/catalog/drafts/{draft_id}/replace"),
    ("POST", "/api/admin/catalog/offers/{offer_id}/retire"),
    ("GET", "/api/admin/catalog/offers/{offer_id}"),
    ("GET", "/api/admin/catalog/operations/{request_id}"),
}
_SUBSCRIPTION_INGRESS = {
    ('POST', '/transcribe/'),
    ('GET', '/api/interview-sessions'),
    ('GET', '/api/interview-sessions/{session_id}'),
    ('GET', '/api/interview-sessions/{session_id}/transcript-entries'),
    ('DELETE', '/api/interview-sessions/{session_id}/transcript-entries'),
    ('GET', '/api/interview-sessions/{session_id}/transcript/download'),
    ('GET', '/api/interview-sessions/{session_id}/notes'),
    ('GET', '/api/interview-sessions/{session_id}/ask-ai/messages'),
    ('POST', '/api/interview-sessions/{session_id}/notes/generate'),
    ('POST', '/api/interview-sessions/{session_id}/ask-ai'),
    ('POST', '/api/screen/analyze-context'),
    ('GET', '/api/screen/sessions/{session_id}/results'),
    ('GET', '/api/resumes'),
    ('POST', '/api/resumes'),
    ('POST', '/api/resumes/active-set'),
    ('GET', '/api/resumes/current'),
    ('GET', '/api/resumes/review-candidate'),
    ('GET', '/api/resumes/{resume_id}/status'),
    ('DELETE', '/api/resumes/{resume_id}'),
    ('POST', '/api/resumes/{resume_id}/extract'),
    ('POST', '/api/resumes/{resume_id}/confirm'),
    ('POST', '/api/resumes/{resume_id}/rebuild-index'),
    ('POST', '/generate/stream'),
    ('POST', '/api/auth/profile/bootstrap'),
    ('GET', '/api/interview-sessions/{session_id}/my-answers'),
    ('POST', '/api/interview-sessions/{session_id}/my-answers'),
    ('GET', '/api/interview-sessions/{session_id}/answer-sources'),
    ('GET', '/api/interview-sessions/{session_id}/transcript-entries/{transcript_id}/diagram'),
    ('POST', '/api/interview-sessions/{session_id}/transcript-entries/{transcript_id}/diagram'),
    ('POST', '/api/interview-sessions/{session_id}/transcript-entries/{transcript_id}/diagram/generate'),
    ('POST', '/api/interview-sessions/{session_id}/transcript-entries/{transcript_id}/diagram/retry'),
    ('POST', '/api/interview-sessions/{session_id}/transcript-entries/{transcript_id}/diagram/cancel'),
}
HOSTED_INGRESS = _STATIC_INGRESS | _DRAFT_INGRESS | _LIFECYCLE_INGRESS | _SUBSCRIPTION_INGRESS


def draft_ingress(method, path):
    templates = _DRAFT_INGRESS | (
        _LIFECYCLE_INGRESS if settings.CATALOG_LIFECYCLE_ENABLED == "true" else set()
    )
    return any(
        method == verb
        and re.fullmatch(re.sub(r"\{[a-z_]+\}", lambda _: _UUID, template), path)
        for verb, template in templates
    )


def subscription_ingress(method: str, path: str) -> bool:
    if path == '/api/account/audio/capabilities':
        return settings.SUBSCRIPTIONS_ENABLED == 'true' and settings.HOSTED_AUDIO_ENABLED and method == 'GET'
    return settings.SUBSCRIPTIONS_ENABLED == 'true' and any(
        method == verb and re.fullmatch(re.sub(r'\{[a-z_]+\}',lambda _: _UUID,template),path)
        for verb,template in _SUBSCRIPTION_INGRESS
    )


class CommercialBoundaryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        original_send = send
        if scope['type'] == 'http' and (scope['path'].lower().startswith('/api/admin/billing') or scope['path'].lower().startswith('/api/billing/email/')):
            raw = scope.get('raw_path', scope['path'].encode()).split(b'?', 1)[0]
            if raw != scope['path'].encode() or scope.get('query_string') or not billing_admin_ingress(scope['method'],scope['path']):
                await JSONResponse({'detail':{'code':'billing_path_unavailable'}},status_code=404,headers={'Cache-Control':'no-store'})(scope,receive,send)
                return
        if (scope['type'] == 'websocket' and settings.HOSTED_AUDIO_ENABLED
                and settings.SUBSCRIPTIONS_ENABLED == 'true'
                and scope['path'] == '/api/account/audio/stream'
                and scope.get('raw_path', b'/api/account/audio/stream') == b'/api/account/audio/stream'
                and not scope.get('query_string')):
            await self.app(scope, receive, send)
            return
        if settings.SUBSCRIPTIONS_ENABLED == 'true' and scope['type'] == 'websocket':
            # These legacy WebSockets have no reviewed lease envelope. No local
            # fallback may turn the new account mode into an unmetered bypass.
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if settings.SUBSCRIPTIONS_ENABLED == 'true' and scope['type'] == 'http':
            # Registered feature gates complement each handler's owned-resource
            # checks. No quota is invented for approved unlimited features.
            feature = None
            path=scope['path']
            if path.startswith(('/api/resume/','/api/job-context/','/api/audio/system','/generate/refinement/')) or path in ('/api/resume','/api/job-context') or scope['method']=='POST' and re.fullmatch(r'/api/interview-sessions/'+_UUID+r'/transcript-entries',path):
                await JSONResponse({'detail':{'code':'subscription_execution_unavailable'}},status_code=503,headers={'Cache-Control':'no-store'})(scope,receive,send)
                return
            if path.startswith('/api/job-contexts'):
                feature='job_context.extract' if path=='/api/job-contexts/extract' else 'job_context.manage'
            if path.startswith('/classify'):
                feature='answers.generate'
            if scope['method']=='GET' and path.startswith('/api/interview-sessions') and not path.endswith('/my-answers') and '/diagram' not in path and not path.endswith('/answer-sources'):
                feature='transcripts.export' if path.endswith('/transcript/download') else 'sessions.history'
            elif scope['method']=='POST' and re.fullmatch(r'/api/interview-sessions/'+_UUID+r'/notes/generate',path):
                feature='notes.generate'
            elif scope['method']=='POST' and re.fullmatch(r'/api/interview-sessions/'+_UUID+r'/ask-ai',path):
                feature='session.ask_ai'
            if feature:
                from starlette.concurrency import run_in_threadpool
                from starlette.exceptions import HTTPException
                from starlette.requests import Request

                from app.commercial.catalog_store import CatalogStoreError
                from app.commercial.subscription_execution import execution_service
                from app.commercial.subscription_screen import safe_error
                try:
                    service,actor=execution_service(Request(scope))
                    await run_in_threadpool(service.require_feature,actor,feature)
                except (HTTPException,CatalogStoreError) as error:
                    error=safe_error(error) if isinstance(error,CatalogStoreError) else error
                    await JSONResponse({'detail':error.detail},status_code=error.status_code,headers={'Cache-Control':'no-store'})(scope,receive,send)
                    return
            if scope['path'].startswith(('/generate','/transcribe')):
                async def execution_send(message):
                    if message['type'] == 'http.response.start':
                        headers = MutableHeaders(scope=message)
                        headers['Cache-Control'] = 'no-store'
                        headers['Pragma'] = 'no-cache'
                        headers.add_vary_header('Authorization')
                    await original_send(message)
                send = execution_send
            if not subscription_ingress(scope['method'],scope['path']) and (scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE') and scope['path'].startswith(
                ('/transcribe', '/api/screen/', '/api/resume', '/api/audio/system', '/api/question-detect')
            ) or (scope['method'] == 'POST' and re.fullmatch(
                r'/api/interview-sessions/'+_UUID+r'/(notes/generate|ask-ai)',scope['path']
            ))):
                await JSONResponse({'detail': {'code': 'subscription_execution_unavailable'}},
                                   status_code=503, headers={'Cache-Control':'no-store'})(scope,receive,send)
                return
        if scope['type'] == 'http' and scope['path'].lower().startswith('/api/account/'):
            async def account_send(message):
                if message['type'] == 'http.response.start':
                    headers = MutableHeaders(scope=message)
                    headers['Cache-Control'] = 'no-store'
                    headers['Pragma'] = 'no-cache'
                    headers.add_vary_header('Authorization')
                await original_send(message)
            send = account_send
            raw = scope.get('raw_path', scope['path'].encode()).split(b'?', 1)[0]
            reviewed = {'/api/account/subscription'}
            if settings.HOSTED_AUDIO_ENABLED: reviewed.add('/api/account/audio/capabilities')
            if scope['method'] != 'GET' or scope['path'] not in reviewed or raw != scope['path'].encode():
                await JSONResponse({'detail': {'code': 'commercial_path_unreviewed'}}, status_code=404)(scope, receive, send)
                return
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/api/catalog":
            raw = scope.get("raw_path", scope["path"].encode()).split(b"?", 1)[0]
            if scope["method"] != "GET" or scope["path"] != "/api/catalog" or raw != b"/api/catalog":
                await JSONResponse({"detail":{"code":"commercial_path_unreviewed"}}, status_code=404,headers={"Cache-Control":"no-store"})(scope,receive,send)
                return
        if scope["type"] == "http" and scope["path"].lower().startswith(
            ("/api/commercial/", "/api/admin/catalog", "/api/admin/billing", "/api/interview-sessions", "/api/auth/", '/api/screen/', '/api/resumes', '/api/job-contexts')
        ):

            async def private_send(message):
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
                    headers.add_vary_header("Authorization")
                await original_send(message)

            send = private_send
            # Do not let slash redirects/encoded aliases become another probe
            # ingress. Query fields never participate in identity or authority.
            probe = "/api/commercial/admin/me"
            raw = scope.get("raw_path", scope["path"].encode()).split(b"?", 1)[0]
            if (
                scope["path"].rstrip("/") == probe
                and scope["path"] != probe
                or scope["path"] == probe
                and raw != probe.encode()
            ):
                status = 503 if settings.HOSTED_COMMERCIAL_MODE else 404
                await JSONResponse(
                    {"detail": {"code": "commercial_path_unreviewed"}},
                    status_code=status,
                )(scope, receive, send)
                return
            if scope["path"].startswith("/api/admin/catalog") and (
                raw != scope["path"].encode()
                or not any(
                    draft_ingress(verb, scope["path"])
                    for verb in ("GET", "POST", "PATCH")
                )
            ):
                status = 503 if settings.HOSTED_COMMERCIAL_MODE else 404
                await JSONResponse(
                    {"detail": {"code": "commercial_path_unreviewed"}},
                    status_code=status,
                )(scope, receive, send)
                return
        if settings.HOSTED_COMMERCIAL_MODE:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            if (
                scope["type"] == "http"
                and (scope["method"], scope["path"]) not in _STATIC_INGRESS
                and not handoff_ingress(scope['method'], scope['path'])
                and not draft_ingress(scope["method"], scope["path"])
                and not subscription_ingress(scope["method"], scope["path"])
                and not billing_admin_ingress(scope["method"], scope["path"])
            ):
                await JSONResponse(
                    {"detail": {"code": "commercial_path_unreviewed"}}, status_code=503
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)
