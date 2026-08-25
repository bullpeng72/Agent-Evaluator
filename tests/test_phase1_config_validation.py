"""
tests/test_phase1_config_validation.py
=========================================
Phase 1 (계약 굳히기) — Config 검증 감사에서 발견된 미검증 7개 Config에
__post_init__ 검증을 추가한 것의 회귀 테스트.

Gate B/C/D/E/F의 33개 Config 중 26개는 이미 __post_init__ 검증을 갖추고 있었다
(각 파일에 버그 ID 주석 포함). Gate A(6개 전부)와 Gate G의 ObservabilityConfig만
검증이 없었다 — 이 파일은 그 7개에 새로 추가한 검증만 다룬다. 나머지 26개는
각자의 기존 테스트에서 이미 커버된다.
"""
from __future__ import annotations

import pytest

from agent_evaluator import (
    ContextRetentionConfig,
    GoalAlignmentConfig,
    InstructionConfig,
    KnowledgeRetentionConfig,
    ObservabilityConfig,
    PlanConfig,
    SubtaskConfig,
)


class TestInstructionConfig:
    def test_negative_violation_weight_corrected(self):
        with pytest.warns(UserWarning, match="violation_weight"):
            cfg = InstructionConfig(violation_weight=-0.5)
        assert cfg.violation_weight == 0.1

    def test_negative_violation_weights_dict_warns_without_mutation(self):
        with pytest.warns(UserWarning, match="violation_weights"):
            cfg = InstructionConfig(violation_weights={"format": -0.2})
        # 경고만, 자동 보정 안 함(딕셔너리라 안전한 기본값 없음)
        assert cfg.violation_weights == {"format": -0.2}

    def test_min_chars_greater_than_max_chars_warns(self):
        with pytest.warns(UserWarning, match="min_chars"):
            InstructionConfig(min_chars=100, max_chars=50)

    def test_min_words_greater_than_max_words_warns(self):
        with pytest.warns(UserWarning, match="min_words"):
            InstructionConfig(min_words=100, max_words=50)

    def test_valid_config_no_warning(self):
        InstructionConfig(min_chars=10, max_chars=100, violation_weight=0.1)  # no warning


class TestGoalAlignmentConfig:
    def test_llm_blend_weight_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="llm_blend_weight"):
            GoalAlignmentConfig(llm_blend_weight=1.5)

    def test_alignment_threshold_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="alignment_threshold"):
            GoalAlignmentConfig(alignment_threshold=-0.1)

    def test_valid_config_no_warning(self):
        GoalAlignmentConfig(llm_blend_weight=0.5, alignment_threshold=0.6)


class TestPlanConfig:
    def test_min_steps_greater_than_max_steps_warns(self):
        with pytest.warns(UserWarning, match="min_steps"):
            PlanConfig(min_steps=20, max_steps=5)

    def test_negative_min_steps_corrected(self):
        with pytest.warns(UserWarning, match="min_steps"):
            cfg = PlanConfig(min_steps=-3)
        assert cfg.min_steps == 0

    def test_valid_config_no_warning(self):
        PlanConfig(min_steps=2, max_steps=15)


class TestContextRetentionConfig:
    def test_negative_entity_weight_corrected(self):
        with pytest.warns(UserWarning, match="entity_weight"):
            cfg = ContextRetentionConfig(entity_weight=-0.5)
        assert cfg.entity_weight == 0.6

    def test_negative_goal_weight_corrected(self):
        with pytest.warns(UserWarning, match="goal_weight"):
            cfg = ContextRetentionConfig(goal_weight=-0.5)
        assert cfg.goal_weight == 0.4

    def test_zero_sum_weights_raises(self):
        with pytest.raises(ValueError, match="entity_weight \\+ goal_weight"):
            ContextRetentionConfig(entity_weight=0.0, goal_weight=0.0)

    def test_retention_threshold_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="retention_threshold"):
            ContextRetentionConfig(retention_threshold=1.5)

    def test_valid_config_no_warning(self):
        ContextRetentionConfig()


class TestSubtaskConfig:
    def test_min_completion_rate_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="min_completion_rate"):
            SubtaskConfig(min_completion_rate=1.5)

    def test_valid_config_no_warning(self):
        SubtaskConfig(min_completion_rate=0.8)


class TestKnowledgeRetentionConfig:
    def test_negative_seed_turns_corrected(self):
        with pytest.warns(UserWarning, match="seed_turns"):
            cfg = KnowledgeRetentionConfig(seed_turns=-1)
        assert cfg.seed_turns == 0

    def test_check_from_turn_less_than_seed_turns_warns(self):
        with pytest.warns(UserWarning, match="check_from_turn"):
            KnowledgeRetentionConfig(seed_turns=5, check_from_turn=2)

    def test_retention_threshold_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="retention_threshold"):
            KnowledgeRetentionConfig(retention_threshold=-0.1)

    def test_valid_config_no_warning(self):
        KnowledgeRetentionConfig(seed_turns=2, check_from_turn=3)


class TestObservabilityConfig:
    def test_min_coverage_out_of_range_warns(self):
        with pytest.warns(UserWarning, match="min_coverage"):
            ObservabilityConfig(min_coverage=1.5)

    def test_negative_min_coverage_warns(self):
        with pytest.warns(UserWarning, match="min_coverage"):
            ObservabilityConfig(min_coverage=-0.1)

    def test_valid_config_no_warning(self):
        ObservabilityConfig(min_coverage=0.95)
