"""
tests/test_decorators_harness.py
=================================
v0.9.0 Harness Config 6종 단위·통합 테스트.
- InstructionConfig, LoopDetectionConfig, GoalAlignmentConfig,
  ReproducibilityConfig, FaultToleranceConfig, PlanConfig
- @agent_eval / @batch_eval / @conversation_eval 파라미터 통합
- helper 함수 직접 단위 테스트
"""
from __future__ import annotations

import json
import pytest

from agent_evaluator import PerformanceMonitor
from agent_evaluator.decorators import (
    agent_eval,
    batch_eval,
    conversation_eval,
    flush_conversation,
    InstructionConfig,
    LoopDetectionConfig,
    GoalAlignmentConfig,
    ReproducibilityConfig,
    FaultToleranceConfig,
    PlanConfig,
    KnowledgeRetentionConfig,
)
from agent_evaluator.helpers.taskresult_helpers import (
    eval_instruction_adherence,
    eval_loop_detection,
    eval_goal_alignment,
    eval_fault_tolerance,
    eval_plan_coherence,
    eval_context_retention,
    eval_subtask_completion,
    compute_reproducibility_score,
    _kr_strip_particle,
    _is_fact_retained_in_text,
    _KOREAN_UNITS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def monitor():
    return PerformanceMonitor()


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Config 데이터클래스 기본 생성 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigDataclasses:
    def test_instruction_config_defaults(self):
        cfg = InstructionConfig()
        assert cfg.expected_format is None
        assert cfg.required_sections == []
        assert cfg.max_chars is None
        assert cfg.min_chars is None
        assert cfg.max_words is None
        assert cfg.min_words is None
        assert cfg.forbidden_phrases == []
        assert cfg.required_keywords == []
        assert cfg.expected_language is None
        assert cfg.fail_on_violation is False
        assert cfg.violation_weight == 0.1

    def test_instruction_config_custom(self):
        cfg = InstructionConfig(
            expected_format="json",
            required_sections=["summary"],
            max_chars=200,
            required_keywords=["key1", "key2"],
            fail_on_violation=True,
        )
        assert cfg.expected_format == "json"
        assert "summary" in cfg.required_sections
        assert cfg.max_chars == 200
        assert cfg.fail_on_violation is True

    def test_loop_detection_config_defaults(self):
        cfg = LoopDetectionConfig()
        assert cfg.consecutive_repeat_threshold == 3
        assert cfg.window_size == 5
        assert cfg.duplicate_in_window_threshold == 3
        assert cfg.check_response_loop is False
        assert cfg.response_similarity_threshold == 0.95
        assert cfg.on_loop_detected == "record"

    def test_loop_detection_config_custom(self):
        cfg = LoopDetectionConfig(
            consecutive_repeat_threshold=2,
            on_loop_detected="warn",
        )
        assert cfg.consecutive_repeat_threshold == 2
        assert cfg.on_loop_detected == "warn"

    def test_goal_alignment_config_defaults(self):
        cfg = GoalAlignmentConfig()
        assert cfg.use_keyword_overlap is True
        assert cfg.goal_tool_map == {}
        assert cfg.alignment_threshold == 0.6
        assert cfg.ignore_no_tool_tasks is True

    def test_reproducibility_config_defaults(self):
        cfg = ReproducibilityConfig()
        assert cfg.runs == 3
        assert cfg.similarity_measure == "token_f1"
        assert cfg.reproducibility_threshold == 0.85
        assert cfg.fail_on_low_reproducibility is False

    def test_reproducibility_config_custom(self):
        cfg = ReproducibilityConfig(runs=5, similarity_measure="jaccard", reproducibility_threshold=0.9)
        assert cfg.runs == 5
        assert cfg.similarity_measure == "jaccard"

    def test_fault_tolerance_config_defaults(self):
        cfg = FaultToleranceConfig()
        assert cfg.check_fallback_attempts is True
        assert cfg.partial_success_threshold == 0.5
        assert cfg.score_recovery_quality is True
        assert cfg.expected_fallback_tools == {}

    def test_plan_config_defaults(self):
        cfg = PlanConfig()
        assert cfg.plan_field == "plan"
        assert cfg.steps_field == "steps"
        assert cfg.check_goal_coverage is True
        assert cfg.check_step_ordering is True
        assert cfg.check_executability is True
        assert cfg.available_tools == []
        assert cfg.min_steps == 2
        assert cfg.max_steps == 15

    def test_plan_config_custom(self):
        cfg = PlanConfig(
            available_tools=["search", "summarize"],
            min_steps=3,
            max_steps=10,
        )
        assert "search" in cfg.available_tools
        assert cfg.min_steps == 3


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: eval_instruction_adherence 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalInstructionAdherence:
    def test_plain_response_passes(self):
        cfg = InstructionConfig(expected_format="plain")
        result = eval_instruction_adherence("This is a plain response.", cfg)
        assert result["score"] == 1.0
        assert result["violation_count"] == 0

    def test_json_format_valid(self):
        cfg = InstructionConfig(expected_format="json")
        result = eval_instruction_adherence('{"key": "value"}', cfg)
        assert result["checks"]["format"] is True

    def test_json_format_invalid(self):
        cfg = InstructionConfig(expected_format="json")
        result = eval_instruction_adherence("This is not JSON", cfg)
        assert result["checks"]["format"] is False
        assert result["violation_count"] > 0

    def test_markdown_format_valid(self):
        cfg = InstructionConfig(expected_format="markdown")
        result = eval_instruction_adherence("# Heading\n\nSome **bold** text", cfg)
        assert result["checks"]["format"] is True

    def test_yaml_format_valid(self):
        cfg = InstructionConfig(expected_format="yaml")
        result = eval_instruction_adherence("key: value\nother: data", cfg)
        assert result["checks"]["format"] is True

    def test_required_sections_pass(self):
        cfg = InstructionConfig(required_sections=["Introduction", "Conclusion"])
        resp = "Introduction: blah blah. Conclusion: done."
        result = eval_instruction_adherence(resp, cfg)
        assert result["checks"]["sections"] is True

    def test_required_sections_fail(self):
        cfg = InstructionConfig(required_sections=["Introduction", "Conclusion"])
        result = eval_instruction_adherence("Just some text.", cfg)
        assert result["checks"]["sections"] is False
        assert result["violation_count"] > 0

    def test_required_sections_no_false_positive_substring(self):
        # "AI" ⊂ "said" (s-a-i-d) 서브스트링 오탐 방지 — 경계 인식 매칭 확인
        cfg = InstructionConfig(required_sections=["AI"])
        result = eval_instruction_adherence("I said nothing about artificial intelligence.", cfg)
        assert result["checks"]["sections"] is False  # "AI" 섹션이 없음

    def test_max_chars_pass(self):
        cfg = InstructionConfig(max_chars=100)
        result = eval_instruction_adherence("Short text", cfg)
        assert result["checks"]["length"] is True

    def test_max_chars_fail(self):
        cfg = InstructionConfig(max_chars=10)
        result = eval_instruction_adherence("A" * 50, cfg)
        assert result["checks"]["length"] is False

    def test_min_chars_fail(self):
        cfg = InstructionConfig(min_chars=50)
        result = eval_instruction_adherence("Short", cfg)
        assert result["checks"]["length"] is False

    def test_forbidden_phrases_pass(self):
        cfg = InstructionConfig(forbidden_phrases=["I don't know"])
        result = eval_instruction_adherence("The answer is 42.", cfg)
        assert result["checks"]["forbidden"] is True

    def test_forbidden_phrases_fail(self):
        cfg = InstructionConfig(forbidden_phrases=["I don't know"])
        result = eval_instruction_adherence("I don't know the answer.", cfg)
        assert result["checks"]["forbidden"] is False
        assert result["violation_count"] > 0

    def test_forbidden_phrases_no_false_positive_substring(self):
        # "hate" ⊂ "whatever" 서브스트링 오탐 방지 — 경계 인식 매칭 사용 확인
        cfg = InstructionConfig(forbidden_phrases=["hate"])
        result = eval_instruction_adherence("whatever you prefer", cfg)
        assert result["checks"]["forbidden"] is True  # "hate"가 단어 경계로 존재하지 않음

    def test_required_keywords_pass(self):
        cfg = InstructionConfig(required_keywords=["answer", "42"])
        result = eval_instruction_adherence("The answer is 42.", cfg)
        assert result["checks"]["keywords"] is True

    def test_required_keywords_fail(self):
        cfg = InstructionConfig(required_keywords=["quantum", "physics"])
        result = eval_instruction_adherence("The answer is 42.", cfg)
        assert result["checks"]["keywords"] is False

    def test_score_decreases_with_violations(self):
        cfg = InstructionConfig(
            required_keywords=["keyword1"],
            forbidden_phrases=["bad phrase"],
        )
        result_clean = eval_instruction_adherence("keyword1 present", cfg)
        result_bad = eval_instruction_adherence("bad phrase here, keyword1 missing", cfg)
        assert result_clean["score"] >= result_bad["score"]

    def test_fail_on_violation_does_not_raise(self):
        """fail_on_violation=True여도 helper 함수 자체는 예외를 던지지 않음."""
        cfg = InstructionConfig(
            required_keywords=["missing_keyword_xyz"],
            fail_on_violation=True,
        )
        result = eval_instruction_adherence("This response has no matching keyword", cfg)
        assert result["violation_count"] > 0  # violation 있음
        # helper는 예외 없이 반환

    def test_empty_response(self):
        cfg = InstructionConfig(required_keywords=["word"])
        result = eval_instruction_adherence("", cfg)
        assert "score" in result

    def test_max_words_pass(self):
        cfg = InstructionConfig(max_words=5)
        result = eval_instruction_adherence("one two three", cfg)
        assert result["checks"]["length"] is True

    def test_max_words_fail(self):
        cfg = InstructionConfig(max_words=2)
        result = eval_instruction_adherence("one two three four five", cfg)
        assert result["checks"]["length"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: eval_loop_detection 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalLoopDetection:
    def _make_tool_calls(self, names):
        return [{"name": n, "success": True} for n in names]

    def test_no_loop(self):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=3)
        tools = self._make_tool_calls(["search", "summarize", "format"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is False

    def test_consecutive_repeat_detected(self):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=3)
        tools = self._make_tool_calls(["search", "search", "search", "summarize"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is True
        assert result["loop_type"] == "consecutive_repeat"
        assert result["loop_tool"] == "search"

    def test_consecutive_repeat_not_reached(self):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=4)
        tools = self._make_tool_calls(["search", "search", "search", "summarize"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is False

    def test_window_duplicate_detected(self):
        cfg = LoopDetectionConfig(window_size=5, duplicate_in_window_threshold=3)
        tools = self._make_tool_calls(["search", "format", "search", "process", "search"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is True
        assert result["loop_type"] == "window_duplicate"

    def test_window_duplicate_not_reached(self):
        cfg = LoopDetectionConfig(window_size=5, duplicate_in_window_threshold=4)
        tools = self._make_tool_calls(["search", "format", "search", "process", "search"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is False

    def test_empty_tool_calls(self):
        cfg = LoopDetectionConfig()
        result = eval_loop_detection([], None, cfg)
        assert result["detected"] is False

    def test_single_tool_call(self):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=3)
        tools = self._make_tool_calls(["search"])
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is False

    def test_result_keys(self):
        cfg = LoopDetectionConfig()
        result = eval_loop_detection([], None, cfg)
        assert "detected" in result
        assert "loop_type" in result
        assert "loop_at_step" in result
        assert "loop_tool" in result


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: eval_goal_alignment 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalGoalAlignment:
    def _make_tool_calls(self, names):
        return [{"name": n, "success": True} for n in names]

    def test_no_tool_calls_ignore(self):
        cfg = GoalAlignmentConfig(ignore_no_tool_tasks=True)
        result = eval_goal_alignment("search for data", [], cfg)
        assert result is None

    def test_no_tool_calls_no_ignore(self):
        cfg = GoalAlignmentConfig(ignore_no_tool_tasks=False)
        result = eval_goal_alignment("search for data", [], cfg)
        assert result is not None
        assert "score" in result

    def test_goal_tool_map_aligned(self):
        cfg = GoalAlignmentConfig(
            use_keyword_overlap=False,
            goal_tool_map={"search": ["web_search", "db_lookup"]},
            ignore_no_tool_tasks=False,
        )
        tools = self._make_tool_calls(["web_search"])
        result = eval_goal_alignment("search for information", tools, cfg)
        assert result is not None
        assert result["score"] > 0

    def test_keyword_overlap_method(self):
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=False)
        tools = self._make_tool_calls(["search"])
        result = eval_goal_alignment("search and retrieve data", tools, cfg)
        assert result is not None
        assert result["method"] == "keyword_overlap"
        assert "score" in result

    def test_result_structure(self):
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=False)
        tools = self._make_tool_calls(["search"])
        result = eval_goal_alignment("find something", tools, cfg)
        if result is not None:
            assert "score" in result
            assert "method" in result

    def test_keyword_overlap_stopword_only_question_returns_none(self):
        # 질문이 stopword만으로 구성되면 score=None — Gate A avg_goal_a 오염 방지
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=False)
        tools = self._make_tool_calls(["search", "summarize"])
        result = eval_goal_alignment("what is the", tools, cfg)
        assert result is not None
        assert result["score"] is None
        assert result["method"] == "keyword_overlap_no_tokens"

    def test_tool_name_key_format_supported(self):
        # 데코레이터 내부 포맷("tool_name" 키)이 올바르게 인식되는지 검증
        # 기존 "name" 키 포맷도 하위 호환 유지
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=False)

        # "tool_name" 포맷 (데코레이터 내부 포맷)
        tools_toolname = [{"tool_name": "search", "success": True}]
        r1 = eval_goal_alignment("search for data", tools_toolname, cfg)
        assert r1 is not None
        assert r1["score"] is not None
        assert r1["score"] > 0, "tool_name 키 포맷의 도구 이름이 keyword_overlap으로 정렬돼야 함"

        # "tool" 포맷도 지원
        tools_tool = [{"tool": "search", "success": True}]
        r2 = eval_goal_alignment("search for data", tools_tool, cfg)
        assert r2 is not None
        assert r2["score"] is not None
        assert r2["score"] > 0, "tool 키 포맷의 도구 이름이 keyword_overlap으로 정렬돼야 함"

        # "name" 포맷 (하위 호환)
        tools_name = [{"name": "search", "success": True}]
        r3 = eval_goal_alignment("search for data", tools_name, cfg)
        assert r3 is not None
        assert r3["score"] is not None
        assert r3["score"] > 0, "name 키 포맷 하위 호환이 유지돼야 함"

        # 모든 포맷이 동일한 점수를 반환해야 함
        assert r1["score"] == r2["score"] == r3["score"]

    def test_tool_name_key_goal_tool_map(self):
        # goal_tool_map 방식에서도 "tool_name" 키 인식 검증
        cfg = GoalAlignmentConfig(
            use_keyword_overlap=False,
            goal_tool_map={"search": ["web_search"]},
            ignore_no_tool_tasks=False,
        )
        tools_toolname = [{"tool_name": "web_search", "success": True}]
        result = eval_goal_alignment("search for data", tools_toolname, cfg)
        assert result is not None
        assert result["score"] > 0, "tool_name 포맷이 goal_tool_map에서도 정렬 인식돼야 함"


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: eval_fault_tolerance 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalFaultTolerance:
    def test_no_failures(self):
        cfg = FaultToleranceConfig()
        tools = [{"name": "search", "success": True}, {"name": "format", "success": True}]
        result = eval_fault_tolerance(tools, cfg)
        assert not result["failures_detected"]
        # grade "none" = no failures to evaluate (system worked perfectly)
        assert result["grade"] in ("good", "none")

    def test_failure_with_fallback(self):
        cfg = FaultToleranceConfig(check_fallback_attempts=True)
        tools = [
            {"name": "primary_search", "success": False},
            {"name": "backup_search", "success": True},
        ]
        result = eval_fault_tolerance(tools, cfg)
        assert result["failures_detected"]
        assert result["fallback_attempts"] >= 1

    def test_failure_no_fallback(self):
        cfg = FaultToleranceConfig(check_fallback_attempts=True)
        tools = [
            {"name": "search", "success": False},
        ]
        result = eval_fault_tolerance(tools, cfg)
        assert result["failures_detected"]
        assert result["fallback_attempts"] == 0
        assert result["grade"] in ("poor", "partial")

    def test_empty_tool_calls(self):
        cfg = FaultToleranceConfig()
        result = eval_fault_tolerance([], cfg)
        assert not result["failures_detected"]

    def test_recovery_rate_calculation(self):
        cfg = FaultToleranceConfig()
        tools = [
            {"name": "t1", "success": False},
            {"name": "t1_backup", "success": True},
            {"name": "t2", "success": False},
            {"name": "t2_backup", "success": False},
        ]
        result = eval_fault_tolerance(tools, cfg)
        assert result["failures_detected"]
        assert "recovery_rate" in result
        assert 0.0 <= result["recovery_rate"] <= 1.0

    def test_result_keys(self):
        cfg = FaultToleranceConfig()
        result = eval_fault_tolerance([], cfg)
        assert "failures_detected" in result
        assert "fallback_attempts" in result
        assert "recovery_rate" in result
        assert "grade" in result


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: eval_plan_coherence 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestEvalPlanCoherence:
    def test_no_plan_returns_none(self):
        cfg = PlanConfig()
        result = eval_plan_coherence("This is just a response.", "What is the plan?", cfg)
        # 플랜이 없으면 None 반환 가능
        if result is not None:
            assert "score" in result

    def test_numbered_steps_parsed(self):
        cfg = PlanConfig(check_goal_coverage=True)
        resp = "1. Gather data\n2. Process information\n3. Output results"
        result = eval_plan_coherence(resp, "gather and process", cfg)
        if result is not None:
            assert "score" in result
            assert result["score"] >= 0.0

    def test_json_plan_parsed(self):
        cfg = PlanConfig()
        plan = json.dumps({"steps": ["gather data", "process", "output"]})
        result = eval_plan_coherence(plan, "process data", cfg)
        if result is not None:
            assert "score" in result

    def test_executability_check(self):
        cfg = PlanConfig(
            check_executability=True,
            available_tools=["search", "format"],
        )
        resp = "1. Use search\n2. Use format\n3. Output results"
        result = eval_plan_coherence(resp, "search and format", cfg)
        if result is not None:
            assert "score" in result

    def test_result_keys(self):
        cfg = PlanConfig()
        resp = "1. Step one\n2. Step two\n3. Step three"
        result = eval_plan_coherence(resp, "do steps", cfg)
        if result is not None:
            assert "score" in result
            assert "goal_coverage" in result
            assert "ordering_score" in result
            assert "executability_score" in result

    def test_executability_no_false_positive_substring(self):
        # "get" ⊂ "budget" 서브스트링 오탐 방지 — 경계 인식 매칭 확인
        cfg = PlanConfig(
            check_executability=True,
            available_tools=["get"],
            check_goal_coverage=False,
            check_step_ordering=False,
        )
        resp = "1. Set budget\n2. Review results\n3. Finalize report"
        result = eval_plan_coherence(resp, "budget review", cfg)
        if result is not None:
            # "get" is NOT a word boundary match in "budget" → executability_score should be 0.0
            assert result["executability_score"] == 0.0

    def test_ordering_markers_no_false_positive_substring(self):
        # "after" ⊂ "thereafter", "second" ⊂ "secondary", "then" ⊂ "authenticate" — 오탐 방지
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        # 각 스텝에 순서 마커가 부분 문자열로 포함되지만 독립 단어가 아님
        resp = "1. Thereafter we proceed\n2. Secondary validation\n3. Authenticate the user"
        result = eval_plan_coherence(resp, "validate", cfg)
        # 번호 목록이므로 is_numbered=True → ordering_score=1.0 (번호 목록 최우선)
        # → ordering_score가 부분문자열 오탐으로 1.0이 되어선 안 된다는 것을 확인하기 위해
        # 번호 없는 버전으로 테스트
        resp_unnumbered = "Thereafter we proceed. Secondary validation. Authenticate the user."
        result2 = eval_plan_coherence(resp_unnumbered, "validate", cfg)
        if result2 is not None:
            # "thereafter"/"secondary"/"authenticate" 모두 독립 마커가 아님 → ordering_score=0.0
            assert result2["ordering_score"] == 0.0

    def test_disabled_check_fields_return_none(self):
        # 비활성 체크 필드는 0.0/1.0 초기값 대신 None을 반환해야 함 (진단 혼동 방지)
        resp = "1. Gather data\n2. Process\n3. Output results"

        # goal_coverage: check_goal_coverage=False → None
        cfg_no_goal = PlanConfig(
            check_goal_coverage=False,
            check_step_ordering=True,
            check_executability=False,
        )
        r = eval_plan_coherence(resp, "process data", cfg_no_goal)
        if r is not None:
            assert r["goal_coverage"] is None, "check_goal_coverage=False이면 goal_coverage=None이어야 함"
            assert r["ordering_score"] is not None, "check_step_ordering=True이면 ordering_score가 측정값이어야 함"

        # ordering_score: check_step_ordering=False → None
        cfg_no_order = PlanConfig(
            check_goal_coverage=True,
            check_step_ordering=False,
            check_executability=False,
        )
        r2 = eval_plan_coherence(resp, "gather process output", cfg_no_order)
        if r2 is not None:
            assert r2["ordering_score"] is None, "check_step_ordering=False이면 ordering_score=None이어야 함"

        # executability_score: check_executability=False → None
        cfg_no_exec = PlanConfig(
            check_goal_coverage=True,
            check_step_ordering=True,
            check_executability=False,
        )
        r3 = eval_plan_coherence(resp, "gather process output", cfg_no_exec)
        if r3 is not None:
            assert r3["executability_score"] is None, "check_executability=False이면 executability_score=None이어야 함"

        # available_tools=[] (비어있음)인 경우에도 executability_score=None
        cfg_empty_tools = PlanConfig(
            check_goal_coverage=True,
            check_step_ordering=True,
            check_executability=True,
            available_tools=[],
        )
        r4 = eval_plan_coherence(resp, "gather process output", cfg_empty_tools)
        if r4 is not None:
            assert r4["executability_score"] is None, "available_tools=[]이면 executability_score=None이어야 함"

    def test_single_step_plain_text_ordering_score_is_one(self):
        # Bug R32: step_count=1 인 비JSON·비번호 플랜은 순서 문제가 정의상 없음에도
        # sequential marker 검사에서 0.0을 받던 버그.
        # Fix: step_count <= 1 → ordering_score=1.0 (trivially ordered)
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
            min_steps=1,  # 1-step 허용
        )
        # 단일 불릿 단계 — JSON 아님, 번호 없음, sequential marker 없음
        single_bullet = "- Gather all required data"
        result = eval_plan_coherence(single_bullet, "gather data", cfg)
        assert result is not None, "단일 불릿 단계가 파싱되어야 함"
        assert result["ordering_score"] == 1.0, (
            f"1-step 플랜의 ordering_score가 1.0이어야 하지만 {result['ordering_score']} — "
            "sequential marker 없다는 이유로 0.0이 반환되던 버그 회귀"
        )

    def test_single_step_score_not_halved_by_ordering_zero(self):
        # 1-step 플랜에서 ordering_score=0.0 이 goal_coverage와 평균되어
        # score가 절반으로 억제되던 Gate A 오염 시나리오 회귀 방지
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=True,
            check_executability=False,
            min_steps=1,
        )
        single_step = "- Gather data"
        result = eval_plan_coherence(single_step, "gather data", cfg)
        assert result is not None
        # goal_coverage >= some non-zero value, ordering_score=1.0 → score > 0.5
        # Without fix, score = (goal_coverage + 0.0)/2 ≤ 0.5
        assert result["ordering_score"] == 1.0
        assert result["score"] > 0.5, (
            "1-step 플랜 score가 0.5를 초과해야 함 — ordering_score=0.0 이 평균에 포함되던 버그"
        )

    def test_multi_step_plain_text_ordering_still_uses_markers(self):
        # 2개 이상의 비번호·비JSON 단계는 여전히 sequential marker 기반으로 평가 (회귀 방지)
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        # 마커 없는 2-step 불릿
        no_markers = "- Do A\n- Do B"
        result = eval_plan_coherence(no_markers, "something", cfg)
        if result is not None:
            # step_count >= 2이면 marker 검사 적용 — 마커 없으므로 0.0
            assert result["ordering_score"] == 0.0, (
                "2-step 비번호 비JSON 플랜에서 마커 없으면 ordering_score=0.0이어야 함 (회귀)"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Section 6-B: 한국어 조사 탈락 매칭 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestKrStripParticle:
    """_kr_strip_particle 헬퍼 단위 테스트."""

    def test_basic_particle_strip(self):
        assert _kr_strip_particle("서울의") == "서울"
        assert _kr_strip_particle("날씨를") == "날씨"
        assert _kr_strip_particle("학교에서") == "학교"
        assert _kr_strip_particle("서울에게") == "서울"

    def test_non_korean_passthrough(self):
        assert _kr_strip_particle("weather") == "weather"
        assert _kr_strip_particle("Seoul") == "Seoul"
        assert _kr_strip_particle("123") == "123"

    def test_too_short_stem_no_strip(self):
        # 조사를 제거하면 어근이 2글자 미만이 되는 경우 원형 유지
        assert _kr_strip_particle("이에서") == "이에서"  # 어근 "이" = 1글자 → 유지

    def test_plan_coherence_korean_particle_coverage(self):
        # 질문에 조사 부착형 토큰, 계획에 어근 형태 — goal_coverage > 0 이어야 함
        # 기존 버그: '서울의' ≠ '서울' → goal_coverage=0.0
        # 수정 후: _kr_strip_particle('서울의')='서울' → plan에서 발견 → matched
        cfg = PlanConfig(
            check_goal_coverage=True,
            check_step_ordering=False,
            check_executability=False,
        )
        question = "서울의 날씨를 알려주세요"
        response = "1. 날씨 정보를 검색합니다\n2. 서울 기온을 확인합니다\n3. 결과를 출력합니다"
        result = eval_plan_coherence(response, question, cfg)
        assert result is not None
        # goal_coverage > 0: '서울의'→'서울', '날씨를'→'날씨' 모두 plan에서 발견
        assert result["goal_coverage"] is not None
        assert result["goal_coverage"] > 0.0, (
            f"한국어 조사 탈락 매칭 실패: goal_coverage={result['goal_coverage']}"
        )

    def test_context_retention_korean_particle_goal(self):
        # 질문의 조사 부착 토큰이 응답의 어근 형태와 매칭돼야 함
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(
            key_entities=[],
            check_original_goal=True,
            goal_overlap_threshold=0.3,
        )
        question = "서울의 날씨를 알려주세요"
        # 응답에 '서울'과 '날씨' (어근 형태)만 포함
        response = "서울 날씨는 맑습니다."
        result = eval_context_retention(response, question, "", cfg)
        assert result is not None
        assert result["retention_score"] is not None
        # '서울의'→'서울', '날씨를'→'날씨' 모두 응답에서 어근으로 발견
        assert result["goal_retained"] is True, (
            f"한국어 조사 탈락 매칭 실패: goal_retained={result['goal_retained']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: compute_reproducibility_score 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeReproducibilityScore:
    def test_identical_responses(self):
        responses = ["The answer is 42", "The answer is 42", "The answer is 42"]
        result = compute_reproducibility_score(responses)
        assert result["score"] == pytest.approx(1.0, abs=0.01)
        assert result["variance"] == pytest.approx(0.0, abs=0.01)

    def test_different_responses(self):
        responses = ["apples", "oranges", "bananas"]
        result = compute_reproducibility_score(responses)
        assert result["score"] < 0.5

    def test_token_f1_measure(self):
        responses = ["cat sat on mat", "cat sat on mat"]
        result = compute_reproducibility_score(responses, measure="token_f1")
        assert result["score"] == pytest.approx(1.0, abs=0.01)

    def test_jaccard_measure(self):
        responses = ["apple banana cherry", "apple banana cherry"]
        result = compute_reproducibility_score(responses, measure="jaccard")
        assert result["score"] == pytest.approx(1.0, abs=0.01)

    def test_exact_measure_identical(self):
        responses = ["exact same", "exact same", "exact same"]
        result = compute_reproducibility_score(responses, measure="exact")
        assert result["score"] == 1.0

    def test_exact_measure_different(self):
        responses = ["first response", "second response"]
        result = compute_reproducibility_score(responses, measure="exact")
        assert result["score"] == 0.0

    def test_single_response(self):
        """단일 응답 — 비교 불가, score 반환 가능."""
        result = compute_reproducibility_score(["only one"])
        assert "score" in result

    def test_result_keys(self):
        result = compute_reproducibility_score(["a", "b", "c"])
        assert "score" in result
        assert "variance" in result
        assert "pairwise_scores" in result
        assert "run_count" in result

    def test_run_count(self):
        responses = ["r1", "r2", "r3"]
        result = compute_reproducibility_score(responses)
        assert result["run_count"] == 3

    def test_pairwise_scores_type(self):
        responses = ["hello world", "hello world", "hello world"]
        result = compute_reproducibility_score(responses)
        assert isinstance(result["pairwise_scores"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: @agent_eval 통합 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentEvalHarnessIntegration:
    def test_instruction_config_recorded_in_extra(self, monitor):
        cfg = InstructionConfig(expected_format="plain", required_keywords=["answer"])

        @agent_eval(monitor, task_type="qa", instructions=cfg)
        def agent(question, ground_truth=""):
            return "The answer is yes"

        agent("Is it possible?", ground_truth="yes")
        t = monitor.tasks[-1]
        assert t.extra is not None
        assert "instruction_adherence" in t.extra
        assert "score" in t.extra["instruction_adherence"]

    def test_instruction_config_fail_on_violation(self, monitor):
        cfg = InstructionConfig(
            required_keywords=["required_word"],
            fail_on_violation=True,
        )

        @agent_eval(monitor, task_type="qa", instructions=cfg)
        def agent(question, ground_truth=""):
            return "Response without the word"

        agent("question", ground_truth="")
        t = monitor.tasks[-1]
        assert t.extra is not None
        assert "instruction_adherence" in t.extra
        # violation 있으면 success=False
        assert t.success is False

    def test_loop_detection_config_no_loop(self, monitor):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=3)

        @agent_eval(monitor, task_type="qa", loop_detection=cfg)
        def agent(question, ground_truth=""):
            return "response"

        agent("question")
        t = monitor.tasks[-1]
        if t.extra and "loop_detection" in t.extra:
            assert t.extra["loop_detection"]["detected"] is False

    def test_goal_alignment_config(self, monitor):
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=True)

        @agent_eval(monitor, task_type="qa", goal_alignment=cfg)
        def agent(question, ground_truth=""):
            return "response"

        agent("search for data")
        t = monitor.tasks[-1]
        # no tool calls → ignored (None stored or absent)
        # should not raise

    def test_fault_tolerance_config(self, monitor):
        cfg = FaultToleranceConfig(check_fallback_attempts=True)

        @agent_eval(monitor, task_type="qa", fault_tolerance=cfg)
        def agent(question, ground_truth=""):
            return "response"

        agent("question")
        t = monitor.tasks[-1]
        if t.extra and "fault_tolerance" in t.extra:
            assert "grade" in t.extra["fault_tolerance"]

    def test_plan_tracking_config(self, monitor):
        cfg = PlanConfig(check_goal_coverage=True)

        @agent_eval(monitor, task_type="planning", plan_tracking=cfg)
        def agent(question, ground_truth=""):
            return "1. Gather data\n2. Process it\n3. Output"

        agent("Make a plan")
        t = monitor.tasks[-1]
        # result may or may not contain plan_coherence depending on step extraction
        # just verify no exception

    def test_multiple_harness_configs(self, monitor):
        """여러 harness config 동시 적용 — 모두 extra에 저장됨."""
        @agent_eval(
            monitor,
            task_type="qa",
            instructions=InstructionConfig(expected_format="plain"),
            loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
            fault_tolerance=FaultToleranceConfig(),
        )
        def agent(question, ground_truth=""):
            return "plain response text"

        agent("question")
        t = monitor.tasks[-1]
        assert t.extra is not None
        assert "instruction_adherence" in t.extra
        if "loop_detection" in t.extra:
            assert "detected" in t.extra["loop_detection"]

    def test_no_harness_config_backward_compat(self, monitor):
        """harness config 없으면 기존 동작과 동일."""
        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "response"

        agent("question", ground_truth="response")
        t = monitor.tasks[-1]
        assert t is not None
        assert t.task_type == "qa"

    def test_reproducibility_config_sync(self, monitor):
        call_count = [0]

        @agent_eval(
            monitor,
            task_type="qa",
            reproducibility=ReproducibilityConfig(runs=2, similarity_measure="token_f1"),
        )
        def agent(question, ground_truth=""):
            call_count[0] += 1
            return "consistent answer"

        agent("question")
        # reproducibility requires runs=2, so function called 2 times
        assert call_count[0] == 2
        t = monitor.tasks[-1]
        assert t.extra is not None
        assert "reproducibility" in t.extra
        assert t.extra["reproducibility"]["score"] >= 0.9  # consistent answers → high score

    def test_reproducibility_score_varies(self, monitor):
        counter = [0]

        @agent_eval(
            monitor,
            task_type="qa",
            reproducibility=ReproducibilityConfig(runs=3, similarity_measure="token_f1"),
        )
        def agent(question, ground_truth=""):
            counter[0] += 1
            return f"answer number {counter[0]}"  # different each time

        agent("question")
        t = monitor.tasks[-1]
        assert "reproducibility" in t.extra
        # Different answers → lower score
        assert t.extra["reproducibility"]["score"] < 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Section 9: @batch_eval harness params 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchEvalHarnessIntegration:
    def test_batch_eval_instructions(self, monitor):
        cfg = InstructionConfig(required_keywords=["result"])

        @batch_eval(monitor, task_type="qa", instructions=cfg)
        def batch_agent(questions, ground_truths=None):
            return ["result one", "result two", "result three"]

        batch_agent(["q1", "q2", "q3"])
        assert len(monitor.tasks) == 3
        for t in monitor.tasks:
            if t.extra and "instruction_adherence" in t.extra:
                assert t.extra["instruction_adherence"]["checks"]["keywords"] is True

    def test_batch_eval_loop_detection(self, monitor):
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=3)

        @batch_eval(monitor, task_type="qa", loop_detection=cfg)
        def batch_agent(questions, ground_truths=None):
            return [f"answer {i}" for i in range(len(questions))]

        batch_agent(["q1", "q2"])
        assert len(monitor.tasks) == 2

    def test_batch_eval_no_harness(self, monitor):
        """harness config 없으면 기존 동작."""
        @batch_eval(monitor, task_type="qa")
        def batch_agent(questions, ground_truths=None):
            return ["a1", "a2"]

        batch_agent(["q1", "q2"], ground_truths=["a1", "a2"])
        assert len(monitor.tasks) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Section 10: @conversation_eval harness params 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestConversationEvalHarnessParams:
    def test_conversation_eval_accepts_instructions(self, monitor):
        """conversation_eval에서 instructions 파라미터 수용 — 예외 없음."""
        cfg = InstructionConfig(expected_format="plain")

        @conversation_eval(monitor, instructions=cfg)
        def chatbot(session_id, question, ground_truth=""):
            return "response"

        chatbot("sess_1", "Hello?")
        flush_conversation("sess_1")

    def test_conversation_eval_accepts_loop_detection(self, monitor):
        cfg = LoopDetectionConfig()

        @conversation_eval(monitor, loop_detection=cfg)
        def chatbot(session_id, question, ground_truth=""):
            return "response"

        chatbot("sess_2", "Hello?")
        flush_conversation("sess_2")

    def test_conversation_eval_backward_compat(self, monitor):
        """harness config 없으면 기존 동작."""
        @conversation_eval(monitor)
        def chatbot(session_id, question, ground_truth=""):
            return "response"

        chatbot("sess_3", "Hello?")
        chatbot("sess_3", "How are you?")
        flushed = flush_conversation("sess_3")
        assert flushed is True


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: 엣지 케이스 및 에러 핸들링
# ─────────────────────────────────────────────────────────────────────────────

class TestHarnessEdgeCases:
    def test_instruction_adherence_no_exception_on_empty_config(self):
        cfg = InstructionConfig()
        result = eval_instruction_adherence("some response", cfg)
        # 검사 항목 없음 → score=None (Gate A avg_ifr 집계 제외)
        assert result["score"] is None
        assert result["violation_count"] == 0

    def test_loop_detection_dict_tool_calls(self):
        """tool_calls가 dict 리스트 형식."""
        cfg = LoopDetectionConfig(consecutive_repeat_threshold=2)
        tools = [
            {"name": "search", "input": {}, "output": "result"},
            {"name": "search", "input": {}, "output": "result"},
        ]
        result = eval_loop_detection(tools, None, cfg)
        assert result["detected"] is True

    def test_goal_alignment_with_empty_question(self):
        cfg = GoalAlignmentConfig(use_keyword_overlap=True, ignore_no_tool_tasks=False)
        tools = [{"name": "search", "success": True}]
        result = eval_goal_alignment("", tools, cfg)
        # 빈 질문이어도 예외 없이 반환
        if result is not None:
            assert "score" in result

    def test_reproducibility_two_responses(self):
        result = compute_reproducibility_score(["same", "same"])
        assert result["score"] == pytest.approx(1.0, abs=0.01)
        assert result["run_count"] == 2

    def test_context_retention_noop_returns_none_score(self):
        # check_original_goal=False + no entities → 측정 불가 → retention_score=None (Gate A 제외)
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=False)
        result = eval_context_retention("some response", "what is X", "", cfg)
        assert result["retention_score"] is None
        assert result.get("no_checks") is True

    def test_context_retention_empty_question_noop_returns_none_score(self):
        # question="" + no entities → 측정 불가 → retention_score=None (Gate A 제외)
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=True)
        result = eval_context_retention("some response", "", "", cfg)
        assert result["retention_score"] is None

    def test_context_retention_stopword_only_question_noop_returns_none_score(self):
        # question이 stopword만으로 구성(q_sig={}) + key_entities=[] → retention_score=1.0 허위 상향 방지
        # "How?" → "how" ∈ _GOAL_STOPWORDS → q_sig={} → _can_check_goal=False → no_checks=True
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=True)
        result = eval_context_retention("The meeting is confirmed.", "How?", "", cfg)
        assert result["retention_score"] is None, (
            f"stopword-only question should yield retention_score=None, not {result['retention_score']}"
        )
        assert result.get("no_checks") is True

    def test_context_retention_autoextract_filters_stopwords(self):
        # auto-extract: "The", "In" 같은 문장 시작 기능어는 entity 목록에서 제외
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=False)
        context = "The capital is Seoul. In Korea, population is large."
        # "Seoul"은 고유명사 → 추출; "The", "In" 등 기능어 → 제외
        result = eval_context_retention("Seoul is the answer.", "", context, cfg)
        # "The", "In" 등이 entities에 포함되지 않아야 함 (entity_score 허위 상향 방지)
        retained_lower = [e.lower() for e in result["entities_retained"] + result["entities_lost"]]
        assert "the" not in retained_lower
        assert "in" not in retained_lower

    def test_subtask_marker_no_false_positive_substring(self):
        # "report" ⊂ "reporting" — 2차 마커 체크에서도 경계 인식 매칭 확인
        from agent_evaluator.decorators import SubtaskConfig
        cfg = SubtaskConfig(
            expected_subtasks=["create report"],
            completion_markers=["done"],
        )
        # "reporting done" — "report" in "reporting"은 substring이지만 경계 매칭 실패
        result = eval_subtask_completion("reporting done here", [], cfg)
        assert result["completion_rate"] == 0.0  # false positive 없음

    def test_latin_ratio_excludes_nonletter_chars(self):
        # `[\]^_`` 등 비문자가 latin_ratio에 포함되지 않아야 함 — expected_language="en" false-pass 방지
        cfg = InstructionConfig(expected_language="en")
        # 영문자 없이 백틱·대괄호만 있는 응답 → latin_ratio ≈ 0 → lang_ok=False
        result = eval_instruction_adherence("```[주석] 한국어 응답입니다.```", cfg)
        assert result["checks"]["language"] is False  # 비문자가 Latin으로 오산정되지 않음

    def test_knowledge_retention_implicit_coverage_denominator(self):
        # implicit retention: 분모는 long_tokens(len>=2)만 → 1글자 토큰이 분모를 부풀리지 않음
        from agent_evaluator.decorators import KnowledgeRetentionConfig
        from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention
        cfg = KnowledgeRetentionConfig(
            facts_to_retain=["I am sorry"],   # tokens: ["i","am","sorry"] → long: ["am","sorry"]
            check_from_turn=1,
        )
        # "am sorry" 포함 응답 → long_tokens 기준 coverage=2/2=1.0 → retained
        result = eval_knowledge_retention("I am very sorry about that", [], cfg)
        assert result is not None
        assert "I am sorry" in result["retained_facts"]

    def test_knowledge_retention_autoextract_filters_stopwords(self):
        # auto_extract_seed=True: 문장 시작 기능어("The", "In", "What" 등)가 facts에 포함되면
        # 응답 어디서나 발견되어 retention_score 허위 상향 — stopword 필터로 제거되어야 함
        from agent_evaluator.decorators import KnowledgeRetentionConfig
        from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention
        cfg = KnowledgeRetentionConfig(
            auto_extract_seed=True,
            seed_turns=1,
            check_from_turn=1,
        )
        # 기능어만 있는 텍스트 — "The", "What", "In", "Is" 모두 _GOAL_STOPWORDS
        history = [{"user": "The meeting is scheduled. What should I do? In the morning."}]
        response = "Okay, the meeting is confirmed."
        result = eval_knowledge_retention(response, history, cfg)
        # 기능어 전부 필터링 → facts=[] → None 반환 (0.0 또는 1.0이 아님)
        assert result is None, (
            f"stopword-only auto_extract should return None, not {result}"
        )

    def test_dimension_averages_none_for_unmeasured(self):
        # 미측정 차원은 0.0 대신 None 반환 — Gate A _rqe_a=0.0 포함 방지
        from agent_evaluator import PerformanceMonitor
        m = PerformanceMonitor()
        metrics = m.quality_evaluator.get_quality_metrics()
        # 평가 없음 → dimension_averages 비어 있음 (0.0 sentinel 아님)
        dim_avgs = metrics.get("dimension_averages", {})
        for k, v in dim_avgs.items():
            assert v is None, f"dimension_averages['{k}'] should be None when not measured, got {v}"

    def test_fault_tolerance_all_fail(self):
        cfg = FaultToleranceConfig()
        tools = [
            {"name": "t1", "success": False},
            {"name": "t2", "success": False},
        ]
        result = eval_fault_tolerance(tools, cfg)
        assert result["failures_detected"]
        assert result["grade"] in ("poor", "partial", "good")  # grade depends on fallback detection logic

    def test_context_retention_autoextract_limit_after_filter(self):
        # [:20] 제한이 stopword 필터 전에 적용되면, 기능어 20개가 슬롯을 차지해
        # 21번째 이후의 의미있는 엔티티가 key_entities에서 누락됨
        # Fix: dedup 단계에서 필터 적용 → [:20]은 의미있는 엔티티에만 적용
        from agent_evaluator.decorators import ContextRetentionConfig
        stopword_caps = [
            "The", "An", "Is", "Are", "Was", "Were", "What", "How", "Why", "When",
            "Where", "Who", "Which", "Does", "Did", "Can", "Could", "Will", "Would", "Should",
        ]  # 20개 고유 대문자 기능어 (모두 _GOAL_STOPWORDS에 소문자로 존재)
        # "Pythonista" — 21번째에 배치; filter-before-limit 버그 시 [:20]이 이를 배제
        context = " ".join(stopword_caps) + " Pythonista"
        cfg = ContextRetentionConfig(check_original_goal=False)
        result = eval_context_retention("Pythonista is great.", "", context, cfg)
        all_entities = result["entities_retained"] + result["entities_lost"]
        assert "Pythonista" in all_entities, (
            "[:20] 제한이 필터 전에 적용되어 21번째 의미있는 엔티티 누락 — "
            "filter-before-limit 버그 회귀"
        )

    def test_quality_eval_stopwords_includes_function_words(self):
        # "of", "or", "by", "to" 등 2글자 영어 기능어가 expected_elements로 추출되면
        # completeness 토큰 매칭에서 쉽게 충족되어 Gate A _rqe_a 점수 허위 상향
        # Fix: _QUALITY_EVAL_STOPWORDS에 추가하여 auto-extraction 시 제외
        from agent_evaluator.core.trackers.monitor import _QUALITY_EVAL_STOPWORDS
        for word in ("of", "or", "if", "by", "to", "as", "so", "it", "be"):
            assert word in _QUALITY_EVAL_STOPWORDS, (
                f"'{word}' must be in _QUALITY_EVAL_STOPWORDS — "
                "2글자 기능어가 completeness expected_elements에 포함되면 Gate A 과대평가"
            )

    def test_context_retention_entity_only_score_not_capped_by_goal_weight(self):
        # check_original_goal=False 또는 question="" 시 goal 검사 불가 → _can_check_goal=False
        # 이때 goal_weight=0.4가 _w_sum에 포함되면 max retention_score = entity_weight = 0.6
        # Fix: _can_check_goal=False 이면 entity score만으로 full 점수 산출
        from agent_evaluator.decorators import ContextRetentionConfig
        # key_entities=["Seoul"] + check_original_goal=False → goal 미측정
        cfg = ContextRetentionConfig(key_entities=["Seoul"], check_original_goal=False)
        # Seoul이 응답에 있음 → entity_score=1.0, 올바른 retention_score=1.0 (bug 시 0.6)
        result = eval_context_retention("Seoul is the capital.", "", "", cfg)
        assert result["retention_score"] == 1.0, (
            f"check_original_goal=False인데 goal_weight 페널티로 retention_score={result['retention_score']} "
            "— entity-only 시 1.0이어야 함 (goal_weight-in-denominator 버그 회귀)"
        )
        # 엔티티가 없는 경우도 확인: question="" → goal 측정 불가
        cfg2 = ContextRetentionConfig(key_entities=["Seoul"])
        result2 = eval_context_retention("Seoul is the capital.", "", "", cfg2)
        assert result2["retention_score"] == 1.0, (
            f"question='' → _can_check_goal=False인데 retention_score={result2['retention_score']} "
            "— 1.0이어야 함"
        )

    def test_instruction_adherence_markdown_bullet_at_start(self):
        # r"\n[-*]\s" 패턴은 응답 첫 줄 불릿을 탐지 못함 (앞에 \n 없음)
        # Fix: r"(?:^|\n)[-*][ \t]" 로 교체 — 첫 줄 불릿도 탐지
        cfg = InstructionConfig(expected_format="markdown")
        # 불릿이 응답 시작에 있는 경우 — 이전 패턴에서 False Negative 발생
        result_start = eval_instruction_adherence("- item one\n- item two", cfg)
        assert result_start["checks"]["format"] is True, (
            "첫 줄 불릿('-')이 markdown으로 탐지되지 않음 — r\"\\n[-*]\\s\" 누락 버그 회귀"
        )
        # * 불릿도 동일하게 확인
        result_star = eval_instruction_adherence("* item one\n* item two", cfg)
        assert result_star["checks"]["format"] is True, (
            "첫 줄 '*' 불릿이 markdown으로 탐지되지 않음"
        )
        # 본문 중간 불릿 (기존 동작 유지)
        result_mid = eval_instruction_adherence("Some text\n- item one", cfg)
        assert result_mid["checks"]["format"] is True

    def test_plan_coherence_json_dict_steps_ordering_score_not_zero(self):
        # Bug R31: JSON {"steps":[...]} 형식에서 파싱한 단계는 배열 인덱스로 순서가 확정됨.
        # 이전 코드: is_numbered = bool(re.search(numbering pattern, json_string)) → False
        # → sequential markers 검사 → step descriptions에 "then"/"next" 없음 → ordering_score=0.0
        # Fix: _from_json=True → is_numbered=True → ordering_score=1.0
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        plan_json = json.dumps({"steps": ["Gather data", "Analyze results", "Write report"]})
        result = eval_plan_coherence(plan_json, "gather analyze", cfg)
        assert result is not None, "JSON 플랜은 steps가 3개이므로 None이 아니어야 함"
        assert result["ordering_score"] == 1.0, (
            f"JSON 배열에서 파싱한 플랜의 ordering_score가 1.0이어야 하지만 {result['ordering_score']} — "
            "_from_json 플래그 없이 sequential marker 검사가 적용되어 0.0으로 억제되던 버그 회귀"
        )

    def test_plan_coherence_json_bare_list_ordering_score_not_zero(self):
        # JSON 베어 리스트 형식도 동일하게 _from_json=True → ordering_score=1.0
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        plan_bare = json.dumps(["Step A", "Step B", "Step C"])
        result = eval_plan_coherence(plan_bare, "step complete", cfg)
        assert result is not None
        assert result["ordering_score"] == 1.0, (
            "JSON 베어 리스트에서 파싱한 플랜의 ordering_score가 1.0이어야 함"
        )

    def test_plan_coherence_plain_text_without_numbers_ordering_uses_markers(self):
        # 비JSON·비번호 목록은 여전히 sequential marker 검사를 사용해야 함 (회귀 방지)
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        # "then"/"next" 마커 없는 일반 텍스트 → ordering_score가 marker 기반으로 낮아야 함
        plain = "Do first task. Do second task. Do third task."
        result = eval_plan_coherence(plain, "task", cfg)
        if result is not None:
            # is_numbered=False, _from_json=False → sequential markers 검사 적용
            # → "first"/"second"는 sequential marker가 아니므로 낮거나 0
            assert result["ordering_score"] is not None

    def test_goal_alignment_no_measurement_method_returns_none_score(self):
        # Bug R31: goal_tool_map={} + use_keyword_overlap=False → method="none"
        # 이전 코드: score=0.0 반환 → Gate A avg_goal_a에 거짓 0.0이 포함됨
        # Fix: method=="none" → score=None 반환으로 Gate A 집계에서 제외
        cfg = GoalAlignmentConfig(
            use_keyword_overlap=False,   # keyword_overlap 비활성
            goal_tool_map={},            # goal_tool_map 미설정 (기본값)
            ignore_no_tool_tasks=False,
        )
        tools = [{"name": "some_tool", "success": True}]
        result = eval_goal_alignment("do something with some tool", tools, cfg)
        assert result is not None, "tool_calls 있으면 None이 아닌 dict 반환 필요"
        assert result["score"] is None, (
            f"측정 방법이 없을 때 score가 None이어야 하지만 {result['score']} — "
            "method='none'에서 score=0.0이 반환되어 Gate A를 허위 억제하던 버그 회귀"
        )
        assert result["method"] == "no_measurement"

    def test_agent_eval_with_none_harness_params(self, monitor=None):
        """None harness params → 기존 동작."""
        if monitor is None:
            monitor = PerformanceMonitor()

        @agent_eval(
            monitor,
            task_type="qa",
            instructions=None,
            loop_detection=None,
            goal_alignment=None,
            fault_tolerance=None,
            plan_tracking=None,
            reproducibility=None,
        )
        def agent(question, ground_truth=""):
            return "response"

        agent("question")
        t = monitor.tasks[-1]
        assert t is not None


# ─────────────────────────────────────────────────────────────────────────────
# Bug R33: 한국어 단위 접미 숫자 추출·보존 검사 버그 회귀 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestKoreanUnitNumberExtraction:
    """R33 Fix: r'\\b\\d{2,}\\b' → r'\\d{2,}' 패턴 수정 회귀 테스트.

    Python의 \\b는 한글을 \\w로 처리하므로 숫자 직후 한글 단위('년','개','명','원' 등)가
    오면 \\b 경계가 성립하지 않아 숫자를 전혀 추출하지 못한다.
    수정 패턴 r'\\d{2,}'는 경계 조건 없이 2자리 이상 숫자를 추출한다.
    """

    def test_context_retention_extracts_year_followed_by_korean_unit(self):
        # "2024년" — \\b\\d{2,}\\b 버그 시 key_entities에 "2024"가 포함되지 않아
        # "2024년에 설립됨" 응답에서 retention_score = 0.0 (false negative)
        # key_entities=[] + context 제공 시 auto-extraction 트리거됨
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=False)
        context = "2024년 서울에서 50개 사용"
        response = "2024년에 서울에서 50개가 사용되었습니다."
        result = eval_context_retention(response, "", context, cfg)
        all_entities = result["entities_retained"] + result["entities_lost"]
        assert "2024" in all_entities, (
            "r'\\b\\d{2,}\\b' 버그: '2024년'에서 '2024'를 추출하지 못함 — "
            "r'\\d{2,}' 수정 후에는 key_entities에 포함되어야 함"
        )
        assert "50" in all_entities, (
            "r'\\b\\d{2,}\\b' 버그: '50개'에서 '50'을 추출하지 못함"
        )

    def test_context_retention_korean_number_retained_in_response(self):
        # auto_extract로 추출한 "2024"가 응답 "2024년에는"에서 보존 확인되어야 함
        # _is_fact_retained_in_text 버그 시 "2024"가 "2024년에는"에서 False 반환 → entities_lost
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(
            key_entities=["2024"],
            check_original_goal=False,
        )
        result = eval_context_retention("2024년에는 서울에서 진행됩니다.", "", "", cfg)
        assert "2024" in result["entities_retained"], (
            "_is_fact_retained_in_text 버그: '2024'가 '2024년에는'에서 찾히지 않음 — "
            "_KOREAN_UNITS 단위 허용 수정 후에는 entities_retained에 있어야 함"
        )

    def test_context_retention_count_and_person_units(self):
        # "50개", "100명" — 개(count)·명(person) 단위도 올바르게 추출·보존되어야 함
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(
            key_entities=["50", "100"],
            check_original_goal=False,
        )
        result = eval_context_retention("50개 제품과 100명이 참여합니다.", "", "", cfg)
        assert "50" in result["entities_retained"], (
            "'50'이 '50개'에서 보존 확인 실패 — _KOREAN_UNITS 미포함 버그 회귀"
        )
        assert "100" in result["entities_retained"], (
            "'100'이 '100명'에서 보존 확인 실패 — _KOREAN_UNITS 미포함 버그 회귀"
        )

    def test_knowledge_retention_extracts_numbers_with_korean_units(self):
        # auto_extract_seed=True: history에서 "2024년"·"1500원" 숫자를 facts로 추출
        from agent_evaluator.decorators import KnowledgeRetentionConfig
        from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention
        cfg = KnowledgeRetentionConfig(
            auto_extract_seed=True,
            seed_turns=1,
            check_from_turn=1,
        )
        history = [{"user": "2024년에 1500원으로 구매했다"}]
        response = "2024년 구매 내역과 1500원 결제가 확인됩니다."
        result = eval_knowledge_retention(response, history, cfg)
        assert result is not None, "숫자 facts가 추출되어야 하므로 None이 아님"
        retained = result.get("retained_facts", [])
        assert any("2024" in f for f in retained), (
            r"\b\d{2,}\b 버그: '2024년'에서 '2024' 미추출 → retained_facts에 없음 — "
            r"\d{2,} 수정 후 포함되어야 함"
        )


class TestIsFactRetainedInTextKoreanUnits:
    """R33 Fix: _is_fact_retained_in_text에서 숫자+한국어단위 조합 처리 버그 회귀 테스트."""

    def test_numeric_fact_before_nyen_is_found(self):
        # "2024"가 "2024년에는" 에서 찾혀야 함 (이전: '년'이 _KOREAN_PARTICLES_1에 없어 False)
        assert _is_fact_retained_in_text("2024", "2024년에는 진행됩니다") is True, (
            "'2024'가 '2024년에는'에서 찾히지 않음 — _KOREAN_UNITS 단위 허용 미적용 버그 회귀"
        )

    def test_numeric_fact_before_gae_is_found(self):
        assert _is_fact_retained_in_text("50", "총 50개의 제품") is True, (
            "'50'이 '50개'에서 찾히지 않음"
        )

    def test_numeric_fact_before_myeong_is_found(self):
        assert _is_fact_retained_in_text("100", "회의에 100명이 참석") is True, (
            "'100'이 '100명'에서 찾히지 않음"
        )

    def test_numeric_fact_before_won_is_found(self):
        assert _is_fact_retained_in_text("1500", "예산은 1500원입니다") is True, (
            "'1500'이 '1500원'에서 찾히지 않음"
        )

    def test_korean_unit_constants_include_common_units(self):
        # 핵심 단위 문자가 _KOREAN_UNITS에 포함되어 있는지 확인
        for unit in ('년', '월', '일', '개', '명', '원', '위', '층'):
            assert unit in _KOREAN_UNITS, f"'{unit}'이 _KOREAN_UNITS에 없음"

    def test_non_numeric_fact_particle_check_unchanged(self):
        # 비숫자 사실은 여전히 조사만 허용 (기존 동작 회귀 방지)
        # "서울이" → '이' in _KOREAN_PARTICLES_1 → True
        assert _is_fact_retained_in_text("서울", "서울이 수도") is True
        # "서울군" → '군' not in _KOREAN_PARTICLES_1 and not numeric → False
        assert _is_fact_retained_in_text("서울", "서울군에 위치") is False, (
            "비숫자 사실 '서울'이 복합어 '서울군'에서 false positive 발생 — 기존 엄격 검사 회귀"
        )

    def test_single_digit_not_extracted_by_auto_pattern(self):
        # r'\\d{2,}' 는 1자리 숫자 미추출 (의도적 동작 유지)
        import re
        matches = re.findall(r'\d{2,}', "3월 1일 제1회 행사")
        assert "3" not in matches, "1자리 숫자 '3'이 추출되면 안 됨"
        assert "1" not in matches, "1자리 숫자 '1'이 추출되면 안 됨"


# ─────────────────────────────────────────────────────────────────────────────
# Bug R34: 영어 고유명사+한국어 조사 추출 버그 / JSON 빈 배열 _from_json 오전파 버그
# ─────────────────────────────────────────────────────────────────────────────

class TestEnglishProperNounKoreanParticleExtraction:
    """R34 Fix: r'\\b[A-Z][a-z]+\\b' → r'\\b[A-Z][a-z]+' 패턴 수정 회귀 테스트.

    Python의 \\b는 한글을 \\w로 처리하므로 영어 대문자 단어('Seoul', 'Claude' 등) 직후
    한국어 조사('에서', '이', '를' 등)가 오면 끝 \\b 경계가 성립하지 않아 고유명사를 추출하지 못한다.
    eval_context_retention의 auto-extract와 eval_knowledge_retention의 auto_extract_seed
    양쪽에서 발생하는 동일 버그.
    """

    def test_context_retention_extracts_proper_noun_before_korean_particle(self):
        # "Seoul에서" — \\b[A-Z][a-z]+\\b 버그 시 key_entities에 "Seoul"이 포함되지 않음
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=False)
        context = "Seoul에서 Claude를 사용한 결과"
        response = "Seoul에서 Claude를 활용했습니다."
        result = eval_context_retention(response, "", context, cfg)
        all_entities = result["entities_retained"] + result["entities_lost"]
        assert "Seoul" in all_entities, (
            r"\b[A-Z][a-z]+\b 버그: 'Seoul에서'에서 'Seoul'을 추출하지 못함 — "
            r"\b[A-Z][a-z]+ 수정 후 key_entities에 포함되어야 함"
        )
        assert "Claude" in all_entities, (
            r"\b[A-Z][a-z]+\b 버그: 'Claude를'에서 'Claude'를 추출하지 못함"
        )

    def test_context_retention_proper_noun_retained_with_korean_particle(self):
        # 추출된 "Seoul"이 응답 "Seoul이 중요합니다"에서 보존 확인되어야 함
        # _is_fact_retained_in_text: "이" in _KOREAN_PARTICLES_1 → True (기존 동작 유지)
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(
            key_entities=["Seoul"],
            check_original_goal=False,
        )
        result = eval_context_retention("Seoul이 중요합니다", "", "", cfg)
        assert "Seoul" in result["entities_retained"], (
            "'Seoul'이 'Seoul이 중요합니다'에서 보존으로 인식되지 않음 — "
            "'이' in _KOREAN_PARTICLES_1 경로 회귀"
        )

    def test_context_retention_multiple_proper_nouns_korean_mixed(self):
        # "Google이 발표한 Gemini와 Anthropic의 Claude" 에서 고유명사 4개 모두 추출
        from agent_evaluator.decorators import ContextRetentionConfig
        cfg = ContextRetentionConfig(check_original_goal=False)
        context = "Google이 발표한 Gemini와 Anthropic의 Claude"
        result = eval_context_retention("Google, Gemini, Anthropic, Claude 모두 확인", "", context, cfg)
        all_entities = result["entities_retained"] + result["entities_lost"]
        for name in ("Google", "Gemini", "Anthropic", "Claude"):
            assert name in all_entities, (
                f"r'\\b[A-Z][a-z]+\\b' 버그: '{name}이/와/의'에서 '{name}'을 추출하지 못함"
            )

    def test_knowledge_retention_extracts_proper_noun_with_korean_particle(self):
        # auto_extract_seed=True: history에서 "Seoul에서" 고유명사 추출
        from agent_evaluator.decorators import KnowledgeRetentionConfig
        from agent_evaluator.helpers.taskresult_helpers import eval_knowledge_retention
        cfg = KnowledgeRetentionConfig(
            auto_extract_seed=True,
            seed_turns=1,
            check_from_turn=1,
        )
        history = [{"user": "Seoul에서 Claude를 사용해 2024년 보고서를 작성했다"}]
        response = "Seoul과 Claude를 활용한 분석 결과입니다."
        result = eval_knowledge_retention(response, history, cfg)
        assert result is not None, "고유명사 facts가 추출되어야 하므로 None이 아님"
        retained = result.get("retained_facts", [])
        assert any("Seoul" in f for f in retained), (
            r"\b[A-Z][a-z]+\b 버그: 'Seoul에서'에서 'Seoul' 미추출 → retained_facts에 없음"
        )

    def test_old_pattern_versus_new_pattern_difference(self):
        # r'\\b[A-Z][a-z]+\\b' vs r'\\b[A-Z][a-z]+' 차이 명시적 검증
        import re
        text = "Seoul에서 Google이 Samsung을 인수"
        old = re.findall(r'\b[A-Z][a-z]+\b', text)
        new = re.findall(r'\b[A-Z][a-z]+', text)
        assert "Seoul" not in old, "구 패턴: 'Seoul에서'에서 'Seoul' 추출됨 → 버그 회귀"
        assert "Seoul" in new, "신 패턴: 'Seoul에서'에서 'Seoul' 추출 실패"
        assert "Google" not in old, "구 패턴: 'Google이'에서 'Google' 추출됨 → 버그 회귀"
        assert "Google" in new, "신 패턴: 'Google이'에서 'Google' 추출 실패"


class TestPlanCoherenceJsonEmptyArrayFallback:
    """R34 Fix: JSON 빈 배열 fallback 시 _from_json 오전파 버그 회귀 테스트.

    {"steps": []} JSON 응답에서 _from_json=True가 설정된 후 bullet-point 폴백 경로로
    진행될 때 _from_json이 리셋되지 않아 bullet-point 단계가 JSON 배열처럼 ordering_score=1.0을
    받는 버그. bullet-point 단계는 sequential marker 검사를 받아야 한다.
    """

    def test_json_empty_steps_with_bullet_response_uses_marker_check(self):
        # {"steps": []} JSON + 응답 본문에 bullet(-) 단계 → _from_json 리셋 후 marker 검사
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        # JSON은 빈 steps, 응답 본문에 bullet-point 단계 (sequential marker 없음)
        response = '{"steps": []}\n- do this\n- do that\n- finish'
        result = eval_plan_coherence(response, "do task", cfg)
        # bullet-point 단계 3개가 추출되어야 함 (not None)
        assert result is not None, "bullet-point 단계가 추출되어 result가 있어야 함"
        assert result["step_count"] == 3
        # _from_json이 False로 리셋됐으므로 sequential marker 검사가 적용되어야 함
        # marker 없는 bullet-point → ordering_score < 1.0 (is_numbered=False, step_count>1)
        ordering = result.get("ordering_score")
        if ordering is not None:
            assert ordering < 1.0, (
                f"JSON 빈 배열 fallback 시 _from_json=True 오전파 버그 회귀: "
                f"bullet-point 단계가 ordering_score=1.0을 받음 (마커 없음인데 {ordering})"
            )

    def test_json_valid_steps_still_gets_from_json_true(self):
        # 정상 JSON steps → _from_json=True → ordering_score=1.0 (회귀 방지)
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        import json
        response = json.dumps({"steps": ["First step", "Second step", "Third step"]})
        result = eval_plan_coherence(response, "", cfg)
        assert result is not None
        assert result["ordering_score"] == 1.0, (
            "정상 JSON steps의 ordering_score가 1.0이어야 함 — _from_json=True 회귀"
        )

    def test_json_bare_list_still_gets_from_json_true(self):
        # JSON 베어 리스트 → _from_json=True → ordering_score=1.0 (회귀 방지)
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )
        import json
        response = json.dumps(["Step A", "Step B", "Step C"])
        result = eval_plan_coherence(response, "", cfg)
        assert result is not None
        assert result["ordering_score"] == 1.0, (
            "JSON 베어 리스트의 ordering_score가 1.0이어야 함 — _from_json=True 회귀"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: @agent_eval dict-response 버그 회귀 테스트 (R35)
# Bug: eval_instruction_adherence / eval_plan_coherence 가 str(raw_result) 를 사용해
# LangChain dict 반환({"output": "...", "answer": "..."}) 시 Python repr 을 평가하던 문제.
# Fix: task_result.response (프레임워크 추출 완료된 문자열) 를 사용하도록 수정.
# ─────────────────────────────────────────────────────────────────────────────

class TestInstructionAdherenceDictReturnValue:
    """dict 반환값을 가진 에이전트에서 InstructionConfig 평가 회귀 테스트."""

    def test_instruction_keywords_found_in_dict_answer(self, monitor):
        # LangChain 스타일 {"answer": "..."} 반환 시 실제 answer 문자열에서 키워드 검사해야 함.
        # Bug 전: str({"answer": "Seoul is the capital"}) → "{'answer': 'Seoul is the capital'}"
        #  → required_keyword "Seoul" 이 발견되긴 하지만, "answer" 등 노이즈 포함 문자열 평가
        # Bug 케이스: required_keyword 가 dict repr 에만 존재하는 경우 false positive 발생
        cfg = InstructionConfig(required_keywords=["capital"])

        @agent_eval(monitor, task_type="qa", instructions=cfg)
        def agent(question, ground_truth=""):
            return {"answer": "Seoul is the capital of Korea"}

        agent("What is the capital of Korea?", ground_truth="Seoul")
        t = monitor.tasks[-1]
        assert "instruction_adherence" in (t.extra or {}), "instruction_adherence 결과 없음"
        result = t.extra["instruction_adherence"]
        assert result["score"] == 1.0, (
            f"dict 반환값의 answer 에서 키워드 'capital' 을 찾아야 함, score={result['score']}"
        )
        assert result["violation_count"] == 0

    def test_instruction_format_json_from_dict_answer(self, monitor):
        # {"answer": '{"result": "ok"}'} 반환 시 answer 값(JSON 문자열)으로 format 검사해야 함.
        cfg = InstructionConfig(expected_format="json")

        @agent_eval(monitor, task_type="qa", instructions=cfg)
        def agent(question, ground_truth=""):
            return {"answer": '{"result": "ok"}'}

        agent("Return JSON", ground_truth="")
        t = monitor.tasks[-1]
        result = (t.extra or {}).get("instruction_adherence", {})
        assert result.get("checks", {}).get("format") is True, (
            "answer 값이 JSON 형식인데 format 검사 실패 — task_result.response 미사용 의심"
        )

    def test_instruction_keyword_missing_in_answer_key(self, monitor):
        # answer 값에 키워드 없음 → violation 발생해야 함
        cfg = InstructionConfig(required_keywords=["conclusion"])

        @agent_eval(monitor, task_type="qa", instructions=cfg)
        def agent(question, ground_truth=""):
            return {"answer": "The result is positive"}

        agent("Summarize", ground_truth="")
        t = monitor.tasks[-1]
        result = (t.extra or {}).get("instruction_adherence", {})
        assert result.get("violation_count", 0) >= 1, (
            "answer 값에 'conclusion' 없으므로 violation 이 있어야 함"
        )


class TestPlanCoherenceDictReturnValue:
    """dict 반환값을 가진 에이전트에서 PlanConfig 평가 회귀 테스트."""

    def test_plan_extracted_from_dict_output_json_steps(self, monitor):
        # LangChain 스타일 {"output": '{"steps": ["A", "B", "C"]}'} 반환 시
        # output 값(JSON 문자열)에서 steps 를 파싱해야 함.
        # Bug 전: str({"output": '...'}) → Python repr → JSON 파싱 실패 → plan=None
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )

        @agent_eval(monitor, task_type="planning", plan_tracking=cfg)
        def agent(question, ground_truth=""):
            return {"output": json.dumps({"steps": ["Step A", "Step B", "Step C"]})}

        agent("Plan something", ground_truth="")
        t = monitor.tasks[-1]
        plan = (t.extra or {}).get("plan_coherence")
        assert plan is not None, (
            "dict output 값에서 JSON steps 를 파싱해야 하는데 plan_coherence=None "
            "— task_result.response 미사용 의심 (str(raw_result) 는 Python repr)"
        )
        assert plan.get("step_count", 0) == 3, f"3개 단계가 파싱되어야 함, got {plan.get('step_count')}"
        assert plan.get("ordering_score") == 1.0, "JSON 파싱 성공 시 ordering_score=1.0 이어야 함"

    def test_plan_extracted_from_answer_key_numbered_list(self, monitor):
        # {"answer": "1. fetch\n2. process\n3. save"} 반환 시
        # answer 값에서 번호 목록으로 steps 를 추출해야 함.
        cfg = PlanConfig(
            check_step_ordering=True,
            check_goal_coverage=False,
            check_executability=False,
        )

        @agent_eval(monitor, task_type="planning", plan_tracking=cfg)
        def agent(question, ground_truth=""):
            return {"answer": "1. fetch data\n2. process data\n3. save results"}

        agent("Plan the data pipeline", ground_truth="")
        t = monitor.tasks[-1]
        plan = (t.extra or {}).get("plan_coherence")
        assert plan is not None, (
            "dict answer 값의 번호 목록에서 steps 를 추출해야 하는데 plan_coherence=None"
        )
        assert plan.get("step_count", 0) == 3, f"3개 단계가 파싱되어야 함, got {plan.get('step_count')}"
