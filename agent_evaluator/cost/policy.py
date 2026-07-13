"""
CostTracker & AdaptivePolicy — Phase 3-C 평가 비용 최적화

LLM 기반 평가(LLM Judge, DeepEval 등) 비용을 추적하고
이상 감지 상태에 따라 샘플링률을 자동 조정한다.
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from enum import Enum
from typing import Any

from agent_evaluator.exceptions import ValidationError


class SamplingStage(str, Enum):
    DEFAULT = "default"          # 기본 샘플링률
    ANOMALY = "anomaly"          # 이상 감지 시 높은 샘플링률
    BUDGET_EXCEEDED = "budget_exceeded"  # 예산 초과 시 샘플링 중단


class CostTracker:
    """공급자별 LLM 평가 비용 추적.

    Example::
        tracker = CostTracker(budget_per_day=5.0)
        tracker.record(provider="anthropic", model="claude-haiku-4-5", cost_usd=0.001)
        stats = tracker.get_daily_stats()
    """

    def __init__(self, budget_per_day: float | None = None, alert_at: float = 0.8) -> None:
        """
        Args:
            budget_per_day: 일 예산 USD 한도. None이면 한도 없음.
            alert_at: 예산 소진 경고 비율 (0.0~1.0). Default 0.8.
        """
        if alert_at < 0.0 or alert_at > 1.0:
            raise ValidationError(f"alert_at must be in [0.0, 1.0], got {alert_at}")
        self.budget_per_day = budget_per_day
        self.alert_at = alert_at
        self._records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, provider: str, model: str, cost_usd: float,
               input_tokens: int = 0, output_tokens: int = 0,
               evaluation_type: str = "llm_judge") -> None:
        """비용 기록.

        Args:
            provider: 공급자 이름 ("anthropic", "openai").
            model: 모델 이름.
            cost_usd: 비용 (USD).
            input_tokens: 입력 토큰 수.
            output_tokens: 출력 토큰 수.
            evaluation_type: 평가 유형 ("llm_judge", "deepeval", "ragas").
        """
        entry = {
            "provider": provider,
            "model": model,
            "cost_usd": cost_usd,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "evaluation_type": evaluation_type,
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
        }
        with self._lock:
            self._records.append(entry)

    def get_today_cost(self) -> float:
        today = date.today().isoformat()
        with self._lock:
            return sum(r["cost_usd"] for r in self._records if r.get("date") == today)

    def is_budget_exceeded(self) -> bool:
        if self.budget_per_day is None:
            return False
        return self.get_today_cost() >= self.budget_per_day

    def is_budget_alert(self) -> bool:
        if self.budget_per_day is None:
            return False
        return self.get_today_cost() >= self.budget_per_day * self.alert_at

    def get_daily_stats(self) -> dict[str, Any]:
        today = date.today().isoformat()
        with self._lock:
            today_records = [r for r in self._records if r.get("date") == today]
            all_records = list(self._records)

        today_total = sum(r["cost_usd"] for r in today_records)
        by_provider: dict[str, float] = {}
        by_type: dict[str, float] = {}
        for r in today_records:
            p = r["provider"]
            t = r["evaluation_type"]
            by_provider[p] = by_provider.get(p, 0.0) + r["cost_usd"]
            by_type[t] = by_type.get(t, 0.0) + r["cost_usd"]

        budget_remaining = None
        if self.budget_per_day is not None:
            budget_remaining = max(0.0, self.budget_per_day - today_total)

        # 7일 일별 추이
        daily_history: dict[str, float] = {}
        for r in all_records:
            d = r.get("date", "")
            daily_history[d] = daily_history.get(d, 0.0) + r["cost_usd"]

        return {
            "today_total_usd": round(today_total, 6),
            "budget_per_day": self.budget_per_day,
            "budget_remaining_usd": round(budget_remaining, 6) if budget_remaining is not None else None,
            "budget_alert": self.is_budget_alert(),
            "budget_exceeded": self.is_budget_exceeded(),
            "by_provider": {k: round(v, 6) for k, v in by_provider.items()},
            "by_evaluation_type": {k: round(v, 6) for k, v in by_type.items()},
            "today_call_count": len(today_records),
            "daily_history": {k: round(v, 6) for k, v in sorted(daily_history.items())},
        }

    def get_all_records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


    def learn_cost_model(self, tasks: list) -> dict[str, float]:
        """태스크 결과에서 모델별 비용을 학습한다 (F2)."""
        _model_costs: dict[str, list] = {}
        _model_tokens: dict[str, int] = {}
        for t in tasks:
            _tu = getattr(t, "tokens_used", {}) or {}
            if not isinstance(_tu, dict):
                continue
            _model = str(_tu.get("model", "unknown"))
            _total_tok = int(_tu.get("total", 0) or 0)
            _extra = getattr(t, "extra", {}) or {}
            _cost = float(_extra.get("cost_usd", 0) or _tu.get("cost_usd", 0) or 0)
            if _total_tok > 0 and _cost > 0:
                _model_costs.setdefault(_model, []).append(_cost)
                _model_tokens[_model] = _model_tokens.get(_model, 0) + _total_tok
        _learned: dict[str, float] = {}
        for _m, _costs in _model_costs.items():
            _total_cost = sum(_costs)
            _total_tok = _model_tokens.get(_m, 1)
            _learned[_m] = round(_total_cost / (_total_tok / 1000), 8)
        self._learned_prices = _learned
        return _learned

    @property
    def auto_price_map(self) -> dict[str, float]:
        """학습된 가격과 기본 가격을 병합해 반환한다 (F2)."""
        _base = {
            "claude-opus-4-6": 0.015,
            "claude-sonnet-4-6": 0.003,
            "claude-haiku-4-5": 0.00025,
            "gpt-4o": 0.005,
            "gpt-4o-mini": 0.00015,
        }
        _base.update(getattr(self, "_learned_prices", {}))
        return _base


class AdaptivePolicy:
    """이상 감지 상태에 따라 샘플링률을 자동 조정하는 정책.

    Args:
        default_sample_rate: 기본 샘플링률 (0.0~1.0). Default 0.1.
        anomaly_sample_rate: 이상 감지 시 샘플링률. Default 1.0.
        budget_per_day: 일 예산 한도 USD. Default None.
        alert_at: 예산 경고 비율. Default 0.8.

    Example::
        policy = AdaptivePolicy(default_sample_rate=0.1, anomaly_sample_rate=1.0, budget_per_day=5.0)
        monitor = PerformanceMonitor(
            enable_llm_judge=True,
            judge_sample_rate=policy.current_sample_rate,
            judge_budget_per_day=5.0,
        )
        # 이상 감지 시:
        policy.enter_anomaly_mode()
        monitor.judge_sample_rate = policy.current_sample_rate
    """

    def __init__(
        self,
        default_sample_rate: float = 0.1,
        anomaly_sample_rate: float = 1.0,
        budget_per_day: float | None = None,
        alert_at: float = 0.8,
    ) -> None:
        for rate, name in [(default_sample_rate, "default_sample_rate"), (anomaly_sample_rate, "anomaly_sample_rate")]:
            if not (0.0 <= rate <= 1.0):
                raise ValidationError(f"{name} must be in [0.0, 1.0], got {rate}")

        self.default_sample_rate = default_sample_rate
        self.anomaly_sample_rate = anomaly_sample_rate
        self.cost_tracker = CostTracker(budget_per_day=budget_per_day, alert_at=alert_at)
        self._stage = SamplingStage.DEFAULT
        self._stage_history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def current_stage(self) -> SamplingStage:
        with self._lock:
            return self._stage

    @property
    def current_sample_rate(self) -> float:
        stage = self.current_stage
        if stage == SamplingStage.BUDGET_EXCEEDED:
            return 0.0
        if stage == SamplingStage.ANOMALY:
            return self.anomaly_sample_rate
        return self.default_sample_rate

    def enter_anomaly_mode(self, reason: str = "") -> None:
        """이상 감지 시 높은 샘플링률 단계로 전환."""
        self._transition(SamplingStage.ANOMALY, reason)

    def exit_anomaly_mode(self) -> None:
        """이상 상태 해소 시 기본 단계로 복귀."""
        if self.cost_tracker.is_budget_exceeded():
            self._transition(SamplingStage.BUDGET_EXCEEDED, "budget exceeded after anomaly")
        else:
            self._transition(SamplingStage.DEFAULT, "anomaly resolved")

    def check_budget(self) -> None:
        """예산 상태를 확인하고 필요 시 샘플링 중단 단계로 전환."""
        if self.cost_tracker.is_budget_exceeded():
            self._transition(SamplingStage.BUDGET_EXCEEDED, "daily budget exceeded")

    def _transition(self, new_stage: SamplingStage, reason: str) -> None:
        with self._lock:
            if self._stage == new_stage:
                return
            old_stage = self._stage
            self._stage = new_stage
            self._stage_history.append({
                "from": old_stage.value,
                "to": new_stage.value,
                "reason": reason,
                "at": datetime.now().isoformat(),
            })

    def get_status(self) -> dict[str, Any]:
        """현재 정책 상태 반환."""
        return {
            "stage": self.current_stage.value,
            "current_sample_rate": self.current_sample_rate,
            "default_sample_rate": self.default_sample_rate,
            "anomaly_sample_rate": self.anomaly_sample_rate,
            "cost": self.cost_tracker.get_daily_stats(),
            "stage_history": list(self._stage_history[-10:]),  # 최근 10개
        }


    def learn_cost_model(self, tasks: list) -> dict[str, float]:
        """태스크 결과에서 모델별 비용을 학습한다 (F2).

        각 태스크의 ``tokens_used["model"]`` 과 ``extra["cost_usd"]`` 또는
        ``tokens_used["cost_usd"]`` 에서 실제 비용을 추출하고, 1k 토큰당 비용을 계산한다.

        Args:
            tasks: TaskResult 리스트.

        Returns:
            ``{model_name: cost_per_1k_tokens}`` 딕셔너리.
        """
        _model_costs: dict[str, list] = {}
        _model_tokens: dict[str, int] = {}

        for t in tasks:
            _tu = getattr(t, "tokens_used", {}) or {}
            if not isinstance(_tu, dict):
                continue
            _model = str(_tu.get("model", "unknown"))
            _total_tok = int(_tu.get("total", 0) or 0)
            # cost_usd 추출: extra > tokens_used 순서
            _extra = getattr(t, "extra", {}) or {}
            _cost = float(_extra.get("cost_usd", 0) or _tu.get("cost_usd", 0) or 0)
            if _total_tok > 0 and _cost > 0:
                _model_costs.setdefault(_model, []).append(_cost)
                _model_tokens[_model] = _model_tokens.get(_model, 0) + _total_tok

        _learned: dict[str, float] = {}
        for _m, _costs in _model_costs.items():
            _total_cost = sum(_costs)
            _total_tok = _model_tokens.get(_m, 1)
            _learned[_m] = round(_total_cost / (_total_tok / 1000), 8)

        self._learned_prices = _learned
        return _learned

    @property
    def auto_price_map(self) -> dict[str, float]:
        """학습된 가격과 설정된 가격을 병합해 반환한다 (F2).

        학습된 가격이 설정된 가격보다 우선한다.

        Returns:
            ``{model_name: cost_per_1k_tokens}`` 딕셔너리.
        """
        _base = {
            "claude-opus-4-6": 0.015,
            "claude-sonnet-4-6": 0.003,
            "claude-haiku-4-5": 0.00025,
            "gpt-4o": 0.005,
            "gpt-4o-mini": 0.00015,
        }
        _base.update(getattr(self, "_learned_prices", {}))
        return _base
