# Appendix B. CLI 명령어 완전 레퍼런스

Agent Evaluator v0.9.7 CLI 전체 명령어 목록. `pip install agent-evaluator` 설치 후 바로 사용 가능하다.

> **설계 철학**: `agent-eval` CLI는 Harness Gate(A–G)를 CI/CD 파이프라인에 통합하는 인터페이스다. Python 코드에서 선언한 Harness Config(InstructionConfig, SLAConfig 등)가 JSON 결과 파일로 저장되면, CLI가 이를 읽어 Gate 판정·트렌드 분석·시각화를 수행한다. 배포 전 자동 검증(`gate`), 누적 품질 추적(`trend`), 실시간 관측(`monitor`), 대화형 분석(`dashboard`)을 하나의 도구로 커버한다.

---

## 전체 명령어 목록

| 명령어 | 용도 |
|--------|------|
| `agent-eval init` | 대화형 API 키 설정 마법사 |
| `agent-eval check` | 현재 설정 상태 출력 |
| `agent-eval dashboard` | FastAPI 대시보드 실행 |
| `agent-eval gate` | CI/CD 품질 게이팅 (단일 결과 검사) |
| `agent-eval trend` | 다중 결과 트렌드 분석 + 회귀 감지 |
| `agent-eval dataset` | 골든 데이터셋 관리 |
| `agent-eval monitor` | Arize Phoenix 서버 기동 + OTEL 설정 |
| `agent-eval --version` | 버전 출력 |

---

## agent-eval init

대화형으로 API 키를 설정하고 `.env` 파일을 자동 생성하는 마법사.

**사용법**

```bash
agent-eval init
```

**동작 순서**

1. 현재 디렉토리에 `.env` 파일이 존재하는지 확인
2. OpenAI API 키 입력 요청 (LLM Judge, DeepEval, Ragas에 필요)
3. Anthropic API 키 입력 요청 (LLM Judge 대안)
4. `.env` 파일 생성 또는 업데이트

**출력 예시**

```
Agent Evaluator 설정 마법사
===========================
[1/2] OpenAI API Key (선택): sk-...
[2/2] Anthropic API Key (선택): sk-ant-...
.env 파일이 생성되었습니다.
```

**주의**: API 키 미입력 시 해당 기능(LLM Judge, 알림)이 비활성 상태로 동작한다.

---

## agent-eval check

현재 설정 상태와 설치된 선택적 의존성(extras)을 출력한다.

**사용법**

```bash
agent-eval check
```

**출력 항목**

- `.env` 파일 존재 여부
- 환경변수 설정 상태 (API 키 마스킹 표시)
- 설치된 extras 목록 (langchain, crewai, autogen, eval, serve, otel 등)
- 사용 가능한 기능 요약

**출력 예시**

```
Agent Evaluator v0.9.7 설정 상태
=================================
.env 파일: /Users/username/project/.env (존재)

환경변수:
  OPENAI_API_KEY:    sk-...abc (설정됨)
  ANTHROPIC_API_KEY: 미설정
  SLACK_WEBHOOK_URL: 미설정

기본 설치 포함 기능:
  LLM Judge:   ✅ openai, anthropic (API 키 필요)
  대시보드:    ✅ fastapi, uvicorn, jinja2
  OTEL 모니터: ✅ opentelemetry-sdk, arize-phoenix

추가 설치 extras:
  [langchain]  ❌ 미설치 (LangChain 에이전트 사용 시 필요)
  [eval]       ❌ 미설치 (DeepEval/Ragas 외부 평가 도구 필요 시)

사용 가능한 기능:
  LLM Judge:   ✅ (OPENAI_API_KEY 감지)
  대시보드:    ✅ (기본 설치에 포함)
  OTEL 모니터: ✅ (기본 설치에 포함)
```

---

## agent-eval dashboard

FastAPI 기반 평가 결과 대시보드를 실행한다. 9개 탭(품질, 성능, 에이전틱, 보안, 멀티턴 대화, 이상 감지, 평가 비용, 골든 데이터셋, 투명성)으로 구성된다.

각 탭이 커버하는 Gate:

| 탭 | 커버 Gate | 주요 지표 |
|----|-----------|---------|
| 품질 | A (목표달성) | TCR, Accuracy, Response Quality |
| 성능 | D (성능계약) | Latency P50/P95/P99, Token Economy |
| 에이전틱 | B (행동무결성), F (다중에이전트) | Tool Call, Workflow, Coordination |
| 보안 | E (보안경계) | InputSanitization, OutputLeakage, ToolAuth |
| 멀티턴 대화 | A, B, G | ConversationMetrics, context_retention |
| 이상 감지 | 전체 Gate | AnomalyDetector (통계적 이상치) |
| 평가 비용 | D (비용 부분) | Token/API 비용 추적 |
| 골든 데이터셋 | 전체 | GoldenSetBuilder 관리 케이스 |
| 투명성 | G (운영관측성) | TestTransparencyManager 추적 |

**사용법**

```bash
agent-eval dashboard [결과디렉토리] [옵션]
```

**옵션**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | 8765 | 서버 포트 |
| `--host` | 127.0.0.1 | 서버 호스트 |
| `--watch` | False | 파일 변경 감시 + 자동 새로고침 |

**예시**

```bash
# 기본 실행 (현재 디렉토리 results/ 자동 탐색)
agent-eval dashboard

# 특정 디렉토리 지정
agent-eval dashboard results/

# 실시간 감시 모드로 포트 변경
agent-eval dashboard results/ --watch --port 9000

# 외부 접근 허용
agent-eval dashboard results/ --host 0.0.0.0 --port 8765
```

**사전 조건**

- `pip install agent-evaluator` 기본 설치 (대시보드 포함)
- 결과 디렉토리에 `*.json` 평가 결과 파일 존재 필요 (`save_to_file()` 호출로 생성)

**주의**: 데이터가 없으면 대시보드가 빈 상태로 표시된다. `monitor.save_to_file("evaluation")` 호출 후 실행할 것.

---

## agent-eval gate

평가 결과 JSON 파일을 읽어 설정한 임계값과 비교한다. 임계값 미달 시 `sys.exit(1)`로 종료하여 CI/CD 파이프라인을 차단한다.

> **참고**: `agent-eval gate`는 Python API의 `HarnessEvaluationGate`를 CLI로 래핑한 명령어다. Config-as-Code로 선언한 Harness Config(InstructionConfig, SLAConfig 등)를 JSON 결과에 적용해 Gate A-G 전체를 한 번에 판정한다. Python 코드에서 직접 사용하려면 `from agent_evaluator import HarnessEvaluationGate`를 참고한다.

**사용법**

```bash
agent-eval gate <result.json> [옵션]
```

**옵션**

| 옵션 | 타입 | 설명 |
|------|------|------|
| `--tcr` | float | Task Completion Rate 최소값 (%) |
| `--accuracy` | float | Accuracy 최소값 (%) |
| `--p95-latency` | float | P95 레이턴시 최대값 (초) |
| `--hallucination` | float | Hallucination Rate 최대값 (%) |
| `--llm-judge` | float | LLM Judge 종합 점수 최소값 (0~5) |
| `--min-gate-score` | float | Harness Gate A–G 가중 복합 점수 최소값 (0.0–1.0) |
| `--group-weights` | 문자열 | Gate별 가중치 (예: `A:2.0,E:3.0`) |
| `--gate-thresholds` | 문자열 | Gate별 개별 점수 임계값 (예: `A:0.8,E:0.9`) |
| `--required-gates` | 문자열 | 필수 통과 Gate 목록 (예: `A,E`) — 나머지는 경고만 발생 |
| `--fail-on-gate-warn` | flag | Gate 경고 시에도 종료 코드 1 반환 (기본: 경고는 통과) |
| `--fail-on-regression` | float | 기준선 대비 허용 회귀율 (%) |
| `--baseline` | 파일경로 | 기준선 파일 경로 (기본: `<result_dir>/baseline.json`) |
| `--save-baseline` | flag | 현재 결과를 기준선으로 저장 |
| `--junit-xml` | 파일경로 | JUnit XML 결과 파일 경로 (CI 시스템 연동) |

**예시**

```bash
# 직접 임계값 지정
agent-eval gate result.json --tcr 85 --accuracy 70

# 여러 임계값 동시 지정
agent-eval gate result.json --tcr 90 --accuracy 80 --p95-latency 3.0 --hallucination 5

# LLM Judge 점수 게이팅
agent-eval gate result.json --tcr 85 --llm-judge 3.5

# 기준선 저장 후 회귀 감지
agent-eval gate result.json --save-baseline
agent-eval gate result.json --tcr 85 --fail-on-regression 10

# JUnit XML 출력 (CI 통합)
agent-eval gate result.json --tcr 85 --junit-xml test-results/gate-results.xml

# Gate A–G 가중 복합 점수 게이팅
agent-eval gate result.json --min-gate-score 0.7

# Gate별 가중치 지정 — Gate A와 E를 더 엄격하게 판정
agent-eval gate result.json --min-gate-score 0.7 --group-weights A:2.0,E:3.0
```

**종료 코드**

| 코드 | 의미 |
|------|------|
| `0` | 모든 임계값 통과 |
| `1` | 임계값 미달 (배포 차단) |
| `2` | `--fail-on-regression` 지정 시 기준선 대비 회귀 초과 |

**적정 임계값 자동 제안**

현재 측정값의 95% 수준을 임계값으로 자동 계산하여 저장한다.

```python
from agent_evaluator import QuickEval

eval_q = QuickEval("results/")
# ... 평가 실행 후
eval_q.generate_gate_config("gate_config.json")
```

**CI/CD 통합 예시 (GitHub Actions)**

```yaml
- name: 품질 게이팅
  run: agent-eval gate results/evaluation.json --tcr 85 --accuracy 70
```

---

## agent-eval trend

여러 평가 결과 파일에서 시간 흐름에 따른 지표 추이를 분석한다. `gate`가 단일 결과를 점검하는 반면, `trend`는 N회 실행의 기울기(slope)로 개선·회귀 방향을 판정한다. CI/CD에서 `--fail-on-regression`을 지정하면 회귀 감지 시 종료 코드 **1**을 반환한다.

**사용법**

```bash
agent-eval trend <결과디렉토리> [옵션]
```

**옵션**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `결과디렉토리` | (필수) | 평가 결과 JSON 파일이 저장된 디렉토리 |
| `--window`, `-w` | `10` | 분석할 최근 파일 수 |
| `--pattern` | `*.json` | 파일 이름 글로브 패턴 |
| `--slope-threshold` | `0.3` | 이 절댓값 미만의 slope는 `stable`로 판정 (단위: %/run 또는 초/run). slope 계산 공식은 Appendix H §H.6 참고 |
| `--fail-on-regression` | — | 회귀 감지 시 종료 코드 1 반환 |
| `--output-json` | — | 분석 결과를 JSON 파일로 저장 |

**종료 코드**

| 코드 | 의미 |
|------|------|
| `0` | 회귀 없음 (또는 `--fail-on-regression` 미지정) |
| `1` | 회귀 감지 (`--fail-on-regression` 지정 시) |

> **참고**: `trend` 실패(회귀 감지) 시 종료 코드 `1`을 반환한다. `gate`는 임계값 미달 시 `1`, `--fail-on-regression` 회귀 초과 시 `2`를 반환한다. CI/CD 파이프라인에서 두 명령어를 별도 스텝으로 실행하면 어느 스텝이 실패했는지로 원인을 구분할 수 있다.

**분석 지표**

- **TCR** (Task Completion Rate): slope > 0 → improving, < 0 → degrading
- **Accuracy**: slope > 0 → improving
- **P95 Latency**: slope > 0 → degrading (지연 증가)
- **Hallucination Rate**: slope > 0 → degrading (환각 증가)

**예시**

```bash
# 기본 트렌드 분석 (최근 10개 파일)
agent-eval trend results/

# 최근 5개 파일만 분석
agent-eval trend results/ --window 5

# 특정 파일 패턴으로 필터링
agent-eval trend results/ --pattern '*quality*.json' --window 20

# 회귀 감지 시 CI/CD 중단
agent-eval trend results/ --fail-on-regression

# 민감도 조정 + 결과 저장
agent-eval trend results/ --slope-threshold 0.5 --output-json trend_report.json
```

**출력 예시**

```
트렌드 분석 결과 (최근 10회 실행)
====================================
지표              방향        slope
─────────────────────────────────────
TCR               improving   +1.23 %/run
Accuracy          stable       +0.12 %/run
P95 Latency       stable       +0.05 초/run
Hallucination     degrading   +0.87 %/run  ⚠️

⚠️ 회귀 감지: Hallucination Rate 상승 추세
```

**`gate`와의 차이**

| 항목 | `gate` | `trend` |
|------|--------|---------|
| 대상 | 단일 결과 파일 | 디렉토리 내 N개 파일 |
| 판정 방식 | 절댓값 임계값 비교 | slope(기울기) 방향 판정 |
| 주요 용도 | 현재 빌드 pass/fail | 시간 흐름에 따른 품질 변화 감지 |
| CI 통합 | 배포 전 게이트 | 주간/스프린트 리포트, 회귀 경보 |

**CI/CD 통합 예시 (GitHub Actions)**

```yaml
- name: 트렌드 회귀 감지
  run: agent-eval trend results/ --window 10 --fail-on-regression
```

---

## agent-eval dataset

골든 데이터셋 관리 서브커맨드. 평가 결과에서 케이스를 자동으로 추출하여 골든 데이터셋으로 저장한다.

**사용법**

```bash
agent-eval dataset build [옵션]
```

**옵션**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--source` | `./results` | 평가 결과 JSON 파일이 저장된 디렉토리 |
| `--output` | `<source>/golden_datasets/` | 골든셋 출력 디렉토리 |
| `--strategy` | `failure_cases edge_cases` | 추출 전략 (복수 지정 가능): `failure_cases`, `edge_cases`, `high_value`, `coverage_gap` |
| `--max-cases` | 50 | 추출할 최대 케이스 수 |
| `--no-review` | False | 사람 검토 없이 바로 저장 |
| `--name` | 자동 생성 | 저장 파일 이름 (`candidates_YYYYMMDD_HHMMSS.json`) |

**예시**

```bash
# 기본 추출 (기본값: ./results, 최대 50개)
agent-eval dataset build

# 결과 디렉토리 지정
agent-eval dataset build --source results/

# 고품질 케이스 중심 추출
agent-eval dataset build --source results/ --strategy high_value failure_cases

# 저장 경로 및 케이스 수 지정
agent-eval dataset build --source results/ --output data/golden/ --max-cases 30
```

**동작 방식**

1. 결과 디렉토리의 모든 JSON 파일을 스캔
2. 지정한 전략(`--strategy`)으로 케이스 선별 (실패 케이스, 엣지 케이스, 고가치 케이스 등)
3. `GoldenSetBuilder`를 통해 골든 데이터셋 파일로 저장

---

## agent-eval monitor

Arize Phoenix 서버를 기동하고 OTLP 스팬 수신 환경을 설정한다. 운영 단계 실시간 모니터링에 사용한다.

**사용법**

```bash
agent-eval monitor [옵션]
```

**옵션**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | `6006` | Phoenix UI + OTLP HTTP 포트 |
| `--host` | `localhost` | Phoenix 바인딩 호스트 |
| `--no-open` | — | 브라우저 자동 오픈 비활성화 |
| `--attach <url>` | — | 자체 기동 없이 기존 Phoenix에 연결 |
| `--check` | — | 설치 상태 및 포트 점유 확인 |
| `--working-dir <path>` | `./` | Phoenix DB 저장 디렉토리 |
| `--sync-datasets <glob>` | — | 골든셋 JSON 파일을 Phoenix Datasets로 업로드 |
| `--reset` | — | Phoenix DB를 삭제하고 초기화 (데이터 전체 삭제) |
| `--yes`, `-y` | — | `--reset` 확인 프롬프트를 건너뜀 |

**예시**

```bash
# 기본 실행 (포트 6006)
agent-eval monitor

# 포트 변경
agent-eval monitor --port 6007

# 설치 상태만 확인 (서버 미기동)
agent-eval monitor --check

# 기존 Phoenix 서버에 연결 (자체 기동 없음)
agent-eval monitor --attach http://localhost:6006

# 골든셋 자동 업로드
agent-eval monitor --sync-datasets 'data/golden_datasets/*.json'

# Phoenix DB 초기화 (모든 트레이스·데이터 삭제)
agent-eval monitor --reset

# 초기화 확인 프롬프트 생략 (CI/CD 비대화형 환경)
agent-eval monitor --reset --yes
```

> **주의**: `--reset`은 Phoenix DB에 저장된 모든 트레이스, 데이터셋, Evaluators 결과를 삭제한다. 복구 불가능하므로 신중하게 사용할 것.

**사전 조건**

```bash
# OTEL 모니터링은 기본 설치에 포함
pip install agent-evaluator
```

**동작 순서**

1. Phoenix 패키지 설치 확인
2. 지정 포트 사용 가능 여부 확인
3. Phoenix 서버 기동 (`http://localhost:6006`)
4. OTLP 엔드포인트 설정 (`http://localhost:6006/v1/traces`)
5. 코드에서 `setup_otel()` 호출 시 자동 연결됨

**코드 연동**

```python
from agent_evaluator import PerformanceMonitor, setup_otel

# setup_otel()은 PerformanceMonitor 생성 이전에 호출해야 함
setup_otel(
    endpoint="http://localhost:6006",
    service_name="my-agent",
)
monitor = PerformanceMonitor(output_dir="results/", use_korean_tokenizer=True)
```

**주의**: `setup_otel()` endpoint에 `/v1/traces` 경로를 붙이지 말 것. SDK가 자동으로 추가한다.

---

## agent-eval --version

설치된 버전을 출력한다.

**사용법**

```bash
agent-eval --version
```

**출력 예시**

```
agent-evaluator 0.9.5
```

---

## 환경변수가 CLI 동작에 미치는 영향

| 환경변수 | 영향받는 명령어 | 설명 |
|---------|--------------|------|
| `OPENAI_API_KEY` | `gate`, `dashboard` | LLM Judge 자동 활성화 |
| `ANTHROPIC_API_KEY` | `gate`, `dashboard` | Anthropic LLM Judge 사용 |
| `SLACK_WEBHOOK_URL` | `dashboard` | 알림 핸들러 실제 전송 활성 |
| `AGENT_EVALUATOR_WEBHOOK_URL` | `dashboard` | 일반 웹훅 알림 활성 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `monitor` | OTLP 수집 엔드포인트 오버라이드 |
| `PHOENIX_HOST` / `PHOENIX_PORT` | `monitor` | Phoenix 서버 호스트·포트 오버라이드 |

API 키가 미설정된 경우 해당 기능은 비활성 상태로 동작하며 오류는 발생하지 않는다.
