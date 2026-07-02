"""
agent_evaluator.gates.gate_g_observability.evaluators
========================================================
Gate G(Observability) 평가 함수 4종.

SPEC-000: agent_evaluator/helpers/taskresult_helpers.py에서 그대로 이관(로직 변경 없음).
taskresult_helpers.py는 이 모듈을 re-export하여 하위호환을 유지한다.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def eval_observability(
    tool_calls: List[Dict[str, Any]],
    task_result_extra: Dict[str, Any],
    task_id: str,
    task_type: str,
    execution_time_s: float,
    config: Any,
) -> Dict[str, Any]:
    """Trace 완성도·필수 속성 존재 여부·감사 이벤트 커버리지를 측정한다.

    Args:
        tool_calls: TaskResult.tool_calls.
        task_result_extra: TaskResult.extra.
        task_id: TaskResult.task_id.
        task_type: TaskResult.task_type.
        execution_time_s: TaskResult.execution_time.
        config: ObservabilityConfig 인스턴스.

    Returns:
        {trace_coverage, missing_attributes, missing_audit_events, observability_score}
    """
    # BUG-G2 fix: `or [...]` falsy trap — required_span_attributes=[] means "check nothing",
    # must use explicit None check instead of truthy override.
    _raw_attrs = getattr(config, "required_span_attributes", None)
    required_attrs: List[str] = (
        _raw_attrs if _raw_attrs is not None
        else ["task_id", "task_type", "execution_time"]
    )
    check_continuity: bool = getattr(config, "check_trace_continuity", True)
    audit_events: List[str] = getattr(config, "audit_events", []) or []
    # BUG-G3 fix: `or 0.95` falsy trap — min_coverage=0.0 must not be overridden.
    _raw_cov = getattr(config, "min_coverage", None)
    min_coverage: float = _raw_cov if _raw_cov is not None else 0.95

    extra = task_result_extra or {}
    actual_attrs: Dict[str, Any] = {
        "task_id": task_id,
        "task_type": task_type,
        "execution_time": execution_time_s,
    }
    # extra에 추가 속성이 있으면 포함 — 기본 속성(task_id/task_type/execution_time)은 덮어쓰지 않음
    # dict 값(예: {"model": "gpt-4"})도 속성으로 인정 — 존재 여부는 값 타입이 아닌 None 여부로만 판단
    for _k, _v in extra.items():
        if _k not in actual_attrs and _v is not None:
            actual_attrs[_k] = _v

    # 필수 속성 체크
    missing_attributes = [a for a in required_attrs if actual_attrs.get(a) is None]
    attr_completeness = 1.0 - (len(missing_attributes) / len(required_attrs)) if required_attrs else 1.0

    # trace 연속성: tool_calls 수 vs span 수 비교
    tc_count = len(tool_calls or [])
    # BUG-G8 fix: `or` falsy trap — otel_spans=0(명시적 0 스팬)이 falsy라서
    # span_count로 폴백되는 버그. 0은 "0개의 스팬을 기록했음"의 유효한 값이므로
    # None과 구별해야 한다.
    _raw_otel = extra.get("otel_spans")
    otel_spans = _raw_otel if _raw_otel is not None else extra.get("span_count")
    if check_continuity and tc_count > 0:
        if otel_spans is None:
            logger.warning(
                "ObservabilityConfig: check_trace_continuity=True이지만 extra에 "
                "'otel_spans' 또는 'span_count'가 없습니다. trace_coverage=0.0으로 처리됩니다. "
                "EvalMetadata(extra={'otel_spans': N}) 또는 'span_count'를 설정하세요."
            )
        span_count = max(0, int(float(otel_spans or 0)))
        trace_coverage = min(1.0, span_count / tc_count) if tc_count > 0 else 1.0
    else:
        trace_coverage = 1.0  # tool_calls 없으면 완전 커버

    # 감사 이벤트 체크
    recorded_events = set(extra.get("audit_events") or [])
    missing_audit_events = [e for e in audit_events if e not in recorded_events]
    audit_completeness = 1.0 - (len(missing_audit_events) / len(audit_events)) if audit_events else 1.0

    # 종합 observability score
    observability_score = (trace_coverage + attr_completeness + audit_completeness) / 3.0
    slo_met = trace_coverage >= min_coverage

    return {
        "trace_coverage": round(trace_coverage, 4),
        "attr_completeness": round(attr_completeness, 4),
        "audit_completeness": round(audit_completeness, 4),
        "missing_attributes": missing_attributes,
        "missing_audit_events": missing_audit_events,
        "observability_score": round(observability_score, 4),
        "slo_met": slo_met,
    }


def eval_explainability(
    response: str, tool_calls: List[Any], config: Any
) -> Dict[str, Any]:
    """에이전트 응답에 필요한 설명이 포함되어 있는지 평가한다.

    Args:
        response: 에이전트 응답 문자열.
        tool_calls: 도구 호출 리스트 (현재 미사용, 향후 확장용).
        config: ExplainabilityConfig 인스턴스.

    Returns:
        {score, checks, violations, has_reasoning, has_citations}
    """
    response_lower = response.lower() if response else ""
    checks: Dict[str, bool] = {}
    violations: List[str] = []

    require_reasoning = getattr(config, "require_reasoning", True)
    reasoning_markers = getattr(config, "reasoning_markers", [])
    min_reasoning_length = getattr(config, "min_reasoning_length", 20)
    require_uncertainty_expression = getattr(config, "require_uncertainty_expression", False)
    uncertainty_markers = getattr(config, "uncertainty_markers", [])
    require_citations = getattr(config, "require_citations", False)
    citation_markers = getattr(config, "citation_markers", [])

    # Reasoning check
    if require_reasoning:
        has_reasoning = any(m.lower() in response_lower for m in reasoning_markers)
        long_enough = len(response.strip()) >= min_reasoning_length if response else False
        checks["reasoning"] = has_reasoning and long_enough
        if not checks["reasoning"]:
            violations.append("missing_reasoning")

    # Uncertainty check
    if require_uncertainty_expression:
        has_uncertainty = any(m.lower() in response_lower for m in uncertainty_markers)
        checks["uncertainty"] = has_uncertainty
        if not has_uncertainty:
            violations.append("missing_uncertainty_expression")

    # Citation check
    if require_citations:
        has_citation = any(m.lower() in response_lower for m in citation_markers)
        checks["citations"] = has_citation
        if not has_citation:
            violations.append("missing_citations")

    # Action-Explanation Alignment check (check_action_explanation_alignment=True)
    # 각 도구 호출이 응답에서 언급(설명)되는지 확인
    # 도구명을 underscore 분리 후 핵심 토큰이 응답에 있는지 검사
    unexplained_tools: List[str] = []
    if getattr(config, "check_action_explanation_alignment", False) and tool_calls:
        _tool_names_expl: List[str] = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                _n = tc.get("name") or tc.get("tool", "")
            elif hasattr(tc, "name"):
                _n = getattr(tc, "name", "")
            else:
                _n = str(tc)
            if _n:
                _tool_names_expl.append(_n)

        for tool_name in _tool_names_expl:
            # 도구명을 토큰으로 분리하여 응답에서 하나라도 언급되면 설명된 것으로 간주
            tokens_expl = [t for t in re.split(r"[_\-\s]+", tool_name.lower()) if len(t) > 2]
            if tokens_expl and not any(tok in response_lower for tok in tokens_expl):
                unexplained_tools.append(tool_name)

        if _tool_names_expl:
            aligned_rate = 1.0 - len(unexplained_tools) / len(_tool_names_expl)
            checks["action_explanation_alignment"] = aligned_rate >= 0.5
            if not checks["action_explanation_alignment"]:
                for _ut in unexplained_tools:
                    violations.append(f"unexplained_tool:{_ut}")

    # checks가 비었으면 요구 사항 없음 → score=None으로 Gate G 집계에서 제외
    # (요구사항을 모두 비활성화한 상태에서 만점 1.0이 Gate G에 기여되던 문제 방지)
    passed = sum(1 for v in checks.values() if v)
    score: Optional[float] = passed / len(checks) if checks else None

    return {
        "score": round(score, 4) if score is not None else None,
        "checks": checks,
        "violations": violations,
        "has_reasoning": checks.get("reasoning"),   # None = 검사 미실행
        "has_citations": checks.get("citations"),   # None = 검사 미실행
        "unexplained_tools": unexplained_tools,
    }


def eval_error_diagnosis(
    response: Optional[str],
    has_error: bool,
    task_success: bool,
    config: Any,
) -> Optional[Dict[str, Any]]:
    """오류 진단 품질 평가 (Harness G — Observability).

    실패 응답이 오류를 인정하고, 근본 원인을 제시하며, 대안을 제안하는지 평가한다.

    Args:
        response: 에이전트 응답 텍스트.
        has_error: 태스크 실행 중 예외가 발생했는지 여부.
        task_success: 태스크 성공 여부.
        config: :class:`ErrorDiagnosisConfig` 인스턴스.

    Returns:
        Dict with keys: diagnosis_score, acknowledged_failure, identified_root_cause,
        provided_suggestion, is_failure_case.
        태스크가 성공(오류 없음)이면 ``None`` 반환 — 성공 태스크는 진단 대상 없음.
        ``only_on_failure=True`` 이면 명시적 스킵, ``False`` 이면 BUG-G6 방지를 위해
        성공 태스크도 ``None`` 처리 (실패 마커 기반 점수 0.0으로 Gate G를 부당하게 낮추는 것 방지).
    """
    # BUG-G6 fix: only_on_failure=False이더라도 성공 태스크(오류 없음)에는 실패 마커가 존재하지 않으므로
    # 점수가 항상 0.0이 되어 Gate G를 부당하게 하락시킨다. 성공 태스크는 진단 대상이 없으므로 None을 반환.
    if task_success and not has_error:
        return None

    response_lower = (response or "").lower()

    acknowledged = any(
        m.lower() in response_lower for m in config.failure_acknowledgment_markers
    )
    has_root_cause = any(
        m.lower() in response_lower for m in config.root_cause_markers
    )
    has_suggestion = any(
        m.lower() in response_lower for m in config.suggestion_markers
    )

    total_weight = (
        config.acknowledgment_weight
        + config.root_cause_weight
        + config.suggestion_weight
    )
    score = (
        (config.acknowledgment_weight * float(acknowledged))
        + (config.root_cause_weight * float(has_root_cause))
        + (config.suggestion_weight * float(has_suggestion))
    ) / max(total_weight, 1e-9)

    return {
        "diagnosis_score": round(score, 4),
        "acknowledged_failure": acknowledged,
        "identified_root_cause": has_root_cause,
        "provided_suggestion": has_suggestion,
        "is_failure_case": has_error or not task_success,
    }


def eval_latency_attribution(
    execution_time_ms: float,
    extra: Optional[Dict[str, Any]],
    config: Any,
) -> Dict[str, Any]:
    """Evaluate latency breakdown across components.

    Args:
        execution_time_ms: 전체 실행 시간(밀리초).
        extra: TaskResult.extra 딕셔너리 (컴포넌트별 지연 정보 포함).
        config: :class:`~agent_evaluator.LatencyAttributionConfig` 인스턴스.

    Returns:
        attribution_score, tool_ratio, model_ratio, network_ratio,
        unattributed_ratio, bottleneck, tool_ms, model_ms 를 담은 딕셔너리.
    """
    extra = extra or {}

    # Extract component latencies from extra
    tool_latencies = extra.get(config.tool_latency_key, {}) or {}
    tool_ms: float = 0.0
    if isinstance(tool_latencies, dict):
        tool_ms = sum(float(v) for v in tool_latencies.values() if isinstance(v, (int, float)) and v >= 0)
    elif isinstance(tool_latencies, (int, float)):
        tool_ms = float(tool_latencies)

    model_ms = max(0.0, float(extra.get(config.model_latency_key, 0.0) or 0.0))
    network_ms = max(0.0, float(extra.get(config.network_latency_key, 0.0) or 0.0))

    # If the task is very fast (<10ms) and no component data was provided,
    # unattributed_penalty would fire falsely (the 1ms floor inflates unattributed_ratio
    # to 1.0 for sub-ms tasks). Return None so Gate G excludes this task.
    _has_component_data = tool_ms > 0 or model_ms > 0 or network_ms > 0
    if not _has_component_data and execution_time_ms < 10.0:
        return {
            "attribution_score": None,
            "tool_ratio": 0.0,
            "model_ratio": 0.0,
            "network_ratio": 0.0,
            "unattributed_ratio": 1.0,
            "bottleneck": "unattributed",
            "tool_ms": 0.0,
            "model_ms": 0.0,
        }

    total = max(execution_time_ms, 1.0)
    attributed = tool_ms + model_ms + network_ms
    # If attributed components exceed total (e.g. overlapping measurements), cap to total
    # so that all ratios sum to exactly 1.0
    if attributed > total:
        scale = total / attributed
        tool_ms *= scale
        model_ms *= scale
        network_ms *= scale
        attributed = total
    unattributed_ms = max(0.0, total - attributed)

    tool_ratio = tool_ms / total
    model_ratio = model_ms / total
    network_ratio = network_ms / total
    unattributed_ratio = unattributed_ms / total

    # Determine bottleneck
    components = {
        "tool": tool_ms,
        "model": model_ms,
        "network": network_ms,
        "unattributed": unattributed_ms,
    }
    bottleneck = max(components, key=lambda k: components[k])

    # Score: penalize high tool ratio and high unattributed ratio
    tool_penalty = max(0.0, tool_ratio - config.max_tool_time_ratio)
    unattributed_penalty = max(0.0, unattributed_ratio - config.max_unattributed_ratio)
    attribution_score = max(0.0, 1.0 - tool_penalty - unattributed_penalty * 0.5)

    return {
        "attribution_score": round(attribution_score, 4),
        "tool_ratio": round(tool_ratio, 4),
        "model_ratio": round(model_ratio, 4),
        "network_ratio": round(network_ratio, 4),
        "unattributed_ratio": round(unattributed_ratio, 4),
        "bottleneck": bottleneck,
        "tool_ms": round(tool_ms, 2),
        "model_ms": round(model_ms, 2),
    }
