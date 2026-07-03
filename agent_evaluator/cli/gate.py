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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_evaluator.cli._utils import _supports_color
# SPEC-010 REQ-2: Harness Gate A-G 회귀 판정 로직을 quick_eval.py와 공유한다(HarnessEvaluationGate
# Python API와 동일한 판정 공식 — 중복 구현 방지).
from agent_evaluator.quick_eval import _compute_gate_regressions


# ---------------------------------------------------------------------------
# ANSI 색상
# ---------------------------------------------------------------------------

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
            "total_cost":       float | None,   # USD
        }
    """
    metrics: Dict[str, Optional[float]] = {
        "tcr": None,
        "accuracy": None,
        "p95_latency": None,
        "hallucination": None,
        "llm_judge_overall": None,
        "total_cost": None,
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
            p95_val = float(p95_raw)
            # 0.0 은 레이턴시 미측정(LatencyTracker 미사용)을 의미하므로 None 처리
            if p95_val > 0.0:
                metrics["p95_latency"] = p95_val
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

    # -- 총 비용 --
    token_block = efficiency_metrics.get("tokens", {})
    cost_raw = token_block.get("total_cost")
    if cost_raw is not None:
        try:
            metrics["total_cost"] = float(cost_raw)
        except (TypeError, ValueError):
            pass

    return metrics


# ---------------------------------------------------------------------------
# Harness Gate 그룹 점수 추출 및 가중치 계산
# ---------------------------------------------------------------------------

def _load_harness_groups(data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """결과 JSON에서 Harness Gate A–G 그룹 점수를 추출한다.

    Args:
        data: 평가 결과 JSON dict.

    Returns:
        {"A": score_or_None, ..., "G": score_or_None}
    """
    groups: Dict[str, Optional[float]] = {g: None for g in "ABCDEFG"}
    harness = (data.get("extra_metrics") or {}).get("harness_groups", {})
    for key in "ABCDEFG":
        group_data = harness.get(key)
        if isinstance(group_data, dict):
            score = group_data.get("score")
            if score is not None:
                try:
                    groups[key] = float(score)
                except (TypeError, ValueError):
                    pass
    return groups


def _parse_group_weights(weights_str: Optional[str]) -> Dict[str, float]:
    """'A:2.0,B:1.5,E:3.0' 형식 문자열을 가중치 dict로 파싱한다.

    Args:
        weights_str: 쉼표 구분 'Gate:Weight' 쌍. None 이면 빈 dict 반환.

    Returns:
        {"A": 2.0, "B": 1.5, ...}  (미지정 Gate는 기본값 1.0 으로 처리)

    Raises:
        ValueError: 형식이 잘못된 경우.
    """
    if not weights_str:
        return {}
    result: Dict[str, float] = {}
    for token in weights_str.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid weight format: '{token}'. Example: A:2.0,B:1.5")
        gate_key = parts[0].strip().upper()
        if gate_key not in "ABCDEFG" or len(gate_key) != 1:
            raise ValueError(f"Invalid Gate key: '{gate_key}'. Must be one of A–G.")
        try:
            result[gate_key] = float(parts[1].strip())
        except ValueError:
            raise ValueError(f"Weight is not a number: '{parts[1]}'")
    return result


def _parse_gate_thresholds(thresholds_str: Optional[str]) -> Dict[str, float]:
    """'A:0.8,D:0.9,E:0.95' 형식 문자열을 Gate별 임계값 dict로 파싱한다.

    Args:
        thresholds_str: 쉼표 구분 'Gate:Score' 쌍. None 이면 빈 dict 반환.

    Returns:
        {"A": 0.8, "D": 0.9, ...}

    Raises:
        ValueError: 형식이 잘못된 경우.
    """
    if not thresholds_str:
        return {}
    result: Dict[str, float] = {}
    for token in thresholds_str.split(","):
        token = token.strip()
        if not token:
            continue
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid gate-thresholds format: '{token}'. Example: A:0.8,D:0.9")
        gate_key = parts[0].strip().upper()
        if gate_key not in "ABCDEFG" or len(gate_key) != 1:
            raise ValueError(f"Invalid Gate key: '{gate_key}'. Must be one of A–G.")
        try:
            val = float(parts[1].strip())
        except ValueError:
            raise ValueError(f"Score is not a number: '{parts[1]}'")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"Gate score must be 0.0–1.0, got {val}")
        result[gate_key] = val
    return result


def _compute_composite_gate(
    groups: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> Optional[float]:
    """Harness Gate A–G 그룹 점수의 가중 평균을 계산한다.

    Args:
        groups: Gate별 점수 dict (None 이면 해당 Gate 제외).
        weights: Gate별 가중치. 미지정 Gate는 1.0 으로 처리.

    Returns:
        가중 평균 (0.0–1.0), 유효 데이터 없으면 None.
    """
    total_w = 0.0
    weighted_sum = 0.0
    for gate, score in groups.items():
        if score is None:
            continue
        w = weights.get(gate, 1.0)
        weighted_sum += score * w
        total_w += w
    if total_w == 0.0:
        return None
    return weighted_sum / total_w


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


def _save_baseline(
    path: Path,
    metrics: Dict[str, Optional[float]],
    harness_scores: Optional[Dict[str, Optional[float]]] = None,
) -> None:
    """현재 메트릭을 기준선 파일로 저장한다.

    Args:
        path: 저장 경로.
        metrics: 5개 평면 지표(tcr/accuracy/p95_latency/hallucination/llm_judge_overall/total_cost).
        harness_scores: (SPEC-010 REQ-1) Harness Gate A-G 점수 ``{"A": 0.82, ...}``. 지정하면
            ``"gate_scores"`` 키로 함께 저장되어 이후 ``--fail-on-regression``이 Gate 점수도
            회귀 비교 대상으로 삼을 수 있다. 기존 5개 평면 지표 필드는 그대로 유지한다
            (하위호환 — 이 필드가 없는 구버전 baseline.json도 계속 읽을 수 있어야 한다).
    """
    payload: Dict[str, Any] = {k: v for k, v in metrics.items()}
    # _load_harness_groups()는 harness_groups 자체가 없어도 {"A": None, ..., "G": None}처럼
    # 항상 7개 키의 dict를 반환하므로(단순 truthy 체크로는 항상 True), 실제로 값이 하나라도
    # 있는지(any non-None)로 판단해 harness_groups 데이터가 전혀 없는 결과 파일에서는
    # baseline.json에 무의미한 전부-None gate_scores를 남기지 않는다.
    if harness_scores and any(v is not None for v in harness_scores.values()):
        payload["gate_scores"] = dict(harness_scores)
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
    ("tcr",             "TCR",                  "tcr",           "min",  "%"),
    ("accuracy",        "Accuracy",             "accuracy",       "min",  "%"),
    ("p95_latency",     "P95 Latency",          "p95_latency",    "max",  "s"),
    ("hallucination",   "Hallucination Rate",   "hallucination",  "max",  "%"),
    ("llm_judge_overall", "LLM Judge (Overall)", "llm_judge",    "min",  "/5"),
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

_ANSI_ESC = re.compile(r"\033\[[0-9;]*m")


def _vlen(s: str) -> int:
    """ANSI 이스케이프 코드를 제외한 표시 문자 수를 반환한다."""
    return len(_ANSI_ESC.sub("", s))


def _pad_right(s: str, width: int) -> str:
    """ANSI 코드를 고려해 오른쪽 공백을 채운다."""
    return s + " " * max(0, width - _vlen(s))


def _pad_left(s: str, width: int) -> str:
    """ANSI 코드를 고려해 왼쪽 공백을 채운다."""
    return " " * max(0, width - _vlen(s)) + s


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


def _fmt_delta(current: float, threshold: float, direction: str, unit: str) -> str:
    """임계값 대비 현재값의 차이(델타)를 사람이 읽기 좋은 형태로 포맷한다."""
    if direction == "min":
        delta = current - threshold  # 양수면 초과(좋음), 음수면 미달(나쁨)
    else:
        delta = threshold - current  # 양수면 임계값 내(좋음), 음수면 초과(나쁨)
    sign = "+" if delta >= 0 else ""
    if unit == "%":
        return f"{sign}{delta:.1f}%"
    if unit == "s":
        return f"{sign}{delta:.2f}s"
    if unit == "/5":
        return f"{sign}{delta:.2f}"
    return f"{sign}{delta:.2f}"


def _print_composite_gate(
    groups: Dict[str, Optional[float]],
    weights: Dict[str, float],
    min_score: float,
    composite: Optional[float],
) -> bool:
    """Harness Gate A–G 복합 점수 섹션을 출력하고 통과 여부를 반환한다."""
    _GATE_NAMES = {
        "A": "Goal Achievement",
        "B": "Behavioral Integrity",
        "C": "Reliability",
        "D": "Performance Contract",
        "E": "Security Boundary",
        "F": "Multi-Agent Coordination",
        "G": "Observability",
    }
    print()
    print(f"  {B}Harness Gate Composite Score{R}  {D}(--min-gate-score {min_score:.2f}){R}")
    print(f"  {'─' * 26}  {'─' * 7}  {'─' * 8}  {'─' * 6}")
    print(f"  {'Gate':<26}  {'Score':>7}  {'Weight':>8}  {'Status'}")
    print(f"  {'─' * 26}  {'─' * 7}  {'─' * 8}  {'─' * 6}")
    for gate in "ABCDEFG":
        score = groups.get(gate)
        w = weights.get(gate, 1.0)
        name = f"{gate}. {_GATE_NAMES.get(gate, '')}"
        if score is None:
            score_str = f"{D}N/A{R}"
            status_str = f"{D}—{R}"
        elif score >= 0.7:
            score_str = f"{G}{score:.3f}{R}"
            status_str = f"{G}pass{R}"
        elif score >= 0.5:
            score_str = f"{Y}{score:.3f}{R}"
            status_str = f"{Y}warn{R}"
        else:
            score_str = f"{RD}{score:.3f}{R}"
            status_str = f"{RD}fail{R}"
        weight_str = f"×{w:.1f}" if weights else f"{D}×1.0{R}"
        print(f"  {name:<26}  {_pad_left(score_str, 7)}  {_pad_left(weight_str, 8)}  {status_str}")
    print()
    if composite is None:
        print(f"  {D}Composite score: N/A (no Harness data){R}")
        passed = True
    else:
        passed = composite >= min_score
        color = G if passed else RD
        result_label = f"{G}✅ PASS{R}" if passed else f"{RD}❌ FAIL{R}"
        print(
            f"  Composite score: {color}{composite:.4f}{R}  "
            f"threshold: ≥ {min_score:.2f}  {result_label}"
        )
    return passed


def _print_table(
    gate_results: List[Dict[str, Any]],
    result_path: str,
    regressions: Optional[List[Dict[str, Any]]] = None,
    composite_result: Optional[Dict[str, Any]] = None,
) -> None:
    """게이팅 결과 테이블을 터미널에 출력한다."""
    active = [g for g in gate_results if g["active"]]
    fail_count = sum(1 for g in active if not g["passed"] and g["current"] is not None)
    skip_count = sum(1 for g in active if g["current"] is None)
    active_count = len(active)

    print()
    print(f"  {_SEP}")
    print(f"  {B}Agent Evaluator — Quality Gate{R}")
    print(f"  Result: {D}{result_path}{R}")
    print(f"  {_SEP}")
    print()

    # 복합 게이트 섹션
    composite_passed = True
    if composite_result is not None:
        composite_passed = _print_composite_gate(
            composite_result["groups"],
            composite_result["weights"],
            composite_result["min_score"],
            composite_result["composite"],
        )
        print()
        print(f"  {_SEP}")
        print()

    if active_count > 0:
        # header (5 columns: Metric / Current / Threshold / Delta / Result)
        print(f"  {'Metric':<22}  {'Current':<11}  {'Threshold':<12}  {'Delta':<10}  {'Result'}")
        print(f"  {'─' * 22}  {'─' * 11}  {'─' * 12}  {'─' * 10}  {'─' * 6}")

        for g in active:
            label_str = g["label"]
            cur_str = _fmt_value(g["current"], g["unit"])
            thr_str = _fmt_threshold(g["threshold"], g["direction"], g["unit"])

            if g["current"] is None:
                result_str = f"{RD}❌ SKIP{R}"
                delta_str = f"{D}N/A{R}"
            elif g["passed"]:
                result_str = f"{G}✅ PASS{R}"
                delta_str = f"{G}{_fmt_delta(g['current'], g['threshold'], g['direction'], g['unit'])}{R}"
            else:
                result_str = f"{RD}❌ FAIL{R}"
                delta_str = f"{RD}{_fmt_delta(g['current'], g['threshold'], g['direction'], g['unit'])}{R}"

            print(f"  {label_str:<22}  {_pad_right(cur_str, 11)}  {_pad_right(thr_str, 12)}  {_pad_right(delta_str, 10)}  {result_str}")

        print()

    print(f"  {_SEP}")

    # 요약에서 복합 게이트 실패 반영
    if not composite_passed:
        fail_count += 1

    # 회귀 결과
    if regressions:
        print()
        print(f"  {B}{Y}Regressions detected:{R}")
        for reg in regressions:
            direction_sym = "↓" if reg["pct_change"] < 0 else "↑"
            print(
                f"  {RD}⚠  {reg['label']}{R}"
                f"  baseline: {_fmt_value(reg['baseline_val'], reg['unit'])}"
                f"  →  current: {_fmt_value(reg['current'], reg['unit'])}"
                f"  ({direction_sym}{abs(reg['pct_change']):.1f}%)"
            )
        print()
        print(f"  {_SEP}")

    # 요약
    print()
    if active_count == 0:
        print(f"  {D}No thresholds specified. Use --tcr, --accuracy, etc.{R}")
    elif fail_count == 0 and not regressions:
        passed = active_count - skip_count
        print(f"  {G}{B}✅ All checks passed ({passed}/{active_count}){R}")
    elif regressions and fail_count == 0:
        print(f"  {Y}{B}⚠  Thresholds passed but regressions detected ({len(regressions)}){R}")
    else:
        passed = active_count - fail_count - skip_count
        print(f"  {RD}{B}❌ Quality gate failed ({passed}/{active_count} passed){R}")
        print(f"  {D}→ Fail this step in your CI pipeline{R}")

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
            msg = f"current: {cur_str}, threshold: {thr_str}"
            lines.append(f'      <failure message="{msg}">{msg}</failure>')
        lines.append("    </testcase>")

    # 회귀 항목도 별도 testcase로 기록
    for reg in regression_list:
        test_name = f"{reg['label']} (regression)"
        cur_str = _fmt_value(reg["current"], reg["unit"])
        base_str = _fmt_value(reg["baseline_val"], reg["unit"])
        msg = f"current: {cur_str}, baseline: {base_str} ({reg['pct_change']:+.1f}%)"
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
            f"{RD}❌ Result file not found: {result_file}{R}",
            file=sys.stderr,
        )
        return 1

    try:
        with open(result_file, encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{RD}❌ Failed to parse JSON: {exc}{R}", file=sys.stderr)
        return 1

    # ── 메트릭 추출 ─────────────────────────────────────────────────────────
    metrics = _load_metrics(data)
    # SPEC-010 REQ-1: Harness Gate A-G 점수도 미리 로드해 둔다 — --save-baseline(저장)과
    # --min-gate-score(복합 점수 계산) 양쪽에서 재사용하고, --fail-on-regression 시 회귀
    # 비교 대상에도 포함한다.
    harness_scores = _load_harness_groups(data)

    # ── 기준선 경로 결정 ─────────────────────────────────────────────────────
    if getattr(args, "baseline", None):
        baseline_path = Path(args.baseline)
    else:
        baseline_path = _default_baseline_path(result_file)

    # ── --save-baseline: 저장 후 종료 ────────────────────────────────────────
    if getattr(args, "save_baseline", False):
        _save_baseline(baseline_path, metrics, harness_scores=harness_scores)
        print(f"{G}✅ Baseline saved: {baseline_path}{R}")
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

    # ── Harness Gate 복합 점수 ───────────────────────────────────────────────
    composite_result: Optional[Dict[str, Any]] = None
    min_gate_score = getattr(args, "min_gate_score", None)
    if min_gate_score is not None:
        group_weights_str = getattr(args, "group_weights", None)
        try:
            weights = _parse_group_weights(group_weights_str)
        except ValueError as exc:
            print(f"{RD}❌ --group-weights error: {exc}{R}", file=sys.stderr)
            return 1
        composite = _compute_composite_gate(harness_scores, weights)
        composite_result = {
            "groups": harness_scores,
            "weights": weights,
            "min_score": min_gate_score,
            "composite": composite,
        }

    # ── Gate별 개별 임계값 검증 (--gate-thresholds) ──────────────────────────
    gate_threshold_violations: List[str] = []
    gate_threshold_str = getattr(args, "gate_thresholds", None)
    if gate_threshold_str:
        try:
            gate_thresholds = _parse_gate_thresholds(gate_threshold_str)
        except ValueError as exc:
            print(f"{RD}❌ --gate-thresholds error: {exc}{R}", file=sys.stderr)
            return 1
        required_gates_raw = getattr(args, "required_gates", None)
        required_set = (
            set(g.strip().upper() for g in required_gates_raw.split(","))
            if required_gates_raw else None
        )
        fail_on_warn = getattr(args, "fail_on_gate_warn", False)
        harness_raw = (data.get("extra_metrics") or {}).get("harness_groups", {})
        min_gate_fallback = getattr(args, "min_gate_score", None)
        for gate_id in "ABCDEFG":
            if required_set is not None and gate_id not in required_set:
                continue
            gate_data = harness_raw.get(gate_id)
            if not isinstance(gate_data, dict):
                continue
            score = gate_data.get("score")
            if score is None:
                continue
            threshold = gate_thresholds.get(gate_id, min_gate_fallback)
            if threshold is None:
                continue
            score_f = float(score)
            status = gate_data.get("status", "")
            passed = score_f >= threshold
            if fail_on_warn and status == "warn":
                passed = False
            if not passed:
                reason = f"status={status}" if (fail_on_warn and status == "warn") else f"{score_f:.3f} < {threshold:.3f}"
                gate_threshold_violations.append(f"Gate {gate_id}: {reason}")

        if gate_threshold_violations:
            print(f"\n{RD}Gate 임계값 미달:{R}", file=sys.stderr)
            for v in gate_threshold_violations:
                print(f"  {RD}✗ {v}{R}", file=sys.stderr)

    # ── 회귀 감지 ───────────────────────────────────────────────────────────
    regressions: List[Dict[str, Any]] = []
    fail_on_regression = getattr(args, "fail_on_regression", None)
    if fail_on_regression is not None:
        baseline_data = _load_baseline(baseline_path)
        if baseline_data is None:
            print(
                f"{Y}⚠  No baseline file found ({baseline_path}) — skipping regression check.{R}",
                file=sys.stderr,
            )
        else:
            regressions = _check_regression(metrics, baseline_data, fail_on_regression)
            # SPEC-010 REQ-2: Harness Gate A-G 점수도 회귀 비교 대상에 포함한다.
            # baseline_data에 "gate_scores"가 없으면(구버전 baseline.json) 빈 dict로 처리되어
            # 회귀가 감지되지 않는다 — 기존 5개 평면 지표 회귀 비교에는 영향 없음(하위호환).
            _baseline_gate_scores = baseline_data.get("gate_scores") or {}
            _gate_regressions = _compute_gate_regressions(
                harness_scores, _baseline_gate_scores, fail_on_regression / 100.0
            )
            for _greg in _gate_regressions:
                _gate_id = _greg["gate"]
                _base_val = _greg["baseline_score"]
                _pct_change = (
                    (_greg["delta"] / _base_val * 100.0) if _base_val else 0.0
                )
                regressions.append({
                    "name": f"gate_{_gate_id}",
                    "label": f"Gate {_gate_id}",
                    "current": _greg["current_score"],
                    "baseline_val": _base_val,
                    "pct_change": _pct_change,
                    "unit": "",
                })

    # ── 출력 ────────────────────────────────────────────────────────────────
    _print_table(gate_results, str(result_file), regressions if regressions else None, composite_result)

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

    # 복합 게이트 실패
    if composite_result is not None:
        composite = composite_result.get("composite")
        if composite is not None and composite < composite_result["min_score"]:
            return 1

    # Gate별 임계값 위반
    if gate_threshold_violations:
        return 1

    return 0
