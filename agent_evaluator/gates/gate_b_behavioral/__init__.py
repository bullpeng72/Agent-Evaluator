"""
agent_evaluator.gates.gate_b_behavioral
==========================================
Gate B — Behavioral Integrity.

SPEC-000: decorators.py의 6개 Config(LoopDetectionConfig, ScopeConfig,
ToolParameterSafetyConfig, ContextWindowConfig, StateConsistencyConfig, DeadlockConfig),
helpers/taskresult_helpers.py의 6개 eval_* 함수, monitor.py의 Gate B 집계 로직을 이
패키지로 이관했다.

Gate B는 Gate A(Goal Achievement)의 avg_goal_alignment/avg_plan_coherence를 진단용으로만
재참조한다(스코어링에는 미포함) — monitor.py가 `_a_group["details"]`에서 값을 전달한다.
원래 위치에는 하위호환을 위한 re-export만 남는다.
"""
from __future__ import annotations

