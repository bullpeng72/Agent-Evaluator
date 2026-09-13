"""
agent_evaluator.cli._violations_detail
========================================
SPEC-041: shared implementation of the ``violations`` / ``blocked-detail``
subcommands, mounted symmetrically under both ``agent-eval claude`` and
``agent-eval opencode`` so the two hosts give the same experience.

  * ``agent-eval <host> violations "<query>" [--detail]`` — wraps
    :func:`agent_evaluator.storage.sqlite_backend.search_violations`.
  * ``agent-eval <host> blocked-detail <task_id>`` — wraps
    :func:`agent_evaluator.storage.sqlite_backend.show_violation` + host-transcript
    fallback (:mod:`agent_evaluator.integrations._blocked_detail`).

The only per-host difference is the default batch-report DB path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_G = "\033[32m"
_R = "\033[0m"
_D = "\033[2m"
_RD = "\033[31m"

_PROJECT_ROOT_MARKERS = (".git", "pyproject.toml", "setup.py", "setup.cfg")

_HOST_DEFAULTS = {
    "claude": ("results/claude_code_live_guardrail", "claude_code_sessions.db"),
    "opencode": ("results/opencode_live_guardrail", "opencode_sessions.db"),
}


def _project_root(start: Path | None = None) -> Path:
    try:
        cur = (start or Path.cwd()).resolve()
    except (OSError, RuntimeError):
        return Path(".").resolve()
    for cand in (cur, *cur.parents):
        if any((cand / m).exists() for m in _PROJECT_ROOT_MARKERS):
            return cand
    return cur


def resolve_db_path(host: str, explicit: str | None = None) -> str:
    """Return the batch-report SQLite path for *host* (``"claude"`` / ``"opencode"``).

    Precedence: ``explicit`` (``--db``) → ``$AGENT_EVALUATOR_OUTPUT_DIR`` → the host
    default dir, all anchored at the project root when relative.
    """
    if explicit:
        return explicit
    default_dir, filename = _HOST_DEFAULTS.get(host, _HOST_DEFAULTS["claude"])
    output_dir = os.environ.get("AGENT_EVALUATOR_OUTPUT_DIR", default_dir)
    rel = Path(output_dir) / filename
    return str(rel if rel.is_absolute() else _project_root() / rel)


def _no_db_msg(db_path: str, host: str) -> str:
    return (
        f"{_RD}No batch-report database at {db_path}{_R}\n"
        f"{_D}It is created when the first LiveGuardrail-monitored {host} session ends. "
        f"Pass --db <path> if it lives elsewhere.{_R}"
    )


def run_violations(
    host: str,
    query: str | None,
    *,
    detail: bool = False,
    db: str | None = None,
    limit: int = 10,
    since: str | None = None,
    gate: str | None = None,
) -> int:
    """SPEC-045 REQ-6: ``query``가 없으면(생략) 키워드 없는 브라우징 모드로 동작한다.

    ``query``가 주어지면 기존 ``search_violations()`` 경로(FTS5 키워드 검색)를 그대로
    쓴다 — 이 분기는 100% 하위호환(기존 호출 방식 무변경).
    """
    from agent_evaluator.integrations.violation_search_mcp import format_results
    from agent_evaluator.storage.sqlite_backend import list_violations, search_violations

    db_path = resolve_db_path(host, db)
    if not os.path.exists(db_path):
        print(_no_db_msg(db_path, host))
        return 1
    try:
        if query:
            results = search_violations(
                db_path, query, limit=limit, include_blocked=True, detail=detail
            )
            text = format_results(results)
        else:
            results = list_violations(
                db_path, limit=limit, include_blocked=True, detail=detail,
                since=since, gate=gate,
            )
            text = format_results(
                results,
                header=(
                    "Recent violation/blocked-attempt history (most recent first, "
                    "no keyword filter):"
                ),
                empty_message=(
                    "No violation/blocked-attempt history recorded yet — nothing to list."
                ),
            )
    except Exception as exc:  # noqa: BLE001 - surface any read failure verbatim
        print(f"{_RD}Could not read {db_path}: {exc}{_R}")
        return 1
    print(text)
    return 0


def run_blocked_detail(
    host: str, task_id: str, *, db: str | None = None, as_json: bool = False
) -> int:
    from agent_evaluator.integrations._blocked_detail import (
        format_blocked_detail,
        recover_blocked_commands,
    )
    from agent_evaluator.storage.sqlite_backend import show_violation

    db_path = resolve_db_path(host, db)
    sv: dict = {"task_id": task_id, "found": False, "blocked": []}
    if os.path.exists(db_path):
        try:
            sv = show_violation(db_path, task_id)
        except Exception as exc:  # noqa: BLE001
            print(f"{_RD}Could not read {db_path}: {exc}{_R}")
            return 1

    if as_json:
        recovered = None
        need = any(not (b.get("arg_excerpt") or "").strip() for b in sv.get("blocked") or [])
        if need or not sv.get("found"):
            recovered = recover_blocked_commands(task_id, host=host)
        print(json.dumps({"db_path": db_path, "detail": sv, "recovered": recovered}, indent=2))
        return 0 if (sv.get("found") or (recovered and recovered.get("items"))) else 1

    print(format_blocked_detail(sv, host=host))
    if not sv.get("found"):
        _rec = recover_blocked_commands(task_id, host=host)
        return 0 if _rec.get("items") else 1
    return 0


def add_violation_detail_subcommands(host_sub, host: str) -> None:
    """Register ``violations`` + ``blocked-detail`` on a host's subparser action.

    ``host_sub`` is the ``add_subparsers()`` result for ``agent-eval <host>``;
    ``host`` is ``"claude"`` or ``"opencode"``.
    """
    v = host_sub.add_parser(
        "violations",
        help=(
            "List/search past blocked/observed Gate B/E violations "
            "(like the search_violations MCP)"
        ),
        description=(
            "Full-text search the LiveGuardrail batch-report DB for past Gate B/E "
            "violations. --detail also prints the captured command excerpt for blocked rows. "
            "Omit the query entirely to browse the most recent history instead (SPEC-045 "
            "REQ-6) — no keyword needed; use --since/--gate to narrow."
        ),
        epilog=(
            f'{_G}agent-eval {host} violations{_R}'
            f'                          # browse recent, no keyword\n'
            f'{_G}agent-eval {host} violations --since 2026-09-08{_R}\n'
            f'{_G}agent-eval {host} violations --gate B --detail{_R}\n'
            f'{_G}agent-eval {host} violations "rm -rf"{_R}\n'
            f'{_G}agent-eval {host} violations "dangerous tool parameters" --detail{_R}\n'
        ),
    )
    v.add_argument(
        "query", nargs="?", default=None,
        help=(
            "free-text query (keywords; command text also matches now). "
            "Omit to browse recent history."
        ),
    )
    v.add_argument("--detail", action="store_true", help="show the captured command excerpt")
    v.add_argument("--db", default=None, help="override the batch-report DB path")
    v.add_argument("--limit", type=int, default=10, help="max rows per sub-query (default 10)")
    v.add_argument(
        "--since", default=None,
        help="ISO-8601 timestamp lower bound, browse mode only (e.g. 2026-09-08)",
    )
    v.add_argument(
        "--gate", choices=["B", "E"], default=None,
        help="filter to this gate, browse mode only (applies to blocked rows)",
    )

    b = host_sub.add_parser(
        "blocked-detail",
        help="Show the exact blocked command(s) for one session (task_id)",
        description=(
            "Given a task_id (== the session id, e.g. from `violations` output), print "
            "every blocked tool call with its captured argument excerpt. Falls back to the "
            "host session transcript when the excerpt was not captured."
        ),
        epilog=f"{_G}agent-eval {host} blocked-detail 16325c72-3030-4cee-a8c6-7b66f048bb81{_R}\n",
    )
    b.add_argument("task_id", help="session / task id from a `violations` result")
    b.add_argument("--json", dest="as_json", action="store_true", help="machine-readable output")
    b.add_argument("--db", default=None, help="override the batch-report DB path")


def dispatch(host: str, cmd: str | None, args) -> int | None:
    """Return an exit code if *cmd* is one of ours, else ``None`` (not handled)."""
    if cmd == "violations":
        return run_violations(
            host, args.query, detail=args.detail, db=args.db, limit=args.limit,
            since=args.since, gate=args.gate,
        )
    if cmd == "blocked-detail":
        return run_blocked_detail(host, args.task_id, db=args.db, as_json=args.as_json)
    return None
