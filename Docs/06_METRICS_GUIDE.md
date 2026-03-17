# 📊 평가 메트릭 가이드

Layer별 메트릭 상세 설명 및 사용법

# 평가 지표 상세 가이드

> 🎯 Agent Evaluator의 모든 평가 지표에 대한 완벽 가이드

이 문서는 Agent Evaluator에서 제공하는 모든 평가 지표에 대한 상세한 설명, 계산 방법, 해석 방법, 그리고 실제 사용 예제를 제공합니다.

## 버전 정보

**Breaking Changes:** 레거시 API 완전 제거!

  * ❌ **레거시 클래스 제거:** `EvaluatedCrew`, `LangChainEvaluationCallback`, `LangGraphEvaluatedWorkflow`, `EvaluatedAutoGenAgent`
  * ✅ **새로운 통합 API:** `CrewAIEvaluator`, `LangChainEvaluator`, `LangGraphEvaluator`, `AutoGenEvaluator`
  * 📦 **75% 코드 감소:** 더 안정적이고 유지보수하기 쉬운 코드베이스
  * 🚀 **프로덕션 준비 완료**

**마이그레이션:** [마이그레이션 가이드 보기](<API_REFERENCE.html#migration-guide>)

**이 가이드는 다음 버전을 기준으로 작성되었습니다:**

  * Agent Evaluator: **v0.5.0**
  * Python: 3.8+
  * DeepEval: 0.20.0+ (선택사항, Layer 3)
  * Ragas: 0.1.0+ (선택사항, Layer 3)
  * LangChain: 0.1.0+ (선택사항)
  * CrewAI: 최신 버전 (선택사항)

## 목차

  * [🚀 0. 빠른 시작 (개발자용)](<#빠른-시작>)
  * [1\. 메트릭 체계 개요](<#메트릭-체계-개요>)
  * [2\. Layer 1: Native Metrics (기본 메트릭 10개)](<#layer-1-native-metrics-기본-메트릭-10개>)
  * [3\. Layer 2: Agentic AI Metrics (에이전트 메트릭 6개)](<#layer-2-agentic-ai-metrics-에이전트-메트릭-6개>)
  * [4\. Layer 3: Advanced Metrics (고급 메트릭 9~10개)](<#layer-3-advanced-metrics-고급-메트릭-9개>)
    * [4.1 DeepEval 메트릭](<#deepeval-메트릭>)
    * [4.2 RAGAS 메트릭 (RAG 전용)](<#ragas-메트릭-rag-전용>)
  * [5\. 메트릭 선택 가이드](<#메트릭-선택-가이드>)
  * [6\. 실전 활용 팁](<#실전-활용-팁>)
  * [📊 7. 품질 관리자 가이드 (QA Manager)](<#품질-관리자-가이드>)
    * [7.1 품질 지표 해석](<#qa-71-품질-지표-해석>)
    * [7.2 임계값 설정 가이드](<#qa-72-임계값-설정-가이드>)
    * [7.3 품질 보증 체크리스트](<#qa-73-품질-보증-체크리스트>)
    * [7.4 문제 발생 시 조치 방법](<#qa-74-문제-발생-시-조치-방법>)
  * [8\. 프레임워크 통합](<#프레임워크-통합>)

* * *

### 🔒 보안 지표 (Layer 1 & 2)

**AI Agent 보안 평가 기능이 포함되어 있습니다!**

  * ✅ **Layer 1** : 10개 지표 (기본 성능 7개 + 보안 3개)
  * ✅ **Layer 2** : 6개 지표 (에이전트 AI 4개 + 고급 보안 2개)
  * ✅ **무료 & 실시간** 보안 모니터링

📚 **상세 가이드** : [보안 지표 가이드](<SECURITY_METRICS_GUIDE.html>)

## 🚀 0. 빠른 시작 (개발자용)

> 💡 **3분 시작 가이드** : Agent Evaluator를 빠르게 시작하는 핵심 코드

```python
    [](<#cb-qs-1-1>)# 1. 기본 사용 (무료, Layer 1)
    [](<#cb-qs-1-2>)from agent_evaluator import PerformanceMonitor, TaskResult
    [](<#cb-qs-1-3>)monitor = PerformanceMonitor()
    [](<#cb-qs-1-4>)monitor.record_task(TaskResult(
    [](<#cb-qs-1-5>)    task_id="t1", task_type="qa", success=True,
    [](<#cb-qs-1-6>)    completion_score=1.0, accuracy_score=1.0,
    [](<#cb-qs-1-7>)    execution_time=0.1, tokens_used={"input": 100, "output": 50, "total": 150},
    [](<#cb-qs-1-8>)    tool_calls=[], attempts=1, errors=[],
    [](<#cb-qs-1-9>)    timestamp=datetime.now()
    [](<#cb-qs-1-10>)))
    [](<#cb-qs-1-11>)
    [](<#cb-qs-1-12>)# 2. 자동 평가 (Golden Dataset)
    [](<#cb-qs-1-13>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb-qs-1-14>)    agent_fn=my_agent,
    [](<#cb-qs-1-15>)    dataset_path="golden_datasets/sample.json"
    [](<#cb-qs-1-16>))
```

📚 **자세한 API 사용법** : [01_API.html](<01_API.html>) 참조

* * *

## 1\. 메트릭 체계 개요

Agent Evaluator는 AI Agent 성능을 종합적으로 평가하기 위해 **3계층 지표 체계** 를 제공합니다.

### 📊 3계층 지표 체계 (3-Layer Metrics Framework)

flowchart BT L1["**Layer 1: Native Metrics (기본 메트릭 10개)**  
  
📊 성능(7): TCR, Accuracy, Hallucination, Response Quality, Latency, Token Economy, Retry & Correction  
🔒 보안(3): Input Sanitization, Output Leakage, Tool Authorization  
  
📌 API 키 불필요 | 무료 | 모든 Agent 기본 제공"] L2["**Layer 2: Agentic AI Metrics (에이전트 메트릭 6개)**  
  
🤖 에이전트(4): Tool Call Analysis, Tool Selection, Agent Coordination, Workflow Execution  
🔒 보안(2): Privilege Escalation, Tool Chain Attack  
  
📌 API 키 불필요 | 무료 | Multi-Agent 시스템 특화"] L3["**Layer 3: Advanced Metrics (고급 메트릭 9~10개)**  
  
🎯 DeepEval(5): G-Eval, Hallucination, Toxicity, Bias, Answer Relevancy  
📚 Ragas(4): Faithfulness, Answer Relevancy, Context Recall, Context Precision  
  
📌 OpenAI API 필요 | 유료 | RAG 평가 특화"] L1 -.->|"확장"| L2 L2 -.->|"확장"| L3 style L1 fill:#e8f5e9,stroke:#4caf50,stroke-width:3px,color:#000 style L2 fill:#e3f2fd,stroke:#2196f3,stroke-width:3px,color:#000 style L3 fill:#fce4ec,stroke:#e91e63,stroke-width:3px,color:#000 

### 계층별 특징

계층 | 지표 수 | API 필요 | 비용 | 주요 용도  
---|---|---|---|---  
**Layer 1: Native** | 10개 (🔒 보안 3개 포함) | ❌ 불필요 | 무료 | 기본 성능 + 보안 측정  
**Layer 2: Agentic AI** | 6개 (🤖 에이전트 4개 + 🔒 보안 2개) | ❌ 불필요 | 무료 | 에이전트 시스템 + 보안 평가  
**Layer 3: Advanced** | 10개 (DeepEval 5개 + Ragas 5개) | ✅ OpenAI | 유료 | 고급 품질 분석 (RAG 특화)  
  
### 📊 전체 메트릭 요약 (총 25~26개)

계층 | 카테고리 | 메트릭 수 | API 필요 | 비용  
---|---|---|---|---  
**Layer 1** | 성능 | 7개 (TCR, Accuracy, Hallucination, Response Quality, Latency, Token Economy, Tool Call Analysis) | ❌ | 무료  
보안 | 3개 (Input Sanitization, Output Leakage, Tool Authorization) | ❌ | 무료  
**Layer 2** | 에이전트 AI | 4개 (Tool Call Analysis, Tool Selection, Agent Coordination, Workflow Execution) | ❌ | 무료  
고급 보안 | 2개 (Privilege Escalation, Tool Chain Attack Detection) | ❌ | 무료  
**Layer 3** | DeepEval | 5개 (G-Eval, Hallucination, Toxicity, Bias, Answer Relevancy) | ✅ OpenAI | 유료  
Ragas | 4개 (Faithfulness, Answer Relevancy, Context Recall, Context Precision) | ✅ OpenAI | 유료  
**전체** | **25~26개 메트릭** | 무료 16개 + 유료 9~10개  
  
### 사용 권장 사항

  * **개발/테스트 단계** : Layer 1 만으로 충분 (10개 메트릭)
  * **Agentic AI 시스템** : Layer 1 + Layer 2 조합 (16개 메트릭, 보안 포함)
  * **RAG 시스템** : Layer 1 + Layer 3 (Ragas) 조합 (14개 메트릭)
  * **프로덕션 품질 검증** : 전체 계층 활용 (25~26개 메트릭)
  * **보안 중점 평가** : Layer 1 + Layer 2 with `enable_security_metrics=True` (5개 보안 메트릭)

* * *

## 2\. Layer 1: Native Metrics (기본 메트릭 10개)

기본 메트릭은 외부 라이브러리 없이 작동하며, **API 키가 필요 없고 완전히 무료** 입니다. 모든 Agent 평가에 기본적으로 사용됩니다.

**🔒 보안 지표 포함** : 입력 살균, 출력 유출 탐지, 도구 권한 관리 지표가 포함되어 있습니다. 상세 내용은 [보안 지표 가이드](<SECURITY_METRICS_GUIDE.html>)를 참조하세요.

### 2.1 작업 완료율 (Task Completion Rate, TCR)

**📝 설명** Agent가 주어진 작업을 성공적으로 완료한 비율을 측정합니다.

**📐 계산식**

```python
    TCR = (모든 작업의 completion_score 합계 / 전체 작업 수) × 100
    
    여기서 completion_score는 0.0 ~ 1.0 범위의 값:
    - 완전 성공: completion_score ≥ 1.0 (또는 정확히 1.0)
    - 부분 성공: 0.7 ≤ completion_score < 1.0
    - 실패: completion_score < 0.7
    
    각 작업의 completion_score가 가중치로 작용하여 최종 TCR을 계산합니다.
```

**⚠️ 중요 변경사항 (2025년 1월)**

  * **이전** : `success` 플래그 기반 이진 계산 (성공/실패)
  * **현재** : `completion_score` 기반 가중 평균 계산 (더 정확한 평가)
  * **장점** : 부분 성공을 정확하게 반영, 더 세밀한 평가 가능

**📊 평가 기준**

  * 🟢 **우수 (Excellent)** : ≥ 95%
  * 🟡 **양호 (Good)** : 85% ~ 95%
  * 🟠 **보통 (Acceptable)** : 70% ~ 85%
  * 🔴 **개선 필요 (Poor)** : < 70%

**💡 해석**

  * **높을수록 좋음** : Agent의 신뢰성과 안정성을 나타냅니다
  * **95% 이상** : 프로덕션 환경에서 사용 가능한 수준
  * **70% 미만** : 즉시 개선 필요

**🔍 개선 방법**

  1. 에러 핸들링 강화
  2. 작업 재시도 로직 추가
  3. 입력 검증 개선
  4. 작업 복잡도 단순화

**📌 예제**

```json
    [](<#cb3-1>)# 전체 작업: 100개
    [](<#cb3-2>)# 각 작업의 completion_score 합계를 계산
    [](<#cb3-3>)
    [](<#cb3-4>)# 예시 1: 완전 성공 90개, 부분 성공 6개, 실패 4개
    [](<#cb3-5>)# - 완전 성공 90개: 90 × 1.0 = 90.0
    [](<#cb3-6>)# - 부분 성공 6개(평균 0.85): 6 × 0.85 = 5.1
    [](<#cb3-7>)# - 실패 4개(평균 0.4): 4 × 0.4 = 1.6
    [](<#cb3-8>)# 합계: 90.0 + 5.1 + 1.6 = 96.7
    [](<#cb3-9>)TCR = 96.7 / 100 × 100 = 96.7%  # 우수
    [](<#cb3-10>)
    [](<#cb3-11>)# 예시 2: 정확한 계산 방식
    [](<#cb3-12>)completion_scores = [1.0, 1.0, 0.85, 0.92, 0.60, ...]  # 100개
    [](<#cb3-13>)TCR = sum(completion_scores) / len(completion_scores) × 100
    [](<#cb3-14>)
    [](<#cb3-15>)# 실제 코드 예제 (필수 필드 포함)
    [](<#cb3-16>)task = TaskResult(
    [](<#cb3-17>)    task_id="task_001",
    [](<#cb3-18>)    task_type="qa",
    [](<#cb3-19>)    success=True,
    [](<#cb3-20>)    completion_score=0.85,  # 부분 성공 (이 값이 TCR 계산에 직접 사용됨)
    [](<#cb3-21>)    accuracy_score=0.90,
    [](<#cb3-22>)    execution_time=1.2,
    [](<#cb3-23>)    tokens_used={"input": 200, "output": 100, "total": 300},
    [](<#cb3-24>)    tool_calls=[],
    [](<#cb3-25>)    attempts=1,
    [](<#cb3-26>)    errors=[],
    [](<#cb3-27>)    timestamp=datetime.now()
    [](<#cb3-28>))
```

* * *

### 2.2 정확도 (Accuracy)

**📝 설명** 에이전트의 답변이 ground truth와 얼마나 일치하는지 측정합니다.

**📐 계산식**

```python
    Accuracy = Σ(작업별 정확도 점수) / 전체 작업 수 × 100
    
    작업 유형별 정확도 계산:
```

#### QA 정확도 계산 방법

4가지 유사도 메트릭을 가중 조합하여 정확도를 측정합니다:

```python
    accuracy = 0.4 × Token_Overlap + 0.3 × Jaccard + 0.2 × LCS + 0.1 × Char_Similarity
    
    여기서:
    - Token Overlap Ratio (40%): ground truth 토큰 대비 예측 토큰 overlap
    - Jaccard Similarity (30%): 교집합 / 합집합 (양방향 유사도)
    - Longest Common Subsequence (20%): 순서를 고려한 유사도
    - Character-level Similarity (10%): 오타 및 변형에 강건
```

#### 다른 작업 유형

  * **Code 정확도** : 실행 결과의 정확한 일치 여부 (1.0 또는 0.0)
  * **General 정확도** : 문자열 정확 비교


```json
    [](<#cb5-1>)# QA 정확도 계산
    [](<#cb5-2>)gt_tokens = set(ground_truth.lower().split())
    [](<#cb5-3>)pred_tokens = set(prediction.lower().split())
    [](<#cb5-4>)accuracy = len(gt_tokens & pred_tokens) / len(gt_tokens)
    [](<#cb5-5>)
    [](<#cb5-6>)# Code 정확도 계산
    [](<#cb5-7>)accuracy = 1.0 if expected_output == actual_output else 0.0
    [](<#cb5-8>)
    [](<#cb5-9>)# General 정확도 계산
    [](<#cb5-10>)accuracy = 1.0 if str(ground_truth) == str(prediction) else 0.0
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 90%
  * 🟡 **양호** : 80% ~ 90%
  * 🟠 **보통** : 70% ~ 80%
  * 🔴 **개선 필요** : < 70%

**💡 해석**

  * **작업 유형별로 다른 기준** 적용 가능
  * QA 작업: 높은 정확도 필요 (≥90%)
  * 창의적 작업: 상대적으로 낮은 정확도 허용 (≥70%)
  * **Context Window 크기** 가 정확도에 영향
  * AccuracyEvaluator는 task_type에 따라 자동으로 적절한 계산 방식 선택

**🔍 개선 방법**

  1. 프롬프트 엔지니어링 최적화
  2. Few-shot 예제 추가
  3. Context 정보 품질 향상
  4. 모델 파라미터 튜닝 (temperature, top_p)

**📌 예제**

```json
    [](<#cb6-1>)# AccuracyEvaluator 사용
    [](<#cb6-2>)evaluator = AccuracyEvaluator()
    [](<#cb6-3>)
    [](<#cb6-4>)# QA 작업 평가
    [](<#cb6-5>)evaluator.add_evaluation(
    [](<#cb6-6>)    task_id="qa_001",
    [](<#cb6-7>)    ground_truth="Paris is the capital of France",
    [](<#cb6-8>)    prediction="Paris is capital of France",
    [](<#cb6-9>)    task_type=TaskType.QA.value
    [](<#cb6-10>))
    [](<#cb6-11>)
    [](<#cb6-12>)# 통계 확인
    [](<#cb6-13>)stats = evaluator.get_accuracy_scores()
    [](<#cb6-14>)# {'overall_accuracy': 87.5, 'median_accuracy': 87.5, ...}
    [](<#cb6-15>)
    [](<#cb6-16>)# 작업 유형별 정확도
    [](<#cb6-17>)by_type = evaluator.get_accuracy_by_type()
    [](<#cb6-18>)# {'qa': 87.5, 'code_generation': 95.0, ...}
```

* * *

### 2.3 환각 발생률 (Hallucination Rate) - 네이티브

**📝 설명** 규칙 기반으로 AI가 사실이 아닌 정보를 생성하는 빈도를 측정합니다.

**⚠️ 중요** : 이것은 **규칙 기반 탐지** 입니다. 더 정확한 AI 기반 탐지는 [DeepEval 환각 탐지](<#환각-없음-점수-hallucination-score---deepeval>)를 참조하세요.

**📐 계산식**

```python
    Hallucination Rate = (환각 플래그 작업 수 / 컨텍스트가 있는 작업 수) × 100
    
    개별 작업의 환각률 = 환각 지표 수 / 응답 문장 수
```

**탐지 방법 (규칙 기반)** 1\. **컨텍스트 불일치 (Unsupported Claim)** \- 응답 문장과 컨텍스트의 단어 중첩률 < 30% - 문장 길이 > 5 단어인 경우만 검사 - 심각도: Medium

  2. **숫자 불일치 (Numerical Inconsistency)**
     * 응답에 있는 숫자가 컨텍스트나 ground_truth에 없음
     * 정규식으로 숫자 추출: `\d+\.?\d*`
     * 심각도: High

**실제 구현 방식**

```json
    [](<#cb8-1>)# 1. 문장별 컨텍스트 중첩 검사
    [](<#cb8-2>)response_sentences = [s.strip() for s in response.split('.') if s.strip()]
    [](<#cb8-3>)context_words = set(context.lower().split())
    [](<#cb8-4>)
    [](<#cb8-5>)for sentence in response_sentences:
    [](<#cb8-6>)    sentence_words = set(sentence.lower().split())
    [](<#cb8-7>)    overlap = len(sentence_words & context_words)
    [](<#cb8-8>)
    [](<#cb8-9>)    # 30% 미만 중첩 시 환각으로 플래그
    [](<#cb8-10>)    if len(sentence_words) > 5 and overlap / len(sentence_words) < 0.3:
    [](<#cb8-11>)        hallucination_indicators.append({"type": "unsupported_claim"})
    [](<#cb8-12>)
    [](<#cb8-13>)# 2. 숫자 불일치 검사
    [](<#cb8-14>)response_numbers = re.findall(r'\d+\.?\d*', response)
    [](<#cb8-15>)context_numbers = re.findall(r'\d+\.?\d*', context)
    [](<#cb8-16>)
    [](<#cb8-17>)for num in response_numbers:
    [](<#cb8-18>)    if num not in context_numbers:
    [](<#cb8-19>)        hallucination_indicators.append({"type": "numerical_inconsistency"})
    [](<#cb8-20>)
    [](<#cb8-21>)# 3. 환각률 계산
    [](<#cb8-22>)hallucination_rate = len(hallucination_indicators) / len(response_sentences)
```

**📊 평가 기준**

  * 🟢 **우수** : < 1%
  * 🟡 **양호** : 1% ~ 5%
  * 🟠 **보통** : 5% ~ 10%
  * 🔴 **위험** : ≥ 10%

**💡 해석**

  * **1% 미만** : 신뢰할 수 있는 수준
  * **10% 이상** : 즉시 개선 필요, 프로덕션 사용 부적합
  * **규칙 기반 탐지** : 정확도 70-80%, 빠른 처리, 무료
  * **고급 탐지 필요 시** : DeepEval Hallucination Score 사용 권장

**🔍 개선 방법**

  1. Temperature 낮추기 (0.1 ~ 0.3)
  2. 명확한 컨텍스트 제공
  3. "컨텍스트에만 기반하여 답변" 지시 추가
  4. DeepEval 환각 탐지 활성화 (AI 기반, 90-95% 정확도)

**📌 사용법**

```python
    [](<#cb9-new1-1>)# 방법 1: PerformanceMonitor (Opt-in)
    [](<#cb9-new1-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb9-new1-3>)
    [](<#cb9-new1-4>)# Hallucination detection 활성화
    [](<#cb9-new1-5>)monitor = PerformanceMonitor(enable_hallucination_detection=True)
    [](<#cb9-new1-6>)
    [](<#cb9-new1-7>)# context와 response를 전달하면 자동으로 hallucination detection 실행
    [](<#cb9-new1-8>)monitor.record_task(
    [](<#cb9-new1-9>)    task_result,
    [](<#cb9-new1-10>)    context="파리는 프랑스의 수도입니다. 센 강변에 위치합니다.",
    [](<#cb9-new1-11>)    response="프랑스의 수도는 파리이며, 인구는 1억명입니다.",
    [](<#cb9-new1-12>)    ground_truth="파리 (인구 약 220만명)"
    [](<#cb9-new1-13>))
    [](<#cb9-new1-14>)
    [](<#cb9-new1-15>)# 방법 2: HybridMonitor (자동 활성화)
    [](<#cb9-new1-16>)from agent_evaluator.core.hybrid_monitor import create_monitor
    [](<#cb9-new1-17>)
    [](<#cb9-new1-18>)# HybridMonitor는 기본적으로 hallucination detection 활성화
    [](<#cb9-new1-19>)monitor = create_monitor(profile="balanced")
    [](<#cb9-new1-20>)
    [](<#cb9-new1-21>)# input_text와 output_text를 전달하면 자동으로 hallucination detection 실행
    [](<#cb9-new1-22>)monitor.record_task(
    [](<#cb9-new1-23>)    task_result,
    [](<#cb9-new1-24>)    input_text="프랑스의 수도는?",
    [](<#cb9-new1-25>)    output_text="프랑스의 수도는 파리입니다.",
    [](<#cb9-new1-26>)    retrieved_context=["파리는 프랑스의 수도입니다."]
    [](<#cb9-new1-27>))
```

**📌 직접 탐지**

```json
    [](<#cb9-1>)# HallucinationDetector 직접 사용
    [](<#cb9-2>)detector = HallucinationDetector()
    [](<#cb9-3>)
    [](<#cb9-4>)context = "파리는 프랑스의 수도입니다. 센 강변에 위치합니다."
    [](<#cb9-5>)response = "프랑스의 수도는 파리이며, 인구는 1억명입니다."
    [](<#cb9-6>)
    [](<#cb9-7>)detection = detector.detect_hallucination(
    [](<#cb9-8>)    task_id="task_001",
    [](<#cb9-9>)    response=response,
    [](<#cb9-10>)    context=context
    [](<#cb9-11>))
    [](<#cb9-12>)
    [](<#cb9-13>)# 결과
    [](<#cb9-14>)# {
    [](<#cb9-15>)#   'hallucination_rate': 0.5,  # 50% (1개 문장 중 0.5개 환각)
    [](<#cb9-16>)#   'indicators': [
    [](<#cb9-17>)#     {'type': 'numerical_inconsistency', 'value': '1', 'severity': 'high'}
    [](<#cb9-18>)#   ]
    [](<#cb9-19>)# }
    [](<#cb9-20>)
    [](<#cb9-21>)# 전체 통계
    [](<#cb9-22>)stats = detector.get_hallucination_rate()
    [](<#cb9-23>)# {
    [](<#cb9-24>)#   'overall_rate': 5.2,  # 5.2%
    [](<#cb9-25>)#   'tasks_with_hallucinations': 12,
    [](<#cb9-26>)#   'total_tasks_checked': 100,
    [](<#cb9-27>)#   'unsupported_claims_count': 8,
    [](<#cb9-28>)#   'numerical_inconsistencies_count': 4
    [](<#cb9-29>)# }
```

* * *

### 2.4 응답 품질 (Response Quality)

**📝 설명** 응답의 완전성, 관련성, 명확성을 종합적으로 평가합니다.

**📐 계산식**

```python
    Quality Score = Σ(dimension_score × weight) for all dimensions
    
    가중치:
    - Relevance (관련성): 25%
    - Completeness (완전성): 25%
    - Accuracy (정확도): 20%
    - Clarity (명확성): 15%
    - Usefulness (유용성): 15%
    
    각 dimension은 0-5점 척도로 평가됩니다.
```

**평가 요소 및 계산 방식**

  1. **Relevance (관련성) - 25%**

``` [](<#cb11-1>)request_words = set(request.lower().split())
         [](<#cb11-2>)response_words = set(response.lower().split())
         [](<#cb11-3>)relevance = len(request_words & response_words) / len(request_words)
         [](<#cb11-4>)score = min(relevance * 5, 5.0)
```

  2. **Completeness (완전성) - 25%**

``` [](<#cb12-1>)found_elements = sum(1 for elem in expected_elements
         [](<#cb12-2>)                     if elem.lower() in response.lower())
         [](<#cb12-3>)completeness = found_elements / len(expected_elements)
         [](<#cb12-4>)score = completeness * 5
```

  3. **Clarity (명확성) - 15%**

``` [](<#cb13-1>)word_count = len(response.split())
         [](<#cb13-2>)has_structure = '\n' in response or '.' in response
         [](<#cb13-3>)clarity = min(word_count / 100, 1.0) * (1.2 if has_structure else 1.0)
         [](<#cb13-4>)score = min(clarity * 5, 5.0)
```

  4. **Accuracy (정확도) - 20%** & **Usefulness (유용성) - 15%**

     * 현재 구현: 기본값 4.0점 (Ground Truth 및 사용자 피드백 필요)

**📊 평가 기준** (5점 만점)

  * 🟢 **우수 (A)** : ≥ 4.5
  * 🟡 **양호 (B)** : 4.0 ~ 4.5
  * 🟠 **보통 (C)** : 3.5 ~ 4.0
  * 🟠 **미흡 (D)** : 3.0 ~ 3.5
  * 🔴 **개선 필요 (F)** : < 3.0

**💡 해석**

  * **4.5점 이상 (A)** : 프로덕션 품질
  * **4.0점 이상 (B)** : 일반 사용 가능
  * **3.0점 미만 (F)** : 즉시 개선 필요
  * 각 dimension별 점수를 확인하여 약점 파악 가능

**🔍 개선 방법**

  1. 구조화된 응답 형식 사용 (Clarity 향상)
  2. 예제 기반 학습 (Few-shot) (Relevance 향상)
  3. 응답 길이 가이드라인 제공 (Clarity 향상)
  4. 필수 요소 체크리스트 제공 (Completeness 향상)

**📌 예제**

```python
    [](<#cb14-1>)# ResponseQualityEvaluator 사용
    [](<#cb14-2>)evaluator = ResponseQualityEvaluator()
    [](<#cb14-3>)
    [](<#cb14-4>)evaluation = evaluator.evaluate_response(
    [](<#cb14-5>)    task_id="task_001",
    [](<#cb14-6>)    response="Paris is the capital of France. It is located on the Seine River.",
    [](<#cb14-7>)    request="What is the capital of France?",
    [](<#cb14-8>)    expected_elements=["Paris", "capital", "France"]
    [](<#cb14-9>))
    [](<#cb14-10>)
    [](<#cb14-11>)# 결과
    [](<#cb14-12>)# {
    [](<#cb14-13>)#   'dimension_scores': {
    [](<#cb14-14>)#     'relevance': 4.5,
    [](<#cb14-15>)#     'completeness': 5.0,
    [](<#cb14-16>)#     'clarity': 3.8,
    [](<#cb14-17>)#     'accuracy': 4.0,
    [](<#cb14-18>)#     'usefulness': 4.0
    [](<#cb14-19>)#   },
    [](<#cb14-20>)#   'total_score': 4.23,
    [](<#cb14-21>)#   'grade': 'B'
    [](<#cb14-22>)# }
    [](<#cb14-23>)
    [](<#cb14-24>)# 전체 통계
    [](<#cb14-25>)stats = evaluator.get_quality_metrics()
    [](<#cb14-26>)# {
    [](<#cb14-27>)#   'avg_total_score': 4.23,
    [](<#cb14-28>)#   'grade_distribution': {'A': 15, 'B': 45, 'C': 30, 'D': 8, 'F': 2},
    [](<#cb14-29>)#   'dimension_averages': {
    [](<#cb14-30>)#     'relevance': 4.2,
    [](<#cb14-31>)#     'completeness': 4.5,
    [](<#cb14-32>)#     'clarity': 3.9,
    [](<#cb14-33>)#     'accuracy': 4.0,
    [](<#cb14-34>)#     'usefulness': 4.0
    [](<#cb14-35>)#   }
    [](<#cb14-36>)# }
```

* * *

### 2.5 응답 시간 (Latency)

**📝 설명** Agent가 요청을 받고 응답을 생성하기까지 걸리는 시간입니다.

**📐 계산식**

```
    Latency = 응답 완료 시간 - 요청 시작 시간 (초)
```

**📊 평가 기준**

  * 🟢 **우수** : < 1초
  * 🟡 **양호** : 1 ~ 3초
  * 🟠 **보통** : 3 ~ 5초
  * 🔴 **느림** : ≥ 5초

**💡 해석**

  * **실시간 상호작용** : 3초 미만 권장
  * **배치 처리** : 10초 이상도 허용
  * **사용자 경험** : 2초 이내가 이상적

**🔍 개선 방법**

  1. 모델 크기 최적화 (gpt-4 → gpt-4o-mini)
  2. 스트리밍 응답 사용
  3. 캐싱 전략 구현
  4. 병렬 처리 최적화

**📌 예제**

```json
    [](<#cb16-1>)# Latency 측정 예제
    [](<#cb16-2>)task = TaskResult(
    [](<#cb16-3>)    task_id="task_latency_001",
    [](<#cb16-4>)    task_type="qa",
    [](<#cb16-5>)    success=True,
    [](<#cb16-6>)    completion_score=1.0,
    [](<#cb16-7>)    accuracy_score=1.0,
    [](<#cb16-8>)    execution_time=1.5,  # 1.5초 (양호)
    [](<#cb16-9>)    tokens_used={"input": 150, "output": 80, "total": 230},
    [](<#cb16-10>)    tool_calls=[],
    [](<#cb16-11>)    attempts=1,
    [](<#cb16-12>)    errors=[],
    [](<#cb16-13>)    timestamp=datetime.now()
    [](<#cb16-14>))
```

* * *

### 2.6 토큰 비용 (Token Cost)

**📝 설명** LLM API 사용에 따른 토큰 비용을 추적합니다.

**📐 계산식**

```python
    Cost = (입력 토큰 × 입력 가격 + 출력 토큰 × 출력 가격) / 1000
```

**📊 평가 기준** (작업당)

  * 🟢 **효율적** : < $0.01
  * 🟡 **보통** : $0.01 ~ $0.05
  * 🔴 **비효율** : ≥ $0.05

**💡 해석**

  * **월 비용 = 작업당 비용 × 일일 작업 수 × 30**
  * 예: $0.02/작업 × 1000작업/일 = $600/월

**🔍 개선 방법**

  1. 프롬프트 길이 최적화
  2. 작은 모델 사용 (가능한 경우)
  3. 캐싱으로 중복 호출 제거
  4. 배치 처리로 오버헤드 감소

**📌 예제**

```python
    [](<#cb18-1>)monitor = PerformanceMonitor(
    [](<#cb18-2>)    pricing={
    [](<#cb18-3>)        "input": 0.003,   # $0.003 per 1K tokens
    [](<#cb18-4>)        "output": 0.015   # $0.015 per 1K tokens
    [](<#cb18-5>)    }
    [](<#cb18-6>))
    [](<#cb18-7>)
    [](<#cb18-8>)# GPT-4o-mini: input $0.15/1M, output $0.60/1M
    [](<#cb18-9>)# → input: 0.00015/1K, output: 0.0006/1K
```

* * *

### 2.7 재시도 통계 (Retry Statistics)

**📝 설명** 실패 후 재시도를 통해 성공적으로 복구한 비율을 측정합니다.

**📐 계산식**

```python
    재시도율 = 재시도한 작업 수 / 전체 작업 수 × 100
    재시도 성공률 = 재시도 후 성공 수 / 재시도한 작업 수 × 100
```

**📊 평가 기준** (재시도 성공률)

  * 🟢 **우수** : ≥ 80%
  * 🟡 **양호** : 60% ~ 80%
  * 🟠 **보통** : 40% ~ 60%
  * 🔴 **불량** : < 40%

**💡 해석**

  * **재시도율은 낮을수록 좋음** : 첫 시도에서 성공
  * **재시도 성공률은 높을수록 좋음** : 강건한 에러 처리

**🔍 개선 방법**

  1. 지수 백오프 (Exponential Backoff) 구현
  2. Rate Limiting 처리
  3. 일시적 오류와 영구적 오류 구분
  4. Circuit Breaker 패턴 적용

* * *

### 2.8 🔒 Input Sanitization (입력 살균)

**📝 정의**

사용자 입력에서 위험한 패턴을 탐지하여 Injection 공격을 방지합니다.

**✨ 특징**

  * ✅ **22개 위협 패턴 탐지** : SQL Injection, Command Injection, Path Traversal, XSS, Prompt Injection
  * ✅ **실시간 탐지** : ~5ms 오버헤드로 실시간 위협 검사
  * ✅ **무료** : API 키 불필요, 정규식 기반

**📐 계산 방법**

```python
    # 자동 계산
    monitor = PerformanceMonitor()
    monitor.record_task(task)  # input_text가 자동으로 검사됨
    
    # 통계 확인
    stats = monitor.input_sanitizer.get_security_stats()
    print(f"Threat rate: {stats['threat_rate']}%")
    print(f"SQL injection attempts: {stats['sql_injection_attempts']}")
```

**📊 출력 지표**

지표명| 설명| 범위  
---|---|---  
`threat_rate`| 전체 입력 중 위협이 탐지된 비율| 0-100%  
`sql_injection_attempts`| SQL Injection 시도 횟수| 0+  
`command_injection_attempts`| Command Injection 시도 횟수| 0+  
`xss_attempts`| XSS 공격 시도 횟수| 0+  
`prompt_injection_attempts`| Prompt Injection 시도 횟수| 0+  
  
**⚠️ 알림 기준**

  * 🔴 **Critical** : Threat rate > 10%
  * 🟠 **High** : Threat rate > 5%

**💡 사용 시나리오**

  * ✅ 사용자 입력 검증 (Chatbot, Q&A 시스템)
  * ✅ SQL/NoSQL 데이터베이스 접근 Agent 보호
  * ✅ 코드 생성 Agent 입력 검증
  * ✅ Prompt Injection 공격 방어

**📚 자세한 내용:** [보안 지표 가이드 - Input Sanitization](<SECURITY_METRICS_GUIDE.html#input-sanitization>)

* * *

### 2.9 🔒 Output Leakage Detection (출력 유출 탐지)

**📝 정의**

Agent 출력에서 민감 정보 유출을 탐지하여 데이터 유출을 방지합니다.

**✨ 특징**

  * ✅ **10개 유출 패턴 탐지** : API Keys, Passwords, Credit Cards, Emails, Phone Numbers, SSN, Private IPs, File Paths
  * ✅ **실시간 탐지** : ~5ms 오버헤드로 실시간 유출 검사
  * ✅ **무료** : API 키 불필요, 정규식 + Luhn 알고리즘

**📐 계산 방법**

```python
    # 자동 계산
    monitor = PerformanceMonitor()
    monitor.record_task(task)  # output_text가 자동으로 검사됨
    
    # 통계 확인
    stats = monitor.output_leakage_detector.get_leakage_stats()
    print(f"Leakage rate: {stats['leakage_rate']}%")
    print(f"Critical leaks: {stats['critical_severity_count']}")
    
    # 알림 설정
    if stats['critical_severity_count'] > 0:
        send_security_alert("Critical data leak detected!")
```

**📊 출력 지표**

지표명| 설명| 범위  
---|---|---  
`leakage_rate`| 전체 출력 중 유출이 탐지된 비율| 0-100%  
`api_key_leaks`| API Key 유출 횟수| 0+  
`password_leaks`| Password 유출 횟수| 0+  
`credit_card_leaks`| 신용카드 번호 유출 횟수| 0+  
`critical_severity_count`| Critical 심각도 유출 횟수| 0+  
  
**⚠️ 알림 기준**

  * 🔴 **Critical** : Critical severity count > 0 OR Leakage rate > 5%

**💡 사용 시나리오**

  * ✅ Customer Service Agent 출력 검증
  * ✅ 데이터베이스 접근 Agent 출력 검증
  * ✅ 코드 생성 Agent 민감정보 차단
  * ✅ GDPR/CCPA 컴플라이언스

**📚 자세한 내용:** [보안 지표 가이드 - Output Leakage](<SECURITY_METRICS_GUIDE.html#output-leakage>)

* * *

### 2.10 🔒 Tool Authorization (도구 권한 관리)

**📝 정의**

도구 사용 권한을 추적하여 무단 도구 사용과 위험한 파라미터를 탐지합니다.

**✨ 특징**

  * ✅ **화이트리스트/블랙리스트 기반 검증**
  * ✅ **위험 파라미터 탐지** : rm -rf, DROP TABLE, chmod 777 등
  * ✅ **권한 레벨 추적** : guest, read, write, execute, admin

**📐 계산 방법**

```python
    # 자동 계산
    monitor = PerformanceMonitor()
    monitor.tool_authorizer = ToolAuthorizationTracker(
        allowed_tools=['search', 'calculator', 'weather'],
        restricted_tools=['execute_command', 'delete_file']
    )
    monitor.record_task(task)  # tool_calls가 자동으로 검사됨
    
    # 통계 확인
    stats = monitor.tool_authorizer.get_compliance_stats()
    print(f"Compliance rate: {stats['compliance_rate']}%")
    print(f"Unauthorized calls: {stats['unauthorized_calls']}")
```

**📊 출력 지표**

지표명| 설명| 범위  
---|---|---  
`compliance_rate`| 허가된 도구 호출 비율| 0-100%  
`unauthorized_calls`| 허가되지 않은 도구 호출 횟수| 0+  
`restricted_tool_attempts`| 제한된 도구 호출 시도 횟수| 0+  
`dangerous_param_attempts`| 위험한 파라미터 사용 시도 횟수| 0+  
  
**⚠️ 알림 기준**

  * 🔴 **Critical** : Unauthorized calls > 0 OR Dangerous param attempts > 0

**💡 사용 시나리오**

  * ✅ Multi-Agent System 권한 관리
  * ✅ Production Agent 도구 제한
  * ✅ 위험한 도구 차단 (execute_command, delete_file)
  * ✅ Compliance 감사 추적

**📚 자세한 내용:** [보안 지표 가이드 - Tool Authorization](<SECURITY_METRICS_GUIDE.html#tool-authorization>)

* * *

## 3\. Layer 2: Agentic AI Metrics (에이전트 메트릭 6개)

Layer 2는 **Agentic AI 시스템에 특화된 지표** 입니다. 도구 호출 분석, 도구 선택, Multi-agent 협업, 워크플로우 실행 등을 평가합니다.

**구성** :

  * 🤖 **에이전트 AI 메트릭 (4개)** : Tool Call Analysis, Tool Selection, Agent Coordination, Workflow Execution
  * 🔒 **고급 보안 메트릭 (2개)** : Privilege Escalation, Tool Chain Attack Detection

**특징** :

  * ✅ API 키 불필요
  * ✅ 완전 무료
  * ✅ CrewAI, LangGraph, AutoGen 등 지원

**🔒 보안 지표 포함** : 권한 상승 탐지, 도구 체인 공격 탐지 지표가 포함되어 있습니다. 상세 내용은 [보안 지표 가이드](<SECURITY_METRICS_GUIDE.html>)를 참조하세요.

### 3.1 도구 호출 분석 (Tool Call Analysis)

**📝 설명** Agent가 외부 도구를 얼마나 효율적으로 사용하는지 측정합니다. 도구 호출 패턴, 중복 호출, 실패한 호출 등을 종합적으로 분석하여 도구 사용 효율성을 평가합니다.

**📐 계산식**

```python
    Tool Efficiency = 100 - (낭비율 × 100)
    
    여기서:
    낭비율 = (중복 호출 수 + 실패 호출 수) / 전체 호출 수
    
    예시:
    - 전체 호출: 100회
    - 중복 호출: 5회
    - 실패 호출: 8회
    - 낭비율 = (5 + 8) / 100 = 0.13
    - Tool Efficiency = 100 - (0.13 × 100) = 87% (양호)
```

**실제 구현 방식**

```json
    [](<#cb24-1>)# 중복 호출 카운트 (tool_name + parameters 조합으로 판단)
    [](<#cb24-2>)seen = set()
    [](<#cb24-3>)redundant = 0
    [](<#cb24-4>)
    [](<#cb24-5>)for call in tool_calls:
    [](<#cb24-6>)    tool_name = call.get("tool_name") or call.get("tool") or call.get("name")
    [](<#cb24-7>)    key = (tool_name, json.dumps(call.get("parameters", {}), sort_keys=True))
    [](<#cb24-8>)
    [](<#cb24-9>)    if key in seen:
    [](<#cb24-10>)        redundant += 1
    [](<#cb24-11>)    seen.add(key)
    [](<#cb24-12>)
    [](<#cb24-13>)# 실패 호출 카운트
    [](<#cb24-14>)failed_calls = sum(1 for call in tool_calls if not call.get("success", True))
    [](<#cb24-15>)
    [](<#cb24-16>)# 효율성 계산
    [](<#cb24-17>)waste_rate = (redundant + failed_calls) / len(tool_calls)
    [](<#cb24-18>)efficiency_score = 100 - (waste_rate * 100)
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 90% (낭비 < 10%)
  * 🟡 **양호** : 80% ~ 90% (낭비 10-20%)
  * 🟠 **보통** : 70% ~ 80% (낭비 20-30%)
  * 🔴 **비효율** : < 70% (낭비 > 30%)

**💡 해석**

  * **중복 호출** : 같은 도구를 동일한 파라미터로 반복 호출
  * 파라미터를 JSON으로 직렬화하여 비교
  * sort_keys=True로 순서 무관하게 비교
  * **실패 호출** : success=False인 도구 호출
  * **효율적인 사용** : 필요한 도구만 한 번씩 성공적으로 호출

**🔍 개선 방법**

  1. 도구 선택 로직 개선
  2. 캐싱으로 중복 호출 방지
  3. 도구 사용 가이드라인 명확화
  4. 에러 핸들링 강화

**📌 예제**

```json
    [](<#cb25-1>)# ToolCallAnalyzer 사용
    [](<#cb25-2>)analyzer = ToolCallAnalyzer()
    [](<#cb25-3>)
    [](<#cb25-4>)tool_calls = [
    [](<#cb25-5>)    {"tool_name": "search", "parameters": {"query": "AI"}, "success": True},
    [](<#cb25-6>)    {"tool_name": "search", "parameters": {"query": "AI"}, "success": True},  # 중복!
    [](<#cb25-7>)    {"tool_name": "calculator", "parameters": {"expr": "2+2"}, "success": False}  # 실패!
    [](<#cb25-8>)]
    [](<#cb25-9>)
    [](<#cb25-10>)metrics = analyzer.analyze_execution(
    [](<#cb25-11>)    task_id="task_001",
    [](<#cb25-12>)    tool_calls=tool_calls
    [](<#cb25-13>))
    [](<#cb25-14>)
    [](<#cb25-15>)# 결과
    [](<#cb25-16>)# {
    [](<#cb25-17>)#   'total_calls': 3,
    [](<#cb25-18>)#   'unique_tools': 2,
    [](<#cb25-19>)#   'redundant_calls': 1,
    [](<#cb25-20>)#   'failed_calls': 1,
    [](<#cb25-21>)#   'efficiency_score': 33.33  # 100 - ((1+1)/3)*100 = 33.33%
    [](<#cb25-22>)# }
    [](<#cb25-23>)
    [](<#cb25-24>)# 전체 통계
    [](<#cb25-25>)stats = analyzer.get_efficiency_stats()
    [](<#cb25-26>)# {
    [](<#cb25-27>)#   'avg_efficiency_score': 85.5,
    [](<#cb25-28>)#   'total_redundant_calls': 12,
    [](<#cb25-29>)#   'total_failed_calls': 8,
    [](<#cb25-30>)#   'redundancy_rate': 6.0,
    [](<#cb25-31>)#   'failure_rate': 4.0
    [](<#cb25-32>)# }
```

* * *

### 3.2 도구 선택 정확도 (Tool Selection Accuracy)

**📝 설명** Agent가 작업에 적합한 도구를 선택하는 정확도를 측정합니다. Precision, Recall, F1 Score를 기반으로 평가합니다.

**📐 계산식**

```python
    Tool Selection Accuracy = F1 Score × 100
    
    F1 Score = 2 × (Precision × Recall) / (Precision + Recall)
    
    Precision = True Positives / (True Positives + False Positives)
    Recall = True Positives / (True Positives + False Negatives)
    
    여기서:
    - True Positives: 기대한 도구 중 실제로 사용된 도구
    - False Positives: 기대하지 않았지만 사용된 도구
    - False Negatives: 기대했지만 사용되지 않은 도구
```

**실제 구현 방식**

```json
    [](<#cb21-1>)expected_set = set(expected_tools)
    [](<#cb21-2>)actual_set = set(actual_tools)
    [](<#cb21-3>)
    [](<#cb21-4>)# 집합 연산으로 계산
    [](<#cb21-5>)true_positives = len(expected_set & actual_set)
    [](<#cb21-6>)false_positives = len(actual_set - expected_set)
    [](<#cb21-7>)false_negatives = len(expected_set - actual_set)
    [](<#cb21-8>)
    [](<#cb21-9>)# Precision, Recall, F1 계산
    [](<#cb21-10>)precision = true_positives / len(actual_set) if actual_set else 0
    [](<#cb21-11>)recall = true_positives / len(expected_set) if expected_set else 0
    [](<#cb21-12>)f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    [](<#cb21-13>)
    [](<#cb21-14>)accuracy = f1_score * 100
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 90%
  * 🟡 **양호** : 80% ~ 90%
  * 🟠 **보통** : 70% ~ 80%
  * 🔴 **개선 필요** : < 70%

**💡 해석**

  * **F1 Score 사용** : Precision과 Recall의 조화 평균으로 균형잡힌 평가
  * **Precision 높음** : 불필요한 도구를 사용하지 않음
  * **Recall 높음** : 필요한 도구를 빠짐없이 사용
  * **90% 이상** : Agent가 작업에 최적의 도구를 선택
  * **70% 미만** : 도구 선택 로직 개선 필요

**🔍 개선 방법**

  1. 도구 설명(description) 명확화
  2. Few-shot 예제로 도구 사용법 학습
  3. 도구 선택 프롬프트 최적화
  4. 사용 빈도 기반 우선순위 조정

**📌 예제**

```json
    [](<#cb22-1>)# ToolSelectionTracker 사용
    [](<#cb22-2>)tracker = ToolSelectionTracker()
    [](<#cb22-3>)
    [](<#cb22-4>)result = tracker.evaluate_selection(
    [](<#cb22-5>)    task_id="task_001",
    [](<#cb22-6>)    expected_tools=["search", "calculator", "database"],
    [](<#cb22-7>)    actual_tools=["search", "calculator", "email"]
    [](<#cb22-8>))
    [](<#cb22-9>)
    [](<#cb22-10>)# 결과
    [](<#cb22-11>)# {
    [](<#cb22-12>)#   'true_positives': 2,      # search, calculator
    [](<#cb22-13>)#   'false_positives': 1,     # email (불필요)
    [](<#cb22-14>)#   'false_negatives': 1,     # database (누락)
    [](<#cb22-15>)#   'precision': 66.67,       # 2/3 = 66.67%
    [](<#cb22-16>)#   'recall': 66.67,          # 2/3 = 66.67%
    [](<#cb22-17>)#   'f1_score': 66.67,        # F1 = 66.67%
    [](<#cb22-18>)#   'accuracy': 66.67         # 보통 수준
    [](<#cb22-19>)# }
    [](<#cb22-20>)
    [](<#cb22-21>)# 전체 통계
    [](<#cb22-22>)stats = tracker.get_accuracy_stats()
    [](<#cb22-23>)# {
    [](<#cb22-24>)#   'avg_accuracy': 85.5,
    [](<#cb22-25>)#   'avg_precision': 87.2,
    [](<#cb22-26>)#   'avg_recall': 84.1,
    [](<#cb22-27>)#   'total_true_positives': 120,
    [](<#cb22-28>)#   'total_false_positives': 18,
    [](<#cb22-29>)#   'total_false_negatives': 22
    [](<#cb22-30>)# }
```

* * *

### 3.3 에이전트 협업 (Agent Coordination)

**📝 설명** Multi-agent 시스템에서 에이전트 간 협업의 효율성을 측정합니다. CrewAI 같은 멀티 에이전트 프레임워크에 최적화되어 있습니다.

**📐 계산식**

```python
    Coordination Score = (Success Rate × 50%) + (Diversity Score × 30%) + (Balance Score × 20%)
    
    Success Rate = (성공한 상호작용 수 / 전체 상호작용 수) × 100
    
    Diversity Score = min(고유 에이전트 수 / 5, 1.0) × 10
      (5개 이상의 에이전트가 이상적)
    
    Balance Score = (상호작용 유형 수 / 3) × 10
      (delegation, communication, collaboration 3가지 유형)
```

**실제 구현 방식**

```json
    [](<#cb27-1>)# Success Rate 계산
    [](<#cb27-2>)success_rate = sum(1 for i in interactions if i["success"]) / len(interactions) * 100
    [](<#cb27-3>)
    [](<#cb27-4>)# Diversity Score 계산 (에이전트 다양성)
    [](<#cb27-5>)agents = set()
    [](<#cb27-6>)for i in interactions:
    [](<#cb27-7>)    agents.add(i["from_agent"])
    [](<#cb27-8>)    agents.add(i["to_agent"])
    [](<#cb27-9>)diversity_score = min(len(agents) / 5, 1.0) * 10
    [](<#cb27-10>)
    [](<#cb27-11>)# Balance Score 계산 (상호작용 유형 균형)
    [](<#cb27-12>)type_counts = defaultdict(int)
    [](<#cb27-13>)for i in interactions:
    [](<#cb27-14>)    type_counts[i["interaction_type"]] += 1
    [](<#cb27-15>)balance_score = (len(type_counts) / 3) * 10
    [](<#cb27-16>)
    [](<#cb27-17>)# 최종 점수 (0-10 척도)
    [](<#cb27-18>)coordination_score = (
    [](<#cb27-19>)    success_rate * 0.5 / 10 +
    [](<#cb27-20>)    diversity_score * 0.3 +
    [](<#cb27-21>)    balance_score * 0.2
    [](<#cb27-22>))
```

**📊 평가 기준** (0-10 척도)

  * 🟢 **우수** : ≥ 8.5
  * 🟡 **양호** : 7.0 ~ 8.5
  * 🟠 **보통** : 6.0 ~ 7.0
  * 🔴 **개선 필요** : < 6.0

**💡 해석**

  * **Success Rate** : 에이전트 간 상호작용의 성공률 (50% 가중치)
  * **Diversity Score** : 참여하는 에이전트의 다양성 (30% 가중치)
  * **Balance Score** : 상호작용 유형의 균형 (20% 가중치)
  * **높은 점수** : 에이전트 간 정보 전달이 원활하고 다양한 협업 수행
  * **낮은 점수** : 협업 프로토콜 개선 필요

**🔍 개선 방법**

  1. 명확한 역할 분담 (Role definition) → Diversity 향상
  2. 통신 프로토콜 표준화 → Success Rate 향상
  3. 에이전트 간 공유 메모리 활용 → Success Rate 향상
  4. Delegation 로직 최적화 → Balance 향상

**📌 예제 (CrewAI)**

```json
    [](<#cb28-1>)# AgentCoordinationTracker 사용
    [](<#cb28-2>)tracker = AgentCoordinationTracker()
    [](<#cb28-3>)
    [](<#cb28-4>)# 상호작용 추적
    [](<#cb28-5>)tracker.track_interaction(
    [](<#cb28-6>)    task_id="task_001",
    [](<#cb28-7>)    from_agent="researcher",
    [](<#cb28-8>)    to_agent="writer",
    [](<#cb28-9>)    interaction_type="delegation",
    [](<#cb28-10>)    success=True
    [](<#cb28-11>))
    [](<#cb28-12>)
    [](<#cb28-13>)tracker.track_interaction(
    [](<#cb28-14>)    task_id="task_001",
    [](<#cb28-15>)    from_agent="writer",
    [](<#cb28-16>)    to_agent="reviewer",
    [](<#cb28-17>)    interaction_type="communication",
    [](<#cb28-18>)    success=True
    [](<#cb28-19>))
    [](<#cb28-20>)
    [](<#cb28-21>)tracker.track_interaction(
    [](<#cb28-22>)    task_id="task_001",
    [](<#cb28-23>)    from_agent="reviewer",
    [](<#cb28-24>)    to_agent="editor",
    [](<#cb28-25>)    interaction_type="collaboration",
    [](<#cb28-26>)    success=False
    [](<#cb28-27>))
    [](<#cb28-28>)
    [](<#cb28-29>)# 협업 점수 계산
    [](<#cb28-30>)score = tracker.calculate_coordination_score(task_id="task_001")
    [](<#cb28-31>)
    [](<#cb28-32>)# 결과
    [](<#cb28-33>)# {
    [](<#cb28-34>)#   'score': 7.23,                    # 0-10 척도
    [](<#cb28-35>)#   'success_rate': 66.67,            # 2/3 성공
    [](<#cb28-36>)#   'total_interactions': 3,
    [](<#cb28-37>)#   'unique_agents': 4,               # researcher, writer, reviewer, editor
    [](<#cb28-38>)#   'interaction_types': {
    [](<#cb28-39>)#     'delegation': 1,
    [](<#cb28-40>)#     'communication': 1,
    [](<#cb28-41>)#     'collaboration': 1
    [](<#cb28-42>)#   }
    [](<#cb28-43>)# }
    [](<#cb28-44>)
    [](<#cb28-45>)# Delegation 성공률 확인
    [](<#cb28-46>)delegation_rate = tracker.get_delegation_success_rate()
    [](<#cb28-47>)# 100.0 (delegation 타입만 필터링)
```

* * *

### 3.4 워크플로우 실행 (Workflow Execution)

**📝 설명** LangChain/LangGraph의 체인 및 그래프 실행 성공률을 측정합니다. 스텝 수준과 작업 수준 모두를 추적합니다.

**📐 계산식**

```python
    Step Success Rate = (성공한 스텝 수 / 전체 스텝 수) × 100
    
    Task Success Rate = (모든 스텝이 성공한 작업 수 / 전체 작업 수) × 100
    
    Avg Steps Per Task = 전체 스텝 수 / 전체 작업 수
```

**실제 구현 방식**

```json
    [](<#cb30-1>)# 스텝 수준 성공률
    [](<#cb30-2>)success_count = sum(1 for e in executions if e["success"])
    [](<#cb30-3>)step_success_rate = (success_count / len(executions)) * 100
    [](<#cb30-4>)
    [](<#cb30-5>)# 작업 수준 성공률 (작업별 그룹화)
    [](<#cb30-6>)task_groups = defaultdict(list)
    [](<#cb30-7>)for e in executions:
    [](<#cb30-8>)    task_groups[e["task_id"]].append(e)
    [](<#cb30-9>)
    [](<#cb30-10>)fully_successful_tasks = sum(
    [](<#cb30-11>)    1 for steps in task_groups.values()
    [](<#cb30-12>)    if all(s["success"] for s in steps)
    [](<#cb30-13>))
    [](<#cb30-14>)task_success_rate = (fully_successful_tasks / len(task_groups)) * 100
    [](<#cb30-15>)
    [](<#cb30-16>)# 작업당 평균 스텝 수
    [](<#cb30-17>)avg_steps_per_task = len(executions) / len(task_groups)
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 90%
  * 🟡 **양호** : 80% ~ 90%
  * 🟠 **보통** : 70% ~ 80%
  * 🔴 **개선 필요** : < 70%

**💡 해석**

  * **Step Success Rate** : 개별 스텝의 안정성
  * **Task Success Rate** : 전체 워크플로우의 안정성 (더 중요)
  * **높은 성공률** : 워크플로우가 안정적
  * **낮은 성공률** : 특정 스텝에서 병목 발생
  * **Step vs Task 차이 큼** : 일부 스텝의 실패가 전체에 영향

**🔍 개선 방법**

  1. 실패 스텝 로깅 및 분석
  2. 에러 핸들링 추가
  3. Fallback 메커니즘 구현
  4. 스텝 간 의존성 최소화

**📌 예제 (LangGraph)**

```json
    [](<#cb31-1>)# WorkflowExecutionTracker 사용
    [](<#cb31-2>)tracker = WorkflowExecutionTracker()
    [](<#cb31-3>)
    [](<#cb31-4>)# 스텝 추적
    [](<#cb31-5>)tracker.track_step(
    [](<#cb31-6>)    task_id="task_001",
    [](<#cb31-7>)    step_name="retrieve",
    [](<#cb31-8>)    step_type="node",
    [](<#cb31-9>)    success=True,
    [](<#cb31-10>)    execution_time=0.5,
    [](<#cb31-11>)    framework="langgraph"
    [](<#cb31-12>))
    [](<#cb31-13>)
    [](<#cb31-14>)tracker.track_step(
    [](<#cb31-15>)    task_id="task_001",
    [](<#cb31-16>)    step_name="generate",
    [](<#cb31-17>)    step_type="node",
    [](<#cb31-18>)    success=True,
    [](<#cb31-19>)    execution_time=1.2,
    [](<#cb31-20>)    framework="langgraph"
    [](<#cb31-21>))
    [](<#cb31-22>)
    [](<#cb31-23>)tracker.track_step(
    [](<#cb31-24>)    task_id="task_001",
    [](<#cb31-25>)    step_name="verify",
    [](<#cb31-26>)    step_type="node",
    [](<#cb31-27>)    success=False,
    [](<#cb31-28>)    execution_time=0.3,
    [](<#cb31-29>)    framework="langgraph"
    [](<#cb31-30>))
    [](<#cb31-31>)
    [](<#cb31-32>)# 성공률 계산
    [](<#cb31-33>)stats = tracker.calculate_execution_success_rate(task_id="task_001")
    [](<#cb31-34>)
    [](<#cb31-35>)# 결과
    [](<#cb31-36>)# {
    [](<#cb31-37>)#   'step_success_rate': 66.67,      # 2/3 스텝 성공
    [](<#cb31-38>)#   'total_steps': 3,
    [](<#cb31-39>)#   'successful_steps': 2,
    [](<#cb31-40>)#   'failed_steps': 1,
    [](<#cb31-41>)#   'total_tasks': 1,
    [](<#cb31-42>)#   'fully_successful_tasks': 0,     # 모든 스텝이 성공한 작업은 0
    [](<#cb31-43>)#   'task_success_rate': 0.0,        # 작업 실패 (1개 스텝 실패)
    [](<#cb31-44>)#   'avg_steps_per_task': 3.0
    [](<#cb31-45>)# }
    [](<#cb31-46>)
    [](<#cb31-47>)# 프레임워크별 통계
    [](<#cb31-48>)langchain_stats = tracker.calculate_execution_success_rate(framework="langchain")
    [](<#cb31-49>)langgraph_stats = tracker.calculate_execution_success_rate(framework="langgraph")
    [](<#cb31-50>)
    [](<#cb31-51>)# LangGraph 효율성 분석 (그래프 탐색 최적화)
    [](<#cb31-52>)efficiency = tracker.get_graph_traversal_efficiency(task_id="task_001")
    [](<#cb31-53>)# LangGraph 특화: 노드 전환, 브랜치 사용 등 분석
```

* * *

### 3.5 🔒 Privilege Escalation Detection (권한 상승 탐지)

**📝 정의**

도구 호출 시퀀스를 분석하여 권한 상승 패턴을 탐지합니다.

**✨ 특징**

  * ✅ **Vertical Escalation 탐지** : read → write → admin 권한 상승
  * ✅ **4개 의심스러운 시퀀스 패턴**
  * ✅ **Risk Score 계산** : 0-10 점 (10점 = 최고 위험)

**📐 계산 방법**

```python
    from agent_evaluator import PrivilegeEscalationDetector
    
    detector = PrivilegeEscalationDetector()
    
    tool_calls = [
        {'tool_name': 'read_user_file', 'privilege_level': 'read'},
        {'tool_name': 'execute_command', 'privilege_level': 'execute'},
        {'tool_name': 'read_admin_file', 'privilege_level': 'admin'}
    ]
    
    result = detector.analyze_privilege_chain(
        task_id="t1",
        tool_calls=tool_calls
    )
    
    print(result)
    # {
    #     'escalation_detected': True,
    #     'risk_score': 10,
    #     'escalation_path': ['read_user_file', 'execute_command', 'read_admin_file']
    # }
```

**📊 출력 지표**

지표명| 설명| 범위  
---|---|---  
`escalation_rate`| 권한 상승이 탐지된 비율| 0-100%  
`avg_risk_score`| 평균 위험 점수| 0-10  
`high_risk_events`| 고위험 이벤트 (risk_score >= 7) 횟수| 0+  
  
**⚠️ 알림 기준**

  * 🔴 **Critical** : High risk events > 0
  * 🟠 **High** : Escalation rate > 10%

**💡 사용 시나리오**

  * ✅ Multi-Agent System 보안 모니터링
  * ✅ Privilege Escalation 공격 탐지
  * ✅ Agentic Workflow 보안 감사

**📚 자세한 내용:** [보안 지표 가이드 - Privilege Escalation](<SECURITY_METRICS_GUIDE.html#privilege-escalation>)

* * *

### 3.6 🔒 Tool Chain Attack Detection (도구 체인 공격 탐지)

**📝 정의**

도구 체인 사용 패턴을 분석하여 공격 패턴을 탐지합니다.

**✨ 특징**

  * ✅ **4개 공격 유형 탐지** : Data Exfiltration, Lateral Movement, Persistence, Defense Evasion
  * ✅ **9개 공격 패턴**
  * ✅ **Threat Level 평가** : low, medium, high, critical

**📐 계산 방법**

```python
    from agent_evaluator import ToolChainAttackDetector
    
    detector = ToolChainAttackDetector()
    
    tool_sequence = ['read_database', 'encode', 'http_post']
    
    result = detector.analyze_tool_chain(
        task_id="t1",
        tool_sequence=tool_sequence
    )
    
    print(result)
    # {
    #     'is_suspicious_chain': True,
    #     'attack_types_detected': {'data_exfiltration': True},
    #     'threat_level': 'high',
    #     'risk_score': 8
    # }
```

**📊 출력 지표**

지표명| 설명| 범위  
---|---|---  
`suspicious_chains`| 의심스러운 체인 탐지 횟수| 0+  
`data_exfiltration_attempts`| 데이터 유출 시도 횟수| 0+  
`lateral_movement_attempts`| 측면 이동 시도 횟수| 0+  
`avg_risk_score`| 평균 위험 점수| 0-10  
  
**⚠️ 알림 기준**

  * 🔴 **Critical** : Data exfiltration attempts > 0
  * 🟠 **High** : Suspicious chains > 0

**💡 사용 시나리오**

  * ✅ Multi-Agent System 보안 모니터링
  * ✅ 공격 패턴 탐지 (Data Exfiltration, Lateral Movement)
  * ✅ APT (Advanced Persistent Threat) 탐지

**📚 자세한 내용:** [보안 지표 가이드 - Tool Chain Attack](<SECURITY_METRICS_GUIDE.html#attack-detection>)

* * *

## 4\. Layer 3: Advanced Metrics (고급 메트릭 10개)

Layer 3는 **DeepEval과 Ragas를 활용한 고급 평가 지표** 입니다. LLM 기반 평가로 높은 정확도를 제공합니다.

**특징**

  * ⚠️ OpenAI API 키 필요
  * ⚠️ API 비용 발생
  * ✅ 90-95% 정확도
  * ✅ RAG 시스템 평가에 최적

### 4.1 DeepEval 메트릭

DeepEval은 LLM을 평가자로 사용하여 더 정확하고 인간 친화적인 평가를 제공합니다.

#### 4.1.1 G-Eval 점수

**📝 설명** LLM을 평가자로 사용하여 사용자 정의 품질 기준에 따라 응답을 평가합니다.

**🔑 특징**

  * **사용자 정의 기준** : 원하는 품질 기준 설정 가능
  * **유연성** : 다양한 작업 유형에 적용
  * **인간 판단과 높은 상관관계** : 85%+ 일치율

**📐 계산 과정**

  1. 평가 기준 정의
  2. LLM이 기준에 따라 평가
  3. 0.0 ~ 1.0 점수 반환

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.8 ~ 0.9
  * 🟠 **보통** : 0.7 ~ 0.8
  * 🔴 **개선 필요** : < 0.7

**💡 사용 시나리오**

  1. **커스텀 평가** : 특정 도메인 요구사항
  2. **다면적 평가** : 여러 기준 동시 평가
  3. **주관적 품질** : 창의성, 유용성 등

**📌 예제**

```python
    [](<#cb32-1>)monitor.record_task(
    [](<#cb32-2>)    task,
    [](<#cb32-3>)    enable_advanced_metrics=True,
    [](<#cb32-4>)    input_text="프랑스의 수도는?",
    [](<#cb32-5>)    output_text="파리입니다.",
    [](<#cb32-6>)    quality_criteria="""
    [](<#cb32-7>)    답변은 다음 기준을 만족해야 합니다:
    [](<#cb32-8>)    1. 정확성: 사실에 기반한 정보
    [](<#cb32-9>)    2. 간결성: 불필요한 정보 없음
    [](<#cb32-10>)    3. 완전성: 질문에 완전히 답변
    [](<#cb32-11>)    4. 명확성: 이해하기 쉬운 표현
    [](<#cb32-12>)    """
    [](<#cb32-13>))
```

* * *

#### 4.1.2 Answer Relevancy

**📝 설명** 생성된 답변이 질문과 얼마나 관련성이 있는지 측정합니다.

**🔑 특징**

  * **의미론적 유사도** : 키워드가 아닌 의미 기반 평가
  * **맥락 이해** : 질문의 의도 파악

**📐 계산 방법**

  1. 답변에서 역생성 질문 생성
  2. 원래 질문과의 유사도 계산
  3. 불필요한 정보 패널티

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.7 ~ 0.9
  * 🟠 **보통** : 0.5 ~ 0.7
  * 🔴 **개선 필요** : < 0.5

**💡 해석**

  * **0.9 이상** : 질문에 직접적으로 답변
  * **0.5 미만** : 관련 없는 정보 포함

**🔍 개선 방법**

  1. 프롬프트에 "질문에만 답변" 명시
  2. Temperature 낮추기
  3. 응답 길이 제한

* * *

#### 4.1.3 환각 없음 점수 (Hallucination Score) - DeepEval

**📝 설명** AI 기반으로 컨텍스트와의 일치도를 측정합니다. **점수가 높을수록 환각이 없고 컨텍스트에 충실함** 을 의미합니다.

**⚠️ 중요 개념**

  * **hallucination_score** : 0.0 ~ 1.0 범위의 "환각 없음" 점수
  * **높은 점수 (0.9 이상)** : 환각이 거의 없음, 컨텍스트에 충실 ⬆ **좋음**
  * **낮은 점수 (0.7 미만)** : 환각이 많이 감지됨 ⬇ **나쁨**
  * [네이티브 환각 발생률](<#환각-발생률-hallucination-rate---네이티브>)과는 **반대 방향** 입니다

**🔑 특징**

  * **LLM 기반 분석** : 규칙이 아닌 이해 기반
  * **정밀한 탐지** : 미묘한 환각도 감지
  * **이유 제공** : 왜 환각으로 판단했는지 설명
  * **정확도 향상** : 네이티브보다 90-95% 정확

**📐 탐지 유형**

  1. **Factual Hallucination** : 사실과 다른 정보
  2. **Contextual Hallucination** : 컨텍스트 외 정보
  3. **Contradictory Hallucination** : 모순된 진술

**📊 평가 기준** (점수 높을수록 좋음 ⬆)

  * 🟢 **우수** : ≥ 0.9 (환각 거의 없음)
  * 🟡 **양호** : 0.8 ~ 0.9
  * 🟠 **보통** : 0.7 ~ 0.8
  * 🔴 **개선 필요** : < 0.7 (환각 많음)

**💡 비교: 네이티브 vs DeepEval**

항목 | 네이티브 환각 발생률 | DeepEval 환각 없음 점수  
---|---|---  
측정 대상 | 환각 발생 비율 | 컨텍스트 일치도  
방향 | ⬇ 낮을수록 좋음 | ⬆ 높을수록 좋음  
방식 | 규칙 기반 | AI 기반  
정확도 | 70-80% | 90-95%  
속도 | 빠름 | 느림  
비용 | 무료 | API 비용  
설명 | 없음 | 있음  
  
**📌 예제**

```json
    [](<#cb33-1>)# DeepEval 환각 없음 점수
    [](<#cb33-2>){
    [](<#cb33-3>)    'hallucination_score': 0.92,      # ⬆ 환각 없음 점수 (높을수록 좋음)
    [](<#cb33-4>)    'hallucination_detected': False,  # 환각 감지 여부 (False = 좋음)
    [](<#cb33-5>)    'hallucination_passed': True      # 임계값 통과 여부 (True = 좋음)
    [](<#cb33-6>)}
    [](<#cb33-7>)
    [](<#cb33-8>)# 점수 해석:
    [](<#cb33-9>)# 0.92 = 매우 우수 → 컨텍스트에 충실한 응답
    [](<#cb33-10>)# 만약 0.65였다면 → 환각이 많이 감지됨, 개선 필요
```

* * *

#### 4.1.4 독성 탐지 (Toxicity Detection)

**📝 설명** 응답에 포함된 독성 또는 부적절한 콘텐츠를 탐지합니다.

**🔑 탐지 유형**

  1. **욕설/비속어**
  2. **폭력적 표현**
  3. **차별적 언어**
  4. **성적 콘텐츠**
  5. **위협적 표현**

**📊 평가 기준** (낮을수록 좋음 ⬇)

  * 🟢 **안전** : < 0.1
  * 🟡 **감시** : 0.1 ~ 0.3
  * 🟠 **경고** : 0.3 ~ 0.5
  * 🔴 **위험** : ≥ 0.5

**💡 해석**

  * ⬇ **낮을수록 좋음** : 독성이 낮을수록 안전한 응답
  * **0.1 미만** : 안전한 수준
  * **0.3 이상** : 개선 필요
  * **0.5 이상** : 즉시 필터링 필요

**🔍 개선 방법**

  1. Safety System Message 추가
  2. 출력 필터링 구현
  3. 사용자 입력 검증
  4. Content Moderation API 사용

* * *

#### 4.1.5 편향 탐지 (Bias Detection)

**📝 설명** 응답에 포함된 편향(성별, 인종, 종교 등)을 탐지합니다.

**🔑 탐지 유형**

  1. **성별 편향** : 성별에 대한 고정관념
  2. **인종 편향** : 인종/민족 차별
  3. **종교 편향** : 특정 종교 선호/차별
  4. **연령 편향** : 연령 차별
  5. **지역 편향** : 특정 지역 선호

**📊 평가 기준** (낮을수록 좋음 ⬇)

  * 🟢 **공정** : < 0.1
  * 🟡 **경미** : 0.1 ~ 0.3
  * 🟠 **보통** : 0.3 ~ 0.5
  * 🔴 **심각** : ≥ 0.5

**💡 해석**

  * ⬇ **낮을수록 좋음** : 편향이 낮을수록 공정한 응답
  * **0.1 미만** : 편향 없는 수준
  * **0.3 이상** : 개선 필요
  * **0.5 이상** : 심각한 편향 문제

**🔍 개선 방법**

  1. 공정성 가이드라인 추가
  2. 다양한 예제 사용
  3. 편향 제거 프롬프트 기법
  4. 정기적인 편향 감사

* * *

### 4.2 RAGAS 메트릭 (RAG 전용)

RAGAS는 Retrieval-Augmented Generation (RAG) 시스템 전용 평가 프레임워크입니다.

**📌 PerformanceMonitor 통합**  
`record_rag_metrics()` 메서드로 RAG 메트릭을 기록하고, `get_rag_metrics_summary()`로 요약 통계를 확인할 수 있습니다.

#### 4.2.1 Faithfulness (충실도)

**📝 설명** 생성된 답변이 검색된 컨텍스트에 얼마나 충실한지 측정합니다.

**🔑 특징**

  * **환각 방지** : RAG 시스템의 핵심 지표
  * **주장 검증** : 각 주장이 컨텍스트에서 지원되는지 확인

**📐 계산식**

```python
    Faithfulness = 컨텍스트에서 지원되는 주장 수 / 전체 주장 수
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.8 ~ 0.9
  * 🟠 **보통** : 0.7 ~ 0.8
  * 🔴 **개선 필요** : < 0.7

**💡 해석**

  * **0.9 이상** : 신뢰할 수 있는 RAG 시스템
  * **0.7 미만** : 환각 문제 심각

**📌 예제**

```json
    [](<#cb35-1>)# 검색된 컨텍스트
    [](<#cb35-2>)retrieved_context = [
    [](<#cb35-3>)    "파리는 프랑스의 수도입니다.",
    [](<#cb35-4>)    "파리는 센 강변에 위치합니다."
    [](<#cb35-5>)]
    [](<#cb35-6>)
    [](<#cb35-7>)# 생성된 답변
    [](<#cb35-8>)answer = "파리는 프랑스의 수도이며 센 강변에 위치합니다."
    [](<#cb35-9>)# ✅ 모든 주장이 컨텍스트에서 지원됨 → Faithfulness = 1.0
    [](<#cb35-10>)
    [](<#cb35-11>)# 환각이 있는 답변
    [](<#cb35-12>)answer = "파리는 프랑스의 수도이며 인구는 1000만명입니다."
    [](<#cb35-13>)# ❌ "인구 1000만" 주장이 컨텍스트에 없음 → Faithfulness < 1.0
```

* * *

#### 4.2.2 Context Precision (컨텍스트 정밀도)

**📝 설명** 검색된 컨텍스트 중 실제로 관련 있는 정보의 비율을 측정합니다.

**🔑 특징**

  * **검색 품질** : 검색 시스템의 정밀도 평가
  * **노이즈 탐지** : 불필요한 정보 포함 여부

**📐 계산식**

```python
    Context Precision = 관련 있는 컨텍스트 수 / 전체 검색된 컨텍스트 수
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.8 ~ 0.9
  * 🟠 **보통** : 0.7 ~ 0.8
  * 🔴 **개선 필요** : < 0.7

**💡 해석**

  * **높은 정밀도** : 관련 정보만 검색
  * **낮은 정밀도** : 불필요한 정보 많음

**🔍 개선 방법**

  1. 검색 쿼리 최적화
  2. Re-ranking 추가
  3. 임베딩 모델 개선
  4. 메타데이터 필터링

* * *

#### 4.2.3 Context Recall (컨텍스트 재현율)

**📝 설명** 정답을 생성하는데 필요한 정보가 검색된 컨텍스트에 얼마나 포함되어 있는지 측정합니다.

**🔑 특징**

  * **검색 완전성** : 필요한 정보를 모두 찾았는지
  * **누락 탐지** : 중요 정보 누락 여부

**📐 계산식**

```python
    Context Recall = 검색된 관련 정보 수 / 필요한 전체 정보 수
```

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.8 ~ 0.9
  * 🟠 **보통** : 0.7 ~ 0.8
  * 🔴 **개선 필요** : < 0.7

**💡 해석**

  * **높은 재현율** : 필요한 정보 모두 검색
  * **낮은 재현율** : 중요 정보 누락

**🔍 개선 방법**

  1. Top-K 증가
  2. 하이브리드 검색 (키워드 + 의미)
  3. 쿼리 확장 (Query Expansion)
  4. 다중 검색 전략

* * *

#### 4.2.4 Answer Relevancy (답변 관련성)

**📝 설명** 생성된 답변이 질문과 얼마나 관련성이 있는지 측정합니다.

**🔑 특징**

  * **질문 이해** : 질문의 의도 파악
  * **불필요한 정보 감지** : 질문과 무관한 내용

**📐 계산 방법**

  1. 답변에서 역생성 질문 생성
  2. 원래 질문과의 유사도 계산

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.9
  * 🟡 **양호** : 0.7 ~ 0.9
  * 🟠 **보통** : 0.5 ~ 0.7
  * 🔴 **개선 필요** : < 0.5

* * *

#### 4.2.5 RAGAS Overall Score

**📝 설명** 모든 RAGAS 메트릭의 종합 점수입니다.

**📐 계산식**

```python
    RAGAS Overall = (Faithfulness + Context Precision +
                     Context Recall + Answer Relevancy) / 4
```

**⚠️ 중요 참고사항**

  * 계산 시 에러가 발생한 메트릭은 제외됩니다
  * 숫자가 아닌 값은 자동으로 필터링됩니다
  * 최소 1개 이상의 유효한 메트릭이 필요합니다

**📊 평가 기준**

  * 🟢 **우수** : ≥ 0.8
  * 🟡 **양호** : 0.6 ~ 0.8
  * 🟠 **보통** : 0.4 ~ 0.6
  * 🔴 **개선 필요** : < 0.4

**💡 해석**

  * **0.8 이상** : 프로덕션 수준 RAG 시스템
  * **0.6 이상** : 일반 사용 가능
  * **0.4 미만** : 전면 재설계 필요

* * *

* * *

## 5\. 메트릭 선택 가이드

### 5.1 계층별 사용 시나리오

#### 시나리오 1: 개발/테스트 (무료)

**사용 계층** : Layer 1만

```json
    [](<#cb39-1>)monitor = create_monitor(profile="minimal")
```

  * ✅ 완전 무료
  * ✅ 빠른 피드백
  * ✅ 기본 성능 파악
  * 💡 **추천** : 초기 개발 단계, CI/CD 파이프라인

#### 시나리오 2: Agentic AI 시스템

**사용 계층** : Layer 1 + Layer 2

```json
    [](<#cb40-1>)monitor = HybridPerformanceMonitor()
    [](<#cb40-2>)# TaskResult에 framework, expected_tools 등 설정
```

  * ✅ 무료
  * ✅ Agent 특화 지표
  * 💡 **추천** : CrewAI, LangGraph, AutoGen 사용 시

#### 시나리오 3: RAG 시스템

**사용 계층** : Layer 1 + Layer 3 (Ragas)

```json
    [](<#cb41-1>)monitor = create_monitor(profile="rag")
```

  * ⚠️ API 비용 발생
  * ✅ RAG 최적화
  * 💡 **추천** : RAG 파이프라인 품질 검증

#### 시나리오 4: 프로덕션 검증 (전체)

**사용 계층** : Layer 1 + Layer 2 + Layer 3

```json
    [](<#cb42-1>)monitor = create_monitor(profile="full")
```

  * ⚠️ 높은 API 비용
  * ✅ 최고 정확도
  * 💡 **추천** : 프로덕션 배포 전 최종 검증

* * *

### 5.2 작업 유형별 추천 메트릭

#### QA (Question Answering)

  * ✅ **필수** : TCR, Accuracy, Hallucination
  * 🎯 **권장** : G-Eval, Answer Relevancy
  * 📚 **RAG 사용 시** : RAGAS 전체

#### 창의적 작업 (Creative Writing)

  * ✅ **필수** : TCR, Quality
  * 🎯 **권장** : G-Eval, Toxicity, Bias

#### 코드 생성

  * ✅ **필수** : TCR, Accuracy
  * 🎯 **권장** : Tool Call Analysis

#### 데이터 분석

  * ✅ **필수** : TCR, Accuracy, Tool Call Analysis
  * 🎯 **권장** : Hallucination

#### RAG 시스템

  * ✅ **필수** : TCR, Accuracy, Hallucination
  * 🎯 **권장** : RAGAS 전체 메트릭

* * *

### 5.3 프로파일별 메트릭 구성

#### Minimal (무료)

```json
    [](<#cb43-1>)monitor = create_monitor(profile="minimal")
```

  * Native 메트릭만 (8개)
  * API 비용 없음
  * 빠른 평가

#### Balanced (권장)

```json
    [](<#cb44-1>)monitor = create_monitor(profile="balanced")
```

  * Native + DeepEval
  * 중간 비용
  * 대부분의 사용 사례에 적합

#### RAG (RAG 시스템용)

```json
    [](<#cb45-1>)monitor = create_monitor(profile="rag")
```

  * Native + DeepEval + RAGAS
  * RAG 시스템 전용
  * 종합 평가

#### Full (전체)

```json
    [](<#cb46-1>)monitor = create_monitor(profile="full")
```

  * 모든 메트릭 활성화
  * 최고 정확도
  * 높은 비용

* * *

### 5.4 비용 대비 효과 분석

프로파일 | 월 비용 (1000작업/일) | 정확도 | 권장 사용  
---|---|---|---  
Minimal | $0 | 70% | 개발/테스트  
Balanced | $30-50 | 85% | 일반 프로덕션  
RAG | $50-80 | 90% | RAG 시스템  
Full | $80-120 | 95% | 미션 크리티컬  
  
* * *

## 6\. 실전 활용 팁

### 6.1 임계값 설정 (계층별)

```json
    [](<#cb47-1>)# Layer 1: Native Metrics (기본)
    [](<#cb47-2>)thresholds_layer1 = {
    [](<#cb47-3>)    "tcr": 90.0,                    # Task Completion Rate
    [](<#cb47-4>)    "accuracy": 85.0,               # Accuracy
    [](<#cb47-5>)    "hallucination": 5.0,           # Hallucination Rate (낮을수록 좋음)
    [](<#cb47-6>)    "quality": 4.0,                 # Response Quality (5점 만점)
    [](<#cb47-7>)    "latency": 3.0,                 # Latency (초)
    [](<#cb47-8>)    "cost_per_task": 0.01,          # Cost per task ($)
    [](<#cb47-9>)    "tool_efficiency": 90.0,        # Tool Call Analysis - Efficiency Score
    [](<#cb47-10>)    "retry_success_rate": 80.0,     # Retry Success Rate
    [](<#cb47-11>)    # 보안 지표
    [](<#cb47-12>)    "threat_rate": 5.0,             # Input Sanitization threat rate
    [](<#cb47-13>)    "leakage_rate": 1.0,            # Output Leakage rate
    [](<#cb47-14>)    "compliance_rate": 95.0         # Tool Authorization compliance
    [](<#cb47-15>)}
    [](<#cb47-12>)
    [](<#cb47-13>)# Layer 2: Agentic AI Metrics (에이전트 시스템)
    [](<#cb47-17>)thresholds_layer2 = {
    [](<#cb47-18>)    "tool_selection_accuracy": 85.0,  # Tool Selection Accuracy
    [](<#cb47-19>)    "agent_coordination": 80.0,       # Agent Coordination Score
    [](<#cb47-20>)    "workflow_execution": 85.0,       # Workflow Execution Success Rate
    [](<#cb47-21>)    # 보안 지표
    [](<#cb47-22>)    "escalation_rate": 10.0,         # Privilege Escalation rate
    [](<#cb47-23>)    "suspicious_chains": 0            # Tool Chain Attack suspicious chains
    [](<#cb47-24>)}
    [](<#cb47-19>)
    [](<#cb47-20>)# Layer 3: Advanced Metrics (고급)
    [](<#cb47-21>)thresholds_layer3 = {
    [](<#cb47-22>)    # DeepEval
    [](<#cb47-23>)    "g_eval": 0.8,                  # G-Eval Score
    [](<#cb47-24>)    "hallucination_score": 0.8,     # Hallucination Score (높을수록 좋음)
    [](<#cb47-25>)    "toxicity": 0.1,                # Toxicity (낮을수록 좋음)
    [](<#cb47-26>)    "bias": 0.1,                    # Bias (낮을수록 좋음)
    [](<#cb47-27>)
    [](<#cb47-28>)    # Ragas
    [](<#cb47-29>)    "faithfulness": 0.8,            # Faithfulness
    [](<#cb47-30>)    "context_recall": 0.8,          # Context Recall
    [](<#cb47-31>)    "context_precision": 0.8,       # Context Precision
    [](<#cb47-32>)    "answer_relevancy": 0.8         # Answer Relevancy
    [](<#cb47-33>)}
    [](<#cb47-34>)
    [](<#cb47-35>)# 통합 설정: Layer 3 메트릭 활성화
    [](<#cb47-36>)monitor = HybridPerformanceMonitor(
    [](<#cb47-37>)    use_deepeval=True,
    [](<#cb47-38>)    use_ragas=True,
    [](<#cb47-39>)    deepeval_model="gpt-4o-mini",
    [](<#cb47-40>)    ragas_model="gpt-4o-mini"
    [](<#cb47-41>))
    [](<#cb47-42>)
    [](<#cb47-43>)# 임계값 설정 (PerformanceMonitor 방식 동일)
    [](<#cb47-44>)monitor.thresholds = {
    [](<#cb47-45>)    **thresholds_layer1,
    [](<#cb47-46>)    **thresholds_layer2,
    [](<#cb47-47>)    **thresholds_layer3
    [](<#cb47-48>)}
```

### 6.2 메트릭 해석 체크리스트

  * 작업 유형에 맞는 메트릭 선택했는가?
  * 충분한 샘플 수 (최소 100개)인가?
  * 시간대/사용자별 편향은 없는가?
  * 임계값이 비즈니스 요구사항에 맞는가?
  * 개선 가능한 메트릭을 식별했는가?

### 6.3 주간/월간 리뷰

**주간 리뷰** \- TCR, Accuracy 트렌드 - 비용 증감 분석 - 새로운 에러 패턴

**월간 리뷰** \- 전체 메트릭 비교 - 개선 효과 측정 - 목표 대비 성과

* * *

## 📊 7. 품질 관리자 가이드 (QA Manager)

> 💼 **품질 관리자를 위한 실전 가이드** : AI Agent 품질을 측정, 평가, 관리하는 체계적인 방법을 제공합니다.

### 7.1 품질 지표 해석

#### 📊 Layer 1 품질 지표 (Native Metrics)

메트릭 | 의미 | 품질 영향 | 권장 임계값 | 위험 신호  
---|---|---|---|---  
**TCR**  
(Task Completion Rate) | 작업 완료율  
전체 작업 중 성공한 비율 | **매우 높음**  
전체 시스템 신뢰성 | ✅ ≥ 90%  
⚠️ 80-90%  
❌ < 80% | < 80%: 치명적  
즉시 조사 필요  
**Accuracy**  
(정확도) | 답변 정확성  
올바른 정보 제공 비율 | **높음**  
사용자 신뢰 직결 | ✅ ≥ 85%  
⚠️ 70-85%  
❌ < 70% | < 70%: 품질 불량  
개선 필요  
**Hallucination**  
(환각 비율) | 거짓 정보 생성 비율  
근거 없는 답변 | **매우 높음**  
신뢰성 파괴 | ✅ < 5%  
⚠️ 5-10%  
❌ > 10% | > 10%: 위험  
배포 중단 권장  
**Quality Score**  
(품질 점수) | 전반적 답변 품질  
(완전성, 유용성) | **높음**  
사용자 만족도 | ✅ ≥ 4.0/5.0  
⚠️ 3.0-4.0  
❌ < 3.0 | < 3.0: 사용자 불만  
개선 필요  
**Latency**  
(응답 시간) | 평균 응답 속도  
(초 단위) | **중간**  
사용자 경험 | ✅ < 3초  
⚠️ 3-5초  
❌ > 5초 | > 5초: UX 저하  
최적화 필요  
**Cost**  
(비용) | 작업당 평균 비용  
(API 호출 비용) | **중간**  
운영 효율성 | 예산에 따라  
프로젝트별 설정 | 예산 초과 시  
최적화 검토  
  
#### 🤖 Layer 2 품질 지표 (Agentic AI Metrics)

메트릭 | 의미 | 품질 영향 | 권장 임계값  
---|---|---|---  
**Tool Selection Accuracy** | 도구 선택 정확도  
적절한 도구 선택 비율 | **높음**  
작업 효율성 | ✅ ≥ 85%  
⚠️ 70-85%  
**Agent Efficiency** | 에이전트 효율성  
불필요한 호출 최소화 | **중간**  
비용 절감 | ✅ ≥ 80%  
⚠️ 60-80%  
**Coordination Score** | 협업 효과성  
멀티 에이전트 조율 | **높음**  
복잡한 작업 성공률 | ✅ ≥ 4.0/5.0  
⚠️ 3.0-4.0  
**Workflow Efficiency** | 워크플로우 효율  
단계 실행 최적화 | **중간**  
전체 성능 | ✅ ≥ 75%  
⚠️ 60-75%  
  
#### 📈 메트릭 간 상관관계

**핵심 인사이트:**

  * **TCR ↓ + Hallucination ↑** → 신뢰성 위기: 즉시 배포 중단 고려
  * **Accuracy ↓ + Quality ↓** → 모델 재학습 또는 프롬프트 개선 필요
  * **Latency ↑ + Tool Selection ↓** → 비효율적 도구 사용: 워크플로우 최적화
  * **Cost ↑ + Efficiency ↓** → 불필요한 API 호출: 캐싱 또는 로직 개선
  * **Coordination ↓** → 멀티 에이전트 설계 재검토 필요

### 7.2 임계값 설정 가이드

#### 🎯 개발 단계별 임계값 전략

단계 | 목표 | TCR | Accuracy | Hallucination | Quality  
---|---|---|---|---|---  
**Alpha**  
(내부 테스트) | 기본 동작 확인  
기능 검증 | ≥ 70%  
(낮은 기준선) | ≥ 60%  
(기본 동작) | < 15%  
(허용 범위 넓음) | ≥ 3.0  
(최소 품질)  
**Beta**  
(제한된 사용자) | 안정성 확보  
실사용 테스트 | ≥ 85%  
(안정화) | ≥ 80%  
(실용 수준) | < 8%  
(관리 필요) | ≥ 3.5  
(양호)  
**Production**  
(전체 공개) | 고품질 보장  
사용자 신뢰 | ≥ 90%  
(고품질) | ≥ 85%  
(정확성 확보) | < 5%  
(최소화) | ≥ 4.0  
(우수)  
**Enterprise**  
(기업용) | 미션 크리티컬  
최고 수준 | ≥ 95%  
(최고 신뢰성) | ≥ 90%  
(전문가 수준) | < 3%  
(거의 없음) | ≥ 4.5  
(탁월)  
  
#### 🏢 산업별 권장 임계값

산업 | 특성 | 핵심 메트릭 | 권장값  
---|---|---|---  
**금융/의료**  
(High-stakes) | 오류 허용 불가  
법적 책임 | Accuracy, Hallucination | Accuracy ≥ 95%  
Hallucination < 2%  
**고객 서비스**  
(Customer-facing) | 사용자 경험 중시  
빠른 응답 | Quality, Latency, TCR | Quality ≥ 4.0  
Latency < 3초  
TCR ≥ 90%  
**콘텐츠 생성**  
(Creative) | 창의성 중요  
다양성 허용 | Quality, Hallucination | Quality ≥ 3.5  
Hallucination < 10%  
**내부 도구**  
(Internal) | 생산성 향상  
비용 효율 | Efficiency, Cost | Efficiency ≥ 75%  
예산 내 유지  
  
#### ⚙️ 실전 임계값 설정 코드

```json
    [](<#cb-qa-thresholds-1>)# Alpha 단계 임계값
    [](<#cb-qa-thresholds-2>)thresholds_alpha = {
    [](<#cb-qa-thresholds-3>)    "tcr": 70.0,
    [](<#cb-qa-thresholds-4>)    "accuracy": 60.0,
    [](<#cb-qa-thresholds-5>)    "hallucination": 15.0,
    [](<#cb-qa-thresholds-6>)    "quality_score": 3.0
    [](<#cb-qa-thresholds-7>)}
    [](<#cb-qa-thresholds-8>)
    [](<#cb-qa-thresholds-9>)# Production 단계 임계값
    [](<#cb-qa-thresholds-10>)thresholds_production = {
    [](<#cb-qa-thresholds-11>)    "tcr": 90.0,
    [](<#cb-qa-thresholds-12>)    "accuracy": 85.0,
    [](<#cb-qa-thresholds-13>)    "hallucination": 5.0,
    [](<#cb-qa-thresholds-14>)    "quality_score": 4.0
    [](<#cb-qa-thresholds-15>)}
    [](<#cb-qa-thresholds-16>)
    [](<#cb-qa-thresholds-17>)# 평가 시 임계값 적용
    [](<#cb-qa-thresholds-18>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb-qa-thresholds-19>)    agent_fn=my_agent,
    [](<#cb-qa-thresholds-20>)    dataset_path="golden_datasets/prod.json"
    [](<#cb-qa-thresholds-21>))
    [](<#cb-qa-thresholds-22>)
    [](<#cb-qa-thresholds-23>)# 임계값 검증
    [](<#cb-qa-thresholds-24>)if results["tcr"] < thresholds_production["tcr"]:
    [](<#cb-qa-thresholds-25>)    print("⚠️  TCR 기준 미달: 배포 불가")
    [](<#cb-qa-thresholds-26>)if results["hallucination"] > thresholds_production["hallucination"]:
    [](<#cb-qa-thresholds-27>)    print("🚨 Hallucination 위험: 긴급 개선 필요")
```

### 7.3 품질 보증 체크리스트

#### ✅ 배포 전 필수 체크리스트

**📋 Release Checklist (Production 배포 전)**

항목 | 기준 | 검증 방법 | Pass/Fail  
---|---|---|---  
1\. **Golden Dataset 평가** | 전체 테스트 케이스 실행 | `evaluate_with_golden_dataset()` | [ ]  
2\. **TCR ≥ 90%** | 작업 완료율 기준 충족 | 리포트 확인 | [ ]  
3\. **Accuracy ≥ 85%** | 정확도 기준 충족 | 리포트 확인 | [ ]  
4\. **Hallucination < 5%** | 환각 최소화 | 리포트 확인 (필수) | [ ]  
5\. **Quality ≥ 4.0** | 품질 점수 기준 충족 | 리포트 확인 | [ ]  
6\. **Latency < 3초** | 사용자 경험 보장 | P95 latency 확인 | [ ]  
7\. **Layer 2 검증**  
(Multi-agent 시) | 도구 선택, 협업 점수 | `enable_layer2_metrics=True` | [ ]  
8\. **비용 예산 확인** | 작업당 비용 < 예산 | Cost per task 계산 | [ ]  
  
**🔴 하나라도 Fail 시 → 배포 중단하고 개선 후 재평가**

#### 📅 주간 모니터링 체크리스트

**🗓️ 매주 월요일 체크**

  * ✅ **지난 주 TCR 트렌드** : 감소 추세 있는지 확인
  * ✅ **Hallucination 스파이크** : 갑작스런 증가 있는지 모니터링
  * ✅ **P95 Latency** : 사용자 경험 저하 여부
  * ✅ **비용 추이** : 예산 대비 실제 비용 추적
  * ✅ **실패 작업 분석** : 실패 케이스 패턴 파악
  * ✅ **사용자 피드백** : 품질 관련 불만 수집

### 7.4 문제 발생 시 조치 방법

#### 🚨 문제 유형별 대응 가이드

##### 🔴 시나리오 1: TCR 급감 (90% → 75%)

**증상:** 작업 완료율이 갑자기 15% 이상 하락

**원인 분석:**

  * 외부 API 장애 또는 타임아웃 증가
  * 최근 코드 변경으로 인한 버그
  * 모델 업데이트로 인한 행동 변화

**즉시 조치:**

  1. 실패한 작업 로그 수집 및 분석
  2. 외부 API 상태 확인 (timeout, rate limit)
  3. 최근 배포 롤백 검토
  4. 임시로 재시도 로직 활성화

**근본 해결:**

  * 에러 핸들링 강화
  * Fallback 메커니즘 추가
  * 테스트 케이스 보강

##### 🟠 시나리오 2: Hallucination 급증 (<5% → 12%)

**증상:** 거짓 정보 생성 비율이 임계값의 2배 이상

**원인 분석:**

  * 프롬프트 변경으로 인한 제약 조건 약화
  * RAG 시스템의 검색 품질 저하
  * 모델의 과도한 창의성 (Temperature 너무 높음)

**즉시 조치:**

  1. 🚨 **배포 일시 중단** (High-stakes 서비스의 경우)
  2. Hallucination 발생 케이스 수동 검토
  3. Temperature 낮추기 (예: 0.7 → 0.3)
  4. 프롬프트에 "근거 제시" 명시 강화

**근본 해결:**

  * RAG 검색 정확도 개선
  * Grounding 메커니즘 강화
  * Fact-checking 레이어 추가

##### 🟡 시나리오 3: Latency 증가 (2초 → 6초)

**증상:** 평균 응답 시간이 2배 이상 증가

**원인 분석:**

  * 불필요한 도구 호출 증가 (Tool Selection 문제)
  * 모델 API 응답 시간 증가
  * 비효율적인 워크플로우 설계

**즉시 조치:**

  1. Layer 2 메트릭 활성화하여 Tool Selection 분석
  2. 타임아웃 설정 조정
  3. 캐싱 메커니즘 활성화
  4. 병렬 처리 가능한 작업 식별

**근본 해결:**

  * 워크플로우 최적화 (불필요한 단계 제거)
  * 더 빠른 모델로 전환 (예: GPT-4 → GPT-3.5-turbo)
  * 도구 호출 우선순위 재설계

##### 🟢 시나리오 4: 비용 초과 (예산의 150%)

**증상:** API 호출 비용이 예산을 50% 초과

**원인 분석:**

  * 사용량 급증 (좋은 신호일 수도 있음)
  * 비효율적인 에이전트 설계 (중복 호출)
  * 높은 비용의 모델 과도 사용

**즉시 조치:**

  1. 사용량 분석: 실제 증가 vs 비효율
  2. Agent Efficiency 메트릭 확인
  3. 고비용 호출 케이스 식별
  4. 임시 rate limiting 적용

**근본 해결:**

  * 캐싱 전략 도입
  * Tiered model 전략 (간단한 작업은 저비용 모델)
  * 불필요한 호출 제거

#### 📊 에스컬레이션 매트릭스

심각도 | 상황 | 대응 시간 | 담당자  
---|---|---|---  
**P0 (Critical)** | TCR < 70% 또는  
Hallucination > 15% | **즉시**  
(배포 중단) | CTO + 팀 전체  
**P1 (High)** | TCR 70-85% 또는  
Hallucination 10-15% | **1시간 이내** | Lead + QA Manager  
**P2 (Medium)** | TCR 85-90% 또는  
Hallucination 5-10% | **당일** | QA Manager  
**P3 (Low)** | 기타 개선 사항  
(Latency, Cost) | **주간 회의** | 담당 개발자  
  
**💡 QA 관리자 핵심 원칙**

  1. **데이터 기반 의사결정** : 감이 아닌 메트릭으로 판단
  2. **사전 예방** : 주간 모니터링으로 문제 조기 발견
  3. **명확한 기준** : 임계값과 에스컬레이션 프로세스 문서화
  4. **지속적 개선** : 실패 케이스를 Golden Dataset에 추가
  5. **사용자 중심** : 메트릭이 아닌 사용자 만족이 최종 목표

* * *

## 8\. 프레임워크 통합

주요 AI 프레임워크와의 통합 방법입니다.

프레임워크 | 통합 클래스 | 사용 방법  
---|---|---  
LangChain | `LangChainEvaluator` \+ `AdvancedLangChainCallback` | Evaluator로 래핑, Callback 사용  
LangGraph | `LangGraphEvaluator` | Evaluator로 그래프 래핑  
CrewAI | `CrewAIEvaluator` | Evaluator로 Crew 래핑  
AutoGen | `AutoGenEvaluator` | Evaluator로 Agent 래핑  
  
**📚 v0.5.0 통합 가이드:**

  * ✅ **Clean API** : 모든 프레임워크에서 일관된 `Evaluator` 패턴 사용
  * ✅ **Layer 1/2/3 자동 추적** : `enable_layer2=True`로 고급 메트릭 활성화
  * ✅ **보고서 자동 생성** : `evaluator.generate_report()`로 통합 리포트
  * 📦 **코드 75% 감소** : framework_integrations.py (780→198 lines)

**자세한 내용:** [API Reference - 프레임워크 통합](<API_REFERENCE.html#프레임워크-통합>) | [마이그레이션 가이드](<API_REFERENCE.html#migration-guide>)

* * *

## 참고 자료

  * [DeepEval 공식 문서](<https://docs.confident-ai.com/>)
  * [RAGAS 공식 문서](<https://docs.ragas.io/>)
  * [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.html>)
  * [개발자 빠른 시작 가이드](<DEVELOPER_QUICKSTART_GUIDE.html>)
  * [대시보드 가이드](<DASHBOARD.html>)

* * *

**Agent Evaluator v0.5.1**

**최종 업데이트** : 2025-12-15

© 2024-2025 MIT License
