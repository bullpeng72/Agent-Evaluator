"""
agent_evaluator.gates
======================
SPEC-000: Gate 패키지 전면 분해.

decorators.py / helpers/taskresult_helpers.py / core/trackers/monitor.py에 흩어져 있던
Harness Gate(A-G) 관련 코드를 Gate 단위 수직 슬라이스로 재구성하는 패키지.
Strangler Fig 방식으로 Gate 단위 이관 중이며, 원래 위치에는 하위호환을 위한 re-export만 남는다.

이관 진행 상황은 Docs/specs/SPEC-000-gate-package-decomposition.md 참조.
"""
from __future__ import annotations

