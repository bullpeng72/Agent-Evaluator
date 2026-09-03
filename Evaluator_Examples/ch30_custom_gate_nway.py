"""
ch30_custom_gate_nway.py — 커스텀 Gate 플러그인 & N-way 비교
=================================================================
Book Chapter 30 — Harness 확장: 커스텀 Gate + 다중 버전 비교

Harness 내장 7개 Gate(A-G)로 충분하지 않을 때, 코어를 포크하지 않고
독립적인 Gate를 추가하는 법(``PerformanceMonitor.register_gate()``)과
버전이 3개 이상일 때 pairwise A/B를 반복하는 대신 한 번에 비교하는 법
(``QuickEval.ab_test_nway()``)을 시연한다.

  섹션 1: register_gate() — 커스텀 "Cost Efficiency" Gate 등록
  섹션 2: 커스텀 Gate가 대시보드/비교/회귀 판정에 그대로 편입되는지 확인
  섹션 3: ab_test_nway() — 프롬프트 v1/v2/v3 동시 비교 + FDR 보정

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch30_custom_gate_nway.py

결과:
    results/ch30_custom_gate.json
    results/ch30_prompt_v1.json, ch30_prompt_v2.json, ch30_prompt_v3.json
"""

import random
from pathlib import Path

from agent_evaluator import PerformanceMonitor, QuickEval, create_taskresult, setup_otel
from agent_evaluator.gates.base import _g

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = str(_PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Phoenix OTEL 선택적 연결 (agent-eval monitor 실행 중일 때만 활성화)
# ---------------------------------------------------------------------------
try:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 6006)) == 0:
            setup_otel(endpoint="http://localhost:6006", service_name="ch30-custom-gate-nway")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

# ===========================================================================
# 섹션 1: register_gate() — 커스텀 "Cost Efficiency" Gate 등록
# ===========================================================================
print("=== 섹션 1: register_gate() — 커스텀 Gate 등록 ===")


def _compute_cost_gate(tasks: list, min_samples_default: int) -> dict:
    """태스크당 비용이 예산(0.02$) 이내인 비율을 점수로 낸다.

    register_gate()의 계약: (tasks, min_samples_default) -> dict, 반환값은
    gates/base.py::_g()가 만드는 형태(name/score/status/gate/details)를
    따라야 다른 6개 Gate와 동일한 소비 경로(대시보드·비교·회귀 판정)를 탄다.
    """
    _BUDGET_USD = 0.02
    costs = [
        t.extra.get("custom_cost_usd")
        for t in tasks
        if (t.extra or {}).get("custom_cost_usd") is not None
    ]
    if not costs:
        return _g(None, "Cost Efficiency", {"avg_cost_usd": None, "n": 0})
    within_budget = sum(1 for c in costs if c <= _BUDGET_USD)
    score = within_budget / len(costs)
    return _g(score, "Cost Efficiency", {
        "avg_cost_usd": round(sum(costs) / len(costs), 5),
        "within_budget_rate": round(score, 4),
        "n": len(costs),
    })


monitor = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
monitor.register_gate("COST", _compute_cost_gate)

random.seed(1)
for i in range(20):
    cost = random.uniform(0.005, 0.035)  # 일부는 예산(0.02$) 초과
    monitor.record_task(create_taskresult(
        task_id=f"cost_{i:03d}",
        question=f"질문 {i}", response="응답", ground_truth="응답",
        execution_time=1.0, task_type="qa",
        extra={"custom_cost_usd": round(cost, 5)},
    ))

report = monitor.generate_report()
monitor.save_to_file("ch30_custom_gate")

# ===========================================================================
# 섹션 2: 커스텀 Gate가 다른 6개 Gate와 동일하게 편입되는지 확인
# ===========================================================================
print("\n=== 섹션 2: harness_groups에 편입된 커스텀 Gate 확인 ===")

harness = (report.to_dict().get("extra_metrics") or {}).get("harness_groups", {})
cost_gate = harness.get("COST", {})
print(f"  Gate COST  score={cost_gate.get('score')}  status={cost_gate.get('status')}")
print(f"    details: {cost_gate.get('details')}")
print(f"  overall.scored_group_ids: {harness.get('overall', {}).get('scored_group_ids')}")
print("""
  register_gate()로 등록한 Gate는 overall 점수·harness_groups.schema.json
  additionalProperties 허용 범위·대시보드 표시에 내장 7개 Gate와 동일하게
  편입된다 — 단, 내장 A-G처럼 다른 Gate와 데이터를 주고받지는 않는다
  (완전히 독립적인 Gate만 이 방식으로 추가할 수 있다).
""")

# ===========================================================================
# 섹션 3: ab_test_nway() — 프롬프트 v1/v2/v3 동시 비교
# ===========================================================================
print("=== 섹션 3: ab_test_nway() — 3개 이상 버전 동시 비교 ===")
print("""
  버전이 2개뿐이면 ab_test()로 충분하지만, 3개 이상을 비교하려고 ab_test()를
  pairwise로 반복 호출하면(v1-v2, v1-v3, v2-v3 …) 비교 쌍이 늘어날수록
  "우연히 유의해 보이는" 쌍이 늘어나는 다중비교 문제가 생긴다. ab_test_nway()는
  모든 쌍을 한 번에 비교하고 Benjamini-Hochberg FDR 보정을 일괄 적용한다.
""")


def _make_prompt_variant(name: str, base_accuracy: float, n: int = 40) -> QuickEval:
    qe = QuickEval(_OUTPUT_DIR)
    for i in range(n):
        score = max(0.0, min(1.0, base_accuracy + random.uniform(-0.1, 0.1)))
        qe._monitor.record_task(create_taskresult(
            task_id=f"{name}_{i:03d}",
            question=f"질문 {i}", response="응답", ground_truth="응답",
            accuracy_score=score, execution_time=1.0, task_type="qa",
        ))
    qe.save()
    return qe


v1 = _make_prompt_variant("ch30_prompt_v1", base_accuracy=0.70)  # 기존
v2 = _make_prompt_variant("ch30_prompt_v2", base_accuracy=0.72)  # 소폭 개선 시도
v3 = _make_prompt_variant("ch30_prompt_v3", base_accuracy=0.85)  # 대폭 개선 시도

nway_result = QuickEval.ab_test_nway(
    {"v1_기존": v1, "v2_소폭개선": v2, "v3_대폭개선": v3},
    metric="accuracy_score",
    fdr_alpha=0.05,
)

print(f"\n  버전별 평균: {nway_result['variant_stats']}")
print(f"\n  {'쌍':<24}{'delta':>9}{'p-value':>10}{'FDR 보정':>11}{'유의(원시)':>10}{'유의(FDR)':>10}")
for pair in nway_result["pairwise"]:
    p = pair["p_value"]
    p_adj = pair["p_value_fdr_adjusted"]
    label = f"{pair['a']} vs {pair['b']}"
    print(f"  {label:<24}{pair['delta']:>+9.4f}"
          f"{(f'{p:.4f}' if p is not None else 'n/a'):>10}"
          f"{(f'{p_adj:.4f}' if p_adj is not None else 'n/a'):>11}"
          f"{str(pair['significant']):>10}{str(pair['significant_fdr']):>10}")

if nway_result["sample_size_warnings"]:
    print("\n  경고:")
    for w in nway_result["sample_size_warnings"]:
        print(f"    - {w}")

print("\n결과 저장 완료: results/ch30_custom_gate.json, ch30_prompt_v{1,2,3}.json")
print("확인: agent-eval dashboard results/")
