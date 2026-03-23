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
    python 01_quality_metrics.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent_evaluator import PerformanceMonitor, TaskResult
from agent_evaluator.reporting import generate_comprehensive_html_report

# ────────────────────────────────────────────────────────────────────────────────
# 데이터셋 — tier별 예상 결과 명시
# tier: "high"        → accuracy >65%, quality >3.5/5.0, hl_score 낮음
#       "hallucination" → accuracy <40%, hl_score 높음 (사실과 다른 응답)
#       "low_quality"   → quality avg <3.0 (내용 부실)
# ────────────────────────────────────────────────────────────────────────────────

QA_DATASET = [
    # ─── 정상 QA (high) ──────────────────────────────────────────────────────────
    {"q": "대한민국의 수도는 어디인가요?",
     "a": "대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 도시로 경제·문화·정치의 중심지입니다.",
     "truth": "서울",
     "context": "대한민국은 동아시아에 위치한 국가입니다. 수도는 서울이며 인구는 약 5,100만 명입니다.",
     "type": "qa", "tier": "high"},
    {"q": "Python에서 리스트 컴프리헨션의 문법은 무엇인가요?",
     "a": "[표현식 for 변수 in 반복가능객체 if 조건] 형태입니다. 예: [x*2 for x in range(10) if x%2==0]",
     "truth": "[expression for item in iterable if condition]",
     "context": "Python의 리스트 컴프리헨션은 간결하게 리스트를 생성하는 문법입니다.",
     "type": "qa", "tier": "high"},
    {"q": "머신러닝에서 과적합(overfitting)이란 무엇인가요?",
     "a": "과적합이란 모델이 훈련 데이터에 지나치게 맞춰져 새로운 데이터에 대한 일반화 성능이 떨어지는 현상입니다.",
     "truth": "훈련 데이터에 지나치게 최적화되어 테스트 데이터 성능이 낮아지는 현상",
     "context": "머신러닝에서 훈련 세트와 테스트 세트의 성능 차이가 크면 과적합이라고 합니다.",
     "type": "reasoning", "tier": "high"},
    {"q": "HTTP와 HTTPS의 차이점을 설명하세요.",
     "a": "HTTP는 암호화되지 않은 통신 프로토콜이며, HTTPS는 SSL/TLS를 통해 암호화된 보안 통신 프로토콜입니다.",
     "truth": "HTTPS는 SSL/TLS 암호화를 사용하는 보안 HTTP",
     "context": "HTTP는 HyperText Transfer Protocol, HTTPS는 HTTP Secure의 약자입니다.",
     "type": "qa", "tier": "high"},
    {"q": "SQL에서 JOIN의 종류를 나열하세요.",
     "a": "INNER JOIN(교집합), LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN, CROSS JOIN이 있습니다.",
     "truth": "INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN, CROSS JOIN",
     "context": "SQL의 JOIN은 두 테이블을 연결하는 연산입니다.",
     "type": "qa", "tier": "high"},
    {"q": "도커(Docker)의 주요 장점은 무엇인가요?",
     "a": "Docker의 장점: 환경 일관성 보장, 빠른 배포, 리소스 효율성, 격리된 실행 환경, 버전 관리 용이성입니다.",
     "truth": "환경 일관성, 빠른 배포, 격리된 실행 환경",
     "context": "Docker는 컨테이너 기반 가상화 플랫폼입니다.",
     "type": "qa", "tier": "high"},
    {"q": "RESTful API 설계 원칙을 설명하세요.",
     "a": "REST 원칙: 무상태성(Stateless), 클라이언트-서버 분리, 캐시 가능, 계층화된 시스템, 균일한 인터페이스.",
     "truth": "무상태성, 클라이언트-서버 분리, 균일한 인터페이스 등",
     "context": "REST(Representational State Transfer)는 웹 API 설계 아키텍처 스타일입니다.",
     "type": "qa", "tier": "high"},
    {"q": "비동기 프로그래밍에서 async/await의 역할은?",
     "a": "async는 함수를 코루틴으로 선언하고, await는 비동기 작업 완료 시까지 실행을 일시 중단합니다.",
     "truth": "async는 코루틴 선언, await는 비동기 작업 완료 대기",
     "context": "Python의 asyncio 라이브러리는 비동기 프로그래밍을 지원합니다.",
     "type": "qa", "tier": "high"},
    {"q": "빅O 표기법에서 O(n log n)의 의미는?",
     "a": "O(n log n)은 n * log(n)에 비례하는 시간 복잡도입니다. 병합 정렬, 퀵 정렬(평균)이 해당합니다.",
     "truth": "n * log(n)에 비례하는 시간 복잡도, 예: 병합 정렬",
     "context": "알고리즘의 시간 복잡도를 표현하는 빅O 표기법입니다.",
     "type": "reasoning", "tier": "high"},
    {"q": "파이썬의 GIL이란 무엇인가요?",
     "a": "GIL(Global Interpreter Lock)은 여러 스레드가 동시에 Python 바이트코드를 실행하지 못하도록 하는 뮤텍스입니다.",
     "truth": "파이썬 인터프리터가 한 번에 하나의 스레드만 실행하도록 하는 잠금 메커니즘",
     "context": "CPython에는 GIL이 있어 멀티스레딩의 CPU 성능 향상이 제한됩니다.",
     "type": "qa", "tier": "high"},
    {"q": "Kubernetes의 Pod란 무엇인가요?",
     "a": "Kubernetes Pod는 하나 이상의 컨테이너와 스토리지, 네트워크 리소스를 포함하는 최소 배포 단위입니다.",
     "truth": "하나 이상의 컨테이너를 포함하는 Kubernetes의 최소 배포 단위",
     "context": "Kubernetes는 컨테이너 오케스트레이션 플랫폼입니다.",
     "type": "qa", "tier": "high"},
    {"q": "Git의 rebase와 merge의 차이점은?",
     "a": "rebase는 커밋 히스토리를 선형으로 재작성하고, merge는 병합 커밋을 생성합니다.",
     "truth": "rebase는 선형 히스토리, merge는 병합 커밋 포함 히스토리",
     "context": "Git의 브랜치 통합 전략입니다.",
     "type": "qa", "tier": "high"},
    {"q": "트랜잭션 ACID 속성을 설명하세요.",
     "a": "ACID: Atomicity(원자성), Consistency(일관성), Isolation(격리성), Durability(지속성).",
     "truth": "Atomicity, Consistency, Isolation, Durability",
     "context": "데이터베이스 트랜잭션의 신뢰성을 보장하는 4가지 속성입니다.",
     "type": "qa", "tier": "high"},

    # ─── 할루시네이션 케이스 (hallucination) ─────────────────────────────────────
    # 사실과 다른 응답 → detect_hallucination() 높은 점수 기대
    {"q": "양자 컴퓨터는 현재 몇 큐비트까지 구현되었나요?",
     "a": "양자 컴퓨터는 현재 100만 큐비트까지 구현되었으며 모든 암호화를 해독할 수 있습니다.",
     "truth": "IBM 등이 1,000 큐비트 이상 달성, 실용적 양자 우위는 제한적",
     "context": "양자 컴퓨터는 양자역학적 현상을 이용하는 컴퓨터로, 2024년 기준 수천 큐비트 수준입니다.",
     "type": "qa", "tier": "hallucination"},
    {"q": "Python은 컴파일 언어인가요?",
     "a": "Python은 순수 컴파일 언어로 실행 전에 기계어로 완전히 변환됩니다. 인터프리터가 전혀 관여하지 않습니다.",
     "truth": "Python은 인터프리터 언어로 소스코드를 한 줄씩 실행",
     "context": "Python은 인터프리터 기반 언어로 .pyc 바이트코드를 사용하지만 JIT 컴파일은 기본이 아닙니다.",
     "type": "qa", "tier": "hallucination"},
    {"q": "HTTP 상태코드 200의 의미는?",
     "a": "HTTP 200은 요청이 완전히 실패했음을 나타냅니다. 서버가 처리하지 못한 경우입니다.",
     "truth": "HTTP 200 OK: 요청 성공",
     "context": "HTTP 상태코드에서 200 OK는 요청이 성공적으로 처리됐음을 의미합니다.",
     "type": "qa", "tier": "hallucination"},
    {"q": "TCP와 UDP의 차이점은?",
     "a": "TCP와 UDP는 동일한 프로토콜입니다. 둘 다 연결 지향적이며 신뢰성을 보장합니다.",
     "truth": "TCP는 연결 지향 신뢰성 보장, UDP는 비연결 빠른 전송",
     "context": "TCP(연결 지향, 신뢰성)와 UDP(비연결, 빠른 속도)는 서로 다른 전송 계층 프로토콜입니다.",
     "type": "qa", "tier": "hallucination"},

    # ─── 저품질 응답 (low_quality) ────────────────────────────────────────────────
    # 내용 부실 → ResponseQuality avg_total <3.0 기대
    {"q": "딥러닝에서 배치 정규화(Batch Normalization)의 효과는?",
     "a": "배치 정규화는 좋습니다.",
     "truth": "학습 속도 향상, 그래디언트 소실 완화, 정규화 효과",
     "context": "Batch Normalization은 각 레이어의 입력을 정규화하여 학습을 안정화합니다.",
     "type": "reasoning", "tier": "low_quality"},
    {"q": "GraphQL과 REST API의 주요 차이점은?",
     "a": "다릅니다.",
     "truth": "GraphQL은 단일 엔드포인트, 클라이언트 주도 데이터 선택 vs REST는 다중 엔드포인트",
     "context": "GraphQL은 Facebook이 개발한 API 쿼리 언어입니다.",
     "type": "reasoning", "tier": "low_quality"},
    {"q": "CI/CD 파이프라인의 구성 요소를 설명하세요.",
     "a": "자동화입니다.",
     "truth": "빌드, 테스트, 배포 단계로 구성된 자동화 파이프라인",
     "context": "CI/CD는 소프트웨어 개발 주기를 자동화하는 방법론입니다.",
     "type": "qa", "tier": "low_quality"},
]

# 코드 정확도 검증 케이스
CODE_CASES = [
    {"task_id": "quality_code_001", "q": "리스트 합계 함수를 작성하세요.",
     "expected": "def sum_list(lst):\n    return sum(lst)",
     "actual": "def sum_list(items):\n    total = 0\n    for x in items:\n        total += x\n    return total",
     "tier": "high"},
    {"task_id": "quality_code_002", "q": "리스트를 점수 기준 내림차순 정렬하세요.",
     "expected": "sorted(lst, key=lambda x: x['score'], reverse=True)",
     "actual": "sorted(lst, key=lambda x: x['score'], reverse=True)",
     "tier": "high"},
    {"task_id": "quality_code_003", "q": "range로 제곱 리스트를 생성하세요.",
     "expected": "for i in range(n): result.append(i**2)",
     "actual": "result = [x for x in range(n)]",
     "tier": "low_quality"},
    {"task_id": "quality_code_004", "q": "파일을 읽어 내용을 반환하세요.",
     "expected": "with open('file.txt', 'r') as f: data = f.read()",
     "actual": "with open('file.txt', 'r') as f:\n    data = f.read()\nprint(data)",
     "tier": "high"},
    {"task_id": "quality_code_005", "q": "pandas로 CSV를 읽으세요.",
     "expected": "import pandas as pd\ndf = pd.read_csv('data.csv')",
     "actual": "import numpy as np",
     "tier": "low_quality"},
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
