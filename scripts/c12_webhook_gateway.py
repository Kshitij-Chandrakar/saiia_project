"""Temporary path-only gateway. Run on loopback; never tunnel the main backend."""

import asyncio
import http.client
import re

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
PATH = "/api/billing/webhook"
LIMIT = 131072
UPSTREAM_PORT = 8000


def forward(raw: bytes, signature: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", UPSTREAM_PORT, timeout=30)
    try:
        connection.request(
            "POST",
            PATH,
            body=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
        )
        response = connection.getresponse()
        return response.status if response.status in {200, 400, 403, 413, 503} else 502
    except (OSError, http.client.HTTPException):
        return 503
    finally:
        connection.close()


async def read_body(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > LIMIT:
            raise HTTPException(413)
    return bytes(raw)


@app.post(PATH)
async def webhook(request: Request):
    if request.url.query:
        raise HTTPException(404)
    signature = request.headers.get("x-razorpay-signature", "")
    if not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise HTTPException(400)
    try:
        raw = await asyncio.wait_for(read_body(request), timeout=10)
    except asyncio.TimeoutError as error:
        raise HTTPException(408) from error
    status = await run_in_threadpool(forward, raw, signature)
    return JSONResponse(
        {"received": True}
        if status == 200
        else {"detail": "webhook_rejected_or_unavailable"},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )
