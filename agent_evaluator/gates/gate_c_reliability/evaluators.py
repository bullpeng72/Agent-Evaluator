"""
agent_evaluator.gates.gate_c_reliability.evaluators
======================================================
Gate C(Reliability) 평가 함수 5종.

SPEC-000: agent_evaluator/helpers/taskresult_helpers.py에서 그대로 이관(로직 변경 없음).
taskresult_helpers.py는 이 모듈을 re-export하여 하위호환을 유지한다.

_token_overlap_ratio는 Gate A·B·F도 공유하는 인프라이므로 taskresult_helpers.py에
그대로 두고 여기서는 import만 한다.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agent_evaluator.helpers.taskresult_helpers import _token_overlap_ratio

logger = logging.getLogger(__name__)


def eval_fault_tolerance(
    tool_calls: list[dict[str, Any]],
    config: Any,
) -> dict[str, Any]:
    """도구 호출 실패 후 폴백·복구 시도 여부를 평가.

    Args:
        tool_calls: 도구 호출 리스트. 각 항목은 {"name": str, "success": bool, ...}.
        config: FaultToleranceConfig 인스턴스.

    Returns:
        {failures_detected, fallback_attempts, recovery_rate, grade}
    """
    if not tool_calls:
        return {"failures_detected": False, "fallback_attempts": 0, "recovery_rate": 1.0, "grade": "none"}

    failed_indices: list[int] = []
    for i, tc in enumerate(tool_calls):
        if isinstance(tc, dict) and not tc.get("success", True):
            failed_indices.append(i)

    if not failed_indices:
        return {"failures_detected": False, "fallback_attempts": 0, "recovery_rate": 1.0, "grade": "good"}

    # check_fallback_attempts=False: 폴백 탐지 건너뜀
    if not getattr(config, "check_fallback_attempts", True):
        return {
            "failures_detected": True,
            "fallback_attempts": 0,
            "recovery_rate": 0.0,
            "grade": "untracked",
        }

    # expected_fallback_tools: {failed_tool_name: [allowed_fallback_names]}
    expected_fallbacks: dict[str, list[str]] = getattr(config, "expected_fallback_tools", {}) or {}

    # 폴백 탐지: 실패 직후 다른 도구 호출 시 폴백으로 간주
    fallback_attempts = 0
    recovered = 0
    wrong_fallbacks: list[str] = []
    for fi in failed_indices:
        next_idx = fi + 1
        if next_idx < len(tool_calls):
            next_tc = tool_calls[next_idx]
            failed_name = tool_calls[fi].get("name", "")
            next_name = next_tc.get("name", "") if isinstance(next_tc, dict) else ""
            # 다른 이름의 도구 호출 = 폴백 시도
            if next_name and next_name != failed_name:
                fallback_attempts += 1
                # expected_fallback_tools가 있으면 올바른 폴백인지 추가 검증
                if expected_fallbacks and failed_name in expected_fallbacks:
                    allowed = expected_fallbacks[failed_name]
                    if next_name not in allowed:
                        wrong_fallbacks.append(
                            f"{failed_name}→{next_name} (허용: {allowed})"
                        )
                        # 잘못된 폴백은 복구 실패로 처리
                        continue
                if isinstance(next_tc, dict) and next_tc.get("success", True):
                    recovered += 1

    recovery_rate = recovered / len(failed_indices) if failed_indices else 1.0

    if fallback_attempts == 0:
        grade = "poor"
    elif wrong_fallbacks:
        grade = "wrong_fallback"
    elif recovery_rate >= config.partial_success_threshold:
        grade = "good"
    else:
        grade = "partial"

    result_dict: dict[str, Any] = {
        "failures_detected": True,
        "fallback_attempts": fallback_attempts,
        "recovery_rate": recovery_rate,
        "grade": grade,
    }
    if wrong_fallbacks:
        result_dict["wrong_fallbacks"] = wrong_fallbacks
    # score_recovery_quality=True: grade를 0~1 점수로 변환해 추가
    if getattr(config, "score_recovery_quality", True):
        if grade == "wrong_fallback":
            # C-5: 이분법(any wrong → 0.2) 대신 wrong_fallback 비율에 비례한 블렌딩 점수 산출.
            # wrong_rate = (잘못된 폴백 수) / (총 폴백 시도 수)
            # blended = (1 - wrong_rate) × recovery_rate + wrong_rate × 0.2
            # 예) 10회 폴백 중 1회 잘못 → wrong_rate=0.1 → score≈0.83 (0.2 대신)
            # 예) 전부 잘못 → wrong_rate=1.0 → score=0.2 (기존과 동일)
            _wrong_rate = len(wrong_fallbacks) / max(fallback_attempts, 1)
            _blended = (1.0 - _wrong_rate) * recovery_rate + _wrong_rate * 0.2
            result_dict["recovery_quality_score"] = round(min(1.0, max(0.0, _blended)), 4)
            result_dict["wrong_fallback_rate"] = round(_wrong_rate, 4)
        else:
            _grade_to_score = {"good": 1.0, "partial": 0.5, "poor": 0.0, "none": 1.0, "untracked": 0.5}
            result_dict["recovery_quality_score"] = _grade_to_score.get(grade, 0.5)
    return result_dict


def compute_reproducibility_score(
    responses: list[str],
    measure: str = "token_f1",
) -> dict[str, Any]:
    """여러 번 실행된 응답 간의 유사도로 재현성 점수를 계산.

    Args:
        responses: 동일 입력에 대한 반복 응답 리스트.
        measure: 유사도 측정 방식 ("token_f1"|"jaccard"|"exact").

    Returns:
        {score, variance, pairwise_scores, run_count}
    """
    # C-4: 인식 불가 measure 값 → 경고 없이 token_f1 폴백 시 사용자가 잘못된 값 지정 사실을 인식 못함
    _VALID_MEASURES = {"token_f1", "jaccard", "exact"}
    if measure not in _VALID_MEASURES:
        import warnings as _w
        _w.warn(
            f"compute_reproducibility_score: measure={measure!r}는 유효하지 않습니다. "
            f"유효한 값: {sorted(_VALID_MEASURES)}. 'token_f1'로 폴백합니다.",
            UserWarning,
            stacklevel=2,
        )
        measure = "token_f1"

    run_count = len(responses)
    if run_count < 2:
        if run_count == 0:
            logger.warning(
                "compute_reproducibility_score: responses 리스트가 비어 있습니다. "
                "score=1.0 반환 — 재현성 측정이 실행되지 않았습니다."
            )
        elif run_count == 1:
            logger.warning(
                "compute_reproducibility_score: run_count=1이면 재현성을 측정할 수 없습니다. "
                "ReproducibilityConfig(runs=2) 이상으로 설정하세요. score=1.0 반환."
            )
        return {"score": 1.0, "variance": 0.0, "pairwise_scores": [], "run_count": run_count}

    def _sim(a: str, b: str) -> float:
        if measure == "exact":
            return 1.0 if a == b else 0.0
        elif measure == "jaccard":
            s1, s2 = set(a.lower().split()), set(b.lower().split())
            if not s1 and not s2:
                return 1.0
            return len(s1 & s2) / len(s1 | s2) if s1 | s2 else 0.0
        else:  # token_f1 (default)
            return _token_overlap_ratio(a, b)

    pairwise: list[float] = []
    for i in range(run_count):
        for j in range(i + 1, run_count):
            pairwise.append(_sim(responses[i], responses[j]))

    score = sum(pairwise) / len(pairwise) if pairwise else 1.0
    variance = sum((s - score) ** 2 for s in pairwise) / len(pairwise) if pairwise else 0.0

    return {
        "score": score,
        "variance": variance,
        "pairwise_scores": pairwise,
        "run_count": run_count,
    }


def eval_graceful_degradation(
    response: str,
    tool_calls: list[Any],
    has_error: bool,
    execution_time: float,
    config: Any,
) -> dict[str, Any]:
    """장애/저하 상황에서의 응답 품질을 평가한다.

    Args:
        response: 에이전트 응답 문자열.
        tool_calls: 도구 호출 리스트.
        has_error: 에러 발생 여부.
        execution_time: 실행 시간(밀리초).
        config: GracefulDegradationConfig 인스턴스.

    Returns:
        {degradation_score, mode, is_empty, acknowledged_error, has_partial_result, timeout_fallback}
    """
    response_lower = (response or "").lower()
    is_empty = not bool((response or "").strip())

    # Detect partial result markers
    has_partial_result = any(
        m.lower() in response_lower for m in (config.partial_result_markers or [])
    )

    # Detect error acknowledgment (conditional on check_error_acknowledgment flag)
    check_ack = bool(getattr(config, "check_error_acknowledgment", True))
    error_ack_markers = [
        "error", "failed", "unable", "cannot", "sorry", "오류", "실패", "불가", "죄송"
    ]
    acknowledged_error = (
        check_ack and any(m in response_lower for m in error_ack_markers)
    )

    # Compute degradation score
    if is_empty:
        score = max(config.quality_floor, max(0.0, 1.0 - config.empty_response_penalty))
        mode = "empty"
    elif has_error and has_partial_result:
        score = max(config.quality_floor, 0.6)
        mode = "partial"
    elif has_error and acknowledged_error:
        score = max(config.quality_floor, 0.5)
        mode = "acknowledged"
    elif has_error:
        score = config.quality_floor
        mode = "degraded"
    elif has_partial_result:
        # C-9: has_error=False이더라도 에이전트가 스스로 '부분 결과'를 명시한 경우 1.0 미만 처리.
        # 예) "부분적으로 완료했습니다" 응답 → mode="partial_self_reported", score=0.7
        # has_error=True 브랜치(0.6)보다 높되 완전 성공(1.0)보다 낮게 설정.
        score = max(config.quality_floor, 0.7)
        mode = "partial_self_reported"
    else:
        score = 1.0
        mode = "normal"

    # Timeout fallback detection
    timeout_fallback = False
    if config.detect_timeout_fallback:
        # Check 1: execution_time이 timeout_threshold_ms를 초과하면 타임아웃으로 판정
        _timeout_ms = getattr(config, "timeout_threshold_ms", None)
        if _timeout_ms is not None and execution_time > float(_timeout_ms):
            timeout_fallback = True
        # Check 2: 도구명에 "fallback"/"default" 포함 여부
        if not timeout_fallback and tool_calls:
            tool_names_fb = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    n = tc.get("name") or tc.get("tool", "")
                elif hasattr(tc, "name"):
                    n = getattr(tc, "name", "")
                else:
                    n = str(tc)
                tool_names_fb.append(n)
            timeout_fallback = any(
                "fallback" in n.lower() or "default" in n.lower() for n in tool_names_fb
            )

    return {
        "degradation_score": round(score, 4),
        "mode": mode,
        "is_empty": is_empty,
        "acknowledged_error": acknowledged_error,
        "has_partial_result": has_partial_result,
        "timeout_fallback": timeout_fallback,
    }


def eval_retry_consistency(task_result: Any, config: Any) -> dict[str, Any] | None:
    """재시도 일관성 평가 (Harness C — Reliability).

    단일 태스크의 시도 횟수와 성공 여부를 기반으로 재시도 효율성을 산출한다.

    Args:
        task_result: ``TaskResult`` 인스턴스.
        config: :class:`RetryConsistencyConfig` 인스턴스.

    Returns:
        Dict with keys: consistency_score, attempts, succeeded, retry_efficient.
        시도 횟수가 ``min_retry_count`` 미만이면 ``None`` 반환.
    """
    attempts = int(getattr(task_result, "attempts", 1) or 1)

    if attempts < config.min_retry_count:
        return None

    success = bool(getattr(task_result, "success", True))
    accuracy = float(getattr(task_result, "accuracy_score", 0.0) or 0.0)

    if success:
        # Success in fewer attempts = better consistency.
        # Floor at 0.1 so a successful task (however many retries) never scores 0.0
        # like a complete failure does.
        efficiency = max(0.1, 1.0 - (attempts - 1) * 0.15)
        consistency_score = efficiency
    else:
        # Failed despite retries — use accuracy as consistency proxy
        if config.penalize_degradation:
            consistency_score = max(0.0, accuracy - config.improvement_threshold)
        else:
            # penalize_degradation=False: 패널티 없음 — accuracy 그대로 사용
            consistency_score = accuracy

    # C-16: defense-in-depth — accuracy_score > 1.0 이거나 penalize_degradation=False 경로에서
    # consistency_score가 1.0을 초과할 수 있음. Config 검증(C11)과 무관하게 클램핑.
    return {
        "consistency_score": round(min(1.0, max(0.0, consistency_score)), 4),
        "attempts": attempts,
        "succeeded": success,
        "retry_efficient": success and attempts <= 2,
        # 세션 수준 집계에 필요한 Config 요약
        "_config": {
            "group_by_task_prefix": bool(getattr(config, "group_by_task_prefix", True)),
            "improvement_threshold": float(getattr(config, "improvement_threshold", 0.1)),
            "penalize_degradation": bool(getattr(config, "penalize_degradation", True)),
        },
    }


def eval_idempotency(
    tool_calls: list[Any], response: str, config: Any
) -> dict[str, Any]:
    """Evaluate whether the task is safe to retry without side effects.

    Args:
        tool_calls: 도구 호출 목록.
        response: 에이전트 응답 텍스트.
        config: :class:`~agent_evaluator.IdempotencyConfig` 인스턴스.

    Returns:
        idempotency_score, non_idempotent_tools, duplicate_detected, safe_to_retry,
        non_idempotent_count 를 담은 딕셔너리.
    """
    tool_names: list[str] = []
    for tc in (tool_calls or []):
        if isinstance(tc, dict):
            # B-51: tc["function"]이 string이면 str.get() → AttributeError
            _fn = tc.get("function")
            name = (tc.get("name") or tc.get("tool")
                    or (_fn.get("name", "") if isinstance(_fn, dict) else (_fn or "")))
        elif hasattr(tc, "name"):
            name = getattr(tc, "name", "")
        else:
            name = str(tc)
        if name:
            tool_names.append(name)

    # Check for non-idempotent tool patterns
    # 토큰 단위 매칭: "recreate_session"에서 "create"가 오탐되지 않도록 구분자(_-/.)로 분리 후 정확 매칭
    non_idempotent_tools: list[str] = []
    _idem_sep_re = re.compile(r"[_\-\/\.\s]+")
    for tool_name in tool_names:
        _parts = _idem_sep_re.split(tool_name.lower())
        for pattern in (config.non_idempotent_patterns or []):
            if pattern.lower() in _parts:
                non_idempotent_tools.append(tool_name)
                break

    # Check if response indicates duplicate was detected
    response_lower = (response or "").lower()
    duplicate_detected = any(
        m.lower() in response_lower for m in (config.duplicate_detection_markers or [])
    )

    # Compute score
    penalty = len(set(non_idempotent_tools)) * config.non_idempotent_penalty
    base_score = max(0.0, 1.0 - penalty)
    # Bonus: agent self-detected duplicate (shows awareness)
    if duplicate_detected and non_idempotent_tools:
        base_score = min(1.0, base_score + 0.1)

    safe_to_retry = len(non_idempotent_tools) == 0 or duplicate_detected

    return {
        "idempotency_score": round(base_score, 4),
        "non_idempotent_tools": list(set(non_idempotent_tools)),
        "duplicate_detected": duplicate_detected,
        "safe_to_retry": safe_to_retry,
        "non_idempotent_count": len(set(non_idempotent_tools)),
    }
