"""
agent_evaluator.gates.gate_d_performance
===========================================
Gate D — Performance Contract.

SPEC-000: decorators.py의 5개 Config(SLAConfig, EfficiencyConfig, ResourceBudgetConfig,
TTFTVariabilityConfig, CostPredictabilityConfig), helpers/taskresult_helpers.py의
eval_sla/eval_efficiency/eval_resource_budget, monitor.py의 Gate D 집계 로직을 이 패키지로
이관했다. SLAConfig는 Gate C(Reliability)에도 breach_rate로 기여하는 이중 귀속 Config이며,
이 공유 데이터(_sla_results/_sla_window_penalty/_sla_budget_penalty/_sla_warning)는 아직
migration되지 않은 Gate C 섹션에서 계속 계산되어 aggregate.compute()에 파라미터로 전달된다.
원래 위치에는 하위호환을 위한 re-export만 남는다.
"""
