"""
agent_evaluator.gates.gate_g_observability
=============================================
Gate G — Observability.

SPEC-000: decorators.py의 4개 Config(ObservabilityConfig, ExplainabilityConfig,
ErrorDiagnosisConfig, LatencyAttributionConfig), helpers/taskresult_helpers.py의
4개 eval_* 함수, monitor.py의 Gate G 집계 로직을 이 패키지로 이관했다.

이 이관으로 SPEC-000의 Gate A-G 전체 이관이 완료된다(F→E→D→A→B→C→G).

Gate G는 Gate C(Reliability)가 계산한 hall_rate/avg_llm_faithfulness를 파라미터로
전달받아 소비한다(LLMJudge faithfulness 활성 시 Gate G의 hallucination fallback을
비활성화하는 이중 반영 방지 로직 — Gate C의 `compute()`가 반환하는 shared_raw 원본값을
그대로 사용).
"""
from __future__ import annotations

