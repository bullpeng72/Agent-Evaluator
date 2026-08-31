"""
ch31_recommendation_tracking.py — 개선 이력 추적 (폐루프 학습)
===================================================================
Book Chapter 31 — 개선 이력 추적(폐루프 학습): Chapter 28(RCA)과 짝을 이루는
마지막 고리 — "추천한 조치를 실제로 적용했더니 나아졌는가"를 기록하고 누적한다.

ch28(RCA)이 "무엇이 원인일 가능성이 있는지" 후보를 내고 그 후보 지표명을
recommend_fix/format_recommendation에 넘겨 처방을 얻는다면, 이 챕터는 그 처방을
실제로 적용한 뒤 재평가한 결과를 판정·기록해 폐루프를 완성한다.

  섹션 1: 개선 전(before) / 개선 후(after) 결과 생성
  섹션 2: verify_recommendation_outcome() — 실제로 개선됐는가 판정
  섹션 3: record_recommendation_outcome() — 판정을 감사 로그에 기록
  섹션 4: load_recommendation_outcomes() / summarize_recommendation_outcomes()
  섹션 5: 대시보드 Improve 탭과의 연동

HOTL 원칙: verdict는 confirmed/refuted/inconclusive 세 상태로만 보고한다 —
"이 추천 덕분에 좋아졌다"는 인과 주장은 하지 않는다(다른 변경이 동시에
있었을 수 있다, Chapter 17 §17.3의 회귀 분석 경계심과 동일).

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch31_recommendation_tracking.py

결과:
    results/ch31_before.json, ch31_after.json
    results/recommendation_outcomes.jsonl  ← agent-eval dashboard의
                                              🔧 Improve 탭이 그대로 읽는 파일
"""

import json
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.rca import (
    load_recommendation_outcomes,
    record_recommendation_outcome,
    summarize_recommendation_outcomes,
    verify_recommendation_outcome,
)

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR = str(_PROJECT_ROOT / "results")
# agent-eval dashboard가 results_dir 아래 이 고정 파일명을 자동으로 읽는다
# (serve/routers/diagnose.py::_RECOMMENDATIONS_FILENAME) — 별도 설정 불필요.
_RECOMMENDATIONS_LOG = str(Path(_OUTPUT_DIR) / "recommendation_outcomes.jsonl")

# ===========================================================================
# 섹션 1: 개선 전(before) / 개선 후(after) 결과 생성
# ===========================================================================
print("=== 섹션 1: 개선 전/후 결과 생성 ===")
print("""
  ch28의 시나리오를 이어받는다 — Gate A가 plan_coherence 저하로 떨어졌었고
  (ontology/mast_taxonomy.py 기준으로는 "계획 실패" 계열 실패모드), 프롬프트에
  단계별 계획을 명시적으로 요구하는 지시문을 추가하는 조치를 취했다고 가정한다.
""")

monitor_before = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
for i in range(15):
    monitor_before.record_task(create_taskresult(
        task_id=f"before_{i:03d}",
        question=f"프로젝트 계획을 세워줘 ({i})",
        response="네, 진행하겠습니다",
        ground_truth="계획 수립 완료",
        execution_time=1.0, task_type="qa",
        extra={"plan_coherence": {"score": 0.35}},
    ))
before_report = monitor_before.generate_report()
monitor_before.save_to_file("ch31_before")
before_dict = before_report.to_dict()

monitor_after = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)
for i in range(15):
    monitor_after.record_task(create_taskresult(
        task_id=f"after_{i:03d}",
        question=f"프로젝트 계획을 세워줘 ({i})",
        response="계획을 수립했습니다: 1) 조사 2) 설계 3) 구현",
        ground_truth="계획 수립 완료",
        execution_time=1.0, task_type="qa",
        extra={"plan_coherence": {"score": 0.88}},  # 조치 적용 후 개선
    ))
after_report = monitor_after.generate_report()
monitor_after.save_to_file("ch31_after")
after_dict = after_report.to_dict()

_a = (before_dict.get("extra_metrics") or {}).get("harness_groups", {}).get("A", {})
_b = (after_dict.get("extra_metrics") or {}).get("harness_groups", {}).get("A", {})
print(f"  before Gate A: {_a.get('score')}   after Gate A: {_b.get('score')}")

# ===========================================================================
# 섹션 2: verify_recommendation_outcome() — 실제로 개선됐는가 판정
# ===========================================================================
print("\n=== 섹션 2: verify_recommendation_outcome() ===")

verdict = verify_recommendation_outcome(
    before_dict, after_dict,
    target_gate="A", target_field="avg_plan_coherence",
    improvement_threshold=0.05,
)
print(f"  target_gate:        {verdict['target_gate']}")
print(f"  before → after:     {verdict['before_score']} → {verdict['after_score']}")
print(f"  gate_delta:         {verdict['gate_delta']:+.4f}")
print(f"  verdict:            {verdict['verdict']}")
print(f"  target_field_result: {verdict['target_field_result']}")

# ===========================================================================
# 섹션 3: record_recommendation_outcome() — 감사 로그에 기록
# ===========================================================================
print("\n=== 섹션 3: record_recommendation_outcome() — 이력 기록 ===")

entry = record_recommendation_outcome(
    _RECOMMENDATIONS_LOG,
    recommendation_id="plan-coherence-explicit-steps",
    target_gate="A",
    before=before_dict,
    after=after_dict,
    target_field="avg_plan_coherence",
    note="프롬프트에 '단계별로 계획을 명시하라' 지시문 추가",
)
print(f"  기록됨: {entry['recommendation_id']} → verdict={entry['verdict']}")
print(f"  로그 파일: {_RECOMMENDATIONS_LOG}")
print("""
  이 로그는 .aoo/claims.jsonl과 동일한 append-only JSON Lines 형식이다 —
  기록만 하고 순위·성공률은 계산하지 않는다(표본이 적을 때 오도하기 쉬운
  통계이기 때문 — 개수 집계까지만 자동화하고, "다음에 뭘 추천할지"는 사람이
  이 개수를 보고 판단한다).
""")

# ===========================================================================
# 섹션 4: 이력 조회 및 집계
# ===========================================================================
print("=== 섹션 4: load_recommendation_outcomes() / summarize_recommendation_outcomes() ===")

outcomes = load_recommendation_outcomes(_RECOMMENDATIONS_LOG)
summary = summarize_recommendation_outcomes(outcomes)

print(f"  전체 기록: {summary['total']}건")
print(f"    confirmed:    {summary['confirmed']}")
print(f"    refuted:      {summary['refuted']}")
print(f"    inconclusive: {summary['inconclusive']}")
print(f"  Gate별: {summary['by_gate']}")

# ── 개선된 리포트: 이 로그가 결과 JSON의 인사이트로 되돌아온다 ────────────────
# 위에서 쌓은 recommendation_outcomes.jsonl은 다음 실행부터 build_insights()가
# extra_metrics.insights.improvement_priors((Gate,변경 카테고리)별 confirm-rate
# 실적)와 recommendations[].prior로 되읽는다 — 순위·자동추천이 아니라, 다음
# 조치를 사람이 판단할 때 참고하는 과거 실적 카운트다.
_ins_after = (json.loads((Path(_OUTPUT_DIR) / "ch31_after.json").read_text(encoding="utf-8"))
              .get("extra_metrics", {}).get("insights", {}))
_recs = _ins_after.get("recommendations") or []
for _r in _recs[:2]:
    _pr = _r.get("prior")
    print(f"  insights.recommendations[{_r.get('gate')}]: {(_r.get('guidance') or '')[:70]}")
    if _pr:
        print(f"    └ prior: {_pr}")
_ipr = _ins_after.get("improvement_priors")
print(f"  insights.improvement_priors: {_ipr if _ipr else 'null (아직 실적 표본 부족)'}")

# ===========================================================================
# 섹션 5: 대시보드 Improve 탭과의 연동
# ===========================================================================
print("\n=== 섹션 5: 대시보드에서 확인하기 ===")
print("""
  agent-eval dashboard results/ → 🔧 Improve 탭

  "Recommendation Outcome History" 섹션이 방금 기록한 항목을 그대로
  보여준다 — 별도 API 연동 없이 results_dir/recommendation_outcomes.jsonl
  파일만 있으면 대시보드가 자동으로 읽는다.

  RCA 진단(ch28)도 같은 탭에서 재현할 수 있다 — Current에 ch31_after.json,
  Baseline에 ch31_before.json을 선택하면 섹션 1~2의 판정을 화면에서 그대로
  볼 수 있다.
""")

print("결과 저장 완료: results/ch31_before.json, ch31_after.json, recommendation_outcomes.jsonl")
print("확인: agent-eval dashboard results/")
