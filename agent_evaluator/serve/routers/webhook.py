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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


class WebhookTestBody(BaseModel):
    url: str
    payload: Dict[str, Any] = {}


@router.post("/test", summary="웹훅 테스트")
async def test_webhook(body: WebhookTestBody) -> Dict[str, Any]:
    """Proxy a test POST to the provided webhook URL.

    Returns:
        {"ok": True, "status": <http-status-code>}
    """
    url = body.url
    payload: Any = body.payload

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
