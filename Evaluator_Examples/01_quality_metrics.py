"""
품질 지표 검증 예제 — Agent Evaluator
======================================

커버 지표 (품질 카테고리):
  Layer 1  │ Accuracy Evaluation        (QA / Code / General)
           │ Hallucination Detection    (Fact consistency)
           │ Response Quality           (6-dimension: relevance·completeness·accuracy·clarity·usefulness·safety)
  Layer 3  │ Ragas: Faithfulness · Answer Relevancy · Context Precision · Context Recall (시뮬레이션)

실행:
    python 01_quality_metrics.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta

# 프로젝트 루트 자동 감지
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent_evaluator import PerformanceMonitor, TaskResult

# ────────────────────────────────────────────────────────────────────────────────
# 시뮬레이션 데이터셋
# ────────────────────────────────────────────────────────────────────────────────

QA_DATASET = [
    {
        "q": "대한민국의 수도는 어디인가요?",
        "a": "대한민국의 수도는 서울입니다. 서울은 한강을 중심으로 발전한 도시로 경제·문화·정치의 중심지입니다.",
        "truth": "서울",
        "context": "대한민국은 동아시아에 위치한 국가입니다. 수도는 서울이며, 인구는 약 5,100만 명입니다.",
        "type": "qa",
    },
    {
        "q": "Python에서 리스트 컴프리헨션의 문법은 무엇인가요?",
        "a": "[표현식 for 변수 in 반복가능객체 if 조건] 형태로 작성합니다. 예: [x*2 for x in range(10) if x % 2 == 0]",
        "truth": "[expression for item in iterable if condition]",
        "context": "Python의 리스트 컴프리헨션은 간결하게 리스트를 생성하는 문법입니다.",
        "type": "qa",
    },
    {
        "q": "머신러닝에서 과적합(overfitting)이란 무엇인가요?",
        "a": "과적합이란 모델이 훈련 데이터에 지나치게 맞춰져 새로운 데이터에 대한 일반화 성능이 떨어지는 현상입니다. 드롭아웃, 정규화, 데이터 증강으로 방지할 수 있습니다.",
        "truth": "훈련 데이터에 지나치게 최적화되어 테스트 데이터 성능이 낮아지는 현상",
        "context": "머신러닝에서 모델 훈련 시 훈련 세트와 테스트 세트의 성능 차이가 크면 과적합이라고 합니다.",
        "type": "reasoning",
    },
    {
        "q": "HTTP와 HTTPS의 차이점을 설명하세요.",
        "a": "HTTP는 암호화되지 않은 통신 프로토콜이며, HTTPS는 SSL/TLS를 통해 암호화된 보안 통신 프로토콜입니다. HTTPS는 데이터 무결성과 기밀성을 보장합니다.",
        "truth": "HTTPS는 SSL/TLS 암호화를 사용하는 보안 HTTP",
        "context": "HTTP는 HyperText Transfer Protocol, HTTPS는 HTTP Secure의 약자입니다.",
        "type": "qa",
    },
    {
        "q": "SQL에서 JOIN의 종류를 나열하세요.",
        "a": "SQL JOIN의 종류: INNER JOIN(교집합), LEFT JOIN(왼쪽 전체+교집합), RIGHT JOIN(오른쪽 전체+교집합), FULL OUTER JOIN(합집합), CROSS JOIN(모든 조합)이 있습니다.",
        "truth": "INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN, CROSS JOIN",
        "context": "SQL의 JOIN은 두 테이블을 연결하는 연산입니다.",
        "type": "qa",
    },
    {
        "q": "도커(Docker)의 주요 장점은 무엇인가요?",
        "a": "Docker의 장점: 환경 일관성 보장, 빠른 배포, 리소스 효율성, 격리된 실행 환경, 버전 관리 용이성입니다.",
        "truth": "환경 일관성, 빠른 배포, 격리된 실행 환경",
        "context": "Docker는 컨테이너 기반 가상화 플랫폼입니다.",
        "type": "qa",
    },
    {
        "q": "RESTful API 설계 원칙을 설명하세요.",
        "a": "REST 원칙: 1) 무상태성(Stateless) 2) 클라이언트-서버 분리 3) 캐시 가능 4) 계층화된 시스템 5) 균일한 인터페이스 6) 코드 온 디맨드(선택적)",
        "truth": "무상태성, 클라이언트-서버 분리, 균일한 인터페이스 등",
        "context": "REST(Representational State Transfer)는 웹 API 설계 아키텍처 스타일입니다.",
        "type": "qa",
    },
    {
        "q": "비동기 프로그래밍에서 async/await의 역할은?",
        "a": "async는 함수를 코루틴으로 선언하고, await는 비동기 작업이 완료될 때까지 현재 코루틴의 실행을 일시 중단합니다. 이를 통해 I/O 바운드 작업을 효율적으로 처리합니다.",
        "truth": "async는 코루틴 선언, await는 비동기 작업 완료 대기",
        "context": "Python의 asyncio 라이브러리는 비동기 프로그래밍을 지원합니다.",
        "type": "qa",
    },
    {
        "q": "빅O 표기법에서 O(n log n)의 의미는?",
        "a": "O(n log n)은 입력 크기 n에 대해 n * log(n)에 비례하는 시간 복잡도입니다. 병합 정렬, 퀵 정렬(평균)이 이에 해당합니다.",
        "truth": "n * log(n)에 비례하는 시간 복잡도, 예: 병합 정렬",
        "context": "알고리즘의 시간 복잡도를 표현하는 빅O 표기법입니다.",
        "type": "reasoning",
    },
    {
        "q": "마이크로서비스 아키텍처의 단점은 무엇인가요?",
        "a": "마이크로서비스의 단점: 네트워크 오버헤드 증가, 분산 시스템 복잡성, 서비스 간 통신 관리 어려움, 데이터 일관성 유지 어려움, 운영 복잡도 증가",
        "truth": "네트워크 오버헤드, 분산 복잡성, 운영 복잡도 증가",
        "context": "마이크로서비스 아키텍처는 대규모 애플리케이션을 소규모 독립 서비스로 분리합니다.",
        "type": "reasoning",
    },
    # 할루시네이션 유발 케이스 (낮은 accuracy)
    {
        "q": "양자 컴퓨터는 현재 몇 큐비트까지 구현되었나요?",
        "a": "양자 컴퓨터는 현재 100만 큐비트까지 구현되었으며 모든 암호화를 해독할 수 있습니다.",
        "truth": "IBM 등이 1,000 큐비트 이상 달성, 실용적 양자 우위는 제한적",
        "context": "양자 컴퓨터는 양자역학적 현상을 이용하는 컴퓨터로, 2024년 기준 수천 큐비트 수준입니다.",
        "type": "qa",
        "has_hallucination": True,
    },
    {
        "q": "파이썬의 GIL이란 무엇인가요?",
        "a": "GIL(Global Interpreter Lock)은 파이썬에서 여러 네이티브 스레드가 동시에 파이썬 바이트코드를 실행하지 못하도록 하는 뮤텍스입니다.",
        "truth": "파이썬 인터프리터가 한 번에 하나의 스레드만 실행하도록 하는 잠금 메커니즘",
        "context": "CPython에는 GIL이 있어 멀티스레딩의 CPU 성능 향상이 제한됩니다.",
        "type": "qa",
    },
    {
        "q": "Kubernetes의 Pod란 무엇인가요?",
        "a": "Kubernetes Pod는 하나 이상의 컨테이너와 스토리지, 네트워크 리소스를 포함하는 가장 작은 배포 단위입니다.",
        "truth": "하나 이상의 컨테이너를 포함하는 Kubernetes의 최소 배포 단위",
        "context": "Kubernetes는 컨테이너 오케스트레이션 플랫폼입니다.",
        "type": "qa",
    },
    {
        "q": "GraphQL과 REST API의 주요 차이점은?",
        "a": "GraphQL은 클라이언트가 필요한 데이터 구조를 직접 정의하여 요청하는 쿼리 언어입니다. REST는 서버가 정한 엔드포인트 구조를 따르지만, GraphQL은 단일 엔드포인트에서 유연한 쿼리가 가능합니다.",
        "truth": "GraphQL은 단일 엔드포인트, 클라이언트 주도 데이터 선택 vs REST는 다중 엔드포인트",
        "context": "GraphQL은 Facebook이 개발한 API 쿼리 언어입니다.",
        "type": "reasoning",
    },
    {
        "q": "CI/CD 파이프라인의 구성 요소를 설명하세요.",
        "a": "CI/CD는 지속적 통합(Continuous Integration)과 지속적 배포(Continuous Delivery/Deployment)의 조합입니다. 구성요소: 소스 제어, 빌드, 테스트, 스테이징, 프로덕션 배포",
        "truth": "빌드, 테스트, 배포 단계로 구성된 자동화 파이프라인",
        "context": "CI/CD는 소프트웨어 개발 주기를 자동화하는 방법론입니다.",
        "type": "qa",
    },
    # 낮은 품질 응답 케이스
    {
        "q": "딥러닝에서 배치 정규화(Batch Normalization)의 효과는?",
        "a": "배치 정규화는 좋습니다.",
        "truth": "학습 속도 향상, 그래디언트 소실 완화, 정규화 효과",
        "context": "Batch Normalization은 각 레이어의 입력을 정규화하여 학습을 안정화합니다.",
        "type": "reasoning",
        "low_quality": True,
    },
    {
        "q": "Git의 rebase와 merge의 차이점은?",
        "a": "rebase는 커밋 히스토리를 선형으로 재작성하여 깔끔한 히스토리를 만들고, merge는 두 브랜치를 합치면서 병합 커밋을 생성합니다. rebase는 협업 시 주의가 필요합니다.",
        "truth": "rebase는 선형 히스토리, merge는 병합 커밋 포함 히스토리",
        "context": "Git의 브랜치 통합 전략입니다.",
        "type": "qa",
    },
    {
        "q": "트랜잭션 ACID 속성을 설명하세요.",
        "a": "ACID: Atomicity(원자성)-전부 실행 또는 전부 롤백, Consistency(일관성)-규칙 준수, Isolation(격리성)-동시 트랜잭션 간 간섭 없음, Durability(지속성)-커밋 후 영구 보존",
        "truth": "Atomicity, Consistency, Isolation, Durability",
        "context": "데이터베이스 트랜잭션의 신뢰성을 보장하는 4가지 속성입니다.",
        "type": "qa",
    },
    {
        "q": "신경망에서 드롭아웃(Dropout)의 역할은?",
        "a": "드롭아웃은 학습 중 랜덤하게 뉴런을 비활성화하여 과적합을 방지합니다. 앙상블 효과를 제공하고 모델의 일반화 능력을 향상시킵니다.",
        "truth": "랜덤 뉴런 비활성화를 통한 과적합 방지 및 일반화 향상",
        "context": "Dropout은 Hinton et al.이 제안한 정규화 기법입니다.",
        "type": "qa",
    },
    {
        "q": "캐시 메모리와 RAM의 차이점은?",
        "a": "캐시 메모리는 CPU 근처에 있는 소용량 고속 메모리로 자주 사용되는 데이터를 저장합니다. RAM은 대용량이지만 캐시보다 느립니다. L1/L2/L3 캐시 계층 구조가 있습니다.",
        "truth": "캐시는 소용량 고속, RAM은 대용량 저속",
        "context": "컴퓨터 메모리 계층 구조에서 캐시는 CPU와 RAM 사이에 위치합니다.",
        "type": "qa",
    },
    # 추가 다양한 타입
    {
        "q": "자연어 처리(NLP)에서 토크나이저의 역할은?",
        "a": "토크나이저는 텍스트를 토큰(단어, 서브워드, 문자 등)으로 분리하는 과정입니다. BPE, WordPiece, SentencePiece 등 다양한 방식이 있습니다.",
        "truth": "텍스트를 작은 단위(토큰)로 분리하는 도구",
        "context": "NLP 모델 학습 전처리 단계에서 텍스트를 토큰으로 변환합니다.",
        "type": "information_retrieval",
    },
    {
        "q": "클라우드 컴퓨팅의 IaaS, PaaS, SaaS의 차이는?",
        "a": "IaaS(인프라): 가상 서버·스토리지·네트워크 제공 (AWS EC2). PaaS(플랫폼): 개발 환경 및 미들웨어 제공 (Heroku). SaaS(소프트웨어): 완성된 앱 제공 (Gmail, Salesforce)",
        "truth": "IaaS는 인프라, PaaS는 플랫폼, SaaS는 완성 소프트웨어 제공",
        "context": "클라우드 서비스 모델의 세 가지 유형입니다.",
        "type": "qa",
    },
    {
        "q": "해시 테이블의 충돌 해결 방법은?",
        "a": "충돌 해결: 1) 체이닝(Chaining) - 연결 리스트로 처리 2) 오픈 어드레싱(Open Addressing) - 선형 탐사, 이차 탐사, 이중 해싱",
        "truth": "체이닝과 오픈 어드레싱(선형 탐사 등)",
        "context": "해시 테이블에서 서로 다른 키가 같은 해시값을 가질 때 발생하는 충돌을 처리합니다.",
        "type": "qa",
    },
    {
        "q": "AI에서 강화학습의 핵심 요소는?",
        "a": "강화학습의 핵심: 에이전트(Agent), 환경(Environment), 상태(State), 행동(Action), 보상(Reward), 정책(Policy), 가치 함수(Value Function)",
        "truth": "에이전트, 환경, 상태, 행동, 보상",
        "context": "강화학습은 에이전트가 환경과 상호작용하며 누적 보상을 최대화하도록 학습합니다.",
        "type": "reasoning",
    },
    {
        "q": "서버리스(Serverless) 아키텍처의 장단점은?",
        "a": "장점: 인프라 관리 불필요, 자동 확장, 사용량 기반 비용. 단점: 콜드 스타트 지연, 상태 관리 어려움, 벤더 종속, 디버깅 어려움",
        "truth": "자동 확장과 비용 효율이 장점, 콜드 스타트와 벤더 종속이 단점",
        "context": "서버리스는 서버 관리 없이 함수 단위로 실행되는 클라우드 모델입니다.",
        "type": "reasoning",
    },
]

CONTEXTS = {
    "rag_faithfulness": [
        "에이전트 평가 프레임워크는 태스크 완료율, 정확도, 할루시네이션 탐지 등을 측정합니다.",
        "LLM 기반 애플리케이션에서 RAG 시스템은 검색된 문서를 기반으로 답변을 생성합니다.",
        "보안 평가에는 프롬프트 인젝션, SQL 인젝션, 권한 상승 탐지가 포함됩니다.",
        "Layer 1 메트릭은 외부 의존성 없이 알고리즘 기반으로 계산됩니다.",
        "DeepEval과 Ragas는 LLM 기반 평가 지표를 제공하는 외부 라이브러리입니다.",
    ]
}


def run_quality_evaluation():
    print("\n" + "=" * 70)
    print("  품질 지표 평가 — Agent Evaluator")
    print("  Coverage: Accuracy · Hallucination · Response Quality · RAG Metrics")
    print("=" * 70)

    random.seed(42)

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        enable_transparency=True,
        output_dir=str(project_root / "results"),
    )

    base_time = datetime.now() - timedelta(hours=2)
    task_count = 0

    for i, item in enumerate(QA_DATASET):
        task_id = f"quality_{i+1:03d}"
        task_type = item["type"]
        has_hallucination = item.get("has_hallucination", False)
        low_quality = item.get("low_quality", False)

        # 정확도 시뮬레이션
        if has_hallucination:
            accuracy = random.uniform(0.15, 0.30)
            completion = random.uniform(0.3, 0.5)
            success = False
        elif low_quality:
            accuracy = random.uniform(0.35, 0.50)
            completion = random.uniform(0.4, 0.6)
            success = False
        else:
            accuracy = random.uniform(0.72, 0.97)
            completion = random.uniform(0.75, 1.0)
            success = True

        exec_time = random.uniform(0.8, 3.5)
        input_tokens = random.randint(80, 400)
        output_tokens = random.randint(60, 350)

        task = TaskResult(
            task_id=task_id,
            task_type=task_type,
            success=success,
            completion_score=round(completion, 3),
            accuracy_score=round(accuracy, 3),
            execution_time=exec_time,
            tokens_used={"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens},
            tool_calls=[],
            attempts=1,
            errors=[] if success else ["accuracy_below_threshold"],
            timestamp=base_time + timedelta(minutes=i * 3),
            framework="native",
        )

        # record_task: hallucination detection 포함
        context_text = item.get("context", " ".join(CONTEXTS["rag_faithfulness"]))
        monitor.record_task(
            task,
            ground_truth=item["truth"],
            context=context_text,
            request=item["q"],
            response=item["a"],
            expected_elements=item["truth"].split("·") if "·" in item["truth"] else [item["truth"]],
        )

        # Response quality 평가 (6-dimension)
        monitor.quality_evaluator.evaluate_response(
            task_id=task_id,
            response=item["a"],
            request=item["q"],
            expected_elements=item["truth"].split() if not low_quality else [],
            ground_truth=item["truth"],
        )

        # RAG 메트릭 시뮬레이션 (Layer 3 Ragas 대체)
        if task_type in ("qa", "information_retrieval") and not has_hallucination:
            monitor.record_rag_metrics(
                faithfulness=round(random.uniform(0.70, 0.95), 3),
                answer_relevancy=round(random.uniform(0.72, 0.96), 3),
                context_precision=round(random.uniform(0.65, 0.92), 3),
                context_recall=round(random.uniform(0.68, 0.94), 3),
            )
        elif has_hallucination:
            monitor.record_rag_metrics(
                faithfulness=round(random.uniform(0.10, 0.35), 3),
                answer_relevancy=round(random.uniform(0.15, 0.40), 3),
                context_precision=round(random.uniform(0.20, 0.45), 3),
                context_recall=round(random.uniform(0.10, 0.30), 3),
            )

        task_count += 1

    # 코드 정확도 테스트 (CODE_GENERATION 타입)
    code_cases = [
        {
            "task_id": "quality_code_001",
            "expected": "def sum_list(lst):\n    return sum(lst)",
            "actual": "def sum_list(items):\n    total = 0\n    for x in items:\n        total += x\n    return total",
            "accuracy": 0.85,
        },
        {
            "task_id": "quality_code_002",
            "expected": "sorted(lst, key=lambda x: x['score'], reverse=True)",
            "actual": "sorted(lst, key=lambda x: x['score'], reverse=True)",
            "accuracy": 1.0,
        },
        {
            "task_id": "quality_code_003",
            "expected": "for i in range(n): result.append(i**2)",
            "actual": "result = [x for x in range(n)]",
            "accuracy": 0.45,
        },
        {
            "task_id": "quality_code_004",
            "expected": "with open('file.txt', 'r') as f: data = f.read()",
            "actual": "with open('file.txt', 'r') as f:\n    data = f.read()\nprint(data)",
            "accuracy": 0.88,
        },
        {
            "task_id": "quality_code_005",
            "expected": "import pandas as pd\ndf = pd.read_csv('data.csv')",
            "actual": "import numpy as np",
            "accuracy": 0.20,
        },
    ]

    for cc in code_cases:
        code_task = TaskResult(
            task_id=cc["task_id"],
            task_type="code_generation",
            success=cc["accuracy"] >= 0.7,
            completion_score=cc["accuracy"],
            accuracy_score=cc["accuracy"],
            execution_time=random.uniform(1.5, 5.0),
            tokens_used={"input": random.randint(100, 300), "output": random.randint(50, 200), "total": 0},
            tool_calls=[],
            attempts=1 if cc["accuracy"] > 0.5 else 2,
            errors=[] if cc["accuracy"] >= 0.7 else ["code_mismatch"],
            timestamp=base_time + timedelta(hours=1),
            framework="langchain",
        )
        code_task.tokens_used["total"] = code_task.tokens_used["input"] + code_task.tokens_used["output"]

        monitor.record_task(
            code_task,
            ground_truth=cc["expected"],
            request=f"다음 코드를 작성하세요: {cc['expected'][:50]}",
            response=cc["actual"],
            expected_elements=[],
        )
        monitor.quality_evaluator.evaluate_response(
            task_id=cc["task_id"],
            response=cc["actual"],
            request=f"코드를 작성하세요",
            expected_elements=[],
            ground_truth=cc["expected"],
        )
        task_count += 1

    # 리포트 저장
    report = monitor.generate_report()
    filename = f"[Q]_quality_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    saved_path = monitor.save_to_file(filename)

    # 결과 요약 출력
    accuracy_data = report.accuracy_metrics.get("accuracy_scores", {})
    quality_data = report.accuracy_metrics.get("quality", {})
    hallucination_data = report.accuracy_metrics.get("hallucination", {})
    rag_data = monitor.get_rag_metrics_summary()

    print(f"\n{'─'*70}")
    print(f"  총 평가 태스크: {report.total_tasks}개")
    print(f"  저장 위치: {saved_path}")
    print(f"\n  [Accuracy]")
    print(f"    평균 정확도: {accuracy_data.get('overall_accuracy', 0):.1f}%")
    print(f"    중간값:      {accuracy_data.get('median_accuracy', 0):.1f}%")

    print(f"\n  [Response Quality — 6 Dimensions]")
    dim_scores = quality_data.get("dimension_scores", quality_data.get("dimension_averages", {}))
    for dim in ["relevance", "completeness", "accuracy", "clarity", "usefulness"]:
        score = dim_scores.get(dim, 0)
        print(f"    {dim:<15}: {score:.2f}/5.0")
    print(f"    avg_total:      {quality_data.get('avg_total_score', 0):.2f}/5.0")

    print(f"\n  [Hallucination Detection]")
    print(f"    탐지율:      {hallucination_data.get('overall_rate', 0):.1f}%")
    print(f"    무근거 주장: {hallucination_data.get('unsupported_claims_count', 0)}건")

    print(f"\n  [RAG Metrics — Simulated Layer 3]")
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        val = rag_data.get(metric, {}).get("mean", 0)
        print(f"    {metric:<22}: {val:.3f}")

    if report.alerts:
        print(f"\n  [Alerts — {len(report.alerts)}건]")
        for a in report.alerts[:3]:
            print(f"    [{a['severity'].upper()}] {a['metric']}")

    print(f"{'─'*70}\n")
    return saved_path


def run_golden_dataset_demo():
    """
    Golden Dataset 파일 기반 자동 평가 데모
    ─────────────────────────────────────────
    results/golden_datasets/quality_tech_qa.json 을 로드하고
    PerformanceMonitor.evaluate_with_golden_dataset() 파이프라인을 시연합니다.

    실제 에이전트 연동 시에는 simulated_agent() 대신
    LLM API 호출 함수를 전달하면 됩니다.
    """
    print("\n" + "=" * 70)
    print("  Golden Dataset 기반 자동 평가 데모")
    print("  파일: results/golden_datasets/quality_tech_qa.json")
    print("=" * 70)

    golden_path = project_root / "results" / "golden_datasets" / "quality_tech_qa.json"
    if not golden_path.exists():
        print(f"\n⚠️  Golden Dataset 파일이 없습니다: {golden_path}")
        print("   먼저 01_quality_metrics.py 를 한 번 실행하여 파일을 생성하세요.")
        return

    # 시뮬레이션 에이전트 — QA_DATASET 응답을 조회 반환
    _qa_lookup = {item["q"]: item["a"] for item in QA_DATASET}

    def simulated_agent(question: str) -> dict:
        """실제 에이전트 함수 자리 — LLM API 호출로 교체 가능"""
        answer = _qa_lookup.get(question, "관련 정보를 찾을 수 없습니다.")
        return {
            "answer": answer,
            "tools_used": ["web_search"] if "검색" in question else [],
            "latency": random.uniform(0.5, 2.0),
            "token_usage": {
                "input": random.randint(50, 200),
                "output": random.randint(40, 150),
                "total": 0,
            },
        }

    monitor = PerformanceMonitor(
        enable_hallucination_detection=True,
        enable_transparency=True,
        output_dir=str(project_root / "results"),
    )

    results = monitor.evaluate_with_golden_dataset(
        agent_fn=simulated_agent,
        dataset_path=str(golden_path),
        enable_layer2_metrics=False,   # tool selection 평가 비활성 (QA 전용 데이터셋)
        enable_advanced_metrics=False,
        verbose=True,
    )

    if "error" not in results:
        print(f"\n{'─'*70}")
        print(f"  [Golden Dataset 평가 결과]")
        print(f"  총 평가: {results.get('total_evaluated', 0)}건")
        l1 = results.get("layer1_metrics", {})
        accuracy_val = l1.get("accuracy", 0)
        print(f"  평균 정확도: {accuracy_val:.1f}%")
        pf = results.get("pass_fail", {})
        if pf:
            print(f"  Pass:  {pf.get('pass', 0)}건  Fail: {pf.get('fail', 0)}건")
        print(f"{'─'*70}\n")
    else:
        print(f"\n❌ 평가 실패: {results['error']}\n")


if __name__ == "__main__":
    run_quality_evaluation()
    run_golden_dataset_demo()
