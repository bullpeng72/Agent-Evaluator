"""
agent_evaluator.gates.gate_d_performance.evaluators
======================================================
Gate D(Performance Contract) 평가 함수 3종.

SPEC-000: agent_evaluator/helpers/taskresult_helpers.py에서 그대로 이관(로직 변경 없음).
taskresult_helpers.py는 이 모듈을 re-export하여 하위호환을 유지한다.

eval_sla의 반환 dict(특히 "_config" 서브딕셔너리)는 Gate C(Reliability)의 SLA breach rate
집계에도 사용된다 — SLAConfig의 이중 귀속(CLAUDE.md "SLAConfig dual contribution") 참조.
"""
from __future__ import annotations

from typing import Any


def eval_sla(
    execution_time_s: float,
    tokens_used: Any,
    cost_usd: float | None,
    config: Any,
    ttft_ms: float | None = None,
) -> dict[str, Any]:
    """SLA 준수 여부 단일 태스크 수준 평가.

    Args:
        execution_time_s: 실행 시간(초).
        tokens_used: 사용 토큰 수 (int 또는 dict).
        cost_usd: 태스크당 비용 (없으면 None).
        config: SLAConfig 인스턴스.
        ttft_ms: Time To First Token (ms). None이면 검사 생략.

    Returns:
        {sla_met, breaches, latency_ok, cost_ok, token_ok, ttft_ok, execution_time_s, cost_usd}
    """
    # C-19: `or 5000.0` 패턴은 None/0.0 모두 폴백으로 처리해 p95_ms=0.0 명시 설정을 덮어씀
    # None만 폴백하도록 수정: 0.0은 "지연 0ms 초과시 breach" 의미로 유효한 설정임
    _p95_raw = getattr(config, "p95_ms", None)
    _p99_raw = getattr(config, "p99_ms", None)
    p95_ms = float(_p95_raw) if _p95_raw is not None else 5000.0
    p99_ms = float(_p99_raw) if _p99_raw is not None else 10000.0
    max_cost = getattr(config, "max_cost_per_task", None)
    token_limit = getattr(config, "token_limit", None)
    ttft_threshold = getattr(config, "ttft_ms", None)

    actual_ms = execution_time_s * 1000.0
    breaches: list[str] = []

    latency_ok = actual_ms <= p95_ms and actual_ms <= p99_ms
    if actual_ms > p95_ms:
        breaches.append(f"latency {actual_ms:.0f}ms > p95 {p95_ms:.0f}ms")
    if actual_ms > p99_ms:
        breaches.append(f"latency {actual_ms:.0f}ms > p99 {p99_ms:.0f}ms")

    cost_ok = True
    if max_cost is not None and cost_usd is not None:
        cost_ok = float(cost_usd) <= float(max_cost)
        if not cost_ok:
            breaches.append(f"cost ${cost_usd:.5f} > max ${max_cost:.5f}")

    # token_limit 검사
    token_ok = True
    if token_limit is not None:
        _total_tokens: int = 0
        if isinstance(tokens_used, dict):
            # C-23: `tokens_used.get("total") or fallback` 패턴은 total=0(0토큰)을
            # falsy로 처리해 input+output 합산으로 폴백 → 잘못된 breach 발생.
            # None-only 폴백으로 수정: total=0은 유효한 "0 토큰 사용" 값임.
            _raw_total = tokens_used.get("total")
            if _raw_total is not None:
                try:
                    _total_tokens = int(_raw_total)
                except (TypeError, ValueError):
                    _total_tokens = 0
            else:
                _total_tokens = int(
                    tokens_used.get("input", 0) + tokens_used.get("output", 0)
                )
        else:
            try:
                _total_tokens = int(tokens_used or 0)
            except (TypeError, ValueError):
                _total_tokens = 0
        token_ok = _total_tokens <= int(token_limit)
        if not token_ok:
            breaches.append(f"tokens {_total_tokens} > limit {token_limit}")

    # TTFT 검사 (ttft_ms 파라미터 또는 SLAConfig.ttft_ms 사용)
    ttft_ok = True
    _actual_ttft = ttft_ms
    _ttft_limit = ttft_threshold
    if _actual_ttft is not None and _ttft_limit is not None:
        ttft_ok = float(_actual_ttft) <= float(_ttft_limit)
        if not ttft_ok:
            breaches.append(f"ttft {_actual_ttft:.0f}ms > limit {_ttft_limit:.0f}ms")

    return {
        "sla_met": len(breaches) == 0,
        "breaches": breaches,
        "latency_ok": latency_ok,
        "cost_ok": cost_ok,
        "token_ok": token_ok,
        "ttft_ok": ttft_ok,
        "execution_time_s": round(execution_time_s, 4),
        "cost_usd": round(float(cost_usd), 6) if cost_usd is not None else None,
        # 세션 수준 집계에 필요한 Config 요약 (_compute_harness_groups에서 사용)
        "_config": {
            "breach_window": int(getattr(config, "breach_window", 10)),
            "warn_threshold": int(getattr(config, "warn_threshold", 2)),
            "fail_threshold": int(getattr(config, "fail_threshold", 5)),
            "budget_usd": getattr(config, "budget_usd", None),
            # Gate D p95 정규화 임계값으로 사용 (_compute_harness_groups에서 참조)
            # C-19 동일 수정: None만 폴백, 0.0은 유효한 설정
            "p95_ms": p95_ms,
        },
    }


def eval_efficiency(
    completion_score: float,
    tokens_used: int,
    execution_time_s: float,
    cost_usd: float | None,
    config: Any,
) -> dict[str, Any]:
    """비용 대비 완료율(ROI) 단일 태스크 수준 평가.

    Args:
        completion_score: 완료율 (0.0–1.0).
        tokens_used: 사용 토큰 수.
        execution_time_s: 실행 시간(초).
        cost_usd: 비용(USD). None이면 tokens_used로 대체.
        config: EfficiencyConfig 인스턴스.

    Returns:
        {efficiency_ratio, cost_value, cost_unit, cost_per_completion, penalized}
    """
    cost_unit: str = getattr(config, "cost_unit", "tokens") or "tokens"
    penalize_failed: bool = getattr(config, "penalize_failed_tokens", True)

    # D-EFF-1: `or` 패턴은 total=0(명시적 0토큰)을 falsy로 처리해 input+output으로 폴백 — 버그.
    # eval_sla(C-23)·_compute_harness_groups(D-1)과 동일한 None-only 폴백으로 수정한다.
    _tokens_int: int
    if isinstance(tokens_used, dict):
        _raw_total_eff = tokens_used.get("total")
        _tokens_int = (
            int(_raw_total_eff) if _raw_total_eff is not None
            else int(tokens_used.get("input", 0) + tokens_used.get("output", 0))
        )
    else:
        _tokens_int = int(tokens_used or 0)
    if cost_unit == "usd":
        if cost_usd is not None:
            cost_value = float(cost_usd)
        else:
            # D-D: cost_unit="usd"이지만 cost_usd 미측정 시 `else` 분기로 token 수가
            # cost_value로 사용됨 → cost_unit 레이블("usd")과 실제 단위(tokens) 불일치.
            # target_cost_per_completion이 USD 기준이면 비교 자체가 무의미.
            # cost_value=0.0으로 설정 → ratio=None → Gate D 집계 제외.
            cost_value = 0.0
    elif cost_unit == "time_ms":
        cost_value = execution_time_s * 1000.0
    else:
        cost_value = float(_tokens_int)

    # 실패한 태스크 패널티 (completion_score=0 이면 비용은 낭비)
    penalized = penalize_failed and completion_score < 0.1

    # efficiency = completion_score / cost
    # cost_value=0은 tokens_used=0/None 등 측정 불가 상황 — ratio=None으로 집계 제외
    ratio: float | None
    if cost_value <= 0:
        ratio = None
    else:
        ratio = completion_score / cost_value

    # 패널티 적용: 완전 실패 태스크는 ratio를 0으로 처리
    # cost_value=0(ratio=None)인 경우는 측정 불가이므로 패널티 대상에서 제외
    if penalized and ratio is not None:
        ratio = 0.0

    # cost_per_completion: completion_score 1.0 달성에 필요한 비용 추정
    cost_per_completion = cost_value / completion_score if cost_value > 0 and completion_score > 0 else float("inf")

    # target_cost_per_completion 기반 calibrated_score 계산
    # warn_ratio / fail_ratio: 목표 대비 몇 배 비싸면 경고/실패로 판정할지
    target = getattr(config, "target_cost_per_completion", None)
    warn_ratio = float(getattr(config, "warn_ratio", 2.0) or 2.0)
    fail_ratio = float(getattr(config, "fail_ratio", 4.0) or 4.0)
    calibrated_score: float | None = None
    efficiency_grade: str = "n/a"

    # D-C: penalized=True이면 efficiency_ratio=0.0(패널티)이지만 calibrated_score는
    # 실제 cost_per_completion 기반으로 계산되어 의도치 않게 높은 값이 나올 수 있음.
    # (예: completion=0.05, cost_usd=0.001, target=0.01 → calibrated_score=0.7 "good")
    # Gate D는 calibrated_score 우선 사용하므로 실패 태스크가 좋은 점수를 받게 됨.
    # 패널티 태스크는 calibrated_score도 0.0으로 명시해 두 경로 일관성 확보.
    if penalized:
        calibrated_score = 0.0
        efficiency_grade = "penalized"

    if not penalized and target is not None and float(target) > 0 and cost_per_completion != float("inf"):
        target_f = float(target)
        ratio_vs_target = cost_per_completion / target_f
        if ratio_vs_target <= 1.0:
            calibrated_score = 1.0
            efficiency_grade = "excellent"
        elif ratio_vs_target <= warn_ratio:
            # 1.0 → warn_ratio 구간을 선형으로 1.0 → 0.7 매핑
            calibrated_score = 1.0 - 0.3 * (ratio_vs_target - 1.0) / max(warn_ratio - 1.0, 1e-6)
            efficiency_grade = "good"
        elif ratio_vs_target <= fail_ratio:
            # warn_ratio → fail_ratio 구간을 0.7 → 0.3 매핑
            calibrated_score = 0.7 - 0.4 * (ratio_vs_target - warn_ratio) / max(fail_ratio - warn_ratio, 1e-6)
            efficiency_grade = "warn"
        else:
            calibrated_score = max(0.0, 0.3 - 0.3 * (ratio_vs_target - fail_ratio) / max(fail_ratio, 1e-6))
            efficiency_grade = "fail"

    result: dict[str, Any] = {
        "efficiency_ratio": round(ratio, 8) if ratio is not None else None,
        "cost_value": round(cost_value, 4),
        "cost_unit": cost_unit,
        "cost_per_completion": round(cost_per_completion, 4) if cost_per_completion != float("inf") else None,
        "completion_score": round(completion_score, 4),
        "penalized": penalized,
    }
    if calibrated_score is not None:
        result["calibrated_score"] = round(calibrated_score, 4)
        result["efficiency_grade"] = efficiency_grade
    _fallback_ref = getattr(config, "fallback_reference_cost_per_completion", None)
    if _fallback_ref is not None:
        # Gate D 집계(gate_d_performance/aggregate.py)가 calibrated_score 없는 태스크의
        # efficiency_ratio 정규화 기준값으로 참조 — eval_sla의 "_config" 패턴과 동일.
        result["_config"] = {"fallback_reference_cost_per_completion": float(_fallback_ref)}
    return result


def eval_resource_budget(
    tokens_used: int,
    cost_usd: float,
    elapsed_ms: float,
    config: Any,
    task_succeeded: bool = True,
) -> dict[str, Any]:
    """정의된 예산 한도에 대한 리소스 소비를 평가한다.

    Args:
        tokens_used: 사용된 토큰 수.
        cost_usd: 비용 (USD).
        elapsed_ms: 경과 시간 (밀리초).
        config: ResourceBudgetConfig 인스턴스.
        task_succeeded: 태스크 성공 여부 (count_failed_tokens=False 시 실패 토큰 제외).

    Returns:
        {budget_score, token_utilization, cost_utilization, time_utilization, over_budget, warnings}
    """
    warnings_list: list[str] = []
    over_budget = False
    count_failed = bool(getattr(config, "count_failed_tokens", True))

    # When count_failed_tokens=False and task failed, exclude token/cost from budget scoring
    # D-A: cost_usd=None(미측정) 시 None이 그대로 전파되면 _utilization(None, limit)에서
    # None/float → TypeError 발생. _consumed 저장과 동일하게 None→0.0 변환.
    _effective_tokens = float(tokens_used) if (count_failed or task_succeeded) else 0.0
    _effective_cost = (
        float(cost_usd) if (count_failed or task_succeeded) and cost_usd is not None else 0.0
    )

    def _utilization(used: float, limit: float | None) -> float | None:
        if limit is None or limit <= 0:
            return None
        return used / limit

    token_util = _utilization(
        _effective_tokens,
        float(config.max_tokens) if config.max_tokens is not None else None,
    )
    cost_util = _utilization(_effective_cost, config.max_cost_usd)
    time_util = _utilization(elapsed_ms, config.max_execution_time_ms)

    for name, util in [("tokens", token_util), ("cost", cost_util), ("time", time_util)]:
        if util is None:
            continue
        if util > 1.0:
            warnings_list.append(f"over_budget:{name}:{util:.2f}x")
            over_budget = True
        elif util >= config.warn_at_pct:
            warnings_list.append(f"warn:{name}:{util:.1%}")

    # Budget score: worst-case utilization drives score.
    # If no limits are configured, return None so Gate D excludes this from aggregation
    # rather than inflating the score with an artificial 1.0.
    utils = [u for u in [token_util, cost_util, time_util] if u is not None]
    if utils:
        budget_score: float | None = max(0.0, 1.0 - max(utils))
    else:
        budget_score = None

    return {
        "budget_score": round(budget_score, 4) if budget_score is not None else None,
        "token_utilization": round(token_util, 4) if token_util is not None else None,
        "cost_utilization": round(cost_util, 4) if cost_util is not None else None,
        "time_utilization": round(time_util, 4) if time_util is not None else None,
        "over_budget": over_budget,
        "warnings": warnings_list,
        # 세션 수준 rollover 집계에 필요한 Config 요약
        "_config": {
            "rollover": bool(getattr(config, "rollover", False)),
            "max_tokens": getattr(config, "max_tokens", None),
            "max_cost_usd": getattr(config, "max_cost_usd", None),
            "max_execution_time_ms": getattr(config, "max_execution_time_ms", None),
        },
        # rollover 계산용 실제 소비량 보존
        "_consumed": {
            "tokens": float(tokens_used) if task_succeeded or count_failed else 0.0,
            "cost_usd": float(cost_usd) if (task_succeeded or count_failed) and cost_usd is not None else 0.0,
            "time_ms": float(elapsed_ms),
        },
    }
