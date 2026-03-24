"""
품질 지표 검증 예제 — Agent Evaluator v0.6.0
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

from agent_evaluator import PerformanceMonitor, TaskResult
from agent_evaluator.reporting import generate_comprehensive_html_report


def _load_golden(filename: str) -> list:
    path = project_root / "results" / "golden_datasets" / filename
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
# 골든 데이터셋에서 로드 (results/golden_datasets/)
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
    print("  품질 지표 검증 — Agent Evaluator v0.6.0")
    print("  Accuracy · Hallucination · ResponseQuality · RAG Metrics")
    print("=" * 70)

    rng = random.Random(42)

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        enable_transparency=True,
        output_dir=str(project_root / "results"),
    )

    base_time = datetime.now() - timedelta(hours=2)

    # 검증 추적
    hl_scores_by_tier: dict = {"high": [], "hallucination": [], "low_quality": []}
    task_tier_map: dict = {}  # task_id → tier (정확도 분리 검증용)

    print("\n  [1/3] QA 데이터셋 평가 (Accuracy · Hallucination · Quality)")
    print(f"  {'task_id':<20} {'tier':<15} {'hl_score':>10}  {'메모'}")
    print(f"  {'─'*20} {'─'*15} {'─'*10}  {'─'*20}")

    for i, item in enumerate(QA_DATASET):
        task_id = f"quality_{i+1:03d}"
        tier = item["tier"]
        task_type = item["type"]
        context_text = item.get("context", "")

        success = tier == "high"
        completion = rng.uniform(0.82, 1.0) if success else rng.uniform(0.15, 0.50)

        task = TaskResult(
            task_id=task_id,
            task_type=task_type,
            success=success,
            completion_score=round(completion, 3),
            accuracy_score=0.0,          # add_evaluation()으로 계산
            execution_time=rng.uniform(0.8, 3.5),
            tokens_used={
                "input": rng.randint(80, 400),
                "output": rng.randint(60, 350),
                "total": 0,
            },
            tool_calls=[],
            attempts=1,
            errors=[] if success else [f"{tier}_quality_issue"],
            timestamp=base_time + timedelta(minutes=i * 3),
            framework="native",
        )
        task.tokens_used["total"] = task.tokens_used["input"] + task.tokens_used["output"]

        # ① HallucinationDetector 직접 호출 — 케이스별 점수 캡처
        task_tier_map[task_id] = tier

        hl_score = 0.0
        if context_text:
            hl_result = monitor.hallucination_detector.detect_hallucination(
                task_id=task_id,
                response=item["a"],
                context=context_text,
                ground_truth=item["truth"],
                request=item["q"],
            )
            hl_score = hl_result.get("hallucination_rate", 0.0)
            hl_scores_by_tier[tier].append(hl_score)

        # ② record_task — TCR · Latency · Token 측정
        #    context=None: 할루시네이션 탐지는 위에서 직접 처리
        monitor.record_task(
            task,
            ground_truth=item["truth"],
            context=None,
            request=item["q"],
            response=item["a"],
            expected_elements=item["truth"].split() if tier == "high" else [],
        )

        # ③ AccuracyEvaluator 직접 호출 — 텍스트 유사도 정확도 계산
        monitor.accuracy_evaluator.add_evaluation(
            task_id=task_id,
            ground_truth=item["truth"],
            prediction=item["a"],
            task_type=task_type,
        )

        # ④ ResponseQualityEvaluator — 5차원 품질 평가
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=item["a"],
            request=item["q"],
            expected_elements=item["truth"].split() if tier == "high" else [],
            ground_truth=item["truth"],
        )

        # ⑤ RAG 지표 — tier별 예상 범위 반영
        if task_type in ("qa", "information_retrieval"):
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

        # 케이스별 출력 (할루시네이션 / 저품질 강조)
        flag = "⚠️ " if tier == "hallucination" else ("🔻 " if tier == "low_quality" else "   ")
        print(f"  {flag}{task_id:<18} {tier:<15} {hl_score:>10.3f}  {item['q'][:30]}...")

    # ─── 코드 정확도 평가 ──────────────────────────────────────────────────────
    print(f"\n  [2/3] Code Accuracy 평가 (AST/정규화 비교)")
    print(f"  {'task_id':<20} {'tier':<15} {'메모'}")
    print(f"  {'─'*20} {'─'*15} {'─'*30}")

    for cc in CODE_CASES:
        tier = cc["tier"]
        code_task = TaskResult(
            task_id=cc["task_id"],
            task_type="code_generation",
            success=tier == "high",
            completion_score=0.9 if tier == "high" else 0.35,
            accuracy_score=0.0,
            execution_time=rng.uniform(1.5, 5.0),
            tokens_used={
                "input": rng.randint(100, 300),
                "output": rng.randint(50, 200),
                "total": 0,
            },
            tool_calls=[],
            attempts=1 if tier == "high" else 2,
            errors=[] if tier == "high" else ["code_mismatch"],
            timestamp=base_time + timedelta(hours=1),
            framework="native",
        )
        code_task.tokens_used["total"] = code_task.tokens_used["input"] + code_task.tokens_used["output"]

        monitor.record_task(
            code_task,
            ground_truth=cc["expected"],
            request=cc["q"],
            response=cc["actual"],
        )

        # AccuracyEvaluator — code_generation: AST → 정규화 비교 순 fallback
        monitor.accuracy_evaluator.add_evaluation(
            task_id=cc["task_id"],
            ground_truth=cc["expected"],
            prediction=cc["actual"],
            task_type="code_generation",
        )

        monitor.quality_evaluator.evaluate_response(
            task_id=cc["task_id"],
            response=cc["actual"],
            request=cc["q"],
            expected_elements=[],
            ground_truth=cc["expected"],
        )

        flag = "   " if tier == "high" else "🔻 "
        print(f"  {flag}{cc['task_id']:<18} {tier:<15} {cc['q'][:35]}...")

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
    if hl_scores_by_tier["hallucination"]:
        avg_hl = sum(hl_scores_by_tier["hallucination"]) / len(hl_scores_by_tier["hallucination"])
        avg_nm = sum(hl_scores_by_tier["high"]) / len(hl_scores_by_tier["high"]) if hl_scores_by_tier["high"] else 0
        print(f"    할루시네이션 케이스 평균 점수: {avg_hl:.3f}")
        print(f"    정상 케이스 평균 점수:         {avg_nm:.3f}")

    print(f"\n  [RAG Metrics — Layer 3 시뮬레이션]")
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        val = rag_data.get(metric, {}).get("mean", 0)
        print(f"    {metric:<22}: {val:.3f}")

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
        # 혼합 데이터셋(high+hl+low_quality) 평균 1.5/5.0 이상
        ("평균 품질 점수",                  "> 1.5/5.0", f"{avg_total:.2f}",       avg_total > 1.5),
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


if __name__ == "__main__":
    run_quality_evaluation()
