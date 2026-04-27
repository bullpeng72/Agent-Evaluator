# Appendix C. 환경변수 & 설정 레퍼런스

Agent Evaluator v0.9.1에서 사용하는 환경변수와 `.env` 파일 설정 전체를 정리한다.

> **Harness Engineering 관점**: 환경변수는 단순한 설정값이 아니다. 개발·스테이징·프로덕션 환경마다 다른 LLM 판정 모델, 다른 OTEL 엔드포인트, 다른 알림 채널을 주입함으로써 **동일한 코드(Harness Config)가 환경별로 독립적인 Gate 기준을 갖출 수 있게 하는 핵심 메커니즘**이다.

---

> ### API 키는 절대 코드에 하드코딩 금지
>
> API 키(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등)를 소스 코드에 직접 작성하면 Git 히스토리에 영구적으로 남고 유출 시 회수가 불가능하다. 반드시 `.env` 파일 또는 시크릿 관리 시스템을 통해 주입해야 한다.
>
> ```python
> # 잘못된 예 — 절대 하지 말 것
> client = openai.OpenAI(api_key="sk-proj-abc123...")  # ❌
>
> # 올바른 예
> import os
> client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # ✅
> ```

---

## .env 파일 패턴

프로젝트 루트의 `.env` 파일에 설정을 모아두는 방식을 권장한다. `agent-eval init` 명령어로 대화형 생성이 가능하다. `python-dotenv`는 기본 설치에 포함되어 있어 별도 설치 없이 바로 사용할 수 있다.

아래는 모든 환경변수를 포함한 완전한 `.env` 예시다. 실제 사용하는 항목만 남기고 나머지는 삭제하거나 주석 처리한다.

```bash
# ============================================================
# Agent Evaluator — 완전한 .env 예시 (v0.9.1)
# ============================================================

# ------------------------------------------------------------
# [필수] LLM API 키 — 최소 하나는 설정해야 LLM Judge 사용 가능
# ------------------------------------------------------------
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...        # Gemini / Vertex AI 어댑터 사용 시

# ------------------------------------------------------------
# [선택] LLM Judge 공급자 선택 (v0.8.3+)
# auto     = API 키 기반 자동 결정 (기본값, Anthropic 우선)
# openai   = OpenAI 모델 강제
# anthropic = Anthropic 모델 강제
# ------------------------------------------------------------
AGENT_EVALUATOR_JUDGE_PROVIDER=auto

# ------------------------------------------------------------
# [선택] 대시보드 포트 (기본: 8765)
# ------------------------------------------------------------
# AGENT_EVAL_DASHBOARD_PORT=8765

# ------------------------------------------------------------
# [선택] OTEL / Phoenix 모니터링
# ------------------------------------------------------------
# OTEL_ENABLED=true
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # 표준 OTEL gRPC 엔드포인트
# PHOENIX_ENDPOINT=http://localhost:6006              # Phoenix UI + HTTP 수신

# ------------------------------------------------------------
# [선택] 알림
# ------------------------------------------------------------
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
# ALERT_WEBHOOK_URL=https://your-server.com/webhooks/alert
```

코드에서 로드하는 방법:

```python
from agent_evaluator import load_env, get_settings

load_env()                  # .env 파일 로드 (python-dotenv 래퍼)
settings = get_settings()   # 설정 딕셔너리 반환
print(settings)
```

`.env` 파일은 `.gitignore`에 반드시 추가하여 버전 관리에서 제외해야 한다.

```bash
echo ".env" >> .gitignore
```

---

## API 키 환경변수

### OPENAI_API_KEY

OpenAI API 키. 다음 기능에서 사용된다.

- `LLMJudge` — GPT 모델로 completeness / relevance / factual_consistency 채점
- 외부 평가 라이브러리 DeepEval 지표 (G-Eval, Hallucination Score, Toxicity, Bias, Answer Relevancy)
- 외부 평가 라이브러리 Ragas 지표 (Faithfulness, Context Precision 등)

```bash
export OPENAI_API_KEY=sk-proj-...
```

**주의**: Anthropic-only 환경(OpenAI 키 없음)에서는 임베딩 기반 AnswerRelevancy 지표가 자동 제외된다.

---

### ANTHROPIC_API_KEY

Anthropic Claude API 키. `LLMJudge`의 기본 또는 대안 모델로 사용된다.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`LLMJudgeConfig(model="claude-sonnet-4-6")` 지정 시 이 키가 사용된다.

```python
from agent_evaluator.decorators import agent_eval, LLMJudgeConfig

@agent_eval(monitor, task_type="qa", llm_judge=LLMJudgeConfig(model="claude-sonnet-4-6"))
def agent(question: str, ground_truth: str = "") -> str: ...
```

---

### GOOGLE_API_KEY

Gemini API 키. `framework="gemini"` 또는 `framework="vertexai"` 어댑터 사용 시 필요하다.

```bash
export GOOGLE_API_KEY=AIza...
```

---

## LLM Judge 관련 환경변수

### AGENT_EVALUATOR_JUDGE_PROVIDER

*(v0.8.3 신규)*

`LLMJudge`가 사용할 LLM 공급자를 환경 단위로 고정한다. 개발 환경에서는 비용이 낮은 OpenAI, 프로덕션 Gate 판정에서는 정확도가 높은 Anthropic을 강제하는 식으로 **환경별 Gate 기준을 코드 변경 없이 분리**할 수 있다.

| 값 | 동작 |
|----|------|
| `auto` | API 키 기반 자동 결정. `ANTHROPIC_API_KEY`가 있으면 Anthropic 우선 (기본값) |
| `openai` | `OPENAI_API_KEY`로 OpenAI 모델 강제 |
| `anthropic` | `ANTHROPIC_API_KEY`로 Anthropic 모델 강제 |

```bash
# 개발 환경 .env — 비용 절감
AGENT_EVALUATOR_JUDGE_PROVIDER=openai

# 프로덕션 환경 .env — 정확도 우선
AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic
```

코드에서 모델을 명시하면 이 환경변수보다 우선한다.

```python
# 코드 명시가 환경변수보다 우선
llm_judge=LLMJudgeConfig(model="gpt-4o-mini")   # 환경변수 무시하고 OpenAI 강제
```

---

## 대시보드 관련 환경변수

### AGENT_EVAL_DASHBOARD_PORT

FastAPI 대시보드 서버 포트. 기본값은 `8765`.

```bash
AGENT_EVAL_DASHBOARD_PORT=8765    # 기본값
AGENT_EVAL_DASHBOARD_PORT=9000    # 포트 변경
```

CLI에서도 동일하게 적용된다.

```bash
agent-eval dashboard               # 8765 포트 (기본)
# 또는 환경변수로 포트 변경 후 실행
AGENT_EVAL_DASHBOARD_PORT=9000 agent-eval dashboard
```

---

## OTEL 관련 환경변수

### OTEL_ENABLED

OTEL(OpenTelemetry) 스팬 발행 전역 활성화 여부.

```bash
OTEL_ENABLED=true     # OTEL 활성화
OTEL_ENABLED=false    # 비활성화 (기본)
```

코드에서 직접 제어하는 방법:

```python
from agent_evaluator import setup_otel

setup_otel(
    endpoint="http://localhost:4317",   # OTEL Collector 또는 Phoenix HTTP 엔드포인트
    service_name="my-agent",
    enable_metrics=False,    # Phoenix /v1/metrics 미지원이므로 False 권장
)
```

`setup_otel()`은 반드시 `PerformanceMonitor` 생성 **이전**에 호출해야 한다.

---

### OTEL_EXPORTER_OTLP_ENDPOINT

OpenTelemetry 표준 OTLP 엔드포인트. SDK가 스팬을 전송하는 기본 주소다. 기본값은 `http://localhost:4317`(gRPC).

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317    # 기본값 (OTEL Collector gRPC)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006    # Phoenix HTTP 직접 연결 시
```

`agent-eval monitor` 실행 시 Phoenix가 `6006` 포트에서 OTLP HTTP 수신을 시작한다.

---

### PHOENIX_ENDPOINT

Arize Phoenix 서버 주소. 기본값은 `http://localhost:6006`.

```bash
PHOENIX_ENDPOINT=http://localhost:6006
# 외부 서버 사용 시
PHOENIX_ENDPOINT=https://my-phoenix.company.com
```

`setup_otel()` endpoint 파라미터와 동일하게 작동한다. 경로(`/v1/traces`)는 포함하지 말 것 — SDK가 자동으로 추가한다.

**OTEL_EXPORTER_OTLP_ENDPOINT vs PHOENIX_ENDPOINT**: 두 변수가 모두 설정된 경우 `OTEL_EXPORTER_OTLP_ENDPOINT`가 우선한다. 일반적으로는 하나만 설정하면 충분하다. Phoenix를 OTEL 백엔드로 사용하는 경우 `PHOENIX_ENDPOINT`만 설정하는 것이 단순하다.

---

## 알림 관련 환경변수

### SLACK_WEBHOOK_URL

Slack 웹훅 URL. 설정 시 알림 핸들러가 실제 Slack 채널로 메시지를 전송한다. 미설정 시 Mock 핸들러로 자동 대체된다.

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

Slack 앱 설정에서 Incoming Webhooks를 활성화하고 URL을 복사하여 설정한다.

---

### ALERT_WEBHOOK_URL

일반 HTTP 웹훅 URL. 커스텀 알림 시스템(Slack 외)과 연동 시 사용한다.

```bash
ALERT_WEBHOOK_URL=https://your-server.com/webhooks/alert
```

POST 요청으로 알림 데이터(JSON 형식)가 전송된다.

---

## 기능별 필요 환경변수 표

> v0.7.8부터 LLM Judge, 대시보드, OTEL 모니터링, PDF 처리는 기본 설치에 포함됩니다. 아래 표에서 "기본 설치 포함" 항목은 별도 extras 설치 없이 사용 가능합니다.
>
> ⚠️ **v0.7.7 이전에서 업그레이드하는 경우**: `pip install --upgrade agent-evaluator`만 실행하면 충분합니다. 기존 extras(`[langchain]`, `[eval]` 등) 설정은 유지됩니다.

| 기능 / extras | 필요 환경변수 | 선택 환경변수 | 비고 |
|--------|-------------|-------------|------|
| **LLM Judge** (기본 설치 포함) | `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 중 하나 | `AGENT_EVALUATOR_JUDGE_PROVIDER` | API 키만 있으면 바로 사용 |
| **대시보드** (기본 설치 포함) | 없음 | `AGENT_EVAL_DASHBOARD_PORT`, `SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_URL` | 대시보드 자체는 키 불필요 |
| **OTEL 모니터링** (기본 설치 포함) | 없음 | `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `PHOENIX_ENDPOINT` | `agent-eval monitor`로 설정 가능 |
| `[langchain]` | `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | LangChain 모델 호출 시 |
| `[crewai]` | LLM 공급자 키 | — | CrewAI 내부 LLM 호출 시 |
| `[autogen]` | LLM 공급자 키 | — | AutoGen 내부 LLM 호출 시 |
| `[eval]` | `OPENAI_API_KEY` | — | DeepEval, Ragas 지표 계산 |
| `[dspy]` | LLM 공급자 키 | — | DSPy 프로그램 실행 시 |
| `[pydanticai]` | LLM 공급자 키 | — | PydanticAI Agent 실행 시 |

---

## agent-eval init 마법사 사용법

`agent-eval init`는 대화형으로 `.env` 파일을 생성한다.

```bash
agent-eval init
```

**생성되는 .env 파일 예시**

```bash
# Agent Evaluator Configuration
# Generated by: agent-eval init
# Date: 2026-04-09

# LLM API Keys
OPENAI_API_KEY=sk-proj-xxxx
ANTHROPIC_API_KEY=

# LLM Judge Provider (auto / openai / anthropic)
AGENT_EVALUATOR_JUDGE_PROVIDER=auto

# Dashboard
# AGENT_EVAL_DASHBOARD_PORT=8765

# Notification
SLACK_WEBHOOK_URL=

# OTEL (optional - configure with agent-eval monitor)
OTEL_ENABLED=false
PHOENIX_ENDPOINT=http://localhost:6006
```

`.env` 파일은 `.gitignore`에 반드시 추가하여 버전 관리에서 제외해야 한다.

```bash
echo ".env" >> .gitignore
```

---

## 설정 우선순위

1. 코드에서 직접 지정한 파라미터 (`LLMJudgeConfig(model="gpt-4o-mini")` 등)
2. 환경변수 (`OPENAI_API_KEY`, `AGENT_EVALUATOR_JUDGE_PROVIDER` 등)
3. `.env` 파일의 값
4. SDK 기본값

같은 설정이 여러 곳에 있을 경우 우선순위가 높은 값이 사용된다.

---

## LLMJudge 모델 선택 우선순위

동일 코드에서 여러 API 키가 설정된 경우, `LLMJudge`는 아래 순서로 모델을 선택한다.

| 우선순위 | 조건 | 사용 모델 |
|---------|------|---------|
| 1 | `LLMJudgeConfig(model="claude-...")` 명시 | 지정된 Anthropic 모델 |
| 2 | `LLMJudgeConfig(model="gpt-...")` 명시 | 지정된 OpenAI 모델 |
| 3 | `AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic` | `claude-haiku-4-5-20251001` (기본) |
| 4 | `AGENT_EVALUATOR_JUDGE_PROVIDER=openai` | `gpt-4o-mini` (기본) |
| 5 | `AGENT_EVALUATOR_JUDGE_PROVIDER=auto` 또는 미설정, `ANTHROPIC_API_KEY` 있음 | `claude-haiku-4-5-20251001` |
| 6 | `AGENT_EVALUATOR_JUDGE_PROVIDER=auto` 또는 미설정, `OPENAI_API_KEY`만 있음 | `gpt-4o-mini` |
| 7 | API 키 모두 미설정 | LLM Judge 비활성 (오류 없음) |

**예시**: `OPENAI_API_KEY`와 `ANTHROPIC_API_KEY`가 모두 설정되고 `AGENT_EVALUATOR_JUDGE_PROVIDER=auto`(기본)인 경우 Anthropic 키가 우선 사용된다. OpenAI를 강제하려면 `AGENT_EVALUATOR_JUDGE_PROVIDER=openai`로 설정하거나 `LLMJudgeConfig(model="gpt-4o-mini")`로 명시 지정한다.

---

## 환경변수와 Harness Config의 관계

환경변수는 **전역 인프라 설정**이고, Harness Config는 **태스크별 배포 기준**이다. 둘은 독립적으로 동작하며 혼동에 주의해야 한다.

| 구분 | 환경변수 | Harness Config |
|------|---------|---------------|
| 적용 범위 | 전체 프로세스 | 데코레이터/Monitor 인스턴스 단위 |
| 설정 위치 | `.env` 파일, 셸 환경 | Python 코드 (`@agent_eval(sla=SLAConfig(...))`) |
| Git 추적 | ❌ (보안상 제외) | ✅ (Config-as-Code) |
| 런타임 변경 | ✅ 가능 | ❌ 불변 (frozen dataclass) |
| 환경별 분리 | `.env` 파일 교체만으로 분리 | 코드 변경 없이 환경변수로 제어 불가 |

**핵심**: `OTEL_ENABLED=true`는 OpenTelemetry 스팬 발행을 켜지만, `ObservabilityConfig`의 배포 판정 기준과는 무관하다. 두 설정 모두 필요한 경우 독립적으로 설정한다.

```python
# 인프라 설정 (환경변수 — .env에서 환경별로 분리)
# OTEL_ENABLED=true
# AGENT_EVALUATOR_JUDGE_PROVIDER=anthropic

# 배포 기준 (Config-as-Code — 코드로 관리, 환경 무관하게 일관 적용)
from agent_evaluator import ObservabilityConfig, SLAConfig
from agent_evaluator.decorators import agent_eval

@agent_eval(
    monitor,
    sla=SLAConfig(p95_ms=3000),
    observability=ObservabilityConfig(min_coverage=0.9),
)
def agent(...): ...
```

**Harness Engineering 실천**: `.env` 파일을 환경별(`dev.env`, `staging.env`, `prod.env`)로 분리하고 CI/CD 파이프라인에서 배포 환경에 맞는 파일을 주입하면, Harness Config(Gate 기준)는 코드 한 곳에서 관리하면서 LLM 판정 모델·OTEL 엔드포인트·알림 채널을 환경별로 독립 운영할 수 있다.

---

## 보안 권장사항

- **API 키는 절대 코드에 하드코딩 금지** — Git 히스토리에 영구 기록되며 삭제해도 이전 커밋에 남는다
- `.env` 파일을 절대 git 커밋하지 말 것 (`echo ".env" >> .gitignore`)
- 프로덕션 환경에서는 환경변수를 시크릿 관리 시스템(AWS Secrets Manager, HashiCorp Vault, GitHub Secrets 등)에 저장
- CI/CD 파이프라인에서는 `OPENAI_API_KEY`를 리포지토리 시크릿으로 등록 후 주입
- API 키가 출력 로그나 에러 메시지에 노출되지 않도록 `OutputLeakageDetector` 활성화 권장

```python
# CI/CD에서 시크릿 주입 예시 (GitHub Actions)
# .github/workflows/eval.yml
# env:
#   OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
#   ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
#   AGENT_EVALUATOR_JUDGE_PROVIDER: anthropic
```
