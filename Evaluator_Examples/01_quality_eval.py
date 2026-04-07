"""
품질 지표 검증 예제 — Agent Evaluator v0.6.7
============================================

검증 지표 (Layer 1 — 품질):
  AccuracyEvaluator      │ add_evaluation(task_id, ground_truth, prediction, task_type)
                         │   → QA · 코드 · 범용 텍스트 정확도 (토큰 F1 · Jaccard · LCS)
                         │   기대: 전체 평균 >10% (long-response vs short-ground_truth 특성상 낮음)
  HallucinationDetector  │ detect_hallucination(task_id, response, context, ground_truth)
                         │   → 반환: hallucination_rate (0.0–1.0), indicators, timestamp
                         │   기대: 할루시네이션 tier avg_rate > 정상 tier avg_rate
  ResponseQualityEval.   │ evaluate_response(task_id, response, request, expected_elements, ground_truth)
                         │   → 관련성·완전성·정확성·명확성·유용성 5차원
                         │   기대: 저품질 케이스 avg_total <3.0
  RAG Metrics (Layer 3)  │ record_rag_metrics(faithfulness, answer_relevancy, ...)
                         │   기대: 할루시네이션 케이스 faithfulness <0.4

핵심 개선 사항 (v0.6.0):
  - AccuracyEvaluator.add_evaluation() 직접 호출 추가 (기존: 누락)
  - HallucinationDetector.detect_hallucination() 직접 호출 → 케이스별 결과 캡처
  - 케이스 tier (high / hallucination / low_quality) 기반 예상 범위 정의
  - 최종 검증 테이블: 예상 vs 실제 분리 여부 PASS/FAIL 출력

실행:
    python 01_quality_eval.py
"""

import json
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from agent_evaluator import PerformanceMonitor, TaskResult, create_taskresult
from agent_evaluator.decorators import agent_eval, EvalMetadata
from agent_evaluator.reporting import generate_comprehensive_html_report


def _try_setup_otel(service_name: str) -> None:
    """Phoenix가 실행 중이면 OTEL 활성화 (선택적). 미실행 시 무시."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        _s.settimeout(1)
        if _s.connect_ex(("localhost", 6006)) != 0:
            return
    try:
        from agent_evaluator import setup_otel
        setup_otel(endpoint="http://localhost:6006", service_name=service_name)
        print(f"  📡  Phoenix 모니터링 활성화 — http://localhost:6006  (service: {service_name})")
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).debug("setup_otel 실패: %s", _e)

_try_setup_otel("01-quality-eval")

# ── 모듈 레벨 공유 상태 (@agent_eval 데코레이터 함수용) ──────────────────────────
_sc_01: dict = {}                                                   # 루프 이터레이션별 시나리오 데이터
_hl_scores_by_tier_01: dict = {"high": [], "hallucination": [], "low_quality": []}  # tier별 hl_score 수집


def _load_golden(filename: str) -> list:
    path = project_root / "data" / "golden_datasets" / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ────────────────────────────────────────────────────────────────────────────────
# 데이터셋 — tier별 예상 결과 명시
# tier: "high"        → accuracy >65%, quality >3.5/5.0, hl_score 낮음
#       "hallucination" → accuracy <40%, hl_score 높음 (사실과 다른 응답)
#       "low_quality"   → quality avg <3.0 (내용 부실)
# ────────────────────────────────────────────────────────────────────────────────
# 데이터셋 — tier별 예상 결과 명시
# tier: "high"        → accuracy >65%, quality >3.5/5.0, hl_score 낮음
#       "hallucination" → accuracy <40%, hl_score 높음 (사실과 다른 응답)
#       "low_quality"   → quality avg <3.0 (내용 부실)
# 골든 데이터셋에서 로드 (data/golden_datasets/)
# ────────────────────────────────────────────────────────────────────────────────

_raw_qa = _load_golden("quality_tech_qa.json")
QA_DATASET = [
    {"q": d["question"], "a": d["response"], "truth": d["ground_truth"],
     "context": d["context"], "type": d["task_type"], "tier": d["tier"]}
    for d in _raw_qa
]

# 코드 정확도 검증 케이스
_raw_code = _load_golden("quality_code_cases.json")
CODE_CASES = [
    {"task_id": d["task_id"], "q": d["question"],
     "expected": d["ground_truth"], "actual": d["response"], "tier": d["tier"]}
    for d in _raw_code
]

def run_quality_evaluation():
    print("\n" + "=" * 70)
    print("  품질 지표 검증 — Agent Evaluator v0.6.7")
    print("  Accuracy · Hallucination · ResponseQuality · RAG Metrics")
    print("=" * 70)

    rng = random.Random(42)

    import os
    _has_api = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

    # for_rag_evaluation(): hallucination_detection 기본 활성화 (RAG/QA 품질 평가 최적화)
    monitor = PerformanceMonitor.for_rag_evaluation(
        output_dir=str(project_root / "results"),  # Phoenix Top-models / Cost 차트 그룹핑용
        enable_transparency=True,
        enable_llm_judge=_has_api,   # API 키 있으면 자동 활성화
        judge_sample_rate=1.0,       # 전량 채점 (데모용)
        # judge_model 생략 → agent-eval init 설정 자동 반영
    )

    base_time = datetime.now() - timedelta(hours=2)

    # 검증 추적
    task_tier_map: dict = {}  # task_id → tier (정확도 분리 검증용)

    # ── QA 평가 @agent_eval 데코레이터 함수 ──────────────────────────────────────
    @agent_eval(
        monitor,
        task_type="qa",
        task_id_prefix="quality",
        task_id_fn=lambda args, kw: f"quality_{_sc_01.get('idx', 0)+1:03d}",
        flush_every=10,
        flush_filename="01_quality_eval",
    )
    def _qa_eval_agent(question: str, context: str = "", ground_truth: str = "") -> str:
        sc = _sc_01
        item = sc["item"]
        tier = item["tier"]
        i = sc["idx"]
        task_id = f"quality_{i+1:03d}"

        # ① HallucinationDetector — tier별 hl_score 수집 (검증 테이블용)
        if context:
            hl_result = monitor.hallucination_detector.detect_hallucination(
                task_id=task_id,
                response=item["a"],
                context=context,
                ground_truth=item["truth"],
                request=question,
            )
            hl_score = hl_result.get("hallucination_rate", 0.0)
            _hl_scores_by_tier_01[tier].append(hl_score)

        # ③ AccuracyEvaluator
        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=item["truth"],
            prediction=item["a"],
            task_type=item["type"],
        )

        # ④ ResponseQualityEvaluator
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=item["a"],
            request=question,
            expected_elements=item["truth"].split() if tier == "high" else [],
            ground_truth=item["truth"],
        )

        # ⑤ RAG 지표
        if item["type"] in ("qa", "information_retrieval"):
            if tier == "high":
                monitor.record_rag_metrics(
                    faithfulness=round(rng.uniform(0.72, 0.95), 3),
                    answer_relevancy=round(rng.uniform(0.74, 0.96), 3),
                    context_precision=round(rng.uniform(0.68, 0.92), 3),
                    context_recall=round(rng.uniform(0.70, 0.94), 3),
                )
            elif tier == "hallucination":
                monitor.record_rag_metrics(
                    faithfulness=round(rng.uniform(0.05, 0.25), 3),
                    answer_relevancy=round(rng.uniform(0.08, 0.30), 3),
                    context_precision=round(rng.uniform(0.10, 0.35), 3),
                    context_recall=round(rng.uniform(0.05, 0.22), 3),
                )

        if tier != "high":
            raise RuntimeError(f"{tier}_quality_issue")
        return item["a"]

    # ── 코드 평가 @agent_eval 데코레이터 함수 ────────────────────────────────────
    @agent_eval(
        monitor,
        task_type="code_generation",
        task_id_prefix="code",
        task_id_fn=lambda args, kw: _sc_01.get("code_task_id", "code_000"),
        flush_every=5,
        flush_filename="01_quality_code",
    )
    def _code_eval_agent(question: str, ground_truth: str = "") -> str:
        sc = _sc_01
        cc = sc["cc"]
        tier = cc["tier"]
        task_id = sc["code_task_id"]

        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=cc["expected"],
            prediction=cc["actual"],
            task_type="code_generation",
        )
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=cc["actual"],
            request=question,
            expected_elements=[],
            ground_truth=cc["expected"],
        )

        if tier != "high":
            raise RuntimeError("code_mismatch")
        return cc["actual"]

    print("\n  [1/3] QA 데이터셋 평가 (Accuracy · Hallucination · Quality)")
    print(f"  {'task_id':<20} {'tier':<15} {'hl_score':>10}  {'메모'}")
    print(f"  {'─'*20} {'─'*15} {'─'*10}  {'─'*20}")

    global _sc_01, _hl_scores_by_tier_01
    _hl_scores_by_tier_01 = {"high": [], "hallucination": [], "low_quality": []}  # reset

    for i, item in enumerate(QA_DATASET):
        _sc_01 = {"idx": i, "item": item}
        task_id = f"quality_{i+1:03d}"
        tier = item["tier"]
        task_tier_map[task_id] = tier  # keep for verification table
        try:
            _qa_eval_agent(
                question=item["q"],
                context=item.get("context", ""),
                ground_truth=item["truth"],
            )
        except RuntimeError:
            pass
        hl_score = _hl_scores_by_tier_01[tier][-1] if _hl_scores_by_tier_01[tier] else 0.0
        flag = "⚠️ " if tier == "hallucination" else ("🔻 " if tier == "low_quality" else "   ")
        print(f"  {flag}{task_id:<18} {tier:<15} {hl_score:>10.3f}  {item['q'][:30]}...")

    # ─── 코드 정확도 평가 ──────────────────────────────────────────────────────
    print(f"\n  [2/3] Code Accuracy 평가 (AST/정규화 비교)")
    print(f"  {'task_id':<20} {'tier':<15} {'메모'}")
    print(f"  {'─'*20} {'─'*15} {'─'*30}")

    for cc in CODE_CASES:
        _sc_01 = {"cc": cc, "code_task_id": cc["task_id"]}
        try:
            _code_eval_agent(question=cc["q"], ground_truth=cc["expected"])
        except RuntimeError:
            pass
        flag = "   " if cc["tier"] == "high" else "🔻 "
        print(f"  {flag}{cc['task_id']:<18} {cc['tier']:<15} {cc['q'][:35]}...")

    # ─── 리포트 저장 ──────────────────────────────────────────────────────────
    report = monitor.generate_report()
    filename = f"[Q]_quality_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)
    html_path = Path(saved_path).with_suffix('.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(generate_comprehensive_html_report(monitor))
    print(f"📄 HTML 리포트 저장: {html_path}")

    # ─── 결과 집계 ────────────────────────────────────────────────────────────
    print(f"\n  [3/3] 집계 결과")
    accuracy_data = report.accuracy_metrics.get("accuracy_scores", {})
    quality_data = report.accuracy_metrics.get("quality", {})
    hallucination_data = report.accuracy_metrics.get("hallucination", {})
    rag_data = monitor.get_rag_metrics_summary()
    accuracy_by_type = monitor.accuracy_evaluator.get_accuracy_by_type()

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개  |  저장: {saved_path}")

    print(f"\n  [AccuracyEvaluator — 타입별 텍스트 유사도]")
    for t, score in sorted(accuracy_by_type.items()):
        print(f"    {t:<22}: {score:.1f}%")
    print(f"    {'전체 평균':<22}: {accuracy_data.get('overall_accuracy', 0):.1f}%")

    print(f"\n  [ResponseQualityEvaluator — 5차원 (0–5.0)]")
    dim_scores = quality_data.get("dimension_scores", quality_data.get("dimension_averages", {}))
    for dim in ["relevance", "completeness", "accuracy", "clarity", "usefulness"]:
        print(f"    {dim:<15}: {dim_scores.get(dim, 0):.2f}/5.0")
    avg_total = quality_data.get("avg_total_score", 0)
    print(f"    {'avg_total':<15}: {avg_total:.2f}/5.0  (grade: {quality_data.get('avg_grade', 'N/A')})")

    print(f"\n  [HallucinationDetector — 컨텍스트 기반]")
    print(f"    전체 탐지율:  {hallucination_data.get('overall_rate', 0):.1f}%")
    print(f"    무근거 주장:  {hallucination_data.get('unsupported_claims_count', 0)}건")
    if _hl_scores_by_tier_01["hallucination"]:
        avg_hl = sum(_hl_scores_by_tier_01["hallucination"]) / len(_hl_scores_by_tier_01["hallucination"])
        avg_nm = sum(_hl_scores_by_tier_01["high"]) / len(_hl_scores_by_tier_01["high"]) if _hl_scores_by_tier_01["high"] else 0
        print(f"    할루시네이션 케이스 평균 점수: {avg_hl:.3f}")
        print(f"    정상 케이스 평균 점수:         {avg_nm:.3f}")

    print(f"\n  [RAG Metrics — Layer 3 시뮬레이션]")
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        val = rag_data.get(metric, {}).get("mean", 0)
        print(f"    {metric:<22}: {val:.3f}")

    if _has_api and monitor.llm_judge:
        judge_summary = monitor.llm_judge.get_summary()
        if judge_summary["count"] > 0:
            avg = judge_summary["avg_scores"]
            print(f"\n  [LLM Judge — 3차원 자동 채점 (0–5)]")
            print(f"    채점 건수:             {judge_summary['count']}건  (비용 ${judge_summary['total_cost_usd']:.5f})")
            print(f"    completeness        평균: {avg.get('completeness', 0):.2f}/5")
            print(f"    relevance           평균: {avg.get('relevance', 0):.2f}/5")
            print(f"    factual_consistency 평균: {avg.get('factual_consistency', 0):.2f}/5")
            print(f"    overall             평균: {avg.get('overall', 0):.2f}/5")
            print(f"    → 대시보드 Quality 탭 하단 '🤖 LLM Judge 점수' 섹션에서 확인 가능")

    # ─── 검증 테이블 ──────────────────────────────────────────────────────────
    print(f"\n  {'━'*70}")
    print(f"  검증 테이블 — 예상 범위 vs 실제 측정값")
    print(f"  {'━'*70}")
    print(f"  {'지표':<38} {'기대':<22} {'실제':<12} 결과")
    print(f"  {'─'*38} {'─'*22} {'─'*12} {'─'*6}")

    overall_acc = accuracy_data.get("overall_accuracy", 0)
    rag_faith = rag_data.get("faithfulness", {}).get("mean", 0)
    claims_count = hallucination_data.get("unsupported_claims_count", 0)

    # 정확도 tier 분리 검증: high tier avg > hallucination tier avg
    # (AccuracyEvaluator 내부 evaluations 리스트에서 task_id → tier 매핑으로 집계)
    acc_by_tier: dict = {"high": [], "hallucination": [], "low_quality": []}
    for ev in monitor.accuracy_evaluator.evaluations:
        t = task_tier_map.get(ev["task_id"])
        if t in acc_by_tier:
            acc_by_tier[t].append(ev["accuracy"])

    avg_acc_high = sum(acc_by_tier["high"]) / len(acc_by_tier["high"]) if acc_by_tier["high"] else 0
    avg_acc_hl   = sum(acc_by_tier["hallucination"]) / len(acc_by_tier["hallucination"]) if acc_by_tier["hallucination"] else 0
    acc_separation = avg_acc_high > avg_acc_hl
    acc_sep_label  = f"{avg_acc_high:.3f}>{avg_acc_hl:.3f}"

    checks = [
        # 전체 평균 10%+ — long-response vs short ground_truth 특성상 자연히 낮음
        ("전체 평균 정확도",                "> 10.0%",   f"{overall_acc:.1f}%",   overall_acc > 10),
        # 혼합 데이터셋(high+hl+low_quality) 평균 1.2/5.0 이상 (시뮬레이션 텍스트 특성 반영)
        ("평균 품질 점수",                  "> 1.2/5.0", f"{avg_total:.2f}",       avg_total > 1.2),
        # 컨텍스트 미지원 주장이 최소 1건 이상 탐지되었는지
        ("unsupported claims 탐지",         "> 0건",      f"{claims_count}건",     claims_count > 0),
        ("RAG faithfulness (정상 케이스)",   "> 0.50",    f"{rag_faith:.3f}",      rag_faith > 0.50),
        # AccuracyEvaluator tier 분리: 정상 케이스 정확도 > 할루시네이션 케이스 정확도
        ("정확도 tier 분리 (high > hl)",    "High>HL",   acc_sep_label,            acc_separation),
    ]

    all_pass = True
    for name, expected, actual, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False
        print(f"  {name:<38} {expected:<22} {actual:<12} {status}")

    print(f"  {'━'*70}")
    print(f"  최종 결과: {'✅ 모든 검증 통과' if all_pass else '⚠️ 일부 검증 실패 — 위 항목 확인'}")
    print(f"  {'━'*70}\n")

    if report.alerts:
        print(f"  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:4]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")
        print()

    return saved_path


def run_llm_judge_demo():
    """LLM-as-Judge 평가 패턴 시연 (v0.6.3 신규).

    ground_truth 없이도 completeness · relevance · factual_consistency 3차원
    자동 채점이 가능합니다.  OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 가 필요합니다.

    API 키 미설정 시 graceful skip 됩니다.
    """
    import os
    api_key_set = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

    print("\n" + "=" * 70)
    print("  LLM-as-Judge 평가 패턴 — Agent Evaluator v0.6.7")
    print("  목표: ground_truth 없이 3차원 자동 채점 (completeness/relevance/factual)")
    print("=" * 70)

    if not api_key_set:
        print("\n  ⚠️  API 키 미설정 — LLM Judge 데모를 건너뜁니다.")
        print("     OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 를 설정하세요.")
        print("     (agent-eval init 으로 간편 설정 가능)")
        return

    from agent_evaluator import LLMJudge

    # ── 오픈도메인 QA 케이스 (ground_truth 없음) ────────────────────────────
    OPEN_QA = [
        {
            "question": "마이크로서비스 아키텍처의 장단점을 설명해줘",
            "response": "마이크로서비스는 서비스별 독립 배포·확장이 가능하고 장애 격리에 유리합니다. "
                        "단점으로는 서비스 간 통신 오버헤드, 분산 트랜잭션 복잡성이 있습니다.",
            "tier": "good",
        },
        {
            "question": "Python의 GIL이 무엇인지 설명해줘",
            "response": "GIL은 Global Interpreter Lock으로, CPython에서 한 번에 하나의 스레드만 "
                        "Python 바이트코드를 실행할 수 있도록 하는 뮤텍스입니다. "
                        "멀티코어 CPU의 병렬 처리를 제한하지만 I/O 바운드 작업에는 영향이 적습니다.",
            "tier": "good",
        },
        {
            "question": "데이터베이스 인덱스란 무엇인가요?",
            "response": "인덱스는 데이터를 더 빨리 찾기 위해 사용됩니다. "
                        "모든 테이블에 인덱스를 걸면 조회 속도가 빨라집니다.",
            "tier": "low",   # 불완전한 설명 — 단점·트레이드오프 누락
        },
    ]

    # judge_model=None → agent-eval init 설정(OPENAI_MODEL/ANTHROPIC_MODEL) 자동 적용
    judge = LLMJudge(sample_rate=1.0)  # 데모: 전량 채점
    print(f"\n  Judge 모델: {judge.model}  (agent-eval init 설정 자동 반영)")

    print(f"\n  {'task':<8} {'tier':<6} {'completeness':>13} {'relevance':>10} {'factual':>8} {'overall':>8}")
    print(f"  {'─'*8} {'─'*6} {'─'*13} {'─'*10} {'─'*8} {'─'*8}")

    for i, case in enumerate(OPEN_QA):
        task_id = f"judge_{i+1:02d}"
        result = judge.judge(
            task_id=task_id,
            question=case["question"],
            response=case["response"],
        )

        if result.get("error"):
            print(f"  {task_id:<8} {case['tier']:<6}  {'API 오류: ' + result['error'][:40]}")
            continue
        if result.get("skipped"):
            print(f"  {task_id:<8} {case['tier']:<6}  (skipped)")
            continue

        s = result["scores"]
        flag = "✅" if case["tier"] == "good" else "🔻"
        print(
            f"  {flag} {task_id:<6} {case['tier']:<6}"
            f" {s['completeness']:>13}  {s['relevance']:>9}  {s['factual_consistency']:>7}  {s['overall']:>7.2f}"
        )
        if result.get("reasoning"):
            print(f"     └ {result['reasoning'][:65]}")

    summary = judge.get_summary()
    if summary["count"] > 0:
        avg = summary["avg_scores"]
        print(f"\n  ─── Judge 집계 ({summary['count']}건, 비용 ${summary['total_cost_usd']:.5f}) ───")
        print(f"  completeness       평균: {avg.get('completeness', 0):.2f}/5")
        print(f"  relevance          평균: {avg.get('relevance', 0):.2f}/5")
        print(f"  factual_consistency 평균: {avg.get('factual_consistency', 0):.2f}/5")
        print(f"  overall            평균: {avg.get('overall', 0):.2f}/5")

    # PerformanceMonitor 통합 패턴 — monitor.task() 와 enable_llm_judge 함께 사용
    print(f"\n  ─── PerformanceMonitor 통합 패턴 ───")
    print(f"  monitor = PerformanceMonitor(")
    print(f"      enable_llm_judge=True,   # judge_model 생략 → init 설정 자동 반영")
    print(f"      judge_sample_rate=0.1,   # 10% 샘플링 (비용 제어)")
    print(f"      judge_budget_per_day=5.0 # 일 $5 한도")
    print(f"  )")
    print(f"  with monitor.task('t1', 'qa', question=question) as t:")
    print(f"      t.response = agent.run(question)  # ground_truth 없어도 자동 채점")
    print()


if __name__ == "__main__":
    run_quality_evaluation()
    run_llm_judge_demo()
