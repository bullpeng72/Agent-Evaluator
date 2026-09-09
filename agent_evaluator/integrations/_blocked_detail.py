"""
agent_evaluator.integrations._blocked_detail
==============================================
SPEC-041: shared helpers behind ``search_violations`` → *blocked-attempt detail*.

The batch-report DB stores a short PII-redacted ``arg_excerpt`` for every blocked
tool call (``blocked_attempt_capture``, on by default). When that excerpt is
missing — a session recorded before capture was enabled, or capture turned off —
this module recovers the offending command *best-effort* from the host's own
session transcript, keyed by ``task_id`` (which is the Claude Code / OpenCode
session id).

Two hosts, one shape:
  * Claude Code — ``~/.claude/projects/<slug>/<task_id>.jsonl`` (assistant
    ``tool_use`` block + the following ``tool_result``).
  * OpenCode    — ``~/.local/share/opencode/opencode.db`` ``part`` table
    (``type == "tool"`` rows whose ``state`` errored with a guardrail marker).

Everything here is best-effort and never raises — a missing / rotated / unreadable
transcript just yields an empty list.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

# Deny text produced by a LiveGuardrail block *starts with* one of these (verdict.reason
# from gates/live_guardrail.py). Matching the prefix — not just "contains" — avoids
# treating an ordinary command whose *output* quotes the phrase (e.g. a grep of the
# codebase) as a block.
_BLOCK_REASON_PREFIXES: tuple[str, ...] = (
    "dangerous tool parameters",
    "tool_authorization:",
    "scope violation",
    "deadlock:",
    "loop_detection:",
    "privilege_escalation:",
    "tool_chain_attack:",
    "protected write",
    "team scope claim",
    "protected branch",
    "human_only:",
)
# For the OpenCode path the plugin wraps the reason: "[agent-evaluator] blocked by Gate B: …"
_BLOCK_MARKERS: tuple[str, ...] = _BLOCK_REASON_PREFIXES + (
    "blocked by LiveGuardrail",
    "blocked by Gate",
)


def _looks_like_block(text: str) -> bool:
    t = (text or "").lstrip().lstrip("→").lstrip()
    return (
        t.startswith(_BLOCK_REASON_PREFIXES)
        or "blocked by Gate" in t[:60]
        or ("blocked by LiveGuardrail" in t[:60])
    )


_COMMAND_KEYS: tuple[str, ...] = (
    "command",
    "cmd",
    "script",
    "filePath",
    "file_path",
    "path",
    "pattern",
    "query",
    "url",
)


def _excerpt_from_input(tool_input: Any, limit: int = 400) -> str:
    """Pick the most command-like field from a tool-call input dict (or stringify it)."""
    if isinstance(tool_input, str):
        text = tool_input
    elif isinstance(tool_input, dict):
        text = ""
        for k in _COMMAND_KEYS:
            v = tool_input.get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
        if not text:
            try:
                text = json.dumps(tool_input, ensure_ascii=False, sort_keys=True, default=str)
            except Exception:
                text = str(tool_input)
    else:
        text = str(tool_input)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# --------------------------------------------------------------------------- Claude


def _claude_projects_root() -> Path:
    return Path(os.path.expanduser("~/.claude/projects"))


def find_claude_transcript(task_id: str) -> Path | None:
    """Locate ``<task_id>.jsonl`` under any project slug (the session may have run
    in a different cwd than the current one)."""
    root = _claude_projects_root()
    if not root.is_dir():
        return None
    try:
        for proj in root.iterdir():
            cand = proj / f"{task_id}.jsonl"
            if cand.is_file():
                return cand
    except OSError:
        return None
    return None


def _recover_from_claude(task_id: str) -> list[dict[str, Any]]:
    path = find_claude_transcript(task_id)
    if path is None:
        return []
    tool_use: dict[str, tuple[str, Any, str, str]] = {}
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                content = (obj.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use":
                        tool_use[str(c.get("id"))] = (
                            c.get("name") or "?",
                            c.get("input"),
                            (c.get("input") or {}).get("description", "")
                            if isinstance(c.get("input"), dict)
                            else "",
                            obj.get("timestamp", ""),
                        )
                    elif c.get("type") == "tool_result":
                        # A guardrail block is a tool_result with is_error=True whose text
                        # *starts with* a known verdict.reason prefix. Plain output that
                        # merely quotes the phrase (a codebase grep) has is_error=False and
                        # usually doesn't start with it — both filters must pass.
                        if not c.get("is_error"):
                            continue
                        body = c.get("content")
                        if isinstance(body, list):
                            txt = " ".join(p.get("text", "") for p in body if isinstance(p, dict))
                        else:
                            txt = (
                                body
                                if isinstance(body, str)
                                else json.dumps(body, ensure_ascii=False, default=str)
                            )
                        if not _looks_like_block(txt):
                            continue
                        nm, inp, desc, ts = tool_use.get(
                            str(c.get("tool_use_id")), ("?", None, "", "")
                        )
                        out.append(
                            {
                                "tool_name": nm,
                                "command": _excerpt_from_input(inp),
                                "description": desc,
                                "deny": " ".join((txt or "").split())[:300],
                                "timestamp": ts,
                            }
                        )
    except OSError:
        return []
    return out


# ------------------------------------------------------------------------- OpenCode


def _opencode_db_path() -> Path | None:
    for cand in (
        Path(os.path.expanduser("~/.local/share/opencode/opencode.db")),
        Path(os.path.expanduser("~/Library/Application Support/opencode/opencode.db")),
    ):
        if cand.is_file():
            return cand
    return None


def _recover_from_opencode(task_id: str) -> list[dict[str, Any]]:
    db = _opencode_db_path()
    if db is None:
        return []
    out: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = conn.execute(
                "SELECT data FROM part WHERE session_id = ? ORDER BY time_created", (task_id,)
            ).fetchall()
        except sqlite3.Error:
            return []
        for (data,) in rows:
            try:
                d = json.loads(data)
            except Exception:
                continue
            if d.get("type") != "tool":
                continue
            state = d.get("state") or {}
            err = ""
            for k in ("error", "message", "output"):
                v = state.get(k)
                if isinstance(v, str):
                    err += " " + v
            # OpenCode plugin throws `[agent-evaluator] blocked by Gate X: <reason>` — the
            # tool part records that as an errored state. Require both the error status and
            # a guardrail-shaped message.
            if state.get("status") != "error":
                continue
            if "agent-evaluator] blocked by" not in err and not _looks_like_block(err):
                continue
            out.append(
                {
                    "tool_name": d.get("tool") or "?",
                    "command": _excerpt_from_input(state.get("input")),
                    "description": (state.get("input") or {}).get("description", "")
                    if isinstance(state.get("input"), dict)
                    else "",
                    "deny": " ".join(err.split())[:300],
                    "timestamp": "",
                }
            )
    finally:
        conn.close()
    return out


# --------------------------------------------------------------------------- public


def recover_blocked_commands(task_id: str, host: str = "auto") -> dict[str, Any]:
    """Best-effort recovery of blocked command text from a host transcript.

    Args:
        task_id: session id (== the guardrail DB ``task_id``).
        host: ``"claude"``, ``"opencode"``, or ``"auto"`` (try both, first hit wins).

    Returns:
        ``{"source": "claude-transcript" | "opencode-db" | None, "items": [...]}``
        where each item is ``{tool_name, command, description, deny, timestamp}``.
        ``items`` empty and ``source`` ``None`` when nothing was recoverable.
    """
    order = (
        ["claude"]
        if host == "claude"
        else ["opencode"]
        if host == "opencode"
        else ["claude", "opencode"]
    )
    for h in order:
        try:
            items = (
                _recover_from_claude(task_id) if h == "claude" else _recover_from_opencode(task_id)
            )
        except Exception:
            items = []
        if items:
            return {
                "source": "claude-transcript" if h == "claude" else "opencode-db",
                "items": items,
            }
    return {"source": None, "items": []}


def format_blocked_detail(sv: dict[str, Any], *, host: str = "auto") -> str:
    """Render :func:`agent_evaluator.storage.sqlite_backend.show_violation` output as text.

    Falls back to transcript recovery for any blocked row whose ``arg_excerpt`` is empty.
    """
    task_id = sv.get("task_id", "?")
    if not sv.get("found"):
        return (
            f"No blocked-attempt history for task_id={task_id} in this database. "
            f"(Wrong DB path, or the session has not ended / was never guardrail-monitored.)"
        )
    lines = [
        f"Blocked-attempt detail — task_id={task_id} "
        f"(task_type={sv.get('task_type')}, at {sv.get('timestamp')}):"
    ]
    blocked = sv.get("blocked") or []
    need_fallback = any(not (b.get("arg_excerpt") or "").strip() for b in blocked)
    recovered = (
        recover_blocked_commands(task_id, host=host)
        if (need_fallback or not blocked)
        else {"source": None, "items": []}
    )
    for i, b in enumerate(blocked, 1):
        lines.append(
            f"{i}. tool={b.get('tool_name')}  gate={b.get('gate')}\n   reason : {b.get('reason')}"
        )
        excerpt = (b.get("arg_excerpt") or "").strip()
        if excerpt:
            lines.append(f"   command: {excerpt}")
        elif i - 1 < len(recovered["items"]):
            r = recovered["items"][i - 1]
            lines.append(f"   command: {r['command']}   [recovered from {recovered['source']}]")
        else:
            lines.append(
                "   command: (not captured — enable blocked_attempt_capture; "
                "no host transcript found for recovery)"
            )
    if not blocked and recovered["items"]:
        lines.append(f"(no DB rows; recovered from {recovered['source']}:)")
        for i, r in enumerate(recovered["items"], 1):
            lines.append(f"{i}. tool={r['tool_name']}  command: {r['command']}")
    if sv.get("observed_summary"):
        lines.append(f"observed (executed) violations: {sv['observed_summary']}")
    return "\n".join(lines)
