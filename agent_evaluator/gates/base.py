"""
agent_evaluator.gates.base
============================
전 Gate(A-G)가 공유하는 최소 인프라 — 표본 가드, 상태 판정, 그룹 딕셔너리 조립 헬퍼.

SPEC-000 Commit 0: monitor.py의 모듈 레벨 상수/함수(_DEFAULT_MIN_SAMPLES, _min_sample_warning)와
_compute_harness_groups 내부 nested closure(_status, _g)를 순수 함수로 그대로 승격했다.
동작 변경 없음 — 이관 자체가 목적인 인프라 전용 커밋.
"""
from __future__ import annotations

from typing import Any

# SPEC-002: 전 Gate 공통 최소 표본 가드 기본값 — Config에 자체 min_samples 필드가 없는
# 지표(A/B/C-비SLA/E/F/G)에 적용된다. Gate D의 TTFT/Cost는 기존 Config 필드(기본 5)를 그대로 쓴다.
_DEFAULT_MIN_SAMPLES: int = 3


def _min_sample_warning(metric_name: str, count: int, min_samples: int, unit: str = "samples") -> str | None:
    """count가 1개 이상이지만 min_samples 미만이면 표준 포맷 경고 문자열을 반환한다.

    count == 0(해당 지표가 아예 측정되지 않음)은 경고 대상이 아니다 — "데이터 없음"은
    이미 details의 avg_*=None / 키 부재로 표현되는 기존 컨벤션과 겹치므로, 여기서 또
    경고를 내면 "측정 안 함"과 "표본 부족"이 혼동된다.

    Args:
        unit: 카운트 단위 (SPEC-012) — task 기반 지표는 기본값 "samples"를 그대로 쓰고,
            이벤트 기반 지표(Gate F coordination/tool_selection, Gate G tool_coverage)는
            "interactions"/"evaluations"/"calls"처럼 실제 단위를 명시해 task 표본과
            혼동되지 않게 한다.
    """
    if 0 < count < min_samples:
        return f"{metric_name}: {count} {unit} < min_samples={min_samples}"
    return None


def _status(score: float | None, warn: float = 0.7, fail: float = 0.5) -> str:
    """Gate 점수 → pass/warn/fail/n-a 판정."""
    if score is None:
        return "n/a"
    if score >= warn:
        return "pass"
    if score >= fail:
        return "warn"
    return "fail"


def _g(
    score: float | None,
    name: str,
    details: dict[str, Any],
    f_score: bool = False,
) -> dict[str, Any]:
    """그룹 딕셔너리 생성 헬퍼 — status와 gate 키를 동시에 출력."""
    _st = (_status(score) if not f_score else (_status(score) if score is not None else "n/a"))
    return {"name": name, "score": score, "status": _st, "gate": _st, "details": details}
