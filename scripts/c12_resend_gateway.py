"""Future acceptance only: expose this loopback gateway, never the backend."""

import asyncio
import http.client
import time

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from scripts.c12_webhook_gateway import read_body

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
PATH = "/api/billing/email/events"
UPSTREAM_PORT = 8122
REQUEST_LIMIT = 12
attempts = 0
deadline = time.monotonic() + 15 * 60


def forward(raw, headers):
    connection = http.client.HTTPConnection("127.0.0.1", UPSTREAM_PORT, timeout=15)
    try:
        connection.request("POST", PATH, body=raw, headers=headers)
        response = connection.getresponse()
        return (
            response.status
            if response.status in (200, 400, 409, 413, 415, 503)
            else 502
        )
    except (OSError, http.client.HTTPException):
        return 503
    finally:
        connection.close()


@app.post(PATH)
async def callback(request: Request):
    global attempts
    if request.url.query or request.scope.get("raw_path") != PATH.encode():
        raise HTTPException(404)
    if time.monotonic() >= deadline:
        raise HTTPException(503)
    attempts += 1
    if attempts > REQUEST_LIMIT:
        raise HTTPException(503)
    headers = {}
    for key in ("svix-id", "svix-timestamp", "svix-signature", "content-type"):
        if len(request.headers.getlist(key)) != 1:
            raise HTTPException(400)
        headers[key] = request.headers[key]
    if request.headers.get("content-encoding", "identity") != "identity":
        raise HTTPException(415)
    try:
        raw = await asyncio.wait_for(read_body(request), timeout=10)
        status = await run_in_threadpool(forward, raw, headers)
    except asyncio.TimeoutError:
        status = 503
    return JSONResponse(
        {"received": status == 200},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )
