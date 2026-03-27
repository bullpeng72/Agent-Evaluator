"""
agent-eval gate — CI/CD 품질 게이팅 명령어.

평가 결과 JSON을 로드해 임계값 기준으로 통과/실패를 판정하고
종료 코드를 반환한다.

종료 코드:
    0 — 모든 기준 통과
    1 — 임계값 기준 미달
    2 — 이전 버전 대비 회귀 감지 (--fail-on-regression 사용 시)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# ANSI 색상
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return "ANSICON" in os.environ or "WT_SESSION" in os.environ
    return True


_COLOR = _supports_color()

G  = "\033[32m" if _COLOR else ""   # green
Y  = "\033[33m" if _COLOR else ""   # yellow
RD = "\033[31m" if _COLOR else ""   # red
B  = "\033[1m"  if _COLOR else ""   # bold
R  = "\033[0m"  if _COLOR else ""   # reset
D  = "\033[2m"  if _COLOR else ""   # dim
C  = "\033[36m" if _COLOR else ""   # cyan


# ---------------------------------------------------------------------------
# 메트릭 파싱
# ---------------------------------------------------------------------------

def _load_metrics(data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """결과 JSON dict에서 게이팅에 필요한 지표값을 추출한다.

    Args:
        data: 평가 결과 JSON을 파싱한 dict.

    Returns:
        {
            "tcr":              float | None,   # 0-100 %
            "accuracy":         float | None,   # 0-100 %
            "p95_latency":      float | None,   # seconds
            "hallucination":    float | None,   # 0-100 %
            "llm_judge_overall": float | None,  # 0-5 점
        }
    """
    metrics: Dict[str, Optional[float]] = {
        "tcr": None,
        "accuracy": None,
        "p95_latency": None,
        "hallucination": None,
        "llm_judge_overall": None,
    }

    # -- TCR --
    accuracy_metrics = data.get("accuracy_metrics", {})
    tcr_block = accuracy_metrics.get("tcr", {})
    tcr_raw = tcr_block.get("tcr")
    if tcr_raw is None:
        # fallback: success_rate
        tcr_raw = tcr_block.get("success_rate")
    if tcr_raw is not None:
        try:
            val = float(tcr_raw)
            # 내부 0-1 스케일이면 ×100
            metrics["tcr"] = val * 100.0 if val <= 1.0 else val
        except (TypeError, ValueError):
            pass

    # -- 정확도 --
    acc_block = accuracy_metrics.get("accuracy_scores", {})
    acc_raw = acc_block.get("overall_accuracy")
    if acc_raw is not None:
        try:
            val = float(acc_raw)
            metrics["accuracy"] = val * 100.0 if val <= 1.0 else val
        except (TypeError, ValueError):
            pass

    # -- 환각 탐지율 --
    hall_block = accuracy_metrics.get("hallucination", {})
    hall_raw = hall_block.get("overall_rate")
    if hall_raw is not None:
        try:
            val = float(hall_raw)
            metrics["hallucination"] = val * 100.0 if val <= 1.0 else val
        except (TypeError, ValueError):
            pass

    # -- P95 지연시간 --
    efficiency_metrics = data.get("efficiency_metrics", {})
    latency_block = efficiency_metrics.get("latency", {})
    p95_raw = latency_block.get("p95")
    if p95_raw is not None:
        try:
            metrics["p95_latency"] = float(p95_raw)
        except (TypeError, ValueError):
            pass

    # -- LLM Judge 종합 점수 (tasks 배열 평균) --
    tasks = data.get("tasks", [])
    scores: List[float] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        llm_judge = task.get("llm_judge")
        if not isinstance(llm_judge, dict):
            continue
        score_block = llm_judge.get("scores", {})
        overall = score_block.get("overall")
        if overall is not None:
            try:
                scores.append(float(overall))
            except (TypeError, ValueError):
                pass
    if scores:
        metrics["llm_judge_overall"] = sum(scores) / len(scores)

    return metrics


# ---------------------------------------------------------------------------
# 기준선 관리
# ---------------------------------------------------------------------------

def _default_baseline_path(result_file: Path) -> Path:
    """결과 파일과 같은 디렉토리의 baseline.json 경로를 반환한다."""
    return result_file.parent / "baseline.json"


def _load_baseline(path: Path) -> Optional[Dict[str, Any]]:
    """기준선 파일을 로드한다. 없으면 None 반환."""
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _save_baseline(path: Path, metrics: Dict[str, Optional[float]]) -> None:
    """현재 메트릭을 기준선 파일로 저장한다."""
    payload: Dict[str, Any] = {k: v for k, v in metrics.items()}
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 게이팅 판정
# ---------------------------------------------------------------------------

# (name, label, threshold_attr, direction, unit, format_str)
# direction: "min" → 현재값 ≥ 임계값, "max" → 현재값 ≤ 임계값
_GATE_DEFS: List[Tuple[str, str, str, str, str]] = [
    ("tcr",             "TCR",              "tcr",           "min",  "%"),
    ("accuracy",        "정확도",           "accuracy",       "min",  "%"),
    ("p95_latency",     "P95 지연시간",      "p95_latency",    "max",  "s"),
    ("hallucination",   "환각 탐지율",       "hallucination",  "max",  "%"),
    ("llm_judge_overall", "LLM Judge (종합)", "llm_judge",    "min",  "/5"),
]


def _check_gates(
    metrics: Dict[str, Optional[float]],
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    """각 지표별 게이팅 결과를 반환한다.

    Returns:
        각 항목 dict:
            name, label, current, threshold, direction, unit,
            active (임계값 지정 여부), passed (bool)
    """
    results: List[Dict[str, Any]] = []

    for metric_key, label, arg_attr, direction, unit in _GATE_DEFS:
        threshold = getattr(args, arg_attr, None)
        current = metrics.get(metric_key)

        if threshold is None:
            # 임계값 미지정 — 활성 게이트 아님
            results.append({
                "name": metric_key,
                "label": label,
                "current": current,
                "threshold": None,
                "direction": direction,
                "unit": unit,
                "active": False,
                "passed": True,
            })
            continue

        if current is None:
            # 지표값 없음 → 실패 처리
            results.append({
                "name": metric_key,
                "label": label,
                "current": None,
                "threshold": threshold,
                "direction": direction,
                "unit": unit,
                "active": True,
                "passed": False,
            })
            continue

        if direction == "min":
            passed = current >= threshold
        else:  # "max"
            passed = current <= threshold

        results.append({
            "name": metric_key,
            "label": label,
            "current": current,
            "threshold": threshold,
            "direction": direction,
            "unit": unit,
            "active": True,
            "passed": passed,
        })

    return results


def _check_regression(
    metrics: Dict[str, Optional[float]],
    baseline: Dict[str, Any],
    tolerance_pct: float,
) -> List[Dict[str, Any]]:
    """기준선 대비 회귀를 감지한다.

    Args:
        metrics: 현재 메트릭 dict.
        baseline: 기준선 파일 내용.
        tolerance_pct: 허용 회귀 비율(%).

    Returns:
        회귀가 감지된 항목 목록 (각 dict: name, label, current, baseline_val, pct_change).
    """
    regressions: List[Dict[str, Any]] = []
    tol = tolerance_pct / 100.0

    for metric_key, label, _, direction, unit in _GATE_DEFS:
        current = metrics.get(metric_key)
        baseline_val = baseline.get(metric_key)

        if current is None or baseline_val is None:
            continue
        if not isinstance(baseline_val, (int, float)):
            continue

        base = float(baseline_val)
        if base == 0.0:
            continue  # 분모 0 guard

        if direction == "min":
            # 값이 낮아지면 회귀: current < baseline * (1 - tol)
            regressed = current < base * (1.0 - tol)
        else:
            # 지연시간 등: current > baseline * (1 + tol) 이면 회귀
            regressed = current > base * (1.0 + tol)

        if regressed:
            pct_change = (current - base) / base * 100.0
            regressions.append({
                "name": metric_key,
                "label": label,
                "current": current,
                "baseline_val": base,
                "pct_change": pct_change,
                "unit": unit,
            })

    return regressions


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

_SEP = "━" * 48
_SEP_THIN = "─" * 40


def _fmt_value(val: Optional[float], unit: str) -> str:
    """지표값을 사람이 읽기 좋은 형태로 포맷한다."""
    if val is None:
        return f"{D}N/A{R}"
    if unit == "%":
        return f"{val:.1f}%"
    if unit == "s":
        return f"{val:.2f}s"
    if unit == "/5":
        return f"{val:.2f}/5"
    return f"{val:.2f}"


def _fmt_threshold(threshold: Optional[float], direction: str, unit: str) -> str:
    """임계값 문자열 포맷."""
    if threshold is None:
        return f"{D}—{R}"
    sym = "≥" if direction == "min" else "≤"
    if unit == "%":
        return f"{sym} {threshold:.0f}%"
    if unit == "s":
        return f"{sym} {threshold:.1f}s"
    if unit == "/5":
        return f"{sym} {threshold:.1f}/5"
    return f"{sym} {threshold:.2f}"


def _print_table(
    gate_results: List[Dict[str, Any]],
    result_path: str,
    regressions: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """게이팅 결과 테이블을 터미널에 출력한다."""
    print()
    print(f"  {_SEP}")
    print(f"  {B}Agent Evaluator — Quality Gate{R}")
    print(f"  결과: {D}{result_path}{R}")
    print(f"  {_SEP}")
    print()

    # 헤더
    print(f"  {'지표':<20}  {'현재값':<12}  {'기준값':<12}  {'결과'}")
    print(f"  {'─' * 20}  {'─' * 11}  {'─' * 11}  {'─' * 6}")

    active_count = 0
    fail_count = 0

    for g in gate_results:
        if not g["active"]:
            continue
        active_count += 1

        label_str = g["label"]
        cur_str = _fmt_value(g["current"], g["unit"])
        thr_str = _fmt_threshold(g["threshold"], g["direction"], g["unit"])

        if g["current"] is None:
            result_str = f"{RD}❌ SKIP{R}"
        elif g["passed"]:
            result_str = f"{G}✅ PASS{R}"
        else:
            result_str = f"{RD}❌ FAIL{R}"
            fail_count += 1

        # 색상 제거 후 패딩 계산 (ANSI 코드가 없는 문자열 길이 기준)
        print(f"  {label_str:<20}  {cur_str:<12}  {thr_str:<12}  {result_str}")

    print()
    print(f"  {_SEP}")

    # 회귀 결과
    if regressions:
        print()
        print(f"  {B}{Y}회귀 감지 항목:{R}")
        for reg in regressions:
            direction_sym = "↓" if reg["pct_change"] < 0 else "↑"
            print(
                f"  {RD}⚠  {reg['label']}{R}"
                f"  기준선: {_fmt_value(reg['baseline_val'], reg['unit'])}"
                f"  →  현재: {_fmt_value(reg['current'], reg['unit'])}"
                f"  ({direction_sym}{abs(reg['pct_change']):.1f}%)"
            )
        print()
        print(f"  {_SEP}")

    # 요약
    print()
    if active_count == 0:
        print(f"  {D}임계값 기준이 지정되지 않았습니다. --tcr, --accuracy 등 옵션을 사용하세요.{R}")
    elif fail_count == 0 and not regressions:
        print(f"  {G}{B}✅ 모든 기준 통과 ({active_count}/{active_count}){R}")
    elif regressions and fail_count == 0:
        print(f"  {Y}{B}⚠  임계값은 통과했으나 회귀 감지 ({len(regressions)}건){R}")
    else:
        passed = active_count - fail_count
        print(f"  {RD}{B}❌ 품질 기준 미달 ({fail_count}/{active_count} 실패){R}")
        print(f"  {D}→ CI 파이프라인에서 이 단계를 실패 처리하세요{R}")

    print(f"  {_SEP}")
    print()


# ---------------------------------------------------------------------------
# JUnit XML 출력
# ---------------------------------------------------------------------------

def _write_junit_xml(
    gate_results: List[Dict[str, Any]],
    regressions: Optional[List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """JUnit XML 형식으로 결과를 저장한다.

    Args:
        gate_results: 게이팅 결과 목록.
        regressions: 회귀 감지 목록 (None이면 생략).
        output_path: 출력 파일 경로.
    """
    active = [g for g in gate_results if g["active"]]
    failures = [g for g in active if not g["passed"]]
    regression_list = regressions or []

    lines: List[str] = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append('<testsuites name="agent-eval-gate">')
    lines.append(
        f'  <testsuite name="quality-gate" '
        f'tests="{len(active)}" '
        f'failures="{len(failures)}">'
    )

    for g in active:
        class_name = "agent_evaluator.gate"
        test_name = g["label"]
        cur_str = _fmt_value(g["current"], g["unit"])
        thr_str = _fmt_threshold(g["threshold"], g["direction"], g["unit"])
        lines.append(f'    <testcase name="{test_name}" classname="{class_name}">')
        if not g["passed"]:
            msg = f"현재값: {cur_str}, 기준값: {thr_str}"
            lines.append(f'      <failure message="{msg}">{msg}</failure>')
        lines.append("    </testcase>")

    # 회귀 항목도 별도 testcase로 기록
    for reg in regression_list:
        test_name = f"{reg['label']} (regression)"
        cur_str = _fmt_value(reg["current"], reg["unit"])
        base_str = _fmt_value(reg["baseline_val"], reg["unit"])
        msg = f"현재값: {cur_str}, 기준선: {base_str} ({reg['pct_change']:+.1f}%)"
        lines.append(f'    <testcase name="{test_name}" classname="agent_evaluator.gate.regression">')
        lines.append(f'      <failure message="{msg}">{msg}</failure>')
        lines.append("    </testcase>")

    lines.append("  </testsuite>")
    lines.append("</testsuites>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# cmd_gate
# ---------------------------------------------------------------------------

def cmd_gate(args: argparse.Namespace) -> int:
    """gate 서브커맨드 핸들러.

    Args:
        args: argparse.Namespace — CLI 인수.

    Returns:
        종료 코드 (0=통과, 1=기준 미달, 2=회귀 감지).

    Example:
        # argparse.Namespace를 직접 생성해 호출하는 경우
        import argparse
        ns = argparse.Namespace(
            result_file="results/ci.json",
            tcr=85.0, accuracy=None, p95_latency=None,
            hallucination=None, llm_judge=None,
            fail_on_regression=None, baseline=None,
            save_baseline=False, junit_xml=None,
        )
        exit_code = cmd_gate(ns)
    """
    result_file = Path(args.result_file)

    # ── 결과 파일 로드 ───────────────────────────────────────────────────────
    if not result_file.is_file():
        print(
            f"{RD}❌ 결과 파일을 찾을 수 없습니다: {result_file}{R}",
            file=sys.stderr,
        )
        return 1

    try:
        with open(result_file, encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{RD}❌ JSON 파싱 실패: {exc}{R}", file=sys.stderr)
        return 1

    # ── 메트릭 추출 ─────────────────────────────────────────────────────────
    metrics = _load_metrics(data)

    # ── 기준선 경로 결정 ─────────────────────────────────────────────────────
    if getattr(args, "baseline", None):
        baseline_path = Path(args.baseline)
    else:
        baseline_path = _default_baseline_path(result_file)

    # ── --save-baseline: 저장 후 종료 ────────────────────────────────────────
    if getattr(args, "save_baseline", False):
        _save_baseline(baseline_path, metrics)
        print(f"{G}✅ 기준선 저장 완료: {baseline_path}{R}")
        # 기준선 저장만 요청한 경우 — 게이팅은 계속 진행
        # (추가 옵션이 없으면 0으로 종료)
        has_gate_args = any(
            getattr(args, attr, None) is not None
            for _, _, attr, _, _ in _GATE_DEFS
        )
        if not has_gate_args and getattr(args, "fail_on_regression", None) is None:
            return 0

    # ── 게이팅 판정 ─────────────────────────────────────────────────────────
    gate_results = _check_gates(metrics, args)

    # ── 회귀 감지 ───────────────────────────────────────────────────────────
    regressions: List[Dict[str, Any]] = []
    fail_on_regression = getattr(args, "fail_on_regression", None)
    if fail_on_regression is not None:
        baseline_data = _load_baseline(baseline_path)
        if baseline_data is None:
            print(
                f"{Y}⚠  기준선 파일 없음 ({baseline_path}) — 회귀 검사를 건너뜁니다.{R}",
                file=sys.stderr,
            )
        else:
            regressions = _check_regression(metrics, baseline_data, fail_on_regression)

    # ── 출력 ────────────────────────────────────────────────────────────────
    _print_table(gate_results, str(result_file), regressions if regressions else None)

    # ── JUnit XML ───────────────────────────────────────────────────────────
    junit_xml_path = getattr(args, "junit_xml", None)
    if junit_xml_path:
        _write_junit_xml(gate_results, regressions or None, Path(junit_xml_path))
        print(f"{D}JUnit XML: {junit_xml_path}{R}")

    # ── 종료 코드 결정 ───────────────────────────────────────────────────────
    if regressions:
        return 2

    active_gates = [g for g in gate_results if g["active"]]
    if any(not g["passed"] for g in active_gates):
        return 1

    return 0
