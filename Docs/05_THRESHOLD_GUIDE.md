# 🎯 품질 기준 설정 가이드

임계값 설정 및 품질 게이트 구성

# Threshold Configuration 가이드

## 개요

이 가이드는 Agent Evaluator의 **임계값(Threshold) 설정 및 검증** 방법을 설명합니다. 실제 구현(`agent_evaluator/core/agent_evaluator.py`, `agent_evaluator/core/hybrid_monitor.py`)을 기반으로 작성되었으며, 모든 예제는 검증되었습니다.

### 주요 검증 사항

다음 항목들이 실제 구현과 일치함을 확인했습니다:

  1. **Threshold 딕셔너리 구조** : `monitor.thresholds = {metric_name: value}`
  2. **지원되는 메트릭** :
     * Layer 1 (Foundation): `tcr`, `accuracy`, `hallucination`, `quality`, `latency`, `cost_per_task`
     * Layer 3 (RAG): `faithfulness`, `answer_relevancy`, `context_recall`, `context_precision`
     * Layer 2 (Agentic): `tool_selection_accuracy`, `agent_coordination`, `workflow_execution`, `retry_success_rate`
     * Layer 2 (Security): `input_sanitization`, `output_leakage`, `authorization`, `privilege_escalation`, `tool_chain_attack`
  3. **compare_with_thresholds() 반환값** : `{metric: {name, value, threshold, status, direction, unit, layer?, details?}}`
  4. **load_thresholds_from_config()** : 저장된 임계값 파일에서 자동 로드 지원
  5. **Latency 계산** : P95 (95 백분위수) 사용, 평균이 아님
  6. **Quality 변환** : 5점 척도 → 10점 척도 (×2 변환)

## 목차

  1. [Threshold란?](<#threshold란>)
  2. [Layer 1 Thresholds (Foundation Metrics)](<#layer-1-thresholds-native-metrics>)
  3. [Layer 2 Thresholds (Agentic Metrics + Security)](<#layer-2-thresholds-agentic-ai-metrics>)
  4. [Threshold 설정 전략](<#threshold-설정-전략>)
  5. [환경별 Threshold 설정](<#환경별-threshold-설정>)
  6. [Threshold 비교 및 검증](<#threshold-비교-및-검증>)
  7. [CI/CD 통합](<#cicd-통합>)
  8. [Best Practices](<#best-practices>)
  9. [시나리오별 예제](<#시나리오별-예제>)
  10. [FAQ & Troubleshooting](<#faq-troubleshooting>)
  11. [📊 품질 관리자 가이드 (QA Manager)](<#qa-guide>)
     * [11.1 임계값 관리 전략](<#qa-strategy>)
     * [11.2 임계값 생명주기 관리](<#qa-lifecycle>)
     * [11.3 임계값 변경 관리](<#qa-change>)
     * [11.4 임계값 위반 대응](<#qa-violation>)
     * [11.5 정기 임계값 리뷰](<#qa-review>)

* * *

## Threshold란?

### 정의

**Threshold**(임계값)는 AI 에이전트의 **허용 가능한 성능 기준** 입니다. 각 메트릭에 대해 최소/최대 값을 설정하여, 에이전트가 이 기준을 충족하는지 자동으로 검증할 수 있습니다.

### 왜 필요한가?

#### 1\. 품질 게이트 (Quality Gate)

  * 프로덕션 배포 전 **자동 품질 검증**
  * 기준 미달 시 배포 차단
  * CI/CD 파이프라인과 통합

#### 2\. 회귀 방지 (Regression Prevention)

  * 에이전트 업데이트 시 **성능 저하 감지**
  * 이전 버전과 비교하여 품질 유지 보장

#### 3\. 객관적 평가

  * 주관적 판단 대신 **정량적 기준**
  * 팀 간 일관된 품질 표준

#### 4\. 프로덕션 준비 검증

  * “이 에이전트를 배포해도 될까?”라는 질문에 대한 **자동화된 답변**

### Pass/Fail 판정

각 메트릭은 threshold와 비교하여 **Pass** 또는 **Fail** 로 판정됩니다:

  * **Pass (✅)** : 메트릭 값이 threshold를 충족 
    * “높을수록 좋은” 메트릭: `value >= threshold`
    * “낮을수록 좋은” 메트릭: `value <= threshold`
  * **Fail (❌)** : 메트릭 값이 threshold를 불충족 
    * “높을수록 좋은” 메트릭: `value < threshold`
    * “낮을수록 좋은” 메트릭: `value > threshold`

**CI/CD에서의 판정** :

  * **모든 메트릭이 Pass** : 배포 진행 (exit code 0)
  * **하나라도 Fail** : 배포 차단 (exit code 1)

* * *

## Layer 1 Thresholds (Foundation Metrics)

Layer 1은 **기본적인 AI 성능 메트릭** 입니다.

### 1\. Task Completion Rate (TCR)

**메트릭** : `tcr` **단위** : `%` **방향** : 높을수록 좋음 (higher is better) **정의** : 에이전트가 작업을 성공적으로 완료한 비율

#### 계산 방식
```python
    TCR = (성공한 작업 수 / 전체 작업 수) × 100
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 (Dev) | 70-80% | 실험적 기능 허용  
스테이징 (Staging) | 85-90% | 프로덕션 준비 검증  
프로덕션 (Production) | 95%+ | 높은 신뢰성 요구  
  
#### 설정 예제
```python
    [](<#cb2-1>)monitor.thresholds = {
    [](<#cb2-2>)    'tcr': 90.0  # 90% 이상이어야 Pass
    [](<#cb2-3>)}
```

#### 해석

  * **TCR < 90%**: 작업 실패율이 높음 → 프롬프트 개선 필요
  * **TCR ≥ 90%** : 안정적 → Pass

### 2\. Accuracy (정확도)

**메트릭** : `accuracy` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 에이전트 응답이 정답(ground truth)과 얼마나 유사한지

#### 계산 방식
```python
    Accuracy = Semantic Similarity Score × 100
```

  * 기본: BERT 기반 임베딩 유사도
  * 설정 가능: OpenAI embeddings, sentence-transformers 등

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 60-70% | 초기 개발 단계  
스테이징 | 75-85% | 품질 검증  
프로덕션 | 85-90% | 높은 정확도 요구  
  
#### 설정 예제
```python
    [](<#cb4-1>)monitor.thresholds = {
    [](<#cb4-2>)    'accuracy': 85.0  # 85% 이상이어야 Pass
    [](<#cb4-3>)}
```

#### 해석

  * **Accuracy < 85%**: 응답 품질이 낮음 → Golden Dataset 또는 프롬프트 개선
  * **Accuracy ≥ 85%** : 응답 품질 양호 → Pass

### 3\. Hallucination Rate (환각 비율)

**메트릭** : `hallucination` **단위** : `%` **방향** : 낮을수록 좋음 (lower is better) **정의** : 에이전트가 사실이 아닌 정보를 생성한 비율

#### 계산 방식
```python
    Hallucination Rate = (Hallucination 발생 횟수 / 전체 작업 수) × 100
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 10-15% | 실험 허용  
스테이징 | 5-10% | 품질 검증  
프로덕션 | 2-5% | 매우 낮은 환각률 요구  
  
#### 설정 예제
```python
    [](<#cb6-1>)monitor.thresholds = {
    [](<#cb6-2>)    'hallucination': 5.0  # 5% 이하여야 Pass
    [](<#cb6-3>)}
```

#### 해석

  * **Hallucination > 5%**: 환각이 너무 많음 → RAG 시스템 개선, 프롬프트 수정
  * **Hallucination ≤ 5%** : 환각률 낮음 → Pass

### 4\. Quality (응답 품질)

**메트릭** : `quality` **단위** : `/10` (0-10 척도) **방향** : 높을수록 좋음 **정의** : 응답의 전반적인 품질 (명확성, 완전성, 관련성 등)

#### 계산 방식
```python
    Quality Score = ResponseQualityEvaluator의 평균 점수 × 2 (10점 척도로 변환)
```

  * 원본: 5점 척도 (total_score 기준)
  * 변환: 10점 척도로 환산하여 threshold 비교

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 5-6/10 | 기본 품질  
스테이징 | 7-8/10 | 좋은 품질  
프로덕션 | 8-9/10 | 매우 높은 품질  
  
#### 설정 예제
```python
    [](<#cb8-1>)monitor.thresholds = {
    [](<#cb8-2>)    'quality': 7.0  # 7/10 이상이어야 Pass
    [](<#cb8-3>)}
```

#### 해석

  * **Quality < 7/10**: 응답 품질 개선 필요
  * **Quality ≥ 7/10** : 품질 양호 → Pass

### 5\. Latency (응답 시간)

**메트릭** : `latency` **단위** : `s` (초) **방향** : 낮을수록 좋음 **정의** : 에이전트의 P95 응답 시간 (상위 5% 제외)

#### 계산 방식
```python
    Latency = P95 응답 시간 (초)
```

  * P95: 95 백분위수 응답 시간 (이상치 제외)
  * 평균이 아닌 P95 사용하여 더 안정적인 평가

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
실시간 챗봇 | 1-2초 | 빠른 응답 필요  
일반 에이전트 | 3-5초 | 적당한 응답 시간  
복잡한 작업 | 10-30초 | 시간이 걸리는 작업  
  
#### 설정 예제
```python
    [](<#cb10-1>)monitor.thresholds = {
    [](<#cb10-2>)    'latency': 3.0  # 3초 이하여야 Pass (P95 기준)
    [](<#cb10-3>)}
```

#### 해석

  * **Latency > 3s**: 응답이 너무 느림 → 프롬프트 간소화, 모델 최적화
  * **Latency ≤ 3s** : 응답 속도 양호 → Pass

### 6\. Cost per Task (작업당 비용)

**메트릭** : `cost_per_task` **단위** : `$` (달러) **방향** : 낮을수록 좋음 **정의** : 작업 하나를 처리하는 데 드는 평균 비용 (LLM API 비용)

#### 계산 방식
```python
    Cost per Task = (Input Tokens × Input Price + Output Tokens × Output Price)의 평균
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
간단한 QA | $0.01-0.05 | 저비용 작업  
일반 에이전트 | $0.05-0.20 | 중간 비용  
복잡한 작업 | $0.20-1.00 | 고비용 허용  
  
#### 설정 예제
```python
    [](<#cb12-1>)monitor.thresholds = {
    [](<#cb12-2>)    'cost_per_task': 0.10  # $0.10 이하여야 Pass
    [](<#cb12-3>)}
```

#### 해석

  * **Cost > $0.10**: 비용이 너무 높음 → 작은 모델 사용, 프롬프트 최적화
  * **Cost ≤ $0.10** : 비용 적절 → Pass

### 7\. RAG 메트릭 (선택적)

RAG 시스템을 사용하는 경우 다음 메트릭을 추가할 수 있습니다:

#### Faithfulness (충실도)

**메트릭** : `faithfulness` **단위** : (0-1 척도) **방향** : 높을수록 좋음 **정의** : 생성된 답변이 제공된 컨텍스트에 얼마나 충실한지
```python
    [](<#cb13-1>)monitor.thresholds = {
    [](<#cb13-2>)    'faithfulness': 0.8  # 0.8 이상이어야 Pass
    [](<#cb13-3>)}
```

**참고** : 현재는 placeholder 구현. RAG 평가 기능 활성화 필요.

#### Answer Relevancy (답변 관련성)

**메트릭** : `answer_relevancy` **단위** : (0-1 척도) **방향** : 높을수록 좋음 **정의** : 생성된 답변이 질문과 얼마나 관련있는지
```python
    [](<#cb14-1>)monitor.thresholds = {
    [](<#cb14-2>)    'answer_relevancy': 0.8  # 0.8 이상이어야 Pass
    [](<#cb14-3>)}
```

**참고** : 현재는 placeholder 구현. RAG 평가 기능 활성화 필요.

#### Context Recall (컨텍스트 재현율)

**메트릭** : `context_recall` **단위** : (0-1 척도) **방향** : 높을수록 좋음 **정의** : 필요한 정보가 검색된 컨텍스트에 얼마나 포함되어 있는지
```python
    [](<#cb15-1>)monitor.thresholds = {
    [](<#cb15-2>)    'context_recall': 0.8  # 0.8 이상이어야 Pass
    [](<#cb15-3>)}
```

**참고** : 현재는 placeholder 구현. RAG 평가 기능 활성화 필요.

#### Context Precision (컨텍스트 정밀도)

**메트릭** : `context_precision` **단위** : (0-1 척도) **방향** : 높을수록 좋음 **정의** : 검색된 컨텍스트 중 관련 있는 정보의 비율
```python
    [](<#cb16-1>)monitor.thresholds = {
    [](<#cb16-2>)    'context_precision': 0.8  # 0.8 이상이어야 Pass
    [](<#cb16-3>)}
```

**참고** : 현재는 placeholder 구현. RAG 평가 기능 활성화 필요.

### 8. Layer 2 Security 메트릭 (v0.6.0)

Layer 2 Security 메트릭은 **보안 위협** 을 평가합니다 (`enable_security_metrics=True` 필요).

#### Input Sanitization (입력 검증)

**메트릭** : `input_sanitization` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 악의적 입력이 적절히 검증/차단되는 비율
```python
    [](<#cb16a-1>)monitor.thresholds = {
    [](<#cb16a-2>)    'input_sanitization': 95.0  # 95% 이상이어야 Pass
    [](<#cb16a-3>)}
```

#### Output Leakage (출력 유출 방지)

**메트릭** : `output_leakage` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 민감한 정보가 출력에 포함되지 않는 비율
```python
    [](<#cb16b-1>)monitor.thresholds = {
    [](<#cb16b-2>)    'output_leakage': 95.0  # 95% 이상이어야 Pass (유출 방지율)
    [](<#cb16b-3>)}
```

#### Authorization (권한 검증)

**메트릭** : `authorization` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 권한이 적절히 검증되는 비율
```python
    [](<#cb16c-1>)monitor.thresholds = {
    [](<#cb16c-2>)    'authorization': 98.0  # 98% 이상이어야 Pass
    [](<#cb16c-3>)}
```

**통합 예제** :
```python
    [](<#cb16d-1>)# Layer 1: Foundation Thresholds
    [](<#cb16d-2>)monitor.thresholds = {
    [](<#cb16d-3>)    # Basic Metrics
    [](<#cb16d-4>)    'tcr': 90.0,
    [](<#cb16d-5>)    'accuracy': 85.0,
    [](<#cb16d-6>)    'hallucination': 5.0,
    [](<#cb16d-7>)    'quality': 7.0,
    [](<#cb16d-8>)    # Security Metrics
    [](<#cb16d-9>)    'input_sanitization': 95.0,
    [](<#cb16d-10>)    'output_leakage': 95.0,
    [](<#cb16d-11>)    'authorization': 98.0
    [](<#cb16d-12>)}
```

* * *

## Layer 2 Thresholds (Agentic Metrics + Security)

Layer 2는 **Agentic AI 시스템의 고급 메트릭과 고급 보안 메트릭** 입니다.

### 1\. Tool Selection Accuracy (도구 선택 정확도)

**메트릭** : `tool_selection_accuracy` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 에이전트가 올바른 도구를 선택한 비율 (F1 Score 기반)

#### 계산 방식
```python
    Tool Selection Accuracy = (모든 작업의 F1 Score 평균) × 100
    
    F1 Score = 2 × (Precision × Recall) / (Precision + Recall)
    - Precision = 올바른 도구 / 사용한 도구
    - Recall = 올바른 도구 / 필요한 도구
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 60-70% | 초기 개발  
스테이징 | 75-85% | 품질 검증  
프로덕션 | 85-95% | 높은 정확도 요구  
  
#### 설정 예제
```python
    [](<#cb18-1>)monitor.thresholds = {
    [](<#cb18-2>)    'tool_selection_accuracy': 80.0  # 80% 이상이어야 Pass
    [](<#cb18-3>)}
```

#### 해석

  * **Tool Selection < 80%**: 도구 선택이 부정확함 → 프롬프트 개선, Golden Dataset 확인
  * **Tool Selection ≥ 80%** : 도구 선택 양호 → Pass

#### Golden Dataset 요구사항

Layer 2 메트릭을 사용하려면 Golden Dataset에 `expected_tools` 필드가 필요합니다:
```json
    [](<#cb19-1>){
    [](<#cb19-2>)  "id": "qa_001",
    [](<#cb19-3>)  "question": "What is 15 + 27?",
    [](<#cb19-4>)  "expected_tools": ["calculator"]
    [](<#cb19-5>)}
```

### 2\. Agent Coordination (에이전트 협업 점수)

**메트릭** : `agent_coordination` **단위** : `/10` (0-10 척도) **방향** : 높을수록 좋음 **정의** : Multi-agent 시스템에서 에이전트 간 협업 품질

#### 계산 방식
```python
    Coordination Score = (
        0.5 × Success Rate +
        0.3 × Agent Diversity +
        0.2 × Interaction Balance
    ) × 10
    
    - Success Rate: 성공한 상호작용 비율
    - Agent Diversity: 참여한 고유 에이전트 비율
    - Interaction Balance: 상호작용 유형의 균형도
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 5-6/10 | 초기 개발  
스테이징 | 7-8/10 | 품질 검증  
프로덕션 | 8-9/10 | 높은 협업 품질 요구  
  
#### 설정 예제
```python
    [](<#cb21-1>)monitor.thresholds = {
    [](<#cb21-2>)    'agent_coordination': 7.0  # 7/10 이상이어야 Pass
    [](<#cb21-3>)}
```

#### 해석

  * **Coordination < 7/10**: 협업이 원활하지 않음 → 에이전트 간 통신 개선
  * **Coordination ≥ 7/10** : 협업 양호 → Pass

#### Golden Dataset 요구사항
```json
    [](<#cb22-1>){
    [](<#cb22-2>)  "id": "qa_002",
    [](<#cb22-3>)  "question": "Research AI trends and write a report.",
    [](<#cb22-4>)  "expected_agents": ["manager", "researcher", "writer"]
    [](<#cb22-5>)}
```

### 3\. Workflow Execution Success Rate (워크플로우 실행 성공률)

**메트릭** : `workflow_execution` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 워크플로우 단계가 성공적으로 실행된 비율

#### 계산 방식
```python
    Workflow Execution = (성공한 단계 수 / 전체 단계 수) × 100
```

#### Threshold 권장값

환경 | 권장값 | 설명  
---|---|---  
개발 | 70-80% | 실험적 워크플로우  
스테이징 | 85-90% | 품질 검증  
프로덕션 | 95-100% | 매우 높은 안정성 요구  
  
#### 설정 예제
```python
    [](<#cb24-1>)monitor.thresholds = {
    [](<#cb24-2>)    'workflow_execution': 90.0  # 90% 이상이어야 Pass
    [](<#cb24-3>)}
```

#### 해석

  * **Workflow < 90%**: 워크플로우 단계 실패가 많음 → 단계 최적화, 에러 처리 강화
  * **Workflow ≥ 90%** : 워크플로우 안정적 → Pass

#### 상세 정보 (details)

`compare_with_thresholds()`에서 반환되는 `details` 필드:

  * `total_steps`: 전체 단계 수
  * `successful_steps`: 성공한 단계 수
  * `task_success_rate`: 작업 수준의 성공률


```json
    [](<#cb25-1>){
    [](<#cb25-2>)    'workflow_execution': {
    [](<#cb25-3>)        'value': 95.0,
    [](<#cb25-4>)        'threshold': 90.0,
    [](<#cb25-5>)        'status': 'pass',
    [](<#cb25-6>)        'details': {
    [](<#cb25-7>)            'total_steps': 100,
    [](<#cb25-8>)            'successful_steps': 95,
    [](<#cb25-9>)            'task_success_rate': 92.5
    [](<#cb25-10>)        }
    [](<#cb25-11>)    }
    [](<#cb25-12>)}
```

#### Golden Dataset 요구사항
```json
    [](<#cb26-1>){
    [](<#cb26-2>)  "id": "qa_003",
    [](<#cb26-3>)  "question": "Summarize this document.",
    [](<#cb26-4>)  "expected_workflow_steps": ["retrieval", "generation", "validation"]
    [](<#cb26-5>)}
```

### 4\. Layer 2 Security 메트릭 (v0.6.0)

Layer 2 Security 메트릭은 **고급 보안 위협** 을 평가합니다.

#### Privilege Escalation (권한 상승 감지)

**메트릭** : `privilege_escalation` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 권한 상승 시도가 적절히 차단되는 비율
```python
    [](<#cb26a-1>)monitor.thresholds = {
    [](<#cb26a-2>)    'privilege_escalation': 98.0  # 98% 이상이어야 Pass
    [](<#cb26a-3>)}
```

#### Attack Detection (공격 탐지)

**메트릭** : `attack_detection` **단위** : `%` **방향** : 높을수록 좋음 **정의** : 멀티에이전트 공격 패턴이 탐지되는 비율
```python
    [](<#cb26b-1>)monitor.thresholds = {
    [](<#cb26b-2>)    'attack_detection': 95.0  # 95% 이상이어야 Pass
    [](<#cb26b-3>)}
```

**통합 예제** :
```python
    [](<#cb26c-1>)# Layer 2: Agentic + Security Thresholds
    [](<#cb26c-2>)monitor.thresholds = {
    [](<#cb26c-3>)    # Agentic Metrics
    [](<#cb26c-4>)    'tool_selection_accuracy': 80.0,
    [](<#cb26c-5>)    'agent_coordination': 7.0,
    [](<#cb26c-6>)    'workflow_execution': 90.0,
    [](<#cb26c-7>)    # Security Metrics
    [](<#cb26c-8>)    'privilege_escalation': 98.0,
    [](<#cb26c-9>)    'attack_detection': 95.0
    [](<#cb26c-10>)}
```

* * *

## Threshold 설정 전략

### 1\. Bottom-Up 접근법 (권장)

**과정** : 1. **Threshold 없이** Golden Dataset 평가 실행 2. 현재 성능 확인 3. 현재 성능보다 **약간 높은** threshold 설정 4. 점진적으로 threshold 상향

**예제** :
```python
    [](<#cb27-1>)# 1단계: 평가 실행 (threshold 없음)
    [](<#cb27-2>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb27-3>)    agent_fn=my_agent,
    [](<#cb27-4>)    dataset_path="golden_dataset.json"
    [](<#cb27-5>))
    [](<#cb27-6>)
    [](<#cb27-7>)# 2단계: 현재 성능 확인
    [](<#cb27-8>)report = monitor.generate_report()
    [](<#cb27-9>)current_tcr = monitor.tcr_tracker.get_tcr()
    [](<#cb27-10>)current_accuracy = report.accuracy_metrics.get('overall_accuracy', 0)
    [](<#cb27-11>)print(f"현재 TCR: {current_tcr:.1f}%")  # 예: 87.5%
    [](<#cb27-12>)print(f"현재 Accuracy: {current_accuracy:.1f}%")  # 예: 82.3%
    [](<#cb27-13>)
    [](<#cb27-14>)# 3단계: 약간 높은 threshold 설정
    [](<#cb27-15>)monitor.thresholds = {
    [](<#cb27-16>)    'tcr': 85.0,  # 현재 87.5% → 85% 목표 (여유)
    [](<#cb27-17>)    'accuracy': 80.0  # 현재 82.3% → 80% 목표 (여유)
    [](<#cb27-18>)}
    [](<#cb27-19>)
    [](<#cb27-20>)# 4단계: 점진적 상향
    [](<#cb27-21>)# 다음 주: tcr 90%, accuracy 85%
    [](<#cb27-22>)# 다음 달: tcr 95%, accuracy 90%
```

### 2\. Top-Down 접근법

**과정** : 1. **이상적인 threshold** 먼저 설정 (프로덕션 기준) 2. 현재 성능과 비교 3. 실패한 메트릭 개선 4. 모든 메트릭이 Pass할 때까지 반복

**예제** :
```python
    [](<#cb28-1>)# 1단계: 이상적인 threshold 설정
    [](<#cb28-2>)monitor.thresholds = {
    [](<#cb28-3>)    'tcr': 95.0,
    [](<#cb28-4>)    'accuracy': 90.0,
    [](<#cb28-5>)    'hallucination': 3.0,
    [](<#cb28-6>)    'tool_selection_accuracy': 85.0,
    [](<#cb28-7>)    'agent_coordination': 8.0,
    [](<#cb28-8>)    'workflow_execution': 95.0
    [](<#cb28-9>)}
    [](<#cb28-10>)
    [](<#cb28-11>)# 2단계: 비교
    [](<#cb28-12>)comparison = monitor.compare_with_thresholds()
    [](<#cb28-13>)failed = [m for m, d in comparison.items() if d['status'] == 'fail']
    [](<#cb28-14>)
    [](<#cb28-15>)# 3단계: 실패 메트릭 개선
    [](<#cb28-16>)if 'accuracy' in failed:
    [](<#cb28-17>)    # 프롬프트 개선, Golden Dataset 업데이트 등
    [](<#cb28-18>)    pass
    [](<#cb28-19>)
    [](<#cb28-20>)# 4단계: 반복
```

### 3\. Benchmark 기반 접근법

**과정** : 1. **산업 표준** 또는 **경쟁사 벤치마크** 조사 2. 유사한 threshold 설정 3. 자사 상황에 맞게 조정

**예제** :
```python
    [](<#cb29-1>)# 산업 표준 (예: OpenAI, Anthropic 공개 벤치마크)
    [](<#cb29-2>)monitor.thresholds = {
    [](<#cb29-3>)    'tcr': 92.0,  # 산업 평균
    [](<#cb29-4>)    'accuracy': 87.0,  # 산업 평균
    [](<#cb29-5>)    'hallucination': 4.0  # 산업 평균
    [](<#cb29-6>)}
```

* * *

## 환경별 Threshold 설정

### 개발 환경 (Development)

**목적** : 빠른 실험과 반복 **특징** : 느슨한 threshold, 빠른 피드백
```json
    [](<#cb30-1>)# dev_thresholds.py
    [](<#cb30-2>)DEV_THRESHOLDS = {
    [](<#cb30-3>)    # Layer 1: 느슨한 기준
    [](<#cb30-4>)    'tcr': 70.0,
    [](<#cb30-5>)    'accuracy': 65.0,
    [](<#cb30-6>)    'hallucination': 15.0,
    [](<#cb30-7>)    'quality': 5.0,          # 5/10 이상
    [](<#cb30-8>)    'latency': 10.0,
    [](<#cb30-9>)    'cost_per_task': 0.50,
    [](<#cb30-10>)
    [](<#cb30-11>)    # Layer 2: 선택적 사용
    [](<#cb30-12>)    'tool_selection_accuracy': 60.0,
    [](<#cb30-13>)    # agent_coordination, workflow_execution은 생략 가능
    [](<#cb30-14>)}
    [](<#cb30-15>)
    [](<#cb30-16>)monitor.thresholds = DEV_THRESHOLDS
```

### 스테이징 환경 (Staging)

**목적** : 프로덕션 준비 검증 **특징** : 중간 수준 threshold, 프로덕션과 유사
```json
    [](<#cb31-1>)# staging_thresholds.py
    [](<#cb31-2>)STAGING_THRESHOLDS = {
    [](<#cb31-3>)    # Layer 1: 중간 기준
    [](<#cb31-4>)    'tcr': 85.0,
    [](<#cb31-5>)    'accuracy': 80.0,
    [](<#cb31-6>)    'hallucination': 8.0,
    [](<#cb31-7>)    'quality': 7.0,          # 7/10 이상
    [](<#cb31-8>)    'latency': 5.0,
    [](<#cb31-9>)    'cost_per_task': 0.20,
    [](<#cb31-10>)
    [](<#cb31-11>)    # Layer 2: 모두 사용
    [](<#cb31-12>)    'tool_selection_accuracy': 75.0,
    [](<#cb31-13>)    'agent_coordination': 7.0,
    [](<#cb31-14>)    'workflow_execution': 85.0
    [](<#cb31-15>)}
    [](<#cb31-16>)
    [](<#cb31-17>)monitor.thresholds = STAGING_THRESHOLDS
```

### 프로덕션 환경 (Production)

**목적** : 최고 품질 보장 **특징** : 엄격한 threshold, 높은 신뢰성
```json
    [](<#cb32-1>)# production_thresholds.py
    [](<#cb32-2>)PRODUCTION_THRESHOLDS = {
    [](<#cb32-3>)    # Layer 1: 엄격한 기준
    [](<#cb32-4>)    'tcr': 95.0,
    [](<#cb32-5>)    'accuracy': 90.0,
    [](<#cb32-6>)    'hallucination': 3.0,
    [](<#cb32-7>)    'quality': 8.0,          # 8/10 이상
    [](<#cb32-8>)    'latency': 3.0,
    [](<#cb32-9>)    'cost_per_task': 0.15,
    [](<#cb32-10>)
    [](<#cb32-11>)    # Layer 2: 높은 기준
    [](<#cb32-12>)    'tool_selection_accuracy': 85.0,
    [](<#cb32-13>)    'agent_coordination': 8.5,
    [](<#cb32-14>)    'workflow_execution': 95.0
    [](<#cb32-15>)}
    [](<#cb32-16>)
    [](<#cb32-17>)monitor.thresholds = PRODUCTION_THRESHOLDS
```

### 환경 자동 감지
```python
    [](<#cb33-1>)import os
    [](<#cb33-2>)
    [](<#cb33-3>)def get_thresholds_for_env():
    [](<#cb33-4>)    env = os.getenv("ENV", "development")
    [](<#cb33-5>)
    [](<#cb33-6>)    if env == "production":
    [](<#cb33-7>)        return PRODUCTION_THRESHOLDS
    [](<#cb33-8>)    elif env == "staging":
    [](<#cb33-9>)        return STAGING_THRESHOLDS
    [](<#cb33-10>)    else:
    [](<#cb33-11>)        return DEV_THRESHOLDS
    [](<#cb33-12>)
    [](<#cb33-13>)monitor.thresholds = get_thresholds_for_env()
```

### Threshold 파일에서 로드

`load_thresholds_from_config()` 메서드를 사용하여 저장된 임계값을 자동으로 로드할 수 있습니다.

#### 기본 임계값 로드
```python
    [](<#cb34-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb34-2>)
    [](<#cb34-3>)monitor = PerformanceMonitor()
    [](<#cb34-4>)
    [](<#cb34-5>)# 기본 임계값 파일(thresholds.json)에서 로드
    [](<#cb34-6>)monitor.load_thresholds_from_config()
    [](<#cb34-7>)
    [](<#cb34-8>)# 로드된 임계값 확인
    [](<#cb34-9>)print(monitor.thresholds)
    [](<#cb34-10>)# {'tcr': 90.0, 'accuracy': 85.0, 'hallucination': 5.0, ...}
```

#### Test Configuration에서 로드
```python
    [](<#cb35-1>)# 특정 Test Configuration ID를 지정하여 로드
    [](<#cb35-2>)monitor.load_thresholds_from_config(config_id="production_test_v1")
    [](<#cb35-3>)
    [](<#cb35-4>)# Test Configuration에 저장된 임계값이 로드됨
    [](<#cb35-5>)print(monitor.thresholds)
```

#### 로드 우선순위

  1. **config_id 지정 시** : Test Configuration의 `thresholds` 필드
  2. **config_id 없을 때** : `data/thresholds.json` 파일
  3. **파일 없을 때** : PerformanceMonitor 내장 기본값


```json
    [](<#cb36-1>)// PerformanceMonitor 기본 임계값 (v0.6.0)
    [](<#cb36-2>){
    [](<#cb36-3>)    "// Layer 1: Foundation Metrics": "",
    [](<#cb36-4>)    "tcr": 90.0,
    [](<#cb36-5>)    "accuracy": 85.0,
    [](<#cb36-6>)    "hallucination": 5.0,
    [](<#cb36-7>)    "quality": 7.0,
    [](<#cb36-8>)    "latency": 3.0,
    [](<#cb36-9>)    "cost_per_task": 0.05,
    [](<#cb36-10>)    "// Layer 2: Security Metrics": "",
    [](<#cb36-11>)    "input_sanitization": 95.0,
    [](<#cb36-12>)    "output_leakage": 95.0,
    [](<#cb36-13>)    "authorization": 98.0,
    [](<#cb36-14>)    "// Layer 3: Hybrid Metrics": "",
    [](<#cb36-15>)    "faithfulness": 0.8,
    [](<#cb36-16>)    "answer_relevancy": 0.8,
    [](<#cb36-17>)    "context_recall": 0.8,
    [](<#cb36-18>)    "context_precision": 0.8
    [](<#cb36-19>)}
```

#### 임계값 저장 (JSON 파일)

임계값을 JSON 파일에 저장하고 `load_thresholds_from_config()`로 불러올 수 있습니다:
```python
    [](<#cb37-1>)import json
    [](<#cb37-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb37-3>)
    [](<#cb37-4>)# 임계값을 파일에 저장
    [](<#cb37-5>)thresholds = {'tcr': 95.0, 'accuracy': 90.0, 'hallucination': 3.0}
    [](<#cb37-6>)with open("thresholds.json", "w") as f:
    [](<#cb37-7>)    json.dump(thresholds, f)
    [](<#cb37-8>)
    [](<#cb37-9>)# 저장된 임계값 로드
    [](<#cb37-10>)monitor = PerformanceMonitor()
    [](<#cb37-11>)monitor.load_thresholds_from_config()
```

* * *

## Threshold 비교 및 검증

### compare_with_thresholds() 메서드

`compare_with_thresholds()` 메서드는 현재 메트릭 값을 임계값과 비교하여 Pass/Fail 판정을 제공합니다.

#### 반환값 구조
```json
    [](<#cb38-1>){
    [](<#cb38-2>)    'metric_name': {
    [](<#cb38-3>)        'name': str,           # 메트릭 표시 이름 (한글)
    [](<#cb38-4>)        'value': float,        # 현재 측정값
    [](<#cb38-5>)        'threshold': float,    # 임계값
    [](<#cb38-6>)        'status': str,         # 'pass' | 'fail' | 'pending'
    [](<#cb38-7>)        'direction': str,      # 'higher' | 'lower' (높을수록 좋은지, 낮을수록 좋은지)
    [](<#cb38-8>)        'unit': str,          # 단위 ('%', 's', '$', '/10', 등)
    [](<#cb38-9>)        'layer': str,         # 'Layer 2' (Layer 1 메트릭은 이 필드 없음)
    [](<#cb38-10>)        'details': dict       # 추가 상세 정보 (선택적, Layer 2 일부 메트릭에만 존재)
    [](<#cb38-11>)    }
    [](<#cb38-12>)}
```

#### 지원되는 메트릭

**Layer 1 (Basic Metrics)** :

  * `tcr`: Task Completion Rate (%)
  * `accuracy`: Accuracy (%)
  * `hallucination`: Hallucination Rate (%)
  * `quality`: Response Quality (/10) ✨ _: 자동 계산_
  * `latency`: Latency (s, P95 기준)
  * `cost_per_task`: Cost per Task ($)
  * `faithfulness`: Faithfulness (0-1) ⚡ _: 실제 값 계산_
  * `answer_relevancy`: Answer Relevancy (0-1) ⚡ _: 실제 값 계산_
  * `context_recall`: Context Recall (0-1) ⚡ _: 실제 값 계산_
  * `context_precision`: Context Precision (0-1) ⚡ _: 실제 값 계산_

**Layer 2 (Security Metrics)** ⚡ _v0.6.0_ :

  * `input_sanitization`: Input Sanitization (%)
  * `output_leakage`: Output Leakage Prevention (%)
  * `authorization`: Authorization Verification (%)

**Layer 2 (Agentic Metrics)** :

  * `tool_selection_accuracy`: Tool Selection Accuracy (%)
  * `agent_coordination`: Agent Coordination (/10) - details 포함
  * `workflow_execution`: Workflow Execution (%) - details 포함

**Layer 2 (Security Metrics)** ⚡ _v0.6.0_ :

  * `privilege_escalation`: Privilege Escalation Detection (%)
  * `attack_detection`: Attack Pattern Detection (%)

> **✨ 개선사항** : RAG 메트릭(faithfulness, answer_relevancy, context_recall, context_precision)이 이제 실제 값으로 계산되며, `compare_with_thresholds()`에서 자동으로 pass/fail 판정을 수행합니다. Response Quality도 자동 계산됩니다.

### 기본 비교 예제
```python
    [](<#cb39-1>)# Threshold 설정
    [](<#cb39-2>)monitor.thresholds = {
    [](<#cb39-3>)    'tcr': 90.0,
    [](<#cb39-4>)    'accuracy': 85.0,
    [](<#cb39-5>)    'tool_selection_accuracy': 80.0
    [](<#cb39-6>)}
    [](<#cb39-7>)
    [](<#cb39-8>)# Golden Dataset 평가
    [](<#cb39-9>)results = monitor.evaluate_with_golden_dataset(
    [](<#cb39-10>)    agent_fn=my_agent,
    [](<#cb39-11>)    dataset_path="golden_dataset.json",
    [](<#cb39-12>)    enable_layer2_metrics=True
    [](<#cb39-13>))
    [](<#cb39-14>)
    [](<#cb39-15>)# Threshold 비교
    [](<#cb39-16>)comparison = monitor.compare_with_thresholds()
    [](<#cb39-17>)
    [](<#cb39-18>)# 결과 출력
    [](<#cb39-19>)for metric, data in comparison.items():
    [](<#cb39-20>)    status_icon = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb39-21>)    print(f"{status_icon} {data['name']}: {data['value']:.1f}{data['unit']} (임계값: {data['threshold']}{data['unit']})")
```

**출력 예제** :
```
    ✅ 작업 완료율 (TCR): 92.5% (임계값: 90.0%)
    ✅ 정확도 (Accuracy): 87.3% (임계값: 85.0%)
    ❌ 도구 선택 정확도 (Tool Selection Accuracy): 75.2% (임계값: 80.0%)
```

### 상세 비교 예제
```python
    [](<#cb41-1>)comparison = monitor.compare_with_thresholds()
    [](<#cb41-2>)
    [](<#cb41-3>)for metric, data in comparison.items():
    [](<#cb41-4>)    print(f"\n{'='*70}")
    [](<#cb41-5>)    print(f"{data['name']}")
    [](<#cb41-6>)    print(f"{'='*70}")
    [](<#cb41-7>)    print(f"Layer: {data.get('layer', 'Layer 1')}")
    [](<#cb41-8>)    print(f"현재값: {data['value']:.2f}{data['unit']}")
    [](<#cb41-9>)    print(f"임계값: {data['threshold']}{data['unit']}")
    [](<#cb41-10>)    print(f"방향: {'높을수록 좋음' if data['direction'] == 'higher' else '낮을수록 좋음'}")
    [](<#cb41-11>)    print(f"상태: {'✅ PASS' if data['status'] == 'pass' else '❌ FAIL'}")
    [](<#cb41-12>)
    [](<#cb41-13>)    # Layer 2 메트릭의 상세 정보 출력
    [](<#cb41-14>)    if 'details' in data:
    [](<#cb41-15>)        print(f"\n상세 정보:")
    [](<#cb41-16>)        for key, value in data['details'].items():
    [](<#cb41-17>)            print(f"  • {key}: {value}")
```

**출력 예제** (Agent Coordination):
```
    ======================================================================
    에이전트 협업 점수 (Agent Coordination)
    ======================================================================
    Layer: Layer 2
    현재값: 8.50/10
    임계값: 7.0/10
    방향: 높을수록 좋음
    상태: ✅ PASS
    
    상세 정보:
      • success_rate: 0.95
      • total_interactions: 42
      • unique_agents: 5
```

### Pass/Fail 판정
```python
    [](<#cb43-1>)comparison = monitor.compare_with_thresholds()
    [](<#cb43-2>)failed_metrics = [metric for metric, data in comparison.items() if data['status'] == 'fail']
    [](<#cb43-3>)
    [](<#cb43-4>)if failed_metrics:
    [](<#cb43-5>)    print(f"❌ 품질 게이트 실패!")
    [](<#cb43-6>)    print(f"실패한 메트릭: {len(failed_metrics)}개")
    [](<#cb43-7>)    for metric in failed_metrics:
    [](<#cb43-8>)        data = comparison[metric]
    [](<#cb43-9>)        print(f"  - {data['name']}: {data['value']:.1f}{data['unit']} (필요: {data['threshold']}{data['unit']})")
    [](<#cb43-10>)    exit(1)  # CI/CD 실패
    [](<#cb43-11>)else:
    [](<#cb43-12>)    print(f"✅ 품질 게이트 통과!")
    [](<#cb43-13>)    print(f"모든 메트릭이 임계값을 충족합니다.")
    [](<#cb43-14>)    exit(0)  # CI/CD 성공
```

* * *

## ✨ RAG 메트릭 Threshold 설정

RAG (Retrieval-Augmented Generation) 시스템을 평가할 때 사용하는 4가지 핵심 메트릭에 대한 threshold 설정 가이드입니다.

### RAG 메트릭 개요

이제 PerformanceMonitor가 RAG 메트릭을 직접 추적하고, `compare_with_thresholds()`에서 자동으로 실제 값을 계산하여 pass/fail 판정을 수행합니다.

메트릭 | 설명 | 범위 | 권장 임계값 | 방향  
---|---|---|---|---  
`faithfulness` | 답변이 제공된 컨텍스트에 충실한 정도 (환각 방지) | 0-1 | ≥0.8 | 높을수록 좋음  
`answer_relevancy` | 답변이 질문과 관련있는 정도 | 0-1 | ≥0.85 | 높을수록 좋음  
`context_recall` | 필요한 정보를 컨텍스트에서 잘 검색했는지 (완전성) | 0-1 | ≥0.75 | 높을수록 좋음  
`context_precision` | 검색된 컨텍스트의 정확도 (노이즈 최소화) | 0-1 | ≥0.8 | 높을수록 좋음  
  
### RAG Threshold 설정 예제
```python
    [](<#cb43a-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb43a-2>)
    [](<#cb43a-3>)# PerformanceMonitor 초기화
    [](<#cb43a-4>)monitor = PerformanceMonitor()
    [](<#cb43a-5>)
    [](<#cb43a-6>)# RAG 메트릭 threshold 설정
    [](<#cb43a-7>)monitor.thresholds = {
    [](<#cb43a-8>)    "faithfulness": 0.8,           # 환각 방지
    [](<#cb43a-9>)    "answer_relevancy": 0.85,      # 답변 관련성
    [](<#cb43a-10>)    "context_recall": 0.75,        # 검색 완전성
    [](<#cb43a-11>)    "context_precision": 0.8,     # 검색 정확도
    [](<#cb43a-12>)}
    [](<#cb43a-13>)
    [](<#cb43a-14>)# RAG 메트릭 기록
    [](<#cb43a-15>)monitor.record_rag_metrics(
    [](<#cb43a-16>)    faithfulness=0.85,
    [](<#cb43a-17>)    answer_relevancy=0.88,
    [](<#cb43a-18>)    context_recall=0.78,
    [](<#cb43a-19>)    context_precision=0.82
    [](<#cb43a-20>))
    [](<#cb43a-21>)
    [](<#cb43a-22>)# 최신 기능: Threshold 비교 (자동으로 실제 값 계산)
    [](<#cb43a-23>)comparison = monitor.compare_with_thresholds()
    [](<#cb43a-24>)
    [](<#cb43a-25>)# 결과 확인
    [](<#cb43a-26>)for metric in ["faithfulness", "answer_relevancy", "context_recall", "context_precision"]:
    [](<#cb43a-27>)    data = comparison[metric]
    [](<#cb43a-28>)    status = "✅" if data["status"] == "pass" else "❌"
    [](<#cb43a-29>)    print(f"{status} {data['name']}: {data['value']:.3f} (임계값: {data['threshold']})")
```

**출력 예제** :
```
    ✅ Faithfulness: 0.850 (임계값: 0.8)
    ✅ Answer Relevancy: 0.880 (임계값: 0.85)
    ✅ Context Recall: 0.780 (임계값: 0.75)
    ✅ Context Precision: 0.820 (임계값: 0.8)
```

### RAG 메트릭 요약 확인
```python
    [](<#cb43b-1>)# RAG 메트릭 요약 가져오기
    [](<#cb43b-2>)rag_summary = monitor.get_rag_metrics_summary()
    [](<#cb43b-3>)
    [](<#cb43b-4>)print(f"평균 Faithfulness: {rag_summary['faithfulness']['mean']:.3f}")
    [](<#cb43b-5>)print(f"평균 Answer Relevancy: {rag_summary['answer_relevancy']['mean']:.3f}")
    [](<#cb43b-6>)print(f"평균 Context Recall: {rag_summary['context_recall']['mean']:.3f}")
    [](<#cb43b-7>)print(f"평균 Context Precision: {rag_summary['context_precision']['mean']:.3f}")
```

### 한국어 RAG 평가와 통합

KoreanRAGEvaluator와 함께 사용하여 한국어 RAG 시스템을 체계적으로 평가할 수 있습니다.
```python
    [](<#cb43c-1>)from agent_evaluator import PerformanceMonitor
    [](<#cb43c-2>)from korean_rag_evaluator import KoreanRAGEvaluator
    [](<#cb43c-3>)
    [](<#cb43c-4>)# 초기화
    [](<#cb43c-5>)monitor = PerformanceMonitor()
    [](<#cb43c-6>)rag_evaluator = KoreanRAGEvaluator(rag_system=my_rag_system)
    [](<#cb43c-7>)
    [](<#cb43c-8>)# Threshold 설정
    [](<#cb43c-9>)monitor.thresholds = {
    [](<#cb43c-10>)    "faithfulness": 0.8,
    [](<#cb43c-11>)    "answer_relevancy": 0.85,
    [](<#cb43c-12>)    "context_recall": 0.75,
    [](<#cb43c-13>)    "context_precision": 0.8
    [](<#cb43c-14>)}
    [](<#cb43c-15>)
    [](<#cb43c-16>)# 개별 QA 평가 및 기록
    [](<#cb43c-17>)result = rag_evaluator.evaluate_single(
    [](<#cb43c-18>)    question="한국의 수도는 어디인가요?",
    [](<#cb43c-19>)    expected_answer="서울입니다"
    [](<#cb43c-20>))
    [](<#cb43c-21>)
    [](<#cb43c-22>)# PerformanceMonitor에 기록
    [](<#cb43c-23>)monitor.record_rag_metrics(
    [](<#cb43c-24>)    faithfulness=result.faithfulness,
    [](<#cb43c-25>)    answer_relevancy=result.answer_relevancy,
    [](<#cb43c-26>)    context_recall=result.context_recall,
    [](<#cb43c-27>)    context_precision=result.context_precision
    [](<#cb43c-28>))
    [](<#cb43c-29>)
    [](<#cb43c-30>)# Threshold 비교 (자동 pass/fail 판정)
    [](<#cb43c-31>)comparison = monitor.compare_with_thresholds()
    [](<#cb43c-32>)
    [](<#cb43c-33>)# CSV 내보내기 (RAG 메트릭 포함)
    [](<#cb43c-34>)monitor.export_report("rag_evaluation_report.csv", format="csv")
```

> **⚡ 핵심 개선사항** :
> 
>   * `record_rag_metrics()`: RAG 메트릭을 PerformanceMonitor에 직접 기록
>   * `compare_with_thresholds()`: RAG 메트릭의 실제 평균값을 자동 계산하여 pass/fail 판정
>   * `get_rag_metrics_summary()`: RAG 메트릭의 평균, 최소, 최대, 표준편차 등 통계 제공
>   * `export_report()`: CSV 내보내기 시 RAG 메트릭 자동 포함 (13+ 메트릭 지원)
> 


* * *

## CI/CD 통합

### CI/CD 예제 (GitLab CI / Jenkins 권장)
```json
    [](<#cb44-1>)# .github/workflows/agent-quality-gate.yml
    [](<#cb44-2>)name: Agent Quality Gate
    [](<#cb44-3>)
    [](<#cb44-4>)on:
    [](<#cb44-5>)  push:
    [](<#cb44-6>)    branches: [main, develop]
    [](<#cb44-7>)  pull_request:
    [](<#cb44-8>)    branches: [main]
    [](<#cb44-9>)
    [](<#cb44-10>)jobs:
    [](<#cb44-11>)  quality-gate:
    [](<#cb44-12>)    runs-on: ubuntu-latest
    [](<#cb44-13>)
    [](<#cb44-14>)    steps:
    [](<#cb44-15>)      - uses: actions/checkout@v3
    [](<#cb44-16>)
    [](<#cb44-17>)      - name: Set up Python
    [](<#cb44-18>)        uses: actions/setup-python@v4
    [](<#cb44-19>)        with:
    [](<#cb44-20>)          python-version: '3.10'
    [](<#cb44-21>)
    [](<#cb44-22>)      - name: Install dependencies
    [](<#cb44-23>)        run: |
    [](<#cb44-24>)          pip install agent-evaluator
    [](<#cb44-26>)
    [](<#cb44-27>)      - name: Run Quality Gate
    [](<#cb44-28>)        env:
    [](<#cb44-29>)          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    [](<#cb44-30>)          ENV: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}
    [](<#cb44-31>)        run: |
    [](<#cb44-32>)          python ci_quality_gate.py
    [](<#cb44-33>)
    [](<#cb44-34>)      - name: Upload Results
    [](<#cb44-35>)        if: always()
    [](<#cb44-36>)        uses: actions/upload-artifact@v3
    [](<#cb44-37>)        with:
    [](<#cb44-38>)          name: evaluation-results
    [](<#cb44-39>)          path: evaluation_results.json
```

### CI/CD 스크립트
```python
    [](<#cb45-1>)# ci_quality_gate.py
    [](<#cb45-2>)import os
    [](<#cb45-3>)import sys
    [](<#cb45-4>)from agent_evaluator import PerformanceMonitor
    [](<#cb45-5>)
    [](<#cb45-6>)def main():
    [](<#cb45-7>)    monitor = PerformanceMonitor()
    [](<#cb45-8>)
    [](<#cb45-9>)    # 환경별 Threshold 설정
    [](<#cb45-10>)    env = os.getenv("ENV", "development")
    [](<#cb45-11>)
    [](<#cb45-12>)    if env == "production":
    [](<#cb45-13>)        monitor.thresholds = {
    [](<#cb45-14>)            'tcr': 95.0,
    [](<#cb45-15>)            'accuracy': 90.0,
    [](<#cb45-16>)            'hallucination': 3.0,
    [](<#cb45-17>)            'tool_selection_accuracy': 85.0,
    [](<#cb45-18>)            'agent_coordination': 8.0,
    [](<#cb45-19>)            'workflow_execution': 95.0
    [](<#cb45-20>)        }
    [](<#cb45-21>)    elif env == "staging":
    [](<#cb45-22>)        monitor.thresholds = {
    [](<#cb45-23>)            'tcr': 85.0,
    [](<#cb45-24>)            'accuracy': 80.0,
    [](<#cb45-25>)            'hallucination': 8.0,
    [](<#cb45-26>)            'tool_selection_accuracy': 75.0,
    [](<#cb45-27>)            'agent_coordination': 7.0,
    [](<#cb45-28>)            'workflow_execution': 85.0
    [](<#cb45-29>)        }
    [](<#cb45-30>)    else:
    [](<#cb45-31>)        monitor.thresholds = {
    [](<#cb45-32>)            'tcr': 70.0,
    [](<#cb45-33>)            'accuracy': 65.0,
    [](<#cb45-34>)            'tool_selection_accuracy': 60.0
    [](<#cb45-35>)        }
    [](<#cb45-36>)
    [](<#cb45-37>)    print(f"🚀 환경: {env}")
    [](<#cb45-38>)    print(f"📊 Threshold:")
    [](<#cb45-39>)    for metric, value in monitor.thresholds.items():
    [](<#cb45-40>)        print(f"   {metric}: {value}")
    [](<#cb45-41>)
    [](<#cb45-42>)    # Golden Dataset 평가
    [](<#cb45-43>)    print(f"\n🔍 Golden Dataset 평가 실행 중...")
    [](<#cb45-44>)    results = monitor.evaluate_with_golden_dataset(
    [](<#cb45-45>)        agent_fn=my_agent,
    [](<#cb45-46>)        dataset_path="golden_dataset.json",
    [](<#cb45-47>)        enable_layer2_metrics=True
    [](<#cb45-48>)    )
    [](<#cb45-49>)
    [](<#cb45-50>)    # Threshold 비교
    [](<#cb45-51>)    print(f"\n🎯 Threshold 비교:")
    [](<#cb45-52>)    comparison = monitor.compare_with_thresholds()
    [](<#cb45-53>)
    [](<#cb45-54>)    passed = []
    [](<#cb45-55>)    failed = []
    [](<#cb45-56>)
    [](<#cb45-57>)    for metric, data in comparison.items():
    [](<#cb45-58>)        status_icon = "✅" if data['status'] == 'pass' else "❌"
    [](<#cb45-59>)        print(f"{status_icon} {data['name']}: {data['value']:.1f}{data['unit']} (임계값: {data['threshold']}{data['unit']})")
    [](<#cb45-60>)
    [](<#cb45-61>)        if data['status'] == 'pass':
    [](<#cb45-62>)            passed.append(metric)
    [](<#cb45-63>)        else:
    [](<#cb45-64>)            failed.append(metric)
    [](<#cb45-65>)
    [](<#cb45-66>)    # 결과 요약
    [](<#cb45-67>)    print(f"\n📊 요약:")
    [](<#cb45-68>)    print(f"   통과: {len(passed)}개")
    [](<#cb45-69>)    print(f"   실패: {len(failed)}개")
    [](<#cb45-70>)
    [](<#cb45-71>)    # CI/CD 판정
    [](<#cb45-72>)    if failed:
    [](<#cb45-73>)        print(f"\n❌ CI/CD 품질 게이트 실패!")
    [](<#cb45-74>)        print(f"\n실패한 메트릭 ({len(failed)}개):")
    [](<#cb45-75>)        for metric in failed:
    [](<#cb45-76>)            data = comparison[metric]
    [](<#cb45-77>)            print(f"   - {data['name']}")
    [](<#cb45-78>)            print(f"     현재: {data['value']:.1f}{data['unit']}")
    [](<#cb45-79>)            print(f"     필요: {data['threshold']}{data['unit']}")
    [](<#cb45-80>)
    [](<#cb45-81>)        print(f"\n💡 조치 필요:")
    [](<#cb45-82>)        print(f"   1. 에이전트 프롬프트 개선")
    [](<#cb45-83>)        print(f"   2. Golden Dataset 검토 및 업데이트")
    [](<#cb45-84>)        print(f"   3. Threshold 재검토 (필요시)")
    [](<#cb45-85>)
    [](<#cb45-86>)        sys.exit(1)  # CI/CD 실패
    [](<#cb45-87>)    else:
    [](<#cb45-88>)        print(f"\n✅ CI/CD 품질 게이트 통과!")
    [](<#cb45-89>)        print(f"   모든 메트릭이 임계값을 충족합니다.")
    [](<#cb45-90>)        print(f"   배포를 진행하세요.")
    [](<#cb45-91>)
    [](<#cb45-92>)        sys.exit(0)  # CI/CD 성공
    [](<#cb45-93>)
    [](<#cb45-94>)def my_agent(question: str):
    [](<#cb45-95>)    # 에이전트 구현
    [](<#cb45-96>)    pass
    [](<#cb45-97>)
    [](<#cb45-98>)if __name__ == "__main__":
    [](<#cb45-99>)    main()
```

### GitLab CI 예제
```json
    [](<#cb46-1>)# .gitlab-ci.yml
    [](<#cb46-2>)stages:
    [](<#cb46-3>)  - test
    [](<#cb46-4>)  - quality-gate
    [](<#cb46-5>)  - deploy
    [](<#cb46-6>)
    [](<#cb46-7>)quality-gate:
    [](<#cb46-8>)  stage: quality-gate
    [](<#cb46-9>)  image: python:3.10
    [](<#cb46-10>)  script:
    [](<#cb46-11>)    - pip install agent-evaluator
    [](<#cb46-13>)    - python ci_quality_gate.py
    [](<#cb46-14>)  artifacts:
    [](<#cb46-15>)    when: always
    [](<#cb46-16>)    paths:
    [](<#cb46-17>)      - evaluation_results.json
    [](<#cb46-18>)    reports:
    [](<#cb46-19>)      junit: test-results.xml
    [](<#cb46-20>)  only:
    [](<#cb46-21>)    - main
    [](<#cb46-22>)    - develop
```

* * *

## Best Practices

### 1\. Threshold 설정 원칙

#### ✅ 좋은 원칙

**점진적 상향** \- 처음부터 너무 높은 threshold 설정하지 말기 - 현재 성능 → 약간 높은 threshold → 점진적 개선

**환경별 차별화** \- 개발: 느슨한 threshold (빠른 실험) - 스테이징: 중간 threshold (품질 검증) - 프로덕션: 엄격한 threshold (높은 품질)

**메트릭 우선순위** \- 핵심 메트릭 (TCR, Accuracy)에 집중 \- 나머지는 점진적으로 추가

**데이터 기반 결정** \- 실제 평가 결과를 바탕으로 threshold 설정 - 주관적 판단 최소화

#### ❌ 나쁜 원칙

**비현실적 목표**
```python
    [](<#cb47-1>)# 너무 높음 - 달성 불가능
    [](<#cb47-2>)monitor.thresholds = {
    [](<#cb47-3>)    'tcr': 100.0,  # 100%는 비현실적
    [](<#cb47-4>)    'accuracy': 99.0,
    [](<#cb47-5>)    'hallucination': 0.0  # 0%는 불가능
    [](<#cb47-6>)}
```

**환경 무시**
```python
    [](<#cb48-1>)# 개발 환경에서 프로덕션 threshold 사용 - 실험 방해
    [](<#cb48-2>)monitor.thresholds = PRODUCTION_THRESHOLDS  # ❌
```

**너무 많은 메트릭**
```python
    [](<#cb49-1>)# 한 번에 모든 메트릭 추가 - 관리 어려움
    [](<#cb49-2>)monitor.thresholds = {
    [](<#cb49-3>)    'tcr': 90.0,
    [](<#cb49-4>)    'accuracy': 85.0,
    [](<#cb49-5>)    'quality': 80.0,
    [](<#cb49-6>)    'relevance': 80.0,
    [](<#cb49-7>)    'hallucination': 5.0,
    [](<#cb49-8>)    'latency': 3.0,
    [](<#cb49-9>)    'cost_per_task': 0.10,
    [](<#cb49-10>)    'tool_selection_accuracy': 80.0,
    [](<#cb49-11>)    'agent_coordination': 7.0,
    [](<#cb49-12>)    'workflow_execution': 90.0,
    [](<#cb49-13>)    # ... 너무 많음
    [](<#cb49-14>)}
```

### 2\. Threshold 업데이트 주기

**권장 주기** :

  * **주간 리뷰** : 현재 성능 확인, 작은 조정
  * **월간 리뷰** : Threshold 상향, 새 메트릭 추가
  * **분기 리뷰** : 전체 Threshold 체계 재검토

**예제** :
```python
    [](<#cb50-1>)# 주간 (Week 1)
    [](<#cb50-2>)monitor.thresholds = {
    [](<#cb50-3>)    'tcr': 85.0,
    [](<#cb50-4>)    'accuracy': 80.0
    [](<#cb50-5>)}
    [](<#cb50-6>)
    [](<#cb50-7>)# 주간 (Week 4)
    [](<#cb50-8>)monitor.thresholds = {
    [](<#cb50-9>)    'tcr': 88.0,  # +3%
    [](<#cb50-10>)    'accuracy': 82.0  # +2%
    [](<#cb50-11>)}
    [](<#cb50-12>)
    [](<#cb50-13>)# 월간 (Month 2)
    [](<#cb50-14>)monitor.thresholds = {
    [](<#cb50-15>)    'tcr': 90.0,  # +5% from start
    [](<#cb50-16>)    'accuracy': 85.0,  # +5% from start
    [](<#cb50-17>)    'tool_selection_accuracy': 75.0  # 새 메트릭 추가
    [](<#cb50-18>)}
```

### 3\. 실패 시 대응

#### Threshold 실패가 발생하면:

**1) 원인 분석** \- 어떤 메트릭이 실패했는가? - 어떤 QAPair에서 실패했는가? - 일시적 문제인가, 구조적 문제인가?

**2) 우선순위 결정** \- 핵심 메트릭 (TCR, Accuracy) 먼저 해결 - Layer 2 메트릭은 나중에

**3) 개선 조치** \- 프롬프트 개선 - Golden Dataset 업데이트 - 에이전트 로직 수정 - (최후) Threshold 완화

**4) 재평가** \- 개선 후 다시 평가 - 통과할 때까지 반복

**예제** :
```python
    [](<#cb51-1>)# 실패 분석
    [](<#cb51-2>)comparison = monitor.compare_with_thresholds()
    [](<#cb51-3>)failed = [m for m, d in comparison.items() if d['status'] == 'fail']
    [](<#cb51-4>)
    [](<#cb51-5>)if 'accuracy' in failed:
    [](<#cb51-6>)    print("Accuracy 실패 - Golden Dataset의 ground_truth 검토")
    [](<#cb51-7>)    # Dashboard에서 실패한 QAPair 확인
    [](<#cb51-8>)    # ground_truth 업데이트
    [](<#cb51-9>)    # 재평가
    [](<#cb51-10>)
    [](<#cb51-11>)if 'tool_selection_accuracy' in failed:
    [](<#cb51-12>)    print("Tool Selection 실패 - expected_tools 확인")
    [](<#cb51-13>)    # Dashboard에서 실제 사용 도구 vs expected_tools 비교
    [](<#cb51-14>)    # expected_tools 업데이트 또는 프롬프트 개선
    [](<#cb51-15>)    # 재평가
```

### 4\. 문서화

**Threshold 변경 이력 기록** :
```json
    [](<#cb52-1>)# Threshold Change Log
    [](<#cb52-2>)
    [](<#cb52-3>)## 2024-01-15
    [](<#cb52-4>)- TCR: 85% → 90% (성능 개선)
    [](<#cb52-5>)- Accuracy: 80% → 85% (프롬프트 개선 후)
    [](<#cb52-6>)
    [](<#cb52-7>)## 2024-01-01
    [](<#cb52-8>)- Tool Selection Accuracy: 75% 추가 (Layer 2 도입)
    [](<#cb52-9>)- Agent Coordination: 7/10 추가
```

* * *

## 시나리오별 예제

### 시나리오 1: 간단한 QA 챗봇

**특징** : 단일 에이전트, 간단한 질문 응답
```python
    [](<#cb53-1>)monitor.thresholds = {
    [](<#cb53-2>)    # Layer 1만 사용
    [](<#cb53-3>)    'tcr': 90.0,  # 높은 완료율
    [](<#cb53-4>)    'accuracy': 85.0,  # 정확한 응답
    [](<#cb53-5>)    'latency': 2.0,  # 빠른 응답 (2초)
    [](<#cb53-6>)    'cost_per_task': 0.05  # 저비용 ($0.05)
    [](<#cb53-7>)    # Layer 2는 불필요 (단일 에이전트)
    [](<#cb53-8>)}
```

### 시나리오 2: 복잡한 Research Agent (Multi-Agent)

**특징** : 여러 에이전트 협업, 긴 작업 시간, 도구 사용
```python
    [](<#cb54-1>)monitor.thresholds = {
    [](<#cb54-2>)    # Layer 1
    [](<#cb54-3>)    'tcr': 85.0,  # 복잡한 작업이므로 약간 낮춤
    [](<#cb54-4>)    'accuracy': 80.0,
    [](<#cb54-5>)    'latency': 30.0,  # 긴 작업 시간 허용
    [](<#cb54-6>)    'cost_per_task': 1.00,  # 높은 비용 허용
    [](<#cb54-7>)
    [](<#cb54-8>)    # Layer 2 (핵심!)
    [](<#cb54-9>)    'tool_selection_accuracy': 85.0,  # 도구 선택 중요
    [](<#cb54-10>)    'agent_coordination': 8.0,  # 협업 품질 중요
    [](<#cb54-11>)    'workflow_execution': 90.0  # 워크플로우 안정성 중요
    [](<#cb54-12>)}
```

### 시나리오 3: RAG 시스템

**특징** : 문서 검색 + 생성, Workflow 중심
```python
    [](<#cb55-1>)monitor.thresholds = {
    [](<#cb55-2>)    # Layer 1
    [](<#cb55-3>)    'tcr': 95.0,  # 높은 안정성 요구
    [](<#cb55-4>)    'accuracy': 90.0,  # 정확한 정보 제공
    [](<#cb55-5>)    'hallucination': 3.0,  # 낮은 환각률 (RAG에서 중요)
    [](<#cb55-6>)    'latency': 5.0,
    [](<#cb55-7>)
    [](<#cb55-8>)    # Layer 2
    [](<#cb55-9>)    'tool_selection_accuracy': 80.0,  # vector_search, pdf_reader 선택
    [](<#cb55-10>)    'workflow_execution': 95.0  # retrieval → generation 안정성
    [](<#cb55-11>)}
```

### 시나리오 4: 고객 지원 Agent

**특징** : 빠른 응답, 높은 정확도, 낮은 비용
```python
    [](<#cb56-1>)monitor.thresholds = {
    [](<#cb56-2>)    # Layer 1
    [](<#cb56-3>)    'tcr': 95.0,  # 거의 모든 요청 처리
    [](<#cb56-4>)    'accuracy': 90.0,  # 정확한 답변
    [](<#cb56-5>)    'latency': 3.0,  # 빠른 응답
    [](<#cb56-6>)    'cost_per_task': 0.10,  # 낮은 비용 (대량 요청)
    [](<#cb56-7>)
    [](<#cb56-8>)    # Layer 2
    [](<#cb56-9>)    'tool_selection_accuracy': 85.0  # knowledge_base, order_db 등
    [](<#cb56-10>)}
```

### 시나리오 5: 실험적 Agent (초기 개발)

**특징** : 빠른 반복, 느슨한 기준
```python
    [](<#cb57-1>)monitor.thresholds = {
    [](<#cb57-2>)    # Layer 1만, 느슨하게
    [](<#cb57-3>)    'tcr': 60.0,
    [](<#cb57-4>)    'accuracy': 50.0,
    [](<#cb57-5>)    'latency': 20.0,
    [](<#cb57-6>)    'cost_per_task': 2.00
    [](<#cb57-7>)    # Layer 2는 나중에 추가
    [](<#cb57-8>)}
```

* * *

## FAQ & Troubleshooting

### FAQ

#### Q1: 모든 메트릭에 threshold를 설정해야 하나요?

**A** : 아니요. **핵심 메트릭**(TCR, Accuracy)만 설정해도 충분합니다. 점진적으로 추가하세요.

#### Q2: Threshold를 설정했는데 자꾸 실패합니다.

**A** : Threshold가 너무 높을 수 있습니다. **현재 성능을 먼저 확인** 하고, 현재 성능보다 약간 높거나 같은 수준으로 설정하세요.

#### Q3: 개발 환경과 프로덕션 환경의 threshold를 어떻게 다르게 설정하나요?

**A** : 환경 변수(`ENV`)를 사용하여 자동 감지하거나, 별도의 threshold 파일을 사용하세요.

#### Q4: Layer 2 threshold를 설정했는데 평가가 안 됩니다.

**A** : Golden Dataset에 Layer 2 필드(`expected_tools`, `expected_agents`, `expected_workflow_steps`)가 있는지 확인하세요.

#### Q5: CI/CD에서 threshold 실패 시 배포를 강제로 진행할 수 있나요?

**A** : 가능하지만 **권장하지 않습니다**. 긴급 상황에서만 사용하고, 실패 원인을 즉시 해결하세요.

#### Q6: Threshold를 얼마나 자주 업데이트해야 하나요?

**A** : **주간 리뷰** 로 작은 조정, **월간 리뷰** 로 큰 변경을 권장합니다.

#### Q7: Hallucination threshold는 어떻게 설정하나요?

**A** : 프로덕션에서는 **2-5%** 를 권장합니다. 0%는 불가능하므로 현실적인 값을 설정하세요.

### Troubleshooting

#### 문제 1: TCR이 낮습니다 (< 80%)

**원인** :

  * 에이전트가 작업을 자주 실패함
  * Golden Dataset이 너무 어려움
  * 프롬프트가 부적절

**해결** : 1. Dashboard에서 실패한 QAPair 확인 2. 실패 원인 분석 (timeout, error, 잘못된 응답) 3. 프롬프트 개선 또는 Golden Dataset 업데이트

#### 문제 2: Accuracy가 낮습니다 (< 70%)

**원인** :

  * ground_truth가 너무 엄격하거나 부정확
  * 에이전트 응답 품질이 낮음
  * 유사도 계산 방식 문제

**해결** : 1. Dashboard에서 실패한 QAPair의 응답 확인 2. ground_truth가 적절한지 검토 3. 에이전트 프롬프트 개선

#### 문제 3: Tool Selection Accuracy가 낮습니다

**원인** :

  * expected_tools가 부정확
  * 에이전트가 불필요한 도구를 사용
  * 필요한 도구를 누락

**해결** : 1. Dashboard에서 “실제 사용 도구 vs expected_tools” 비교 2. expected_tools 재정의 3. 에이전트 프롬프트에 명시적 도구 선택 지시

#### 문제 4: Agent Coordination Score가 0입니다

**원인** :

  * expected_agents가 정의되지 않음
  * Agent Coordination 추적이 활성화되지 않음

**해결** : 1. Golden Dataset에 expected_agents 추가 2. CrewAI 사용 시 `enable_coordination_tracking=True` 3\. 상호작용이 실제로 발생하는지 확인

#### 문제 5: CI/CD가 자꾸 실패합니다

**원인** :

  * Threshold가 너무 엄격
  * 환경별 threshold가 제대로 설정되지 않음

**해결** : 1. 환경 변수 확인 (`ENV`) 2. Threshold 완화 (일시적) 3. 근본 원인 해결 후 Threshold 복원

#### 문제 6: Latency threshold를 통과하지 못합니다

**원인** :

  * 에이전트가 너무 느림
  * 불필요한 API 호출
  * 긴 프롬프트

**해결** : 1. 프롬프트 간소화 2. 불필요한 도구 사용 제거 3\. 더 빠른 모델 사용 (GPT-4 → GPT-3.5)

* * *

## 다음 단계

Threshold 설정을 완료했다면:

  1. **Golden Dataset 평가 실행** : `Evaluator_Examples/04_threshold_validation_example.py`
  2. **CI/CD 통합** : GitLab CI 또는 Jenkins 설정
  3. **Dashboard 모니터링** : 실시간 threshold 비교 결과 확인
  4. **프로덕션 배포** : [06_DEPLOYMENT_GUIDE.md](<06_DEPLOYMENT_GUIDE.md>) 참고

* * *

* * *

## 📊 품질 관리자 가이드 (QA Manager)

### 🎯 가이드 개요

이 가이드는 **품질 관리자(QA Manager)** 가 **임계값(Threshold)을 전략적으로 설정, 관리, 검증** 하는 방법을 제공합니다. 

**학습 목표:**

  * ✅ 임계값 기반 품질 관리 전략 수립
  * ✅ 개발 단계별 임계값 생명주기 관리
  * ✅ 임계값 변경 시 체계적 프로세스 운영
  * ✅ 임계값 위반 시 신속한 대응 및 조치
  * ✅ 정기 임계값 리뷰 및 최적화

### 11.1 임계값 관리 전략

#### 11.1.1 임계값의 역할 (QA 관점)

역할 | 설명 | QA 활동 | 기대 효과  
---|---|---|---  
🚪 품질 게이트 | 배포 가능 여부 자동 판단 | 배포 전 임계값 검증 실행 | 불량 배포 사전 차단  
🔍 회귀 탐지 | 성능 저하 조기 발견 | 버전 간 메트릭 비교 | 품질 퇴보 방지  
📏 품질 표준 | 팀 전체의 일관된 기준 | 임계값 문서화 및 공유 | 객관적 품질 평가  
📊 추세 분석 | 장기적 품질 변화 추적 | 임계값 위반 이력 분석 | 선제적 품질 개선  
💡 개선 지표 | 최적화 우선순위 결정 | 임계값 미달 메트릭 식별 | 효율적 리소스 배분  
  
#### 11.1.2 전략적 임계값 설정 원칙

**📐 1. SMART 원칙 적용**

원칙 | 의미 | 임계값 적용 예시 | 잘못된 예시  
---|---|---|---  
**S** pecific | 구체적 | TCR > 85% | "성공률 높아야 함"  
**M** easurable | 측정 가능 | Latency < 5초 | "빠르게 응답"  
**A** chievable | 달성 가능 | Accuracy > 80% | Accuracy > 99.9%  
**R** elevant | 관련성 | 비즈니스 요구에 맞춤 | 불필요한 메트릭  
**T** ime-bound | 시한 설정 | Production 단계별 | 무기한 목표  
  
**⚖️ 2. 균형 잡힌 임계값**

불균형 유형 | 문제점 | 올바른 접근  
---|---|---  
❌ 너무 낮음 | 품질 저하 방지 실패 | 최소 허용 기준 설정  
❌ 너무 높음 | 달성 불가능, 배포 차단 | 현실적 목표 설정  
❌ 단일 메트릭 편향 | 전체 품질 간과 | Layer 1+2+3 종합 관리  
❌ 정적 임계값 | 환경 변화 미반영 | 단계별 동적 임계값  
  
**🎯 3. 비즈니스 요구 우선**

시스템 유형 | 최우선 메트릭 | 임계값 예시 | 이유  
---|---|---|---  
🏥 의료 AI | Accuracy, Hallucination | Accuracy > 95%, Hallucination < 1% | 환자 안전 최우선  
💰 금융 AI | Accuracy, Cost | Accuracy > 98%, Cost < $0.10 | 정확성 + 비용 효율  
🛒 E-commerce | Latency, TCR | Latency < 2초, TCR > 90% | 사용자 경험 중요  
📚 교육 AI | Accuracy, Hallucination | Accuracy > 85%, Hallucination < 3% | 올바른 정보 제공  
🎮 엔터테인먼트 | Latency, Cost | Latency < 3초, Cost < $0.30 | 속도 + 비용 관리  
  
#### 11.1.3 임계값 관리 체계 구축

**📂 임계값 파일 관리 구조**
```
    thresholds/
    ├── alpha/
    │   ├── layer1_thresholds.json
    │   ├── layer2_thresholds.json
    │   └── README.md
    ├── beta/
    │   ├── layer1_thresholds.json
    │   ├── layer2_thresholds.json
    │   └── README.md
    ├── production/
    │   ├── layer1_thresholds.json
    │   ├── layer2_thresholds.json
    │   └── README.md
    ├── enterprise/
    │   ├── layer1_thresholds.json
    │   ├── layer2_thresholds.json
    │   └── README.md
    └── CHANGELOG.md  # 임계값 변경 이력
```

**📝 임계값 문서화 필수 항목**

항목 | 내용 | 예시  
---|---|---  
메트릭 이름 | 측정 대상 | Task Completion Rate  
임계값 | min/max 기준 | min: 85.0  
설정 근거 | 왜 이 값인가? | 과거 3개월 평균 87%, 안전 마진 -2%  
측정 방법 | 어떻게 측정? | (성공 작업 / 전체 작업) * 100  
검증 주기 | 얼마나 자주? | 배포 전 매번, 주간 리뷰  
위반 시 조치 | 무엇을 할 것인가? | 배포 차단, 원인 분석 착수  
담당자 | 누가 관리? | QA Lead  
마지막 업데이트 | 언제 변경? | 2024-12-01  
  
### 11.2 임계값 생명주기 관리

#### 11.2.1 생명주기 5단계

단계 | QA 활동 | 산출물 | 승인 필요  
---|---|---|---  
1️⃣ 초기 설정 | 과거 데이터 분석, 산업 표준 조사, 초기 임계값 제안 | 임계값 제안서 | 팀 리뷰  
2️⃣ 검증 | Alpha 환경에서 테스트, 달성 가능성 확인 | 검증 리포트 | QA Lead  
3️⃣ 적용 | Beta → Production 단계적 적용 | 적용 계획서 | Tech Lead  
4️⃣ 모니터링 | 위반 사례 추적, 추세 분석 | 주간 리포트 | -  
5️⃣ 개선 | 임계값 재조정, 새 기준 제안 | 개선 제안서 | 팀 리뷰  
  
#### 11.2.2 1️⃣ 초기 설정 프로세스

**Step 1: 과거 데이터 분석**
```python
    # 과거 평가 데이터에서 통계 계산
    import json
    import numpy as np
    
    def analyze_historical_data(evaluation_files):
        """과거 평가 데이터에서 임계값 제안"""
        all_metrics = []
    
        for file_path in evaluation_files:
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_metrics.append(data['metrics'])
    
        # 각 메트릭의 통계 계산
        tcr_values = [m.get('task_completion_rate', 0) for m in all_metrics]
        accuracy_values = [m.get('accuracy', 0) for m in all_metrics]
    
        # 평균, 표준편차, 최소/최대
        tcr_mean = np.mean(tcr_values)
        tcr_std = np.std(tcr_values)
        tcr_min = np.min(tcr_values)
    
        # 권장 임계값: 평균 - 1 표준편차 (하위 16% 제외)
        recommended_tcr = max(tcr_mean - tcr_std, tcr_min * 1.05)
    
        print(f"📊 TCR 분석:")
        print(f"   평균: {tcr_mean:.1f}%")
        print(f"   표준편차: {tcr_std:.1f}%")
        print(f"   권장 임계값: {recommended_tcr:.1f}%")
    
        return {
            "task_completion_rate": {"min": recommended_tcr}
        }
    
    # 예시 실행
    files = ["evaluation_results/eval_v1.json", "evaluation_results/eval_v2.json"]
    suggested_thresholds = analyze_historical_data(files)
```

**Step 2: 산업 표준 참고**

산업 | TCR 표준 | Accuracy 표준 | Hallucination 표준  
---|---|---|---  
Healthcare | > 95% | > 95% | < 1%  
Finance | > 98% | > 98% | < 0.5%  
E-commerce | > 90% | > 85% | < 3%  
General SaaS | > 85% | > 80% | < 5%  
  
**Step 3: 임계값 제안서 작성**
```python
    # 임계값 제안서
    
    ## 제안 일자
    2024-12-02
    
    ## 제안자
    QA Manager
    
    ## 제안 배경
    - 과거 3개월 평가 데이터 분석 결과
    - TCR 평균 87.5%, 표준편차 3.2%
    - 하위 16% 제외 시 84.3% 이상 달성 가능
    
    ## 제안 임계값 (Production)
    - Task Completion Rate: > 85%
    - Accuracy: > 80%
    - Hallucination Rate: < 5%
    - Latency: < 5초
    - Cost per Task: < $0.20
    
    ## 근거
    - 과거 데이터 기반 달성 가능한 수준
    - 산업 표준 (General SaaS) 부합
    - 비즈니스 요구사항 충족
    
    ## 단계별 적용 계획
    1. Alpha (2주): 초기 검증
    2. Beta (1개월): 안정성 확인
    3. Production: 정식 적용
    
    ## 승인 요청
    Tech Lead, Product Manager 검토 요청
```

#### 11.2.3 2️⃣ 검증 프로세스

**Alpha 환경 검증 체크리스트**

검증 항목 | 방법 | 합격 기준 | 결과  
---|---|---|---  
달성 가능성 | 100회 평가 실행 | 80% 이상 통과 | [ ]  
오탐 (False Positive) | 정상 작업 100회 테스트 | 95% 이상 Pass | [ ]  
미탐 (False Negative) | 불량 작업 50회 테스트 | 90% 이상 Fail | [ ]  
일관성 | 동일 작업 10회 반복 | 동일 결과 90% 이상 | [ ]  
실행 시간 | 임계값 검증 시간 측정 | < 10초 | [ ]  
  
**💡 검증 Tip:**

  * ✅ **충분한 샘플** : 최소 100회 이상 평가로 통계적 유의성 확보
  * ✅ **다양한 시나리오** : 모든 작업 유형에서 테스트
  * ✅ **엣지 케이스** : 경계값 (임계값 ±5%) 집중 테스트

#### 11.2.4 3️⃣ 적용 프로세스 (단계적 롤아웃)

단계 | 기간 | 범위 | 모니터링 | 롤백 조건  
---|---|---|---|---  
Alpha | 2주 | QA 팀만 | 매일 확인 | 달성률 < 50%  
Beta | 1개월 | 개발팀 10% | 주 2회 확인 | 달성률 < 70%  
Production | 무기한 | 전체 | 주 1회 확인 | 달성률 < 80%  
  
### 11.3 임계값 변경 관리

#### 11.3.1 변경이 필요한 시점

변경 트리거 | 증상 | 변경 방향 | 예시  
---|---|---|---  
🔴 달성 불가능 | 지속적으로 임계값 미달 (< 50%) | 완화 (낮춤) | TCR 85% → 80%  
🟢 너무 쉬움 | 항상 임계값 초과 (> 95%) | 강화 (높임) | TCR 85% → 90%  
🔄 시스템 변경 | 새 모델, 프레임워크 도입 | 재평가 | 전체 임계값 재설정  
📈 비즈니스 요구 | 더 높은 품질 요구 | 강화 | Accuracy 80% → 85%  
💰 비용 압박 | 예산 초과 | 비용 임계값 완화 | Cost < $0.20 → < $0.25  
  
#### 11.3.2 변경 프로세스 (Change Management)

**Step 1: 변경 요청서 (CR - Change Request)**
```python
    # 임계값 변경 요청서 (CR-2024-042)
    
    ## 요청 일자
    2024-12-02
    
    ## 요청자
    QA Manager
    
    ## 변경 대상 임계값
    - **현재**: Task Completion Rate > 85%
    - **변경**: Task Completion Rate > 80%
    
    ## 변경 사유
    - 지난 4주간 달성률 평균 48% (매우 낮음)
    - 신규 모델 도입 후 성능 일시적 하락
    - 개선 중이나 현 임계값 달성 불가
    
    ## 영향 분석
    - **긍정**: 배포 차단 해소, 개발 속도 회복
    - **부정**: 품질 기준 완화, 사용자 경험 저하 우려
    - **위험도**: 중간 (6개월 후 85%로 복구 계획)
    
    ## 대안 검토
    1. 임계값 유지: 배포 계속 차단 (❌ 비현실적)
    2. 일시적 면제: 임계값 우회 (❌ 표준 붕괴)
    3. 단계적 완화: 80% → 82% → 85% (✅ 선택)
    
    ## 승인 필요
    Tech Lead, Product Manager
    
    ## 롤백 계획
    - 조건: 3개월 내 80% 미달 시
    - 조치: 원래 임계값(85%) 복구
```

**Step 2: 영향 분석 (Impact Analysis)**

영향 범위 | 변경 전 | 변경 후 | 차이  
---|---|---|---  
배포 차단 횟수 | 주 5회 | 주 1회 (예상) | -80%  
통과율 | 48% | 85% (예상) | +37%  
실제 TCR 평균 | 82.3% | 82.3% (불변) | 0%  
품질 위험 | 낮음 | 중간 | 증가  
  
**Step 3: 승인 및 적용**
```python
    # 1. 변경 요청서 작성
    vi thresholds/change_requests/CR-2024-042.md
    
    # 2. 승인 요청 (Slack, Email 등)
    # → Tech Lead, Product Manager 리뷰
    
    # 3. 승인 후 Git 커밋
    git checkout -b threshold-change-cr-042
    vi thresholds/production/layer1_thresholds.json
    # task_completion_rate: {"min": 85.0} → {"min": 80.0}
    
    # 4. CHANGELOG 업데이트
    vi thresholds/CHANGELOG.md
    # ## 2024-12-02: CR-042
    # - TCR 임계값 85% → 80% (일시적 완화)
    # - 6개월 후 85%로 복구 예정
    
    # 5. PR 생성 및 머지
    git commit -m "임계값 변경: TCR 85→80% (CR-042)"
    git push origin threshold-change-cr-042
    # → PR 생성 → 승인 → 머지
```

**Step 4: 변경 공지**
```python
    # 📢 임계값 변경 공지
    
    ## 변경 일시
    2024-12-02 15:00 KST
    
    ## 변경 내용
    Task Completion Rate 임계값: **85% → 80%**
    
    ## 이유
    신규 모델 도입에 따른 일시적 성능 조정
    
    ## 영향
    - 배포 차단 빈도 감소
    - 6개월 후 85%로 복구 예정
    
    ## 담당자
    QA Manager (qa-team@company.com)
    
    ## 질문/문의
    Slack #qa-channel
```

#### 11.3.3 변경 이력 관리

**CHANGELOG.md 예시**
```python
    # Threshold Configuration Changelog
    
    ## 2024-12-02 (CR-042)
    ### Changed
    - **Task Completion Rate**: 85% → 80% (Production)
    - **사유**: 신규 모델 도입에 따른 일시적 완화
    - **복구 계획**: 2025-06-01까지 85% 복구
    - **승인자**: Tech Lead, Product Manager
    
    ## 2024-11-15 (CR-038)
    ### Changed
    - **Latency**: < 5초 → < 4초 (Production)
    - **사유**: 비즈니스 요구 (사용자 경험 개선)
    - **영향**: 배포 차단 예상 +20%
    - **승인자**: Product Manager
    
    ## 2024-10-20 (CR-031)
    ### Added
    - **Tool Selection Accuracy**: > 85% (Layer 2 신규 추가)
    - **사유**: 멀티 에이전트 시스템 도입
    - **승인자**: Tech Lead
```

### 11.4 임계값 위반 대응

#### 11.4.1 위반 심각도 분류

심각도 | 조건 | 대응 시간 | 담당자 | 조치  
---|---|---|---|---  
🔴 P0 (Critical) | TCR < 75% OR Hallucination > 10% | 즉시 (1시간 내) | QA Lead + Tech Lead | 배포 차단, 긴급 회의  
🟠 P1 (High) | Accuracy < 70% OR Latency > 10초 | 24시간 내 | QA Manager | 원인 분석, 개선 계획  
🟡 P2 (Medium) | Cost > $0.30 OR Tokens > 15K | 1주일 내 | QA Engineer | 최적화 티켓 생성  
🟢 P3 (Low) | Layer 2 메트릭 경미한 위반 | 다음 스프린트 | 개발팀 | 백로그 추가  
  
#### 11.4.2 위반 대응 프로세스

**🔴 P0 (Critical) 대응 플레이북**

단계 | 시간 | 조치 | 담당  
---|---|---|---  
1\. 탐지 | T+0 | CI/CD 자동 알림 → Slack 긴급 채널 | 자동  
2\. 차단 | T+5분 | 배포 파이프라인 차단, 롤백 준비 | QA Lead  
3\. 분석 | T+30분 | 로그 분석, 실패 샘플 검토, 원인 가설 | QA + Dev  
4\. 회의 | T+1시간 | 긴급 전화 회의 (QA Lead, Tech Lead, PM) | 전체  
5\. 조치 | T+2시간 | 핫픽스 OR 롤백 OR 임계값 임시 면제 | Dev  
6\. 검증 | T+3시간 | 재평가 실행, 임계값 통과 확인 | QA  
7\. 사후 | T+1일 | 근본 원인 분석(RCA), 재발 방지 계획 | QA Lead  
  
**위반 보고서 템플릿**
```python
    # 임계값 위반 보고서 (P0-2024-042)
    
    ## 발생 일시
    2024-12-02 14:35 KST
    
    ## 위반 내용
    - **메트릭**: Task Completion Rate
    - **임계값**: > 85%
    - **실제 값**: 62.5%
    - **위반 폭**: -22.5% (심각)
    
    ## 영향 범위
    - 배포 차단: Release v2.5.3
    - 영향 받은 작업: Code Generation (15/30 실패)
    
    ## 원인 분석
    1. **즉시 원인**: 신규 프롬프트 템플릿 버그
    2. **근본 원인**: 프롬프트 변경 시 사전 테스트 부재
    3. **기여 요인**: Golden Dataset 오래됨 (3개월 전)
    
    ## 조치 내역
    | 시간 | 조치 | 담당자 |
    |------|------|--------|
    | 14:35 | 위반 탐지 (자동) | CI/CD |
    | 14:40 | 배포 차단 | QA Lead |
    | 15:00 | 긴급 회의 | 전체 |
    | 15:30 | 프롬프트 롤백 | Dev |
    | 16:00 | 재평가 → 87.2% (통과) | QA |
    
    ## 재발 방지 계획
    1. 프롬프트 변경 시 필수 사전 평가 프로세스 도입
    2. Golden Dataset 월간 업데이트 정책 수립
    3. 프롬프트 버전 관리 강화
    
    ## 다음 단계
    - [ ] RCA 문서 작성 (기한: 12/03)
    - [ ] 프로세스 개선안 제안 (기한: 12/05)
    - [ ] 팀 회고 미팅 (일정: 12/04 10:00)
```

#### 11.4.3 위반 추세 분석

**월간 위반 이력 테이블**

날짜 | 메트릭 | 임계값 | 실제 | 심각도 | 조치 | 상태  
---|---|---|---|---|---|---  
12/02 | TCR | > 85% | 62.5% | P0 | 롤백 | ✅ 해결  
11/28 | Latency | < 5초 | 6.2초 | P2 | 최적화 | ✅ 해결  
11/25 | Cost | < $0.20 | $0.28 | P2 | 프롬프트 단축 | 🔄 진행중  
11/20 | Tool Selection | > 85% | 78% | P1 | 도구 정의 개선 | ✅ 해결  
  
**위반 패턴 분석**
```python
    # 위반 이력에서 패턴 추출
    import pandas as pd
    
    violations = pd.read_csv("threshold_violations.csv")
    
    # 1. 가장 많이 위반된 메트릭
    top_violated = violations['metric'].value_counts().head(5)
    print("🔴 위반 빈도 TOP 5:")
    print(top_violated)
    # TCR: 8회
    # Latency: 5회
    # Cost: 4회
    
    # 2. 위반 추세 (증가/감소)
    monthly_violations = violations.groupby('month').size()
    print("
    📈 월별 위반 횟수:")
    print(monthly_violations)
    # 증가 추세 → 임계값 재검토 필요
    
    # 3. 재발 위반 (동일 메트릭 반복)
    repeat_violations = violations[violations.duplicated(subset=['metric'], keep=False)]
    print(f"
    🔄 재발 위반: {len(repeat_violations)}건")
    # → 근본 원인 미해결
```

### 11.5 정기 임계값 리뷰

#### 11.5.1 리뷰 주기 및 범위

주기 | 참여자 | 검토 항목 | 산출물  
---|---|---|---  
📅 주간 | QA Engineer | 위반 사례, 달성률 | 주간 리포트  
📅 월간 | QA Manager, QA Lead | 위반 추세, 임계값 적정성 | 월간 리뷰 미팅  
📅 분기 | QA + Tech Lead + PM | 전체 임계값 재평가 | 분기 개선 계획  
📅 반기 | 전사 (QA, Dev, Product) | 전략적 방향 설정 | 반기 품질 전략  
  
#### 11.5.2 월간 리뷰 체크리스트

검토 항목 | 확인 사항 | 조치 기준 | 결과  
---|---|---|---  
1\. 달성률 | 각 임계값 통과율 | < 80% 시 완화 검토 | [ ]  
2\. 위반 빈도 | 월간 위반 횟수 | > 10회 시 원인 분석 | [ ]  
3\. 위반 추세 | 전월 대비 증가/감소 | +50% 증가 시 긴급 대응 | [ ]  
4\. 재발 위반 | 동일 메트릭 반복 위반 | > 3회 시 근본 원인 조사 | [ ]  
5\. 배포 차단 | 임계값으로 인한 차단 횟수 | > 5회 시 프로세스 개선 | [ ]  
6\. 비즈니스 정렬 | 비즈니스 요구와 일치 여부 | 불일치 시 조정 | [ ]  
  
#### 11.5.3 분기 리뷰 프로세스

**Step 1: 데이터 수집 (리뷰 2주 전)**
```python
    # 1. 분기 평가 데이터 통합
    python utils/merge_quarterly_results.py --quarter Q4-2024
    
    # 2. 위반 이력 추출
    python utils/extract_violations.py --start 2024-10-01 --end 2024-12-31
    
    # 3. 리포트 생성
    python utils/generate_threshold_review_report.py --quarter Q4-2024
    # → threshold_review_Q4_2024.pdf
```

**Step 2: 분석 (리뷰 1주 전)**

분석 영역 | 질문 | 판단 기준  
---|---|---  
적정성 | 임계값이 너무 높거나 낮은가? | 달성률 80-95% = 적정  
관련성 | 비즈니스 목표와 정렬되는가? | Product Manager 피드백  
일관성 | 메트릭 간 균형이 맞는가? | Layer 1/2/3 종합 검토  
효과성 | 품질 게이트로서 효과적인가? | 불량 배포 차단 성공률  
  
**Step 3: 리뷰 미팅 (분기 마지막 주)**
```python
    # 분기 임계값 리뷰 미팅 안건
    
    ## 날짜/시간
    2024-12-20 14:00-16:00
    
    ## 참석자
    - QA Manager (주관)
    - QA Lead
    - Tech Lead
    - Product Manager
    
    ## 안건
    1. Q4 임계값 달성 현황 (15분)
    2. 위반 이력 및 추세 분석 (20분)
    3. 문제점 및 개선 아이디어 (30분)
    4. 2025 Q1 임계값 제안 (30분)
    5. 액션 아이템 정리 (15분)
    
    ## 의사결정 필요
    - [ ] TCR 임계값 조정 여부
    - [ ] 신규 Layer 2 메트릭 추가
    - [ ] CI/CD 통합 개선
    
    ## 산출물
    - 분기 리뷰 요약 문서
    - 2025 Q1 임계값 설정안
    - 개선 액션 아이템 (담당자, 마감일)
```

**Step 4: 액션 아이템 (리뷰 직후)**

액션 | 담당자 | 마감일 | 상태  
---|---|---|---  
TCR 임계값 85% → 87% 변경 (CR 생성) | QA Manager | 01/05 | 🔄 진행중  
Communication Overhead 신규 임계값 추가 | QA Lead | 01/10 | 📝 계획  
Golden Dataset 업데이트 (200 → 300 샘플) | QA Engineer | 01/15 | 📝 계획  
CI/CD 위반 알림 Slack 통합 | DevOps | 01/20 | 📝 계획  
  
#### 11.5.4 리뷰 결과 문서화

**분기 리뷰 요약 문서 템플릿**
```python
    # Q4 2024 임계값 리뷰 요약
    
    ## 개요
    - **기간**: 2024-10-01 ~ 2024-12-31
    - **리뷰 일자**: 2024-12-20
    - **참석자**: QA Manager, QA Lead, Tech Lead, Product Manager
    
    ## 주요 지표
    
    ### 달성률
    | 메트릭 | 임계값 | 평균 달성률 | 판정 |
    |--------|--------|-------------|------|
    | TCR | > 85% | 89.2% | ✅ 적정 |
    | Accuracy | > 80% | 82.5% | ✅ 적정 |
    | Latency | < 5초 | 4.1초 | ✅ 적정 |
    | Cost | < $0.20 | $0.18 | ✅ 적정 |
    
    ### 위반 현황
    - **총 위반**: 12건
    - **P0**: 2건
    - **P1**: 4건
    - **P2**: 6건
    - **전분기 대비**: -3건 (개선)
    
    ## 주요 이슈
    1. **TCR 2회 P0 위반**: 프롬프트 변경 사전 테스트 부재
    2. **Cost 지속 증가**: 평균 $0.15 → $0.18 (주의 필요)
    
    ## 결정 사항
    1. ✅ **TCR 임계값 강화**: 85% → 87% (2025 Q1)
    2. ✅ **Cost 모니터링 강화**: 주간 리포트에 추가
    3. ✅ **프롬프트 변경 프로세스**: 사전 평가 필수화
    
    ## 액션 아이템
    (위 표 참조)
    
    ## 다음 리뷰
    2025-03-20 (Q1 2025 리뷰)
```

**✅ QA 관리자 핵심 원칙 (임계값 관리)**

  1. **데이터 기반 설정** : 과거 데이터 + 산업 표준 + 비즈니스 요구 종합
  2. **단계적 적용** : Alpha → Beta → Production 점진적 롤아웃
  3. **지속적 모니터링** : 주간/월간/분기 정기 리뷰
  4. **투명한 변경 관리** : CR → 영향 분석 → 승인 → 공지 프로세스
  5. **신속한 위반 대응** : P0 1시간, P1 24시간, P2 1주일 내
  6. **추세 중심 분석** : 단일 위반보다 패턴 파악
  7. **팀 간 협업** : QA + Dev + Product 긴밀한 소통

**⚠️ 주의사항**

  * ❌ **무분별한 완화 금지** : 달성 어렵다고 계속 낮추면 품질 표준 붕괴
  * ❌ **과도한 강화 금지** : 달성 불가능한 임계값은 무의미
  * ❌ **변경 이력 미기록 금지** : 모든 변경은 CHANGELOG에 기록
  * ❌ **단일 승인자 금지** : 최소 2명 이상 검토/승인 필수

* * *

## 참고 문서

  * [04_GOLDEN_DATASET_GUIDE.md](<04_GOLDEN_DATASET_GUIDE.md>) \- Golden Dataset 작성 가이드
  * [02_METRICS_REFERENCE.md](<02_METRICS_REFERENCE.md>) \- Layer 2 메트릭 가이드
  * [API.md](<API.md>) \- 전체 API 레퍼런스
  * [04_threshold_validation_example.py](<../Evaluator_Examples/04_threshold_validation_example.py>) \- 실전 예제

* * *

* * *

**최종 업데이트** : 2026-03-27
**버전** : Agent Evaluator v0.7.0
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System
**문서** : Threshold Configuration Guide
