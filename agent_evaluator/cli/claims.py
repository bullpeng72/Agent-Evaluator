"""
agent-eval claims — `.aoo/claims.jsonl` 팀 스코프 클레임 관리 (SPEC-038).

지금까지 `TeamConcurrencyConfig`/`append_claim()`/`load_active_claims()`/
`audit_claims()`(SPEC-032/034/036/037)는 파이썬 코드로 직접 호출하는 것이
유일한 사용법이었다 — 클레임을 걸거나 해제하려면 매번 짧은 스크립트를 작성해야
했다. 이 서브커맨드는 새 로직을 추가하지 않고 이 함수들을 얇게 감싸 터미널
한 줄로 같은 작업을 하게 한다.

서브커맨드:
    add      — 새 클레임을 연다 (append_claim, status="active")
    list     — 활성 클레임을 표로 보여준다 (load_active_claims)
    release  — 클레임을 해제한다 (append_claim, status="released")
    audit    — TTL 초과·스코프 겹침 위반을 점검한다 (audit_claims, CI용)
"""
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.gates.team_concurrency import (
    append_claim,
    audit_claims,
    load_active_claims,
    resolve_owner,
)

_COLOR = _supports_color()

G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""


def _ok(msg: str) -> str:
    return f"{G}✅ {msg}{R}"


def _warn(msg: str) -> str:
    return f"{Y}⚠️  {msg}{R}"


def _err(msg: str) -> str:
    return f"{RD}❌ {msg}{R}"


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------

def _cmd_claims_add(args: argparse.Namespace) -> int:
    claims_path = Path(args.claims_path)
    claims_path.parent.mkdir(parents=True, exist_ok=True)

    # "auto"는 명시적으로 --developer auto를 준 경우와, --developer 자체를
    # 생략한 경우(기본값 None) 둘 다에서 같은 git config user.name 조회로
    # 이어져야 한다 — resolve_owner()는 "auto" 리터럴만 특수 처리하므로,
    # 여기서 None을 "auto"로 먼저 치환해 단일 경로로 합친다.
    developer = resolve_owner(args.developer or "auto")
    if not developer:
        print(_err(
            "--developer가 지정되지 않았고 git config user.name도 조회할 수 "
            "없습니다. --developer NAME을 명시하세요."
        ))
        return 1

    claim_id = args.claim_id or f"c-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()

    append_claim(
        claims_path, claim_id=claim_id, developer=developer,
        scope=args.scope, started_at=started_at, status="active",
    )
    print(_ok(f"클레임 개설: claim_id={claim_id}  developer={developer}"))
    for s in args.scope:
        print(f"  {D}scope:{R} {s}")
    print(f"{D}해제하려면: agent-eval claims release {claim_id}{R}")
    return 0


def _cmd_claims_list(args: argparse.Namespace) -> int:
    claims_path = Path(args.claims_path)
    claims = load_active_claims(claims_path)

    if not claims:
        print(f"{D}활성 클레임 없음 ({claims_path}){R}")
        return 0

    now = datetime.now(timezone.utc)
    print(f"{B}활성 클레임 — {claims_path}{R}")
    for c in claims:
        age_str = ""
        started_at = c.get("started_at")
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                age_hours = (now - started).total_seconds() / 3600
                age_str = f"  {D}({age_hours:.1f}h 경과){R}"
            except ValueError:
                age_str = f"  {D}(started_at 파싱 불가: {started_at}){R}"
        scope = ", ".join(c.get("scope", []))
        print(
            f"  {G}{c.get('claim_id')}{R}  {c.get('developer')}  "
            f"[{scope}]{age_str}"
        )
    return 0


def _cmd_claims_release(args: argparse.Namespace) -> int:
    claims_path = Path(args.claims_path)
    active = {c.get("claim_id") for c in load_active_claims(claims_path)}
    if args.claim_id not in active:
        print(_warn(
            f"claim_id={args.claim_id}가 활성 클레임 목록에 없습니다 — "
            f"이미 해제됐거나 존재하지 않는 ID일 수 있습니다."
        ))
        if not args.force:
            print(f"{D}그래도 해제 이벤트를 기록하려면 --force를 추가하세요.{R}")
            return 1

    released_at = datetime.now(timezone.utc).isoformat()
    append_claim(
        claims_path, claim_id=args.claim_id, status="released",
        released_at=released_at,
    )
    print(_ok(f"클레임 해제: claim_id={args.claim_id}"))
    return 0


def _cmd_claims_audit(args: argparse.Namespace) -> int:
    violations = audit_claims(args.claims_path, ttl_hours=args.ttl_hours)
    if not violations:
        print(_ok(f"클레임 로그 위반 없음 ({args.claims_path})"))
        return 0

    print(_err(f"클레임 로그 위반 {len(violations)}건 발견 ({args.claims_path})"))
    for v in violations:
        if v["type"] == "ttl_exceeded":
            print(
                f"  {RD}TTL 초과{R}  claim_id={v['claim_id']}  "
                f"developer={v['developer']}  경과={v['age_hours']}h  "
                f"(기준 {args.ttl_hours}h)"
            )
        elif v["type"] == "overlapping_claims":
            print(
                f"  {RD}스코프 겹침{R}  {v['claim_id_a']}({v['developer_a']}) "
                f"↔ {v['claim_id_b']}({v['developer_b']})  scope={v['scope']}"
            )
    return 1


# ---------------------------------------------------------------------------
# argparse 서브파서 빌더 (main.py에서 호출)
# ---------------------------------------------------------------------------

def build_claims_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """claims 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "claims",
        help="Manage .aoo/claims.jsonl team scope claims (add/list/release/audit)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Add, list, release, and audit team scope claims used by\n"
            "TeamConcurrencyConfig (LiveGuardrail) to detect overlapping work.\n"
            "\n"
            "This is a thin wrapper around append_claim()/load_active_claims()/\n"
            "audit_claims() — no new logic, just a terminal-friendly interface.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval claims add agent_evaluator/gates/configs.py --developer 수아\n"
            "  agent-eval claims add src/ --developer auto\n"
            "  agent-eval claims list\n"
            "  agent-eval claims release c-a1b2c3d4\n"
            "  agent-eval claims audit --ttl-hours 8\n"
        ),
    )
    claims_sub = p.add_subparsers(dest="claims_command")

    add_p = claims_sub.add_parser(
        "add", help="Open a new claim over one or more paths",
    )
    add_p.add_argument("scope", nargs="+", help="Paths/directories this claim covers")
    add_p.add_argument(
        "--developer", "-d", default=None,
        help="Developer name to record. If omitted, resolves via 'git config user.name'.",
    )
    add_p.add_argument(
        "--claims-path", default=".aoo/claims.jsonl", metavar="PATH",
        help="Claims log path (default: .aoo/claims.jsonl)",
    )
    add_p.add_argument(
        "--claim-id", default=None, metavar="ID",
        help="Explicit claim ID (default: auto-generated 'c-<8 hex chars>')",
    )

    list_p = claims_sub.add_parser(
        "list", help="List currently active claims",
    )
    list_p.add_argument(
        "--claims-path", default=".aoo/claims.jsonl", metavar="PATH",
        help="Claims log path (default: .aoo/claims.jsonl)",
    )

    release_p = claims_sub.add_parser(
        "release", help="Release an active claim by ID",
    )
    release_p.add_argument("claim_id", help="claim_id to release")
    release_p.add_argument(
        "--claims-path", default=".aoo/claims.jsonl", metavar="PATH",
        help="Claims log path (default: .aoo/claims.jsonl)",
    )
    release_p.add_argument(
        "--force", action="store_true",
        help="Record the release event even if the claim_id isn't currently active",
    )

    audit_p = claims_sub.add_parser(
        "audit",
        help="Check for TTL-exceeded or overlapping claims (CI-friendly, exit 1 on violation)",
    )
    audit_p.add_argument(
        "--claims-path", default=".aoo/claims.jsonl", metavar="PATH",
        help="Claims log path (default: .aoo/claims.jsonl)",
    )
    audit_p.add_argument(
        "--ttl-hours", type=float, default=8.0, dest="ttl_hours", metavar="HOURS",
        help="Flag active claims older than this as violations (default: 8.0)",
    )


def cmd_claims(args: argparse.Namespace) -> int:
    """claims 서브커맨드 핸들러 — claims_command에 따라 분기한다."""
    handlers = {
        "add": _cmd_claims_add,
        "list": _cmd_claims_list,
        "release": _cmd_claims_release,
        "audit": _cmd_claims_audit,
    }
    claims_command = getattr(args, "claims_command", None)
    handler = handlers.get(claims_command) if claims_command is not None else None
    if handler is None:
        print(_err("claims 서브커맨드를 지정하세요: add | list | release | audit"))
        print(f"{D}자세한 정보: agent-eval claims --help{R}")
        return 1
    return handler(args)
