"""
agent_evaluator.rca.verify
=============================
Phase 4(개선 엔진, 폐루프 학습) — "추천 조치를 적용했더니 실제로 나아졌는가"를
재평가 결과로 확인한다.

범위를 의도적으로 좁혔다: 추천 적용 이력을 자동으로 추적하는 저장소(성공률 누적·
랭킹)는 만들지 않는다 — 검증할 실제 사용 데이터가 아직 없는 상태에서 그 인프라를
먼저 만들면 정확성을 검증할 방법이 없다. 이 모듈은 그 전 단계, 즉 "before/after
두 리포트를 주면 목표 Gate가 실제로 개선됐는지"를 판정하는 순수 함수만 제공한다 —
호출자(사람 또는 향후의 추적 시스템)가 이 판정을 이력에 기록할지는 별개의 문제다.

HOTL 원칙(Chapter 2): "개선됐다"를 확정하지 않는다 — confirmed(개선 방향 확인)/
refuted(악화 또는 무변화)/inconclusive(측정 불가) 세 상태로만 보고한다.
"""
from __future__ import annotations

from typing import Any

from agent_evaluator.rca.diagnose import _as_number, _extract_harness_groups


def verify_recommendation_outcome(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    target_gate: str,
    target_field: str | None = None,
    improvement_threshold: float = 0.05,
) -> dict[str, Any]:
    """추천 적용 전/후 두 리포트를 비교해 목표 Gate(선택적으로 세부 지표까지)가
    실제로 개선됐는지 확인한다.

    Args:
        before: 추천 적용 전 평가 결과 JSON(로드된 dict).
        after: 추천 적용 후 재평가 결과 JSON.
        target_gate: 추천이 목표로 삼은 Gate("A"-"G" 또는 ``register_gate()``로
            등록된 커스텀 Gate id).
        target_field: 추천이 목표로 삼은 세부 지표명(``details``의 키, 선택).
            주어지면 Gate 점수 판정과 별개로 이 지표의 변화도 함께 보고한다.
        improvement_threshold: 이 이상 오르면 confirmed, 이 이상 내리면 refuted,
            그 사이면 inconclusive(변화가 판정하기엔 너무 작음).

    Returns:
        ``{target_gate, before_score, after_score, gate_delta, verdict,
        target_field_result}``. ``verdict``는 ``"confirmed"``·``"refuted"``·
        ``"inconclusive"`` 중 하나 — "추천이 원인이었다"는 인과 주장은 하지 않는다
        (다른 변경이 동시에 있었을 수 있다, Chapter 31 §31.2의 경계심과 동일).
    """
    before_hg = _extract_harness_groups(before)
    after_hg = _extract_harness_groups(after)
    before_score = (before_hg.get(target_gate) or {}).get("score")
    after_score = (after_hg.get(target_gate) or {}).get("score")

    if before_score is None or after_score is None:
        return {
            "target_gate": target_gate,
            "before_score": before_score,
            "after_score": after_score,
            "gate_delta": None,
            "verdict": "inconclusive",
            "reason": "The Gate score could not be measured (None) in before and/or after.",
            "target_field_result": None,
        }

    gate_delta = round(float(after_score) - float(before_score), 4)
    if gate_delta >= improvement_threshold:
        verdict = "confirmed"
    elif gate_delta <= -improvement_threshold:
        verdict = "refuted"
    else:
        verdict = "inconclusive"

    target_field_result = None
    if target_field is not None:
        before_details = (before_hg.get(target_gate) or {}).get("details") or {}
        after_details = (after_hg.get(target_gate) or {}).get("details") or {}
        b_v = _as_number(before_details.get(target_field))
        a_v = _as_number(after_details.get(target_field))
        if b_v is not None and a_v is not None:
            target_field_result = {
                "field": target_field, "before": b_v, "after": a_v,
                "delta": round(a_v - b_v, 4),
            }

    return {
        "target_gate": target_gate,
        "before_score": round(float(before_score), 4),
        "after_score": round(float(after_score), 4),
        "gate_delta": gate_delta,
        "verdict": verdict,
        "target_field_result": target_field_result,
    }
