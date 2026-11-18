
import hmac
import json
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response


GATEWAY_API_KEY = os.environ.get("GATEWAY_API_KEY")
OLLAMA_URL = "http://127.0.0.1:11434"

if not GATEWAY_API_KEY:
    raise RuntimeError("GATEWAY_API_KEY environment variable is required.")

app = FastAPI(
    title="DocuFlow Ollama Gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

ALLOWED_PATH = "/api/chat"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post(ALLOWED_PATH)
async def proxy_chat(
    request: Request,
    authorization: str | None = Header(default=None),
):
    expected = f"Bearer {GATEWAY_API_KEY}"

    if not authorization or not hmac.compare_digest(
        authorization, expected
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")

    raw_body = await request.body()

    if len(raw_body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Request too large")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request body")

    if payload.get("stream") is True:
        raise HTTPException(
            status_code=400,
            detail="Streaming requests are not supported",
        )

    if payload.get("model") != "qwen2.5:7b":
        raise HTTPException(
            status_code=400,
            detail="Unsupported model",
        )

    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            upstream = await client.post(
                f"{OLLAMA_URL}{ALLOWED_PATH}",
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama timed out")
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to local Ollama",
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type="application/json",
    )
