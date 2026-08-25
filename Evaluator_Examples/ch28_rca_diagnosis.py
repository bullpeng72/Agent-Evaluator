"""
ch28_rca_diagnosis.py — Gate 회귀 원인진단 (RCA)
====================================================
Book Chapter 28 — Gate 회귀 원인진단(RCA)

ch17(주간 리뷰)이 "회귀가 있었는가"를 발견했다면, 이 챕터는 그다음 질문
"왜 떨어졌는가"에 답한다. Chapter 31(Gate 하락 원인진단 RCA 프레임워크)의
3단계 절차(감지 → Gate 세부값 원인귀속 → 위반 이력 교차확인)를 자동화한
``agent_evaluator.rca.diagnose()``를 시연한다.

  섹션 1: baseline 결과 생성 — 정상 에이전트
  섹션 2: current 결과 생성 — Gate A가 하락한 에이전트 (plan_coherence 저하)
  섹션 3: diagnose() — 회귀 감지 + 세부 지표 원인귀속
  섹션 4: 다중 Gate 동시 하락 — 공유원인 체크(SharedCauseCheck)
  섹션 5: CLI 대응: agent-eval diagnose

HOTL 원칙(Chapter 2): diagnose()는 "후보 원인 + 근거"만 반환한다 — "이게 원인이다"를
절대 단정하지 않는다. 최종 판단은 사람(QA·거버넌스 담당자)의 몫이다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch28_rca_diagnosis.py

결과:
    results/ch28_baseline.json, ch28_current.json
"""

from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.rca import diagnose

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = str(_PROJECT_ROOT / "results")

# ===========================================================================
# 섹션 1: baseline 결과 생성 — 정상 에이전트 (plan_coherence 높음)
# ===========================================================================
print("=== 섹션 1: baseline 결과 생성 ===")

monitor_baseline = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
for i in range(15):
    monitor_baseline.record_task(create_taskresult(
        task_id=f"base_{i:03d}",
        question=f"프로젝트 계획을 세워줘 ({i})",
        response="계획을 수립했습니다: 1) 조사 2) 설계 3) 구현",
        ground_truth="계획 수립 완료",
        execution_time=1.0,
        task_type="qa",
        extra={
            # §31.4 워크드 예제와 동일한 형태 — plan_coherence가 avg_plan_coherence로
            # Gate A details에 집계된다.
            "plan_coherence": {"score": 0.90},
        },
    ))
report_baseline = monitor_baseline.generate_report()
monitor_baseline.save_to_file("ch28_baseline")
baseline_dict = report_baseline.to_dict()
_gate_a_base = (baseline_dict.get("extra_metrics") or {}).get("harness_groups", {}).get("A", {})
print(f"  baseline Gate A: score={_gate_a_base.get('score')}  "
      f"avg_plan_coherence={_gate_a_base.get('details', {}).get('avg_plan_coherence')}")

# ===========================================================================
# 섹션 2: current 결과 생성 — Gate A 하락 (plan_coherence만 저하, tcr은 유지)
# ===========================================================================
print("\n=== 섹션 2: current 결과 생성 (Gate A 회귀 유도) ===")

monitor_current = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
for i in range(15):
    monitor_current.record_task(create_taskresult(
        task_id=f"cur_{i:03d}",
        question=f"프로젝트 계획을 세워줘 ({i})",
        response="네, 진행하겠습니다",  # 완료는 하지만 계획 자체가 앞뒤가 안 맞음
        ground_truth="계획 수립 완료",
        execution_time=1.0,
        task_type="qa",
        extra={
            # §31.4 실제 사례 재현: plan_coherence만 급락 — top-line 점수만 보면
            # 놓치는, 세부값의 반대 방향 이동을 diagnose()가 그대로 드러내야 한다.
            "plan_coherence": {"score": 0.35},
        },
    ))
report_current = monitor_current.generate_report()
monitor_current.save_to_file("ch28_current")
current_dict = report_current.to_dict()
_gate_a_cur = (current_dict.get("extra_metrics") or {}).get("harness_groups", {}).get("A", {})
print(f"  current  Gate A: score={_gate_a_cur.get('score')}  "
      f"avg_plan_coherence={_gate_a_cur.get('details', {}).get('avg_plan_coherence')}")

# ===========================================================================
# 섹션 3: diagnose() — 회귀 감지 + 세부 지표 원인귀속
# ===========================================================================
print("\n=== 섹션 3: rca.diagnose() — Gate 회귀 원인진단 ===")

result = diagnose(current_dict, baseline_dict, regression_threshold=0.1)

print(f"  감지 방식:   {result['detection_mode']}")
print(f"  감지된 Gate: {result['detected_gates'] or '없음'}")

for finding in result["findings"]:
    print(f"\n  [Gate {finding['gate']}] "
          f"score {finding['baseline_score']:.3f} → {finding['current_score']:.3f}")
    print("    세부 지표 변화(2단계 — 원인귀속, 절대값 큰 순):")
    for d in finding["top_detail_deltas"][:3]:
        delta = d["delta"]
        arrow = "▼" if (delta or 0) < 0 else "▲"
        print(f"      {d['field']:<28} {d['baseline']} → {d['current']}  {arrow} {delta:+.4f}")

print(f"\n  {'-'*60}")
print("  이 리포트는 후보 원인과 근거만 제시합니다 — 최종 판단은 사람의 몫입니다 (HOTL).")

# ===========================================================================
# 섹션 4: 다중 Gate 동시 하락 — 공유원인 체크
# ===========================================================================
print("\n=== 섹션 4: 다중 Gate 동시 하락 — 공유원인 체크 ===")
print("""
  §31.2 교훈: 두 개 이상의 Gate가 동시에 하락해도 diagnose()는 "하나의 원인"으로
  성급히 단정하지 않는다. Gate C·D가 함께 감지되면 가장 싼 체크(SLA breach_rate/
  window_penalty 대조)부터 먼저 시도하고, 그래도 설명이 안 되면 각 Gate를 독립
  원인으로 보고한다 — result["shared_cause_explanations"] /
  result["independently_investigate_gates"]에서 확인할 수 있다.

  (이 챕터의 데이터는 Gate A 단일 회귀만 재현하므로 실제로는 비어 있다 — 다중 Gate
  시나리오는 baseline/current 양쪽에 harness_groups["C"], ["D"]까지 채워 넣으면
  재현할 수 있다.)
""")
print(f"  shared_cause_explanations: {result['shared_cause_explanations']}")
print(f"  independently_investigate_gates: {result['independently_investigate_gates']}")

# ===========================================================================
# 섹션 5: CLI 대응
# ===========================================================================
print("\n=== 섹션 5: CLI로 동일한 진단 실행하기 ===")
print("""
  agent-eval diagnose results/ch28_current.json --baseline results/ch28_baseline.json

  옵션:
    --regression-threshold 10        baseline 대비 허용 회귀 비율(%)
    --violation-db results/v.db      3단계(교차확인) — search_violations() 이력 조회
    --show-diff                      두 리포트의 lineage.git_commit 사이 실제 git
                                      diff까지 함께 표시(agent_version="auto" 필요)
    --json                           원본 dict를 그대로 출력(스크립트 연동용)

  대시보드에서 보려면: agent-eval dashboard results/ → 🔧 Improve 탭
""")

print("결과 저장 완료: results/ch28_baseline.json, ch28_current.json")
print("확인: agent-eval dashboard results/")
