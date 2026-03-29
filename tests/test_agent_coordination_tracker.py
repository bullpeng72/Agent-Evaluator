"""
tests/test_agent_coordination_tracker.py
=========================================
AgentCoordinationTracker 테스트
"""
import pytest

from agent_evaluator.core.trackers.layer2 import AgentCoordinationTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_interactions(tracker: AgentCoordinationTracker, n: int = 3, success: bool = True) -> None:
    for i in range(n):
        tracker.track_interaction(
            task_id=f"t{i}",
            from_agent="orchestrator",
            to_agent=f"agent_{i}",
            interaction_type="delegation",
            success=success,
        )


# ===========================================================================
# track_interaction
# ===========================================================================

class TestTrackInteraction:
    def test_basic_record(self):
        t = AgentCoordinationTracker()
        result = t.track_interaction("t1", "A", "B", "delegation", True)
        assert result["task_id"] == "t1"
        assert result["from_agent"] == "A"
        assert result["to_agent"] == "B"
        assert result["interaction_type"] == "delegation"
        assert result["success"] is True

    def test_empty_agent_name_normalized(self):
        t = AgentCoordinationTracker()
        result = t.track_interaction("t1", "", "", "delegation", True)
        assert result["from_agent"] == "unknown_agent"
        assert result["to_agent"] == "unknown_agent"

    def test_invalid_interaction_type_normalized(self):
        t = AgentCoordinationTracker()
        result = t.track_interaction("t1", "A", "B", "invalid_type", True)
        assert result["interaction_type"] == "delegation"

    def test_valid_interaction_types_accepted(self):
        t = AgentCoordinationTracker()
        for itype in ("delegation", "communication", "collaboration"):
            r = t.track_interaction("t1", "A", "B", itype, True)
            assert r["interaction_type"] == itype

    def test_context_stored(self):
        t = AgentCoordinationTracker()
        result = t.track_interaction("t1", "A", "B", "delegation", True, context={"key": "val"})
        assert result["context"]["key"] == "val"

    def test_interactions_accumulated(self):
        t = AgentCoordinationTracker()
        _add_interactions(t, 5)
        assert len(t.interactions) == 5


# ===========================================================================
# calculate_coordination_score — empty state
# ===========================================================================

class TestCalculateCoordinationScoreEmpty:
    def test_empty_returns_structured_zeros(self):
        t = AgentCoordinationTracker()
        result = t.calculate_coordination_score()
        assert result["overall_score"] == 0.0
        assert result["total_interactions"] == 0
        assert result["unique_agents"] == 0
        assert result["interaction_types"] == {}

    def test_empty_has_required_keys(self):
        t = AgentCoordinationTracker()
        result = t.calculate_coordination_score()
        for key in ("overall_score", "success_rate", "total_interactions", "unique_agents", "interaction_types"):
            assert key in result, f"missing key: {key}"

    def test_task_filter_no_match_returns_zeros(self):
        t = AgentCoordinationTracker()
        _add_interactions(t, 3)
        result = t.calculate_coordination_score(task_id="nonexistent")
        assert result["total_interactions"] == 0


# ===========================================================================
# calculate_coordination_score — populated
# ===========================================================================

class TestCalculateCoordinationScorePopulated:
    def test_all_success_high_score(self):
        t = AgentCoordinationTracker()
        _add_interactions(t, 5, success=True)
        result = t.calculate_coordination_score()
        assert result["success_rate"] == pytest.approx(100.0)
        assert result["overall_score"] > 0

    def test_all_fail_zero_success_rate(self):
        t = AgentCoordinationTracker()
        _add_interactions(t, 3, success=False)
        result = t.calculate_coordination_score()
        assert result["success_rate"] == pytest.approx(0.0)

    def test_task_id_filter(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t2", "A", "C", "delegation", False)
        result = t.calculate_coordination_score(task_id="t1")
        assert result["total_interactions"] == 1
        assert result["success_rate"] == pytest.approx(100.0)

    def test_unique_agents_counted(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t1", "B", "C", "communication", True)
        result = t.calculate_coordination_score()
        assert result["unique_agents"] == 3  # A, B, C

    def test_interaction_types_tallied(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t1", "A", "B", "communication", True)
        result = t.calculate_coordination_score()
        assert result["interaction_types"]["delegation"] == 2
        assert result["interaction_types"]["communication"] == 1


# ===========================================================================
# get_delegation_success_rate
# ===========================================================================

class TestGetDelegationSuccessRate:
    def test_empty_returns_zero(self):
        t = AgentCoordinationTracker()
        assert t.get_delegation_success_rate() == 0.0

    def test_no_delegations_returns_zero(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "communication", True)
        assert t.get_delegation_success_rate() == 0.0

    def test_all_delegations_succeed(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t2", "A", "C", "delegation", True)
        assert t.get_delegation_success_rate() == pytest.approx(100.0)

    def test_half_delegations_succeed(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t2", "A", "C", "delegation", False)
        assert t.get_delegation_success_rate() == pytest.approx(50.0)


# ===========================================================================
# get_interaction_patterns
# ===========================================================================

class TestGetInteractionPatterns:
    def test_empty_returns_none_pattern(self):
        t = AgentCoordinationTracker()
        result = t.get_interaction_patterns()
        assert result["total_interactions"] == 0
        assert result["pattern_type"] == "none"

    def test_hub_pattern_detected(self):
        """중앙 에이전트가 50%+ 인터랙션을 처리하면 hub로 탐지"""
        t = AgentCoordinationTracker()
        for i in range(6):
            t.track_interaction("t1", "hub_agent", f"worker_{i}", "delegation", True)
        t.track_interaction("t1", "worker_0", "worker_1", "communication", True)
        result = t.get_interaction_patterns()
        assert result["pattern_type"] == "hub"

    def test_agent_roles_classified(self):
        t = AgentCoordinationTracker()
        # orchestrator mostly sends
        for i in range(4):
            t.track_interaction("t1", "orchestrator", f"w{i}", "delegation", True)
        # receiver mostly receives
        t.track_interaction("t1", "w0", "receiver", "delegation", True)
        result = t.get_interaction_patterns()
        roles = result["agent_roles"]
        assert roles["orchestrator"]["role"] == "producer"

    def test_top_agent_pairs_present(self):
        t = AgentCoordinationTracker()
        _add_interactions(t, 5)
        result = t.get_interaction_patterns()
        assert "top_agent_pairs" in result
        assert isinstance(result["top_agent_pairs"], list)

    def test_success_rate_in_result(self):
        t = AgentCoordinationTracker()
        t.track_interaction("t1", "A", "B", "delegation", True)
        t.track_interaction("t1", "A", "B", "delegation", False)
        result = t.get_interaction_patterns()
        assert result["success_rate"] == pytest.approx(50.0)


# ===========================================================================
# __repr__
# ===========================================================================

def test_repr_empty():
    t = AgentCoordinationTracker()
    assert "AgentCoordinationTracker" in repr(t)
    assert "interactions=0" in repr(t)


def test_repr_after_track():
    t = AgentCoordinationTracker()
    _add_interactions(t, 3)
    assert "interactions=3" in repr(t)
