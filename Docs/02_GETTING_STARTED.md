# 🚀 빠른 시작 가이드

설치부터 실행까지 Agent Evaluator 시작하기

# Agent Evaluator 시작 가이드

Agent Evaluator의 설치부터 실제 사용까지 모든 과정을 안내합니다.

## 목차

  1. [시스템 요구사항](<#시스템-요구사항>)
  2. [설치](<#설치>)
  3. [설치 확인](<#설치-확인>)
  4. [빠른 시작](<#빠른-시작>)
  5. [데이터 편집 기능](<#데이터-편집-기능>)
  6. [Test 투명성 기능](<#test-투명성-기능>)
  7. [터미널 출력 방법](<#터미널-출력-방법>)
  8. [사용 예제](<#사용-예제>)
  9. [문제 해결](<#문제-해결>)

* * *

## 시스템 요구사항

  * **Python** : 3.11 이상 권장 (3.8+ 지원)
  * **운영체제** : Windows, macOS, Linux
  * **메모리** : 최소 4GB RAM 권장
  * **디스크** : 최소 500MB 여유 공간

* * *

## 설치

Agent Evaluator는 PyPI에 배포되어 있어 pip로 간단히 설치할 수 있습니다:

### 옵션 1: 기본 설치 (권장) ⭐

**대부분의 사용자에게 권장합니다.**

```bash
# 1. Conda 가상환경 생성 (권장)
    conda create --name Evaluator python=3.11
    conda activate Evaluator
    
    # 2. Agent Evaluator 설치
    pip install agent-evaluator
```

**포함 기능:**

  * ✅ FastAPI 대시보드 (`agent-eval serve`, Port 8765, 브라우저 자동 오픈)
  * ✅ Layer 1: Foundation 메트릭 (TCR, Accuracy, Latency, Token Usage)
  * ✅ Layer 2: Agentic + Security 메트릭 (Tool Selection, Agent Coordination, Workflow, Input Sanitization, Output Leakage, Authorization, Privilege Escalation, Attack Detection)
  * ✅ **LangChain 통합** (자동 추적)
  * ✅ **AutoGen 통합** (자동 추적)
  * ✅ 한국어 RAG Dataset Generator
  * ✅ Golden Dataset 자동 평가
  * ✅ Threshold 비교 & Quality Gate

**제외 기능:**

  * ❌ CrewAI 통합 (별도 설치 필요)
  * ❌ LangGraph 통합 (별도 설치 필요)
  * ❌ DeepEval (Layer 3 고급 메트릭)
  * ❌ Ragas (Layer 3 RAG 평가)

### 옵션 2: 최소 설치

**대시보드 없이 코어 기능만 필요한 경우:**

```bash
# 코어 기능만 설치
    pip install agent-evaluator --no-deps
    pip install numpy pandas
```

**포함 기능:**

  * ✅ Layer 1 메트릭
  * ✅ 기본 평가 기능

**제외 기능:**

  * ❌ FastAPI 대시보드 (별도 `[serve]` extra 필요)
  * ❌ 프레임워크 통합
  * ❌ Layer 2, 3 메트릭

**사용 사례:**

  * 기본 메트릭만 사용
  * 가벼운 환경이 필요한 경우
  * 프레임워크 통합 없이 직접 TaskResult 생성

### 옵션 3: 전체 설치

**모든 기능이 필요한 경우:**

```bash
# 기본 패키지 설치
    pip install agent-evaluator
    
    # 추가 프레임워크 설치
    pip install crewai>=1.0.0
    pip install langgraph>=1.0.0
    pip install deepeval>=0.20.0
    pip install ragas>=0.4.0 "datasets>=4.0.0,<6.0.0" langchain-openai>=1.0.0
```

**포함 기능:**

  * ✅ 기본 설치의 모든 기능 (Layer 1 Foundation + Layer 2 Agentic + Security)
  * ✅ **CrewAI 통합** (Agent Coordination 자동 추적)
  * ✅ **LangGraph 통합** (Workflow Execution 자동 추적)
  * ✅ **DeepEval** (Layer 3: G-Eval, Hallucination, Toxicity, Bias)
  * ✅ **Ragas** (Layer 3: Faithfulness, Context Precision/Recall)
  * ✅ **완전 보안 모니터링** (Layer 2 Security 통합)

**사용 사례:**

  * 모든 프레임워크 사용
  * Layer 3 고급 메트릭 필요
  * 프로덕션 환경 모니터링

### 프레임워크별 추가 설치

표준 설치 후 필요한 프레임워크만 추가로 설치할 수 있습니다:

#### CrewAI 추가

```bash
    pip install crewai>=1.0.0
```

#### LangGraph 추가

```bash
    pip install langgraph>=1.0.0
```

#### DeepEval 추가

```bash 
    pip install deepeval>=0.20.0
```

#### Ragas 추가

```bash
    pip install ragas>=0.4.0 "datasets>=4.0.0,<6.0.0" langchain-openai>=1.0.0
```

* * *

## 설치 확인

### 1\. 환경 변수 설정 (선택사항)

Layer 3 고급 메트릭을 사용하는 경우 OpenAI API 키가 필요합니다:

```bash 
    # 터미널에서 직접 설정
    export OPENAI_API_KEY='your-api-key-here'
    
    # 또는 .env 파일에 설정
    echo "OPENAI_API_KEY=your-api-key-here" > .env
```

**참고:** Layer 1, 2 메트릭은 API 키 없이 사용 가능합니다.

### 2\. 설치 확인 테스트

```bash
# Python에서 확인
    python -c "from agent_evaluator import PerformanceMonitor; print('✅ Agent Evaluator 설치 완료')"
```

* * *

## 빠른 시작

#### 💡 Zero Configuration

Agent Evaluator는 **별도 설정 없이 자동으로 올바른 위치에 데이터를 저장** 합니다. `Dashboard/data/evaluation_results/` 경로가 자동으로 감지되고 생성됩니다. 자세한 내용은 [Zero Configuration 가이드](<ZERO_CONFIGURATION_GUIDE.html>)를 참조하세요.

### 기본 사용법

Agent Evaluator를 설치한 후, Python 코드에서 직접 사용할 수 있습니다:

```python
from agent_evaluator import PerformanceMonitor
from agent_evaluator import create_taskresult

# 모니터 생성 (설정 불필요!)
monitor = PerformanceMonitor()

# 간편한 작업 결과 생성 (Helper 함수 사용)
task = create_taskresult(
    task_id="task_001",
    question="대한민국의 수도는 어디인가요?",
    response="서울입니다",
    ground_truth="서울",
    execution_time=1.2
)
monitor.record_task(task)

# 자동 저장 (Dashboard/data/evaluation_results/my_eval.json)
monitor.save_to_file("my_eval.json")

# 리포트 생성
report = monitor.generate_report()
print(f"TCR: {report.accuracy_metrics.tcr}")
```

**자동 저장 위치:** `{프로젝트_루트}/Dashboard/data/evaluation_results/my_eval.json`  
더 자세한 사용법은 [API 레퍼런스](<API_REFERENCE.html>)를 참조하세요.

* * *

## 데이터 편집 기능

### 1단계: 데이터 편집 탭 접근

대시보드 상단에서 **"📝 데이터 편집"** 탭을 클릭합니다.

⚠️ **중요** : Test 결과 데이터(TaskResult)는 평가의 신뢰성을 위해 편집이 제한됩니다.

### 2단계: Golden Dataset 생성 (PDF에서)

**“📄 PDF에서 생성” 탭 선택**

  1. **PDF 파일 업로드**
     * 고객사의 PDF 문서 업로드 (정책, 매뉴얼, 기술 문서 등)
     * 파일명과 크기 확인
  2. **생성 옵션 설정**
     * **OpenAI API Key** : QA 생성용 API 키 입력
     * **청크당 질문 수** : 1-5개 (기본값: 2개)
     * **청크 크기** : 500-3000 문자 (기본값: 1000자)
     * **Dataset ID** : 자동 생성 (수정 가능)
  3. **QA 쌍 자동 생성**
     * **“🚀 QA 쌍 생성 시작”** 버튼 클릭
     * AI가 자동으로 문서 분석 및 QA 생성
     * 진행 상황 표시
  4. **생성 결과 확인**
     * 생성된 QA 쌍 수 확인
     * 미리보기에서 품질 검토
     * `golden_datasets/` 디렉토리에 자동 저장

**생성된 QA 데이터 사용처:**

  * 🎯 **Faithfulness** : 답변-컨텍스트 충실도
  * 🎯 **Context Recall** : 컨텍스트-정답 포함 여부
  * 🎯 **Context Precision** : 컨텍스트 정확도
  * 🎯 **Answer Relevancy** : 답변-질문 관련성

### 3단계: Golden Dataset 편집

**“✏️ 기존 데이터셋 편집” 탭 선택**

  1. **데이터셋 선택**
     * 드롭다운에서 편집할 Golden Dataset 선택
     * PDF에서 생성한 파일 또는 샘플 데이터
  2. **QA 쌍 편집** (각 필드에 사용 메트릭 표시됨) 
     * `question`: 질문 (Faithfulness, Answer Relevancy에 사용)
     * `answer`: 답변 (Faithfulness에 사용)
     * `ground_truth`: 정답 (Context Recall에 사용)
     * `context`: 컨텍스트 (Context Precision, Faithfulness에 사용)
  3. **품질 검토**
     * 질문이 명확한지 확인
     * 답변이 정확한지 검증
     * Ground Truth가 올바른지 확인
     * 컨텍스트가 충분한지 검토
  4. **저장**
     * 편집자 이름 입력
     * 편집 이유 입력
     * **“💾 저장”** 버튼 클릭
  5. **상세 보기**
     * QA 쌍 선택하여 전체 내용 확인
     * 사용되는 메트릭 정보 확인

### 4단계: 임계값 설정

  1. **임계값 설정 탭 선택**

  2. **기본 메트릭 설정** (TaskResult 데이터 사용)

     * TCR: 작업 완료율 최소 목표
     * Accuracy: 정확도 최소 목표
     * Hallucination: 환각 발생률 최대 허용치
     * Latency: 응답 시간 최대 허용치
     * Cost: 작업당 비용 최대 허용치
  3. **RAG 메트릭 설정** (Golden Dataset 사용)

     * Faithfulness: 답변-컨텍스트 충실도 최소값
     * Answer Relevancy: 답변-질문 관련성 최소값
     * Context Recall: 컨텍스트-정답 포함 최소값
     * Context Precision: 컨텍스트 정확도 최소값
  4. **저장**

     * 편집자 이름 입력
     * 변경 사유 입력
     * **“💾 저장”** 버튼 클릭

💡 **각 슬라이더의 help 텍스트에서 데이터 소스를 확인할 수 있습니다**

### 5단계: 버전 관리

  1. **버전 관리 탭 선택**

  2. **버전 목록 확인**

     * 모든 백업 버전이 시간순으로 표시됩니다
     * 각 버전의 설명과 생성 시간 확인
  3. **롤백**

     * 복원할 버전 선택
     * 목표 파일 경로 입력
     * **“⏮️ 복원”** 버튼 클릭

* * *

## Test 투명성 기능

### 1단계: Test 투명성 탭 접근

대시보드 상단에서 **“🔬 Test 투명성”** 탭을 클릭합니다.

### 2단계: 메트릭 계산 추적

  1. **메트릭 계산 추적 탭 선택**

  2. **추적 기록 조회**

     * 모든 메트릭 계산 과정이 표시됩니다
     * 각 단계별 Input/Output 확인
     * 타임라인 그래프로 실행 흐름 파악
  3. **필터링**

     * 메트릭 타입별 필터 (Basic/Advanced)
     * 특정 메트릭 이름으로 검색

### 3단계: 주석 추가

  1. **주석 관리 탭 선택**

  2. **새 주석 작성**

     * **대상 선택** : Task, Metric, Dataset 중 선택
     * **대상 ID 입력** : 예) `task_001`, `metric_tcr`
     * **주석 유형 선택** : 
       * 💬 Comment: 일반 의견
       * 🐛 Issue: 문제 보고
       * 💡 Improvement: 개선 제안
       * ✅ Confirmation: 확인 완료
       * ❓ Question: 질문
     * **우선순위** : Low, Normal, High, Critical
     * **제목 및 내용 입력**
     * **작성자 이름 입력**
     * **“➕ 주석 추가”** 버튼 클릭
  3. **기존 주석 관리**

     * 주석 목록에서 확인
     * 답글 추가 가능
     * 상태 변경 (Open → In Progress → Resolved → Closed)

### 4단계: Audit Log 조회

  1. **Audit Log 탭 선택**

  2. **로그 필터링**

     * 이벤트 유형별 필터
     * 사용자별 필터
     * 대상 타입별 필터
  3. **CSV 다운로드**

     * **“📥 CSV 다운로드”** 버튼으로 전체 로그 내보내기

### 5단계: 상세 리포트 생성

  1. **상세 리포트 탭 선택**

  2. **작업 ID 입력**

     * 리포트를 생성할 Task ID 입력
  3. **리포트 확인**

     * 메트릭 계산 과정
     * 관련 주석
     * 타임라인
     * 최종 결과

* * *

## 터미널 출력 방법

### 개요

Agent Evaluator는 평가 결과를 터미널에서 즉시 확인할 수 있는 다양한 출력 메서드를 제공합니다. Dashboard를 실행하지 않고도 빠르게 결과를 분석할 수 있습니다.

### 방법 1: print_summary() - 빠른 요약

핵심 메트릭을 간략하게 출력합니다:

```python
    from agent_evaluator import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    # ... Agent 평가 수행 ...
    
    # 요약 출력
    report = monitor.generate_report()
    monitor.print_summary(report)
```

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
      - TCR: 95.0%
      - 평균 Accuracy: 92.5%
      - Hallucination Rate: 2.3%
    
    ⚡ 효율성 메트릭:
      - 평균 Latency: 1.23초
      - P95 Latency: 2.45초
      - 평균 Token 사용량: 450 tokens
      - 총 비용: $0.23
    
    ========================================
```

### 방법 2: print_detailed_report() - 상세 분석

모든 메트릭과 Layer별 상세 정보를 출력합니다:

```python
    report = monitor.generate_report()
    monitor.print_detailed_report(report)
```

### 방법 3: 커스텀 출력

필요한 메트릭만 선택하여 출력할 수 있습니다:

```python
    report = monitor.generate_report()
    
    print("핵심 메트릭:")
    print(f"TCR: {report.accuracy_metrics['tcr']['tcr']:.1f}%")
    print(f"Latency: {report.efficiency_metrics['latency']['average']:.2f}s")
```

### 방법 4: Quality Gate 출력

임계값 비교 결과를 Pass/Fail 형식으로 출력합니다:

```python
    monitor.thresholds = {
        'tcr': 95.0,
        'accuracy': 90.0,
        'latency': 2.0,
    }
    
    comparison = monitor.compare_with_thresholds()
    
    for metric, result in comparison.items():
        status = "✅ PASS" if result["status"] == "pass" else "❌ FAIL"
        print(f"{status} {metric}: {result['actual']:.2f} (임계값: {result['threshold']:.2f})")
```

**출력 예시:**

```python
    ✅ PASS tcr: 95.00 (임계값: 95.00)
    ✅ PASS accuracy: 92.50 (임계값: 90.00)
    ✅ PASS latency: 1.23 (임계값: 2.00)
```

#### 💡 터미널 출력 활용 팁

  * **개발 중** : `print_summary()`로 빠른 확인
  * **디버깅** : `print_detailed_report()`로 상세 분석
  * **CI/CD** : Quality Gate 출력으로 자동 검증
  * **통합** : JSON 출력으로 다른 시스템과 연동

* * *

## 사용 예제

### 기본 평가 예제

```python
    from agent_evaluator import PerformanceMonitor
    from agent_evaluator import create_taskresult
    
    # 모니터 생성
    monitor = PerformanceMonitor()
    
    # 여러 작업 평가
    questions = ["수도는?", "인구는?", "언어는?", "화폐는?", "면적은?"]
    responses = ["서울", "약 5천만명", "한국어", "원", "약 100,000km²"]
    truths = ["서울", "5천만명", "한국어", "원", "100,378km²"]
    
    for i in range(5):
        task = create_taskresult(
            task_id=f"task_{i:03d}",
            question=questions[i],
            response=responses[i],
            ground_truth=truths[i],
            execution_time=1.5
        )
        monitor.record_task(task)
    
    # 리포트 생성
    report = monitor.generate_report()
    print(f"TCR: {report.accuracy_metrics.tcr}")
    print(f"평균 지연시간: {report.latency_metrics.mean}초")
```

### 프레임워크 통합 예제

**v0.6.0:** 보안 메트릭 및 고급 통합 클래스 지원.

Layer 2 보안 메트릭, Layer 3 고급 평가, 자동 추적 기능이 포함된 통합 클래스를 사용하세요:

#### CrewAI 통합

```python
    from agent_evaluator.integrations.crewai_evaluator import CrewAIEvaluator
    from crewai import Crew, Agent, Task
    
    # Crew 생성
    crew = Crew(agents=[agent], tasks=[task])
    
    # 평가 래퍼 생성 (Layer 2 자동 추적)
    evaluator = CrewAIEvaluator(crew, enable_layer2=True)
    
    # 실행 및 평가
    result = evaluator.kickoff(inputs={"topic": "AI"})
    report = evaluator.generate_report()
```

#### LangChain 통합

```python
    from agent_evaluator.integrations.langchain_evaluator import LangChainEvaluator
    
    # LangChain 에이전트 생성
    agent = initialize_agent(tools, llm)
    
    # 평가 래퍼 생성
    evaluator = LangChainEvaluator(agent, enable_layer2=True)
    
    # 실행 및 평가 (Tool Selection 자동 추적)
    result = evaluator.run("What is AI?", expected_tools=["search"])
    report = evaluator.generate_report()
```

자세한 내용은 [프레임워크 통합 가이드](<FRAMEWORK_INTEGRATION.html>)를 참조하세요.

**⚠️ 참고:** 기존 클래스 (`EvaluatedCrew`, `LangChainEvaluationCallback` 등)는 deprecated되었습니다. 새로운 통합 클래스를 사용하세요.

* * *

## 문제 해결

### 설치 관련

#### ImportError: No module named ‘langchain’

**원인:** LangChain이 설치되지 않음

**해결:**

```bash 
    pip install langchain langchain-core langchain-community
```

#### ImportError: No module named ‘autogen_agentchat’

**원인:** AutoGen이 설치되지 않음

**해결:**

```bash
    pip install autogen-agentchat autogen-core
```

#### 대시보드 실행 오류

**원인:** `serve` extra가 설치되지 않음

**해결:**

```bash
    pip install agent-evaluator[serve]
    agent-eval serve
```

#### 버전 충돌

**원인:** 패키지 버전 충돌

**해결:**

```bash
# 가상환경 재생성
    conda deactivate
    conda remove -n agent_evaluator --all
    conda create -n agent_evaluator python=3.11
    conda activate agent_evaluator
    pip install agent-evaluator
```

더 자세한 문제 해결은 [문서 디렉토리](<docs/>)를 참조하세요.

### 대시보드 사용 관련

#### 데이터 파일이 없다고 나옵니다

**해결 방법:** 1\. 데이터 편집 탭에서 **“🎲 데모 데이터 생성”** 버튼 클릭 2. 또는 예제를 실행하여 평가 결과 생성

#### Golden Dataset 파일이 없습니다

**해결 방법:** 1\. `golden_datasets/sample_dataset.json` 파일이 자동 생성되어 있습니다 2. 추가 데이터셋은 대시보드의 “PDF에서 생성” 기능 사용 3. 또는 `korean_rag_dataset_generator.py`로 PDF에서 자동 생성

#### Golden Dataset 구조 오류가 발생합니다

**올바른 JSON 구조:**

```json
{
  "dataset_id": "your_dataset_id",
      "source_document": "문서명",
      "created_at": "2025-11-30T12:00:00.000000",
      "total_qa_pairs": 1,
      "metadata": {},
      "qa_pairs": [
        {
          "qa_id": "qa_001",
          "question": "질문?",
          "answer": "답변",
          "context": "컨텍스트 (문자열, 단수형)",
          "ground_truth": "정답",
          "metadata": {}
        }
      ]
    }
```

**주의사항:** \- `context` (단수형) 사용 - `contexts` (복수형) ❌ - `ground_truth` 필드 필수 \- 최상위에 `dataset_id`, `source_document` 등 위치

#### 편집이 저장되지 않습니다

**체크리스트:** \- [ ] 편집자 이름을 입력했나요? - [ ] 편집 사유를 입력했나요? - [ ] 저장 버튼을 클릭했나요? - [ ] 파일 권한이 있나요? (`ls -la evaluation_results/`)

#### 추적 데이터가 보이지 않습니다

**원인:** Test 투명성 기능은 새로 실행된 평가부터 추적됩니다.

**해결 방법:** 1\. `transparency_manager.py`를 평가 코드에 통합 2. 메트릭 계산 시 `start_metric_calculation()` 호출 3. 각 단계마다 `add_calculation_step()` 호출

### OpenAI API 관련

#### openai.error.AuthenticationError

**원인:** API 키가 설정되지 않음 또는 잘못됨

**해결:** 1\. `.env` 파일에 올바른 API 키 설정 2\. 환경 변수로 직접 설정: `export OPENAI_API_KEY='your-key'` 3\. Layer 3 메트릭을 사용하지 않는 경우 무시 가능

* * *

## 유용한 팁

### 데이터 편집 시 주의사항

  1. **항상 편집 사유를 명확히 기록하세요**
     * 좋은 예: “TCR 기준값을 85%로 상향 조정 (팀 목표 변경)”
     * 나쁜 예: “수정”, “변경”
  2. **중요한 편집 전에는 버전 확인**
     * 버전 관리 탭에서 현재 백업 확인
     * 필요시 수동 백업 생성
  3. **편집 후 검증**
     * “개요” 탭에서 변경사항이 메트릭에 반영되었는지 확인

### Test 투명성 활용

  1. **이상 징후 발견 시**
     * 즉시 Issue 타입 주석 추가
     * 우선순위를 적절히 설정
     * 관련 팀원을 멘션
  2. **개선 아이디어 문서화**
     * Improvement 타입 주석으로 제안 기록
     * 구체적인 개선 방안 작성
  3. **정기적인 리뷰**
     * Audit Log를 주기적으로 검토
     * 패턴 분석 및 프로세스 개선

* * *

## 주요 파일 위치

```
프로젝트 구조 예시:
    
    YourProject/                     # 사용자 프로젝트 루트
    ├── .git/                        # Git 저장소 (선택사항)
    ├── Dashboard/                   # 데이터 저장소 (Zero Configuration)
    │   └── data/
    │       ├── evaluation_results/  # 평가 결과 저장소
    │       │   └── *.json           # 평가 데이터 파일
    │       └── golden_datasets/     # Golden Dataset 저장소
    │           └── *.json
    │
    ├── src/                         # 사용자 코드
    │   └── my_agent.py
    └── requirements.txt

    참고: agent_evaluator는 pip로 설치하여 사용합니다.
          대시보드는 pip install agent-evaluator[serve] 후 agent-eval serve 로 실행합니다.
```

* * *

## 다음 단계

설치가 완료되면:

  1. **[README.html](<README.html>)** \- 프로젝트 전체 개요
  2. **[API_REFERENCE.html](<API_REFERENCE.html>)** \- API 레퍼런스
  3. **[LEARNING_GUIDE.html](<LEARNING_GUIDE.html>)** \- 학습 가이드
  4. **[ZERO_CONFIGURATION_GUIDE.html](<ZERO_CONFIGURATION_GUIDE.html>)** \- Zero Configuration 상세 가이드
  5. **[DEPLOYMENT_GUIDE.html](<DEPLOYMENT_GUIDE.html>)** \- 배포 가이드

* * *

**문서 버전** : v0.6.1
**최종 업데이트** : 2026-03-23
