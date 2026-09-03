"""
ch28_rca_diagnosis.py — Gate 회귀 원인진단 (RCA)
====================================================
Book Chapter 28 — Gate 회귀 원인진단(RCA)

ch17(주간 리뷰)이 "회귀가 있었는가"를 발견했다면, 이 챕터는 그다음 질문
"왜 떨어졌는가"에 답한다. 3단계 절차(감지 → Gate 세부값 원인귀속 → 위반 이력
교차확인)를 자동화한 ``agent_evaluator.rca.diagnose()``를 시연한다.

  섹션 1: baseline 결과 생성 — 정상 에이전트
  섹션 2: current 결과 생성 — Gate A가 하락한 에이전트 (plan_coherence 저하)
  섹션 3: diagnose() — 회귀 감지 + 세부 지표 원인귀속 + newly_unmeasured_gates
  섹션 4: 다중 Gate 동시 하락 — 공유원인 체크(SharedCauseCheck)
  섹션 5: diagnose 후보 → 처방 — format_recommendation()으로 잇기
  섹션 6: CLI 대응: agent-eval diagnose

HOTL 원칙(Chapter 2): diagnose()는 "후보 원인 + 근거"만 반환한다 — "이게 원인이다"를
절대 단정하지 않는다. 최종 판단은 사람(QA·거버넌스 담당자)의 몫이다.

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch28_rca_diagnosis.py

결과:
    results/ch28_baseline.json, ch28_current.json
"""

import json
from pathlib import Path

from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel
from agent_evaluator.integrations.recommend_fix_mcp import format_recommendation
from agent_evaluator.ontology.metric_registry import canonical_metric_name
from agent_evaluator.rca import diagnose

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
            setup_otel(endpoint="http://localhost:6006", service_name="ch28-rca-diagnosis")
            print("  Phoenix 모니터링 활성화 — http://localhost:6006")
except Exception:
    pass

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
            # plan_coherence가 avg_plan_coherence로 Gate A details에 집계된다.
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
            # plan_coherence만 급락 — top-line 점수만 보면 놓치는, 세부값의
            # 반대 방향 이동을 diagnose()가 그대로 드러내야 한다.
            "plan_coherence": {"score": 0.35},
        },
    ))
report_current = monitor_current.generate_report()
# baseline_path를 넘기면 save_to_file()이 회귀 기반 모드로 HTML을 렌더하고,
# extra_metrics.insights에 regression_attribution / review_queue / shared_cause_*를
# 함께 채운다 (섹션 7에서 읽는다).
monitor_current.save_to_file(
    "ch28_current", baseline_path=str(Path(_OUTPUT_DIR) / "ch28_baseline.json")
)
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

# newly_unmeasured_gates — baseline엔 점수가 있었는데 current엔 측정 자체가 사라진 Gate.
# Config를 실수로 빼면 그 Gate가 통째로 안 보이는데, 회귀 판정 공식은 current=None을
# 조용히 건너뛰므로 "감지된 Gate 없음"으로만 나온다. diagnose()는 이 커버리지 손실을
# 별도 신호로 낸다(이 예제 데이터는 두 리포트 모두 Gate 구성이 같아 비어 있다).
_unmeasured = result.get("newly_unmeasured_gates", [])
if _unmeasured:
    print(f"  ⚠ 측정 커버리지 손실 — baseline엔 점수가 있었으나 current엔 측정이 없는 Gate:"
          f" {_unmeasured}")
else:
    print("  newly_unmeasured_gates: [] (두 리포트의 Gate 구성이 동일)")

# ===========================================================================
# 섹션 4: 다중 Gate 동시 하락 — 공유원인 체크
# ===========================================================================
print("\n=== 섹션 4: 다중 Gate 동시 하락 — 공유원인 체크 ===")
print("""
  Chapter 17 §17.3의 교훈: 두 개 이상의 Gate가 동시에 하락해도 diagnose()는 "하나의
  원인"으로 성급히 단정하지 않는다. Gate C·D가 함께 감지되면 가장 싼 체크(SLA
  breach_rate/window_penalty 대조)부터 먼저 시도하고, 그래도 설명이 안 되면 각 Gate를
  독립 원인으로 보고한다 — result["shared_cause_explanations"] /
  result["independently_investigate_gates"]에서 확인할 수 있다.

  (이 챕터의 데이터는 Gate A 단일 회귀만 재현하므로 실제로는 비어 있다 — 다중 Gate
  시나리오는 baseline/current 양쪽에 harness_groups["C"], ["D"]까지 채워 넣으면
  재현할 수 있다.)
""")
print(f"  shared_cause_explanations: {result['shared_cause_explanations']}")
print(f"  independently_investigate_gates: {result['independently_investigate_gates']}")

# ===========================================================================
# 섹션 5: diagnose 후보 → 처방 — format_recommendation()으로 잇기
# ===========================================================================
# diagnose()의 findings는 Gate F만 처방까지 담는다. 나머지 Gate는 1순위 후보 지표명을
# 그대로 recommend_fix(= format_recommendation)에 넘기면 된다 —
# canonical_metric_name()이 diagnose가 내는 필드명(avg_*, *_pct, *_ms, hall_rate 등)을
# NATIVE_METRIC_RULES 키로 정규화하므로, 어휘 변환을 손으로 할 필요가 없다.
print("\n=== 섹션 5: diagnose 후보 → 처방 (format_recommendation) ===")

for finding in result["findings"]:
    gate = finding["gate"]
    if not finding["top_detail_deltas"]:
        continue
    top_field = finding["top_detail_deltas"][0]["field"]
    canon = canonical_metric_name(top_field)
    print(f"\n  [Gate {gate}] 1순위 후보 지표: {top_field}"
          + (f"  (→ '{canon}'로 정규화)" if canon != top_field else ""))
    print("  " + "\n  ".join(format_recommendation(gate, top_field).splitlines()))

# ===========================================================================
# 섹션 6: CLI 대응
# ===========================================================================
print("\n=== 섹션 6: CLI로 동일한 진단 실행하기 ===")
print("""
  agent-eval diagnose results/ch28_current.json --baseline results/ch28_baseline.json

  옵션:
    --regression-threshold 10        baseline 대비 허용 회귀 비율(%)
    --violation-db results/v.db      3단계(교차확인) — search_violations() 이력 조회
    --show-diff                      두 리포트의 lineage.git_commit 사이 실제 git
                                      diff까지 함께 표시(agent_version="auto" 필요)
    --repo-path /path/to/repo        --show-diff를 판단할 git 저장소 경로 (기본: 현재 디렉토리)
    --json                           원본 dict를 그대로 출력(스크립트 연동용)

  세부 지표 순위는 필드명 접미사별 스케일 보정표(_pct→100, _ms→2000, _count→10,
  _latency_s→5)로 단위를 맞춘 뒤 매겨진다. 커버리지 손실이 있으면 감지된 Gate와
  별개로 "⚠ 측정 커버리지 손실"과 newly_unmeasured_gates 목록이 함께 출력된다.

  대시보드에서 보려면: agent-eval dashboard results/ → 🔧 Improve 탭
""")

# ===========================================================================
# 섹션 7: 같은 진단이 결과 JSON에 이미 들어 있다 — extra_metrics.insights
# ===========================================================================
# diagnose()를 직접 호출하지 않아도, 섹션 2에서 baseline_path와 함께 저장한
# ch28_current.json의 extra_metrics.insights에 회귀 원인귀속·리뷰 큐·대상별
# 브리프가 기계 판독 형태로 이미 계산돼 있다. CI·에이전트는 이걸 그대로 읽는다.
print("\n=== 섹션 7: extra_metrics.insights — 저장된 기계 판독 진단 계층 ===")

_ins = (json.loads((Path(_OUTPUT_DIR) / "ch28_current.json").read_text(encoding="utf-8"))
        .get("extra_metrics", {}).get("insights", {}))

_ra = _ins.get("regression_attribution")
if _ra:
    print(f"  regression_attribution: {json.dumps(_ra, ensure_ascii=False)[:300]}")
else:
    print("  regression_attribution: null "
          "(프롬프트/Config lineage 변화가 없으면 비어 있다 — 여기선 코드 변경 없음)")

_rq = _ins.get("review_queue") or {}
if _rq.get("n_items"):
    _bp = _rq.get("by_priority") or {}
    print(f"  review_queue: {_rq['n_items']}건 "
          f"(high {_bp.get('high', 0)} / medium {_bp.get('medium', 0)}) "
          f"— `agent-eval dataset promote`로 골든 회귀 케이스 편입")

_sc = _ins.get("shared_cause_explanations")
print(f"  shared_cause_explanations: {_sc if _sc else '[] (Gate A 단일 회귀)'}")

_briefs = _ins.get("briefs") or {}
for _who in ("pm", "qa"):
    if _briefs.get(_who):
        print(f"  briefs.{_who}: {_briefs[_who]}")

print(f"\n  회귀 기반 HTML 리포트: {_OUTPUT_DIR}/ch28_current.html")
print("    └ Gate RCA 진단 섹션 · 📉회귀/🆕신규/✅수정 실패 집합 diff · newly_unmeasured_gates")
print("  CLI 게이트: agent-eval gate results/ch28_current.json \\")
print("               --baseline-result results/ch28_baseline.json \\")
print("               --fail-on-case-regression --digest")

print("\n결과 저장 완료: results/ch28_baseline.json, ch28_current.json  (+ .html)")
print("확인: agent-eval dashboard results/")
