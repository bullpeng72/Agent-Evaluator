# 📊 대시보드 가이드

Streamlit 기반 시각화 및 데이터 관리 (Agent Evaluator v0.5.0)

# Streamlit 대시보드 가이드

> 📊 Agent Evaluator 대시보드 완벽 활용 가이드

이 문서는 Streamlit 기반 대시보드의 모든 기능과 활용 방법을 상세히 설명합니다.

## 빠른 시작
[code] 
    [](<#cb1-1>)# 메인 대시보드 (평가 결과 분석)
    [](<#cb1-2>)streamlit run streamlit_dashboard.py
    [](<#cb1-3>)
    [](<#cb1-4>)# 데이터 편집 대시보드 (테스트 설정)
    [](<#cb1-5>)streamlit run dashboard_data_editor.py --server.port 8503
[/code]

## 대시보드 구성

Agent Evaluator는 **2개의 독립적인 대시보드** 를 제공합니다:

### 1\. 메인 대시보드 (`streamlit_dashboard.py`)

**평가 결과 분석 및 시각화**

**12개의 주요 탭으로 구성 ():**

  * **📊 Overview** : 전체 성능 요약 (TCR, 정확도, 품질, 환각률, 비용 등)
  * **📈 Layer 1: Basic** : 기본 성능 지표 (TCR, Accuracy, Hallucination, Quality + RAG 메트릭)
  * **🔒 Layer 1: Security** : 기본 보안 지표 (Input Sanitization, Output Leakage, Authorization)
  * **🤖 Layer 2: Agentic** : 에이전트 특화 지표 (Tool Selection, Tool Efficiency, Multi-Agent, Workflow)
  * **🛡️ Layer 2: Security** : 에이전트 보안 지표 (Privilege Escalation, Attack Detection)
  * **🔬 Layer 3: Advanced** : 고급 평가 지표 (DeepEval, Ragas)
  * **🚨 Integrated Security** : 통합 보안 대시보드 (Risk Scoring, Alerts, Recommendations)
  * **💡 Insights** : 데이터 기반 인사이트 (Alerts, Recommendations, Task Explorer)
  * **🔍 Test 투명성** : 평가 과정 추적 및 감사 (Traces, Annotations, Audit Log)
  * **📚 지표 설명** : 모든 메트릭에 대한 상세 설명 (Layer 1, 2, 3 Metrics Glossary)
  * **📦 Export** : 리포트 생성 및 투명성 정보 (HTML, CSV, JSON)
  * **⚙️ Settings** : 대시보드 설정 및 구성 (파일 정보, 보안 설정, 시스템 정보)

### 2\. 데이터 편집 대시보드 (`dashboard_data_editor.py`)

**테스트 설정 및 데이터 관리**

2개의 메인 탭으로 구성: - **📝 데이터 편집** : Golden Dataset 생성, 임계값 설정, 테스트 준비, 이력 관리 - **🔬 Test 투명성** : 평가 과정 추적 및 감사

## 목차

  * [1\. 대시보드 시작하기](<#대시보드-시작하기>)
  * [2\. 사이드바 설정](<#사이드바-설정>)
  * [3\. 메인 대시보드 탭별 기능](<#메인-대시보드-탭별-기능>)
  * [4\. 데이터 편집 대시보드](<#데이터-편집-대시보드>)
  * [5\. 고급 활용법](<#고급-활용법>)
  * [6\. 문제 해결](<#문제-해결>)
  * [📊 품질 관리자 가이드 (QA Manager)](<#qa-guide>)
    * [8.1 Dashboard를 통한 품질 모니터링](<#qa-monitoring>)
    * [8.2 임계값 기반 품질 관리](<#qa-threshold>)
    * [8.3 배포 전 품질 검증](<#qa-release>)
    * [8.4 문제 탐지 및 분석](<#qa-troubleshooting>)
    * [8.5 정기 품질 리뷰](<#qa-review>)
  * [🛠️ 운영자 가이드 (Operations)](<#ops-guide>)
    * [9.1 Dashboard 설치 및 구성](<#ops-setup>)
    * [9.2 일상 운영 작업](<#ops-daily>)
    * [9.3 시스템 모니터링](<#ops-monitoring>)
    * [9.4 운영 트러블슈팅](<#ops-troubleshooting>)
    * [9.5 유지보수 및 업그레이드](<#ops-maintenance>)

* * *

## 1\. 대시보드 시작하기

### 1.1 실행 방법

#### 메인 대시보드 (평가 결과 분석)
[code] 
    [](<#cb2-1>)# 기본 실행
    [](<#cb2-2>)streamlit run streamlit_dashboard.py
    [](<#cb2-3>)
    [](<#cb2-4>)# 포트 지정
    [](<#cb2-5>)streamlit run streamlit_dashboard.py --server.port 8502
    [](<#cb2-6>)
    [](<#cb2-7>)# 자동 새로고침 비활성화
    [](<#cb2-8>)streamlit run streamlit_dashboard.py --server.runOnSave false
[/code]

#### 데이터 편집 대시보드 (테스트 설정 및 관리)
[code] 
    [](<#cb3-1>)# 데이터 편집 및 테스트 설정
    [](<#cb3-2>)streamlit run dashboard_data_editor.py
    [](<#cb3-3>)
    [](<#cb3-4>)# 포트 지정 (메인 대시보드와 동시 실행 가능)
    [](<#cb3-5>)streamlit run dashboard_data_editor.py --server.port 8503
[/code]

### 1.2 첫 화면

대시보드 실행 시 다음 URL로 자동 접속됩니다:
[code] 
    메인 대시보드: http://localhost:8501
    데이터 편집: http://localhost:8502 (포트 지정 시)
[/code]

**메인 대시보드 초기 화면 구성**

  * 🎨 **헤더:** Agent Evaluator 로고 및 제목
  * 📊 **사이드바:** 데이터 로드 및 설정
  * 🔄 **메인 영역:** 12개 탭 
    * 📊 Overview
    * 📈 Layer 1: Basic
    * 🔒 Layer 1: Security
    * 🤖 Layer 2: Agentic
    * 🛡️ Layer 2: Security
    * 🔬 Layer 3: Advanced
    * 🚨 Integrated Security
    * 💡 Insights
    * 🔍 Test 투명성
    * 📚 지표 설명
    * 📦 Export

**데이터 편집 대시보드 초기 화면 구성** \- 📝 데이터 편집 탭: Golden Dataset, 임계값 설정, 테스트 준비 - 🔬 Test 투명성 탭: 평가 과정 추적 및 감사

### 1.3 데이터 준비

대시보드를 사용하려면 먼저 데이터가 필요합니다.

**방법 1: 데모 데이터 생성** 1\. 사이드바에서 "🎲 데모 데이터 생성" 버튼 클릭 2. 100개의 샘플 작업이 자동 생성됨 3. 즉시 대시보드에서 확인 가능

**방법 2: 실제 평가 데이터 로드** 1\. 평가 코드 실행하여 JSON 파일 생성 `python monitor.save_to_file("my_evaluation.json")` 2\. 사이드바의 “📂 실제 평가 데이터” 섹션에서 파일 선택 3. “📥 실제 데이터 로드” 버튼 클릭

**방법 3: 예제 실행**
[code] 
    [](<#cb5-1>)# 기본 예제
    [](<#cb5-2>)python Evaluator_Examples/level_1_foundation/01_quickstart.py
    [](<#cb5-3>)
    [](<#cb5-4>)# 평가 결과가 Dashboard/data/evaluation_results/ 디렉토리에 자동 저장됨
    [](<#cb5-5>)# 대시보드에서 자동으로 인식 (Zero Configuration)
[/code]

* * *

## 2\. 사이드바 설정

### 2.1 데이터 관리

#### 데모 데이터 생성
[code] 
    🎲 데모 데이터 생성
[/code]

  * 클릭 시 100개의 샘플 작업 생성
  * 10가지 작업 유형 골고루 분포
  * 리얼리스틱한 메트릭 값

#### 실제 평가 데이터
[code] 
    📂 실제 평가 데이터
    ✅ 발견된 평가 데이터: N개
    
    로드할 파일 선택
    ├─ example1_deepeval_comprehensive.json (Agent 평가 - 2024-11-26 23:00:41)
    ├─ example2_ragas_comprehensive.json (Agent 평가 - 2024-11-26 23:00:43)
    └─ ...
    
    📥 실제 데이터 로드
[/code]

**파일 선택 드롭다운** \- 파일명과 생성 시간 표시 - 최신 파일이 먼저 표시 - 파일 유형 자동 감지 (Agent 평가 / RAG 평가)

**로드 과정** 1\. 드롭다운에서 파일 선택 2. “실제 데이터 로드” 버튼 클릭 3. 로딩 스피너 표시 4. 성공 시 “✅ 파일명 로드 완료!” 메시지 5. 자동으로 대시보드 새로고침

#### 데이터 초기화
[code] 
    🔄 데이터 초기화
[/code]

  * 모든 작업 데이터 삭제
  * Monitor 새로 생성
  * 깨끗한 상태로 시작

### 2.2 가격 설정
[code] 
    💰 토큰 가격 설정
    
    입력 토큰 ($/1K 토큰)
    [0.0030]
    
    출력 토큰 ($/1K 토큰)
    [0.0150]
[/code]

**일반적인 모델 가격**

모델 | 입력 | 출력  
---|---|---  
GPT-4o | $0.0025 | $0.0100  
GPT-4o-mini | $0.00015 | $0.0006  
GPT-4 Turbo | $0.0100 | $0.0300  
Claude 3.5 Sonnet | $0.0030 | $0.0150  
  
**가격 변경 방법** 1\. 입력/출력 토큰 가격 입력 2. Enter 또는 필드 외부 클릭 3. 자동으로 비용 재계산

* * *

## 3\. 메인 대시보드 탭별 기능

메인 대시보드는 **12개의 주요 탭** 으로 구성되어 있으며, 각 탭은 평가 결과의 특정 측면을 심도있게 분석합니다.

**✨ 업데이트:**

  * Layer 1 (Basic/Security), Layer 2 (Agentic/Security) 분리
  * 통합 보안 대시보드(Integrated Security) 추가
  * 보안 리스크 스코어링 및 알림 시스템

### 3.1 📊 Overview 탭

전체 성능을 한눈에 파악할 수 있는 종합 대시보드입니다.

#### 전체 요약

상단에 주요 메트릭 4개를 한눈에 표시:

총 Task 수 | 성공률 | 작업 완료율 (TCR) | 평균 실행 시간  
---|---|---|---  
**100** | **92.5%** | **92.5%** | **2.3초**  
평가 작업 수 | 성공한 비율 | 완료 점수 | 작업당 시간  
  
#### 섹션별 요약

Overview 탭은 5개의 주요 섹션으로 구성:

**1\. 🎯 Core Metrics (기본 성능 지표)** \- TCR (작업 완료율) - 정확도 (Accuracy) - 응답 품질 (Quality) - 환각 발생률 (Hallucination)

**2\. ⚡ Performance (효율성 지표)** \- 평균 응답 시간 - 평균 토큰 사용량 - 총 비용 - Task당 비용

**3\. 🤖 Agentic AI (에이전트 특화 지표)** \- 도구 선택 정확도 - 에이전트 협업 점수 - 워크플로우 성공률 - 재시도 후 성공률

**4\. 🔬 Advanced Metrics (고급 평가 지표)** \- G-Eval (DeepEval) - Hallucination (DeepEval) - Faithfulness (Ragas) - Ragas Overall Score

**5\. 🎯 임계값 비교 (설정된 경우)** \- 통과/경고/미달 항목 요약 - 각 메트릭의 임계값 대비 상태

#### 성능 추세 차트
[code] 
    📈 시간별 TCR 및 정확도 추세
    [꺾은선 그래프]
    - X축: 시간 (또는 작업 순서)
    - Y축: 백분율
    - 파란선: TCR
    - 빨간선: 정확도
[/code]

**차트 기능** \- 🔍 줌: 드래그하여 확대 - 📸 다운로드: 우측 상단 카메라 아이콘 - 🔄 리셋: 더블클릭 - 🎯 호버: 정확한 값 표시

#### 작업 유형별 분포
[code] 
    📊 작업 유형 분포
    [파이 차트]
    - QA: 35%
    - 코드 생성: 20%
    - 데이터 분석: 15%
    - ...
[/code]

**인사이트** \- 가장 많이 수행된 작업 유형 확인 - 각 유형별 성능 비교 가능 - 불균형 감지

### 3.2 📈 Layer 1: Basic 탭

기본 성능 지표를 상세히 분석하는 탭으로, 8개의 서브탭으로 구성되어 있습니다.

#### 서브탭 구성

Layer 1: Basic 탭은 다음 8개의 서브탭으로 구성됩니다:

  1. **📋 Task Completion (작업 완료율)** \- TCR 상세 분석 및 작업 유형별 성공률
  2. **✅ Accuracy (정확도)** \- 정확도 메트릭 상세 분석
  3. **🎨 Quality (품질)** \- 응답 품질 평가 (5가지 차원: Completeness, Coherence, Factual Accuracy, Relevance, Structure)
  4. **🚫 Hallucination (환각)** \- 환각 탐지율 및 발생 패턴 분석

> 💡 **참고** : RAG 메트릭 (Faithfulness, Answer Relevancy, Context Recall, Context Precision)은 **🔬 Advanced 탭** 의 Ragas 섹션에서 확인하실 수 있습니다.

#### 서브탭 1: TCR (작업 완료율)
[code] 
    📊 작업 완료율 (Task Completion Rate)
    
    전체 TCR        성공한 작업      전체 작업      벤치마크 등급
      92.5%           92개           100개          우수
[/code]

**TaskType별 완료율** \- 막대 그래프: 각 작업 유형별 TCR 시각화 - 데이터 테이블: TaskType, TCR (%), 성공, 전체

#### 서브탭 2: Accuracy (정확도)
[code] 
    🎯 정확도 (Accuracy)
    
    전체 정확도    높은 정확도(≥90%)   낮은 정확도(<70%)   평균 정확도
      88.3%            75개              10개              88.3%
[/code]

**TaskType별 정확도** \- 막대 그래프: 각 작업 유형별 정확도 분포 - 색상 스케일: 낮음(밝음) → 높음(진함)

#### 서브탭 3: Hallucination (환각)
[code] 
    🚨 환각 탐지 (Hallucination Detection)
    
    환각 발생률     검사한 응답     플래그된 응답    안전 등급
      2.5%          98개           2개          안전
      ↓ 낮을수록 좋음
[/code]

**환각 탐지 설명**
[code] 
    환각(Hallucination)은 AI가 사실이 아니거나 제공되지 않은 정보를 생성하는 현상입니다.
    
    - 낮음 (<5%): 매우 안전한 수준
    - 보통 (5-10%): 주의 필요
    - 높음 (>10%): 개선 필요
    
    환각률이 높다면 프롬프트 개선이나 검증 메커니즘 추가를 권장합니다.
[/code]

#### 서브탭 4: Quality (품질)
[code] 
    ⭐ 응답 품질 (Response Quality)
    
    평균 품질      최고 품질      최저 품질      고품질 응답(≥8)
      8.2/10        10/10         5.0/10          65개
[/code]

**품질 점수 분포** \- 도넛 차트: 품질 범위별 분포 (0-4, 4-6, 6-8, 8-10)

#### 서브탭 5-8: RAG 메트릭

각 서브탭은 다음 구조로 표시:

  * **설명** : 메트릭의 의미 설명 (faithfulness, answer_relevancy, context_recall, context_precision)
  * **통계** : 평균, 최대, 최소 값 - faithfulness (충실도), answer_relevancy (답변 관련성) 등
  * **분포 차트** : 히스토그램으로 값 분포 시각화

**활성화 조건** :
[code] 
    [](<#cb17-1>)# RAG 메트릭을 사용하려면 평가 시 다음을 활성화:
    [](<#cb17-2>)monitor.record_task(
    [](<#cb17-3>)    task,
    [](<#cb17-4>)    enable_advanced_metrics=True,
    [](<#cb17-5>)    input_text=question,
    [](<#cb17-6>)    output_text=answer,
    [](<#cb17-7>)    retrieved_context=context  # RAG 메트릭에 필요
    [](<#cb17-8>))
[/code]

### 3.3 ⚡ Performance 탭

효율성 지표를 분석하는 탭으로, 3개의 서브탭으로 구성되어 있습니다.

#### 서브탭 구성

  1. **⏱️ 응답 시간 (Latency)** \- 실행 시간 분석
  2. **💰 비용 & 토큰 (Cost & Tokens)** \- 토큰 사용 및 비용 분석
  3. **🔄 재시도 성공 (Retry Success)** \- 재시도 메커니즘 효율성

💡 **참고:** 도구 효율성(Tool Efficiency) 지표는 🤖 Layer 2: Agentic 탭으로 이동했습니다.

#### 서브탭 1: ⏱️ 응답 시간 (Latency)
[code] 
    ⏱️ 응답 시간 분석
    
    평균 응답 시간    P50 (중앙값)    P95           최대
       2.3초           2.1초         4.2초        6.8초
[/code]

**TaskType별 응답 시간** \- Box Plot: 각 작업 유형별 응답 시간 분포 및 아웃라이어 - 요약 테이블: TaskType별 평균, 중앙값, 최소, 최대

#### 서브탭 2: 💰 비용 & 토큰 (Cost & Tokens)
[code] 
    💰 비용 분석
    
    총 비용        Task당 비용    총 토큰 사용    Task당 평균 토큰
    $12.45         $0.0124       1,245,000       12,450
[/code]

**토큰 사용 상세**
[code] 
    Input 토큰     Output 토큰    Input 비율
     450,000        795,000        36.1%
[/code]

**비용 최적화 제안**

Task당 비용에 따라 자동으로 제안 제공:

  * **$0.05 이상** : ⚠️ 높음 - 프롬프트 최적화, 컨텍스트 제거, 더 작은 모델 검토
  * **$0.02 ~ $0.05** : 💡 적정 - 추가 최적화 가능
  * **$0.02 미만** : ✅ 효율적 - 매우 효율적인 비용 수준

#### 서브탭 3: 🔄 재시도 성공 (Retry Success)
[code] 
    🔄 재시도 성공률 분석
    
    재시도한 Task    재시도율    최종 성공률    수정 성공률
         125개        12.5%       98.7%         87.5%
[/code]

**상세 지표**
[code] 
    평균 시도 횟수    재시도 후 성공    1차 시도 성공률
         1.8회          110개             87.5%
[/code]

**재시도 횟수 분포**

시도 횟수 | Task 수  
---|---  
1회 | 875  
2회 | 95  
3회 | 25  
4회 이상 | 5  
  
**재시도 사유 분석**

재시도가 발생한 주요 원인:

  * **API 타임아웃** : 45% - 네트워크 지연 또는 느린 응답
  * **형식 오류** : 30% - 출력 형식 불일치
  * **검증 실패** : 15% - 결과 검증 기준 미달
  * **기타** : 10% - 기타 예외 상황

**권장사항**

재시도 성공률을 기반으로 한 개선 방향:

  * ✅ **우수 (95% 이상)** : 재시도 메커니즘이 효과적으로 작동하고 있습니다
  * ⚠️ **보통 (80-95%)** : 재시도 로직을 검토하고 실패 원인을 분석하세요
  * ❌ **개선 필요 ( <80%)**: 근본 원인을 해결하거나 재시도 전략을 재설계하세요

### 3.3 🔒 Layer 1: Security 탭

**기본 보안 지표** 를 분석하는 탭으로, 3개의 서브탭으로 구성되어 있습니다.

**✨ 신규 추가:** 보안 메트릭 완전 통합

#### 서브탭 구성

  1. **🛡️ Input Sanitization** \- 입력 검증 및 위험 감지
  2. **🔐 Output Leakage** \- 민감 정보 유출 방지
  3. **🔑 Authorization** \- 권한 검증 및 접근 제어

#### 🛡️ Input Sanitization

사용자 입력의 위험성을 검증하고 공격 패턴을 탐지합니다.
[code] 
    🛡️ 입력 검증 (Input Sanitization)
    
    총 입력    위험 감지    차단율    안전 등급
     100개      2개        2.0%      안전
[/code]

**탐지 패턴:**

  * SQL Injection 시도
  * XSS 공격 패턴
  * Command Injection
  * Path Traversal

#### 🔐 Output Leakage

AI 응답에서 민감 정보 유출 여부를 검사합니다.
[code] 
    🔐 출력 유출 방지 (Output Leakage)
    
    총 출력    유출 감지    유출률    보안 등급
     100개      0개        0.0%      안전
[/code]

**검사 항목:**

  * 개인정보(PII) 유출
  * API 키/토큰 노출
  * 내부 경로 노출
  * 시스템 정보 유출

#### 🔑 Authorization

권한 검증 및 접근 제어 메트릭입니다.
[code] 
    🔑 권한 검증 (Authorization)
    
    총 요청    권한 검증    거부율    정책 준수율
     100개      100개       3.0%      97.0%
[/code]

**상세 내용은[보안 메트릭 가이드](<SECURITY_METRICS_GUIDE.html>)를 참고하세요.**

### 3.4 🤖 Layer 2: Agentic 탭

에이전트 특화 지표를 분석하는 탭으로, 4개의 서브탭으로 구성되어 있습니다.

#### 서브탭 구성

  1. **🔧 Tool Selection** \- 도구 선택 정확도 (무엇을 선택했는가)
  2. **⚡ Tool Efficiency** \- 도구 실행 효율성 (얼마나 효율적으로 실행했는가)
  3. **🤝 Multi-Agent (CrewAI)** \- 다중 에이전트 협업 분석
  4. **🔀 Workflow (LangChain/LangGraph)** \- 워크플로우 체인/그래프 실행

💡 **참고:** 재시도(Retry) 지표는 ⚡ Performance 탭으로 이동했습니다.

#### 서브탭 1: 🔧 Tool Selection
[code] 
    🔧 도구 선택 정확도
    
    평균 정확도(F1)  정밀도(Precision)  재현율(Recall)  F1 Score
        92.3%           94.5%            90.2%        92.3%
[/code]

**상세 분석**
[code] 
    평가된 Task 수    정확한 선택    불필요한 도구
         100개           92개            8개
[/code]

**개선 제안**

도구 선택 정확도를 기반으로 한 자동 권장사항:

  * **정확도 < 90%**: 🔴 Agent에게 도구 설명 명확히 제공, Few-shot 예시 추가
  * **Precision < Recall**: 🟡 불필요한 도구 호출 많음 - 필요성 검증 단계 추가
  * **Recall < Precision**: 🟡 필요한 도구 누락 - Agent가 모든 옵션 고려하도록 개선
  * **정확도 ≥ 90%** : ✅ 우수한 도구 선택!

#### 서브탭 2: ⚡ Tool Efficiency
[code] 
    ⚡ 도구 실행 효율성
    
    총 도구 호출    성공률        효율성 점수    중복률
       1,234        95.5%         92.3%         3.2%
[/code]

**상세 지표**
[code] 
    Task당 평균 호출    평균 실행 시간    실패율
         3.2개            0.85초         4.5%
[/code]

**도구별 효율성 분석**

도구명 | 총 호출 | 성공률 | 평균 실행 시간  
---|---|---|---  
search | 450 | 97.8% | 0.52s  
calculator | 320 | 99.1% | 0.12s  
database_query | 264 | 92.4% | 1.45s  
api_call | 200 | 88.5% | 2.18s  
  
**최적화 제안**

시스템이 자동으로 문제를 감지하고 제안:

  * 🔴 **성공률 < 95%**: 도구 파라미터 검증, 에러 핸들링 개선
  * 🟡 **효율성 < 80%**: 중복 호출 제거, 도구 선택 로직 개선
  * 🟡 **중복률 > 10%**: 결과 캐싱, 동일 파라미터 호출 방지
  * 🟢 **평균 실행 시간 > 2초**: 비동기 호출, 타임아웃 설정

#### 서브탭 3: 🤝 Multi-Agent (CrewAI)
[code] 
    🤝 에이전트 협업 분석
    
    협업 점수      총 상호작용    성공률        평균 반응 시간
      8.5/10         245개        94.7%          1.2초
[/code]

**에이전트 간 상호작용 네트워크** \- 상호작용 매트릭스: 에이전트 간 통신 빈도 - 성공/실패 분석

**개선 제안**

  * **협업 점수 ≥ 8.0** : ✅ 에이전트 간 협업이 원활합니다
  * **협업 점수 6.0~8.0** : 🟡 일부 에이전트 간 통신 개선 필요
  * **협업 점수 < 6.0**: 🔴 에이전트 역할 재정의 및 통신 프로토콜 개선 필요

#### 서브탭 4: 🔀 Workflow (LangChain/LangGraph)
[code] 
    🔀 워크플로우 실행 분석
    
    워크플로우 성공률   총 실행 수    평균 노드 수    평균 실행 시간
         95.3%            450개         12.3개         3.2초
[/code]

**노드별 실행 통계**
[code] 
    노드 유형           실행 횟수    성공률    평균 시간
    Chain Node           1,234      97.8%     0.52s
    Conditional Node       456      95.2%     0.12s
    Parallel Node          234      93.6%     1.45s
    LLM Node               789      96.4%     2.18s
[/code]

**워크플로우 최적화 제안**

  * 🔴 **성공률 < 90%**: 실패 노드 확인, 에러 핸들링 강화
  * 🟡 **평균 실행 시간 > 5초**: 병렬 처리 검토, 불필요한 노드 제거
  * ✅ **성공률 ≥ 95%** : 워크플로우가 안정적으로 실행되고 있습니다

### 3.5 🛡️ Layer 2: Security 탭

**에이전트 보안 지표** 를 분석하는 탭으로, 2개의 서브탭으로 구성되어 있습니다.

**✨ 신규 추가:** 에이전트 특화 보안 메트릭

#### 서브탭 구성

  1. **🚨 Privilege Escalation** \- 권한 상승 시도 탐지
  2. **🎯 Attack Detection** \- Prompt Injection, Jailbreak 탐지

#### 🚨 Privilege Escalation

에이전트가 허용된 권한을 초과하여 작업을 수행하려는 시도를 탐지합니다.
[code] 
    🚨 권한 상승 탐지
    
    총 작업    시도 감지    차단 성공    차단율
     100개      1개         1개        100%
[/code]

#### 🎯 Attack Detection

Prompt Injection, Jailbreak 등 AI 공격 패턴을 탐지합니다.
[code] 
    🎯 공격 탐지
    
    총 입력    공격 감지    차단율    오탐률
     100개      3개        100%      0.5%
[/code]

**탐지 유형:**

  * Prompt Injection (프롬프트 인젝션)
  * Jailbreak Attempts (탈옥 시도)
  * Role Manipulation (역할 조작)
  * Context Poisoning (컨텍스트 오염)

**상세 내용은[보안 메트릭 가이드](<SECURITY_METRICS_GUIDE.html>)를 참고하세요.**

### 3.6 🔬 Layer 3: Advanced 탭

DeepEval과 Ragas 같은 고급 평가 메트릭을 표시합니다.

#### 프로바이더 표시

**📊 활성화된 평가 프로바이더**

✅ NATIVE | 🔬 DEEPEVAL | 📚 RAGAS  
---|---|---  
항상 표시 | 메트릭 있을 때 | 메트릭 있을 때  
  
#### DeepEval 지표

**🔬 DeepEval 지표**

지표 | G-Eval 점수 | 환각 탐지율 | 유해성 점수 | 편향 점수  
---|---|---|---|---  
**값** | 0.856 | 15.5% | 0.023 | 0.045  
**상태** | ✓ 양호 | ⚠️ 주의 (12/77) | ✓ 안전 | ✓ 공정  
  
**메트릭 설명** \- **G-Eval** : 0~1 ⬆ (높을수록 좋음) - **환각 탐지율** : AI 기반 환각 탐지 비율 ⬇ (낮을수록 좋음) - `hallucination_detected=True`인 작업의 비율 \- 탐지 수 / 전체 수 표시 - **참고** : 개별 작업의 `hallucination_score` (0~1, 높을수록 환각 없음)와는 별개 - **네이티브 환각 발생률과 차이** : AI 기반 (DeepEval) vs 규칙 기반 (네이티브) - **유해성** : 0~1 ⬇ (낮을수록 안전) - **편향** : 0~1 ⬇ (낮을수록 공정)

**상태 표시** \- 🟢 우수/안전/공정 - 🔵 양호/감시/경미 - 🟡 보통/경고 - 🔴 개선 필요/위험/심각

#### RAGAS 지표 (RAG 평가)

**📚 Ragas 지표 (RAG 평가)**

Faithfulness  
(컨텍스트 충실도) | Context Recall  
(검색 재현율) | Context Precision  
(검색 정밀도) | Answer Relevancy  
(답변 관련성)  
---|---|---|---  
**0.892** | **0.856** | **0.923** | **0.867**  
✓ 양호 | ✓ 양호 | ✓ 우수 | ✓ 양호  
  
* * *

**Ragas 전체 점수: 0.885** (Faithfulness, Context Recall, Context Precision, Answer Relevancy의 평균)

**RAGAS 지표 설명** \- Faithfulness: 컨텍스트 충실도 - Context Recall: 필요한 정보 포함 정도 - Context Precision: 관련 정보만 포함 - Answer Relevancy: 질문-답변 관련성

#### 작업별 고급 지표 상세
[code] 
    ▼ 🔍 Task별 상세 지표 보기
[/code]

Task ID | 유형 | G-Eval ⬆ | 환각 탐지 | 환각 점수 ⬆ | 유해성 ⬇ | 편향 ⬇ | Faithfulness ⬆  
---|---|---|---|---|---|---|---  
task_001 | QA | 0.92 | ✅ 없음 | 0.95 | 0.01 | 0.02 | N/A  
task_002 | RAG | 0.88 | ⚠️ 탐지 | 0.72 | 0.03 | 0.04 | 0.95  
… | … | … | … | … | … | … | …  
  
**컬럼 설명** \- **G-Eval** : 전반적인 품질 점수 (0~1, 높을수록 좋음) - **환각 탐지** : 플래그 (✅ 없음 / ⚠️ 탐지됨) - **환각 점수** : `hallucination_score` (0~1, 높을수록 환각 없음) - **유해성/편향** : 0~1 (낮을수록 좋음) - **Faithfulness** : RAGAS 컨텍스트 충실도 (0~1, 높을수록 좋음)
[code] 
    [다운로드 버튼: CSV로 내보내기]
[/code]

### 3.5 🚨 알림 탭

임계값을 벗어난 항목과 개선 제안을 표시합니다.

#### 알림 레벨별 표시
[code] 
    🚨 알림 (5)
    
    [Critical] 정확도가 65.5%입니다 (70% 기준 미달)
      작업 유형: 데이터 분석
      영향: 높음
      조치: 프롬프트 개선 필요
    
    [High] TCR이 70.8%입니다 (80% 기준 미달)
      영향: 중간
      조치: 에러 핸들링 강화
    
    [Medium] 평균 지연시간 4.2초 (3초 기준 초과)
      영향: 사용자 경험
      조치: 모델 최적화 고려
    
    [Low] 도구 효율성 88.5% (90% 기준 미달)
      영향: 낮음
      조치: 도구 선택 로직 검토
[/code]

**필터링**
[code] 
    레벨 필터: [전체] [Critical] [High] [Medium] [Low]
[/code]

#### 개선 제안
[code] 
    💡 개선 제안 (우선순위순)
    
    1. 🎯 데이터 분석 작업 정확도 향상
       현재: 65.5%
       목표: 80%+
       방법:
       - Few-shot 예제 추가
       - 출력 형식 명확히 지정
       - 검증 단계 추가
       예상 효과: +14.5%p
    
    2. ⚡ 지연시간 감소
       현재: 4.2초
       목표: 3초 이내
       방법:
       - GPT-4o → GPT-4o-mini 전환
       - 스트리밍 응답 활용
       - 캐싱 구현
       예상 효과: -1.5초
    
    3. 💰 비용 최적화
       현재: $0.0124/작업
       목표: $0.0100/작업
       방법:
       - 프롬프트 간소화
       - 배치 처리
       예상 효과: -19%
[/code]

### 3.6 📈 상세 분석 탭

심층 분석과 고급 시각화를 제공합니다.

#### 시간별 성능 추이
[code] 
    📊 시간별 성능 추이
    
    [다중 선 그래프]
    - TCR: 파란선
    - 정확도: 빨간선
    - 환각률: 노란선
    - 지연시간: 초록선
    
    X축: 시간 (1시간 단위)
    Y축: 값 (각 메트릭 별 스케일)
[/code]

**인사이트** \- 피크 시간대 식별 - 성능 저하 구간 감지 - 트렌드 분석

#### 작업 유형별 비교
[code] 
    📊 작업 유형별 메트릭 비교
    
    [레이더 차트]
            정확도
              /\
             /  \
    TCR ----/    \---- 품질
           /      \
          /        \
     지연시간 ---- 비용
[/code]

**활용** \- 각 작업 유형의 강약점 시각화 - 균형잡힌 최적화 목표 설정

#### 상관관계 분석

**📊 메트릭 간 상관관계 (히트맵)**

| TCR | 정확도 | 지연시간 | 비용  
---|---|---|---|---  
**TCR** | 1.0 | 0.8 | -0.3 | 0.2  
**정확도** | 0.8 | 1.0 | -0.2 | 0.3  
**지연시간** | -0.3 | -0.2 | 1.0 | 0.7  
**비용** | 0.2 | 0.3 | 0.7 | 1.0  
  
**인사이트:** \- 정확도 ↑ → TCR ↑ (강한 양의 상관관계 0.8) - 지연시간 ↑ → 비용 ↑ (중간 양의 상관관계 0.7) - 지연시간 ↑ → TCR ↓ (약한 음의 상관관계 -0.3)

#### 토큰 사용량 분석
[code] 
    📊 토큰 사용 패턴
    
    [적층 영역 차트]
    토큰 수
      600 |
      500 |     [출력 토큰]
      400 |  ███████████████
      300 |██████████████████
      200 |███████████████████
      100 |████████████████████
        0 |─────────────────────
          [입력 토큰]
    
    평균 입출력 비율: 1:1.5
    최적 비율 권장: 1:1.2 (비용 절감)
[/code]

### 3.7 🚨 Integrated Security 탭

**통합 보안 대시보드** 로, Layer 1과 Layer 2의 모든 보안 메트릭을 종합적으로 분석합니다.

**✨ 신규 추가:** 보안 리스크 스코어링 및 알림 시스템

#### 🎯 보안 리스크 점수
[code] 
    🛡️ 전체 보안 점수
    
    리스크 점수    리스크 등급    취약점 수    권장사항 수
       15/100       낮음 (안전)      2개         3개
[/code]

**리스크 등급:**

  * 🟢 **낮음 (0-30)** : 안전한 수준
  * 🟡 **중간 (31-60)** : 주의 필요
  * 🔴 **높음 (61-100)** : 즉시 조치 필요

#### 🚨 보안 알림

감지된 보안 이슈를 우선순위별로 표시합니다.

  * 🔴 **Critical** : 즉시 조치 필요
  * 🟡 **Warning** : 검토 필요
  * 🟢 **Info** : 참고 사항

#### 💡 보안 권장사항

AI 기반 보안 개선 제안을 자동으로 생성합니다.

**상세 내용은[보안 메트릭 가이드](<SECURITY_METRICS_GUIDE.html>)를 참고하세요.**

### 3.8 💡 Insights 탭

데이터 기반 인사이트와 실행 가능한 개선 방안을 제공합니다.

#### 서브탭 구성

  1. **🚨 Alerts** \- 알림 및 경고 (심각도별)
  2. **💡 Recommendations** \- 개선 권장사항 (우선순위별)
  3. **📈 Task Explorer** \- 개별 Task 상세 분석

#### 서브탭 1: 🚨 Alerts

임계값을 벗어난 메트릭에 대한 알림을 심각도별로 표시합니다.
[code] 
    🚨 알림 및 경고
    
    총 5개의 알림이 있습니다.
    
    ### 🔴 Critical (긴급)
    - TCR이 임계값 미만 (현재: 72.3%, 목표: ≥85%)
      권장사항: 실패 원인 분석, 에러 핸들링 개선
    
    ### 🟡 High (높음)
    - 평균 지연시간이 목표치 초과 (현재: 5.2s, 목표: ≤3s)
      권장사항: 프롬프트 최적화, 더 빠른 모델 사용
    - 정확도가 낮음 (현재: 68.3%, 목표: ≥80%)
      권장사항: 검증 로직 강화, 품질 검사 추가
    
    ### 🟢 Medium (보통)
    - 환각률이 다소 높음 (현재: 5.2%, 목표: ≤3%)
      권장사항: Context 보강, 사실 확인 메커니즘 추가
[/code]

**알림 표시 방식**

  * Critical 알림은 자동으로 펼쳐진 상태로 표시
  * 각 알림은 메트릭명, 현재 값, 권장사항 포함
  * 모든 지표가 정상이면 "✅ 모든 지표가 정상 범위 내에 있습니다!" 표시

#### 서브탭 2: 💡 Recommendations

자동 생성된 개선 제안을 우선순위별로 제공합니다.
[code] 
    💡 개선 권장사항
    
    총 8개의 개선 제안이 있습니다.
    - 🔴 높음(High): 2개
    - 🟡 보통(Medium): 4개
    - 🟢 낮음(Low): 2개
    
    ---
    
    🔴 [높음] 작업 완료율 개선
    📂 영역: Core Metrics - TCR
    
    🔍 현재 문제점
    TCR이 72.3%로 목표치(85%)를 크게 밑돌고 있습니다.
    약 27.7%의 작업이 완료되지 않고 있습니다.
    
    💡 개선 제안
    1. 실패 Task 로그를 분석하여 공통 패턴 파악
    2. 에러 핸들링 로직 강화
    3. 재시도 메커니즘 추가 또는 개선
    4. Task 검증 단계 추가
    
    📈 예상 효과
    TCR을 85% 이상으로 개선하여 시스템 안정성 향상
[/code]

**권장사항 표시 방식**

  * 우선순위 높음(High) 제안은 자동으로 펼쳐진 상태
  * 각 제안은 영역, 문제점, 개선 제안, 예상 효과 포함
  * 모든 메트릭이 목표치 달성 시 "✅ 모든 메트릭이 목표치를 달성했습니다." 표시

#### 서브탭 3: 📈 Task Explorer

개별 Task를 필터링하고 상세 정보를 탐색할 수 있습니다.
[code] 
    📈 Task 상세 탐색 (125개)
    
    [필터 옵션]
    - TaskType 필터: All / RAG_TASK / TOOL_USE / etc.
    - 상태 필터: All / Success / Failed
    - 정렬 기준: timestamp / execution_time / accuracy_score
    
    [Task 목록 테이블]
    Task ID          Type       Success  TCR    Accuracy  Time(s)  Tokens  Attempts
    task_001        RAG_TASK    ✅      98.5%   95.2%    2.34     1,245    1
    task_002        TOOL_USE    ❌      45.0%   62.1%    5.67     2,890    3
    task_003        RAG_TASK    ✅      100%    98.7%    1.89       987    1
    ...
    
    [상세 보기]
    선택한 Task ID를 선택하면 상세 정보 표시:
    - 기본 정보: Type, Success, Completion Score, Accuracy, Time, Attempts
    - 토큰 사용량: Input, Output, Total
    - 오류 메시지 (실패한 경우)
[/code]

**Task Explorer 기능**

  * **필터링** : TaskType, 성공/실패 상태로 필터
  * **정렬** : 시간순, 실행시간, 정확도 기준으로 정렬
  * **상세 분석** : 개별 Task의 모든 메트릭 확인
  * **디버깅** : 실패한 Task의 오류 메시지 확인

### 3.9 🔍 Test 투명성 탭

평가 과정의 투명성과 재현성을 보장하기 위한 추적 및 감사 기능을 제공합니다.

#### 서브탭 구성

Test 투명성 탭은 다음 4개의 서브탭으로 구성됩니다:

##### 1\. 📊 메트릭 계산 과정

각 메트릭이 어떻게 계산되었는지 상세하게 추적합니다.

  * **입력 데이터** : 계산에 사용된 원본 데이터
  * **중간 단계** : 계산 과정의 각 스텝
  * **최종 결과** : 산출된 메트릭 값
  * **계산 공식** : 사용된 알고리즘 및 로직

> 💡 **활용** : 메트릭 값의 신뢰성 검증, 계산 오류 디버깅, 커스텀 메트릭 개발 시 참고

##### 2\. 📝 Annotations (주석 관리)

평가 결과에 대한 전문가 주석 및 리뷰를 관리합니다.

  * **주석 추가/편집** : 평가 결과에 메모 및 피드백 작성
  * **전문가 리뷰** : 도메인 전문가의 검증 기록
  * **버전별 변경 이력** : 주석 수정 내역 추적
  * **협업 기능** : 팀원 간 주석 공유

> 💡 **활용** : 품질 관리 프로세스, 팀 내 지식 공유, 평가 결과 개선 아이디어 문서화

##### 3\. 📜 Audit Logs (감사 로그)

모든 평가 활동을 타임라인 형식으로 기록합니다.

  * **활동 기록** : 누가, 언제, 무엇을 수행했는지
  * **변경 이력** : 설정 변경, 데이터 수정 내역
  * **시스템 이벤트** : 평가 시작/종료, 에러 발생
  * **규정 준수** : 감사 요구사항 충족을 위한 증적

> 💡 **활용** : 컴플라이언스 검증, 문제 발생 시 원인 추적, 운영 이력 관리

##### 4\. 📋 상세 리포트

투명성 메타데이터 및 재현 가능한 실행 조건을 제공합니다.

  * **평가 환경** : OS, Python 버전, 라이브러리 버전
  * **실행 설정** : 사용된 파라미터 및 옵션
  * **데이터 출처** : 평가 데이터의 원본 및 버전
  * **재현 방법** : 동일한 결과를 얻기 위한 실행 가이드

> 💡 **활용** : 평가 결과 재현, 환경 차이로 인한 문제 해결, 배포 환경 검증

* * *

### 3.8 📚 지표 설명 탭 (Metrics Glossary)

모든 평가 지표에 대한 상세한 설명과 해석 가이드를 제공합니다.

#### 메트릭 카테고리

##### 🎯 Core Metrics (핵심 지표)

  * **TCR (Task Completion Rate)** : 작업의 성공/실패를 측정
  * **Accuracy** : 예상 결과와의 일치도
  * **Quality** : 5가지 차원의 응답 품질
  * **Hallucination** : 사실 왜곡 발생률

##### ⚡ Performance (성능 지표)

  * **Latency** : 응답 시간 (p50, p95, p99)
  * **Cost** : 토큰 비용 및 총 비용
  * **Token Usage** : 입력/출력 토큰 사용량
  * **Retry Success Rate** : 재시도 성공률

##### 🤖 Agentic AI (에이전트 특화 지표)

  * **Tool Selection** : 도구 선택 정확도
  * **Agent Coordination** : 멀티 에이전트 협업 효율성
  * **Workflow Execution** : 워크플로우 실행 성공률
  * **Tool Efficiency** : 도구 사용 효율성

##### 🔬 Advanced (고급 지표)

  * **DeepEval 메트릭** : G-Eval, Hallucination, Answer Relevancy 등
  * **Ragas 메트릭** : Faithfulness, Context Recall/Precision 등

#### 각 메트릭별 상세 정보

지표 설명 탭에서는 각 메트릭마다 다음 정보를 제공합니다:

  1. **정의 (Definition)**
     * 메트릭이 측정하는 대상
     * 왜 중요한지
     * 어떤 상황에서 사용하는지
  2. **계산 방법 (Calculation)**
     * 수식 및 알고리즘
     * 입력 데이터 요구사항
     * 계산 과정 예시
  3. **해석 가이드 (Interpretation)**
     * 값의 범위 (0~1, 0~100, 시간 등)
     * 좋은 값 vs 나쁜 값
     * 임계값 권장사항
     * 벤치마크 참고치
  4. **개선 방법 (Improvement)**
     * 메트릭을 향상시키는 구체적 방법
     * 모델/프롬프트 최적화 팁
     * 시스템 아키텍처 개선 사항
  5. **관련 메트릭 (Related Metrics)**
     * 함께 확인해야 할 지표들
     * 트레이드오프 관계
     * 상관관계 분석

#### 활용 시나리오

##### 👨‍💻 신규 사용자

  * 각 메트릭의 의미를 빠르게 이해
  * 평가 결과 해석 방법 학습
  * 어떤 지표를 우선적으로 봐야 하는지 파악

##### 👔 QA 관리자

  * 임계값 설정 시 참고 자료로 활용
  * 팀원 교육용 가이드 제공
  * 평가 기준 문서화

##### ⚙️ 개발자

  * 메트릭 구현 로직 상세 이해
  * 커스텀 메트릭 개발 시 참고
  * 디버깅 및 문제 해결

> 💡 **팁** : Overview 탭에서 이상한 값을 발견했다면, 지표 설명 탭에서 해당 메트릭의 정의와 개선 방법을 확인하세요!

* * *

### 3.10 📚 지표 설명 탭

**모든 메트릭의 상세 설명** 을 제공하는 참고 자료입니다.

#### 구성

  * **Layer 1 Metrics** : 기본 성능 지표 설명 (TCR, Accuracy, Quality, Hallucination, RAG 메트릭 등)
  * **Layer 2 Metrics** : 에이전트 특화 지표 설명 (Tool Selection, Efficiency, Multi-Agent, Workflow 등)
  * **Layer 3 Metrics** : 고급 평가 지표 설명 (DeepEval, Ragas 메트릭 등)
  * **Security Metrics** : 보안 메트릭 설명 (Input Sanitization, Output Leakage, Authorization, Privilege Escalation, Attack Detection)

각 메트릭에 대해 다음 정보를 제공합니다:

  * 📖 **정의** : 메트릭이 측정하는 것
  * 📐 **계산 방식** : 수식 및 알고리즘
  * 🎯 **해석 가이드** : 값의 의미 및 임계값
  * 💡 **Best Practices** : 개선 방법

### 3.11 📦 Export 탭 

평가 결과를 내보내고 투명성 정보를 제공합니다.

**⚡ 에서 개선:** CSV Export now includes **13+ comprehensive metrics**

  * **Layer 1 (Native 7개):** TCR, Accuracy, Hallucination, Quality, Latency, Cost, Token Usage
  * **Layer 2 (Agentic AI 4개):** Tool Selection, Agent Coordination, Workflow, Retry
  * **RAG Metrics (4개):** Faithfulness, Answer Relevancy, Context Recall, Context Precision

#### 서브탭 구성

  1. **📝 Reports** \- 종합 평가 리포트 생성
  2. **⚙️ 평가 환경 & 설정** \- 평가 환경 및 설정 정보

#### 서브탭 1: 📝 Reports

전체 지표를 포함한 종합 HTML 리포트를 다운로드할 수 있습니다.

**리포트 요약 섹션** \- 작업 완료율 (TCR) - 정확도 - 평균 응답 시간 - 총 비용

**리포트 상세 내용 (Expander)**

  1. **🎯 Core Metrics** \- 기본 성능 지표 
     * 품질 평가 (평가된 응답 수, 평균 품질, 고품질 응답, 등급 분포)
     * 환각 탐지 (검사된 응답, 환각 발생률, 탐지된 환각)
  2. **⚡ Performance** \- 효율성 지표 
     * 토큰 & 비용 (총 토큰, 평균 토큰/Task, 총 비용, 평균 비용/Task)
     * 응답 시간 (평균, 중앙값, 최소/최대, P95)
  3. **🤖 Agentic AI** \- 에이전트 특화 지표 
     * 도구 선택 & 협업 (도구 선택 정확도, 협업 점수, 총 호출, 상호작용)
     * 워크플로우 & 재시도 (워크플로우 성공률, 재시도율, 성공 개수)
  4. **🔬 Advanced Metrics** \- 고급 평가 지표 
     * DeepEval 메트릭 (G-Eval, Hallucination, Answer Relevancy, Bias, Toxicity)
     * Ragas 메트릭 (Faithfulness, Context Recall/Precision, Answer Similarity/Correctness)

**HTML 리포트 생성**
[code] 
    [📥 HTML 리포트 다운로드] 버튼
    - comprehensive_report_YYYYMMDD_HHMMSS.html 형식으로 저장
    - 모든 메트릭과 시각화를 포함한 독립 실행형 HTML 파일
[/code]

#### 서브탭 2: ⚙️ 평가 환경 & 설정

평가 환경 및 감사 정보를 제공합니다.

**투명성 정보** \- 평가 환경 설정 - 사용된 모델 및 파라미터 - 평가 실행 시간 - 데이터 품질 검증 결과

### 3.12 ⚙️ Settings 탭

대시보드 설정 및 구성 옵션을 제공합니다.

#### 주요 기능

  1. **📁 파일 정보**
     * 현재 로드된 평가 파일 정보 표시
     * 병합된 파일 목록 (multi-file 모드인 경우)
     * 파일 로드 상태 확인
  2. **🔒 보안 설정**
     * 보안 메트릭 활성화 상태 확인
     * 활성화된 보안 컴포넌트 목록 
       * Input Sanitization (Layer 1)
       * Output Leakage Detection (Layer 1)
       * Tool Authorization (Layer 1)
       * Privilege Escalation Detection (Layer 2)
       * Attack Detection (Layer 2)
     * 보안 설정 가이드 및 권장사항
  3. **ℹ️ 시스템 정보**
     * Agent Evaluator 버전 정보
     * 대시보드 버전 
     * Python 환경 정보
     * 설치된 의존성 패키지 버전

> 💡 **팁** : Settings 탭에서 보안 메트릭이 비활성화되어 있다면, SecurityEvaluator를 초기화하여 보안 평가를 활성화할 수 있습니다.

* * *

## 4\. 데이터 편집 대시보드

`dashboard_data_editor.py`는 테스트 설정 및 데이터 관리를 위한 독립 대시보드입니다.

### 4.1 실행 방법
[code] 
    [](<#cb38-1>)streamlit run dashboard_data_editor.py
    [](<#cb38-2>)
    [](<#cb38-3>)# 메인 대시보드와 동시 실행
    [](<#cb38-4>)streamlit run dashboard_data_editor.py --server.port 8503
[/code]

### 4.2 대시보드 구성

데이터 편집 대시보드는 **2개의 메인 탭** 으로 구성:

  1. **📝 데이터 편집** \- Golden Dataset, 임계값, 테스트 설정
  2. **🔬 Test 투명성** \- 평가 과정 추적 및 감사

### 4.3 📝 데이터 편집 탭

테스트 관리자를 위한 워크플로우 최적화된 탭으로, 4개의 서브탭으로 구성:

#### 서브탭 구성

  1. **⚙️ 임계값 설정** \- 평가 기준 설정
  2. **📄 Golden Dataset** \- 테스트 데이터 생성 및 관리
  3. **📋 Test 준비** \- 테스트 환경 검증 및 구성 저장
  4. **📊 이력 관리** \- 버전 관리 및 편집 기록

#### 서브탭 1: ⚙️ 임계값 설정

평가 메트릭의 임계값을 설정합니다.

**Preset 선택**
[code] 
    - Minimal: 기본 메트릭만 (TCR, Accuracy, Hallucination)
    - Balanced: 균형잡힌 설정 (Preset + Agentic AI)
    - Strict: 엄격한 기준 (높은 임계값)
    - Production: 프로덕션 환경 (안정성 중시)
[/code]

**커스텀 설정** \- Layer 1 Metrics: TCR, Accuracy, Hallucination, Latency - Layer 2 Metrics: Tool Selection, Agent Coordination, Workflow - Layer 3 Metrics: Faithfulness, Context Recall, Answer Relevancy

#### 서브탭 2: 📄 Golden Dataset

테스트용 Golden Dataset을 생성하고 관리합니다.

**생성 방법**

  1. **PDF에서 자동 생성**
     * PDF 파일 업로드
     * AI가 자동으로 QA 쌍 추출
     * 수동 검증 및 수정
  2. **수동 생성**
     * 질문-답변 쌍 직접 작성
     * 메타데이터 추가 (카테고리, 난이도 등)

**데이터 관리** \- 기존 Dataset 로드 및 편집 - Dataset 병합 - Dataset 내보내기/가져오기

#### 서브탭 3: 📋 Test 준비

테스트 실행 준비 상태를 확인하고 구성을 저장합니다.

**준비 상태 확인**
[code] 
    ✅ Test 실행 준비 완료!
    
    Golden Datasets    Threshold 설정
        5개            Balanced         [🚀 Test 실행]
[/code]

**Step-by-Step 프로세스**
[code] 
    Step 1: Golden Dataset 준비 ✅ 완료
    Step 2: Threshold 설정 ✅ 완료
    Step 3: 고급 평가 설정 (선택사항) 💡 기본값
[/code]

**Test 구성 저장**
[code] 
    💾 Test 구성 관리
    
    구성 이름: test_config_20241130_1430
    환경: production
    작성자: test_manager
    설명: 프로덕션 배포 전 회귀 테스트
    
    Golden Datasets 선택: [5개 선택됨]
    
    [💾 저장]  [취소]
[/code]

#### 서브탭 4: 📊 이력 관리

설정 변경 이력 및 버전 관리를 제공합니다.

**버전 관리** \- 이전 설정으로 롤백 - 변경 사항 비교 - 설정 스냅샷

**편집 기록** \- 누가, 언제, 무엇을 변경했는지 추적 - 변경 이유 및 설명

### 4.4 🔬 Test 투명성 탭

평가 과정의 투명성과 감사 추적을 제공합니다.

#### 주요 기능

**Test 과정 시각화** \- 메트릭 계산 단계별 추적 - 각 단계의 입력/출력 데이터 - 계산 시간 및 리소스 사용량

**데이터 품질 검증**
[code] 
    ✅ 데이터 품질 리포트
    
    전체 품질 점수: 87.5/100
    
    ### 데이터 완전성
    • 총 작업 수: 120개
    • 점수가 있는 작업: 115개 (95.8%)
    • 품질 평가된 작업: 108개 (90.0%)
[/code]

**감사 로그** \- 모든 평가 실행 기록 - 사용된 설정 및 데이터 - 결과 변경 이력

* * *

## 5\. 고급 활용법

### 5.1 데이터 비교

여러 평가 결과를 비교하려면:

  1. 첫 번째 평가 데이터 로드
  2. 스크린샷 캡처 또는 리포트 내보내기
  3. 두 번째 평가 데이터 로드
  4. 메트릭 비교

**팁** : 브라우저 탭을 여러 개 열어 동시에 비교 가능
[code] 
    [](<#cb44-1>)# 탭 1: 포트 8501
    [](<#cb44-2>)streamlit run streamlit_dashboard.py --server.port 8501
    [](<#cb44-3>)
    [](<#cb44-4>)# 탭 2: 포트 8502
    [](<#cb44-5>)streamlit run streamlit_dashboard.py --server.port 8502
[/code]

### 4.2 실시간 모니터링

평가 중 실시간으로 대시보드를 업데이트하려면:
[code] 
    [](<#cb45-1>)# evaluation_script.py
    [](<#cb45-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb45-3>)import time
    [](<#cb45-4>)
    [](<#cb45-5>)monitor = PerformanceMonitor()
    [](<#cb45-6>)
    [](<#cb45-7>)for i in range(100):
    [](<#cb45-8>)    # 작업 수행
    [](<#cb45-9>)    result = perform_task(i)
    [](<#cb45-10>)
    [](<#cb45-11>)    # 기록
    [](<#cb45-12>)    monitor.record_task(result)
    [](<#cb45-13>)
    [](<#cb45-14>)    # 10개마다 저장
    [](<#cb45-15>)    if (i + 1) % 10 == 0:
    [](<#cb45-16>)        monitor.save_to_file("realtime_evaluation.json")
    [](<#cb45-17>)        print(f"Saved: {i+1}/100")
    [](<#cb45-18>)        time.sleep(1)  # 대시보드 로드 시간
    [](<#cb45-19>)
    [](<#cb45-20>)# 최종 저장
    [](<#cb45-21>)monitor.save_to_file("realtime_evaluation.json")
[/code]

대시보드에서: 1. “realtime_evaluation.json” 로드 2. 10개 작업마다 “실제 데이터 로드” 버튼 클릭 3. 진행 상황 실시간 확인

### 4.3 커스텀 임계값 설정

코드에서 임계값을 설정한 후 대시보드에서 확인:
[code] 
    [](<#cb46-1>)monitor = PerformanceMonitor()
    [](<#cb46-2>)monitor.thresholds = {
    [](<#cb46-3>)    "tcr": 95.0,        # 엄격한 기준
    [](<#cb46-4>)    "accuracy": 90.0,
    [](<#cb46-5>)    "hallucination": 1.0,
    [](<#cb46-6>)    "latency": 2.0,
    [](<#cb46-7>)    "cost_per_task": 0.01
    [](<#cb46-8>)}
[/code]

대시보드의 🚨 알림 탭에서 커스텀 임계값 기준으로 알림 표시

### 4.4 A/B 테스트

두 가지 설정을 비교:

  1. **Setup A** : 기존 프롬프트
[code] [](<#cb47-1>)# run_test_a.py
         [](<#cb47-2>)monitor_a = PerformanceMonitor()
         [](<#cb47-3>)# ... 평가 수행
         [](<#cb47-4>)monitor_a.save_to_file("test_a.json")
[/code]

  2. **Setup B** : 개선된 프롬프트
[code] [](<#cb48-1>)# run_test_b.py
         [](<#cb48-2>)monitor_b = PerformanceMonitor()
         [](<#cb48-3>)# ... 평가 수행
         [](<#cb48-4>)monitor_b.save_to_file("test_b.json")
[/code]

  3. **비교** : 대시보드에서 각각 로드하여 메트릭 비교

### 4.5 자동화된 리포팅

정기적으로 리포트를 생성하려면:
[code] 
    [](<#cb49-1>)# 매일 자동 리포트 생성
    [](<#cb49-2>)# crontab -e
    [](<#cb49-3>)0 9 * * * cd /path/to/project && python generate_daily_report.py
[/code]
[code] 
    [](<#cb50-1>)# generate_daily_report.py
    [](<#cb50-2>)from agent_evaluator import PerformanceMonitor
    [](<#cb50-3>)from datetime import datetime
    [](<#cb50-4>)
    [](<#cb50-5>)# 어제 데이터 로드
    [](<#cb50-6>)yesterday = datetime.now().strftime("%Y%m%d")
    [](<#cb50-7>)monitor = PerformanceMonitor.load_from_file(f"evaluation_{yesterday}.json")
    [](<#cb50-8>)
    [](<#cb50-9>)# 리포트 생성
    [](<#cb50-10>)report = monitor.generate_report(period=f"Daily Report - {yesterday}")
    [](<#cb50-11>)
    [](<#cb50-12>)# 요약 출력
    [](<#cb50-13>)monitor.print_summary()
    [](<#cb50-14>)
    [](<#cb50-15>)# 알림 확인
    [](<#cb50-16>)alerts = monitor.get_alerts()
    [](<#cb50-17>)if alerts:
    [](<#cb50-18>)    # 슬랙/이메일 등으로 알림 발송
    [](<#cb50-19>)    send_notification(alerts)
[/code]

* * *

## 6\. 문제 해결

### 6.1 일반적인 문제

#### 문제: 대시보드가 로드되지 않음

**증상**
[code] 
    Streamlit is running...
    You can now view your Streamlit app in your browser.
[/code]

하지만 브라우저에서 접속 안됨

**해결** 1\. 포트 충돌 확인 `bash lsof -i :8501 # 다른 프로세스가 사용 중이면 종료 또는 다른 포트 사용 streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py --server.port 8502`

  2. 방화벽 확인
[code] [](<#cb52-1>)# 로컬호스트 접근 허용 확인
[/code]

  3. 브라우저 캐시 삭제

     * Ctrl + Shift + Delete
     * 캐시 및 쿠키 삭제

#### 문제: 데이터 로드 실패

**증상**
[code] 
    ❌ example2_ragas_comprehensive.json 로드 실패
[/code]

**해결** 1\. 파일 경로 확인 `bash ls evaluation_results/ # 파일이 있는지 확인`

  2. 파일 권한 확인
[code] [](<#cb54-1>)chmod 644 evaluation_results/*.json
[/code]

  3. JSON 형식 검증
[code] [](<#cb55-1>)python -m json.tool < evaluation_results/example2.json
         [](<#cb55-2>)# 오류 있으면 표시됨
[/code]

#### 문제: 고급 메트릭이 표시되지 않음

**증상** \- DeepEval 지표 섹션이 안 보임 - RAGAS 지표 섹션이 안 보임

**원인** \- HybridPerformanceMonitor를 사용하지 않음 - `enable_advanced_metrics=False` \- 고급 메트릭 데이터가 없음

**해결** 1\. HybridPerformanceMonitor 사용 확인 `python from hybrid_monitor import create_monitor monitor = create_monitor(profile="balanced") # 또는 "rag", "full"`

  2. 고급 메트릭 활성화
[code] [](<#cb56-1>)monitor.record_task(
         [](<#cb56-2>)    task,
         [](<#cb56-3>)    enable_advanced_metrics=True,  # ✅
         [](<#cb56-4>)    input_text="...",
         [](<#cb56-5>)    output_text="...",
         [](<#cb56-6>)    quality_criteria="..."
         [](<#cb56-7>))
[/code]

  3. API 키 확인
[code] [](<#cb57-1>)echo $OPENAI_API_KEY
         [](<#cb57-2>)# 설정되어 있는지 확인
[/code]

#### 문제: 차트가 표시되지 않음

**증상** \- 차트 영역이 비어 있음 - 로딩이 계속됨

**해결** 1\. 데이터 확인 - 최소 5개 이상의 작업 필요 - 데모 데이터 로드하여 테스트

  2. Plotly 재설치
[code] [](<#cb58-1>)pip install --upgrade plotly
[/code]

  3. 브라우저 콘솔 확인

     * F12 → Console 탭
     * JavaScript 오류 확인

### 6.2 성능 최적화

#### 대시보드가 느릴 때

**원인** \- 대량의 작업 데이터 (1000개 이상) - 고급 메트릭이 너무 많음

**해결** 1\. 데이터 필터링 `python # 최근 100개만 저장 recent_tasks = monitor.tasks[-100:] monitor_filtered = PerformanceMonitor() for task in recent_tasks: monitor_filtered.record_task(task) monitor_filtered.save_to_file("filtered.json")`

  2. 캐싱 활용 
     * Streamlit은 자동으로 캐싱함
     * `@st.cache_data` 데코레이터 활용
  3. 샘플링 
     * 전체 데이터 대신 샘플링된 데이터 사용

### 6.3 데이터 복구

#### 데이터 손실 시

**백업에서 복구**
[code] 
    [](<#cb59-1>)# evaluation_results 디렉토리 백업
    [](<#cb59-2>)cp -r evaluation_results evaluation_results_backup
    [](<#cb59-3>)
    [](<#cb59-4>)# 복구
    [](<#cb59-5>)cp evaluation_results_backup/*.json evaluation_results/
[/code]

#### 손상된 JSON 파일 복구
[code] 
    [](<#cb60-1>)# repair_json.py
    [](<#cb60-2>)import json
    [](<#cb60-3>)
    [](<#cb60-4>)filename = "damaged_file.json"
    [](<#cb60-5>)
    [](<#cb60-6>)try:
    [](<#cb60-7>)    with open(filename, 'r') as f:
    [](<#cb60-8>)        data = json.load(f)
    [](<#cb60-9>)    print("✅ 파일 정상")
    [](<#cb60-10>)except json.JSONDecodeError as e:
    [](<#cb60-11>)    print(f"❌ JSON 오류: {e}")
    [](<#cb60-12>)    print("수동 복구 필요")
    [](<#cb60-13>)    # 텍스트 에디터로 파일 열어서 수정
[/code]

* * *

## 6\. 키보드 단축키

단축키 | 기능  
---|---  
`Ctrl + R` | 대시보드 새로고침  
`Ctrl + K` | 명령 팔레트 열기  
`F11` | 전체화면  
`Ctrl + F` | 페이지 내 검색  
  
* * *

## 7\. 모범 사례

### 7.1 일일 워크플로우

  1. **아침** : 어제 평가 데이터 로드
  2. **오전** : 🚨 알림 탭에서 문제 확인
  3. **오후** : 개선 작업 수행
  4. **저녁** : 새 평가 실행 및 비교

### 7.2 주간 리뷰

  1. **월요일** : 지난 주 데이터 종합
  2. **수요일** : 중간 점검
  3. **금요일** : 주간 리포트 생성 및 공유

### 7.3 A/B 테스트 절차

  1. 베이스라인 평가 실행
  2. 변경 사항 적용
  3. 새 평가 실행
  4. 대시보드에서 비교
  5. 통계적 유의성 확인

* * *

* * *

## 📊 품질 관리자 가이드 (QA Manager)

### 🎯 가이드 개요

이 가이드는 **품질 관리자(QA Manager)** 가 Streamlit Dashboard를 활용하여 **AI 에이전트 시스템의 품질을 체계적으로 모니터링, 평가, 관리** 하는 방법을 제공합니다. 

**학습 목표:**

  * ✅ Dashboard를 통한 실시간 품질 모니터링 방법
  * ✅ 임계값 기반 품질 관리 체계 구축
  * ✅ 배포 전 품질 검증 프로세스
  * ✅ 품질 문제 탐지 및 분석 기법
  * ✅ 정기 품질 리뷰 운영 방법

### 8.1 Dashboard를 통한 품질 모니터링

#### 8.1.1 실시간 품질 지표 확인

**📊 Overview 탭 활용**

모니터링 항목 | Dashboard 위치 | 확인 주기 | 정상 범위  
---|---|---|---  
전체 작업 수 | Overview → 총 작업 수 | 실시간 | -  
성공/실패 비율 | Overview → 성공/실패 분포 | 실시간 | 성공률 > 90%  
평균 완료 시간 | Overview → 평균 완료 시간 | 실시간 | < 5초  
평균 비용 | Overview → 평균 비용 | 실시간 | < $0.20  
  
**📈 Layer 1: Basic 탭 활용**

Layer 1 메트릭 | Dashboard 표시 | 임계값 (Production) | 위험 신호  
---|---|---|---  
Task Completion Rate | 게이지 차트 + 숫자 | > 85% | < 75% (🔴 즉시 조치)  
Accuracy | 게이지 차트 + 숫자 | > 80% | < 70% (🔴 즉시 조치)  
Hallucination Rate | 게이지 차트 + 숫자 | < 5% | > 10% (🔴 즉시 조치)  
Latency | 막대 차트 + 통계 | < 5초 | > 10초 (🟡 주의)  
Cost per Task | 막대 차트 + 통계 | < $0.20 | > $0.50 (🟡 주의)  
Token Usage | 막대 차트 + 통계 | < 10K tokens | > 20K tokens (🟡 주의)  
  
**🤖 Layer 2: Agentic 탭 활용 (Layer 2 메트릭)**

Layer 2 메트릭 | Dashboard 표시 | 임계값 (Production) | 위험 신호  
---|---|---|---  
Tool Selection Accuracy | 게이지 차트 | > 85% | < 75% (🔴)  
Tool Usage Efficiency | 게이지 차트 | > 80% | < 70% (🔴)  
Agent Coordination Score | 게이지 차트 | > 4.0 / 5.0 | < 3.0 (🔴)  
Communication Overhead | 게이지 차트 | < 20% | > 30% (🟡)  
Workflow Efficiency | 게이지 차트 | > 75% | < 60% (🔴)  
Step Redundancy | 게이지 차트 | < 10% | > 20% (🟡)  
  
#### 8.1.2 품질 추세 분석

**📈 Performance 탭 활용**
[code] 
    Dashboard → Performance 탭
    ├─ Latency Over Time (시간별 지연 시간 추세)
    ├─ Cost Over Time (시간별 비용 추세)
    └─ Token Usage Over Time (시간별 토큰 사용량 추세)
[/code]

**모니터링 방법:**

  1. **추세 확인** : 라인 차트에서 상승/하락 패턴 관찰
  2. **이상치 탐지** : 급격한 변화가 있는 시점 식별
  3. **주기별 비교** : 주간/월간 평균값 비교
  4. **배포 영향 분석** : 새 버전 배포 전후 비교

**💡 QA Tip:** 추세 차트에서 다음 패턴을 주의깊게 관찰하세요:

  * 🔴 **지속적인 상승** : Latency, Cost가 계속 증가 → 성능 저하 신호
  * 🟡 **변동성 증가** : 일관되지 않은 성능 → 안정성 문제
  * 🟢 **계단식 변화** : 특정 시점에 급변 → 배포 또는 데이터 변경 영향

#### 8.1.3 작업 유형별 품질 분석

**📋 Overview 탭 → "작업 유형별 통계" 섹션**

작업 유형 | 모니터링 포인트 | 정상 기준  
---|---|---  
Code Generation | TCR, Accuracy, Latency | TCR > 85%, Accuracy > 80%  
Data Analysis | Accuracy, Hallucination | Accuracy > 85%, Hallucination < 3%  
Question Answering | Accuracy, Latency | Accuracy > 90%, Latency < 3초  
Summarization | Accuracy, Token Usage | Accuracy > 85%, Tokens < 5K  
Translation | Accuracy, Cost | Accuracy > 90%, Cost < $0.10  
  
**분석 방법:**
[code] 
    1. Overview 탭에서 "작업 유형별 통계" 테이블 확인
    2. 각 작업 유형의 평균 메트릭 값 검토
    3. 기준값 대비 낮은 항목 식별
    4. 해당 작업 유형의 샘플 데이터 상세 분석 (Insights 탭 활용)
[/code]

### 8.2 임계값 기반 품질 관리

#### 8.2.1 임계값 설정 (Data Editor Dashboard 활용)

**실행 방법:**
[code] 
    streamlit run Evaluator_Examples/Dashboard/dashboard_data_editor.py
[/code]

**데이터 편집 탭 → "임계값 설정" 섹션**

개발 단계 | TCR | Accuracy | Hallucination | Latency | Cost  
---|---|---|---|---|---  
🔬 Alpha | > 60% | > 60% | < 15% | < 15초 | < $0.50  
🧪 Beta | > 75% | > 75% | < 10% | < 10초 | < $0.30  
🚀 Production | > 85% | > 80% | < 5% | < 5초 | < $0.20  
💎 Enterprise | > 95% | > 90% | < 2% | < 3초 | < $0.15  
  
**임계값 적용 방법:**

  1. Data Editor Dashboard에서 "임계값 설정" 섹션 열기
  2. 현재 개발 단계에 맞는 임계값 입력
  3. "💾 임계값 저장" 버튼 클릭
  4. 메인 Dashboard에서 임계값 기반 색상 표시 확인 
     * 🟢 **녹색** : 임계값 이상 (정상)
     * 🟡 **노란색** : 임계값 근처 (주의)
     * 🔴 **빨간색** : 임계값 이하 (위험)

#### 8.2.2 위험 신호 감지

**자동 알림 체계 (Dashboard 내장)**

위험 수준 | 조건 | Dashboard 표시 | 조치 사항  
---|---|---|---  
🔴 Critical | TCR < 75% OR Hallucination > 10% | 빨간색 게이지 + 경고 메시지 | 즉시 조치 필요  
🟠 High | Accuracy < 70% OR Latency > 10초 | 주황색 게이지 + 경고 | 24시간 내 조치  
🟡 Medium | Cost > $0.30 OR Tokens > 15K | 노란색 게이지 | 주간 리뷰에서 검토  
🟢 Low | 모든 메트릭 정상 | 녹색 게이지 | 정기 모니터링  
  
**Dashboard 위험 신호 체크리스트:**
[code] 
    □ Layer 1: Basic 탭에서 빨간색 게이지가 있는가?
    □ Performance 탭에서 급격한 상승 추세가 보이는가?
    □ Layer 2: Agentic 탭에서 Layer 2 메트릭이 저하되었는가?
    □ Insights 탭에서 반복적인 실패 패턴이 있는가?
    □ 특정 작업 유형의 성능이 다른 유형보다 현저히 낮은가?
[/code]

### 8.3 배포 전 품질 검증

#### 8.3.1 Release Dashboard Checklist

**배포 전 필수 검증 (Dashboard 기반)**

검증 항목 | Dashboard 위치 | 합격 기준 | 결과  
---|---|---|---  
1\. 전체 TCR | Core Metrics → TCR | > 85% | [ ]  
2\. 전체 Accuracy | Core Metrics → Accuracy | > 80% | [ ]  
3\. Hallucination Rate | Core Metrics → Hallucination | < 5% | [ ]  
4\. 평균 Latency | Performance → Latency | < 5초 | [ ]  
5\. 평균 Cost | Performance → Cost | < $0.20 | [ ]  
6\. Tool Selection | Agentic AI → Tool Selection | > 85% | [ ]  
7\. Agent Coordination | Agentic AI → Coordination | > 4.0 / 5.0 | [ ]  
8\. Workflow Efficiency | Agentic AI → Workflow | > 75% | [ ]  
9\. 작업 유형별 균형 | Overview → 작업 유형별 통계 | 모든 유형 > 80% | [ ]  
10\. Layer 3 메트릭 | Advanced → DeepEval/Ragas | 평균 > 0.8 | [ ]  
  
**📋 배포 승인 기준:**

  * ✅ **필수 통과** : 항목 1-5 (Layer 1 Core Metrics) 모두 합격
  * ✅ **권장 통과** : 항목 6-8 (Layer 2 Agentic AI) 최소 2개 합격
  * ✅ **선택 통과** : 항목 9-10 (작업 균형, Layer 3) 80% 이상 합격

#### 8.3.2 A/B 테스트 비교 (Dashboard 활용)

**신규 버전과 기존 버전 비교 방법:**
[code] 
    # 1. 기존 버전 평가
    python evaluate_current_version.py
    # → evaluation_results/v1.0_baseline.json 생성
    
    # 2. 신규 버전 평가
    python evaluate_new_version.py
    # → evaluation_results/candidate.json 생성
    
    # 3. Dashboard에서 각각 로드하여 비교
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py
[/code]

**비교 체크리스트:**

메트릭 | 기존 버전 (v1.0) | 신규 버전 | 변화율 | 판정  
---|---|---|---|---  
TCR | 87.5% | 89.2% | +1.7% | ✅ 개선  
Accuracy | 82.3% | 81.8% | -0.5% | ⚠️ 소폭 하락  
Latency | 4.2초 | 3.8초 | -9.5% | ✅ 개선  
Cost | $0.18 | $0.22 | +22.2% | ❌ 악화  
  
**승인 판단 기준:**

  * ✅ **즉시 승인** : 핵심 메트릭 (TCR, Accuracy) 개선 + 성능/비용 악화 없음
  * 🟡 **조건부 승인** : 핵심 메트릭 개선 but 비용 10% 이내 증가
  * ❌ **반려** : 핵심 메트릭 하락 OR 비용 20% 이상 증가

### 8.4 문제 탐지 및 분석

#### 8.4.1 Dashboard를 통한 문제 패턴 식별

**🔍 Insights 탭 활용**

문제 유형 | Dashboard 증상 | 분석 방법 | 원인 가설  
---|---|---|---  
🔴 반복 실패 | 특정 작업 유형의 TCR < 50% | Insights → 실패 작업 필터링 | 프롬프트 문제, 도구 버그  
🟠 지연 증가 | Latency 추세 상승 | Performance → Latency Over Time | 외부 API 지연, 토큰 증가  
🟡 비용 급등 | Cost 급격히 상승 | Performance → Cost + Token Usage | 비효율적인 프롬프트, 반복 호출  
🟢 환각 빈발 | Hallucination Rate > 10% | Core Metrics → Hallucination | 부적절한 컨텍스트, 모델 한계  
  
**실전 분석 프로세스:**
[code] 
    1. Overview 탭에서 전체 지표 확인
       └─ 이상 신호 발견 (예: TCR 70%)
    
    2. Layer 1: Basic 탭에서 상세 분석
       └─ 어떤 메트릭이 문제인지 식별
    
    3. Performance 탭에서 추세 확인
       └─ 언제부터 문제가 시작되었는지 파악
    
    4. Insights 탭에서 샘플 데이터 검토
       └─ 실패한 작업의 공통점 찾기
    
    5. Export 탭에서 상세 데이터 추출
       └─ CSV/JSON으로 다운로드하여 심층 분석
[/code]

#### 8.4.2 문제 시나리오별 Dashboard 활용법

**시나리오 1: 🔴 TCR이 갑자기 85% → 65%로 급감**

단계 | Dashboard 활용 | 조치  
---|---|---  
1\. 증상 확인 | Core Metrics → TCR 게이지 (빨간색) | 문제 심각도 파악  
2\. 시점 파악 | Performance → Latency Over Time | 문제 발생 시점 특정  
3\. 작업 유형 분석 | Overview → 작업 유형별 통계 | 어떤 작업이 실패하는지 식별  
4\. 샘플 검토 | Insights → 실패 작업 필터 | 실패 원인 공통점 찾기  
5\. 데이터 추출 | Export → CSV 다운로드 | 개발팀에 전달  
  
**시나리오 2: 🟠 평균 Latency가 3초 → 8초로 증가**

단계 | Dashboard 활용 | 조치  
---|---|---  
1\. 추세 분석 | Performance → Latency Over Time | 지속적 증가 vs 급증 판단  
2\. 토큰 확인 | Performance → Token Usage Over Time | 토큰 증가가 원인인지 확인  
3\. Layer 2 확인 | Agentic AI → Communication Overhead | 에이전트 간 통신 과다 확인  
4\. 작업별 분석 | Overview → 작업 유형별 평균 Latency | 특정 작업만 느린지 확인  
5\. 병목 식별 | Insights → 긴 Latency 샘플 | 어느 단계가 느린지 파악  
  
**시나리오 3: 🟡 Tool Selection Accuracy 급감 (85% → 60%)**

단계 | Dashboard 활용 | 조치  
---|---|---  
1\. Layer 2 확인 | Agentic AI → Tool Selection Accuracy | 정확한 수치 확인  
2\. 도구 분석 | Agentic AI → Tool Usage Distribution | 어떤 도구가 잘못 선택되는지  
3\. Layer 1 영향 | Core Metrics → TCR, Accuracy | Layer 1 메트릭 저하 여부  
4\. 샘플 검토 | Insights → 도구 선택 실패 샘플 | 잘못된 선택 패턴 분석  
5\. Golden Dataset | Data Editor → Golden Dataset | 테스트 데이터 업데이트 필요  
  
### 8.5 정기 품질 리뷰

#### 8.5.1 주간 품질 리뷰 (Dashboard 기반)

**📅 Weekly QA Review Checklist**

검토 항목 | Dashboard 활용 | 기준 | 조치  
---|---|---|---  
1\. 전체 성능 추세 | Performance → 모든 차트 | 전주 대비 ±5% 이내 | 추세 보고  
2\. 작업 유형 균형 | Overview → 작업 유형별 통계 | 모든 유형 > 80% | 낮은 유형 개선 계획  
3\. Layer 2 안정성 | Agentic AI → 모든 메트릭 | Production 임계값 유지 | 저하 시 원인 분석  
4\. 비용 효율성 | Performance → Cost Over Time | 주간 총 비용 확인 | 예산 초과 시 최적화  
5\. 실패 패턴 | Insights → 실패 작업 리뷰 | 반복 실패 없음 | 반복 패턴 수정  
6\. Golden Dataset | Data Editor → Dataset 검토 | 최신 상태 유지 | 분기별 업데이트  
  
**주간 리뷰 프로세스:**
[code] 
    1. Dashboard 실행 및 최신 데이터 로드
       streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py
    
    2. Overview 탭에서 주간 요약 확인
       - 총 작업 수, 성공률, 평균 성능
    
    3. Performance 탭에서 추세 분석
       - Latency, Cost, Token Usage 차트
    
    4. Layer 1: Basic + Layer 2: Agentic 탭에서 상세 검토
       - Layer 1 + Layer 2 메트릭 모두 확인
    
    5. Insights 탭에서 이상 샘플 분석
       - 실패/저성능 작업 리뷰
    
    6. Export 탭에서 리포트 생성
       - 주간 리포트 PDF/CSV 다운로드
    
    7. 액션 아이템 정리
       - 개선 필요 항목, 담당자, 마감일
[/code]

#### 8.5.2 월간 품질 리포트 생성

**📊 Monthly QA Report (Dashboard Export 활용)**

리포트 섹션 | Dashboard 데이터 소스 | 포함 내용  
---|---|---  
1\. Executive Summary | Overview → 전체 통계 | 월간 총 작업, 성공률, 주요 지표  
2\. Layer 1 메트릭 분석 | Core Metrics → 모든 차트 | TCR, Accuracy, Hallucination 추세  
3\. Layer 2 메트릭 분석 | Agentic AI → 모든 차트 | 도구, 협업, 워크플로우 효율성  
4\. 성능 분석 | Performance → 추세 차트 | Latency, Cost, Token Usage 변화  
5\. 작업 유형별 분석 | Overview → 작업 유형 통계 | 유형별 성능, 개선/악화 항목  
6\. 주요 이슈 및 조치 | Insights → 실패 샘플 | 발생한 문제, 조치 내역, 결과  
7\. 다음 달 개선 계획 | 전체 종합 | 우선순위, 목표, 담당자  
  
**리포트 생성 방법:**
[code] 
    # 1. 월간 데이터 통합 (모든 평가 결과 병합)
    cd Evaluator_Examples/Dashboard
    python utils/merge_evaluation_results.py --month 2024-12
    
    # 2. Dashboard에서 통합 데이터 로드
    streamlit run streamlit_dashboard.py
    # → 사이드바에서 monthly_2024_12.json 로드
    
    # 3. Export 탭에서 데이터 추출
    # → "📥 Export Data" 섹션
    # → CSV / JSON / PDF 선택하여 다운로드
    
    # 4. 리포트 템플릿에 데이터 반영
    # → Excel/PowerPoint 템플릿 사용
    # → Dashboard 스크린샷 추가
[/code]

**✅ QA 관리자 핵심 원칙 (Dashboard 활용)**

  1. **실시간 모니터링** : 매일 Dashboard 확인 (최소 1회)
  2. **임계값 기반 관리** : 객관적 기준으로 품질 판단
  3. **추세 중심 분석** : 단일 시점이 아닌 변화 패턴 관찰
  4. **작업 유형별 관리** : 전체 평균이 아닌 세부 분석
  5. **Layer 통합 관리** : Layer 1 + Layer 2 + Layer 3 종합 검토
  6. **데이터 기반 의사결정** : Dashboard 데이터로 배포 승인/반려
  7. **정기 리뷰 운영** : 주간/월간 체계적 품질 리뷰

**⚠️ 주의사항**

  * ❌ **과도한 최적화 금지** : 단일 메트릭만 극대화하지 말 것 (TCR 100% but Latency 30초 = 실패)
  * ❌ **샘플 크기 무시 금지** : 10개 샘플 vs 1000개 샘플의 신뢰도는 다름
  * ❌ **추세 무시 금지** : 현재 정상이어도 악화 추세면 조기 대응
  * ❌ **Layer 편향 금지** : Layer 1만 보지 말고 Layer 2, 3도 균형있게 검토

* * *

* * *

## 🛠️ 운영자 가이드 (Operations)

### 🎯 가이드 개요

이 가이드는 **운영자(Operations)** 가 Streamlit Dashboard를 **안정적으로 설치, 구성, 운영, 유지보수** 하는 방법을 제공합니다. 

**학습 목표:**

  * ✅ Dashboard 시스템 설치 및 초기 구성
  * ✅ 일상적인 운영 작업 수행 (데이터 관리, 사용자 지원)
  * ✅ 시스템 모니터링 및 성능 관리
  * ✅ 운영 중 발생하는 문제 해결
  * ✅ 정기 유지보수 및 업그레이드

### 9.1 Dashboard 설치 및 구성

#### 9.1.1 시스템 요구사항

항목 | 최소 사양 | 권장 사양 | 비고  
---|---|---|---  
Python 버전 | 3.8+ | 3.10+ | -  
메모리 (RAM) | 2GB | 4GB+ | 대량 데이터 처리 시  
디스크 공간 | 1GB | 10GB+ | 평가 결과 저장  
CPU | 2 Core | 4 Core+ | 동시 사용자 10명 이상  
네트워크 | 1 Mbps | 10 Mbps+ | 원격 접속 시  
OS | Linux, macOS, Windows | Linux (Ubuntu 20.04+) | 프로덕션 권장  
  
#### 9.1.2 설치 절차

**Step 1: 의존성 설치**
[code] 
    # 1. Conda 가상환경 생성 (권장)
    conda create --name Evaluator python=3.11
    conda activate Evaluator
    
    # 2. 필수 패키지 설치
    pip install streamlit==1.30.0
    pip install pandas plotly
    pip install agent-evaluator
    
    # 3. 설치 확인
    streamlit --version
    # Streamlit, version 1.30.0
    
    python -c "import agent_evaluator; print(agent_evaluator.__version__)"
    # 0.5.0
[/code]

**Step 2: Dashboard 파일 준비**
[code] 
    # ✅ 권장: 패키지에서 직접 실행 (복사 불필요)
    streamlit run $(python -c "import agent_evaluator; print(agent_evaluator.__path__[0])")/streamlit_dashboard.py
    
    # 또는 데이터 편집 Dashboard
    streamlit run $(python -c "import agent_evaluator; print(agent_evaluator.__path__[0])")/dashboard_data_editor.py --server.port 8503
    
    # Agent Evaluator 설치 위치 확인
    pip show agent-evaluator | grep Location
[/code]

**Step 3: 디렉토리 구조 생성**
[code] 
    # 작업 디렉토리 생성
    mkdir -p dashboard_workspace
    cd dashboard_workspace
    
    # 필요한 하위 디렉토리 생성
    mkdir -p evaluation_results   # 평가 결과 저장
    mkdir -p golden_datasets       # Golden Dataset 저장
    mkdir -p thresholds            # 임계값 설정 파일
    mkdir -p logs                  # 로그 파일
    mkdir -p backups               # 백업 파일
    
    # 디렉토리 구조 확인
    tree -L 1
    # dashboard_workspace/
    # ├── evaluation_results/
    # ├── golden_datasets/
    # ├── thresholds/
    # ├── logs/
    # └── backups/
[/code]

**Step 4: 환경 변수 설정**
[code] 
    # .env 파일 생성
    cat > .env << EOF
    # Streamlit 설정
    STREAMLIT_SERVER_PORT=8501
    STREAMLIT_SERVER_ADDRESS=0.0.0.0
    STREAMLIT_SERVER_HEADLESS=true
    
    # 데이터 디렉토리
    EVALUATION_RESULTS_DIR=./evaluation_results
    GOLDEN_DATASETS_DIR=./golden_datasets
    THRESHOLDS_DIR=./thresholds
    
    # 로깅
    LOG_LEVEL=INFO
    LOG_FILE=./logs/dashboard.log
    
    # 보안 (프로덕션 환경)
    # STREAMLIT_SERVER_ENABLE_CORS=false
    # STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true
    EOF
    
    # 환경 변수 로드
    source .env  # Linux/macOS
    # set -a; source .env; set +a  # Windows Git Bash
[/code]

#### 9.1.3 초기 구성 및 테스트

**Step 1: Dashboard 실행 테스트**
[code] 
    # 메인 Dashboard 실행
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py --server.port 8501
    
    # 다른 터미널에서 Data Editor 실행 (선택)
    streamlit run Evaluator_Examples/Dashboard/dashboard_data_editor.py --server.port 8502
    
    # 브라우저에서 접속 확인
    # http://localhost:8501  (메인 Dashboard)
    # http://localhost:8502  (Data Editor)
[/code]

**Step 2: 데모 데이터 로드 테스트**

단계 | 작업 | 예상 결과 | 확인 사항  
---|---|---|---  
1 | Dashboard 접속 | 정상 로딩 | 오류 메시지 없음  
2 | 📥 데모 데이터 로드 버튼 클릭 | 100개 샘플 생성 | "✅ 데모 데이터 로드 완료!" 메시지  
3 | Overview 탭 확인 | 전체 통계 표시 | TCR, Accuracy 등 메트릭 표시  
4 | Layer 1: Basic 탭 확인 | 게이지 차트 표시 | 6개 Layer 1 메트릭  
5 | Performance 탭 확인 | 라인 차트 표시 | Latency, Cost, Token 추세  
  
**Step 3: 실제 데이터 로드 테스트**
[code] 
    # 테스트용 평가 결과 생성
    cd ..
    python Evaluator_Examples/level_1_foundation/01_quickstart.py
    
    # 생성된 파일 확인
    ls -lh evaluation_results/
    # hybrid_evaluation_YYYYMMDD_HHMMSS.json
    
    # Dashboard에서 로드
    # 1. 사이드바 "📂 실제 평가 데이터" 섹션
    # 2. 드롭다운에서 파일 선택
    # 3. "📥 실제 데이터 로드" 버튼 클릭
    # 4. "✅ 파일명 로드 완료!" 메시지 확인
[/code]

#### 9.1.4 방화벽 및 네트워크 설정

**로컬 환경 (개발/테스트)**
[code] 
    # 로컬호스트만 접속 허용 (기본)
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py --server.address localhost
    
    # 포트 8501 (기본값) 사용
    # http://localhost:8501
[/code]

**네트워크 환경 (팀 공유)**
[code] 
    # 모든 인터페이스에서 접속 허용
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py --server.address 0.0.0.0
    
    # 방화벽 포트 오픈 (Linux)
    sudo ufw allow 8501/tcp
    sudo ufw allow 8502/tcp
    
    # 접속 URL
    # http://192.168.1.100:8501  (서버 IP 주소)
[/code]

**프로덕션 환경 (Nginx 리버스 프록시)**
[code] 
    # /etc/nginx/sites-available/dashboard
    server {
        listen 80;
        server_name dashboard.example.com;
    
        location / {
            proxy_pass http://localhost:8501;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    
    # Nginx 재시작
    sudo nginx -t
    sudo systemctl restart nginx
    
    # 접속 URL
    # http://dashboard.example.com
[/code]

### 9.2 일상 운영 작업

#### 9.2.1 데이터 관리

**평가 결과 파일 관리**

작업 | 주기 | 명령어 | 비고  
---|---|---|---  
디스크 사용량 확인 | 매일 | `du -sh evaluation_results/` | 10GB 초과 시 정리  
오래된 파일 정리 | 주간 | `find evaluation_results/ -mtime +30 -delete` | 30일 이상 파일 삭제  
파일 개수 확인 | 매일 | `ls evaluation_results/ | wc -l` | 1000개 초과 시 정리  
백업 | 주간 | `tar -czf backups/eval_$(date +%Y%m%d).tar.gz evaluation_results/` | 압축 백업  
  
**자동 정리 스크립트**
[code] 
    #!/bin/bash
    # cleanup_old_evaluations.sh
    
    EVAL_DIR="evaluation_results"
    DAYS_TO_KEEP=30
    MAX_FILES=1000
    
    echo "=== Evaluation Results Cleanup ==="
    echo "Directory: $EVAL_DIR"
    echo "Keep last: $DAYS_TO_KEEP days"
    
    # 1. 오래된 파일 삭제 (30일 이상)
    DELETED_COUNT=$(find $EVAL_DIR -type f -mtime +$DAYS_TO_KEEP | wc -l)
    find $EVAL_DIR -type f -mtime +$DAYS_TO_KEEP -delete
    echo "✓ Deleted $DELETED_COUNT old files (> $DAYS_TO_KEEP days)"
    
    # 2. 파일 개수 확인 및 추가 정리
    FILE_COUNT=$(ls $EVAL_DIR | wc -l)
    echo "Current file count: $FILE_COUNT"
    
    if [ $FILE_COUNT -gt $MAX_FILES ]; then
        EXTRA=$(($FILE_COUNT - $MAX_FILES))
        echo "⚠ Exceeds max files ($MAX_FILES), deleting $EXTRA oldest files"
        ls -t $EVAL_DIR | tail -n $EXTRA | xargs -I {} rm $EVAL_DIR/{}
        echo "✓ Deleted $EXTRA extra files"
    fi
    
    # 3. 디스크 사용량 확인
    DISK_USAGE=$(du -sh $EVAL_DIR | cut -f1)
    echo "Disk usage: $DISK_USAGE"
    
    echo "=== Cleanup Complete ==="
    
    # Cron 등록 (매일 새벽 2시 실행)
    # crontab -e
    # 0 2 * * * /path/to/cleanup_old_evaluations.sh >> /path/to/logs/cleanup.log 2>&1
[/code]

#### 9.2.2 사용자 지원

**일반적인 사용자 문의 및 답변**

문의 | 원인 | 해결책  
---|---|---  
"Dashboard가 느려요" | 대량 데이터 로드 | 데이터 필터링 또는 샘플링 사용  
"파일을 로드할 수 없어요" | 파일 형식 오류 | JSON 형식 확인, 예제 파일 제공  
"차트가 표시 안 돼요" | 브라우저 캐시 | Ctrl+F5 (강제 새로고침)  
"접속이 안 돼요" | 서버 다운 또는 네트워크 | 서버 상태 확인, 방화벽 확인  
"데이터가 사라졌어요" | 페이지 새로고침 | 파일로 저장 후 재로드  
  
**사용자 가이드 문서 제공**
[code] 
    # Dashboard 사용자 가이드
    
    ## 빠른 시작
    1. 브라우저에서 접속: http://dashboard.example.com
    2. 사이드바에서 "📥 데모 데이터 로드" 클릭
    3. 각 탭에서 메트릭 확인
    
    ## 자주 묻는 질문 (FAQ)
    Q1. 데이터는 어디에 저장되나요?
    A1. 서버의 evaluation_results/ 디렉토리에 저장됩니다.
    
    Q2. 여러 명이 동시에 사용할 수 있나요?
    A2. 네, 각 사용자는 독립적인 세션을 가집니다.
    
    Q3. 데이터를 다운로드할 수 있나요?
    A3. Export 탭에서 CSV/JSON 형식으로 다운로드 가능합니다.
        ⚡ : CSV에는 13+ 메트릭 포함 (Layer 1 + Layer 2 + RAG)
    
    ## 문의
    - Email: support@example.com
    - Slack: #dashboard-support
[/code]

#### 9.2.3 정기 점검 체크리스트

**일일 점검 (Daily Checklist)**

항목 | 확인 사항 | 도구 | 상태  
---|---|---|---  
서버 가동 | Dashboard 접속 가능 | 브라우저 | [ ]  
디스크 공간 | < 80% 사용 | `df -h` | [ ]  
로그 확인 | 오류 메시지 없음 | `tail logs/dashboard.log` | [ ]  
응답 시간 | < 3초 | 브라우저 개발자 도구 | [ ]  
  
**주간 점검 (Weekly Checklist)**

항목 | 확인 사항 | 도구 | 상태  
---|---|---|---  
데이터 정리 | 30일 이상 파일 삭제 | cleanup 스크립트 | [ ]  
백업 | 최신 백업 존재 | `ls -lh backups/` | [ ]  
보안 패치 | Streamlit, Python 업데이트 | `pip list --outdated` | [ ]  
사용자 피드백 | 문의 사항 처리 | Slack, Email | [ ]  
  
### 9.3 시스템 모니터링

#### 9.3.1 성능 지표

**모니터링 항목**

지표 | 측정 방법 | 정상 범위 | 경고 기준  
---|---|---|---  
CPU 사용률 | `top` | < 70% | > 90% (5분 이상)  
메모리 사용률 | `free -h` | < 80% | > 90%  
디스크 I/O | `iostat` | < 80% | > 95%  
네트워크 대역폭 | `iftop` | < 80% | > 90%  
동시 접속자 | `netstat -an | grep 8501` | < 50명 | > 100명  
응답 시간 | 브라우저 개발자 도구 | < 3초 | > 10초  
  
**모니터링 스크립트**
[code] 
    #!/bin/bash
    # monitor_dashboard.sh
    
    echo "=== Dashboard Monitoring ==="
    echo "Timestamp: $(date)"
    
    # 1. CPU 사용률
    CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    echo "CPU Usage: ${CPU}%"
    
    # 2. 메모리 사용률
    MEM=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
    echo "Memory Usage: ${MEM}%"
    
    # 3. 디스크 사용률
    DISK=$(df -h / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    echo "Disk Usage: ${DISK}%"
    
    # 4. Dashboard 프로세스 확인
    DASHBOARD_PID=$(ps aux | grep streamlit | grep -v grep | awk '{print $2}')
    if [ -z "$DASHBOARD_PID" ]; then
        echo "⚠ Dashboard NOT running!"
        # 자동 재시작 (선택)
        # streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py &
    else
        echo "✓ Dashboard running (PID: $DASHBOARD_PID)"
    fi
    
    # 5. 동시 접속자 수
    CONNECTIONS=$(netstat -an | grep 8501 | grep ESTABLISHED | wc -l)
    echo "Active connections: $CONNECTIONS"
    
    # 6. 로그 오류 확인
    ERROR_COUNT=$(tail -n 100 logs/dashboard.log | grep -i "error" | wc -l)
    if [ $ERROR_COUNT -gt 0 ]; then
        echo "⚠ Errors in log: $ERROR_COUNT"
        tail -n 10 logs/dashboard.log | grep -i "error"
    else
        echo "✓ No errors in recent logs"
    fi
    
    echo "=== Monitoring Complete ==="
    
    # Cron 등록 (매 5분마다 실행)
    # crontab -e
    # */5 * * * * /path/to/monitor_dashboard.sh >> /path/to/logs/monitoring.log 2>&1
[/code]

#### 9.3.2 알림 설정

**Slack 알림 통합**
[code] 
    #!/bin/bash
    # alert_slack.sh
    
    SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    MESSAGE="$1"
    
    curl -X POST $SLACK_WEBHOOK   -H 'Content-Type: application/json'   -d "{"text": "$MESSAGE"}"
    
    # 사용 예시
    # ./alert_slack.sh "🚨 Dashboard CPU usage > 90%!"
[/code]

**자동 알림 스크립트**
[code] 
    #!/bin/bash
    # check_and_alert.sh
    
    CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 | cut -d'.' -f1)
    MEM=$(free | grep Mem | awk '{print ($3/$2) * 100.0}' | cut -d'.' -f1)
    DISK=$(df -h / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    
    # CPU 경고
    if [ $CPU -gt 90 ]; then
        ./alert_slack.sh "🚨 Dashboard CPU usage: ${CPU}% (> 90%)"
    fi
    
    # 메모리 경고
    if [ $MEM -gt 90 ]; then
        ./alert_slack.sh "⚠️ Dashboard Memory usage: ${MEM}% (> 90%)"
    fi
    
    # 디스크 경고
    if [ $DISK -gt 80 ]; then
        ./alert_slack.sh "📊 Dashboard Disk usage: ${DISK}% (> 80%)"
    fi
    
    # Dashboard 다운 확인
    if ! pgrep -f streamlit > /dev/null; then
        ./alert_slack.sh "🔴 Dashboard is DOWN! Attempting restart..."
        streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py &
    fi
[/code]

### 9.4 운영 트러블슈팅

#### 9.4.1 일반적인 운영 문제

문제 | 증상 | 원인 | 해결책  
---|---|---|---  
🔴 Dashboard 다운 | 접속 불가 | 프로세스 종료 | `streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py`  
🟠 느린 응답 | 로딩 > 10초 | 대량 데이터, 높은 CPU | 데이터 정리, 서버 업그레이드  
🟡 디스크 부족 | 100% 사용 | 오래된 파일 누적 | cleanup 스크립트 실행  
🟢 메모리 누수 | 메모리 계속 증가 | Streamlit 버그 | Dashboard 재시작  
🔵 네트워크 오류 | "Connection refused" | 방화벽, 포트 충돌 | 방화벽 확인, 포트 변경  
  
#### 9.4.2 로그 분석

**로그 파일 위치**
[code] 
    # Streamlit 로그
    ~/.streamlit/logs/
    
    # 커스텀 로그 (설정한 경우)
    ./logs/dashboard.log
    
    # 시스템 로그 (Linux)
    /var/log/syslog  # Ubuntu/Debian
    /var/log/messages  # CentOS/RHEL
[/code]

**유용한 로그 명령어**
[code] 
    # 최근 100줄 확인
    tail -n 100 ~/.streamlit/logs/*.log
    
    # 실시간 로그 모니터링
    tail -f ~/.streamlit/logs/*.log
    
    # 오류 메시지 필터링
    grep -i "error" ~/.streamlit/logs/*.log
    
    # 특정 날짜 로그 검색
    grep "2024-12-02" ~/.streamlit/logs/*.log
    
    # 오류 발생 빈도 통계
    grep -i "error" ~/.streamlit/logs/*.log | wc -l
[/code]

#### 9.4.3 긴급 복구 절차

**시나리오 1: Dashboard 완전 다운**
[code] 
    # 1. 프로세스 확인
    ps aux | grep streamlit
    # → 프로세스 없음
    
    # 2. 포트 확인
    netstat -tuln | grep 8501
    # → 포트 사용 중이면 다른 프로세스 종료
    
    # 3. Dashboard 재시작
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py --server.port 8501 &
    
    # 4. 접속 확인
    curl http://localhost:8501
    # → HTTP 200 응답 확인
    
    # 5. 로그 확인
    tail -f ~/.streamlit/logs/*.log
    # → 오류 메시지 없는지 확인
[/code]

**시나리오 2: 데이터 손상**
[code] 
    # 1. 백업에서 복구
    cd backups/
    tar -xzf eval_20241201.tar.gz -C ../
    
    # 2. 파일 무결성 확인
    python -c "import json; json.load(open('evaluation_results/test.json'))"
    # → JSON 파싱 오류 없는지 확인
    
    # 3. Dashboard에서 재로드
    # 사이드바 → 파일 선택 → 로드
[/code]

### 9.5 유지보수 및 업그레이드

#### 9.5.1 정기 유지보수

**월간 유지보수 체크리스트**

작업 | 설명 | 명령어 | 상태  
---|---|---|---  
1\. 패키지 업데이트 | 보안 패치 적용 | `pip install --upgrade streamlit agent-evaluator` | [ ]  
2\. 로그 파일 정리 | 1개월 이상 로그 삭제 | `find logs/ -mtime +30 -delete` | [ ]  
3\. 백업 검증 | 백업 복구 테스트 | `tar -tzf backups/latest.tar.gz` | [ ]  
4\. 보안 점검 | 취약점 스캔 | `pip-audit` | [ ]  
5\. 성능 리뷰 | 월간 성능 리포트 작성 | 모니터링 데이터 분석 | [ ]  
  
#### 9.5.2 업그레이드 절차

**Step 1: 업그레이드 준비**
[code] 
    # 1. 현재 버전 확인
    streamlit --version
    python -c "import agent_evaluator; print(agent_evaluator.__version__)"
    
    # 2. 전체 백업
    tar -czf backup_before_upgrade_$(date +%Y%m%d).tar.gz     evaluation_results/ golden_datasets/ thresholds/ logs/
    
    # 3. 릴리스 노트 확인
    # https://docs.streamlit.io/library/changelog
[/code]

**Step 2: 업그레이드 실행**
[code] 
    # 1. Dashboard 중지
    pkill -f streamlit
    
    # 2. 패키지 업그레이드
    pip install --upgrade streamlit
    pip install --upgrade agent-evaluator
    
    # 3. 의존성 확인
    pip check
    
    # 4. Dashboard 재시작
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py &
    
    # 5. 버전 확인
    streamlit --version  # 1.31.0 (업그레이드됨)
[/code]

**Step 3: 업그레이드 검증**

검증 항목 | 방법 | 예상 결과 | 상태  
---|---|---|---  
Dashboard 기동 | 브라우저 접속 | 정상 로딩 | [ ]  
데이터 로드 | 기존 파일 로드 | 오류 없이 로드 | [ ]  
모든 탭 확인 | 탭별 클릭 | 차트 정상 표시 | [ ]  
Export 기능 | CSV 다운로드 | 파일 정상 생성 | [ ]  
성능 확인 | 응답 시간 측정 | < 3초 | [ ]  
  
**Step 4: 롤백 (문제 발생 시)**
[code] 
    # 1. Dashboard 중지
    pkill -f streamlit
    
    # 2. 이전 버전으로 다운그레이드
    pip install streamlit==1.30.0
    pip install agent-evaluator==0.5.0
    
    # 3. 백업 복구 (필요 시)
    tar -xzf backup_before_upgrade_20241202.tar.gz
    
    # 4. Dashboard 재시작
    streamlit run Evaluator_Examples/Dashboard/streamlit_dashboard.py &
    
    # 5. 정상 동작 확인
[/code]

#### 9.5.3 장애 대응 매뉴얼

**P0 (Critical) - 전체 서비스 다운**

단계 | 시간 | 조치 | 담당  
---|---|---|---  
1\. 탐지 | T+0 | 모니터링 알림 또는 사용자 보고 | 자동/운영팀  
2\. 확인 | T+5분 | 서버 접속, 프로세스 확인 | 운영팀  
3\. 긴급 조치 | T+10분 | Dashboard 재시작 | 운영팀  
4\. 공지 | T+15분 | 사용자에게 복구 완료 공지 | 운영팀  
5\. 원인 분석 | T+1시간 | 로그 분석, 근본 원인 파악 | 운영팀 + 개발팀  
6\. 재발 방지 | T+1일 | 모니터링 강화, 자동 복구 설정 | 운영팀  
  
**✅ 운영자 핵심 원칙**

  1. **선제적 모니터링** : 문제가 발생하기 전에 탐지
  2. **자동화** : 반복 작업은 스크립트로 자동화
  3. **백업 철저** : 매주 백업, 월간 복구 테스트
  4. **신속한 대응** : P0 문제는 15분 내 복구
  5. **문서화** : 모든 조치 사항 기록
  6. **사용자 중심** : 사용자 불편 최소화
  7. **지속적 개선** : 월간 성능 리뷰 및 개선

**⚠️ 주의사항**

  * ❌ **프로덕션에서 직접 수정 금지** : 테스트 환경에서 먼저 검증
  * ❌ **백업 없이 업그레이드 금지** : 항상 백업 후 진행
  * ❌ **로그 무시 금지** : 정기적으로 로그 확인
  * ❌ **단독 대응 금지** : 중요 작업은 2명 이상 확인

* * *

## 참고 자료

  * [메트릭 가이드](<METRICS_GUIDE.md>): 모든 지표 상세 설명
  * [API 문서](<API.md>): 프로그래밍 방식 접근
  * [프레임워크 통합](<FRAMEWORK_INTEGRATION.md>): CrewAI, AutoGen 등

* * *

**최종 업데이트** : 2025-12-16  
**버전** : v0.5.0  
**프로젝트** : Agent Evaluator - AI Agent Performance Evaluation System
