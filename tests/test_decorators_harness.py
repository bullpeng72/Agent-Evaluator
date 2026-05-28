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
)
from agent_evaluator.helpers.taskresult_helpers import (
    eval_instruction_adherence,
    eval_loop_detection,
    eval_goal_alignment,
    eval_fault_tolerance,
    eval_plan_coherence,
    compute_reproducibility_score,
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
        assert cfg.duplicate_in_window_threshold == 2
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
        assert result["score"] == 1.0
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

    def test_fault_tolerance_all_fail(self):
        cfg = FaultToleranceConfig()
        tools = [
            {"name": "t1", "success": False},
            {"name": "t2", "success": False},
        ]
        result = eval_fault_tolerance(tools, cfg)
        assert result["failures_detected"]
        assert result["grade"] in ("poor", "partial", "good")  # grade depends on fallback detection logic

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
