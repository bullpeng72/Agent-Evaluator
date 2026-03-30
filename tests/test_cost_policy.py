"""Tests for CostTracker, AdaptivePolicy, and SamplingStage.

Covers cost accumulation, budget checks, alert thresholds, daily stats,
policy stage transitions, and enum values.
"""
from __future__ import annotations

import pytest

from agent_evaluator.cost.policy import AdaptivePolicy, CostTracker, SamplingStage
from agent_evaluator.exceptions import ValidationError


# ---------------------------------------------------------------------------
# SamplingStage enum
# ---------------------------------------------------------------------------

def test_sampling_stage_default_value():
    assert SamplingStage.DEFAULT == "default"


def test_sampling_stage_anomaly_value():
    assert SamplingStage.ANOMALY == "anomaly"


def test_sampling_stage_budget_exceeded_value():
    assert SamplingStage.BUDGET_EXCEEDED == "budget_exceeded"


def test_sampling_stage_all_three_members_exist():
    members = {s.value for s in SamplingStage}
    assert members == {"default", "anomaly", "budget_exceeded"}


# ---------------------------------------------------------------------------
# CostTracker — basic record / get_today_cost
# ---------------------------------------------------------------------------

def test_cost_tracker_record_accumulates():
    tracker = CostTracker()
    tracker.record("anthropic", "claude-haiku", 0.001)
    tracker.record("anthropic", "claude-haiku", 0.002)
    assert tracker.get_today_cost() == pytest.approx(0.003)


def test_cost_tracker_get_today_cost_empty_returns_zero():
    tracker = CostTracker()
    assert tracker.get_today_cost() == 0.0


def test_cost_tracker_record_multiple_providers():
    tracker = CostTracker()
    tracker.record("anthropic", "claude-haiku", 0.001)
    tracker.record("openai", "gpt-4o-mini", 0.002)
    assert tracker.get_today_cost() == pytest.approx(0.003)


def test_cost_tracker_record_stores_all_fields():
    tracker = CostTracker()
    tracker.record(
        provider="openai",
        model="gpt-4o",
        cost_usd=0.005,
        input_tokens=500,
        output_tokens=200,
        evaluation_type="deepeval",
    )
    records = tracker.get_all_records()
    assert len(records) == 1
    r = records[0]
    assert r["provider"] == "openai"
    assert r["model"] == "gpt-4o"
    assert r["cost_usd"] == 0.005
    assert r["input_tokens"] == 500
    assert r["output_tokens"] == 200
    assert r["evaluation_type"] == "deepeval"


# ---------------------------------------------------------------------------
# CostTracker — is_budget_exceeded
# ---------------------------------------------------------------------------

def test_is_budget_exceeded_false_when_no_budget():
    tracker = CostTracker(budget_per_day=None)
    tracker.record("openai", "gpt-4o", 1000.0)
    assert tracker.is_budget_exceeded() is False


def test_is_budget_exceeded_false_below_budget():
    tracker = CostTracker(budget_per_day=5.0)
    tracker.record("anthropic", "claude-haiku", 4.99)
    assert tracker.is_budget_exceeded() is False


def test_is_budget_exceeded_true_at_budget():
    tracker = CostTracker(budget_per_day=5.0)
    tracker.record("anthropic", "claude-haiku", 5.0)
    assert tracker.is_budget_exceeded() is True


def test_is_budget_exceeded_true_over_budget():
    tracker = CostTracker(budget_per_day=1.0)
    tracker.record("anthropic", "claude-haiku", 0.6)
    tracker.record("openai", "gpt-4o-mini", 0.5)
    assert tracker.is_budget_exceeded() is True


# ---------------------------------------------------------------------------
# CostTracker — is_budget_alert
# ---------------------------------------------------------------------------

def test_is_budget_alert_false_when_no_budget():
    tracker = CostTracker(budget_per_day=None)
    tracker.record("openai", "gpt-4o", 999.0)
    assert tracker.is_budget_alert() is False


def test_is_budget_alert_false_below_alert_threshold():
    tracker = CostTracker(budget_per_day=10.0, alert_at=0.8)
    tracker.record("anthropic", "haiku", 7.0)  # 70% — below 80%
    assert tracker.is_budget_alert() is False


def test_is_budget_alert_true_at_alert_threshold():
    tracker = CostTracker(budget_per_day=10.0, alert_at=0.8)
    tracker.record("anthropic", "haiku", 8.0)  # exactly 80%
    assert tracker.is_budget_alert() is True


def test_is_budget_alert_true_above_alert_threshold():
    tracker = CostTracker(budget_per_day=10.0, alert_at=0.5)
    tracker.record("anthropic", "haiku", 6.0)  # 60% > 50%
    assert tracker.is_budget_alert() is True


def test_cost_tracker_invalid_alert_at_raises():
    with pytest.raises(ValidationError):
        CostTracker(alert_at=1.5)


def test_cost_tracker_invalid_alert_at_negative_raises():
    with pytest.raises(ValidationError):
        CostTracker(alert_at=-0.1)


# ---------------------------------------------------------------------------
# CostTracker — get_daily_stats
# ---------------------------------------------------------------------------

def test_get_daily_stats_returns_dict_with_required_keys():
    tracker = CostTracker(budget_per_day=5.0)
    stats = tracker.get_daily_stats()
    for key in (
        "today_total_usd",
        "budget_per_day",
        "budget_remaining_usd",
        "budget_alert",
        "budget_exceeded",
        "by_provider",
        "by_evaluation_type",
        "today_call_count",
        "daily_history",
    ):
        assert key in stats, f"Missing key: {key}"


def test_get_daily_stats_by_provider():
    tracker = CostTracker()
    tracker.record("anthropic", "haiku", 0.001)
    tracker.record("openai", "gpt-4o-mini", 0.002)
    stats = tracker.get_daily_stats()
    assert "anthropic" in stats["by_provider"]
    assert "openai" in stats["by_provider"]
    assert stats["by_provider"]["anthropic"] == pytest.approx(0.001)
    assert stats["by_provider"]["openai"] == pytest.approx(0.002)


def test_get_daily_stats_by_evaluation_type():
    tracker = CostTracker()
    tracker.record("openai", "gpt-4o", 0.01, evaluation_type="deepeval")
    tracker.record("openai", "gpt-4o", 0.02, evaluation_type="ragas")
    stats = tracker.get_daily_stats()
    assert stats["by_evaluation_type"]["deepeval"] == pytest.approx(0.01)
    assert stats["by_evaluation_type"]["ragas"] == pytest.approx(0.02)


def test_get_daily_stats_budget_remaining():
    tracker = CostTracker(budget_per_day=10.0)
    tracker.record("anthropic", "haiku", 3.0)
    stats = tracker.get_daily_stats()
    assert stats["budget_remaining_usd"] == pytest.approx(7.0)


def test_get_daily_stats_no_budget_remaining_is_none():
    tracker = CostTracker(budget_per_day=None)
    stats = tracker.get_daily_stats()
    assert stats["budget_remaining_usd"] is None


# ---------------------------------------------------------------------------
# AdaptivePolicy — initial state
# ---------------------------------------------------------------------------

def test_adaptive_policy_default_stage():
    policy = AdaptivePolicy()
    assert policy.current_stage == SamplingStage.DEFAULT


def test_adaptive_policy_default_sample_rate():
    policy = AdaptivePolicy(default_sample_rate=0.1)
    assert policy.current_sample_rate == pytest.approx(0.1)


def test_adaptive_policy_invalid_default_rate_raises():
    with pytest.raises(ValidationError):
        AdaptivePolicy(default_sample_rate=1.5)


def test_adaptive_policy_invalid_anomaly_rate_raises():
    with pytest.raises(ValidationError):
        AdaptivePolicy(anomaly_sample_rate=-0.1)


# ---------------------------------------------------------------------------
# AdaptivePolicy — get_status
# ---------------------------------------------------------------------------

def test_get_status_returns_required_keys():
    policy = AdaptivePolicy()
    status = policy.get_status()
    for key in ("stage", "current_sample_rate", "default_sample_rate",
                "anomaly_sample_rate", "cost", "stage_history"):
        assert key in status, f"Missing key: {key}"


def test_get_status_stage_matches_current_stage():
    policy = AdaptivePolicy()
    status = policy.get_status()
    assert status["stage"] == policy.current_stage.value


# ---------------------------------------------------------------------------
# AdaptivePolicy — enter_anomaly_mode / exit_anomaly_mode
# ---------------------------------------------------------------------------

def test_enter_anomaly_mode_changes_stage():
    policy = AdaptivePolicy()
    policy.enter_anomaly_mode(reason="test")
    assert policy.current_stage == SamplingStage.ANOMALY


def test_enter_anomaly_mode_raises_sample_rate():
    policy = AdaptivePolicy(default_sample_rate=0.1, anomaly_sample_rate=1.0)
    policy.enter_anomaly_mode()
    assert policy.current_sample_rate == pytest.approx(1.0)


def test_exit_anomaly_mode_reverts_to_default():
    policy = AdaptivePolicy()
    policy.enter_anomaly_mode()
    policy.exit_anomaly_mode()
    assert policy.current_stage == SamplingStage.DEFAULT


def test_exit_anomaly_mode_restores_default_sample_rate():
    policy = AdaptivePolicy(default_sample_rate=0.2, anomaly_sample_rate=1.0)
    policy.enter_anomaly_mode()
    policy.exit_anomaly_mode()
    assert policy.current_sample_rate == pytest.approx(0.2)


def test_enter_anomaly_mode_twice_does_not_duplicate_history():
    """Transitioning to the same stage twice must be a no-op (no duplicate history)."""
    policy = AdaptivePolicy()
    policy.enter_anomaly_mode("first")
    history_len = len(policy._stage_history)
    policy.enter_anomaly_mode("second")  # same stage — should not add a history entry
    assert len(policy._stage_history) == history_len


# ---------------------------------------------------------------------------
# AdaptivePolicy — check_budget
# ---------------------------------------------------------------------------

def test_check_budget_transitions_to_budget_exceeded():
    policy = AdaptivePolicy(budget_per_day=1.0)
    # Exceed the budget
    policy.cost_tracker.record("openai", "gpt-4o", 1.5)
    policy.check_budget()
    assert policy.current_stage == SamplingStage.BUDGET_EXCEEDED


def test_budget_exceeded_sets_sample_rate_to_zero():
    policy = AdaptivePolicy(budget_per_day=1.0, default_sample_rate=0.5)
    policy.cost_tracker.record("openai", "gpt-4o", 2.0)
    policy.check_budget()
    assert policy.current_sample_rate == 0.0


def test_check_budget_no_op_when_within_budget():
    policy = AdaptivePolicy(budget_per_day=10.0)
    policy.cost_tracker.record("openai", "gpt-4o", 5.0)
    policy.check_budget()
    assert policy.current_stage == SamplingStage.DEFAULT


def test_exit_anomaly_mode_goes_to_budget_exceeded_if_over_budget():
    """If budget is already exceeded during anomaly mode, exit should go to BUDGET_EXCEEDED."""
    policy = AdaptivePolicy(budget_per_day=1.0)
    policy.enter_anomaly_mode()
    policy.cost_tracker.record("openai", "gpt-4o", 2.0)  # exceed budget
    policy.exit_anomaly_mode()
    assert policy.current_stage == SamplingStage.BUDGET_EXCEEDED
