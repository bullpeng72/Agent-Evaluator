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


# ---------------------------------------------------------------------------
# _parse_tasks — tolerate null / non-numeric / non-dict entries so a hand-
# written or older-SDK result JSON does not crash the whole report path.
# ---------------------------------------------------------------------------

class TestParseTasksTolerantCoercion:
    def _parse(self, raw):
        import json
        import tempfile
        from pathlib import Path

        from agent_evaluator.serve.loader import parse_file

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            p = f.name
        try:
            return parse_file(Path(p))
        finally:
            import os
            os.unlink(p)

    def test_null_score_fields_do_not_crash(self):
        rf = self._parse({"total_tasks": 2, "tasks": [
            {"task_id": "a", "completion_score": None, "accuracy_score": None,
             "execution_time": None, "attempts": None},
            {"task_id": "b"},  # keys entirely absent
        ]})
        assert len(rf.tasks) == 2
        assert rf.tasks[0].completion_score == 0.0
        assert rf.tasks[0].accuracy_score == 0.0
        assert rf.tasks[0].execution_time == 0.0
        assert rf.tasks[0].attempts == 1  # default, not 0

    def test_string_scores_are_coerced(self):
        rf = self._parse({"total_tasks": 1, "tasks": [
            {"task_id": "a", "completion_score": "0.8", "accuracy_score": "1",
             "execution_time": "2.5", "attempts": "3"},
        ]})
        assert rf.tasks[0].completion_score == 0.8
        assert rf.tasks[0].attempts == 3

    def test_garbage_string_scores_fall_back(self):
        rf = self._parse({"total_tasks": 1, "tasks": [
            {"task_id": "a", "accuracy_score": "n/a", "execution_time": "fast"},
        ]})
        assert rf.tasks[0].accuracy_score == 0.0
        assert rf.tasks[0].execution_time == 0.0

    def test_non_dict_task_entries_are_dropped(self):
        rf = self._parse({"total_tasks": 3, "tasks": [
            "oops", None, 42, {"task_id": "real", "accuracy_score": 0.5},
        ]})
        assert len(rf.tasks) == 1
        assert rf.tasks[0].task_id == "real"

    def test_tasks_not_a_list(self):
        rf = self._parse({"total_tasks": 0, "tasks": "broken"})
        assert rf.tasks == []

    def test_tasks_explicit_null(self):
        # ``"tasks": null`` — sub-parsers do ``raw.get("tasks", [])`` which returns
        # None (not the default), then ``for t in None`` crashes _parse_advanced.
        rf = self._parse({"accuracy_metrics": {"tcr": {"tcr": 50}}, "tasks": None})
        assert rf.tasks == []
        assert round(rf.tcr, 1) == 50.0

    def test_tasks_dict_value(self):
        rf = self._parse({"tasks": {"weird": 1}})
        assert rf.tasks == []


class TestParseFileTolerateBadReportWrapper:
    """Many sub-parsers do ``raw.get("report", {}).get(...)`` / ``raw.get("report",
    raw)`` — the ``, {}`` default only covers a *missing* key, not an explicit
    ``null`` / non-dict "report" value, which would AttributeError mid-parse and
    make the file silently vanish from the dashboard (load_results swallows it)."""

    def _parse(self, raw):
        import json
        import os
        import tempfile
        from pathlib import Path

        from agent_evaluator.serve.loader import parse_file

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            p = f.name
        try:
            return parse_file(Path(p))
        finally:
            os.unlink(p)

    @pytest.mark.parametrize("bad", [None, 5, "x", [], True])
    def test_bad_report_wrapper_does_not_crash(self, bad):
        rf = self._parse({"report": bad, "accuracy_metrics": {"tcr": {"tcr": 71}}})
        # a present-but-bad "report" behaves like an absent one → flat metrics win
        assert round(rf.tcr, 1) == 71.0

    def test_valid_report_wrapper_still_read(self):
        rf = self._parse({"report": {"accuracy_metrics": {"tcr": {"tcr": 88}}}})
        assert round(rf.tcr, 1) == 88.0


class TestResultFilePropertiesTolerateNullMetrics:
    """A result JSON whose ``accuracy_metrics`` / ``efficiency_metrics`` (or a key
    inside them) is ``null`` must not turn ResultFile's numeric properties into
    ``None`` — ``compare_results`` / CSV export / ``_to_meta`` do ``round(prop, n)``
    and a single bad sibling file otherwise 500s the whole dashboard listing.
    """
    def _parse(self, raw):
        import json
        import os
        import tempfile
        from pathlib import Path

        from agent_evaluator.serve.loader import parse_file

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            p = f.name
        try:
            return parse_file(Path(p))
        finally:
            os.unlink(p)

    _PROPS = ("tcr", "accuracy", "hallucination_rate", "avg_latency",
              "p95_latency", "total_cost", "avg_cost_per_task", "total_tokens")

    @pytest.mark.parametrize("raw", [
        {"accuracy_metrics": None, "tasks": []},
        {"efficiency_metrics": None, "tasks": []},
        {"accuracy_metrics": {"tcr": None}, "tasks": []},
        {"accuracy_metrics": {"tcr": {"tcr": None}}, "tasks": []},
        {"accuracy_metrics": {"accuracy_scores": None}, "tasks": []},
        {"efficiency_metrics": {"latency": None}, "tasks": []},
        {"efficiency_metrics": {"tokens": {"total_cost": None}}, "tasks": []},
        {"accuracy_metrics": [1, 2], "tasks": []},
        {"accuracy_metrics": {"tcr": {"tcr": "0.8"}}, "tasks": []},
    ])
    def test_numeric_props_always_roundable(self, raw):
        rf = self._parse(raw)
        for prop in self._PROPS:
            v = getattr(rf, prop)
            assert isinstance(v, (int, float)), f"{prop} -> {v!r}"
            round(v, 4)  # exactly what the consumers do
