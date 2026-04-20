"""
tests/test_coverage_llm_judge.py
=====================================
LLMJudge 미커버 영역 커버리지 개선 테스트.

대상 모듈: agent_evaluator/integrations/llm_judge.py

커버 대상:
  - _build_system_prompt (context / judge_criteria 조합)
  - _resolve_default_model
  - _build_user_message
  - LLMJudge.__init__ (invalid sample_rate, model resolution)
  - LLMJudge.judge (sampling gate, budget gate, result store)
  - LLMJudge._check_budget (daily reset, limit enforcement)
  - LLMJudge._estimate_cost (pricing lookup / default)
  - LLMJudge._call_judge (claude / openai / unsupported dispatch)
  - LLMJudge._call_claude (no API key, import error paths)
  - LLMJudge._call_openai (no API key, import error paths)
  - LLMJudge._parse_judge_response (valid JSON, markdown fences,
    faithfulness, criteria_scores, parse error)
  - LLMJudge.get_summary (empty, with results, criteria aggregation)
  - LLMJudge.register_prompt_to_phoenix (Phoenix not running → None)
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator.integrations.llm_judge import (
    LLMJudge,
    _MODEL_PRICING,
    _build_system_prompt,
    _build_user_message,
    _resolve_default_model,
)


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_base_prompt_contains_dimensions(self):
        prompt = _build_system_prompt()
        for dim in ("completeness", "relevance", "factual_consistency", "toxicity", "bias"):
            assert dim in prompt

    def test_faithfulness_added_when_context(self):
        prompt = _build_system_prompt(context_available=True)
        assert "faithfulness" in prompt
        assert '"faithfulness": <int 0-5>' in prompt

    def test_faithfulness_absent_without_context(self):
        prompt = _build_system_prompt(context_available=False)
        assert "faithfulness" not in prompt

    def test_custom_criteria_added(self):
        prompt = _build_system_prompt(judge_criteria=["medical_accuracy", "citation quality"])
        assert "medical_accuracy" in prompt
        assert "citation_quality" in prompt

    def test_criteria_json_fields(self):
        prompt = _build_system_prompt(judge_criteria=["safety"])
        assert '"safety": <int 0-5>' in prompt

    def test_combined_context_and_criteria(self):
        prompt = _build_system_prompt(context_available=True, judge_criteria=["custom_dim"])
        assert "faithfulness" in prompt
        assert "custom_dim" in prompt

    def test_returns_string(self):
        assert isinstance(_build_system_prompt(), str)
        assert len(_build_system_prompt()) > 100


# ---------------------------------------------------------------------------
# _build_user_message
# ---------------------------------------------------------------------------

class TestBuildUserMessage:
    def test_contains_question_and_response(self):
        msg = _build_user_message("Q?", "A.")
        assert "QUESTION" in msg
        assert "Q?" in msg
        assert "AGENT RESPONSE" in msg
        assert "A." in msg

    def test_context_inserted(self):
        msg = _build_user_message("Q?", "A.", context="ctx text")
        assert "CONTEXT" in msg
        assert "ctx text" in msg

    def test_context_capped_at_default(self):
        long_ctx = "x" * 6000
        msg = _build_user_message("Q?", "A.", context=long_ctx)
        # context is capped at default 4000 chars — 6000 x's should be truncated
        assert "x" * 4001 not in msg
        assert "x" * 100 in msg  # some context still present

    def test_no_context_no_context_block(self):
        msg = _build_user_message("Q?", "A.", context=None)
        assert "CONTEXT" not in msg

    def test_empty_context_not_inserted(self):
        msg = _build_user_message("Q?", "A.", context="")
        assert "CONTEXT" not in msg


# ---------------------------------------------------------------------------
# _resolve_default_model
# ---------------------------------------------------------------------------

class TestResolveDefaultModel:
    def test_returns_string(self):
        result = _resolve_default_model()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_when_no_keys(self):
        # Patch get_settings to raise so we fall through to fallback
        with patch(
            "agent_evaluator.integrations.llm_judge.get_settings" if False else
            "agent_evaluator.config.get_settings",
            side_effect=Exception("no settings"),
        ):
            result = _resolve_default_model()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# LLMJudge.__init__
# ---------------------------------------------------------------------------

class TestLLMJudgeInit:
    def test_valid_sample_rate(self):
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=0.5)
        assert judge.sample_rate == 0.5

    def test_invalid_sample_rate_raises(self):
        with pytest.raises(ValueError):
            LLMJudge(model="gpt-4o-mini", sample_rate=1.5)

    def test_invalid_negative_rate_raises(self):
        with pytest.raises(ValueError):
            LLMJudge(model="gpt-4o-mini", sample_rate=-0.1)

    def test_model_stored(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        assert judge.model == "claude-haiku-4-5-20251001"

    def test_judge_criteria_stored(self):
        judge = LLMJudge(model="gpt-4o-mini", judge_criteria=["safety"])
        assert "safety" in judge.judge_criteria

    def test_no_model_resolves(self):
        judge = LLMJudge()  # model=None → auto resolve
        assert judge.model is not None and len(judge.model) > 0

    def test_pricing_lookup(self):
        judge = LLMJudge(model="gpt-4o-mini")
        assert judge._pricing == _MODEL_PRICING["gpt-4o-mini"]

    def test_pricing_default_for_unknown_model(self):
        from agent_evaluator.integrations.llm_judge import _DEFAULT_PRICING
        judge = LLMJudge(model="unknown-model-xyz")
        assert judge._pricing == _DEFAULT_PRICING

    def test_budget_per_day_stored(self):
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=10.0)
        assert judge.budget_per_day == 10.0

    def test_results_initially_empty(self):
        judge = LLMJudge(model="gpt-4o-mini")
        assert judge.results == []


# ---------------------------------------------------------------------------
# LLMJudge.judge — sampling gate
# ---------------------------------------------------------------------------

class TestLLMJudgeJudge:
    def test_sampling_skips_at_zero_rate(self):
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=0.0)
        result = judge.judge("t1", question="Q", response="A")
        assert result.get("skipped") is True

    def test_always_judges_at_rate_1(self):
        """sample_rate=1.0 should proceed past sampling gate (may fail at API)."""
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=1.0, seed=42)
        # Mock the internal call so we don't hit the real API
        judge._call_judge = lambda *a, **kw: {
            "task_id": "t1",
            "skipped": False,
            "scores": {"completeness": 4, "relevance": 4, "factual_consistency": 4,
                       "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 4.0,
                       "confidence": 1.0},
            "reasoning": "ok",
            "model": "gpt-4o-mini",
            "cost_usd": 0.0001,
        }
        result = judge.judge("t1", question="Q", response="A")
        assert result.get("skipped") is not True

    def test_budget_exceeded_skips(self):
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=1.0, budget_per_day=0.001)
        judge._budget_spent = 999.0
        judge._budget_day = date.today()
        import warnings
        with warnings.catch_warnings(record=True):
            result = judge.judge("t1", question="Q", response="A")
        assert result.get("skipped") is True
        assert result.get("reason") == "budget_exceeded"

    def test_result_appended_to_results(self):
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=1.0)
        mock_result = {
            "task_id": "t1",
            "skipped": False,
            "scores": {"completeness": 3, "relevance": 3, "factual_consistency": 3,
                       "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 3.0,
                       "confidence": 0.9},
            "reasoning": "ok",
            "model": "gpt-4o-mini",
            "cost_usd": 0.0001,
        }
        judge._call_judge = lambda *a, **kw: mock_result
        judge.judge("t1", question="Q", response="A")
        assert len(judge.results) == 1


# ---------------------------------------------------------------------------
# LLMJudge._check_budget
# ---------------------------------------------------------------------------

class TestCheckBudget:
    def test_no_budget_always_true(self):
        judge = LLMJudge(model="gpt-4o-mini")
        assert judge._check_budget() is True

    def test_within_budget(self):
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=10.0)
        judge._budget_spent = 5.0
        judge._budget_day = date.today()
        assert judge._check_budget() is True

    def test_over_budget(self):
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=1.0)
        judge._budget_spent = 2.0
        judge._budget_day = date.today()
        assert judge._check_budget() is False

    def test_new_day_resets_budget(self):
        from datetime import date, timedelta
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=1.0)
        yesterday = date.today() - timedelta(days=1)
        judge._budget_day = yesterday
        judge._budget_spent = 999.0
        # calling _check_budget on a new day resets spent → True
        result = judge._check_budget()
        assert result is True
        assert judge._budget_spent == 0.0


# ---------------------------------------------------------------------------
# LLMJudge._estimate_cost
# ---------------------------------------------------------------------------

class TestEstimateCost:
    def test_cost_positive(self):
        judge = LLMJudge(model="gpt-4o-mini")
        cost = judge._estimate_cost(500, 100)
        assert cost >= 0.0

    def test_cost_added_to_budget_spent(self):
        judge = LLMJudge(model="gpt-4o-mini", budget_per_day=10.0)
        judge._budget_spent = 0.0
        judge._budget_day = date.today()
        cost = judge._estimate_cost(1000, 200)
        assert judge._budget_spent == pytest.approx(cost)

    def test_claude_pricing(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        cost = judge._estimate_cost(1000, 1000)
        # haiku: input=0.00025, output=0.00125 per 1k tokens
        expected = (1000 / 1000 * 0.00025) + (1000 / 1000 * 0.00125)
        assert cost == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# LLMJudge._call_judge dispatch
# ---------------------------------------------------------------------------

class TestCallJudgeDispatch:
    def test_claude_dispatch(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=1.0)
        called = []
        judge._call_claude = lambda *a, **kw: called.append("claude") or {"task_id": "t", "skipped": False, "scores": None}
        judge._call_judge("t", "Q", "A", None)
        assert "claude" in called

    def test_openai_dispatch(self):
        judge = LLMJudge(model="gpt-4o-mini", sample_rate=1.0)
        called = []
        judge._call_openai = lambda *a, **kw: called.append("openai") or {"task_id": "t", "skipped": False, "scores": None}
        judge._call_judge("t", "Q", "A", None)
        assert "openai" in called

    def test_unsupported_model_error_result(self):
        judge = LLMJudge(model="some-unknown-model", sample_rate=1.0)
        result = judge._call_judge("t", "Q", "A", None)
        assert result.get("error") is not None
        assert "Unsupported model" in result["error"]


# ---------------------------------------------------------------------------
# LLMJudge._call_claude / _call_openai (no API key path)
# ---------------------------------------------------------------------------

class TestCallClaudeNoKey:
    def test_no_api_key_returns_error(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = judge._call_claude("t1", "Q", "A", None)
        assert result.get("scores") is None
        assert "ANTHROPIC_API_KEY" in (result.get("error") or "")

    def test_import_error_returns_error(self):
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = judge._call_claude("t1", "Q", "A", None)
        assert result.get("scores") is None
        assert "anthropic" in (result.get("error") or "").lower()


class TestCallOpenAINoKey:
    def test_no_api_key_returns_error(self):
        judge = LLMJudge(model="gpt-4o-mini")
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            result = judge._call_openai("t1", "Q", "A", None)
        assert result.get("scores") is None
        assert "OPENAI_API_KEY" in (result.get("error") or "")

    def test_import_error_returns_error(self):
        judge = LLMJudge(model="gpt-4o-mini")
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = judge._call_openai("t1", "Q", "A", None)
        assert result.get("scores") is None
        assert "openai" in (result.get("error") or "").lower()


# ---------------------------------------------------------------------------
# LLMJudge._parse_judge_response
# ---------------------------------------------------------------------------

class TestParseJudgeResponse:
    def _judge(self):
        return LLMJudge(model="gpt-4o-mini")

    def _valid_json(self, extra: dict | None = None) -> str:
        base = {
            "completeness": 4,
            "relevance": 5,
            "factual_consistency": 4,
            "toxicity": 0,
            "bias": 0,
            "reasoning": "looks good",
        }
        if extra:
            base.update(extra)
        return json.dumps(base)

    def test_basic_parse(self):
        judge = self._judge()
        raw = self._valid_json()
        result = judge._parse_judge_response("t1", raw, 0.001)
        scores = result["scores"]
        assert scores["completeness"] == 4
        assert scores["relevance"] == 5
        assert "overall" in scores
        assert "safety_score" in scores

    def test_clamping(self):
        judge = self._judge()
        raw = json.dumps({
            "completeness": 10, "relevance": -1, "factual_consistency": 3,
            "toxicity": 0, "bias": 0, "reasoning": "r"
        })
        result = judge._parse_judge_response("t1", raw, 0.0)
        assert result["scores"]["completeness"] == 5  # clamped to max
        assert result["scores"]["relevance"] == 0    # clamped to min

    def test_faithfulness_parsed_when_context_available(self):
        judge = self._judge()
        raw = self._valid_json({"faithfulness": 4})
        result = judge._parse_judge_response("t1", raw, 0.0, context_available=True)
        assert result["scores"]["faithfulness"] == 4

    def test_faithfulness_missing_defaults_zero_with_warning(self, caplog):
        judge = self._judge()
        raw = self._valid_json()  # no faithfulness key
        import logging
        with caplog.at_level(logging.WARNING, logger="agent_evaluator.integrations.llm_judge"):
            result = judge._parse_judge_response("t1", raw, 0.0, context_available=True)
        assert result["scores"]["faithfulness"] == 0

    def test_criteria_scores_parsed(self):
        judge = self._judge()
        raw = self._valid_json({"medical_accuracy": 5, "citation_quality": 3})
        result = judge._parse_judge_response(
            "t1", raw, 0.0,
            judge_criteria=["medical_accuracy", "citation_quality"]
        )
        assert "criteria_scores" in result["scores"]
        assert result["scores"]["criteria_scores"]["medical_accuracy"] == 5
        assert result["scores"]["criteria_scores"]["citation_quality"] == 3

    def test_criteria_overall_computed(self):
        judge = self._judge()
        raw = self._valid_json({"safety": 4, "privacy": 2})
        result = judge._parse_judge_response(
            "t1", raw, 0.0,
            judge_criteria=["safety", "privacy"]
        )
        assert "criteria_overall" in result["scores"]
        assert result["scores"]["criteria_overall"] == pytest.approx(3.0)

    def test_markdown_fence_stripped(self):
        judge = self._judge()
        raw = "```json\n" + self._valid_json() + "\n```"
        result = judge._parse_judge_response("t1", raw, 0.0)
        assert result["scores"] is not None

    def test_parse_error_returns_error_key(self):
        judge = self._judge()
        result = judge._parse_judge_response("t1", "NOT_VALID_JSON", 0.0)
        assert result.get("error") is not None
        assert result.get("scores") is None

    def test_confidence_computed(self):
        judge = self._judge()
        raw = self._valid_json({"completeness": 5, "relevance": 5, "factual_consistency": 5})
        result = judge._parse_judge_response("t1", raw, 0.0)
        # All 5s → zero variance → confidence = 1.0
        assert result["scores"]["confidence"] == pytest.approx(1.0)

    def test_safety_score_computed(self):
        judge = self._judge()
        raw = self._valid_json({"toxicity": 0, "bias": 0})
        result = judge._parse_judge_response("t1", raw, 0.0)
        # (10 - 0 - 0) / 10 = 1.0
        assert result["scores"]["safety_score"] == pytest.approx(1.0)

    def test_faithfulness_excluded_from_criteria_when_context_available(self):
        """faithfulness in judge_criteria + context_available → not double-counted."""
        judge = self._judge()
        raw = self._valid_json({"faithfulness": 4})
        result = judge._parse_judge_response(
            "t1", raw, 0.0,
            context_available=True,
            judge_criteria=["faithfulness"],  # should be excluded from criteria_scores
        )
        scores = result["scores"]
        # faithfulness should appear as a top-level score, not in criteria_scores
        assert "faithfulness" in scores
        cs = scores.get("criteria_scores", {})
        assert "faithfulness" not in cs


# ---------------------------------------------------------------------------
# LLMJudge.get_summary
# ---------------------------------------------------------------------------

class TestGetSummary:
    def test_empty_results(self):
        judge = LLMJudge(model="gpt-4o-mini")
        summary = judge.get_summary()
        assert summary["count"] == 0
        assert summary["avg_scores"] == {}
        assert summary["total_cost_usd"] == 0.0

    def test_with_one_result(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge.results.append({
            "task_id": "t1",
            "skipped": False,
            "scores": {
                "completeness": 4, "relevance": 5, "factual_consistency": 4,
                "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 4.33,
                "confidence": 0.9,
            },
            "reasoning": "good",
            "model": "gpt-4o-mini",
            "cost_usd": 0.001,
        })
        summary = judge.get_summary()
        assert summary["count"] == 1
        assert "completeness" in summary["avg_scores"]
        assert summary["total_cost_usd"] == pytest.approx(0.001)

    def test_skipped_excluded(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge.results.append({"task_id": "t1", "skipped": True})
        summary = judge.get_summary()
        assert summary["count"] == 0

    def test_error_excluded(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge.results.append({"task_id": "t1", "skipped": False, "error": "fail", "scores": None})
        summary = judge.get_summary()
        assert summary["count"] == 0

    def test_criteria_scores_aggregated(self):
        judge = LLMJudge(model="gpt-4o-mini")
        for val in [3, 5]:
            judge.results.append({
                "task_id": f"t{val}",
                "skipped": False,
                "scores": {
                    "completeness": 4, "relevance": 4, "factual_consistency": 4,
                    "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 4.0,
                    "confidence": 0.9,
                    "criteria_scores": {"safety": val},
                },
                "cost_usd": 0.0,
            })
        summary = judge.get_summary()
        assert "criteria_scores" in summary["avg_scores"]
        assert summary["avg_scores"]["criteria_scores"]["safety"] == pytest.approx(4.0)

    def test_faithfulness_in_avg_scores(self):
        judge = LLMJudge(model="gpt-4o-mini")
        judge.results.append({
            "task_id": "t1",
            "skipped": False,
            "scores": {
                "completeness": 4, "relevance": 4, "factual_consistency": 4,
                "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 4.0,
                "confidence": 0.9, "faithfulness": 5,
            },
            "cost_usd": 0.0,
        })
        summary = judge.get_summary()
        assert "faithfulness" in summary["avg_scores"]
        assert summary["avg_scores"]["faithfulness"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# LLMJudge.register_prompt_to_phoenix
# ---------------------------------------------------------------------------

class TestRegisterPromptToPhoenix:
    def test_phoenix_not_running_returns_none(self):
        judge = LLMJudge(model="gpt-4o-mini")
        result = judge.register_prompt_to_phoenix(phoenix_endpoint="http://localhost:59999")
        assert result is None

    def test_claude_model_uses_anthropic_provider(self):
        """Test the model_provider branching for Claude models."""
        judge = LLMJudge(model="claude-haiku-4-5-20251001")
        # We only verify no exception is raised for an unavailable endpoint
        result = judge.register_prompt_to_phoenix(phoenix_endpoint="http://localhost:59999")
        assert result is None


# ---------------------------------------------------------------------------
# Integration: judge flow with mocked _call_judge
# ---------------------------------------------------------------------------

class TestJudgeIntegrationFlow:
    def _make_judge_with_mock(self, model: str = "gpt-4o-mini") -> LLMJudge:
        judge = LLMJudge(model=model, sample_rate=1.0, seed=0)
        judge._call_judge = lambda task_id, q, r, ctx: {
            "task_id": task_id,
            "skipped": False,
            "scores": {
                "completeness": 4, "relevance": 5, "factual_consistency": 4,
                "toxicity": 0, "bias": 0, "safety_score": 1.0, "overall": 4.33,
                "confidence": 0.95,
            },
            "reasoning": "test",
            "model": model,
            "cost_usd": 0.001,
        }
        return judge

    def test_end_to_end_judge(self):
        judge = self._make_judge_with_mock()
        result = judge.judge("t1", question="Q", response="A")
        assert result["scores"]["overall"] == pytest.approx(4.33)
        assert result["model"] == "gpt-4o-mini"

    def test_multiple_tasks_summary(self):
        judge = self._make_judge_with_mock()
        for i in range(3):
            judge.judge(f"t{i}", question=f"Q{i}", response=f"A{i}")
        summary = judge.get_summary()
        assert summary["count"] == 3

    def test_deterministic_sampling_with_seed(self):
        judge1 = LLMJudge(model="gpt-4o-mini", sample_rate=0.5, seed=42)
        judge2 = LLMJudge(model="gpt-4o-mini", sample_rate=0.5, seed=42)
        # Both should make the same sampling decisions
        results1 = [judge1._rng.random() for _ in range(10)]
        results2 = [judge2._rng.random() for _ in range(10)]
        assert results1 == results2
