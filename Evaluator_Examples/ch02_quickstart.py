"""
ch02_quickstart.py — Agent-Evaluator 첫 시작
==============================================
Book Chapter 02 — Agent-Evaluator 첫 시작

섹션 1 (§2.3 단계 1~4)      : QuickEval 4단계 — 첫 배포 판정 경험
섹션 2 (§2.3 Harness Config) : InstructionConfig + SLAConfig + HarnessEvaluationGate
섹션 3 (§2.3 판정 결과 읽기)  : report.to_dict()로 Gate A–G 상태 파악
섹션 4 (§2.6 출력 시나리오)  : 터미널 출력 vs 파일 저장 비교
섹션 5 (§2.7 A/B 비교)       : QuickEval.compare()로 에이전트 버전 비교

의존성:
    pip install agent-evaluator

실행:
    python Evaluator_Examples/ch02_quickstart.py

결과:
    results/ch02_quickstart.json/.html  — 섹션 1
    results/ch02_harness.json/.html     — 섹션 2
    results/ch02_v1.json, ch02_v2.json  — 섹션 5
"""

from pathlib import Path

from agent_evaluator import (
    QuickEval,
    PerformanceMonitor,
    HarnessEvaluationGate,
    InstructionConfig,
    SLAConfig,
    create_taskresult,
    load_env,
)
from agent_evaluator.decorators import agent_eval

load_env()

_PROJECT_ROOT = Path(__file__).parent.parent
_OUTPUT_DIR   = str(_PROJECT_ROOT / "results")


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 1 — §2.3 QuickEval 4단계: 첫 배포 판정 경험
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 섹션 1: QuickEval 4단계 — 첫 배포 판정 (§2.3) ===")
print("  Tracker(자동 측정) × Config(기준 선언) × Gate(배포 판정) 3요소 체험")

# 단계 1 — QuickEval로 측정 시작 (PerformanceMonitor + EvalDecorator 1줄 초기화)
eval_q = QuickEval(_OUTPUT_DIR)

# 단계 2 — 에이전트 함수에 데코레이터 적용
#   @eval_q.qa = task_type="qa"로 설정된 @agent_eval 단축형
#   AccuracyEvaluator(Group A) + LatencyTracker(Group D) 자동 활성
@eval_q.qa
def my_agent(question: str, ground_truth: str = "") -> str:
    """평가 대상 에이전트. 실제 프로젝트에서는 LLM 호출로 교체하세요."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    answers = {
        "한국의 수도는?":        "서울입니다.",
        "파이썬을 만든 사람은?":  "귀도 반 로섬입니다.",
        "지구의 위성 이름은?":    "달입니다.",
        "물의 화학식은?":        "H₂O입니다.",
        "우주의 나이는?":        "138억 년입니다.",
    }
    return answers.get(question, "모르겠습니다.")

# 단계 3 — 평가 실행 (일반 함수 호출과 동일)
QA_CASES = [
    ("한국의 수도는?",        "서울입니다."),
    ("파이썬을 만든 사람은?",  "귀도 반 로섬입니다."),
    ("지구의 위성 이름은?",    "달입니다."),
    ("물의 화학식은?",        "H₂O입니다."),
    ("우주의 나이는?",        "138억 년입니다."),
]

print()
for question, gt in QA_CASES:
    resp = my_agent(question, ground_truth=gt)
    print(f"  Q: {question:<22s}  →  {resp}")

summary = eval_q.summary()
print(f"\n  TCR: {summary['tcr']:.1f}%  |  Accuracy: {summary['accuracy']:.1f}%"
      f"  |  p95: {summary.get('p95_latency', 0):.3f}s")

# 단계 4 — 첫 배포 판정 (Gate)
#   TCR < 80% 또는 Accuracy < 70% → sys.exit(1) → CI/CD 배포 차단
print("\n  [Gate] eval_q.gate(tcr=80, accuracy=70)")
try:
    eval_q.gate(tcr=80, accuracy=70)
    print("  ✅ Gate 통과 — 배포 승인")
except SystemExit:
    print("  ❌ Gate 실패 — 임계값 미달 → 배포 차단")

eval_q.save("ch02_quickstart")
print("  저장: results/ch02_quickstart.json + .html")


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 2 — §2.3 Harness Config로 배포 기준 세밀화
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 섹션 2: Harness Config — InstructionConfig + SLAConfig (§2.3) ===")
print("  QuickEval.gate()는 TCR·정확도 단순 임계값")
print("  HarnessEvaluationGate는 33개 Config 전체를 포함한 정밀 판정")

monitor_h = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

# InstructionConfig: 응답에 "완료" 또는 "처리" 키워드가 반드시 포함되어야 함
# violation_weight=0.5: 위반 1건당 IFR 50% 차감 → 기본값(0.1)보다 엄격한 기준
# SLAConfig: p95 응답 시간 2초 이하
instruction_cfg = InstructionConfig(
    required_keywords=["완료", "처리"],
    fail_on_violation=True,
    violation_weight=0.5,          # IFR = max(0, 1 − violation_count × 0.5)
)
sla_cfg = SLAConfig(p95_ms=2000)

@agent_eval(monitor_h, task_type="qa",
            instructions=instruction_cfg,
            sla=sla_cfg)
def task_agent(question: str, ground_truth: str = "") -> str:
    """키워드 준수 에이전트. '완료'/'처리' 포함 여부로 InstructionConfig 검증."""
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    responses = {
        "파일 삭제해줘":    "파일 삭제 처리 완료되었습니다.",    # ✅ 키워드 포함 → IFR 1.0
        "보고서 만들어줘":  "보고서 작성 중입니다.",             # ❌ 키워드 없음 → IFR 0.5
        "데이터 분석해줘":  "분석 결과: 평균 425입니다.",        # ❌ 키워드 없음 → IFR 0.5
    }
    return responses.get(question, "요청을 처리 완료했습니다.")

TASK_CASES = [
    ("파일 삭제해줘",   "삭제 완료"),
    ("보고서 만들어줘", "작성 완료"),
    ("데이터 분석해줘", "분석 완료"),
]

print()
for question, gt in TASK_CASES:
    resp = task_agent(question, ground_truth=gt)
    has_kw = any(k in resp for k in ["완료", "처리"])
    flag = "✅" if has_kw else "❌ InstructionConfig 위반"
    print(f"  {flag}  Q: {question:<14s}  →  {resp}")

# 저장을 Gate 판정 전에 먼저 수행 — sys.exit(1)이 호출되어도 결과 파일이 보존됨
monitor_h.save_to_file("ch02_harness")
print("  저장: results/ch02_harness.json + .html")

report_h = monitor_h.generate_report()
tcr_h = report_h.to_dict().get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
print(f"\n  TCR: {tcr_h:.1f}%  avg_IFR: (1.0+0.5+0.5)/3=0.667  Gate A≈0.583")

# HarnessEvaluationGate — required_groups=["A"]로 Gate A만 판정
# Gate A = (TCR/100 + avg_IFR) / 2 = (0.50 + 0.667) / 2 ≈ 0.583 < 0.7 → FAIL
print("\n  [Gate] HarnessEvaluationGate(report_h, required_groups=[\"A\"]).enforce()")
gate_h = HarnessEvaluationGate(report_h, required_groups=["A"])
try:
    gate_h.enforce()
    print("  ✅ Gate A 통과")
except SystemExit:
    print("  ❌ Gate A 실패 — score(0.583) < min_group_score(0.7) → 배포 차단")


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 3 — §2.3 배포 판정 결과 이해: report.to_dict()
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 섹션 3: 배포 판정 결과 읽기 — report.to_dict() (§2.3) ===")
print("  required_groups=[\"A\"]로 Gate A만 enforce; 아래 진단 루프는 A–G 전체 표시")
print("  report.to_dict()의 키 경로 패턴을 익혀두면 CI 스크립트 작성이 쉬워진다")

d = report_h.to_dict()

# TCR 경로:     d["accuracy_metrics"]["tcr"]["tcr"]
# p95 경로:     d["efficiency_metrics"]["latency"]["p95"]
# Gate A–G:    d["extra_metrics"]["harness_groups"]["A"] ~ ["G"]

tcr_v  = d.get("accuracy_metrics", {}).get("tcr", {}).get("tcr", 0.0)
p95_v  = d.get("efficiency_metrics", {}).get("latency", {}).get("p95", 0.0)
acc_v  = d.get("summary", {}).get("accuracy", 0.0)

print(f"\n  accuracy_metrics.tcr.tcr         = {tcr_v:.1f}%")
print(f"  efficiency_metrics.latency.p95   = {p95_v:.3f}s")
print(f"  summary.accuracy                 = {acc_v:.1f}%")

harness_groups = d.get("extra_metrics", {}).get("harness_groups", {})
if harness_groups:
    print("\n  Gate A–G 점수:")
    for g in ["A", "B", "C", "D", "E", "F", "G"]:
        gdata = harness_groups.get(g, {})
        if isinstance(gdata, dict) and gdata.get("score") is not None:
            score  = gdata["score"]
            status = gdata.get("status", "n/a").upper()
            icon   = "✅" if status == "PASS" else ("⚠️ " if status == "WARN" else "❌")
            print(f"    Gate {g}: {score:.3f}  {icon} {status}")
else:
    print("  (Harness Group 데이터 없음 — Config 없이 실행 시 정상)")


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 4 — §2.6 출력 시나리오: 터미널 출력 vs 파일 저장
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 섹션 4: 출력 시나리오 — 터미널 vs 파일 (§2.6) ===")

monitor_t = PerformanceMonitor(output_dir=_OUTPUT_DIR, use_korean_tokenizer=True)

# 단건 태스크 직접 생성 (create_taskresult는 accuracy_score를 자동 계산)
result_t = create_taskresult(
    task_id="s4_001",
    question="한국의 수도는?",
    response="서울입니다.",
    ground_truth="서울",
    execution_time=0.8,
    task_type="qa",

    use_korean_tokenizer=True,
)
monitor_t.record_task(result_t)

# 시나리오 ① 터미널 출력 — 개발 중 빠른 확인
report_t = monitor_t.generate_report()
summary_t = report_t.to_dict().get("summary", {})
print("\n  시나리오 ① 터미널 출력 — generate_report().to_dict()[\"summary\"]")
print(f"    task_completion_rate : {summary_t.get('task_completion_rate', 0):.3f}")
print(f"    accuracy             : {summary_t.get('accuracy', 0):.3f}")
print(f"    latency_p95          : {summary_t.get('latency_p95', 0):.3f}s")

# 시나리오 ② 파일 저장 (JSON + HTML 동시 생성)
monitor_t.save_to_file("ch02_s4")
print("\n  시나리오 ② 파일 저장 — save_to_file('ch02_s4')")
print("    results/ch02_s4.json  — 기계 읽기용 (CI/CD)")
print("    results/ch02_s4.html  — 브라우저 시각화 (Gate A–G 탭)")
print("    대시보드 실행: agent-eval dashboard results/ --watch")

# 시나리오 ③ OTEL Phoenix (코드 예시 — 실제 실행은 Phoenix 서버 필요)
print("\n  시나리오 ③ OTEL Phoenix — setup_otel() + agent-eval monitor (§2.6)")
print("    # 터미널 1: agent-eval monitor  (→ http://localhost:6006)")
print("    # 터미널 2: setup_otel(endpoint='http://localhost:6006', service_name='my-agent')")
print("    # → Tracing 탭에서 ae.tcr · ae.accuracy · ae.execution_time 실시간 확인")


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 5 — §2.7 QuickEval로 에이전트 A/B 버전 비교
# ──────────────────────────────────────────────────────────────────────────────
print("\n=== 섹션 5: A/B 에이전트 비교 — QuickEval (§2.7) ===")
print("  같은 테스트 케이스로 두 버전을 평가하고 Group A/D 지표 차이를 비교한다")

eval_a = QuickEval(_OUTPUT_DIR)
eval_b = QuickEval(_OUTPUT_DIR)

# 버전 A — 일부 답변 누락
@eval_a.qa
def agent_v1(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    answers = {
        "한국의 수도는?":     "서울입니다.",
        "파이썬 창시자는?":    "",                    # 빈 응답 → 낮은 정확도
        "지구의 자전 주기는?": "약 1년입니다.",        # 오답 (공전과 혼동)
        "빛의 속도는?":       "초속 약 30만 km입니다.",
    }
    return answers.get(question, "모르겠습니다.")

# 버전 B — 개선된 답변
@eval_b.qa
def agent_v2(question: str, ground_truth: str = "") -> str:
    # TODO(현업 적용): 아래 Mock 구현을 실제 LLM 호출로 교체하세요.
    #   예) return client.chat.completions.create(model="gpt-5-nano",
    #        messages=[{"role":"user","content":question}]).choices[0].message.content
    answers = {
        "한국의 수도는?":     "서울입니다.",
        "파이썬 창시자는?":    "귀도 반 로섬입니다.",   # ✅ 개선
        "지구의 자전 주기는?": "약 24시간입니다.",      # ✅ 개선
        "빛의 속도는?":       "초속 약 30만 km입니다.",
    }
    return answers.get(question, "모르겠습니다.")

AB_CASES = [
    ("한국의 수도는?",     "서울입니다."),
    ("파이썬 창시자는?",    "귀도 반 로섬입니다."),
    ("지구의 자전 주기는?", "약 24시간입니다."),
    ("빛의 속도는?",       "초속 약 30만 km입니다."),
]

for q, gt in AB_CASES:
    agent_v1(q, ground_truth=gt)
    agent_v2(q, ground_truth=gt)

eval_a.save("ch02_v1")
eval_b.save("ch02_v2")

s_a = eval_a.summary()
s_b = eval_b.summary()
print(f"\n  v1 — TCR: {s_a['tcr']:.1f}%  Accuracy: {s_a['accuracy']:.1f}%")
print(f"  v2 — TCR: {s_b['tcr']:.1f}%  Accuracy: {s_b['accuracy']:.1f}%")

# compare()는 {'self':..., 'other':..., 'delta':{...}} 반환
# delta는 self(v1) - other(v2) 이므로 음수 = v2가 더 우수
# ※ AccuracyEvaluator는 Token F1·Jaccard·LCS·Char Similarity 4종 가중 평균
#    ground_truth와 response가 동일 표현이면 100%, 오답/빈 응답이면 낮은 점수
delta_tcr = s_b["tcr"] - s_a["tcr"]
delta_acc = s_b["accuracy"] - s_a["accuracy"]
try:
    comparison = eval_a.compare(eval_b)
    raw_delta = comparison.get("delta", {})
    print("\n  eval_a.compare(eval_b) — delta (v2 − v1, 양수 = v2 우수):")
    for k in ["tcr", "accuracy", "p95_latency"]:
        # compare() delta = self(v1) - other(v2); 부호 반전해서 v2 개선도로 표시
        raw = raw_delta.get(k, 0.0)
        val = -raw if isinstance(raw, (int, float)) else 0.0
        unit = "%" if k in ("tcr", "accuracy") else "s"
        arrow = "↑ 개선" if val > 0 else ("↓ 악화" if val < 0 else "—")
        print(f"    {k:<14s}: {val:+.1f}{unit}  {arrow}")
except (AttributeError, TypeError):
    print(f"\n  v2 vs v1 — ΔTCR: {delta_tcr:+.1f}%  ΔAccuracy: {delta_acc:+.1f}%")

verdict = "v2 배포 권고" if s_b["accuracy"] > s_a["accuracy"] else "v1 유지 권고"
print(f"  → 판정: {verdict}")

# ──────────────────────────────────────────────────────────────────────────────
print("\n── 생성된 결과 파일 ──────────────────────────────────────────────────────")
print("  results/ch02_quickstart.json/.html  — §2.3 QuickEval 4단계 첫 배포 판정")
print("  results/ch02_harness.json/.html     — §2.3 Harness Config + Gate 정밀 판정")
print("  results/ch02_s4.*                   — §2.6 터미널·파일·Phoenix 시나리오")
print("  results/ch02_v1.json, ch02_v2.json  — §2.7 A/B 버전 비교")
print()
print("── 다음 단계 ─────────────────────────────────────────────────────────────")
print("  Ch03 → Harness Gate A–G 전체를 한 번에 평가하는 방법")
print("         HarnessEvaluationGate로 7개 Gate 종합 판정 심화")
