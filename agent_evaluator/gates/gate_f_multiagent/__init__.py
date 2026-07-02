"""
agent_evaluator.gates.gate_f_multiagent
==========================================
Gate F — Multi-Agent Coordination.

SPEC-000 Commit 1: decorators.py의 4개 Config(ConsensusConfig, PropagationConfig,
AgentRoleConfig, ConflictResolutionConfig), helpers/taskresult_helpers.py의 4개
eval_* 함수, monitor.py의 Gate F 집계 로직을 이 패키지로 이관했다.
원래 위치(decorators.py/taskresult_helpers.py)에는 하위호환을 위한 re-export만 남는다.
"""
