"""
agent-eval diagnose — Gate 하락 원인진단(RCA) CLI.

Media/Harness_Method Chapter 31의 3단계 절차(감지→원인귀속→교차확인)를 자동화한
``agent_evaluator.rca.diagnose()``를 감싸는 얇은 터미널 출력 레이어다 — 새 판정
로직은 없다.

이 명령은 CI 게이트가 아니다(``agent-eval gate``와 다르다) — 사람이 읽을 진단
리포트를 출력할 뿐 pass/fail을 판정하지 않는다(HOTL 원칙, Chapter 2). 종료 코드는
파일을 정상적으로 읽고 진단을 냈으면 항상 0이다 — 감지된 Gate가 있어도 실패로
취급하지 않는다.

종료 코드:
    0 — 진단 정상 완료(감지된 Gate가 있어도 0)
    1 — 결과 파일을 읽을 수 없음
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.rca import diagnose

_COLOR = _supports_color()
G  = "\033[32m" if _COLOR else ""
Y  = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B  = "\033[1m"  if _COLOR else ""
R  = "\033[0m"  if _COLOR else ""
D  = "\033[2m"  if _COLOR else ""
C  = "\033[36m" if _COLOR else ""


def _load_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _fmt_score(score: float | None) -> str:
    return f"{score:.4f}" if score is not None else "n/a"


def _fmt_delta_value(v: float | None) -> str:
    return f"{v:.4f}" if v is not None else "n/a"


def _print_finding(finding: dict[str, Any]) -> None:
    gate = finding["gate"]
    cur = _fmt_score(finding["current_score"])
    base = finding["baseline_score"]
    base_str = f" (baseline {_fmt_score(base)})" if base is not None else ""
    print(f"\n{B}Gate {gate}{R} — score {cur}{base_str}")

    deltas = finding["top_detail_deltas"]
    if not deltas:
        print(f"  {D}(no comparable detail metrics){R}")
    else:
        print(f"  {D}Detail metric changes (step 2 — attribution, largest absolute first):{R}")
        for d in deltas[:5]:
            delta = d["delta"]
            if delta is None:
                _sign_str = f"{D}(no baseline){R}"
            else:
                _color = RD if delta < 0 else G
                _sign_str = f"{_color}{delta:+.4f}{R}"
            _base_str = _fmt_delta_value(d["baseline"])
            _cur_str = _fmt_delta_value(d["current"])
            print(f"    {d['field']:<32} {_base_str} -> {_cur_str}  {_sign_str}")

    refs = finding["cross_references"]
    if refs:
        print(f"  {D}Related violation history (step 3 — cross-reference):{R}")
        for r in refs[:5]:
            snippet = (r.get("summary") or r.get("text") or str(r))[:80]
            print(f"    - {snippet}")

    mast = finding.get("mast_candidates") or []
    if mast:
        print(f"  {D}For reference — MAST candidate failure modes "
              f"(Cemri et al. NeurIPS 2025, not a conclusion):{R}")
        for m in mast:
            print(f"    [{m['code']}] {m['name']} — {m['description']}")
            print(f"      {D}→ {m['remediation']}{R}")


def cmd_diagnose(args: argparse.Namespace) -> int:
    current = _load_json(args.result_file)
    if current is None:
        print(f"{RD}❌ Could not read result file: {args.result_file}{R}", file=sys.stderr)
        return 1

    baseline = None
    if args.baseline:
        baseline = _load_json(args.baseline)
        if baseline is None:
            print(f"{RD}❌ Could not read baseline file: {args.baseline}{R}", file=sys.stderr)
            return 1

    violation_db_path: str | Path | None = args.violation_db
    if violation_db_path and not Path(violation_db_path).is_file():
        print(
            f"{Y}⚠ violation-db file not found — skipping step 3 (cross-reference): "
            f"{violation_db_path}{R}",
            file=sys.stderr,
        )
        violation_db_path = None

    result = diagnose(
        current, baseline,
        regression_threshold=args.regression_threshold / 100.0,
        violation_db_path=violation_db_path,
        with_experiment_metadata=bool(getattr(args, "show_diff", False)),
        repo_path=getattr(args, "repo_path", "."),
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"{B}Gate RCA Diagnosis{R} — {args.result_file}")
    print(f"{D}Detection mode: {result['detection_mode']}{R}")

    if not result["detected_gates"]:
        print(f"\n{G}✅ No Gate detected — no Gate is in a regression or fail/warn state.{R}")
        return 0

    print(f"\n{Y}Detected Gates: {', '.join(result['detected_gates'])}{R}")

    if result["multi_gate_note"]:
        print(f"\n{Y}⚠ {result['multi_gate_note']}{R}")

    if result["sla_shared_cause_check"]:
        check = result["sla_shared_cause_check"]
        _color = Y if check["likely_shared_cause"] else D
        print(f"\n{_color}[SLA shared-cause check] {check['note']}{R}")
        print(
            f"  {D}sla_breach_rate={check['sla_breach_rate']} "
            f"sla_window_penalty={check['sla_window_penalty']} "
            f"sla_budget_penalty={check['sla_budget_penalty']}{R}"
        )

    for finding in result["findings"]:
        _print_finding(finding)

    exp_meta = result.get("experiment_metadata")
    if exp_meta:
        print(
            f"\n{B}Actual code changes "
            f"(git {exp_meta['from_commit']}..{exp_meta['to_commit']}):{R}"
        )
        print(f"  {D}{exp_meta['diff_stat_summary']}{R}")
        if exp_meta["changed_files"]:
            print(f"  {D}Changed files:{R}")
            for f in exp_meta["changed_files"][:10]:
                print(f"    - {f}")
            if len(exp_meta["changed_files"]) > 10:
                print(f"    {D}... and {len(exp_meta['changed_files']) - 10} more{R}")
        if exp_meta["commits_between"]:
            print(f"  {D}Related commits:{R}")
            for c in exp_meta["commits_between"][:10]:
                print(f"    {c['sha']} {D}{c['date']} {c['author']}{R} — {c['subject']}")
    elif getattr(args, "show_diff", False):
        print(
            f"\n{D}(--show-diff was given but no commit information was found — "
            f"make sure both reports have lineage.git_commit, and that --repo-path "
            f"is a git repository containing both commits.){R}"
        )

    print(
        f"\n{D}This report presents candidate causes and evidence only — the final "
        f"judgment is yours (HOTL, Chapter 2).{R}"
    )
    return 0
