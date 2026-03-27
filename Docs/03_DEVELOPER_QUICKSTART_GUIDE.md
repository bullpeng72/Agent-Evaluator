# 🚀 초급 개발자 개발 가이드

Agent Evaluator를 5분 안에 시작하기

# 초급 개발자 개발 가이드

## 1\. 시작하기 전에

### 🎯 이 가이드의 목표

이 가이드는 **AI Agent 개발이 처음인 분들** 을 위해 작성되었습니다. 다음을 배우게 됩니다:

  * Agent Evaluator 설치 및 기본 사용법
  * Agent 성능을 측정하는 방법
  * Golden Dataset을 활용한 자동 평가
  * 메트릭 해석 및 개선 방향 찾기
  * 실전 프로젝트에 적용하는 방법

### 📋 준비물

항목 | 필수/선택 | 설명  
---|---|---  
Python 3.8+ | ✅ 필수 | Python 3.11 권장  
OpenAI API Key | ⚠️ 선택 | Layer 3 고급 메트릭 사용 시 필요 (Layer 1만 사용 시 불필요)  
기본적인 Python 지식 | ✅ 필수 | 함수, 클래스, 딕셔너리 정도  
AI Agent 코드 | ✅ 필수 | 평가할 Agent 함수  
  
💡 OpenAI API Key가 없어도 됩니다!

**Layer 1 메트릭**(TCR, Accuracy, Latency, Cost 등)은 완전히 무료이며 API 키가 필요 없습니다. 고급 AI 평가(DeepEval, Ragas)만 API 키가 필요합니다.

## 2\. 5분 빠른 시작 ⚡

1

설치하기

```python
    # Conda 가상환경 생성 (권장)
    conda create --name Evaluator python=3.11
    conda activate Evaluator
    
    # Agent Evaluator 설치
    pip install agent-evaluator
```python

2

첫 번째 평가 실행하기

`my_first_evaluation.py` 파일을 만들고 다음 코드를 입력하세요:

```python
    from agent_evaluator import PerformanceMonitor, TaskResult
    from datetime import datetime
    
    # 1. 모니터 생성
    monitor = PerformanceMonitor()
    
    # 2. Agent 함수 (예제)
    def my_simple_agent(question: str) -> str:
        """간단한 Agent 예제"""
        if "2+2" in question or "2 + 2" in question:
            return "2+2는 4입니다."
        return "잘 모르겠습니다."
    
    # 3. Agent 실행 및 평가
    question = "2+2는 얼마인가요?"
    response = my_simple_agent(question)
    
    # 4. 결과 기록
    task = TaskResult(
        task_id="test_001",
        task_type="qa",
        success=True,
        completion_score=1.0,      # 0.0~1.0: 작업 완료 정도
        accuracy_score=0.95,       # 0.0~1.0: 정확도
        execution_time=0.1,        # 초 단위
        tokens_used={"input": 10, "output": 15, "total": 25},
        tool_calls=[],
        attempts=1,
        errors=[],
        timestamp=datetime.now()
    )
    monitor.record_task(task)
    
    # 5. 결과 확인
    report = monitor.generate_report()
    print(f"✅ Task Completion Rate: {report.accuracy_metrics['tcr']['tcr']:.1f}%")
    print(f"✅ Accuracy: {report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.2f}%")
    print(f"✅ Latency: {report.efficiency_metrics['latency']['average']:.2f}s")
```python

3

실행하기

```python
    python my_first_evaluation.py
```python

**예상 출력:**

```python
    ✅ Task Completion Rate: 100.0%
    ✅ Accuracy: 95.00%
    ✅ Latency: 0.10s
```python

🎉 축하합니다!

첫 번째 Agent 평가를 완료했습니다! 이제 더 고급 기능을 배워보겠습니다.

## 3\. 단계별 튜토리얼

### Step 1: Helper 함수로 더 쉽게 사용하기

직접 `TaskResult`를 만드는 대신 **Helper 함수** 를 사용하면 훨씬 간단합니다:

예제: Helper 함수 사용

```python
    from agent_evaluator import PerformanceMonitor
    from agent_evaluator import create_taskresult
    import time

    monitor = PerformanceMonitor()

    def my_agent(question: str) -> str:
        """실제 Agent 로직"""
        # ... Agent 실행 ...
        return "답변입니다"

    # Agent 실행 및 시간 측정
    question = "프랑스의 수도는?"
    start = time.time()
    response = my_agent(question)
    elapsed = time.time() - start

    # Helper 함수로 TaskResult 자동 생성
    task = create_taskresult(
        task_id="task_001",
        question=question,
        response=response,
        ground_truth="파리",         # 정답
        execution_time=elapsed,
        tokens_used={"input": 20, "output": 10, "total": 30}
    )
    
    # 기록
    monitor.record_task(task)
    
    # 결과 확인
    report = monitor.generate_report()
    print(f"Total tasks: {report.total_tasks}")
    print(f"Success rate: {report.success_rate:.2%}")
```python

💡 Helper 함수의 장점

  * `completion_score`가 자동으로 계산됩니다
  * `accuracy_score`가 자동으로 계산됩니다 (ground_truth 제공 시)
  * `success` 플래그가 자동으로 설정됩니다
  * 코드가 훨씬 간결해집니다

### Step 2: 여러 작업 평가하기

실전에서는 여러 작업을 평가해야 합니다:

예제: 여러 작업 평가

```python
    from agent_evaluator import PerformanceMonitor
    from agent_evaluator import create_taskresult

    monitor = PerformanceMonitor()

    # 테스트 케이스들
    test_cases = [
        {"question": "2+2는?", "expected": "4"},
        {"question": "프랑스 수도는?", "expected": "파리"},
        {"question": "지구는 태양 주위를 도는가?", "expected": "네"},
        # ... 더 많은 테스트 케이스
    ]

    # 각 테스트 케이스 평가
    for i, test in enumerate(test_cases):
        response = my_agent(test["question"])

        task = create_taskresult(
            task_id=f"task_{i:03d}",
            question=test["question"],
            response=response,
            ground_truth=test["expected"],
            execution_time=1.0
        )
        monitor.record_task(task)
    
    # 전체 결과 확인
    report = monitor.generate_report()
    print(f"총 작업 수: {report.total_tasks}")
    print(f"평균 정확도: {report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.2f}%")
    
    # 결과 저장
    monitor.save_to_file("evaluation_results/my_evaluation.json")
```python

### Step 3: 임계값 설정 및 Pass/Fail 판정

프로덕션 환경에서는 **임계값** 을 설정하여 품질을 보장합니다:

예제: 임계값 설정

```python
    from agent_evaluator import PerformanceMonitor
    
    # 임계값과 함께 모니터 생성
    monitor = PerformanceMonitor()
    monitor.thresholds = {
        'tcr': 95.0,           # 최소 95% 완료율
        'accuracy': 90.0,      # 최소 90% 정확도
        'latency': 2.0,        # 최대 2초 응답시간
        'hallucination': 5.0,  # 최대 5% 환각률
    }
    
    # ... 평가 수행 ...
    
    # 임계값 비교
    comparison = monitor.compare_with_thresholds()
    
    # 결과 확인
    for metric, result in comparison.items():
        status = "✅ PASS" if result["status"] == "pass" else "❌ FAIL"
        print(f"{metric}: {result['actual']:.2f} (임계값: {result['threshold']:.2f}) {status}")
    
    # 전체 Pass/Fail
    all_passed = all(r["status"] == "pass" for r in comparison.values())
    if not all_passed:
        print("\n⚠️  일부 메트릭이 임계값을 통과하지 못했습니다!")
        exit(1)  # CI/CD에서 실패 처리
```python

## 4\. Golden Dataset 활용하기 (자동 평가)

### Golden Dataset이란?

**Golden Dataset** 은 테스트 케이스의 표준 모음입니다. 질문, 정답, 컨텍스트 등을 포함하며, Agent를 자동으로 평가할 수 있습니다.

💡 왜 Golden Dataset을 사용하나요?

  * **자동화** : 수백 개의 테스트를 한 번에 실행
  * **일관성** : 항상 동일한 기준으로 평가
  * **회귀 테스트** : Agent 업데이트 후 성능 비교
  * **CI/CD 통합** : 자동 품질 게이트

### Step 1: Golden Dataset 파일 만들기

`golden_datasets/sample.json` 파일을 만듭니다:

예제: Golden Dataset (JSON 형식)

```json
    [
      {
        "qa_id": "qa_001",
        "question": "프랑스의 수도는?",
        "answer": "프랑스의 수도는 파리입니다.",
        "context": "프랑스는 서유럽에 위치한 국가이며, 수도는 파리입니다.",
        "ground_truth": "파리",
        "metadata": {
          "domain": "geography",
          "difficulty": "easy"
        }
      },
      {
        "qa_id": "qa_002",
        "question": "2+2는 얼마인가요?",
        "answer": "2+2는 4입니다.",
        "context": "기본적인 덧셈 계산 문제입니다.",
        "ground_truth": "4",
        "metadata": {
          "domain": "math",
          "difficulty": "easy"
        }
      }
    ]
```python

### Step 2: Agent 함수 작성

Golden Dataset을 사용하려면 Agent 함수가 **Dict를 반환** 해야 합니다:

예제: Golden Dataset용 Agent 함수

```python
    def my_agent(question: str) -> dict:
        """
        Agent 함수
    
        Args:
            question: 사용자 질문
    
        Returns:
            dict: 반드시 'answer' 키를 포함해야 함
        """
        # Agent 로직 구현
        if "프랑스" in question and "수도" in question:
            answer = "파리입니다."
        elif "2+2" in question:
            answer = "4입니다."
        else:
            answer = "잘 모르겠습니다."
    
        return {
            "answer": answer,  # 필수!
            "confidence": 0.95,  # 선택
            "sources": ["knowledge_base"]  # 선택
        }
```python

⚠️ 중요: Dict 반환 형식

Agent 함수는 반드시 **`'answer'` 키를 포함한 Dict**를 반환해야 합니다. 그렇지 않으면 오류가 발생합니다.

### Step 3: 자동 평가 실행

이제 단 몇 줄로 자동 평가를 실행할 수 있습니다:

예제: Golden Dataset 자동 평가

```python
    from agent_evaluator import PerformanceMonitor
    
    # 모니터 생성
    monitor = PerformanceMonitor()
    
    # 단 1줄로 자동 평가!
    results = monitor.evaluate_with_golden_dataset(
        agent_fn=my_agent,
        dataset_path="golden_datasets/sample.json"
    )
    
    # 결과 확인
    print(f"✅ 총 테스트: {results['total_tests']}")
    print(f"✅ 성공: {results['passed_tests']}")
    print(f"✅ 실패: {results['failed_tests']}")
    print(f"✅ TCR: {results['tcr']:.1f}%")
    print(f"✅ Accuracy: {results['accuracy']:.2f}%")
    
    # 상세 리포트
    report = monitor.generate_report()
    print(f"Total tasks: {report.total_tasks}")
    print(f"Success rate: {report.success_rate:.2%}")
```python

🚀 자동 평가의 강력함

100개의 테스트 케이스도 몇 초 안에 자동으로 평가됩니다. CI/CD 파이프라인에 통합하면 배포 전 자동 품질 검증이 가능합니다!

### Step 4: PDF에서 Golden Dataset 생성 (고급)

PDF 문서에서 자동으로 Golden Dataset을 생성할 수 있습니다:

예제: PDF에서 Golden Dataset 생성

```python
    from agent_evaluator.datasets.korean_rag_dataset_generator import KoreanRAGDatasetGenerator
    
    # Generator 초기화 (OpenAI API 키 필요)
    generator = KoreanRAGDatasetGenerator(
        model="gpt-4o-mini",  # 또는 "gpt-4o"
        chunk_size=1000
    )
    
    # PDF에서 Golden Dataset 생성
    dataset = generator.generate_from_pdf(
        pdf_path="docs/my_document.pdf",
        num_qa_pairs=20,  # 생성할 QA 쌍 개수
        output_path="golden_datasets/generated.json"
    )
    
    print(f"✅ {len(dataset['qa_pairs'])}개의 QA 쌍 생성 완료!")
    print(f"✅ 저장 위치: golden_datasets/generated.json")
```python

## 5\. 터미널 출력 방법 📟

### 개요

Agent Evaluator는 평가 결과를 터미널에서 바로 확인할 수 있도록 다양한 출력 메서드를 제공합니다. 실시간 피드백과 상세한 분석을 통해 Agent 성능을 즉시 파악할 수 있습니다.

💡 왜 터미널 출력을 사용하나요?

  * **즉각적인 피드백** : 평가 후 바로 결과 확인
  * **개발 중 디버깅** : CI/CD 파이프라인에서 실시간 모니터링
  * **간편한 비교** : 여러 실행 결과를 빠르게 비교
  * **경량 분석** : Dashboard 없이 빠른 분석 가능

### 방법 1: 기본 print_summary() - 빠른 확인

가장 간단한 방법으로, 핵심 메트릭을 한눈에 확인할 수 있습니다:

예제: 기본 요약 출력

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # ... Agent 평가 수행 ...
    
    # 기본 요약 출력
    report = monitor.generate_report()
    monitor.print_summary(report)
```python

**출력 예시:**

```python
    ========================================
             성능 요약 보고서
    ========================================
    
    📊 전체 작업 통계:
      - 총 작업 수: 100
      - 성공: 95 (95.0%)
      - 실패: 5 (5.0%)
    
    ✅ 정확도 메트릭:
      - TCR (Task Completion Rate): 95.0%
      - 평균 Accuracy: 92.5%
      - Hallucination Rate: 2.3%
    
    ⚡ 효율성 메트릭:
      - 평균 Latency: 1.23초
      - P95 Latency: 2.45초
      - 평균 Token 사용량: 450 tokens
      - 총 비용: $0.23
    
    ========================================
```python

### 방법 2: print_detailed_report() - 상세 분석

모든 메트릭과 통계를 자세히 확인할 수 있습니다:

예제: 상세 리포트 출력

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # ... Agent 평가 수행 ...
    
    # 상세 리포트 출력
    report = monitor.generate_report()
    monitor.print_detailed_report(report)
```python

**출력 예시:**

```python
    ================================================================================
                                상세 성능 분석 보고서
    ================================================================================
    
    📊 작업 통계
    ────────────────────────────────────────────────────────────────────────────────
      총 작업 수              : 100
      성공                    : 95 (95.0%)
      실패                    : 5 (5.0%)
      평균 재시도 횟수        : 1.2
    
    ✅ Layer 1: Foundation Metrics (기본 성능 지표)
    ────────────────────────────────────────────────────────────────────────────────
      [정확도]
        - TCR                 : 95.0%
        - Accuracy (평균)     : 92.5%
        - Hallucination Rate  : 2.3%
    
      [지연시간]
        - 평균               : 1.23초
        - 중앙값             : 1.10초
        - P95                : 2.45초
        - P99                : 3.21초
        - 최소               : 0.45초
        - 최대               : 5.67초
    
      [토큰 사용량]
        - 총 Input Tokens    : 35,000
        - 총 Output Tokens   : 15,000
        - 총 Tokens          : 50,000
        - 평균 (작업당)      : 450 tokens
    
      [비용]
        - 총 비용            : $0.23
        - 평균 (작업당)      : $0.0023
    
      [보안 메트릭]
        - Input Sanitization : 98.5%
        - Output Leakage     : 99.0%
        - Authorization      : 97.5%
    
    ⚙️ Layer 2: Agentic + Security Metrics (에이전트 시스템 + 보안 지표)
    ────────────────────────────────────────────────────────────────────────────────
      [도구 사용]
        - Tool Selection Accuracy    : 88.5%
        - Tool Efficiency            : 92.0%
        - 평균 도구 호출 수          : 2.3
    
      [에이전트 협업]
        - Agent Coordination Score   : 91.2%
        - 평균 메시지 교환 수        : 4.5
    
      [보안 메트릭]
        - Privilege Escalation       : 99.5%
        - Attack Detection           : 98.0%
    
    🎯 Layer 3: Advanced Metrics (고급 평가 지표)
    ────────────────────────────────────────────────────────────────────────────────
      [DeepEval]
        - G-Eval Score       : 0.89
        - Hallucination      : 0.02
        - Toxicity           : 0.01
        - Bias               : 0.03
    
      [Ragas (RAG 평가)]
        - Faithfulness       : 0.91
        - Answer Relevancy   : 0.88
        - Context Precision  : 0.85
        - Context Recall     : 0.87
    
    ================================================================================
```python

### 방법 3: 프로그래밍 방식 - 커스텀 출력

직접 Report 객체에서 필요한 데이터만 추출하여 출력할 수 있습니다:

예제: 커스텀 출력

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # ... Agent 평가 수행 ...
    
    # Report 객체 생성
    report = monitor.generate_report()
    
    # 커스텀 출력
    print("=" * 60)
    print("🎯 핵심 메트릭 요약")
    print("=" * 60)
    
    # Layer 1 메트릭
    print(f"\n✅ TCR: {report.accuracy_metrics['tcr']['tcr']:.1f}%")
    print(f"✅ Accuracy: {report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.2f}%")
    print(f"✅ Latency (평균): {report.efficiency_metrics['latency']['average']:.2f}s")
    print(f"✅ Cost (총): ${report.efficiency_metrics['tokens']['total_cost']:.4f}")
    
    # Layer 2 메트릭 (있는 경우)
    if 'tool_selection' in report.agentic_metrics:
        print(f"\n⚙️ Tool Selection: {report.agentic_metrics['tool_selection']['accuracy']:.1f}%")
    
    # Layer 3 메트릭 (있는 경우)
    if 'deepeval' in report.advanced_metrics:
        print(f"\n🎯 G-Eval Score: {report.advanced_metrics['deepeval']['g_eval']:.2f}")
    
    print("=" * 60)
```python

**출력 예시:**

```python
    ============================================================
    🎯 핵심 메트릭 요약
    ============================================================
    
    ✅ TCR: 95.0%
    ✅ Accuracy: 92.5%
    ✅ Latency (평균): 1.23s
    ✅ Cost (총): $0.2300
    
    ⚙️ Tool Selection: 88.5%
    
    🎯 G-Eval Score: 0.89
    ============================================================
```python

### 방법 4: JSON 형식 출력 - 파싱 가능

다른 도구와 통합하거나 자동화된 분석을 위해 JSON 형식으로 출력할 수 있습니다:

예제: JSON 출력

```python
    import json
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    
    # ... Agent 평가 수행 ...
    
    # Report를 JSON으로 출력
    report = monitor.generate_report()
    report_dict = report.to_dict()
    
    # 보기 좋게 출력
    print(json.dumps(report_dict, indent=2, ensure_ascii=False))
```python

### 방법 5: 임계값 비교 출력 - Quality Gate

임계값과 비교하여 Pass/Fail 상태를 명확하게 표시합니다:

예제: 임계값 비교 출력

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.thresholds = {
        'tcr': 95.0,
        'accuracy': 90.0,
        'latency': 2.0,
        'hallucination': 5.0,
    }
    
    # ... Agent 평가 수행 ...
    
    # 임계값 비교
    comparison = monitor.compare_with_thresholds()
    
    print("=" * 70)
    print("📊 Quality Gate 결과")
    print("=" * 70)
    
    for metric, result in comparison.items():
        status_symbol = "✅" if result["status"] == "pass" else "❌"
        status_text = "PASS" if result["status"] == "pass" else "FAIL"
    
        print(f"{status_symbol} {metric:20s} | "
              f"실제: {result['actual']:7.2f} | "
              f"임계값: {result['threshold']:7.2f} | "
              f"{status_text}")
    
    # 전체 결과
    all_passed = all(r["status"] == "pass" for r in comparison.values())
    print("=" * 70)
    if all_passed:
        print("✅ Quality Gate: PASSED - 모든 메트릭이 임계값을 통과했습니다!")
    else:
        print("❌ Quality Gate: FAILED - 일부 메트릭이 임계값을 통과하지 못했습니다.")
    print("=" * 70)
```python

**출력 예시:**

```python
    ======================================================================
    📊 Quality Gate 결과
    ======================================================================
    ✅ tcr                  | 실제:   95.00 | 임계값:   95.00 | PASS
    ✅ accuracy             | 실제:   92.50 | 임계값:   90.00 | PASS
    ✅ latency              | 실제:    1.23 | 임계값:    2.00 | PASS
    ✅ hallucination        | 실제:    2.30 | 임계값:    5.00 | PASS
    ======================================================================
    ✅ Quality Gate: PASSED - 모든 메트릭이 임계값을 통과했습니다!
    ======================================================================
```python

### 실전 활용 팁

#### 1\. 개발 중: 빠른 확인

```python
    # 개발하면서 빠르게 확인
    monitor.print_summary(report)
```python

#### 2\. CI/CD: 자동화된 검증

```python
    # GitHub Actions, Jenkins 등에서 사용
    comparison = monitor.compare_with_thresholds()
    all_passed = all(r["status"] == "pass" for r in comparison.values())
    
    if not all_passed:
        print("❌ Quality Gate Failed!")
        exit(1)  # CI/CD 파이프라인 실패
    else:
        print("✅ Quality Gate Passed!")
        exit(0)
```python

#### 3\. 디버깅: 상세 분석

```python
    # 문제 발생 시 상세 분석
    monitor.print_detailed_report(report)
```python

#### 4\. 자동화: JSON 파싱

```python
    # 다른 시스템과 통합
    report_json = json.dumps(report.to_dict())
    # Slack, Email, 모니터링 시스템으로 전송
```python

⚠️ 주의사항

  * `print_summary()`와 `print_detailed_report()`는 반드시 `generate_report()` 후에 호출해야 합니다
  * Layer 2, 3 메트릭은 해당 기능을 활성화한 경우에만 출력됩니다
  * 터미널 출력은 UTF-8 인코딩을 지원하는 환경에서 가장 잘 작동합니다

## 6\. 메트릭 이해하기

### 3계층 메트릭 체계

Agent Evaluator는 **3개의 계층(Layer)** 으로 구성된 메트릭을 제공합니다:

Layer | 이름 | 설명 | 개수 | 비용 | API 키  
---|---|---|---|---|---  
1 | Foundation Metrics | 기본 성능 지표 6개 (TCR, Accuracy, Hallucination, Response Quality, Latency, Token Economy) | **6개** | 무료 | ❌ 불필요
2 | Agentic + Security Metrics | 에이전틱 5개 (Tool Call, Retry, Tool Selection, Coordination, Workflow) + 보안 5개 (Input Sanitization, Output Leakage, Tool Auth, Privilege Escalation, Tool Chain Attack) | **10개** | 무료 | ❌ 불필요
3 | Advanced Metrics | AI 기반 고급 평가 (DeepEval 5종, Ragas 4종) | **9개** | 유료 | ✅ OpenAI API

### Layer 1: Foundation Metrics (무료, 추천) - 총 6개

초보자는 **Layer 1만 사용** 해도 충분합니다. API 키 불필요, 완전 무료입니다.

#### 📊 기본 성능 메트릭 (6개):

메트릭 | 설명 | 좋은 값  
---|---|---  
**1\. TCR**  
(Task Completion Rate) | 작업 완료율 | ≥ 95%  
**2\. Accuracy** | 정확도 (4가지 유사도 메트릭 조합) | ≥ 90%  
**3\. Hallucination Detection** | 환각 발생 탐지 (컨텍스트 기반) | ≤ 5%  
**4\. Response Quality** | 응답 품질 (Completeness, Relevance, Clarity, Accuracy, Usefulness) | ≥ 85%  
**5\. Latency** | 평균 응답 시간 | ≤ 2초  
**6\. Token Economy** | 토큰 사용량 및 비용 추적 | ≤ $0.10/task  
  
예제: Layer 1 메트릭 확인

```python
    # 평가 후 리포트 생성
    report = monitor.generate_report()
    
    # Layer 1: Foundation Metrics
    print("=== Layer 1: Foundation Metrics ===")
    print(f"TCR: {report.accuracy_metrics['tcr']['tcr']:.1f}%")
    print(f"Accuracy: {report.accuracy_metrics['accuracy_scores']['overall_accuracy']:.2f}%")
    print(f"Hallucination Rate: {report.accuracy_metrics.get('hallucination', {}).get('rate', 0):.2f}%")
    print(f"Latency: {report.efficiency_metrics['latency']['average']:.2f}s")
    print(f"Cost: ${report.efficiency_metrics['tokens']['total_cost']:.4f}")

    # Layer 2: Security Metrics (enable_security_metrics=True 필요)
    if 'security' in report.accuracy_metrics:
        print(f"Input Sanitization: {report.accuracy_metrics['security'].get('input_sanitization', 0):.1f}%")
        print(f"Output Leakage: {report.accuracy_metrics['security'].get('output_leakage', 0):.1f}%")
```python

### Layer 2: Agentic + Security Metrics (무료) - 총 10개

Multi-Agent 시스템, 워크플로우, 도구 사용 Agent를 평가할 때 사용합니다.

#### 🤖 에이전틱 메트릭 (5개):

메트릭 | 설명 | 좋은 값
---|---|---
**1\. Tool Call Analysis** | 도구 호출 패턴 및 성공률 분석 | ≥ 95%
**2\. Retry & Correction** | 재시도 횟수 및 자가 수정 능력 | ≤ 2회/task
**3\. Tool Selection Accuracy** | 올바른 도구를 선택했는지 평가 | ≥ 90%
**4\. Agent Coordination** | 에이전트 간 협업 품질 | ≥ 85%
**5\. Workflow Execution** | 워크플로우 실행 성공률 및 단계별 추적 | ≥ 95%

#### 🛡️ 보안 메트릭 (5개, Opt-in `enable_security_metrics=True`):

메트릭 | 설명 | 좋은 값
---|---|---
**6\. Input Sanitization** | SQL/Command Injection, Path Traversal, XSS, Prompt Injection 탐지 | 0건
**7\. Output Leakage** | API 키, 비밀번호, 개인정보 유출 탐지 | 0건
**8\. Tool Authorization** | 허가된 도구만 호출했는지 검증 | 100%
**9\. Privilege Escalation** | 권한 상승 공격 탐지 | 0건
**10\. Tool Chain Attack Detection** | 도구 체인 공격 패턴 탐지 | 0건  
  
💡 Layer 2는 언제 사용하나요?

  * **단일 Agent** : Layer 1만 사용하면 됩니다
  * **Multi-Agent 시스템** : Layer 1 + Layer 2 사용 (CrewAI, AutoGen)
  * **워크플로우 Agent** : Layer 1 + Layer 2 사용 (LangGraph)
  * **도구 사용 Agent** : Layer 1 + Layer 2 (Tool Selection) 사용

### Layer 3: Advanced Metrics (유료, 고급 사용자용) - 총 9개

AI 기반 고급 평가가 필요할 때만 사용합니다 (OpenAI API 키 필요):

#### 🎯 DeepEval 메트릭 (5개):

  * **G-Eval** : 사용자 정의 평가 기준
  * **Hallucination** : AI 기반 환각 탐지
  * **Toxicity** : 유해성 탐지
  * **Bias** : 편향성 탐지
  * **Answer Relevancy** : 답변 관련성

#### 📚 Ragas 메트릭 (4개, RAG 전용):

  * **Faithfulness** : 컨텍스트 충실도
  * **Context Precision** : 컨텍스트 정확도
  * **Context Recall** : 컨텍스트 재현율
  * **Answer Relevancy** : 답변 관련성

⚠️ Layer 3 주의사항

Layer 3는 OpenAI API 호출 비용이 발생합니다. 프로덕션 환경에서는 Layer 1 + Layer 2만 사용하고, Layer 3는 개발 단계에서만 사용하는 것을 권장합니다.

예제: Layer 3 활성화 (고급)

```python
    from agent_evaluator.core.hybrid_monitor import HybridPerformanceMonitor
    
    # Layer 3 활성화 (OpenAI API 키 필요)
    monitor = HybridPerformanceMonitor(
        use_deepeval=True,  # DeepEval 5종 메트릭
        use_ragas=True      # Ragas 4종 메트릭 (RAG 시스템 전용)
    )
    
    # 평가 실행 (API 비용 발생)
    results = monitor.evaluate_with_golden_dataset(
        agent_fn=my_agent,
        dataset_path="golden_datasets/sample.json"
    )
    
    # Layer 3 메트릭 확인
    print(f"Hallucination (DeepEval): {results['advanced_metrics']['deepeval']['hallucination']:.2f}")
    print(f"Faithfulness (Ragas): {results['advanced_metrics']['ragas']['faithfulness']:.2f}")
```python

## 7\. 실전 예제

### 예제 1: LangChain Agent 평가

LangChain Agent 평가하기

```python
    from langchain_openai import ChatOpenAI
    from langchain.chains import LLMChain
    from langchain.prompts import PromptTemplate
    from agent_evaluator import PerformanceMonitor
    
    # LangChain Agent 생성
    llm = ChatOpenAI(model="gpt-3.5-turbo")
    prompt = PromptTemplate(
        input_variables=["question"],
        template="다음 질문에 답해주세요: {question}"
    )
    chain = LLMChain(llm=llm, prompt=prompt)
    
    # Agent 함수로 래핑
    def langchain_agent(question: str) -> dict:
        response = chain.run(question=question)
        return {"answer": response}
    
    # 평가 실행
    monitor = PerformanceMonitor()
    results = monitor.evaluate_with_golden_dataset(
        agent_fn=langchain_agent,
        dataset_path="golden_datasets/sample.json"
    )
    
    print(f"LangChain Agent TCR: {results['tcr']:.1f}%")
```python

### 예제 2: A/B 테스트 - 두 Agent 비교

두 Agent 성능 비교

```python
    from agent_evaluator import PerformanceMonitor
    
    # 두 개의 Agent
    def agent_v1(question: str) -> dict:
        # 구 버전 로직
        return {"answer": "V1 응답"}
    
    def agent_v2(question: str) -> dict:
        # 신 버전 로직 (개선됨)
        return {"answer": "V2 응답"}
    
    # 각각 평가
    monitor_v1 = PerformanceMonitor()
    monitor_v2 = PerformanceMonitor()
    
    results_v1 = monitor_v1.evaluate_with_golden_dataset(
        agent_fn=agent_v1,
        dataset_path="golden_datasets/sample.json"
    )
    
    results_v2 = monitor_v2.evaluate_with_golden_dataset(
        agent_fn=agent_v2,
        dataset_path="golden_datasets/sample.json"
    )
    
    # 비교
    print("=== A/B Test Results ===")
    print(f"V1 Accuracy: {results_v1['accuracy']:.2f}%")
    print(f"V2 Accuracy: {results_v2['accuracy']:.2f}%")
    print(f"개선율: {results_v2['accuracy'] - results_v1['accuracy']:+.2f}%")
```python

### 예제 3: CI/CD 통합

GitHub Actions CI/CD

```python
    # .github/workflows/quality-gate.yml
    name: Agent Quality Gate
    
    on:
      push:
        branches: [main]
      pull_request:
        branches: [main]
    
    jobs:
      quality-gate:
        runs-on: ubuntu-latest
    
        steps:
          - uses: actions/checkout@v3
          - uses: actions/setup-python@v4
            with:
              python-version: '3.11'
    
          - name: Install dependencies
            run: |
              pip install agent-evaluator
    
          - name: Run Quality Gate
            run: |
              python scripts/quality_gate.py
            env:
              ENV: production
```python

`scripts/quality_gate.py`:

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.thresholds = {
        'tcr': 95.0,
        'accuracy': 90.0,
    }
    
    results = monitor.evaluate_with_golden_dataset(
        agent_fn=my_agent,
        dataset_path="golden_datasets/production.json"
    )
    
    # 임계값 체크
    comparison = monitor.compare_with_thresholds()
    all_passed = all(r["status"] == "pass" for r in comparison.values())
    
    if not all_passed:
        print("❌ Quality Gate Failed!")
        exit(1)  # CI/CD 실패
    
    print("✅ Quality Gate Passed!")
    exit(0)
```python

## 8\. 자주 묻는 질문 (FAQ)

### Q1: OpenAI API Key가 꼭 필요한가요?

**A:** 아니요! **Layer 1 메트릭**(TCR, Accuracy, Latency 등)은 완전 무료이며 API 키가 필요 없습니다. Layer 3 고급 메트릭(DeepEval, Ragas)만 API 키가 필요합니다.

### Q2: Golden Dataset은 어떻게 만드나요?

**A:** 세 가지 방법이 있습니다:

  1. **수동 작성** : JSON 파일을 직접 작성 (소규모)
  2. **PDF 자동 생성** : `KoreanRAGDatasetGenerator` 사용 (대규모)
  3. **실제 사용자 데이터** : 프로덕션 로그에서 추출 (실전)

### Q3: completion_score는 무엇인가요?

**A:** 작업 완료 정도를 나타내는 0.0~1.0 값입니다:

  * `1.0`: 완전히 성공
  * `0.7~0.99`: 부분 성공
  * `0.0~0.69`: 실패

Helper 함수를 사용하면 자동으로 계산됩니다.

### Q4: Agent 함수가 Dict를 반환해야 하나요?

**A:** `evaluate_with_golden_dataset()`를 사용할 때만 Dict 반환이 필요합니다. 수동 평가(`record_task`)는 어떤 형식이든 괜찮습니다.

```python
    # Golden Dataset용 (Dict 필수)
    def my_agent(question: str) -> dict:
        return {"answer": "답변"}
    
    # 수동 평가용 (자유 형식)
    def my_agent(question: str) -> str:
        return "답변"
```python

### Q5: 결과를 저장하면 어디에 저장되나요?

**A:** `monitor.save_to_file("results.json")`를 호출하면:

  1. 지정한 경로에 JSON 파일 저장
  2. 자동으로 Dashboard 레지스트리에 등록 (`~/.agent_evaluator/registry.json`)
  3. Dashboard에서 "데이터 편집" 탭에서 바로 확인 가능

### Q6: 메모리 부족 오류가 발생합니다

**A:** 대량의 작업을 평가할 때는 주기적으로 저장하고 초기화하세요:

```python
    for i in range(10000):
        task = create_taskresult(...)
        monitor.record_task(task)
    
        # 1000개마다 저장 및 초기화
        if i % 1000 == 0:
            monitor.save_to_file(f"batch_{i//1000}.json")
            monitor = PerformanceMonitor()  # 새로 생성
```python

## 9\. 다음 단계

### 📝 실전 예제 파일 (총 5개)

Agent Evaluator는 **카테고리별 5개의 실행 가능한 예제 파일** 을 제공합니다:

  * `01_quality_eval.py` \- 품질 지표 — Accuracy, Hallucination, Response Quality, RAG
  * `02_performance_eval.py` \- 성능 지표 — TCR, Latency (p50/p95/p99), Token Economy
  * `03_agentic_eval.py` \- 에이전틱 지표 — Tool Call, Coordination, Workflow, Retry
  * `04_security_eval.py` \- 보안 지표 — Input Sanitization, Leakage, Auth, Escalation, Attack
  * `05_hybrid_eval.py` \- 하이브리드 평가 — DeepEval, Ragas 통합 (OpenAI API 키 필요)
  * `06_langchain_eval.py` \- LangChain 프레임워크 통합 예제
  * `07_langgraph_eval.py` \- LangGraph 프레임워크 통합 예제
  * `08_crewai_eval.py` \- CrewAI 프레임워크 통합 예제
  * `09_autogen_eval.py` \- AutoGen 프레임워크 통합 예제
  * `10_cross_framework_eval.py` \- 멀티 프레임워크 비교 평가

**실행 방법:**

```bash
    cd Evaluator_Examples
    python 01_quality_eval.py      # 품질 지표 (Accuracy, Hallucination, Quality, RAG)
    python 02_performance_eval.py  # 성능 지표 (TCR, Latency, Token Economy)
    python 03_agentic_eval.py      # 에이전틱 지표 (Tool, Coordination, Workflow)
    python 04_security_eval.py     # 보안 지표 (Sanitization, Leakage, Auth, Attack)
```

### 🎓 더 배우기

  * **API Reference** : 모든 API의 상세 명세 확인 (`Docs/API_REFERENCE.html`)
  * **메트릭 가이드** : 각 메트릭의 상세 설명 (`Docs/METRICS_GUIDE.html`)
  * **보안 메트릭 가이드** : Layer 2 보안 메트릭 (`Docs/SECURITY_METRICS_GUIDE.html`)
  * **Golden Dataset 가이드** : 데이터셋 생성 완전 가이드 (`Docs/GOLDEN_DATASET_GUIDE.html`)
  * **배포 가이드** : 프로덕션 배포 방법 (`Docs/DEPLOYMENT_GUIDE.html`)

### 🚀 고급 기능

  * **Layer 1 보안 메트릭** : Input Sanitization, Output Leakage, Authorization
  * **Layer 2 메트릭** : Multi-Agent 시스템 평가 + Security
  * **Layer 3 메트릭** : AI 기반 고급 평가 (DeepEval, Ragas)
  * **프레임워크 통합** : CrewAI, LangChain, LangGraph, AutoGen
  * Dashboard: 12 탭 시각화 대시보드 (보안 탭 포함)

### 📚 더 알아보기

Agent Evaluator의 다양한 기능에 대해 더 알아보세요:

  * [API 레퍼런스](<API_REFERENCE.html>): 전체 API 문서 (PerformanceMonitor, HybridMonitor 등)
  * [메트릭 가이드](<METRICS_GUIDE.html>): Layer 1/2/3 메트릭 종합 설명
  * [보안 메트릭 가이드](<SECURITY_METRICS_GUIDE.html>): Layer 2 보안 메트릭 상세
  * [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.html>): CrewAI, LangChain, LangGraph, AutoGen
  * [Agentic AI 메트릭 가이드](<AGENTIC_AI_METRICS_GUIDE.html>): Layer 2 Agentic 메트릭 상세
  * [임계값 설정 가이드](<THRESHOLD_CONFIGURATION_GUIDE.html>): Quality Gate 구성
  * [Dashboard 가이드](<DASHBOARD.html>): Dashboard 사용법 (12 탭 구조)
  * [데이터 편집 & 투명성](<DATA_EDITOR_TRANSPARENCY_GUIDE.html>): Test Configuration 관리

### 💬 도움 받기

  * **Documentation** : 전체 문서 확인
  * **Email** : sungwoo.kim@gmail.com

🎉 축하합니다!

이제 Agent Evaluator의 기본을 모두 배웠습니다. 실제 프로젝트에 적용해보세요!

**Agent Evaluator v0.6.2**

개발자: **KIM SUNGWOO**

Email: [sungwoo.kim@gmail.com](<mailto:sungwoo.kim@gmail.com>)

**최종 업데이트** : 2026-03-27

© 2024-2025 MIT License
