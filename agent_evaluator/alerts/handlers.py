"""
알림 핸들러 — Slack, HTTP Webhook, Email.
"""
from __future__ import annotations

import json
import smtplib
import urllib.request
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import AlertEvent


class SlackHandler:
    """Slack Incoming Webhook 핸들러.

    Args:
        webhook_url: Slack Incoming Webhook URL.
        channel: Slack 채널 이름 (선택, webhook 설정에서 결정됨).
        username: 봇 이름. Default "Agent Evaluator".

    Example::
        handler = SlackHandler(webhook_url=os.getenv("SLACK_WEBHOOK"))
    """

    def __init__(self, webhook_url: str, channel: str = "", username: str = "Agent Evaluator") -> None:
        if not webhook_url:
            raise ValueError("webhook_url must not be empty")
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username

    def send(self, event: "AlertEvent") -> None:
        severity_emoji = "\U0001f6a8" if event.severity == "critical" else "\u26a0\ufe0f"
        payload: Dict[str, Any] = {
            "username": self.username,
            "text": f"{severity_emoji} *[{event.severity.upper()}]* {event.rule_name}",
            "attachments": [
                {
                    "color": "#ff0000" if event.severity == "critical" else "#ffaa00",
                    "text": event.message,
                    "footer": "Agent Evaluator",
                    "ts": int(__import__("time").time()),
                }
            ],
        }
        if self.channel:
            payload["channel"] = self.channel

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass


class WebhookHandler:
    """범용 HTTP Webhook 핸들러.

    Args:
        url: Webhook URL.
        headers: 추가 HTTP 헤더 (선택).
        method: HTTP 메서드. Default "POST".
    """

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, method: str = "POST") -> None:
        if not url:
            raise ValueError("url must not be empty")
        self.url = url
        self.headers = headers or {}
        self.method = method

    def send(self, event: "AlertEvent") -> None:
        payload = event.to_dict()
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(self.headers)
        req = urllib.request.Request(
            self.url,
            data=data,
            headers=all_headers,
            method=self.method,
        )
        with urllib.request.urlopen(req, timeout=10):
            pass


class EmailHandler:
    """이메일 알림 핸들러 (SMTP).

    Args:
        smtp_host: SMTP 서버 호스트.
        smtp_port: SMTP 포트. Default 587.
        username: SMTP 로그인 사용자명.
        password: SMTP 비밀번호.
        from_addr: 발신자 이메일.
        to_addrs: 수신자 이메일 목록.
    """

    def __init__(self, smtp_host: str, smtp_port: int = 587,
                 username: str = "", password: str = "",
                 from_addr: str = "", to_addrs: Optional[List[str]] = None) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs or []

    def send(self, event: "AlertEvent") -> None:
        severity_emoji = "\U0001f6a8" if event.severity == "critical" else "\u26a0\ufe0f"
        subject = f"{severity_emoji} [{event.severity.upper()}] Agent Evaluator: {event.rule_name}"
        msg = MIMEText(event.message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.ehlo()
            server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
