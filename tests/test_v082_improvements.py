"""
Tests for v0.8.2 improvements:
- E1: enable_llm_judge / judge_model / enable_anomaly_detection in agent_eval
- E2: rag_mode shortcut in agent_eval
- E3: security_mode / allowed_tools in agent_eval
- E5: Updated AGENT_EVAL_PRESETS (production/development)
- E6: AlertRuleBuilder factory class
- F1: LangGraph token extraction (usage_metadata / response_metadata)
- F2: AutoGen per-turn execution_time from timestamps
- F3: DSPy tool_calls extraction
- F4: vLLM / HuggingFace adapters + *_eval decorators
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# E5: AGENT_EVAL_PRESETS
# ─────────────────────────────────────────────────────────────────────────────
class TestAgentEvalPresetsE5:
    def test_production_preset_has_anomaly_detection(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        prod = AGENT_EVAL_PRESETS["production"]
        assert prod.get("enable_anomaly_detection") is True

    def test_production_preset_flush_every_50(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        prod = AGENT_EVAL_PRESETS["production"]
        assert prod.get("flush_every") == 50

    def test_development_preset_has_llm_judge(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        dev = AGENT_EVAL_PRESETS["development"]
        assert dev.get("enable_llm_judge") is True

    def test_development_preset_has_auto_detect_framework(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        dev = AGENT_EVAL_PRESETS["development"]
        assert dev.get("auto_detect_framework") is True

    def test_testing_preset_values(self):
        from agent_evaluator import AGENT_EVAL_PRESETS
        testing = AGENT_EVAL_PRESETS["testing"]
        # P2-A: testing preset updated — sample_rate=0.1 for load reduction, flush_every=5 for tracking
        assert testing.get("sample_rate") == 0.1
        assert testing.get("timeout") == 60.0
        assert testing.get("flush_every") == 5


# ─────────────────────────────────────────────────────────────────────────────
# E6: AlertRuleBuilder
# ─────────────────────────────────────────────────────────────────────────────
class TestAlertRuleBuilderE6:
    def test_when_accuracy_below_creates_rule(self):
        from agent_evaluator import AlertRuleBuilder, SimpleTaskAlertRule
        rule = AlertRuleBuilder.when_accuracy_below(0.7)
        assert isinstance(rule, SimpleTaskAlertRule)
        assert "accuracy_below" in rule.name

    def test_when_accuracy_below_fires_correctly(self):
        from agent_evaluator import AlertRuleBuilder
        fired = []
        rule = AlertRuleBuilder.when_accuracy_below(
            0.7, handler=lambda msg, tr: fired.append(msg)
        )
        tr = MagicMock()
        tr.accuracy_score = 0.5
        tr.task_id = "t1"
        tr.execution_time = 1.0
        rule.evaluate(tr)
        assert len(fired) == 1

    def test_when_accuracy_below_no_fire_above_threshold(self):
        from agent_evaluator import AlertRuleBuilder
        fired = []
        rule = AlertRuleBuilder.when_accuracy_below(
            0.7, handler=lambda msg, tr: fired.append(msg)
        )
        tr = MagicMock()
        tr.accuracy_score = 0.9
        tr.task_id = "t1"
        tr.execution_time = 1.0
        rule.evaluate(tr)
        assert len(fired) == 0

    def test_when_latency_above_creates_rule(self):
        from agent_evaluator import AlertRuleBuilder
        rule = AlertRuleBuilder.when_latency_above(5.0)
        assert "latency_above" in rule.name

    def test_when_latency_above_fires(self):
        from agent_evaluator import AlertRuleBuilder
        fired = []
        rule = AlertRuleBuilder.when_latency_above(
            2.0, handler=lambda msg, tr: fired.append(tr)
        )
        tr = MagicMock()
        tr.execution_time = 3.5
        tr.accuracy_score = 0.9
        tr.task_id = "t1"
        tr.errors = []
        rule.evaluate(tr)
        assert len(fired) == 1

    def test_when_completion_below_creates_rule(self):
        from agent_evaluator import AlertRuleBuilder
        rule = AlertRuleBuilder.when_completion_below(0.8)
        assert "completion_below" in rule.name

    def test_when_error_creates_rule(self):
        from agent_evaluator import AlertRuleBuilder
        rule = AlertRuleBuilder.when_error()
        assert rule.name == "task_error"
        assert rule.severity == "error"

    def test_when_error_fires_on_nonempty_errors(self):
        from agent_evaluator import AlertRuleBuilder
        fired = []
        rule = AlertRuleBuilder.when_error(handler=lambda msg, tr: fired.append(msg))
        tr = MagicMock()
        tr.errors = ["some error"]
        tr.task_id = "t1"
        tr.accuracy_score = 0.0
        tr.execution_time = 1.0
        rule.evaluate(tr)
        assert len(fired) == 1

    def test_when_tool_calls_exceed_creates_rule(self):
        from agent_evaluator import AlertRuleBuilder
        rule = AlertRuleBuilder.when_tool_calls_exceed(5)
        assert "tool_calls_exceed_5" in rule.name

    def test_when_tool_calls_exceed_fires(self):
        from agent_evaluator import AlertRuleBuilder
        fired = []
        rule = AlertRuleBuilder.when_tool_calls_exceed(
            2, handler=lambda msg, tr: fired.append(msg)
        )
        tr = MagicMock()
        tr.tool_calls = [1, 2, 3]
        tr.task_id = "t1"
        tr.accuracy_score = 0.9
        tr.execution_time = 1.0
        rule.evaluate(tr)
        assert len(fired) == 1

    def test_custom_name_preserved(self):
        from agent_evaluator import AlertRuleBuilder
        rule = AlertRuleBuilder.when_accuracy_below(0.5, name="my_custom_rule")
        assert rule.name == "my_custom_rule"


# ─────────────────────────────────────────────────────────────────────────────
# E2: rag_mode
# ─────────────────────────────────────────────────────────────────────────────
class TestRagModeE2:
    def test_rag_mode_sets_context_arg(self):
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e2/")

        @agent_eval(monitor, task_type="qa", rag_mode=True)
        def rag_fn(question, context="", ground_truth=""):
            return "answer"

        # Should not raise — context_arg auto-set to "context"
        rag_fn("Q?", context="Some context", ground_truth="answer")
        assert monitor.task_count >= 1

    def test_rag_mode_changes_task_type_to_information_retrieval(self):
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e2/")

        @agent_eval(monitor, task_type="qa", rag_mode=True)
        def rag_fn(question, context="", ground_truth=""):
            return "answer"

        rag_fn("What is RAG?", context="RAG is...", ground_truth="RAG")
        tasks = monitor.tasks
        assert len(tasks) >= 1
        assert tasks[-1].task_type == "information_retrieval"

    def test_rag_mode_with_explicit_task_type_other_than_qa(self):
        """rag_mode=True + task_type != 'qa' → task_type should NOT be overridden."""
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e2/")

        @agent_eval(monitor, task_type="tool_use", rag_mode=True)
        def rag_fn(question, context="", ground_truth=""):
            return "answer"

        rag_fn("Q?", context="ctx", ground_truth="ans")
        tasks = monitor.tasks
        assert tasks[-1].task_type == "tool_use"


# ─────────────────────────────────────────────────────────────────────────────
# E3: security_mode
# ─────────────────────────────────────────────────────────────────────────────
class TestSecurityModeE3:
    def test_security_mode_restores_flag_after_call(self):
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e3/", enable_security_metrics=False)

        @agent_eval(monitor, task_type="tool_use", security_mode=True)
        def secure_fn(question, ground_truth=""):
            # Capture state during execution (via monitor's flag)
            return "done"

        secure_fn("do secure thing", ground_truth="done")
        # After call, flag should be restored
        assert monitor.enable_security_metrics is False

    def test_security_mode_does_not_affect_already_enabled_monitor(self):
        """If monitor already has security_metrics enabled, it should stay enabled."""
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e3/", enable_security_metrics=True)

        @agent_eval(monitor, task_type="tool_use", security_mode=True)
        def secure_fn(question, ground_truth=""):
            return "done"

        secure_fn("q", ground_truth="done")
        assert monitor.enable_security_metrics is True

    def test_security_mode_in_agent_eval_signature(self):
        import inspect
        from agent_evaluator import agent_eval
        sig = inspect.signature(agent_eval)
        assert "security_mode" in sig.parameters
        assert "allowed_tools" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# E1: enable_llm_judge / judge_model / enable_anomaly_detection
# ─────────────────────────────────────────────────────────────────────────────
class TestEnableLlmJudgeE1:
    def test_enable_llm_judge_in_agent_eval_signature(self):
        import inspect
        from agent_evaluator import agent_eval
        sig = inspect.signature(agent_eval)
        assert "enable_llm_judge" in sig.parameters
        assert "judge_model" in sig.parameters
        assert "enable_anomaly_detection" in sig.parameters

    def test_enable_llm_judge_restores_after_call(self):
        from agent_evaluator import agent_eval, PerformanceMonitor
        monitor = PerformanceMonitor(output_dir="/tmp/test_e1/", enable_llm_judge=False)

        @agent_eval(monitor, task_type="qa", enable_llm_judge=True)
        def fn(question, ground_truth=""):
            return "answer"

        fn("Q?", ground_truth="A")
        assert monitor.enable_llm_judge is False

    def test_enable_anomaly_detection_in_common_params(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "enable_anomaly_detection" in EvalDecorator._COMMON_PARAMS

    def test_rag_mode_in_common_params(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "rag_mode" in EvalDecorator._COMMON_PARAMS

    def test_security_mode_in_common_params(self):
        from agent_evaluator.decorators import EvalDecorator
        assert "security_mode" in EvalDecorator._COMMON_PARAMS


# ─────────────────────────────────────────────────────────────────────────────
# F1: LangGraph token extraction
# ─────────────────────────────────────────────────────────────────────────────
class TestLangGraphTokenExtractionF1:
    def test_usage_metadata_tokens_extracted(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata

        class FakeAIMessage:
            content = "Hello"
            usage_metadata = {"input_tokens": 10, "output_tokens": 20}
            tool_calls = None
            response_metadata = {}

        raw = {"messages": [FakeAIMessage()]}
        meta = _extract_langgraph_metadata(raw)
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["input"] == 10
        assert meta.tokens_used["output"] == 20
        assert meta.tokens_used["total"] == 30

    def test_response_metadata_token_usage_extracted(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata

        class FakeMsg:
            content = "Hi"
            usage_metadata = None
            response_metadata = {"token_usage": {"prompt_tokens": 5, "completion_tokens": 8}}
            tool_calls = None

        raw = {"messages": [FakeMsg()]}
        meta = _extract_langgraph_metadata(raw)
        assert meta is not None
        assert meta.tokens_used is not None
        assert meta.tokens_used["input"] == 5
        assert meta.tokens_used["output"] == 8

    def test_no_tokens_returns_none_tokens_used(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata

        class FakeMsg:
            content = "Hi"
            usage_metadata = None
            response_metadata = {}
            tool_calls = None

        raw = {"messages": [FakeMsg()]}
        meta = _extract_langgraph_metadata(raw)
        assert meta is not None
        assert meta.tokens_used is None

    def test_multiple_messages_tokens_accumulated(self):
        from agent_evaluator.decorators import _extract_langgraph_metadata

        class FakeMsg:
            def __init__(self, inp, out):
                self.content = "text"
                self.usage_metadata = {"input_tokens": inp, "output_tokens": out}
                self.tool_calls = None
                self.response_metadata = {}

        raw = {"messages": [FakeMsg(5, 10), FakeMsg(3, 7)]}
        meta = _extract_langgraph_metadata(raw)
        assert meta.tokens_used["input"] == 8
        assert meta.tokens_used["output"] == 17


# ─────────────────────────────────────────────────────────────────────────────
# F2: AutoGen per-turn execution_time
# ─────────────────────────────────────────────────────────────────────────────
class TestAutogenPerTurnTimingF2:
    def test_timestamp_as_float_produces_turn_time(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        _msgs = [
            {"role": "user", "content": "Hello", "timestamp": 1000.0},
            {"role": "assistant", "content": "Hi there", "timestamp": 1002.5},
        ]

        class FakeResult:
            # _extract_autogen_metadata checks raw.messages first
            messages = _msgs
            cost = None
            usage_summary = None

        meta = _extract_autogen_metadata(FakeResult())
        assert meta is not None
        # First turn has no previous, execution_time should be 0
        assert meta.conversation_turns[0]["execution_time"] == 0.0
        # Second turn should have elapsed time
        assert meta.conversation_turns[1]["execution_time"] == pytest.approx(2.5, abs=0.01)

    def test_no_timestamp_produces_zero_turn_time(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        class FakeResult:
            messages = [
                {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "A"},
            ]
            cost = None
            usage_summary = None

        meta = _extract_autogen_metadata(FakeResult())
        assert meta is not None
        for turn in meta.conversation_turns:
            assert turn["execution_time"] == 0.0

    def test_execution_time_key_present_in_turns(self):
        from agent_evaluator.decorators import _extract_autogen_metadata

        class FakeResult:
            messages = [{"role": "user", "content": "Hi"}]
            cost = None
            usage_summary = None

        meta = _extract_autogen_metadata(FakeResult())
        assert meta is not None
        assert "execution_time" in meta.conversation_turns[0]


# ─────────────────────────────────────────────────────────────────────────────
# F3: DSPy tool_calls extraction
# ─────────────────────────────────────────────────────────────────────────────
class TestDspyToolCallsF3:
    def test_tool_calls_attr_extracted(self):
        from agent_evaluator.decorators import _extract_dspy_metadata

        class FakePrediction:
            _completions = None
            answer = "42"
            tool_calls = [{"name": "calculator", "args": {"x": 1}, "error": None}]

        meta = _extract_dspy_metadata(FakePrediction())
        assert meta is not None
        assert meta.tool_calls is not None
        assert len(meta.tool_calls) == 1
        assert meta.tool_calls[0]["tool_name"] == "calculator"

    def test_actions_attr_extracted(self):
        from agent_evaluator.decorators import _extract_dspy_metadata

        class FakeAction:
            name = "search"
            args = {"query": "test"}

        class FakePrediction:
            _completions = None
            answer = "result"
            tool_calls = None
            actions = [FakeAction()]

        meta = _extract_dspy_metadata(FakePrediction())
        assert meta is not None
        assert meta.tool_calls is not None
        assert meta.tool_calls[0]["tool_name"] == "search"

    def test_no_tool_calls_does_not_error(self):
        from agent_evaluator.decorators import _extract_dspy_metadata

        class FakePrediction:
            _completions = ["completion text"]
            answer = "42"
            tool_calls = None
            actions = None

        meta = _extract_dspy_metadata(FakePrediction())
        assert meta is not None
        assert meta.tool_calls is None


# ─────────────────────────────────────────────────────────────────────────────
# F4: vLLM / HuggingFace adapters
# ─────────────────────────────────────────────────────────────────────────────
class TestVllmAdapterF4:
    def test_vllm_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "vllm" in _FRAMEWORK_ADAPTERS

    def test_vllm_openai_compatible_response_extracted(self):
        from agent_evaluator.decorators import _extract_vllm_metadata

        class FakeFunction:
            name = "search"
            arguments = '{"q": "test"}'

        class FakeToolCall:
            function = FakeFunction()

        class FakeMessage:
            tool_calls = [FakeToolCall()]

        class FakeChoice:
            message = FakeMessage()

        class FakeUsage:
            prompt_tokens = 10
            completion_tokens = 20
            total_tokens = 30

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        meta = _extract_vllm_metadata(FakeResponse())
        assert meta is not None
        assert meta.framework == "vllm"
        assert meta.tool_calls is not None
        assert meta.tool_calls[0]["tool_name"] == "search"
        assert meta.tokens_used["total"] == 30

    def test_vllm_no_data_returns_none(self):
        from agent_evaluator.decorators import _extract_vllm_metadata
        assert _extract_vllm_metadata("plain string") is None
        assert _extract_vllm_metadata(42) is None

    def test_vllm_registered_in_framework_adapters(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "vllm" in _FRAMEWORK_ADAPTERS


class TestHuggingFaceAdapterF4:
    def test_huggingface_adapter_registered(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "huggingface" in _FRAMEWORK_ADAPTERS

    def test_huggingface_pipeline_response_extracted(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata

        raw = [{"generated_text": "The answer is 42"}]
        meta = _extract_huggingface_metadata(raw)
        assert meta is not None
        assert meta.framework == "huggingface"
        assert meta.chain_steps is not None
        assert meta.chain_steps[0]["name"] == "generation"

    def test_huggingface_empty_list_returns_none(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata
        assert _extract_huggingface_metadata([]) is None

    def test_huggingface_registered_in_framework_adapters(self):
        from agent_evaluator.decorators import _FRAMEWORK_ADAPTERS
        assert "huggingface" in _FRAMEWORK_ADAPTERS

    def test_huggingface_agent_with_tool_calls(self):
        from agent_evaluator.decorators import _extract_huggingface_metadata

        class FakeToolCall:
            name = "web_search"
            arguments = {"query": "AI"}

        class FakeAgent:
            tool_calls = [FakeToolCall()]
            logs = None

        meta = _extract_huggingface_metadata(FakeAgent())
        assert meta is not None
        assert meta.tool_calls is not None
        assert meta.tool_calls[0]["tool_name"] == "web_search"
