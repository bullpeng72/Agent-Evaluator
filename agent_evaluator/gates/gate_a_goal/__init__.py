"""
agent_evaluator.gates.gate_a_goal
====================================
Gate A — Goal Achievement.

SPEC-000: decorators.py의 6개 Config(InstructionConfig, GoalAlignmentConfig, PlanConfig,
SubtaskConfig, ContextRetentionConfig, KnowledgeRetentionConfig), helpers/taskresult_helpers.py의
6개 eval_* 함수, monitor.py의 Gate A 집계 로직을 이 패키지로 이관했다.

Gate B(Behavioral Integrity)가 avg_goal_alignment/avg_plan_coherence를 진단용으로
재참조한다 — aggregate.compute()의 반환 details에 이미 포함되므로, monitor.py는
Gate B 섹션에서 이 값을 aggregate 반환값에서 읽어온다(재계산하지 않음).
원래 위치에는 하위호환을 위한 re-export만 남는다.
"""
from __future__ import annotations

