# Appendix B. CLI 명령어 완전 레퍼런스

Agent Evaluator v0.7.4 CLI 전체 명령어 목록. `pip install agent-evaluator` 설치 후 바로 사용 가능하다.

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
2. OpenAI API 키 입력 요청 (LLM Judge, AccuracyEvaluator에 필요)
3. Anthropic API 키 입력 요청 (LLM Judge 대안)
4. Slack Webhook URL 입력 요청 (알림 기능, 선택)
5. `.env` 파일 생성 또는 업데이트

**출력 예시**

```
Agent Evaluator 설정 마법사
===========================
[1/3] OpenAI API 키 (LLM Judge 사용 시 필요): sk-...
[2/3] Anthropic API 키 (선택): ...
[3/3] Slack Webhook URL (선택): ...
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
Agent Evaluator v0.7.4 설정 상태
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
| `--quality` | float | Response Quality 최소값 (0~5) |
| `--hallucination` | float | Hallucination Rate 최대값 (%) |
| `--config` | 파일경로 | JSON 설정 파일에서 임계값 로드 |

**예시**

```bash
# 직접 임계값 지정
agent-eval gate result.json --tcr 85 --accuracy 70

# 여러 임계값 동시 지정
agent-eval gate result.json --tcr 90 --accuracy 80 --quality 4.0

# 설정 파일 사용
agent-eval gate result.json --config gate_config.json
```

**gate_config.json 형식**

```json
{
    "tcr": 85.0,
    "accuracy": 70.0,
    "quality": 4.0,
    "hallucination": 5.0
}
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

골든 데이터셋 관리 서브커맨드. 평가 결과에서 고품질 케이스를 자동으로 추출하여 골든 데이터셋으로 저장한다.

**사용법**

```bash
agent-eval dataset build <결과디렉토리> [옵션]
```

**옵션**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--min-score` | 0.8 | 최소 점수 임계값 (0.0~1.0) |
| `--output` | data/golden_datasets/ | 저장 경로 |

**예시**

```bash
# 기본 추출 (점수 0.8 이상)
agent-eval dataset build results/

# 고품질 기준 강화
agent-eval dataset build results/ --min-score 0.9

# 저장 경로 지정
agent-eval dataset build results/ --output data/golden/ --min-score 0.85
```

**동작 방식**

1. 결과 디렉토리의 모든 JSON 파일을 스캔
2. `completion_score × accuracy_score` 기반으로 고품질 케이스 선별
3. `GoldenSetBuilder`를 통해 골든 데이터셋 파일로 저장
4. 기존 골든 데이터셋과 자동 병합

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
| `--port` | 6006 | Phoenix 서버 포트 |
| `--check` | False | OTEL 패키지 설치 여부 및 포트 상태만 확인 |

**예시**

```bash
# 기본 실행 (포트 6006)
agent-eval monitor

# 포트 변경
agent-eval monitor --port 6007

# 설치 상태만 확인 (서버 미기동)
agent-eval monitor --check
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
agent-evaluator 0.7.4
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
