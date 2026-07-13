"""
agent_evaluator.gates.gate_c_reliability
===========================================
Gate C — Reliability.

SPEC-000: decorators.py의 5개 Config(ReproducibilityConfig, FaultToleranceConfig,
GracefulDegradationConfig, RetryConsistencyConfig, IdempotencyConfig),
helpers/taskresult_helpers.py의 관련 eval_*/compute_* 함수, monitor.py의 Gate C
집계 로직을 이 패키지로 이관했다.

Gate C는 두 개의 교차 Gate 공유 데이터의 원천이다:
- SLA 공유 데이터(Gate D가 소비): `compute_sla_shared_data()`를 monitor.py가 한 번 호출해
  그 결과를 Gate C·D 양쪽의 aggregate 호출에 전달한다.
- hallucination_rate/avg_llm_faithfulness(Gate G가 소비, 미이관): `compute()`가
  `(group_dict, shared_raw)` 튜플을 반환하며, `shared_raw`에 반올림되지 않은 원본값을
  담아 Gate G 섹션이 재사용할 수 있도록 한다(group_dict 자체는 다른 Gate와 동일하게
  `_g()` 형식 — JSON 리포트에 노출되는 형태는 변경되지 않는다).
"""
from __future__ import annotations

