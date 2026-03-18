"""
Webhook proxy — POST /api/webhook/test

Forwards a test payload to the configured Slack (or generic) webhook URL.
The browser cannot call external webhook URLs directly due to CORS, so this
server-side proxy route receives the request and performs the outbound POST.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/webhook")


@router.post("/test")
async def test_webhook(request: Request) -> Dict[str, Any]:
    """Proxy a test POST to the provided webhook URL.

    Body (JSON):
        url     (str)  — target webhook URL
        payload (dict) — JSON payload to forward

    Returns:
        {"ok": True, "status": <http-status-code>}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    url: str = body.get("url", "")
    payload: Any = body.get("payload", {})

    if not url or not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="유효한 https:// Webhook URL이 필요합니다.")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Webhook responded with {e.code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"ok": True, "status": status}
