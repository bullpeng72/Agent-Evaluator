"""
tests/test_spec043_fault_injection.py
=====================================
SPEC-043 REQ-5 — thin fault-injection harness.

Covers ``FaultInjectionConfig`` / ``_FaultInjector``, the ``tool_guard`` wiring,
the ``fault_injection_session`` context, ``@agent_eval(fault_injection=...)``
end-to-end, and ``lineage.fault_injection``.
"""
from __future__ import annotations

import json
import time

import pytest

from agent_evaluator import PerformanceMonitor, agent_eval
from agent_evaluator.gates.fault_injection import (
    FaultInjectionConfig,
    FaultInjectionError,
    _FaultInjector,
    fault_injection_session,
)
from agent_evaluator.gates.gate_b_behavioral.configs import ScopeConfig
from agent_evaluator.gates.live_guardrail import (
    GuardrailBlockedError,
    LiveGuardrail,
    live_guardrail_session,
    tool_guard,
)


# --------------------------------------------------------------------------- #
# FaultInjectionConfig / _FaultInjector
# --------------------------------------------------------------------------- #
class TestConfigAndInjector:
    def test_is_noop_default(self):
        assert FaultInjectionConfig().is_noop() is True
        assert FaultInjectionConfig(tool_failure_rate=0.1).is_noop() is False
        assert FaultInjectionConfig(added_latency_ms=10).is_noop() is False
        assert FaultInjectionConfig(fail_tools=["x"]).is_noop() is False

    def test_fail_tools_always_raises_case_insensitive(self):
        inj = _FaultInjector(FaultInjectionConfig(fail_tools=["API"]))
        with pytest.raises(FaultInjectionError):
            inj.before_call("api")

    def test_seeded_rate_is_deterministic(self):
        seq_a = []
        inj_a = _FaultInjector(FaultInjectionConfig(tool_failure_rate=0.5, seed=42))
        for _ in range(20):
            try:
                inj_a.before_call("t")
                seq_a.append("ok")
            except FaultInjectionError:
                seq_a.append("fail")
        seq_b = []
        inj_b = _FaultInjector(FaultInjectionConfig(tool_failure_rate=0.5, seed=42))
        for _ in range(20):
            try:
                inj_b.before_call("t")
                seq_b.append("ok")
            except FaultInjectionError:
                seq_b.append("fail")
        assert seq_a == seq_b
        assert "fail" in seq_a and "ok" in seq_a  # 0.5 rate actually varies

    def test_zero_rate_never_raises(self):
        inj = _FaultInjector(FaultInjectionConfig(tool_failure_rate=0.0))
        for _ in range(50):
            inj.before_call("t")  # no raise

    def test_latency_sleeps(self):
        inj = _FaultInjector(FaultInjectionConfig(added_latency_ms=80))
        t0 = time.perf_counter()
        inj.before_call("t")
        assert (time.perf_counter() - t0) >= 0.07


# --------------------------------------------------------------------------- #
# tool_guard(fault_injection=...)
# --------------------------------------------------------------------------- #
class TestToolGuardWiring:
    def test_decorator_arg_injects(self):
        g = LiveGuardrail()

        @tool_guard(fault_injection=FaultInjectionConfig(fail_tools=["boom"]))
        def boom():
            return "ran"

        with live_guardrail_session(g, task_id="s1"), pytest.raises(FaultInjectionError):
            boom()

    def test_no_arg_no_injection(self):
        g = LiveGuardrail()

        @tool_guard()
        def fine():
            return 7

        with live_guardrail_session(g, task_id="s1"):
            assert fine() == 7

    def test_inherits_ambient_session(self):
        g = LiveGuardrail()

        @tool_guard()
        def plain():
            return "ok"

        with fault_injection_session(FaultInjectionConfig(fail_tools=["plain"])):
            with live_guardrail_session(g, task_id="s1"):
                with pytest.raises(FaultInjectionError):
                    plain()

    def test_explicit_noop_arg_still_inherits_ambient(self):
        # a no-op explicit config is treated as "not set" -> ambient still applies
        g = LiveGuardrail()

        @tool_guard(fault_injection=FaultInjectionConfig())
        def plain():
            return "ok"

        with fault_injection_session(FaultInjectionConfig(fail_tools=["plain"])):
            with live_guardrail_session(g, task_id="s1"):
                with pytest.raises(FaultInjectionError):
                    plain()

    def test_block_precedes_injection(self):
        g = LiveGuardrail(scope=ScopeConfig(forbidden_tools=["bt"], fail_on_violation=True))

        @tool_guard(tool_name="bt",
                    fault_injection=FaultInjectionConfig(fail_tools=["bt"]))
        def bt():
            return "ran"

        with live_guardrail_session(g, task_id="s1"):
            with pytest.raises(GuardrailBlockedError):
                bt()

    def test_works_without_active_session(self):
        @tool_guard(fault_injection=FaultInjectionConfig(fail_tools=["x"]))
        def x():
            return 1

        with pytest.raises(FaultInjectionError):
            x()

    def test_injected_failure_recorded_as_tool_failure(self):
        g = LiveGuardrail()

        @tool_guard(tool_name="api", fault_injection=FaultInjectionConfig(fail_tools=["api"]))
        def api():
            return "ok"

        with live_guardrail_session(g, task_id="s1"):
            with pytest.raises(FaultInjectionError):
                api()
        # the failed call is in the tool history with success=False
        recs = g.snapshot().get("tool_calls") or []
        assert any(
            r.get("name") == "api" and r.get("success") is False for r in recs
        )


# --------------------------------------------------------------------------- #
# @agent_eval(fault_injection=...) end to end
# --------------------------------------------------------------------------- #
class TestAgentEvalWiring:
    def test_lineage_and_extra_carry_config(self, tmp_path):
        mon = PerformanceMonitor(output_dir=str(tmp_path))
        g = LiveGuardrail()

        @tool_guard(tool_name="api")
        def call_api(payload):
            return "result"

        @agent_eval(mon, task_type="qa",
                    fault_injection=FaultInjectionConfig(fail_tools=["api"], seed=3))
        def agent(question, ground_truth=""):
            with live_guardrail_session(g, task_id="inner"):
                try:
                    call_api({"q": question})
                except FaultInjectionError:
                    return "degraded"
            return "full"

        for i in range(3):
            agent(f"q{i}", ground_truth="a")

        path = mon.save_to_file("run")
        data = json.loads(open(path).read())
        fi = data["extra_metrics"]["lineage"].get("fault_injection")
        assert isinstance(fi, dict) and fi["fail_tools"] == ["api"] and fi["seed"] == 3
        assert all(t["response"] == "degraded" for t in data["tasks"])
        assert (data["tasks"][0].get("extra") or {}).get("fault_injection")

    def test_no_fault_injection_is_unchanged(self, tmp_path):
        mon = PerformanceMonitor(output_dir=str(tmp_path))

        @agent_eval(mon, task_type="qa")
        def agent(question, ground_truth=""):
            return "answer"

        agent("q", ground_truth="a")
        path = mon.save_to_file("run")
        data = json.loads(open(path).read())
        assert "fault_injection" not in data["extra_metrics"]["lineage"]
        assert "fault_injection" not in (data["tasks"][0].get("extra") or {})

    @pytest.mark.asyncio
    async def test_async_agent_inherits_injection(self, tmp_path):
        mon = PerformanceMonitor(output_dir=str(tmp_path))
        g = LiveGuardrail()

        @tool_guard(tool_name="api")
        async def call_api(payload):
            return "result"

        @agent_eval(mon, task_type="qa",
                    fault_injection=FaultInjectionConfig(fail_tools=["api"]))
        async def agent(question, ground_truth=""):
            with live_guardrail_session(g, task_id="inner"):
                try:
                    await call_api({"q": question})
                except FaultInjectionError:
                    return "degraded"
            return "full"

        r = await agent("q", ground_truth="a")
        assert r == "degraded"
