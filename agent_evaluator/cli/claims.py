"""
agent-eval claims — `.aoo/claims.jsonl` 팀 스코프 클레임 관리 (SPEC-038).

지금까지 `TeamConcurrencyConfig`/`append_claim()`/`load_active_claims()`/
`audit_claims()`(SPEC-032/034/036/037)는 파이썬 코드로 직접 호출하는 것이
유일한 사용법이었다 — 클레임을 걸거나 해제하려면 매번 짧은 스크립트를 작성해야
했다. 이 서브커맨드는 새 로직을 추가하지 않고 이 함수들을 얇게 감싸 터미널
한 줄로 같은 작업을 하게 한다.

서브커맨드:
    add               — 새 클레임을 연다 (append_claim, status="active"). 겹치는 활성
                        클레임이 있으면 non-blocking 경고를 낸다(차단은 여전히 audit의 몫).
    list              — 활성 클레임을 표로 보여준다 (load_active_claims). --developer로 필터.
    release           — 클레임을 해제한다 (append_claim, status="released")
    audit             — TTL 초과·스코프 겹침 위반을 점검한다 (audit_claims, CI용)
    enable-live-check — TeamConcurrencyConfig를 기존 guardrail 설정 JSON에 병합한다
                        (docs/AUTOPILOT_IMPROVEMENTS.md §5 — 지금까지 수동 JSON 편집만
                        가능해서 이 기능이 실전에서 켜진 적이 없었다).
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.gates.team_concurrency import (
    append_claim,
    audit_claims,
    check_scope_claim,
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
            "--developer was not given and git config user.name could not be "
            "resolved. Specify --developer NAME explicitly."
        ))
        return 1

    claim_id = args.claim_id or f"c-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()

    # docs/AUTOPILOT_IMPROVEMENTS.md §5 — add() 자체는 겹침을 안 막는다(그건
    # audit()의 몫, 설계 그대로 유지). 다만 지금까지는 add 시점에 최소한의
    # 경고조차 없어 CI에서 audit을 따로 돌리기 전까지 겹침을 몰랐다 — 여기서
    # 겹침이 있으면 non-blocking 경고만 낸다(exit 0 그대로, 열기 자체는 막지
    # 않는다).
    overlaps = check_scope_claim(args.scope, claims_path)
    if overlaps:
        for o in overlaps:
            print(
                _warn(
                    f"scope overlaps an existing active claim: "
                    f"{o.get('claim_id')} ({o.get('developer')}) — "
                    f"{o.get('scope')}. Coordinate before proceeding, or "
                    f"'agent-eval claims audit' will flag this later."
                )
            )

    append_claim(
        claims_path, claim_id=claim_id, developer=developer,
        scope=args.scope, started_at=started_at, status="active",
    )
    print(_ok(f"Claim opened: claim_id={claim_id}  developer={developer}"))
    for s in args.scope:
        print(f"  {D}scope:{R} {s}")
    print(f"{D}To release: agent-eval claims release {claim_id}{R}")
    return 0


def _cmd_claims_list(args: argparse.Namespace) -> int:
    claims_path = Path(args.claims_path)
    claims = load_active_claims(claims_path)
    developer = getattr(args, "developer", None)
    if developer:
        claims = [c for c in claims if c.get("developer") == developer]

    if not claims:
        label = f" for developer={developer}" if developer else ""
        print(f"{D}No active claims{label} ({claims_path}){R}")
        return 0

    now = datetime.now(timezone.utc)
    print(f"{B}Active claims — {claims_path}{R}")
    for c in claims:
        age_str = ""
        started_at = c.get("started_at")
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                age_hours = (now - started).total_seconds() / 3600
                age_str = f"  {D}({age_hours:.1f}h elapsed){R}"
            except ValueError:
                age_str = f"  {D}(could not parse started_at: {started_at}){R}"
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
            f"claim_id={args.claim_id} is not in the active claims list — "
            f"it may already be released, or the ID may not exist."
        ))
        if not args.force:
            print(f"{D}To record the release event anyway, add --force.{R}")
            return 1

    released_at = datetime.now(timezone.utc).isoformat()
    append_claim(
        claims_path, claim_id=args.claim_id, status="released",
        released_at=released_at,
    )
    print(_ok(f"Claim released: claim_id={args.claim_id}"))
    return 0


def _cmd_claims_audit(args: argparse.Namespace) -> int:
    violations = audit_claims(args.claims_path, ttl_hours=args.ttl_hours)
    if not violations:
        print(_ok(f"No claims log violations ({args.claims_path})"))
        return 0

    print(_err(f"Found {len(violations)} claims log violation(s) ({args.claims_path})"))
    for v in violations:
        if v["type"] == "ttl_exceeded":
            print(
                f"  {RD}TTL exceeded{R}  claim_id={v['claim_id']}  "
                f"developer={v['developer']}  elapsed={v['age_hours']}h  "
                f"(threshold {args.ttl_hours}h)"
            )
        elif v["type"] == "overlapping_claims":
            print(
                f"  {RD}Overlapping scope{R}  {v['claim_id_a']}({v['developer_a']}) "
                f"↔ {v['claim_id_b']}({v['developer_b']})  scope={v['scope']}"
            )
    return 1


def _cmd_claims_enable_live_check(args: argparse.Namespace) -> int:
    """docs/AUTOPILOT_IMPROVEMENTS.md §5 — ``TeamConcurrencyConfig``를 켜는

    CLI/마법사가 없어, 실시간 클레임 겹침 검사는 지금까지 guardrail 설정
    JSON을 손으로 편집해야만 켤 수 있었다(Appendix M 발견 3 — 실제로 이
    기능이 한 번도 켜진 적 없는 프로젝트가 그 결과였다). 새 판정 로직이
    아니다 — ``live_guardrail_stdio.py``가 이미 읽는
    ``{"team_concurrency": {...}}`` 키를 기존 설정 파일에 안전하게
    병합할 뿐이다(``deep_merge_defaults`` — 사용자가 이미 넣은 키는 절대
    덮어쓰지 않는다, ``claude upgrade``/``opencode upgrade``와 같은 패턴).
    """
    from agent_evaluator.cli._integration_health import deep_merge_defaults

    config_path = Path(args.config)
    if not config_path.is_file():
        print(_err(
            f"{config_path} not found — run 'agent-eval claude install' or "
            f"'agent-eval opencode install' first, then point --config at the "
            f"resulting guardrail_config.json / agent-evaluator.config.json"
        ))
        return 1

    try:
        user_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(_err(f"{config_path} is not valid JSON: {exc}"))
        return 1
    if not isinstance(user_config, dict):
        print(_err(f"{config_path} does not contain a JSON object at the top level"))
        return 1

    defaults = {"team_concurrency": {"owner": args.owner, "claims_path": args.claims_path}}
    merged, added = deep_merge_defaults(user_config, defaults)
    if not added:
        print(
            f"{D}{config_path} already has a 'team_concurrency' key — nothing to add "
            f"(edit it directly to change settings).{R}"
        )
        return 0

    config_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(_ok(f"Enabled real-time claim-overlap checking in {config_path}"))
    for path in added:
        print(f"  {D}+ {path}{R}")
    print(
        f"{D}Restart the live session (OpenCode plugin process, or the next Claude "
        f"Code hook call) for this to take effect.{R}"
    )
    return 0


# ---------------------------------------------------------------------------
# argparse 서브파서 빌더 (main.py에서 호출)
# ---------------------------------------------------------------------------

def build_claims_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """claims 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "claims",
        help="Manage .aoo/claims.jsonl team scope claims "
             "(add/list/release/audit/enable-live-check)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Add, list, release, and audit team scope claims used by\n"
            "TeamConcurrencyConfig (LiveGuardrail) to detect overlapping work, and\n"
            "turn on real-time claim-overlap checking in an existing guardrail config.\n"
            "\n"
            "This is a thin wrapper around append_claim()/load_active_claims()/\n"
            "audit_claims() — no new logic, just a terminal-friendly interface.\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval claims add agent_evaluator/gates/configs.py --developer alex\n"
            "  agent-eval claims add src/ --developer auto\n"
            "  agent-eval claims list --developer alex\n"
            "  agent-eval claims release c-a1b2c3d4\n"
            "  agent-eval claims audit --ttl-hours 8\n"
            "  agent-eval claims enable-live-check --config "
            ".opencode/plugin/agent-evaluator.config.json\n"
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
    list_p.add_argument(
        "--developer", default=None, metavar="NAME",
        help="Only show this developer's active claims",
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

    elc_p = claims_sub.add_parser(
        "enable-live-check",
        help="Merge TeamConcurrencyConfig into an existing guardrail config JSON "
             "(real-time claim-overlap checking — until now, manual-JSON-only)",
    )
    elc_p.add_argument(
        "--config", required=True, metavar="PATH",
        help="guardrail_config.json (Claude Code) or agent-evaluator.config.json "
             "(OpenCode) to merge into",
    )
    elc_p.add_argument(
        "--owner", default="auto",
        help="TeamConcurrencyConfig.owner — 'auto' resolves via git config user.name "
             "at guardrail-startup time (default: auto)",
    )
    elc_p.add_argument(
        "--claims-path", default=".aoo/claims.jsonl", dest="claims_path", metavar="PATH",
        help="TeamConcurrencyConfig.claims_path (default: .aoo/claims.jsonl)",
    )


def cmd_claims(args: argparse.Namespace) -> int:
    """claims 서브커맨드 핸들러 — claims_command에 따라 분기한다."""
    handlers = {
        "add": _cmd_claims_add,
        "list": _cmd_claims_list,
        "release": _cmd_claims_release,
        "audit": _cmd_claims_audit,
        "enable-live-check": _cmd_claims_enable_live_check,
    }
    claims_command = getattr(args, "claims_command", None)
    handler = handlers.get(claims_command) if claims_command is not None else None
    if handler is None:
        print(_err(
            "Specify a claims subcommand: add | list | release | audit | enable-live-check"
        ))
        print(f"{D}For details: agent-eval claims --help{R}")
        return 1
    return handler(args)
