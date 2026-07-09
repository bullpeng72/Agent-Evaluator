"""
tests/test_spec039_decorator_architecture.py
================================================
SPEC-039: 데코레이터 아키텍처 결함 수정 + LiveGuardrail 비침습 데코레이터.

REQ-1: preset/explicit 파라미터 sentinel 충돌 수정.
REQ-2: async ReproducibilityConfig 지원.
REQ-3: generator wrapper retry 조합 경고.
"""
import asyncio
import warnings

import pytest

from agent_evaluator import (
    PerformanceMonitor,
    ReproducibilityConfig,
    RetryConfig,
    agent_eval,
    batch_eval,
    conversation_eval,
)
from agent_evaluator.decorators import flush_conversation


class TestReq1PresetSentinelAgentEval:
    """agent_eval: preset과 명시적 파라미터 충돌 시 명시값이 항상 이겨야 한다."""

    def test_explicit_sample_rate_wins_over_preset(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @agent_eval(monitor, task_type="qa", preset="production", sample_rate=1.0)
        def agent(question, ground_truth=""):
            return "answer"

        for i in range(20):
            agent(f"q{i}", ground_truth="a")

        report = monitor.generate_report().to_dict()
        assert report.get("total_tasks") == 20  # production preset(0.1) 무시하고 전수 기록

    def test_unset_sample_rate_applies_preset(self, tmp_path, monkeypatch):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        # random.random()이 항상 1.0(> 어떤 sample_rate보다 큼)을 반환하게 고정 —
        # sample_rate=0.1이 실제로 적용되면 모든 호출이 스킵돼야 한다.
        monkeypatch.setattr("agent_evaluator.decorators.random.random", lambda: 0.99)

        @agent_eval(monitor, task_type="qa", preset="production")
        def agent(question, ground_truth=""):
            return "answer"

        for i in range(10):
            agent(f"q{i}", ground_truth="a")

        report = monitor.generate_report().to_dict()
        # preset의 sample_rate=0.1이 실제로 게이트에 반영됐다면 random()=0.99 > 0.1이므로
        # 전부 스킵되어 기록이 0건이어야 한다(수정 전에는 _effective_sample_rate가 죽은
        # 변수라 sample_rate=1.0 그대로 게이트를 적용해 10건 전부 기록됐다).
        assert (report.get("total_tasks") or 0) == 0

    def test_explicit_enabled_true_wins_over_preset_disabling(self, tmp_path):
        from agent_evaluator.decorators import register_preset

        register_preset("_spec039_disabled", {"enabled": False})
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @agent_eval(monitor, task_type="qa", preset="_spec039_disabled", enabled=True)
        def agent(question, ground_truth=""):
            return "answer"

        agent("q1", ground_truth="a")
        report = monitor.generate_report().to_dict()
        assert report.get("total_tasks") == 1

    def test_unset_enabled_applies_preset_disabling(self, tmp_path):
        from agent_evaluator.decorators import register_preset

        register_preset("_spec039_disabled2", {"enabled": False})
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        calls = []

        @agent_eval(monitor, task_type="qa", preset="_spec039_disabled2")
        def agent(question, ground_truth=""):
            calls.append(question)
            return "answer"

        agent("q1", ground_truth="a")
        # enabled=False(preset)면 decorator()가 원본 함수를 그대로 반환하므로 함수 자체는
        # 여전히 호출된다 — 다만 평가 기록이 전혀 남지 않아야 한다.
        assert calls == ["q1"]
        report = monitor.generate_report().to_dict()
        assert (report.get("total_tasks") or 0) == 0

    def test_no_preset_default_behavior_unaffected(self, tmp_path):
        """preset 없이 쓰는 기존 동작은 완전히 그대로여야 한다 (회귀 없음)."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @agent_eval(monitor, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        for i in range(5):
            agent(f"q{i}", ground_truth="a")
        report = monitor.generate_report().to_dict()
        assert report.get("total_tasks") == 5


class TestReq1PresetSentinelBatchEval:
    def test_explicit_sample_rate_wins_over_preset(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @batch_eval(monitor, task_type="qa", preset="production", sample_rate=1.0)
        def agent(questions, ground_truths=None):
            return ["answer"] * len(questions)

        questions = [f"q{i}" for i in range(15)]
        ground_truths = ["a"] * 15
        agent(questions=questions, ground_truths=ground_truths)

        report = monitor.generate_report().to_dict()
        assert report.get("total_tasks") == 15


class TestReq1PresetSentinelConversationEval:
    def test_explicit_enabled_true_wins_over_preset_disabling(self, tmp_path):
        """conversation_eval은 TaskResult가 아니라 ConversationSession에 기록하므로
        (§REQ-5 조사에서 확인) `monitor.conversation_sessions`로 확인한다."""
        from agent_evaluator.decorators import flush_conversation, register_preset

        register_preset("_spec039_conv_disabled", {"enabled": False})
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @conversation_eval(monitor, preset="_spec039_conv_disabled", enabled=True)
        def chat(question, session_id="s1"):
            return "reply"

        chat("hello", session_id="spec039-conv-1")
        flush_conversation("spec039-conv-1")
        sessions = getattr(monitor, "conversation_sessions", [])
        assert any(s.session_id == "spec039-conv-1" for s in sessions)

    def test_unset_enabled_applies_preset_disabling(self, tmp_path):
        from agent_evaluator.decorators import flush_conversation, register_preset

        register_preset("_spec039_conv_disabled2", {"enabled": False})
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        @conversation_eval(monitor, preset="_spec039_conv_disabled2")
        def chat(question, session_id="s1"):
            return "reply"

        chat("hello", session_id="spec039-conv-2")
        flush_conversation("spec039-conv-2")  # disabled 세션이면 no-op이어야 함
        sessions = getattr(monitor, "conversation_sessions", [])
        assert not any(s.session_id == "spec039-conv-2" for s in sessions)


class TestReq1UnknownPresetWarningUnaffected:
    """알 수 없는 preset 경고 동작은 이번 수정과 무관하게 그대로 유지돼야 한다."""

    def test_agent_eval_unknown_preset_warns(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        with pytest.warns(UserWarning, match="알 수 없는 preset"):
            @agent_eval(monitor, task_type="qa", preset="_does_not_exist")
            def agent(question, ground_truth=""):
                return "answer"


class TestReq2AsyncReproducibility:
    """async 에이전트 함수에서 ReproducibilityConfig가 sync와 동등하게 동작해야 한다."""

    def _details(self, monitor):
        report = monitor.generate_report().to_dict()
        return (report.get("extra_metrics") or {}).get("harness_groups", {}).get("C", {}).get("details", {})

    def test_async_reproducibility_populates_score(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        call_count = {"n": 0}

        @agent_eval(monitor, task_type="qa", reproducibility=ReproducibilityConfig(runs=3))
        async def agent(question, ground_truth=""):
            call_count["n"] += 1
            return "same answer every time"

        asyncio.run(agent("q1", ground_truth="a"))

        details = self._details(monitor)
        assert details.get("avg_reproducibility") is not None
        assert details.get("avg_reproducibility") == 1.0  # 결정론적 응답 → 완전 재현
        # runs=3 → 최초 1회 + 추가 2회 = 총 3회 실제 호출됐어야 한다
        assert call_count["n"] == 3

    def test_async_reproducibility_skip_side_effects(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        call_count = {"n": 0}

        @agent_eval(
            monitor, task_type="qa",
            reproducibility=ReproducibilityConfig(runs=5, skip_side_effects=True),
        )
        async def agent(question, ground_truth=""):
            call_count["n"] += 1
            return "answer"

        asyncio.run(agent("q1", ground_truth="a"))

        # skip_side_effects=True면 추가 실행을 건너뛰므로 정확히 1회만 호출된다
        assert call_count["n"] == 1
        # run_count=1인 태스크는 Gate C 집계에서 의도적으로 제외된다(실제 재현성 측정이
        # 이루어지지 않았기 때문 — gate_c_reliability/aggregate.py:190-199 참고). 대신
        # 태스크 자체에 reproducibility 결과가 기록됐는지(=async 경로가 정상 동작했는지)를
        # 직접 확인한다.
        assert len(monitor.tasks) == 1
        _repro_extra = (monitor.tasks[0].extra or {}).get("reproducibility")
        assert _repro_extra is not None
        assert _repro_extra.get("run_count") == 1
        assert _repro_extra.get("score") == 1.0

    def test_async_without_reproducibility_config_unaffected(self, tmp_path):
        """reproducibility 미지정 시 기존 동작(회귀 없음) — 함수가 정확히 1회만 호출된다."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        call_count = {"n": 0}

        @agent_eval(monitor, task_type="qa")
        async def agent(question, ground_truth=""):
            call_count["n"] += 1
            return "answer"

        asyncio.run(agent("q1", ground_truth="a"))
        assert call_count["n"] == 1
        details = self._details(monitor)
        assert details.get("avg_reproducibility") is None


class TestReq3RetryGeneratorWarning:
    """retry=RetryConfig(...)가 generator/async generator 함수와 함께 쓰이면 데코레이션
    시점에 UserWarning을 내되, 함수 자체는 재시도 없이 정상 동작해야 한다."""

    def test_sync_generator_with_retry_warns(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with pytest.warns(UserWarning, match="generator"):
            @agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3))
            def gen_agent(question, ground_truth=""):
                yield "chunk1"
                yield "chunk2"

        # 경고 이후에도 정상적으로 소비 가능해야 한다 (동작 자체는 안 바뀜)
        chunks = list(gen_agent("q1", ground_truth="a"))
        assert chunks == ["chunk1", "chunk2"]

    def test_async_generator_with_retry_warns(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with pytest.warns(UserWarning, match="generator"):
            @agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3))
            async def agen_agent(question, ground_truth=""):
                yield "chunk1"
                yield "chunk2"

        async def _consume():
            return [c async for c in agen_agent("q1", ground_truth="a")]

        chunks = asyncio.run(_consume())
        assert chunks == ["chunk1", "chunk2"]

    def test_generator_without_retry_no_warning(self, tmp_path):
        """retry 미지정이면 기존과 동일하게 경고가 없어야 한다 (회귀 없음)."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa")
            def gen_agent(question, ground_truth=""):
                yield "chunk1"

            assert not any("retry" in str(x.message) and "generator" in str(x.message) for x in w)

    def test_retry_with_regular_function_no_warning(self, tmp_path):
        """retry + 일반(non-generator) 함수 조합은 이 경고와 무관해야 한다."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @agent_eval(monitor, task_type="qa", retry=RetryConfig(max=3))
            def agent(question, ground_truth=""):
                return "answer"

            assert not any("generator" in str(x.message) for x in w)


class TestReq5ConversationEvalDeadHarnessConfigWarning:
    """conversation_eval이 받는 Harness Config 파라미터는 현재 평가에 반영되지 않으므로,
    하나라도 지정하면 데코레이션 시점에 경고해야 한다."""

    def test_single_harness_param_warns_with_name(self, tmp_path):
        from agent_evaluator import SLAConfig

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        with pytest.warns(UserWarning, match="sla"):
            @conversation_eval(monitor, sla=SLAConfig(p95_ms=2000))
            def chat(question, session_id="s1"):
                return "reply"

    def test_multiple_harness_params_all_named_in_warning(self, tmp_path):
        from agent_evaluator import InstructionConfig, ScopeConfig, SLAConfig

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @conversation_eval(
                monitor,
                sla=SLAConfig(p95_ms=2000),
                instructions=InstructionConfig(),
                scope=ScopeConfig(),
            )
            def chat(question, session_id="s1"):
                return "reply"

            _msgs = [str(x.message) for x in w if "반영되지 않습니다" in str(x.message)]
            assert len(_msgs) == 1
            for _name in ("sla", "instructions", "scope"):
                assert _name in _msgs[0]

    def test_no_harness_params_no_warning(self, tmp_path):
        """Harness Config 없이 쓰는 기존 동작은 회귀 없이 조용해야 한다."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @conversation_eval(monitor, max_turns=5)
            def chat(question, session_id="s1"):
                return "reply"

            assert not any("반영되지 않습니다" in str(x.message) for x in w)

    def test_llm_judge_not_flagged(self, tmp_path):
        """llm_judge는 실제로 동작하는 파라미터이므로 이 경고 대상이 아니다."""
        from agent_evaluator import LLMJudgeConfig

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @conversation_eval(monitor, llm_judge=LLMJudgeConfig())
            def chat(question, session_id="s1"):
                return "reply"

            assert not any("반영되지 않습니다" in str(x.message) for x in w)


def _harness_config_param_names(fn):
    """이름이 `Optional[XConfig] = None` 형태의 Harness Config 파라미터만 골라낸다.

    ``llm_judge``/``security``/``retry``는 Config 타입이지만 Harness Config(Gate A-G) 33종에
    속하지 않으므로 제외한다.
    """
    import inspect as _inspect

    sig = _inspect.signature(fn)
    exclude = {"llm_judge", "security", "retry"}
    return {
        name for name, param in sig.parameters.items()
        if "Config" in str(param.annotation) and name not in exclude
    }


class TestReq4HarnessConfigParamDrift:
    """SPEC-039 REQ-4: Harness Config 파라미터 목록이 agent_eval/batch_eval/conversation_eval/
    EvalDecorator 4곳에서 어긋나면(새 Config를 한 곳에만 추가하고 나머지를 깜빡하면) 이 테스트가
    즉시 실패해야 한다 — 지금까지는 아무것도 이걸 잡아주지 않았다."""

    def test_agent_eval_harness_params_all_present_in_batch_eval(self):
        agent_params = _harness_config_param_names(agent_eval)
        batch_params = _harness_config_param_names(batch_eval)
        missing = agent_params - batch_params
        assert not missing, (
            f"agent_eval에는 있는데 batch_eval 시그니처에는 없는 Harness Config: {missing}"
        )

    def test_agent_eval_harness_params_all_present_in_conversation_eval(self):
        """conversation_eval은 이 파라미터들을 실제로 평가에 반영하지 않지만(REQ-5),
        시그니처 자체는 여전히 agent_eval과 동기화돼 있어야 한다(호출자가 다른 데코레이터로
        갈아탈 때 파라미터 이름이 갑자기 사라지지 않도록)."""
        agent_params = _harness_config_param_names(agent_eval)
        conv_params = _harness_config_param_names(conversation_eval)
        missing = agent_params - conv_params
        assert not missing, (
            f"agent_eval에는 있는데 conversation_eval 시그니처에는 없는 Harness Config: {missing}"
        )

    def test_batch_params_frozenset_matches_batch_eval_signature(self):
        """EvalDecorator._BATCH_PARAMS(손으로 나열)의 Harness Config 부분집합이
        batch_eval의 실제 시그니처와 어긋나면 EvalDecorator.batch()가 새 Config를
        조용히 전달하지 못하게 된다."""
        from agent_evaluator.decorators import EvalDecorator

        sig_harness = _harness_config_param_names(batch_eval)
        missing_from_frozenset = sig_harness - EvalDecorator._BATCH_PARAMS
        assert not missing_from_frozenset, (
            f"batch_eval 시그니처에는 있는데 EvalDecorator._BATCH_PARAMS에는 없는 Harness Config: "
            f"{missing_from_frozenset}"
        )

    def test_conv_params_frozenset_matches_conversation_eval_signature(self):
        from agent_evaluator.decorators import EvalDecorator

        sig_harness = _harness_config_param_names(conversation_eval)
        missing_from_frozenset = sig_harness - EvalDecorator._CONV_PARAMS
        assert not missing_from_frozenset, (
            f"conversation_eval 시그니처에는 있는데 EvalDecorator._CONV_PARAMS에는 없는 "
            f"Harness Config: {missing_from_frozenset}"
        )
