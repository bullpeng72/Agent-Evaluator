# Appendix B. CLI 명령어 완전 레퍼런스

Agent Evaluator v0.7.7 CLI 전체 명령어 목록. `pip install agent-evaluator` 설치 후 바로 사용 가능하다.

---

## 전체 명령어 목록

| 명령어 | 용도 |
|--------|------|
| `agent-eval init` | 대화형 API 키 설정 마법사 |
| `agent-eval check` | 현재 설정 상태 출력 |
| `agent-eval dashboard` | FastAPI 대시보드 실행 |
| `agent-eval gate` | CI/CD 품질 게이팅 |
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
Agent Evaluator v0.7.7 설정 상태
=================================
.env 파일: /Users/username/project/.env (존재)

환경변수:
  OPENAI_API_KEY:    sk-...abc (설정됨)
  ANTHROPIC_API_KEY: 미설정
  SLACK_WEBHOOK_URL: 미설정

설치된 extras:
  [llm]     ✅ openai, anthropic
  [serve]   ✅ fastapi, uvicorn, jinja2
  [langchain] ❌ 미설치
  [otel]    ❌ 미설치

사용 가능한 기능:
  LLM Judge:   ✅ (OPENAI_API_KEY 감지)
  대시보드:    ✅ ([serve] 설치됨)
  OTEL 모니터: ❌ (pip install "agent-evaluator[otel]" 필요)
```

---

## agent-eval dashboard

FastAPI 기반 평가 결과 대시보드를 실행한다. 9개 탭(품질, 성능, 에이전틱, 보안, 멀티턴 대화, 이상 감지, 평가 비용, 골든 데이터셋, 투명성)으로 구성된다.

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

- `pip install "agent-evaluator[serve]"` 설치 필요
- 결과 디렉토리에 `*.json` 평가 결과 파일 존재 필요 (`save_to_file()` 호출로 생성)

**주의**: 데이터가 없으면 대시보드가 빈 상태로 표시된다. `monitor.save_to_file("evaluation")` 호출 후 실행할 것.

---

## agent-eval gate

평가 결과 JSON 파일을 읽어 설정한 임계값과 비교한다. 임계값 미달 시 `sys.exit(1)`로 종료하여 CI/CD 파이프라인을 차단한다.

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
```

**적정 임계값 자동 제안**

현재 측정값의 95% 수준을 임계값으로 자동 계산하여 저장한다.

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")
# ... 평가 실행 후
eval.generate_gate_config("gate_config.json")
```

**CI/CD 통합 예시 (GitHub Actions)**

```yaml
- name: 품질 게이팅
  run: agent-eval gate results/evaluation.json --tcr 85 --accuracy 70
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
| `--source` | `./results` | 결과 JSON 파일 디렉토리 |
| `--output` | `<source>/golden_datasets/` | 골든셋 출력 디렉토리 |
| `--strategy` | `failure_cases edge_cases` | 추출 전략 (복수 지정 가능): `failure_cases`, `edge_cases`, `high_value`, `coverage_gap` |
| `--max-cases` | 50 | 추출할 최대 케이스 수 |
| `--no-review` | False | 사람 검토 없이 바로 저장 |
| `--name` | 자동 생성 | 저장 파일 이름 (`candidates_YYYYMMDD_HHMMSS.json`) |

**예시**

```bash
# 기본 추출 (실패 케이스 + 엣지 케이스, 최대 50개)
agent-eval dataset build

# 소스 디렉토리 지정
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
```

**사전 조건**

```bash
pip install "agent-evaluator[otel]"
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
monitor = PerformanceMonitor(output_dir="results/")
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
agent-evaluator 0.7.7
```

---

## 환경변수가 CLI 동작에 미치는 영향

| 환경변수 | 영향받는 명령어 | 설명 |
|---------|--------------|------|
| `OPENAI_API_KEY` | `gate`, `dashboard` | LLM Judge 자동 활성화 |
| `ANTHROPIC_API_KEY` | `gate`, `dashboard` | Anthropic LLM Judge 사용 |
| `SLACK_WEBHOOK_URL` | `dashboard` | 알림 핸들러 실제 전송 활성 |
| `ALERT_WEBHOOK_URL` | `dashboard` | 일반 웹훅 알림 활성 |
| `OTEL_ENABLED` | `monitor` | OTEL 수집 전역 활성화 |
| `PHOENIX_ENDPOINT` | `monitor` | Phoenix 서버 주소 오버라이드 |

API 키가 미설정된 경우 해당 기능은 비활성 상태로 동작하며 오류는 발생하지 않는다.
