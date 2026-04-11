"""tests/test_loader_parsers.py
================================
serve/loader.py 핵심 파서 회귀 방지 테스트.

이번 세션에서 발견·수정된 버그 2건을 포함한다:
  1. _parse_cost_data: pricing 키 우선 읽기 → evaluation_cost 미탐지 버그
  2. _parse_hallucination_detail: sentence_min_words < 5 → 탐지율 0 버그 (예제 수준)
"""
from __future__ import annotations

import pytest

from agent_evaluator.serve.loader import (
    _parse_cost_data,
    _parse_feedback_data,
    _parse_hallucination_detail,
)


# ---------------------------------------------------------------------------
# _parse_cost_data
# ---------------------------------------------------------------------------

class TestParseCostData:
    """regression: pricing 키가 있어도 evaluation_cost를 올바르게 파싱해야 한다."""

    def test_returns_empty_when_no_evaluation_cost(self):
        """evaluation_cost 키가 없으면 빈 dict 반환."""
        raw = {"pricing": {"input": 0.003, "output": 0.015}}
        assert _parse_cost_data(raw) == {}

    def test_pricing_only_does_not_produce_cost(self):
        """pricing만 있는 일반 결과 파일에서 has_cost가 False여야 한다."""
        raw = {
            "pricing": {"input": 0.003, "output": 0.015, "model": "gpt-4o"},
            "summary": {"task_count": 10},
        }
        result = _parse_cost_data(raw)
        assert result == {}

    def test_evaluation_cost_parsed_correctly(self):
        """evaluation_cost가 있으면 모든 필드를 올바르게 파싱한다."""
        raw = {
            "pricing": {"input": 0.003, "output": 0.015},
            "evaluation_cost": {
                "total_usd": 0.0305,
                "llm_judge_usd": 0.0,
                "by_provider": {"gpt-4o": 0.025, "claude-3-sonnet": 0.005},
                "call_count": 4,
                "model": "gpt-4o-mini",
                "budget_per_day": 10.0,
                "budget_remaining_usd": 9.97,
                "sample_rate_current": 0.1,
                "projected_daily_usd": 0.305,
            },
        }
        result = _parse_cost_data(raw)

        assert result["call_count"] == 4
        assert result["total_usd"] == pytest.approx(0.0305, abs=1e-5)
        assert result["by_provider"]["gpt-4o"] == pytest.approx(0.025, abs=1e-5)
        assert result["model"] == "gpt-4o-mini"
        assert result["budget_per_day"] == 10.0
        assert result["sample_rate_current"] == pytest.approx(0.1, abs=1e-5)

    def test_model_fallback_to_pricing(self):
        """evaluation_cost에 model 없으면 pricing의 model을 사용한다."""
        raw = {
            "pricing": {"input": 0.003, "output": 0.015, "model": "gpt-fallback"},
            "evaluation_cost": {
                "total_usd": 0.01,
                "call_count": 1,
            },
        }
        result = _parse_cost_data(raw)
        assert result["model"] == "gpt-fallback"

    def test_evaluation_cost_overrides_pricing(self):
        """evaluation_cost의 model이 pricing보다 우선한다."""
        raw = {
            "pricing": {"model": "pricing-model"},
            "evaluation_cost": {
                "total_usd": 0.01,
                "call_count": 1,
                "model": "cost-model",
            },
        }
        result = _parse_cost_data(raw)
        assert result["model"] == "cost-model"

    def test_budget_remaining_none_when_not_set(self):
        """budget_remaining_usd가 없으면 None 반환 (한도 없음)."""
        raw = {
            "evaluation_cost": {
                "total_usd": 0.01,
                "call_count": 1,
            }
        }
        result = _parse_cost_data(raw)
        assert result["budget_remaining_usd"] is None

    def test_empty_evaluation_cost_dict(self):
        """evaluation_cost가 빈 dict이면 빈 dict 반환."""
        raw = {"evaluation_cost": {}}
        assert _parse_cost_data(raw) == {}

    def test_zero_call_count(self):
        """call_count=0인 경우도 올바르게 파싱된다."""
        raw = {
            "evaluation_cost": {
                "total_usd": 0.0,
                "call_count": 0,
            }
        }
        result = _parse_cost_data(raw)
        assert result["call_count"] == 0
        assert result["total_usd"] == 0.0


# ---------------------------------------------------------------------------
# _parse_hallucination_detail
# ---------------------------------------------------------------------------

class TestParseHallucinationDetail:
    """hallucination 파서 기본 동작 검증."""

    def test_empty_returns_no_detections(self):
        raw = {}
        detail = _parse_hallucination_detail(raw)
        assert detail.detections == []
        assert detail.indicator_types == {}

    def test_deepeval_detections_filtered_out(self):
        """source=deepeval 탐지는 외부평가 탭 전용 — 품질 탭에서 제외되어야 한다."""
        raw = {
            "evaluators": {
                "hallucination": {
                    "detections": [
                        {"source": "deepeval", "indicators": [{"type": "hallucination"}]},
                        {"source": "native", "indicators": [{"type": "unsupported_claim"}]},
                    ]
                }
            }
        }
        detail = _parse_hallucination_detail(raw)
        assert len(detail.detections) == 1
        assert detail.detections[0]["source"] == "native"

    def test_indicator_types_aggregated(self):
        """indicator_types는 모든 탐지의 type별 합산이어야 한다."""
        raw = {
            "evaluators": {
                "hallucination": {
                    "detections": [
                        {"source": "native", "indicators": [
                            {"type": "unsupported_claim"},
                            {"type": "numerical_inconsistency"},
                        ]},
                        {"source": "native", "indicators": [
                            {"type": "unsupported_claim"},
                        ]},
                    ]
                }
            }
        }
        detail = _parse_hallucination_detail(raw)
        assert detail.indicator_types["unsupported_claim"] == 2
        assert detail.indicator_types["numerical_inconsistency"] == 1

    def test_missing_indicators_key(self):
        """detections 항목에 indicators 키가 없어도 에러 없이 처리."""
        raw = {
            "evaluators": {
                "hallucination": {
                    "detections": [{"source": "native"}]
                }
            }
        }
        detail = _parse_hallucination_detail(raw)
        assert len(detail.detections) == 1
        assert detail.indicator_types == {}


# ---------------------------------------------------------------------------
# _parse_feedback_data
# ---------------------------------------------------------------------------

class TestParseFeedbackData:
    """기본 피드백 파서 동작."""

    def test_empty_returns_empty(self):
        assert _parse_feedback_data({}) == {}

    def test_parses_total_and_rates(self):
        raw = {
            "feedback": {
                "total": 7,
                "positive_rate": 0.57,
                "negative_rate": 0.43,
                "abandon_rate": 0.14,
                "type_distribution": {"thumbs_up": 4, "thumbs_down": 3},
                "records": [],
            }
        }
        result = _parse_feedback_data(raw)
        assert result["total"] == 7
        assert result["positive_rate"] == pytest.approx(0.57, abs=1e-3)
        assert result["type_distribution"]["thumbs_up"] == 4
