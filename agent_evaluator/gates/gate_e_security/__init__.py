"""
agent_evaluator.gates.gate_e_security
========================================
Gate E — Security Boundary.

SPEC-000 Commit: decorators.py의 3개 Config(ThreatSeverityConfig, ComplianceConfig,
ThreatResponseConfig), helpers/taskresult_helpers.py의 3개 eval_* 함수, monitor.py의
Gate E 집계 로직을 이 패키지로 이관했다. 원래 위치에는 하위호환을 위한 re-export만 남는다.
"""
from __future__ import annotations

