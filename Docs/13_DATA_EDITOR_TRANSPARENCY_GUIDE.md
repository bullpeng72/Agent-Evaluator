# 📝 데이터 편집 & 투명성 가이드

테스트 데이터 관리 및 투명성 보장 (Agent Evaluator v0.5.2)

# 데이터 편집 & Test 투명성 가이드

> Dashboard를 통한 데이터 편집 및 Test 과정 투명화 완벽 가이드

## 목차

  1. [개요](<#개요>)
  2. [데이터 편집 기능](<#데이터-편집-기능>)
  3. [Test 투명성 기능](<#test-투명성-기능>)
  4. [UX 설계](<#ux-설계>)
  5. [사용 방법](<#사용-방법>)
  6. [고급 활용](<#고급-활용>)

* * *

## 개요

### 제안 배경

기존 Agent Evaluator는 평가 데이터를 파일로만 관리하고, Test 과정이 블랙박스처럼 보이는 문제가 있었습니다. 이를 해결하기 위해 두 가지 핵심 기능을 추가했습니다:

  1. **Dashboard 데이터 편집** : 평가 데이터를 UI에서 직접 확인하고 편집
  2. **Test 투명성** : 각 메트릭의 계산 과정을 단계별로 추적하고, 결과에 의견 추가

### 주요 기능

#### (1) 데이터 편집 기능

**5개 서브탭 구성 (Test 관리자 워크플로우 최적화)** : 1. ⚙️ **임계값 설정** (1순위) - 3계층 지표 체계 2. 📄 **Golden Dataset 편집** (2순위) - QA 쌍 데이터 관리 3. 📋 **Test 준비** \- 준비 상태 확인 및 환경 구성 4. 🔗 **레지스트리** \- 모든 프로젝트 통합 관리 5. 📊 **이력 관리** \- 버전 관리 및 편집 기록

**주요 기능** :

  * ✅ **3계층 임계값 설정** : 
    * Layer 1 (Basic + Security): TCR, Accuracy, Quality, Hallucination, RAG 메트릭 + Input Sanitization, Output Leakage, Authorization
    * Layer 2 (Agentic + Security): Tool Selection, Efficiency, Multi-Agent, Workflow + Privilege Escalation, Attack Detection
    * Layer 3 (Advanced): DeepEval, Ragas 고급 메트릭
  * ✅ **Golden Dataset 편집** : QA 쌍 데이터 관리
  * ✅ **버전 관리** : 변경 이력 추적 및 롤백
  * ✅ **편집 기록** : 모든 변경사항 Audit Trail

#### (2) Test 투명성 기능

**5가지 새로운 분석 기능** :

  * ✅ **이상치 탐지 (Anomaly Detection)** : 메트릭 간 불일치 자동 감지
  * ✅ **상관관계 분석 (Correlation Analysis)** : 메트릭 관계 분석 및 최적화 방향 제시
  * ✅ **성능 병목 지점 식별 (Performance Bottlenecks)** : 시스템 병목 자동 식별
  * ✅ **데이터 품질 검증 (Data Quality Validation)** : 평가 데이터 완전성 검증
  * ✅ **실행 가능한 개선 방안 (Actionable Insights)** : 우선순위 기반 구체적 개선안

**기존 기능** :

  * ✅ **계산 과정 추적** : 메트릭별 계산 단계 시각화
  * ✅ **주석 시스템** : Test 결과에 코멘트 추가
  * ✅ **Audit Log** : 모든 평가 활동 기록
  * ✅ **상세 설명** : 점수가 나온 이유 자동 생성

### 주요 변경사항

**🔥 Agent Evaluator v0.5.2 & 업데이트 (2026-03-17):**

  1. **레거시 API 완전 제거** : EvaluatedCrew, LangChainEvaluationCallback 등 deprecated 클래스 제거
  2. **보안 메트릭 통합** : Layer 1/2 Security 메트릭 추가 
     * Layer 1 Security: Input Sanitization, Output Leakage, Authorization
     * Layer 2 Security: Privilege Escalation, Attack Detection
  3. **Zero Configuration 강화** : 자동 경로 탐지 및 설정
  4. **통합 보안 대시보드** : 리스크 스코어링 및 알림 시스템

  1. **데이터 편집 탭 순서 변경** : 임계값 설정 → Golden Dataset으로 재배치 (Test 관리자 워크플로우 최적화)
  2. **3계층 지표 체계 도입** : Layer 1 (Basic) + Layer 2 (Agentic) + Layer 3 (Advanced)
  3. **임계값 설정 UI 재구성** : 3개 서브탭으로 분리 (각 계층별 관리)
  4. **Transparency 탭 대폭 개선** : 5가지 새로운 분석 기능 추가

### 아키텍처

graph TB UI[Streamlit Dashboard UI  
dashboard_data_editor.py] UI --> DEM[Data Editor Manager] UI --> TTM[Test Transparency Manager] DEM --> Storage TTM --> Storage subgraph Storage["Data Storage (JSON Files)"] S1[performance_data.json] S2[golden_datasets/*.json] S3[thresholds.json  
3계층 임계값] S4[traces/*.json] S5[annotations/*.json] S6[audit_logs/*.json] end style UI fill:#e3f2fd style DEM fill:#fff3e0 style TTM fill:#fff3e0 style Storage fill:#f3e5f5 

* * *

## 데이터 편집 기능

### 1\. TaskResult 편집

TaskResult는 Agent가 수행한 작업의 평가 결과입니다.

#### 기능

  * **데이터 로드** : `performance_data.json` 파일 로드
  * **필터링** : 작업 유형, 성공 여부, 정렬 기준 선택
  * **인라인 편집** : 테이블에서 직접 값 수정
  * **행 추가/삭제** : 새 작업 추가 또는 기존 작업 삭제
  * **통계 확인** : 실시간 통계 표시

#### UI 구성

graph TB Main["📊 TaskResult 데이터 편집"] Main --> FileSelect["파일 선택: performance_data.json"] Main --> Refresh["🔄 새로고침"] Main --> Info["ℹ️ 로드된 TaskResult: 100개"] Main --> Filter["🔍 필터 옵션"] Filter --> F1["작업 유형"] Filter --> F2["성공 여부"] Filter --> F3["정렬 기준"] Main --> Editor["📋 데이터 편집 테이블"] Editor --> Note["⚠️ 셀을 더블클릭하여 편집"] Editor --> Table["task_id - type - success - score - time"] Main --> EditInfo["편집 정보"] EditInfo --> E1["편집자: Admin"] EditInfo --> E2["이유: Data correction"] EditInfo --> Save["💾 저장"] Main --> Stats["📈 데이터 통계"] Stats --> S1["전체: 100"] Stats --> S2["성공률: 85%"] Stats --> S3["평균점수: 0.82"] style Main fill:#667eea,color:#fff style Editor fill:#e3f2fd style Filter fill:#fff3e0 style Stats fill:#e8f5e9 

#### 사용 예시
```json
    [](<#cb3-1>)# Dashboard UI에서 수행
    [](<#cb3-2>)# 1. "TaskResult 편집" 탭 선택
    [](<#cb3-3>)# 2. 필터로 원하는 데이터 찾기
    [](<#cb3-4>)# 3. 셀 더블클릭하여 값 수정
    [](<#cb3-5>)# 4. 편집자 이름과 이유 입력
    [](<#cb3-6>)# 5. "저장" 버튼 클릭
    [](<#cb3-7>)
    [](<#cb3-8>)# 프로그래매틱으로도 가능
    [](<#cb3-9>)from data_editor_manager import DataEditorManager
    [](<#cb3-10>)
    [](<#cb3-11>)manager = DataEditorManager()
    [](<#cb3-12>)
    [](<#cb3-13>)# 데이터 로드
    [](<#cb3-14>)df = manager.load_task_results("evaluation_results/performance_data.json")
    [](<#cb3-15>)
    [](<#cb3-16>)# 수정
    [](<#cb3-17>)df.loc[df['task_id'] == 'task_001', 'completion_score'] = 0.98
    [](<#cb3-18>)
    [](<#cb3-19>)# 저장 (자동 버전 백업 및 편집 기록 생성)
    [](<#cb3-20>)manager.save_task_results(
    [](<#cb3-21>)    df=df,
    [](<#cb3-22>)    filepath="evaluation_results/performance_data.json",
    [](<#cb3-23>)    editor="John Doe",
    [](<#cb3-24>)    reason="Manual correction based on expert review"
    [](<#cb3-25>))
```

#### 주요 메서드

**DataEditorManager 클래스** :

  * `load_task_results(filepath)`: TaskResult를 DataFrame으로 로드
  * `save_task_results(df, filepath, editor, reason)`: 수정된 데이터 저장 (자동 백업)
  * `add_task_result(task_data, filepath, editor, reason)`: 새 TaskResult 추가
  * `delete_task_result(task_id, filepath, editor, reason)`: TaskResult 삭제
  * `validate_task_result(task_data)`: 데이터 유효성 검증

### 2\. Golden Dataset 편집

Golden Dataset은 RAG 평가를 위한 QA 쌍 데이터입니다.

#### 기능

  * **파일 선택** : `golden_datasets` 디렉토리의 JSON 파일 선택
  * **검색** : 질문 또는 답변 검색
  * **QA 쌍 편집** : Question, Answer, Ground Truth, Context 수정
  * **행 추가/삭제** : 새 QA 쌍 추가 또는 삭제
  * **상세 보기** : 선택한 QA 쌍의 전체 내용 확인
  * **Layer 2 필드 지원** : expected_tools, expected_agents, expected_workflow_steps (Agentic AI 메트릭용)

#### UI 구성

graph TB Main["📚 Golden Dataset 편집"] Main --> FileSelect["파일: dataset_001.json"] Main --> Refresh["🔄 새로고침"] Main --> Info["ℹ️ 로드된 QA 쌍: 45개"] Main --> Search["🔍 검색"] Search --> SearchBox["질문 또는 답변 검색"] Main --> Editor["📋 QA 쌍 편집"] Editor --> Table["qa_id - question - answer - ground_truth"] Main --> Detail["📝 QA 쌍 상세 보기"] Detail --> D1["QA ID: qa_001"] Detail --> D2["질문"] Detail --> D3["답변"] Detail --> D4["Ground Truth"] Detail --> D5["컨텍스트"] Detail --> D6["Expected Tools"] Detail --> D7["Expected Agents"] Main --> EditInfo["편집 정보"] EditInfo --> E1["편집자"] EditInfo --> E2["이유"] EditInfo --> Save["💾 저장"] style Main fill:#667eea,color:#fff style Editor fill:#e3f2fd style Detail fill:#fff3e0 

#### 주요 메서드

**Golden Dataset 관리** :

  * `load_golden_dataset(filepath)`: Golden Dataset을 DataFrame으로 로드
  * `save_golden_dataset(df, filepath, dataset_id, source_document, editor, reason)`: 수정된 데이터 저장
  * `add_qa_pair(qa_data, filepath, editor, reason)`: 새 QA 쌍 추가
  * `delete_qa_pair(qa_id, filepath, editor, reason)`: QA 쌍 삭제
  * `validate_qa_pair(qa_data)`: QA 쌍 유효성 검증

**Layer 2 필드 (Agentic + Security 메트릭)** :
```json
    [](<#cb5-1>)# QA 쌍에 Layer 2 필드 추가
    [](<#cb5-2>)qa_data = {
    [](<#cb5-3>)    "qa_id": "qa_001",
    [](<#cb5-4>)    "question": "문서 검색 후 요약하세요",
    [](<#cb5-5>)    "answer": "검색 결과를 바탕으로...",
    [](<#cb5-6>)    "ground_truth": "정확한 요약",
    [](<#cb5-7>)    "context": "관련 문서 내용...",
    [](<#cb5-8>)    # Layer 2 필드
    [](<#cb5-9>)    "expected_tools": ["search", "summarize"],  # 리스트
    [](<#cb5-10>)    "expected_agents": ["search_agent", "summary_agent"],  # 리스트
    [](<#cb5-11>)    "expected_workflow_steps": ["step1", "step2"]  # 리스트
    [](<#cb5-12>)}
```

### 3\. 임계값 설정 (3계층 지표 체계)

메트릭의 통과/실패 기준값을 3계층 구조로 설정합니다.

#### 기능

  * **3계층 서브탭** : Layer 1 (Basic + Security) / Layer 2 (Agentic + Security) / Layer 3 (Advanced)
  * **슬라이더 조정** : 각 메트릭의 임계값을 슬라이더로 조정
  * **계산 방법 명시** : 각 지표마다 계산 방법 표시
  * **프리셋** : 엄격/표준/관대 프리셋 제공
  * **즉시 적용** : 저장 즉시 다음 평가부터 적용

#### 임계값 관리 메서드

**DataEditorManager 클래스** :

  * `load_thresholds()`: 임계값 설정 로드 (기본값 포함)
  * `save_thresholds(thresholds, editor, reason)`: 임계값 설정 저장 (자동 백업)
  * `load_advanced_eval_config()`: 고급 평가 설정 로드 (DeepEval, Ragas, LangSmith)
  * `save_advanced_eval_config(config, editor, reason)`: 고급 평가 설정 저장

#### UI 구성 (3계층 구조)

graph TB Main["⚙️ 메트릭 임계값 설정"] Main --> Info["📊 3계층 지표 체계"] Main --> Tab1["Layer 1: Basic + Security"] Tab1 --> T1_1["TCR: 90.0%"] Tab1 --> T1_2["Accuracy: 85.0%"] Tab1 --> T1_3["Quality: 4.0/5.0"] Tab1 --> T1_4["Hallucination: 5.0%"] Tab1 --> T1_5["Input Sanitization: 95.0%"] Tab1 --> T1_More["+ Security 메트릭..."] Main --> Tab2["Layer 2: Agentic + Security"] Tab2 --> T2_1["Tool Selection: 85.0%"] Tab2 --> T2_2["Agent Coordination: 80.0%"] Tab2 --> T2_3["Workflow Execution: 85.0%"] Tab2 --> T2_4["Attack Detection: 95.0%"] Main --> Tab3["Layer 3: Advanced"] Tab3 --> T3_1["DeepEval 메트릭"] Tab3 --> T3_2["Ragas 메트릭"] Main --> Preset["🎨 프리셋"] Preset --> P1["📘 엄격"] Preset --> P2["📗 표준"] Preset --> P3["📙 관대"] style Main fill:#667eea,color:#fff style Tab1 fill:#c8e6c9 style Tab2 fill:#fff9c4 style Tab3 fill:#ffccbc 

#### 계층별 임계값 설정 예시

**Layer 1: Basic + Security Metrics**
```json
    [](<#cb7-1>)thresholds_layer1 = {
    [](<#cb7-2>)    "tcr": 90.0,                    # Task Completion Rate
    [](<#cb7-3>)    "accuracy": 85.0,               # Accuracy
    [](<#cb7-4>)    "hallucination": 5.0,           # Hallucination Rate (낮을수록 좋음)
    [](<#cb7-5>)    "quality": 4.0,                 # Response Quality (5점 만점)
    [](<#cb7-6>)    "latency": 3.0,                 # Latency (초)
    [](<#cb7-7>)    "cost_per_task": 0.01,          # Cost per task ($)
    [](<#cb7-8>)    "retry_success_rate": 80.0,     # Retry Success Rate
    [](<#cb7-9>)    # Security Metrics
    [](<#cb7-10>)    "input_sanitization": 95.0,     # Input Sanitization Score
    [](<#cb7-11>)    "output_leakage": 95.0,          # Output Leakage Prevention
    [](<#cb7-12>)    "authorization": 98.0              # Authorization Compliance
    [](<#cb7-13>)}
```

**Layer 2: Agentic + Security Metrics**
```json
    [](<#cb8-1>)thresholds_layer2 = {
    [](<#cb8-2>)    "tool_selection_accuracy": 85.0,  # Tool Selection Accuracy
    [](<#cb8-3>)    "tool_efficiency": 90.0,          # Tool Efficiency (moved from Layer 1)
    [](<#cb8-4>)    "agent_coordination": 80.0,       # Agent Coordination Score
    [](<#cb8-5>)    "workflow_execution": 85.0,       # Workflow Execution Success Rate
    [](<#cb8-6>)    # Security Metrics
    [](<#cb8-7>)    "privilege_escalation": 98.0,    # Privilege Escalation Prevention
    [](<#cb8-8>)    "attack_detection": 95.0           # Attack Pattern Detection
    [](<#cb8-9>)}
```

**Layer 3: Advanced Metrics**
```json
    [](<#cb9-1>)thresholds_layer3 = {
    [](<#cb9-2>)    # DeepEval
    [](<#cb9-3>)    "g_eval": 0.8,
    [](<#cb9-4>)    "hallucination_score": 0.8,
    [](<#cb9-5>)    # Ragas
    [](<#cb9-6>)    "faithfulness": 0.8,
    [](<#cb9-7>)    "context_recall": 0.8,
    [](<#cb9-8>)    "context_precision": 0.8,
    [](<#cb9-9>)    "answer_relevancy": 0.8
    [](<#cb9-10>)}
```

#### 고급 평가 설정 구조
```json
    [](<#cb10-1>)# advanced_eval_config.json
    [](<#cb10-2>){
    [](<#cb10-3>)    "deepeval": {
    [](<#cb10-4>)        "enabled": True,
    [](<#cb10-5>)        "model": "gpt-4o-mini",
    [](<#cb10-6>)        "thresholds": {
    [](<#cb10-7>)            "g_eval": 0.7,
    [](<#cb10-8>)            "hallucination": 0.3,
    [](<#cb10-9>)            "toxicity": 0.3,
    [](<#cb10-10>)            "bias": 0.3
    [](<#cb10-11>)        }
    [](<#cb10-12>)    },
    [](<#cb10-13>)    "ragas": {
    [](<#cb10-14>)        "enabled": True,
    [](<#cb10-15>)        "model": "gpt-4o-mini",
    [](<#cb10-16>)        "thresholds": {
    [](<#cb10-17>)            "context_relevancy": 0.7,
    [](<#cb10-18>)            "answer_similarity": 0.7,
    [](<#cb10-19>)            "answer_correctness": 0.7,
    [](<#cb10-20>)            "overall_score": 0.7
    [](<#cb10-21>)        }
    [](<#cb10-22>)    },
    [](<#cb10-23>)    "langsmith": {
    [](<#cb10-24>)        "enabled": False,
    [](<#cb10-25>)        "api_key": ""
    [](<#cb10-26>)    },
    [](<#cb10-27>)    "metadata": {
    [](<#cb10-28>)        "last_updated": "2024-11-30T...",
    [](<#cb10-29>)        "updated_by": "Admin"
    [](<#cb10-30>)    }
    [](<#cb10-31>)}
```

### 4\. 버전 관리

데이터 변경 이력을 추적하고 롤백할 수 있습니다.

#### 기능

  * **자동 백업** : 데이터 수정 전 자동으로 버전 백업 (`_create_version` 메서드)
  * **버전 목록** : 모든 버전의 생성 시간과 설명 확인
  * **롤백** : 특정 버전으로 복원
  * **필터링** : 데이터 이름으로 필터링

#### 버전 관리 메서드

**DataEditorManager 클래스** :

  * `_create_version(filepath, description)`: 버전 스냅샷 생성 (내부 메서드, 자동 호출)
  * `list_versions(data_name=None)`: 버전 목록 조회
  * `rollback_to_version(version_id, target_filepath, editor)`: 특정 버전으로 롤백

#### 버전 저장 위치

  * `evaluation_results/versions/version_{timestamp}_{filename}.json`
  * 버전 ID 형식: `YYYYMMDD_HHMMSS`

#### UI 구성

graph TB Main["📚 버전 관리"] Main --> Filter["데이터 이름 필터: performance_data"] Main --> Refresh["🔄 새로고침"] Main --> Info["ℹ️ 총 15개의 버전"] Main --> V1["🔖 버전 20241128_103045"] V1 --> V1_Info["생성 시간: 2024-11-28 10:30:45  
설명: Before edit by John Doe"] V1 --> V1_Action["복원할 파일 선택"] V1 --> V1_Rollback["⏮️ 롤백"] Main --> V2["🔖 버전 20241128_091520"] V2 --> V2_Info["이전 버전 정보"] style Main fill:#667eea,color:#fff style V1 fill:#e3f2fd style V2 fill:#e3f2fd 

### 5\. 편집 기록

모든 편집 활동을 추적합니다.

#### 기능

  * **편집 로그** : 누가, 언제, 무엇을, 왜 편집했는지 기록
  * **필터링** : 데이터 유형, 편집 유형, 편집자로 필터
  * **상세 보기** : 변경 전/후 값 비교
  * **Diff 표시** : 변경사항 하이라이트

#### 편집 기록 메서드

**DataEditorManager 클래스** :

  * `_record_edit(edit_type, data_type, data_id, editor, reason, before_value, after_value)`: 편집 기록 (내부 메서드, 자동 호출)
  * `load_edit_history(limit=100)`: 편집 기록 로드 (DataFrame)
  * `get_edit_details(edit_id)`: 특정 편집의 상세 정보 조회

#### 편집 기록 구조 (DataEdit)
```python
    [](<#cb12-1>)@dataclass
    [](<#cb12-2>)class DataEdit:
    [](<#cb12-3>)    edit_id: str              # 편집 ID (YYYYMMDD_HHMMSS_ffffff)
    [](<#cb12-4>)    timestamp: str            # 편집 시간
    [](<#cb12-5>)    editor: str               # 편집자 이름
    [](<#cb12-6>)    edit_type: str            # "create", "update", "delete", "rollback"
    [](<#cb12-7>)    data_type: str            # "task_result", "qa_pair", "threshold", "golden_dataset"
    [](<#cb12-8>)    data_id: str              # 데이터 ID
    [](<#cb12-9>)    before_value: Optional[Dict]  # 변경 전 값
    [](<#cb12-10>)    after_value: Optional[Dict]   # 변경 후 값
    [](<#cb12-11>)    reason: str               # 편집 이유
```

#### 편집 기록 저장 위치

  * `evaluation_results/edit_history/edit_{edit_id}.json`

### 6\. Test 구성 관리 (Phase 3)

Test 환경을 미리 구성하고 저장하여 재사용할 수 있습니다.

#### 기능

  * **환경 설정 저장** : Golden Dataset, 임계값, 고급 평가 설정을 하나의 구성으로 저장
  * **구성 재사용** : 저장된 구성을 불러와서 빠르게 Test 실행
  * **환경별 관리** : development, staging, production 환경별 구성
  * **메타데이터 추적** : 프레임워크, 모델 설정, 태그 등

#### Test 구성 관리 메서드

**DataEditorManager 클래스** :

  * `prepare_test_environment()`: Test 환경 준비 상태 확인
  * `validate_test_environment()`: Test 환경 유효성 검증
  * `create_test_configuration(test_name, golden_datasets, thresholds, enable_transparency, ...)`: Test 구성 생성 및 저장
  * `load_test_configuration(config_id)`: Test 구성 로드
  * `list_test_configurations()`: 모든 Test 구성 목록 조회

#### Test 구성 구조 (Phase 3 Enhanced)
```json
    [](<#cb13-1>)config = {
    [](<#cb13-2>)    # Core fields
    [](<#cb13-3>)    "config_id": "test_config_20241130_120000",
    [](<#cb13-4>)    "test_name": "Production_API_Test",
    [](<#cb13-5>)    "created_at": "2024-11-30T12:00:00",
    [](<#cb13-6>)    "created_by": "admin@example.com",
    [](<#cb13-7>)    "golden_dataset": "golden_datasets/prod.json",  # 단일 (호환성)
    [](<#cb13-8>)    "golden_datasets": ["golden_datasets/prod.json", "golden_datasets/api.json"],  # 복수
    [](<#cb13-9>)    "thresholds": {...},  # 임계값
    [](<#cb13-10>)    "enable_transparency": True,
    [](<#cb13-11>)    "status": "ready",
    [](<#cb13-12>)
    [](<#cb13-13>)    # Phase 3: Enhanced Metadata
    [](<#cb13-14>)    "environment": "production",  # development, staging, production
    [](<#cb13-15>)    "version": "2.0",
    [](<#cb13-16>)    "description": "API 엔드포인트 회귀 테스트",
    [](<#cb13-17>)    "tags": ["api", "regression", "critical"],
    [](<#cb13-18>)    "model_config": {
    [](<#cb13-19>)        "model_name": "gpt-4",
    [](<#cb13-20>)        "temperature": 0.7,
    [](<#cb13-21>)        "max_tokens": 2000
    [](<#cb13-22>)    },
    [](<#cb13-23>)    "framework": "langchain",  # langchain, crewai, langgraph, autogen, custom
    [](<#cb13-24>)    "expected_duration_seconds": 300,
    [](<#cb13-25>)    "metadata": {
    [](<#cb13-26>)        "team": "qa",
    [](<#cb13-27>)        "priority": "high"
    [](<#cb13-28>)    }
    [](<#cb13-29>)}
```

#### 사용 예시
```python
    [](<#cb14-1>)from data_editor_manager import DataEditorManager
    [](<#cb14-2>)
    [](<#cb14-3>)manager = DataEditorManager()
    [](<#cb14-4>)
    [](<#cb14-5>)# Test 구성 생성
    [](<#cb14-6>)config = manager.create_test_configuration(
    [](<#cb14-7>)    test_name="Production_API_Test",
    [](<#cb14-8>)    golden_datasets=["golden_datasets/prod.json", "golden_datasets/api.json"],
    [](<#cb14-9>)    thresholds=None,  # 기본값 사용
    [](<#cb14-10>)    enable_transparency=True,
    [](<#cb14-11>)    author="admin@example.com",
    [](<#cb14-12>)    # Phase 3 Enhanced
    [](<#cb14-13>)    environment="production",
    [](<#cb14-14>)    description="API 엔드포인트 회귀 테스트",
    [](<#cb14-15>)    tags=["api", "regression", "critical"],
    [](<#cb14-16>)    model_config={
    [](<#cb14-17>)        "model_name": "gpt-4",
    [](<#cb14-18>)        "temperature": 0.7,
    [](<#cb14-19>)        "max_tokens": 2000
    [](<#cb14-20>)    },
    [](<#cb14-21>)    framework="langchain",
    [](<#cb14-22>)    version="2.0",
    [](<#cb14-23>)    expected_duration_seconds=300,
    [](<#cb14-24>)    metadata={"team": "qa", "priority": "high"}
    [](<#cb14-25>))
    [](<#cb14-26>)
    [](<#cb14-27>)# Test 구성 로드
    [](<#cb14-28>)loaded_config = manager.load_test_configuration("test_config_20241130_120000")
    [](<#cb14-29>)
    [](<#cb14-30>)# 모든 구성 조회
    [](<#cb14-31>)all_configs = manager.list_test_configurations()
```

#### Test 구성 저장 위치

  * `evaluation_results/test_configs/test_config_{timestamp}.json`

#### UI 구성

graph TB Main["📜 편집 기록"] Main --> Info["ℹ️ 총 25개의 편집 기록"] Main --> Filter["🔍 필터"] Filter --> F1["데이터 유형"] Filter --> F2["편집 유형"] Filter --> F3["편집자"] Main --> Table["편집 기록 테이블"] Table --> Col["시간 - 편집자 - 유형 - 데이터 - 이유"] Main --> Detail["🔍 편집 상세 보기"] Detail --> D1["편집 ID: 20241128_103045_abc123"] Detail --> D2["시간: 2024-11-28 10:30:45"] Detail --> D3["편집자: John Doe"] Detail --> D4["유형: update"] Detail --> D5["이유: Manual correction"] Detail --> D6["변경 전 값"] Detail --> D7["변경 후 값"] style Main fill:#667eea,color:#fff style Table fill:#e3f2fd style Detail fill:#fff3e0 

* * *

## Test 투명성 기능

The system now tracks and visualizes **RAG (Retrieval-Augmented Generation) metrics** :

  * **Faithfulness:** How grounded the answer is in the retrieved context
  * **Answer Relevancy:** How relevant the answer is to the question
  * **Context Recall:** How much of the ground truth is covered by retrieved context
  * **Context Precision:** How many relevant contexts are in top ranks

**Usage:** Call `monitor.record_rag_metrics()` to track these metrics, `get_rag_metrics_summary()` to view stats, and `compare_with_thresholds()` for automated pass/fail evaluation.

### 1\. 메트릭 계산 과정

각 메트릭이 어떻게 계산되었는지 단계별로 추적합니다.

#### 기능

  * **단계별 추적** : 계산 과정을 여러 단계로 분해
  * **타임라인 시각화** : 각 단계의 상태와 순서 표시
  * **중간 결과** : 각 단계의 입출력 데이터 표시
  * **에러 추적** : 실패 시 원인 파악
  * **자동 설명** : 왜 이 점수가 나왔는지 자동 생성 (`_generate_explanation` 메서드)

#### 메트릭 계산 추적 메서드

**TestTransparencyManager 클래스** :

  * `start_metric_calculation(metric_name, metric_type, task_id)`: 메트릭 계산 시작, trace_id 반환
  * `add_calculation_step(trace_id, step_name, description, input_data, output_data, status, error_message)`: 계산 단계 추가
  * `add_intermediate_result(trace_id, step_id, result)`: 중간 결과 추가
  * `complete_metric_calculation(trace_id, final_value, threshold_value, explanation, factors)`: 메트릭 계산 완료
  * `_generate_explanation(trace)`: 메트릭별 자동 설명 생성 (내부 메서드)

#### 메트릭 계산 추적 구조 (MetricCalculationTrace)
```python
    [](<#cb16-1>)@dataclass
    [](<#cb16-2>)class MetricCalculationTrace:
    [](<#cb16-3>)    metric_name: str              # 메트릭 이름
    [](<#cb16-4>)    metric_type: str              # "native", "deepeval", "ragas"
    [](<#cb16-5>)    task_id: str                  # 작업 ID
    [](<#cb16-6>)    calculation_steps: List[TestStep]  # 계산 단계 목록
    [](<#cb16-7>)    final_value: Optional[float]  # 최종 값
    [](<#cb16-8>)    passed_threshold: Optional[bool]  # 임계값 통과 여부
    [](<#cb16-9>)    threshold_value: Optional[float]  # 임계값
    [](<#cb16-10>)    explanation: Optional[str]    # 자동 생성된 설명
    [](<#cb16-11>)    factors: Dict[str, Any]       # 영향 요인
    [](<#cb16-12>)    calculated_at: str            # 계산 시간
    [](<#cb16-13>)    calculation_time: Optional[float]  # 계산 소요 시간
```

#### TestStep 구조
```python
    [](<#cb17-1>)@dataclass
    [](<#cb17-2>)class TestStep:
    [](<#cb17-3>)    step_id: str                  # 단계 ID
    [](<#cb17-4>)    step_name: str                # 단계 이름
    [](<#cb17-5>)    description: str              # 설명
    [](<#cb17-6>)    status: str                   # TestStepStatus (pending, running, success, failed, skipped)
    [](<#cb17-7>)    start_time: Optional[str]     # 시작 시간
    [](<#cb17-8>)    end_time: Optional[str]       # 종료 시간
    [](<#cb17-9>)    duration: Optional[float]     # 소요 시간
    [](<#cb17-10>)    input_data: Optional[Dict]    # 입력 데이터
    [](<#cb17-11>)    output_data: Optional[Dict]   # 출력 데이터
    [](<#cb17-12>)    intermediate_results: List[Dict]  # 중간 결과
    [](<#cb17-13>)    error_message: Optional[str]  # 에러 메시지
    [](<#cb17-14>)    warning_messages: List[str]   # 경고 메시지
```

#### Trace 저장 위치

  * `evaluation_results/traces/trace_{metric_name}_{task_id}.json`

#### 계산 과정 예시 (Faithfulness)
```python
    1. Load Context
       ↓ 검색된 컨텍스트 3개 로드
       ↓ 총 1500자
    
    2. Extract Claims
       ↓ 답변에서 주장(claim) 추출
       ↓ 5개의 주장 발견
    
    3. Verify Claims
       ↓ 각 주장을 컨텍스트로 검증
       ↓ 검증됨: 4개, 검증 안 됨: 1개
    
    4. Calculate Score
       ↓ Faithfulness = 4/5 = 0.8
       ✅ 완료
```

#### UI 구성

graph TB Main["📊 메트릭 계산 과정"] Main --> TraceSelect["Trace: faithfulness_task_001"] Main --> MetricInfo["메트릭: faithfulness - 타입: ragas - 값: 0.800"] Main --> Timeline["타임라인"] Timeline --> T1["◯────●────●────●"] Timeline --> T2["1 2 3 4"] Main --> Step1["📌 단계 1: Load Context - SUCCESS"] Step1 --> S1_Desc["설명: 검색된 컨텍스트 로드"] Step1 --> S1_Input["입력: context_count: 3"] Step1 --> S1_Output["출력: total_chars: 1500"] Main --> Step2["📌 단계 2: Extract Claims - SUCCESS"] Main --> Step3["📌 단계 3: Verify Claims - SUCCESS"] Main --> Explanation["💡 설명"] Explanation --> E1["Faithfulness 점수: 0.800"] Explanation --> E2["답변이 대체로 컨텍스트에 충실합니다"] Main --> Factors["📈 영향 요인"] Factors --> F1["total_claims: 5"] Factors --> F2["verified_claims: 4"] Factors --> F3["verification_rate: 0.8"] style Main fill:#667eea,color:#fff style Step1 fill:#fff3e0 style Explanation fill:#e8f5e9 

#### 코드 예시
```python
    [](<#cb20-1>)from test_transparency_manager import TestTransparencyManager, TestStepStatus
    [](<#cb20-2>)
    [](<#cb20-3>)manager = TestTransparencyManager()
    [](<#cb20-4>)
    [](<#cb20-5>)# 1. 메트릭 계산 시작
    [](<#cb20-6>)trace_id = manager.start_metric_calculation(
    [](<#cb20-7>)    metric_name="faithfulness",
    [](<#cb20-8>)    metric_type="ragas",
    [](<#cb20-9>)    task_id="task_001"
    [](<#cb20-10>))
    [](<#cb20-11>)
    [](<#cb20-12>)# 2. 각 단계 추가
    [](<#cb20-13>)manager.add_calculation_step(
    [](<#cb20-14>)    trace_id=trace_id,
    [](<#cb20-15>)    step_name="Load Context",
    [](<#cb20-16>)    description="검색된 컨텍스트 로드",
    [](<#cb20-17>)    input_data={"context_count": 3},
    [](<#cb20-18>)    output_data={"total_chars": 1500},
    [](<#cb20-19>)    status=TestStepStatus.SUCCESS
    [](<#cb20-20>))
    [](<#cb20-21>)
    [](<#cb20-22>)manager.add_calculation_step(
    [](<#cb20-23>)    trace_id=trace_id,
    [](<#cb20-24>)    step_name="Extract Claims",
    [](<#cb20-25>)    description="답변에서 주장(claim) 추출",
    [](<#cb20-26>)    input_data={"answer_length": 200},
    [](<#cb20-27>)    output_data={"claims_count": 5},
    [](<#cb20-28>)    status=TestStepStatus.SUCCESS
    [](<#cb20-29>))
    [](<#cb20-30>)
    [](<#cb20-31>)manager.add_calculation_step(
    [](<#cb20-32>)    trace_id=trace_id,
    [](<#cb20-33>)    step_name="Verify Claims",
    [](<#cb20-34>)    description="각 주장을 컨텍스트로 검증",
    [](<#cb20-35>)    input_data={"claims_count": 5},
    [](<#cb20-36>)    output_data={"verified_claims": 4, "unverified_claims": 1},
    [](<#cb20-37>)    status=TestStepStatus.SUCCESS
    [](<#cb20-38>))
    [](<#cb20-39>)
    [](<#cb20-40>)# 3. 계산 완료
    [](<#cb20-41>)manager.complete_metric_calculation(
    [](<#cb20-42>)    trace_id=trace_id,
    [](<#cb20-43>)    final_value=0.8,
    [](<#cb20-44>)    threshold_value=0.8,
    [](<#cb20-45>)    explanation="답변이 대체로 컨텍스트에 충실합니다.",
    [](<#cb20-46>)    factors={
    [](<#cb20-47>)        "total_claims": 5,
    [](<#cb20-48>)        "verified_claims": 4,
    [](<#cb20-49>)        "verification_rate": 0.8
    [](<#cb20-50>)    }
    [](<#cb20-51>))
```

### 2\. 주석(Annotation) 시스템

Test 결과에 의견과 코멘트를 추가할 수 있습니다.

#### 주석 유형 (AnnotationType Enum)

  1. **Comment (코멘트)** : 일반적인 의견
  2. **Issue (이슈)** : 문제 제기
  3. **Improvement (개선)** : 개선 제안
  4. **Confirmation (확인)** : 정상 확인
  5. **Question (질문)** : 질문

#### 기능

  * **주석 추가** : 특정 Task, Metric, Dataset에 주석 달기
  * **우선순위** : Low, Normal, High, Critical
  * **상태 관리** : Open, In Progress, Resolved, Closed
  * **답변 스레드** : 주석에 답변 달기
  * **태그** : 분류 및 검색을 위한 태그

#### 주석 관리 메서드

**TestTransparencyManager 클래스** :

  * `add_annotation(target_type, target_id, annotation_type, priority, title, content, author, metadata=None)`: 주석 추가, annotation 딕셔너리 반환
  * `add_reply_to_annotation(annotation_id, author, content)`: 주석에 답변 추가
  * `load_annotations(annotation_type=None, status=None, target_type=None, priority=None)`: 주석 로드 (필터링)

**파라미터** :

  * `target_type`: "task", "metric", "dataset" 등
  * `target_id`: 대상 ID
  * `annotation_type`: AnnotationType enum (NOTE, WARNING, REVIEW, IMPROVEMENT, BUG, QUESTION)
  * `priority`: "low", "medium", "high", "critical"
  * `title`: 주석 제목
  * `content`: 주석 내용
  * `author`: 작성자 이름/이메일
  * `metadata`: 선택적 추가 데이터 (related_metric, related_value 등)

#### Annotation 구조
```python
    [](<#cb21-1>)@dataclass
    [](<#cb21-2>)class Annotation:
    [](<#cb21-3>)    annotation_id: str            # 주석 ID (YYYYMMDD_HHMMSS_ffffff)
    [](<#cb21-4>)    target_type: str              # "task", "metric", "dataset"
    [](<#cb21-5>)    target_id: str                # 대상 ID
    [](<#cb21-6>)    annotation_type: str          # AnnotationType 값
    [](<#cb21-7>)    title: str                    # 제목
    [](<#cb21-8>)    content: str                  # 내용
    [](<#cb21-9>)    author: str                   # 작성자
    [](<#cb21-10>)    created_at: str               # 생성 시간
    [](<#cb21-11>)    related_metric: Optional[str] # 관련 메트릭
    [](<#cb21-12>)    related_value: Optional[float]# 관련 값
    [](<#cb21-13>)    priority: str                 # "low", "normal", "high", "critical"
    [](<#cb21-14>)    status: str                   # "open", "in_progress", "resolved", "closed"
    [](<#cb21-15>)    tags: List[str]               # 태그
    [](<#cb21-16>)    replies: List[Dict]           # 답변 스레드
```

#### 주석 저장 위치

  * `evaluation_results/annotations/annotation_{annotation_id}.json`

#### UI 구성

graph LR Main["📝 주석 관리"] Main --> List["📋 주석 목록"] List --> Filter["필터: 유형/상태/우선순위"] List --> Info["ℹ️ 8개의 주석"] List --> Item1["🟡 Faithfulness 점수 검토  
COMMENT - open"] List --> Item2["답변 스레드 2개"] Main --> Add["➕ 주석 추가"] Add --> A1["대상 유형: metric"] Add --> A2["대상 ID: faithfulness"] Add --> A3["주석 유형: comment"] Add --> A4["우선순위: normal"] Add --> A5["제목 입력"] Add --> A6["내용 입력"] Add --> A7["관련 메트릭"] Add --> A8["태그"] Add --> A9["작성자: Admin"] Add --> Submit["📤 주석 추가"] style Main fill:#667eea,color:#fff style List fill:#e3f2fd style Add fill:#fff3e0 

#### 코드 예시
```python
    [](<#cb23-1>)from test_transparency_manager import TestTransparencyManager, AnnotationType
    [](<#cb23-2>)
    [](<#cb23-3>)manager = TestTransparencyManager()
    [](<#cb23-4>)
    [](<#cb23-5>)# 주석 추가
    [](<#cb23-6>)annotation = manager.add_annotation(
    [](<#cb23-7>)    target_type="metric",
    [](<#cb23-8>)    target_id="faithfulness_task_001",
    [](<#cb23-9>)    annotation_type=AnnotationType.NOTE,
    [](<#cb23-10>)    priority="medium",
    [](<#cb23-11>)    title="Faithfulness 점수 검토",
    [](<#cb23-12>)    content="""
    [](<#cb23-13>)하나의 주장이 검증되지 않았으나, 이는 컨텍스트의 표현 방식 차이로
    [](<#cb23-14>)인한 것으로 보임. 실제로는 정상.
    [](<#cb23-15>)    """,
    [](<#cb23-16>)    author="reviewer@example.com",
    [](<#cb23-17>)    metadata={"related_metric": "faithfulness", "related_value": 0.8}
    [](<#cb23-18>))
    [](<#cb23-21>)
    [](<#cb23-22>)# 답변 추가
    [](<#cb23-23>)manager.add_reply_to_annotation(
    [](<#cb23-24>)    annotation_id=annotation["annotation_id"],
    [](<#cb23-25>)    author="expert@example.com",
    [](<#cb23-26>)    content="동의합니다. 이 경우 정상으로 판단됩니다."
    [](<#cb23-27>))
    [](<#cb23-28>)
    [](<#cb23-29>)# 상태 변경
    [](<#cb23-30>)manager.update_annotation_status(
    [](<#cb23-31>)    annotation_id=annotation_id,
    [](<#cb23-32>)    new_status="resolved",
    [](<#cb23-33>)    user="admin@example.com"
    [](<#cb23-34>))
```

### 3\. Audit Log

모든 평가 활동을 기록합니다.

#### 기록 항목

  * **Evaluation** : 평가 실행
  * **Annotation** : 주석 추가/수정
  * **Edit** : 데이터 편집
  * **View** : 데이터 조회

#### Audit Log 메서드

**TestTransparencyManager 클래스** :

  * `log_event(event_type, user, action, target_type, target_id, details, success, error_message)`: 이벤트 로깅
  * `load_audit_logs(event_type, user, limit=100)`: Audit Log 로드 (필터링)

#### AuditLogEntry 구조
```python
    [](<#cb24-1>)@dataclass
    [](<#cb24-2>)class AuditLogEntry:
    [](<#cb24-3>)    log_id: str                   # 로그 ID (YYYYMMDD_HHMMSS_ffffff)
    [](<#cb24-4>)    timestamp: str                # 시간
    [](<#cb24-5>)    event_type: str               # "evaluation", "annotation", "edit", "view"
    [](<#cb24-6>)    user: str                     # 사용자
    [](<#cb24-7>)    action: str                   # 액션
    [](<#cb24-8>)    target_type: str              # 대상 타입
    [](<#cb24-9>)    target_id: str                # 대상 ID
    [](<#cb24-10>)    details: Dict[str, Any]       # 상세 정보
    [](<#cb24-11>)    success: bool                 # 성공 여부
    [](<#cb24-12>)    error_message: Optional[str]  # 에러 메시지
```

#### Audit Log 저장 위치

  * `evaluation_results/audit_logs/audit_{log_id}.json`

#### UI 구성

graph TB Main["📜 Audit Log"] Main --> Filter["필터 옵션"] Filter --> F1["이벤트: 전체"] Filter --> F2["사용자 입력"] Filter --> F3["로그수: 100"] Main --> Info["ℹ️ 150개의 로그"] Main --> Table["로그 테이블"] Table --> Col["시간 - 이벤트 - 사용자 - 액션 - 대상 - 성공"] Table --> Row1["10:30:45 - eval - John - run - task_001 - ✅"] Table --> Row2["10:25:30 - annot - Jane - create - anno_001 - ✅"] Main --> Detail["🔍 로그 상세 보기"] Detail --> D1["로그 ID: 20241128_103045_abc123"] Detail --> D2["시간: 2024-11-28 10:30:45"] Detail --> D3["이벤트 유형: evaluation"] Detail --> D4["사용자: john@example.com"] Detail --> D5["액션: run_evaluation"] Detail --> D6["대상: task / task_001"] Detail --> D7["성공 여부: ✅ 성공"] Detail --> D8["상세 정보 JSON"] style Main fill:#667eea,color:#fff style Table fill:#e3f2fd style Detail fill:#fff3e0 

### 4\. 상세 리포트

모든 투명성 정보를 하나의 리포트로 통합합니다.

#### 포함 내용

  * 평가 요약
  * 메트릭 계산 추적
  * 주석 목록
  * Audit Log
  * 권장사항

#### 리포트 생성 메서드

**TestTransparencyManager 클래스** :

  * `generate_transparent_report(task_id, task_type, success, metric_traces, annotations)`: 투명한 평가 리포트 생성
  * `_generate_summary(traces)`: 요약 생성 (내부 메서드)
  * `_generate_recommendations(traces)`: 권장사항 생성 (내부 메서드)

#### TransparentEvaluationReport 구조
```python
    [](<#cb26-1>)@dataclass
    [](<#cb26-2>)class TransparentEvaluationReport:
    [](<#cb26-3>)    report_id: str                    # 리포트 ID
    [](<#cb26-4>)    task_id: str                      # 작업 ID
    [](<#cb26-5>)    evaluated_at: str                 # 평가 시간
    [](<#cb26-6>)    task_type: str                    # 작업 타입
    [](<#cb26-7>)    success: bool                     # 성공 여부
    [](<#cb26-8>)    metric_traces: List[MetricCalculationTrace]  # 메트릭 추적
    [](<#cb26-9>)    annotations: List[Annotation]     # 주석 목록
    [](<#cb26-10>)    audit_logs: List[AuditLogEntry]   # Audit Log
    [](<#cb26-11>)    summary: Dict[str, Any]           # 요약
    [](<#cb26-12>)    recommendations: List[str]        # 권장사항
```

#### 리포트 저장 위치

  * `evaluation_results/transparent_report_{report_id}.json`

### 5\. 고급 분석 기능 (Phase 3 Enhanced)

TestTransparencyManager는 5가지 새로운 고급 분석 기능을 제공합니다.

#### 5.1 이상치 탐지 (Anomaly Detection)

**메서드** : `analyze_metric_anomalies(monitor)`

메트릭 간 불일치를 자동으로 감지합니다:

  * TCR과 정확도 불일치 (TCR > 90% but Accuracy < 70%)
  * 품질과 환각률 모순 (Quality > 4.0 but Hallucination > 10%)
  * 고지연 경고 (Latency > 5.0s)
  * 낮은 정확도 경고 (Accuracy < 70%)

반환값:
```json
    [](<#cb27-1>){
    [](<#cb27-2>)    'anomalies': [...],      # 이상치 목록
    [](<#cb27-3>)    'warnings': [...],       # 경고 목록
    [](<#cb27-4>)    'insights': [...],       # 긍정적 인사이트
    [](<#cb27-5>)    'analyzed_at': '...'
    [](<#cb27-6>)}
```

#### 5.2 상관관계 분석 (Correlation Analysis)

**메서드** : `analyze_metric_correlations(monitor)`

메트릭 간 관계를 분석합니다:

  * 지연시간 vs 토큰 사용량
  * 품질 vs 정확도
  * 비용 vs 성능

반환값:
```json
    [](<#cb28-1>){
    [](<#cb28-2>)    'correlations': [...],   # 상관관계 목록
    [](<#cb28-3>)    'analyzed_at': '...'
    [](<#cb28-4>)}
```

#### 5.3 성능 병목 지점 식별 (Performance Bottlenecks)

**메서드** : `identify_performance_bottlenecks(monitor)`

시스템 병목을 자동으로 식별합니다:

  * 지연시간 아웃라이어 (P95 > Mean × 2)
  * 과도한 도구 호출 (Avg Tools > 5)
  * 높은 재시도율 (Retry Rate > 20%)

반환값:
```json
    [](<#cb29-1>){
    [](<#cb29-2>)    'bottlenecks': [...],    # 병목 지점 목록
    [](<#cb29-3>)    'analyzed_at': '...'
    [](<#cb29-4>)}
```

#### 5.4 데이터 품질 검증 (Data Quality Validation)

**메서드** : `generate_data_quality_report(monitor)`

평가 데이터의 완전성을 검증합니다:

  * 평가된 작업 수
  * 점수 누락 여부
  * 에러 발생률
  * 품질 평가 완전성

반환값:
```json
    [](<#cb30-1>){
    [](<#cb30-2>)    'overall_score': 85.0,      # 전체 품질 점수 (0-100)
    [](<#cb30-3>)    'quality_issues': [...],    # 품질 이슈 목록
    [](<#cb30-4>)    'data_completeness': {...}, # 데이터 완전성
    [](<#cb30-5>)    'analyzed_at': '...'
    [](<#cb30-6>)}
```

#### 5.5 실행 가능한 개선 방안 (Actionable Insights)

**메서드** : `generate_actionable_insights(monitor)`

우선순위 기반 구체적 개선안을 제시합니다:

  * 비용 최적화 (Cost > $1.0)
  * 응답 속도 개선 (Latency > 3.0s)
  * 정확도 향상 (Accuracy < 85%)
  * 환각 발생 감소 (Hallucination > 5%)
  * 응답 품질 개선 (Quality < 4.0)

반환값:
```json
    [](<#cb31-1>)[
    [](<#cb31-2>)    {
    [](<#cb31-3>)        'priority': 'high',              # critical, high, medium, low
    [](<#cb31-4>)        'category': 'cost',              # cost, performance, accuracy, reliability, quality
    [](<#cb31-5>)        'title': '비용 최적화 기회',
    [](<#cb31-6>)        'current_state': '총 비용: $10.00',
    [](<#cb31-7>)        'action': 'GPT-4o-mini 사용 고려',
    [](<#cb31-8>)        'expected_impact': '비용을 최대 90% 절감',
    [](<#cb31-9>)        'implementation': [              # 구체적 구현 단계
    [](<#cb31-10>)            '1. create_monitor(profile="minimal")',
    [](<#cb31-11>)            '2. 고급 메트릭 샘플링 적용',
    [](<#cb31-12>)            '3. 더 저렴한 모델로 변경'
    [](<#cb31-13>)        ]
    [](<#cb31-14>)    },
    [](<#cb31-15>)    ...
    [](<#cb31-16>)]
```

* * *

## UX 설계

### 1\. 네비게이션 구조

graph TD Dashboard[Dashboard 메인] Dashboard --> E1[📊 개요] Dashboard --> E2[🎯 정확도 & 품질] Dashboard --> E3[⚡ 효율성] Dashboard --> E4[🔬 고급 평가 지표] Dashboard --> E5[🚨 알림] Dashboard --> N1[📝 데이터 편집 ⭐ NEW] N1 --> N1S1[TaskResult 편집] N1 --> N1S2[Golden Dataset 편집] N1 --> N1S3[임계값 설정] N1 --> N1S4[버전 관리] N1 --> N1S5[편집 기록] Dashboard --> N2[🔬 Test 투명성 ⭐ NEW] N2 --> N2S1[메트릭 계산 과정] N2 --> N2S2[주석 관리] N2 --> N2S3[Audit Log] N2 --> N2S4[상세 리포트] style Dashboard fill:#e3f2fd style N1 fill:#fff9c4 style N2 fill:#fff9c4 

### 2\. 사용자 플로우

#### 플로우 1: 데이터 수정

flowchart TD A[Dashboard 접속] --> B[데이터 편집 탭 선택] B --> C{편집할 데이터  
유형 선택} C -->|TaskResult| D1[TaskResult 편집] C -->|Golden Dataset| D2[Golden Dataset 편집] C -->|임계값| D3[임계값 설정] D1 --> E[필터/검색으로  
대상 찾기] D2 --> E D3 --> E E --> F[셀 더블클릭하여  
편집] F --> G[편집자 이름과  
이유 입력] G --> H[저장 버튼 클릭] H --> I[✅ 자동 백업 및  
편집 기록 생성] style A fill:#e3f2fd style I fill:#c8e6c9 

#### 플로우 2: 평가 결과 검토

flowchart TD A[Dashboard 접속] --> B[Test 투명성 탭 선택] B --> C[메트릭 계산 과정 선택] C --> D[확인할 Trace 선택] D --> E[계산 단계별 확인] E --> F[타임라인 시각화] E --> G[각 단계의 입출력] E --> H[중간 결과] F --> I[설명 확인] G --> I H --> I I --> J{주석 필요?} J -->|Yes| K[주석 관리 탭 이동] K --> L[주석 추가 폼 작성] L --> M[제출] M --> N[✅ 주석 저장 및  
Audit Log 생성] J -->|No| O[검토 완료] style A fill:#e3f2fd style N fill:#c8e6c9 style O fill:#c8e6c9 

### 3\. 디자인 원칙

#### 직관성

  * 명확한 아이콘 사용
  * 일관된 색상 체계
  * 단계별 프로세스 표시

#### 효율성

  * 인라인 편집으로 빠른 수정
  * 필터/검색으로 빠른 탐색
  * 벌크 작업 지원

#### 안전성

  * 자동 백업
  * 변경 전 확인 메시지
  * 롤백 기능

#### 투명성

  * 모든 변경 기록
  * 상세한 설명 제공
  * 시각적 피드백

* * *

## 사용 방법

### 시나리오 1: 평가 데이터 수정

**상황** : Task_001의 completion_score가 잘못 기록되어 수정이 필요
```bash
    [](<#cb35-1>)# 1. Dashboard 실행
    [](<#cb35-2>)streamlit run streamlit_dashboard.py
    [](<#cb35-3>)
    [](<#cb35-4>)# 2. "📝 데이터 편집" 탭 클릭
    [](<#cb35-5>)
    [](<#cb35-6>)# 3. "TaskResult 편집" 선택
    [](<#cb35-7>)
    [](<#cb35-8>)# 4. 필터에서 task_id로 검색: "task_001"
    [](<#cb35-9>)
    [](<#cb35-10>)# 5. completion_score 셀 더블클릭하여 0.98로 수정
    [](<#cb35-11>)
    [](<#cb35-12>)# 6. 편집자 이름: "John Doe"
    [](<#cb35-13>)#    편집 이유: "Manual correction based on expert review"
    [](<#cb35-14>)
    [](<#cb35-15>)# 7. "💾 저장" 클릭
    [](<#cb35-16>)
    [](<#cb35-17>)# ✅ 완료! 자동으로 버전 백업 및 편집 기록 생성됨
```

### 시나리오 2: Golden Dataset QA 쌍 추가

**상황** : 새로운 QA 쌍을 Golden Dataset에 추가
```json
    [](<#cb36-1>)# 1. "📝 데이터 편집" 탭 → "Golden Dataset 편집"
    [](<#cb36-2>)
    [](<#cb36-3>)# 2. 파일 선택: "golden_datasets/company_policy.json"
    [](<#cb36-4>)
    [](<#cb36-5>)# 3. 테이블 하단의 "+" 버튼 클릭 (행 추가)
    [](<#cb36-6>)
    [](<#cb36-7>)# 4. 새 행에 데이터 입력:
    [](<#cb36-8>)#    - qa_id: "qa_046"
    [](<#cb36-9>)#    - question: "재택근무 정책은?"
    [](<#cb36-10>)#    - answer: "주 2회까지 재택근무 가능"
    [](<#cb36-11>)#    - ground_truth: "주 2회"
    [](<#cb36-12>)#    - context: "당사의 재택근무 정책..."
    [](<#cb36-13>)#    - page_number: 15
    [](<#cb36-14>)
    [](<#cb36-15>)# 5. "💾 저장" 클릭
    [](<#cb36-16>)
    [](<#cb36-17>)# ✅ 완료!
```

### 시나리오 3: 임계값 조정

**상황** : Faithfulness 기준을 0.8에서 0.85로 강화
```json
    [](<#cb37-1>)# 1. "📝 데이터 편집" 탭 → "임계값 설정"
    [](<#cb37-2>)
    [](<#cb37-3>)# 2. RAG 메트릭 섹션에서 Faithfulness 슬라이더를 0.85로 조정
    [](<#cb37-4>)
    [](<#cb37-5>)# 3. 편집 이유: "Stricter quality control"
    [](<#cb37-6>)
    [](<#cb37-7>)# 4. "💾 저장" 클릭
    [](<#cb37-8>)
    [](<#cb37-9>)# ✅ 다음 평가부터 새 임계값 적용!
```

### 시나리오 4: 평가 과정 확인 및 주석 추가

**상황** : Faithfulness 점수가 낮게 나온 이유를 확인하고 의견 추가
```json
    [](<#cb38-1>)# 1. "🔬 Test 투명성" 탭 클릭
    [](<#cb38-2>)
    [](<#cb38-3>)# 2. "메트릭 계산 과정" 선택
    [](<#cb38-4>)
    [](<#cb38-5>)# 3. Trace 선택: "trace_faithfulness_task_001"
    [](<#cb38-6>)
    [](<#cb38-7>)# 4. 계산 단계 확인:
    [](<#cb38-8>)#    Step 1: Load Context ✅
    [](<#cb38-9>)#    Step 2: Extract Claims ✅
    [](<#cb38-10>)#    Step 3: Verify Claims ✅
    [](<#cb38-11>)#      → 5개 주장 중 3개만 검증됨
    [](<#cb38-12>)
    [](<#cb38-13>)# 5. 설명 읽기:
    [](<#cb38-14>)#    "⚠️ 주의: 일부 주장이 컨텍스트로 뒷받침되지 않습니다."
    [](<#cb38-15>)
    [](<#cb38-16>)# 6. 주석 추가 버튼 클릭 (또는 "주석 관리" 탭으로 이동)
    [](<#cb38-17>)
    [](<#cb38-18>)# 7. 주석 폼 작성:
    [](<#cb38-19>)#    - 대상 유형: metric
    [](<#cb38-20>)#    - 대상 ID: trace_faithfulness_task_001
    [](<#cb38-21>)#    - 주석 유형: comment
    [](<#cb38-22>)#    - 제목: "낮은 점수 원인 분석"
    [](<#cb38-23>)#    - 내용: "검색된 컨텍스트가 불충분함.
    [](<#cb38-24>)#             검색 top_k를 5로 늘려야 함."
    [](<#cb38-25>)#    - 우선순위: high
    [](<#cb38-26>)#    - 태그: "improvement, search"
    [](<#cb38-27>)
    [](<#cb38-28>)# 8. "📤 주석 추가" 클릭
    [](<#cb38-29>)
    [](<#cb38-30>)# ✅ 주석 저장 및 Audit Log 기록!
```

### 시나리오 5: 버전 롤백

**상황** : 실수로 데이터를 잘못 수정하여 이전 버전으로 복원
```json
    [](<#cb39-1>)# 1. "📝 데이터 편집" 탭 → "버전 관리"
    [](<#cb39-2>)
    [](<#cb39-3>)# 2. 데이터 이름 필터: "performance_data"
    [](<#cb39-4>)
    [](<#cb39-5>)# 3. 버전 목록에서 복원할 버전 선택:
    [](<#cb39-6>)#    🔖 버전 20241128_103045
    [](<#cb39-7>)#    "Before edit by John Doe"
    [](<#cb39-8>)
    [](<#cb39-9>)# 4. "⏮️ 롤백" 버튼 클릭
    [](<#cb39-10>)
    [](<#cb39-11>)# 5. 확인 메시지: "정말로 롤백하시겠습니까?"
    [](<#cb39-12>)#    → "예" 클릭
    [](<#cb39-13>)
    [](<#cb39-14>)# ✅ 복원 완료! 현재 데이터는 자동 백업됨
```

* * *

## 고급 활용

### 1\. CI/CD 통합
```json
    [](<#cb40-1>)# .github/workflows/evaluation.yml
    [](<#cb40-2>)name: Agent Evaluation
    [](<#cb40-3>)
    [](<#cb40-4>)on: [push, pull_request]
    [](<#cb40-5>)
    [](<#cb40-6>)jobs:
    [](<#cb40-7>)  evaluate:
    [](<#cb40-8>)    runs-on: ubuntu-latest
    [](<#cb40-9>)    steps:
    [](<#cb40-10>)      - uses: actions/checkout@v2
    [](<#cb40-11>)
    [](<#cb40-12>)      - name: Setup Python
    [](<#cb40-13>)        uses: actions/setup-python@v2
    [](<#cb40-14>)        with:
    [](<#cb40-15>)          python-version: '3.11'
    [](<#cb40-16>)
    [](<#cb40-17>)      - name: Install dependencies
    [](<#cb40-18>)        run: pip install agent-evaluator
    [](<#cb40-19>)
    [](<#cb40-20>)      - name: Run Evaluation
    [](<#cb40-21>)        run: |
    [](<#cb40-22>)          python evaluate_agent.py
    [](<#cb40-23>)        env:
    [](<#cb40-24>)          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    [](<#cb40-25>)
    [](<#cb40-26>)      - name: Check Thresholds
    [](<#cb40-27>)        run: |
    [](<#cb40-28>)          python check_thresholds.py
    [](<#cb40-29>)          # 임계값 미달 시 실패
    [](<#cb40-30>)
    [](<#cb40-31>)      - name: Upload Results
    [](<#cb40-32>)        uses: actions/upload-artifact@v2
    [](<#cb40-33>)        with:
    [](<#cb40-34>)          name: evaluation-results
    [](<#cb40-35>)          path: evaluation_results/
    [](<#cb40-36>)
    [](<#cb40-37>)      - name: Create Annotations
    [](<#cb40-38>)        if: failure()
    [](<#cb40-39>)        run: |
    [](<#cb40-40>)          python create_annotation.py \
    [](<#cb40-41>)            --type issue \
    [](<#cb40-42>)            --title "Evaluation Failed" \
    [](<#cb40-43>)            --priority critical
```

### 2\. 자동 알림
```python
    [](<#cb41-1>)# alert_on_threshold_violation.py
    [](<#cb41-2>)from data_editor_manager import DataEditorManager
    [](<#cb41-3>)from test_transparency_manager import TestTransparencyManager, AnnotationType
    [](<#cb41-4>)import smtplib
    [](<#cb41-5>)
    [](<#cb41-6>)def check_and_alert():
    [](<#cb41-7>)    """임계값 위반 시 자동 알림"""
    [](<#cb41-8>)    manager = DataEditorManager()
    [](<#cb41-9>)    trans_manager = TestTransparencyManager()
    [](<#cb41-10>)
    [](<#cb41-11>)    # 최근 평가 결과 로드
    [](<#cb41-12>)    df = manager.load_task_results("evaluation_results/performance_data.json")
    [](<#cb41-13>)    thresholds = manager.load_thresholds()
    [](<#cb41-14>)
    [](<#cb41-15>)    # 임계값 확인
    [](<#cb41-16>)    violations = []
    [](<#cb41-17>)
    [](<#cb41-18>)    avg_completion = df['completion_score'].mean()
    [](<#cb41-19>)    if avg_completion < thresholds['tcr'] / 100:
    [](<#cb41-20>)        violations.append({
    [](<#cb41-21>)            "metric": "TCR",
    [](<#cb41-22>)            "value": avg_completion,
    [](<#cb41-23>)            "threshold": thresholds['tcr'] / 100
    [](<#cb41-24>)        })
    [](<#cb41-25>)
    [](<#cb41-26>)    # 위반 발견 시
    [](<#cb41-27>)    if violations:
    [](<#cb41-28>)        # 1. 주석 추가
    [](<#cb41-29>)        for v in violations:
    [](<#cb41-30>)            trans_manager.add_annotation(
    [](<#cb41-31>)                target_type="metric",
    [](<#cb41-32>)                target_id=f"{v['metric']}_violation",
    [](<#cb41-33>)                annotation_type=AnnotationType.BUG,
    [](<#cb41-34>)                priority="high",
    [](<#cb41-35>)                title=f"{v['metric']} Threshold Violation",
    [](<#cb41-36>)                content=f"Value: {v['value']:.3f}, Threshold: {v['threshold']:.3f}",
    [](<#cb41-37>)                author="auto-alert"
    [](<#cb41-38>)            )
    [](<#cb41-39>)
    [](<#cb41-40>)        # 2. 이메일 발송
    [](<#cb41-41>)        send_alert_email(violations)
    [](<#cb41-42>)
    [](<#cb41-43>)def send_alert_email(violations):
    [](<#cb41-44>)    """알림 이메일 발송"""
    [](<#cb41-45>)    # 구현...
    [](<#cb41-46>)    pass
    [](<#cb41-47>)
    [](<#cb41-48>)if __name__ == "__main__":
    [](<#cb41-49>)    check_and_alert()
```

### 3\. 주기적 리포트
```python
    [](<#cb42-1>)# generate_weekly_report.py
    [](<#cb42-2>)from test_transparency_manager import TestTransparencyManager
    [](<#cb42-3>)from datetime import datetime, timedelta
    [](<#cb42-4>)
    [](<#cb42-5>)def generate_weekly_report():
    [](<#cb42-6>)    """주간 리포트 생성"""
    [](<#cb42-7>)    manager = TestTransparencyManager()
    [](<#cb42-8>)
    [](<#cb42-9>)    # 지난 주 Audit Log 조회
    [](<#cb42-10>)    week_ago = datetime.now() - timedelta(days=7)
    [](<#cb42-11>)
    [](<#cb42-12>)    logs = manager.load_audit_logs(limit=1000)
    [](<#cb42-13>)    recent_logs = [
    [](<#cb42-14>)        log for log in logs
    [](<#cb42-15>)        if datetime.fromisoformat(log.timestamp) >= week_ago
    [](<#cb42-16>)    ]
    [](<#cb42-17>)
    [](<#cb42-18>)    # 통계 집계
    [](<#cb42-19>)    stats = {
    [](<#cb42-20>)        "total_evaluations": len([l for l in recent_logs if l.event_type == "evaluation"]),
    [](<#cb42-21>)        "total_edits": len([l for l in recent_logs if l.event_type == "edit"]),
    [](<#cb42-22>)        "total_annotations": len([l for l in recent_logs if l.event_type == "annotation"]),
    [](<#cb42-23>)        "unique_users": len(set(l.user for l in recent_logs))
    [](<#cb42-24>)    }
    [](<#cb42-25>)
    [](<#cb42-26>)    # 리포트 생성
    [](<#cb42-27>)    report = f"""
    [](<#cb42-28>)# 주간 활동 리포트
    [](<#cb42-29>)
    [](<#cb42-30>)**기간:** {week_ago.strftime('%Y-%m-%d')} ~ {datetime.now().strftime('%Y-%m-%d')}
    [](<#cb42-31>)
    [](<#cb42-32>)## 📊 요약
    [](<#cb42-33>)
    [](<#cb42-34>)- 총 평가: {stats['total_evaluations']}회
    [](<#cb42-35>)- 데이터 편집: {stats['total_edits']}회
    [](<#cb42-36>)- 주석 추가: {stats['total_annotations']}개
    [](<#cb42-37>)- 활동 사용자: {stats['unique_users']}명
    [](<#cb42-38>)
    [](<#cb42-39>)## 📈 상세 활동
    [](<#cb42-40>)
    [](<#cb42-41>)...
    [](<#cb42-42>)"""
    [](<#cb42-43>)
    [](<#cb42-44>)    # 저장
    [](<#cb42-45>)    with open(f"weekly_report_{datetime.now().strftime('%Y%m%d')}.md", 'w') as f:
    [](<#cb42-46>)        f.write(report)
    [](<#cb42-47>)
    [](<#cb42-48>)if __name__ == "__main__":
    [](<#cb42-49>)    generate_weekly_report()
```

* * *

## FAQ

### Q: 데이터를 편집하면 기존 파일이 덮어써지나요?

**A** : 네, 하지만 걱정하지 마세요! 편집하기 전에 자동으로 버전 백업이 생성됩니다. “버전 관리” 탭에서 언제든지 이전 버전으로 롤백할 수 있습니다.

### Q: 여러 사람이 동시에 편집하면 어떻게 되나요?

**A** : 현재 버전은 파일 기반이므로 동시 편집 시 나중에 저장한 사람의 변경사항이 적용됩니다. 편집 기록에서 누가 언제 무엇을 변경했는지 확인할 수 있습니다. 향후 버전에서는 Lock 메커니즘을 추가할 예정입니다.

### Q: Test 투명성 기능이 평가 속도를 느리게 하나요?

**A** : 약간의 오버헤드가 있지만, 대부분 무시할 수 있는 수준입니다 (약 5-10% 증가). 필요한 경우 `enable_transparency=False`로 비활성화할 수 있습니다.

### Q: 주석을 CSV나 Excel로 내보낼 수 있나요?

**A** : 네, 다음 코드로 가능합니다:
```python
    [](<#cb43-1>)from test_transparency_manager import TestTransparencyManager
    [](<#cb43-2>)import pandas as pd
    [](<#cb43-3>)
    [](<#cb43-4>)manager = TestTransparencyManager()
    [](<#cb43-5>)annotations = manager.load_annotations()
    [](<#cb43-6>)
    [](<#cb43-7>)# DataFrame으로 변환
    [](<#cb43-8>)data = [asdict(a) for a in annotations]
    [](<#cb43-9>)df = pd.DataFrame(data)
    [](<#cb43-10>)
    [](<#cb43-11>)# CSV 저장
    [](<#cb43-12>)df.to_csv("annotations.csv", index=False, encoding='utf-8-sig')
```

### Q: Audit Log가 너무 많아지면 어떻게 하나요?

**A** : 오래된 로그는 주기적으로 아카이빙할 수 있습니다:
```python
    [](<#cb44-1>)from pathlib import Path
    [](<#cb44-2>)from datetime import datetime, timedelta
    [](<#cb44-3>)import shutil
    [](<#cb44-4>)
    [](<#cb44-5>)audit_dir = Path("evaluation_results/audit_logs")
    [](<#cb44-6>)archive_dir = Path("evaluation_results/audit_logs_archive")
    [](<#cb44-7>)archive_dir.mkdir(exist_ok=True)
    [](<#cb44-8>)
    [](<#cb44-9>)# 30일 이상 된 로그 아카이빙
    [](<#cb44-10>)cutoff_date = datetime.now() - timedelta(days=30)
    [](<#cb44-11>)
    [](<#cb44-12>)for log_file in audit_dir.glob("audit_*.json"):
    [](<#cb44-13>)    if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
    [](<#cb44-14>)        shutil.move(str(log_file), str(archive_dir / log_file.name))
```

* * *

## 🎯 품질 관리자 가이드 (QA Manager Guide)

데이터 편집 및 Test 투명성 기능을 활용한 체계적인 품질 관리 전략을 제시합니다.

### 7.1 데이터 편집 품질 관리

#### 7.1.1 데이터 편집 품질 체크리스트

단계 | 품질 확인 항목 | 검증 방법 | 합격 기준  
---|---|---|---  
1️⃣ 편집 전 | 원본 데이터 백업, 편집 사유 명확화 | 백업 파일 존재 확인, 편집 사유서 작성 | 백업 100% 완료, 사유서 승인  
2️⃣ 편집 중 | 데이터 형식 검증, 필수 필드 확인 | 자동 검증 도구, 필드 체크리스트 | 검증 오류 0건  
3️⃣ 편집 후 | 변경 이력 기록, 영향 분석 | 히스토리 로그, 메트릭 비교 | 히스토리 100% 기록, 메트릭 변화 < 5%  
4️⃣ 검증 | 재평가 실행, 결과 비교 | A/B 테스트, 통계 분석 | 품질 개선 확인, 회귀 없음  
5️⃣ 승인 | QA 검토, 스테이크홀더 승인 | 검토 보고서, 승인 워크플로우 | QA/PM 승인 완료  
  
#### 7.1.2 데이터 편집 권한 관리

역할 | 편집 권한 | 승인 필요 여부 | 감사 추적  
---|---|---|---  
👤 QA Manager | 전체 데이터 편집, 삭제, 임계값 수정 | PM 승인 (프로덕션만) | 모든 액션 로깅  
🧑‍💻 Developer | 테스트/개발 데이터 편집 | QA 승인 (스테이징 이상) | 변경 이력 필수  
📊 Data Analyst | 읽기, 보고서 생성 | 승인 불필요 | 접근 로그만  
👁️ Viewer | 읽기만 가능 | 승인 불필요 | 접근 로그만  
  
#### 7.1.3 데이터 편집 시나리오 및 Best Practices

**시나리오 1: Golden Dataset 품질 개선**
```python
    # QA Manager 워크플로우
    # Step 1: 문제 데이터 식별
    qa_pairs = load_golden_dataset("qa_pairs.json")
    problematic = [qa for qa in qa_pairs if qa['metrics']['accuracy'] < 0.7]
    print(f"문제 데이터: {len(problematic)}개 발견")
    
    # Step 2: 백업 생성
    backup_file = f"qa_pairs_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_backup(qa_pairs, backup_file)
    print(f"✓ 백업 완료: {backup_file}")
    
    # Step 3: Dashboard에서 편집
    # 1. Streamlit Dashboard 실행
    # 2. "📝 데이터 편집" 탭 선택
    # 3. 문제 데이터 필터링 (Accuracy < 0.7)
    # 4. 각 항목 클릭하여 편집:
    #    - Question 명확화
    #    - Expected Answer 구체화
    #    - Context 정보 보완
    
    # Step 4: 변경 이력 확인
    for qa in problematic:
        history = get_edit_history(qa['id'])
        print(f"QA {qa['id']}: {len(history)} 변경 기록")
    
    # Step 5: 재평가 및 검증
    new_metrics = re_evaluate_dataset("qa_pairs.json")
    improvement = calculate_improvement(old_metrics, new_metrics)
    print(f"품질 개선: Accuracy {improvement['accuracy']:+.1%}")
    
```

**시나리오 2: 임계값 수정 후 영향 분석**
```python
    # QA Manager 워크플로우
    # Step 1: 현재 임계값 기록
    current_thresholds = {
        "task_completion_rate": 0.85,
        "accuracy": 0.80,
        "response_time": 5.0
    }
    print("현재 임계값:", current_thresholds)
    
    # Step 2: Dashboard에서 임계값 수정
    # 1. "⚙️ 임계값 설정" 탭 선택
    # 2. 메트릭별 임계값 조정
    # 3. "저장" 클릭
    
    # Step 3: 영향 분석 (Dashboard "📊 Test 투명성" 탭)
    # - 변경 전후 통과율 비교
    # - 영향 받는 테스트 케이스 수
    # - 메트릭 분포 변화
    
    # Step 4: 롤백 결정
    if pass_rate_drop > 0.20:  # 통과율 20% 이상 하락
        print("❌ 임계값 수정 롤백 필요")
        rollback_thresholds(current_thresholds)
    else:
        print("✅ 임계값 수정 승인")
        approve_threshold_change()
    
```

### 7.2 Test 투명성 및 감사 추적

#### 7.2.1 감사 로그 모니터링

로그 유형 | 기록 내용 | 보관 기간 | 접근 권한  
---|---|---|---  
📝 데이터 편집 | 누가, 언제, 무엇을, 왜 변경했는지 | 2년 | QA Manager, PM  
⚙️ 임계값 변경 | 변경 전후 값, 영향 받는 테스트 수 | 2년 | QA Manager, PM  
🔍 테스트 실행 | 실행 시간, 결과, 통과율 | 6개월 | 모든 팀원  
👤 사용자 액션 | 로그인, 페이지 접근, 다운로드 | 3개월 | Admin만  
  
#### 7.2.2 Test 투명성 대시보드 활용

**실시간 품질 모니터링**
```python
    # Streamlit Dashboard "📊 Test 투명성" 탭
    import streamlit as st
    
    # 1. 전체 테스트 통과율
    st.metric("전체 통과율", "87.5%", "+2.3%")
    
    # 2. 메트릭별 통과율
    metrics_pass_rate = {
        "Task Completion Rate": 0.92,
        "Accuracy": 0.85,
        "Response Time": 0.81
    }
    for metric, rate in metrics_pass_rate.items():
        status = "✅" if rate >= 0.85 else "⚠️" if rate >= 0.75 else "❌"
        st.write(f"{status} {metric}: {rate:.1%}")
    
    # 3. 실패 케이스 분석
    failed_cases = get_failed_test_cases()
    st.write(f"실패 케이스: {len(failed_cases)}개")
    for case in failed_cases:
        with st.expander(f"❌ {case['id']}: {case['question'][:50]}..."):
            st.write(f"**실패 이유**: {case['failure_reason']}")
            st.write(f"**Expected**: {case['expected']}")
            st.write(f"**Actual**: {case['actual']}")
            st.write(f"**메트릭**: {case['metrics']}")
            if st.button("편집", key=case['id']):
                edit_qa_pair(case['id'])
    
```

#### 7.2.3 변경 이력 추적 및 롤백

변경 유형 | 추적 정보 | 롤백 절차 | 영향 범위  
---|---|---|---  
Golden Dataset 편집 | 필드별 before/after, 편집자, 시간 | 히스토리에서 이전 버전 선택 → 복원 | 해당 QA Pair만  
임계값 변경 | 메트릭별 변경 전후 값, 승인자 | 설정 파일 이전 버전 복원 | 모든 테스트  
대량 데이터 가져오기 | 파일명, 추가/수정 수, 타임스탬프 | 백업 파일에서 복원 | 전체 Dataset  
데이터 삭제 | 삭제된 항목, 삭제자, 사유 | 휴지통에서 복구 (30일 보관) | 삭제된 항목만  
  
### 7.3 Golden Dataset 품질 보증

#### 7.3.1 Golden Dataset 품질 기준

품질 차원 | 측정 지표 | 목표값 | 측정 방법  
---|---|---|---  
✅ 완전성 | 필수 필드 채움율 | 100% | null/empty 필드 카운트  
🎯 정확성 | Expected Answer 품질 | Expert 검증 > 95% | SME(Subject Matter Expert) 리뷰  
📏 일관성 | 포맷/스타일 통일성 | > 98% | 자동 검증 스크립트  
🔄 최신성 | 업데이트 주기 | 분기별 1회 | 마지막 업데이트 날짜 확인  
📊 대표성 | 시나리오 커버리지 | > 90% | 시나리오 매트릭스 커버리지  
  
#### 7.3.2 Golden Dataset 유효성 검증 스크립트
```python
    #!/usr/bin/env python3
    """Golden Dataset 품질 검증 스크립트"""
    import json
    from typing import Dict, List
    
    def validate_golden_dataset(dataset_path: str) -> Dict:
        """Golden Dataset 전체 품질 검증"""
    
        with open(dataset_path, 'r', encoding='utf-8') as f:
            qa_pairs = json.load(f)
    
        report = {
            "total_pairs": len(qa_pairs),
            "completeness": check_completeness(qa_pairs),
            "consistency": check_consistency(qa_pairs),
            "duplicates": find_duplicates(qa_pairs),
            "quality_issues": find_quality_issues(qa_pairs)
        }
    
        return report
    
    def check_completeness(qa_pairs: List[Dict]) -> Dict:
        """완전성 검증: 필수 필드 존재 여부"""
        required_fields = ['id', 'question', 'expected_answer', 'context']
    
        incomplete = []
        for qa in qa_pairs:
            missing = [f for f in required_fields if not qa.get(f)]
            if missing:
                incomplete.append({
                    "id": qa.get('id', 'unknown'),
                    "missing_fields": missing
                })
    
        return {
            "complete_rate": (len(qa_pairs) - len(incomplete)) / len(qa_pairs),
            "incomplete_pairs": incomplete
        }
    
    def check_consistency(qa_pairs: List[Dict]) -> Dict:
        """일관성 검증: 포맷, 길이, 스타일"""
        issues = []
    
        for qa in qa_pairs:
            # Question이 너무 짧거나 길 경우
            q_len = len(qa.get('question', ''))
            if q_len < 10:
                issues.append({
                    "id": qa['id'],
                    "issue": "question_too_short",
                    "length": q_len
                })
            elif q_len > 500:
                issues.append({
                    "id": qa['id'],
                    "issue": "question_too_long",
                    "length": q_len
                })
    
            # Expected Answer가 비어있거나 너무 짧은 경우
            ans_len = len(qa.get('expected_answer', ''))
            if ans_len < 5:
                issues.append({
                    "id": qa['id'],
                    "issue": "answer_too_short",
                    "length": ans_len
                })
    
        return {
            "consistency_rate": (len(qa_pairs) - len(issues)) / len(qa_pairs),
            "issues": issues
        }
    
    def find_duplicates(qa_pairs: List[Dict]) -> List[Dict]:
        """중복 데이터 탐지"""
        seen = {}
        duplicates = []
    
        for qa in qa_pairs:
            q = qa['question'].strip().lower()
            if q in seen:
                duplicates.append({
                    "duplicate_id": qa['id'],
                    "original_id": seen[q]
                })
            else:
                seen[q] = qa['id']
    
        return duplicates
    
    def find_quality_issues(qa_pairs: List[Dict]) -> List[Dict]:
        """품질 문제 탐지"""
        issues = []
    
        for qa in qa_pairs:
            # Question에 오타/문법 오류 가능성 (간단한 휴리스틱)
            question = qa.get('question', '')
            if '??' in question or '!!' in question:
                issues.append({
                    "id": qa['id'],
                    "issue": "potential_typo",
                    "field": "question"
                })
    
            # Expected Answer가 Question과 너무 유사 (복사 오류 가능성)
            answer = qa.get('expected_answer', '')
            if question and answer and question.lower() == answer.lower():
                issues.append({
                    "id": qa['id'],
                    "issue": "question_answer_identical"
                })
    
        return issues
    
    # 실행 예시
    if __name__ == "__main__":
        report = validate_golden_dataset("golden_qa_pairs.json")
    
        print("=== Golden Dataset 품질 검증 보고서 ===")
        print(f"전체 QA Pairs: {report['total_pairs']}개")
        print(f"완전성: {report['completeness']['complete_rate']:.1%}")
        print(f"일관성: {report['consistency']['consistency_rate']:.1%}")
        print(f"중복: {len(report['duplicates'])}개")
        print(f"품질 이슈: {len(report['quality_issues'])}개")
    
        # 불완전한 데이터 출력
        if report['completeness']['incomplete_pairs']:
            print("\n❌ 불완전한 QA Pairs:")
            for pair in report['completeness']['incomplete_pairs'][:5]:
                print(f"  - {pair['id']}: 누락 필드 {pair['missing_fields']}")
    
        # 중복 데이터 출력
        if report['duplicates']:
            print("\n⚠️ 중복 QA Pairs:")
            for dup in report['duplicates'][:5]:
                print(f"  - {dup['duplicate_id']} (원본: {dup['original_id']})")
    
```

#### 7.3.3 Golden Dataset 개선 프로세스

단계 | QA 활동 | 도구 | 산출물  
---|---|---|---  
1️⃣ 현황 분석 | 품질 검증 스크립트 실행, 이슈 식별 | validate_golden_dataset.py | 품질 보고서  
2️⃣ 우선순위화 | Critical 이슈 선별, 개선 계획 수립 | Dashboard 필터링 | 개선 백로그  
3️⃣ 데이터 편집 | Dashboard에서 이슈 항목 수정 | Streamlit "📝 데이터 편집" | 수정된 Dataset  
4️⃣ 검증 | 재평가 실행, 품질 지표 비교 | Dashboard "📊 메트릭" | 검증 보고서  
5️⃣ 승인 | 팀 리뷰, 변경 이력 문서화 | Git commit + PR | 승인된 Dataset  
  
### 7.4 임계값 검증 워크플로우

#### 7.4.1 임계값 변경 전 영향 분석
```python
    #!/usr/bin/env python3
    """임계값 변경 영향 분석 스크립트"""
    import json
    from typing import Dict, List
    
    def analyze_threshold_impact(
        evaluation_results: List[Dict],
        current_thresholds: Dict[str, float],
        proposed_thresholds: Dict[str, float]
    ) -> Dict:
        """임계값 변경 시 통과율 영향 분석"""
    
        current_pass = []
        proposed_pass = []
    
        for result in evaluation_results:
            # 현재 임계값 기준 통과 여부
            current_passed = all(
                result['metrics'].get(metric, 0) >= threshold
                for metric, threshold in current_thresholds.items()
            )
            current_pass.append(current_passed)
    
            # 제안된 임계값 기준 통과 여부
            proposed_passed = all(
                result['metrics'].get(metric, 0) >= threshold
                for metric, threshold in proposed_thresholds.items()
            )
            proposed_pass.append(proposed_passed)
    
        # 영향 받는 케이스 식별
        affected = []
        for i, result in enumerate(evaluation_results):
            if current_pass[i] != proposed_pass[i]:
                affected.append({
                    "id": result['id'],
                    "current": "PASS" if current_pass[i] else "FAIL",
                    "proposed": "PASS" if proposed_pass[i] else "FAIL",
                    "metrics": result['metrics']
                })
    
        return {
            "current_pass_rate": sum(current_pass) / len(current_pass),
            "proposed_pass_rate": sum(proposed_pass) / len(proposed_pass),
            "affected_count": len(affected),
            "affected_cases": affected
        }
    
    # 사용 예시
    if __name__ == "__main__":
        # 평가 결과 로드
        with open("evaluation_results.json", 'r') as f:
            results = json.load(f)
    
        # 현재 vs 제안 임계값
        current = {
            "task_completion_rate": 0.85,
            "accuracy": 0.80
        }
    
        proposed = {
            "task_completion_rate": 0.90,  # 5% 상향
            "accuracy": 0.75  # 5% 하향
        }
    
        # 영향 분석
        impact = analyze_threshold_impact(results, current, proposed)
    
        print("=== 임계값 변경 영향 분석 ===")
        print(f"현재 통과율: {impact['current_pass_rate']:.1%}")
        print(f"제안 통과율: {impact['proposed_pass_rate']:.1%}")
        print(f"변화: {impact['proposed_pass_rate'] - impact['current_pass_rate']:+.1%}")
        print(f"영향 받는 케이스: {impact['affected_count']}개")
    
        # 영향 받는 케이스 출력
        if impact['affected_cases']:
            print("\n영향 받는 케이스 (최대 5개):")
            for case in impact['affected_cases'][:5]:
                print(f"  - {case['id']}: {case['current']} → {case['proposed']}")
                print(f"    메트릭: {case['metrics']}")
    
```

#### 7.4.2 임계값 검증 체크리스트

검증 항목 | 확인 방법 | 합격 기준 | 담당자  
---|---|---|---  
✅ 영향 분석 완료 | analyze_threshold_impact.py 실행 | 통과율 변화 < 20% | QA Manager  
✅ 비즈니스 정렬 | PM과 목표 확인 | 비즈니스 목표와 일치 | QA + PM  
✅ 히스토리 백업 | 현재 임계값 Git commit | 백업 완료 | QA Manager  
✅ 팀 공지 | Slack/Email 공지 | 전체 팀원 인지 | QA Manager  
✅ 모니터링 설정 | Dashboard 알림 설정 | 알림 테스트 성공 | QA Manager  
  
### 7.5 정기 데이터 품질 리뷰

#### 7.5.1 주간 품질 리뷰 체크리스트

리뷰 항목 | 확인 내용 | 도구/방법 | Action 조건  
---|---|---|---  
📊 메트릭 트렌드 | 전주 대비 메트릭 변화 | Dashboard "📈 트렌드" | 변화 > 10% → 원인 분석  
❌ 실패 케이스 | 반복 실패 패턴 | Dashboard "📊 Test 투명성" | 3회 이상 실패 → 데이터 검토  
📝 편집 이력 | 데이터 편집 빈도 및 사유 | 편집 로그 | 편집 > 10건/주 → 프로세스 개선  
⚙️ 임계값 위반 | 임계값 아래 메트릭 | Dashboard 알림 | 위반 발생 → 즉시 조치  
  
#### 7.5.2 월간 품질 리뷰 프로세스

단계 | 활동 | 산출물 | 참석자  
---|---|---|---  
1️⃣ 데이터 수집 | 월간 메트릭, 편집 이력, 이슈 수집 | 월간 품질 보고서 초안 | QA Manager  
2️⃣ 분석 | 트렌드 분석, 근본 원인 분석 | 인사이트 및 개선 제안 | QA Team  
3️⃣ 리뷰 미팅 | 보고서 발표, 토론, 액션 아이템 도출 | 액션 아이템 리스트 | QA, PM, Dev Lead  
4️⃣ 액션 | 개선 작업 할당 및 추적 | JIRA 티켓 | 담당자들  
5️⃣ Follow-up | 액션 아이템 완료 확인 | 완료 보고서 | QA Manager  
  
#### 7.5.3 월간 품질 보고서 템플릿
```python
    # 월간 Golden Dataset 품질 보고서
    **기간**: 2025년 11월 1일 ~ 11월 30일
    **작성자**: QA Manager
    **작성일**: 2025년 12월 1일
    
    ## 📊 Executive Summary
    - **전체 통과율**: 87.5% (전월 대비 +2.3%)
    - **Golden Dataset 크기**: 250개 QA Pairs (+15개)
    - **데이터 편집**: 8건 (품질 개선)
    - **임계값 변경**: 1건 (Accuracy 0.80 → 0.75)
    
    ## 📈 메트릭 트렌드
    | 메트릭 | 10월 평균 | 11월 평균 | 변화 | 상태 |
    |--------|----------|----------|------|------|
    | Task Completion Rate | 0.84 | 0.88 | +4.8% | ✅ 개선 |
    | Accuracy | 0.82 | 0.85 | +3.7% | ✅ 개선 |
    | Response Time | 3.2s | 3.5s | +9.4% | ⚠️ 주의 |
    | Hallucination Rate | 0.08 | 0.06 | -25% | ✅ 개선 |
    
    ## 🎯 주요 성과
    1. **Golden Dataset 품질 개선**: 15개 신규 QA Pairs 추가, 품질 검증 완료
    2. **임계값 최적화**: Accuracy 임계값 조정으로 통과율 5% 향상
    3. **프로세스 자동화**: 품질 검증 스크립트 도입으로 검증 시간 50% 단축
    
    ## ❌ 주요 이슈
    1. **Response Time 증가**: 복잡한 쿼리 증가로 평균 응답 시간 9.4% 상승
       - **원인**: Multi-hop reasoning 케이스 증가
       - **액션**: 성능 최적화 작업 (JIRA-1234)
    
    2. **반복 실패 케이스**: 5개 케이스가 3회 이상 실패
       - **원인**: 기대 답변 모호성
       - **액션**: QA Pairs 편집 완료
    
    ## 💡 개선 제안
    1. **Golden Dataset 확장**: 엣지 케이스 30개 추가 (Q1 2026)
    2. **자동 알림 강화**: 임계값 위반 시 Slack 알림 설정
    3. **정기 리뷰 주기 변경**: 월간 → 격주 (더 빠른 피드백)
    
    ## 📋 Next Month 목표
    - [ ] Golden Dataset 300개로 확장
    - [ ] Response Time 평균 3.0s 이하 달성
    - [ ] 자동 품질 검증 커버리지 100%
    
```

#### 7.5.4 품질 리뷰 모범 사례

  * **✅ 데이터 기반 의사결정** : 주관적 판단이 아닌 메트릭과 데이터로 품질 평가
  * **✅ 정기적 리뷰** : 주간/월간 정기 리뷰로 지속적 개선
  * **✅ 팀 협업** : QA, PM, Dev가 함께 품질 목표 설정 및 달성
  * **✅ 투명성** : 모든 변경 이력을 기록하고 공유
  * **✅ 자동화** : 반복 작업은 스크립트로 자동화하여 효율성 향상
  * **✅ 롤백 준비** : 언제든 이전 상태로 복구 가능하도록 백업 유지

## 결론

이 가이드에서 제시한 데이터 편집 및 Test 투명성 기능은 다음과 같은 이점을 제공합니다:

### 데이터 편집 기능의 이점

  1. **효율성** : UI에서 직접 데이터 수정, 빠른 반복
  2. **안전성** : 자동 백업 및 롤백, 변경 이력 추적
  3. **협업** : 편집자와 이유 기록, 팀 협업 지원
  4. **유연성** : TaskResult, Golden Dataset, 임계값 모두 편집 가능

### Test 투명성 기능의 이점

  1. **신뢰성** : 메트릭 계산 과정 투명하게 공개
  2. **디버깅** : 문제 발생 시 원인 빠르게 파악
  3. **협업** : 주석으로 의견 공유 및 논의
  4. **추적성** : 모든 평가 활동 Audit Log로 기록

### 다음 단계

  1. **Dashboard 통합** : `streamlit_dashboard.py`에 이 UI 추가
  2. **자동화** : CI/CD 파이프라인에 평가 및 알림 통합
  3. **확장** : 커스텀 메트릭 및 주석 유형 추가
  4. **최적화** : 대용량 데이터 처리 성능 개선

* * *

## 검증 완료 및 개선 사항 요약

### 검증 결과

이 문서는 실제 구현 파일과 비교하여 검증되었습니다:

  * ✅ **data_editor_manager.py** : 모든 클래스 메서드와 데이터 구조 확인
  * ✅ **test_transparency_manager.py** : 투명성 기능 및 고급 분석 메서드 확인
  * ✅ **dashboard_data_editor.py** : UI 컴포넌트 및 워크플로우 확인

### 주요 개선 사항 (2024.11.30)

#### 1\. DataEditorManager 클래스 메서드 명확화

  * 모든 주요 메서드에 대한 정확한 시그니처 추가
  * 자동 백업 및 편집 기록 생성 명시
  * Layer 2 필드 (Agentic + Security 메트릭) 지원 문서화
  * Test 구성 관리 (Phase 3) 추가

#### 2\. TestTransparencyManager 클래스 메서드 명확화

  * 메트릭 계산 추적 프로세스 상세화
  * 주석(Annotation) 시스템 구조 명확화
  * Audit Log 구조 및 저장 위치 추가
  * **5가지 고급 분석 기능 추가** : 
    * 이상치 탐지 (Anomaly Detection)
    * 상관관계 분석 (Correlation Analysis)
    * 성능 병목 지점 식별 (Performance Bottlenecks)
    * 데이터 품질 검증 (Data Quality Validation)
    * 실행 가능한 개선 방안 (Actionable Insights)

#### 3\. 데이터 구조 문서화

  * 모든 `@dataclass` 구조 명시 (DataEdit, DataVersion, TestStep, MetricCalculationTrace, Annotation, AuditLogEntry, TransparentEvaluationReport)
  * ID 생성 패턴 (YYYYMMDD_HHMMSS_ffffff)
  * 파일 저장 위치 및 명명 규칙

#### 4\. 버전 관리 시스템

  * `_create_version` 메서드가 save 시 자동 호출됨을 명시
  * 버전 ID 형식 및 저장 위치 추가
  * 롤백 프로세스 상세화

#### 5\. Test 구성 관리 (Phase 3)

  * 환경별 Test 구성 저장 및 재사용 기능 추가
  * Enhanced Metadata 지원 (environment, tags, model_config, framework, version)
  * 복수 Golden Dataset 지원

### 개발자를 위한 핵심 정보

#### 자동화된 기능

다음 기능들은 **자동으로 실행** 되므로 개발자가 직접 호출할 필요가 없습니다:

  * ✅ 버전 백업 (`save_*` 메서드 호출 시 자동)
  * ✅ 편집 기록 (`_record_edit` 자동 호출)
  * ✅ Audit Log (주석 추가/수정 시 자동)
  * ✅ 메트릭 설명 생성 (`_generate_explanation` 자동)

#### 파일 저장 위치 요약
```
    evaluation_results/
    ├── versions/                    # 버전 백업
    │   └── version_{timestamp}_{filename}.json
    ├── edit_history/                # 편집 기록
    │   └── edit_{edit_id}.json
    ├── traces/                      # 메트릭 계산 추적
    │   └── trace_{metric_name}_{task_id}.json
    ├── annotations/                 # 주석
    │   └── annotation_{annotation_id}.json
    ├── audit_logs/                  # Audit Log
    │   └── audit_{log_id}.json
    ├── test_configs/                # Test 구성
    │   └── test_config_{timestamp}.json
    ├── thresholds.json              # 임계값
    ├── advanced_eval_config.json    # 고급 평가 설정
    └── performance_data.json        # TaskResult 데이터
```

#### 메서드 호출 순서 (투명한 평가)

  1. **Test 구성 준비**
``` [](<#cb46-1>)config = manager.create_test_configuration(...)
```

  2. **메트릭 계산 추적**
``` [](<#cb47-1>)trace_id = transparency.start_metric_calculation(...)
         [](<#cb47-2>)transparency.add_calculation_step(...)
         [](<#cb47-3>)transparency.complete_metric_calculation(...)
```

  3. **주석 추가 (선택)**
``` [](<#cb48-1>)annotation_id = transparency.add_annotation(...)
```

  4. **리포트 생성**
``` [](<#cb49-1>)report = transparency.generate_transparent_report(...)
```

  5. **고급 분석 (Phase 3)**
``` [](<#cb50-1>)anomalies = transparency.analyze_metric_anomalies(monitor)
         [](<#cb50-2>)insights = transparency.generate_actionable_insights(monitor)
```

* * *

**Agent Evaluator** \- 투명하고 편집 가능한 AI Agent 평가 🔬✨

* * *

**최종 업데이트** : 2026-03-17
**버전** : Agent Evaluator v0.5.2
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System  
**검증 완료** : data_editor_manager.py, test_transparency_manager.py, dashboard_data_editor.py
