# `agent-eval monitor` — 운영 모니터링 가이드

OpenTelemetry + Arize Phoenix 기반 프로덕션 실시간 모니터링

**Version**: 0.6.7
**Last Updated**: 2026-03-31
**Status**: 📐 설계 완료 / 구현 예정 (v0.7.x)

---

## 목차

1. [포지셔닝 — dashboard vs monitor](#포지셔닝)
2. [아키텍처 개요](#아키텍처)
3. [구현 계획 (Phase A / B / C)](#구현-계획)
4. [CLI 명세](#cli-명세)
5. [신규 모듈 구조](#신규-모듈-구조)
6. [핵심 코드 인터페이스](#핵심-코드-인터페이스)
7. [환경 설정 / 의존성](#환경-설정--의존성)
8. [사용 예시](#사용-예시)
9. [대시보드 UI 호환성](#대시보드-ui-호환성)
10. [구현 로드맵 (라운드 단위)](#구현-로드맵)

---

## 포지셔닝 {#포지셔닝}

### 두 도구의 역할 분리

| 구분 | `agent-eval dashboard` | `agent-eval monitor` |
|------|----------------------|----------------------|
| **대상** | 개발자 · QM | MLOps · 운영팀 |
| **단계** | 개발 · 검증 · 스테이징 | 프로덕션 · 운영 |
| **데이터 소스** | `save_to_file()` JSON | OTLP 스팬 스트림 (실시간) |
| **업데이트 방식** | 폴링 (15초 / --watch) | 스팬 수신 즉시 갱신 |
| **주요 뷰** | 지표 집계 · 태스크 테이블 · 히스토리 | 트레이스 · 스팬 폭포수 · 실시간 오류 |
| **저장** | JSON 파일 (results/) | PostgreSQL / SQLite (Phoenix 내부) |
| **설치 요건** | `[serve]` extras | `[otel]` extras |
| **실행 방식** | 단일 서버 | Phoenix 서버 + OTEL exporter |

### 의사결정 흐름

```
에이전트 실행
    │
    ├─▶ save_to_file()  ──────────────▶  agent-eval dashboard
    │   (JSON 집계, 항상 동작)            개발·검증 단계 지표 확인
    │
    └─▶ OTLP Span Export (opt-in) ──▶  agent-eval monitor
        (opentelemetry-sdk 설치 시)        프로덕션 실시간 트레이싱
```

---

## 아키텍처 개요 {#아키텍처}

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Application                                          │
│                                                             │
│  PerformanceMonitor.record_task()                           │
│       │                                                     │
│       ├─▶ JSON 생성 (기존 경로, 항상)                         │
│       │                                                     │
│       └─▶ OTELProvider (opt-in)                             │
│               │                                             │
│               ├─▶ Span: ae.task (task_id, metrics)          │
│               ├─▶ Span: ae.framework (langchain/crewai...)   │
│               └─▶ Metric: ae.tcr, ae.latency, ae.tokens     │
│                       │                                     │
└───────────────────────┼─────────────────────────────────────┘
                        │ OTLP/HTTP  :4318
                        ▼
              ┌─────────────────┐
              │  Arize Phoenix  │  agent-eval monitor 로 기동
              │  (OSS, pip)     │  http://localhost:6006
              │                 │
              │  • Trace 뷰     │
              │  • Span 폭포수  │
              │  • 실시간 집계  │
              │  • LLM 평가     │
              └─────────────────┘
```

### 데이터 흐름 상세

```
record_task(result)
    │
    ├─ [항상] _update_trackers()  →  JSON 집계 유지
    │
    └─ [OTELProvider 활성화 시]
           │
           ├─ tracer.start_span("ae.task")
           │       attributes:
           │         ae.task_id, ae.task_type, ae.success
           │         ae.completion_score, ae.accuracy_score
           │         ae.execution_time, ae.tokens_used
           │         ae.tool_calls_count, ae.attempts
           │         ae.framework (langchain/crewai/…)
           │
           ├─ [Phase B] framework child span
           │       ae.framework.tool_calls[]
           │       ae.framework.agent_name
           │
           └─ meter.record("ae.tcr", value, {task_type})
              meter.record("ae.latency_seconds", value)
              meter.record("ae.tokens_total", value)
              meter.record("ae.error_rate", value)
```

---

## 구현 계획 {#구현-계획}

### Phase A — 스팬 익스포트 (v0.7.0 목표)

> **원칙**: 기존 JSON 생성 경로 완전 보존. OTEL은 순수 추가.
> 기존 테스트 756개 전원 통과 유지.

**변경 범위:**

| 파일 | 변경 내용 |
|------|-----------|
| `agent_evaluator/core/otel/provider.py` | **신규** — `OTELProvider` 클래스 |
| `agent_evaluator/core/otel/metrics.py` | **신규** — `OTELMetrics` (MeterProvider 래퍼) |
| `agent_evaluator/core/otel/__init__.py` | **신규** — `setup_otel()` public API |
| `agent_evaluator/core/trackers/monitor.py` | `record_task()` 내 span 발행 훅 추가 |
| `agent_evaluator/core/monitor_context.py` | `evaluation_session` 루트 span 추가 |
| `agent_evaluator/cli/monitor.py` | **신규** — `agent-eval monitor` 서브커맨드 |
| `agent_evaluator/cli/main.py` | `monitor` 서브커맨드 등록 |
| `pyproject.toml` | `[otel]` extras 추가 |
| `agent_evaluator/__init__.py` | `setup_otel` lazy import 추가 |

**설계 원칙 — `_NoopTracer` 패턴:**

```python
# agent_evaluator/core/otel/provider.py
try:
    from opentelemetry import trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

class OTELProvider:
    def __init__(self, enabled: bool = False, ...):
        self._enabled = enabled and _HAS_OTEL
        if self._enabled:
            self._setup_real_provider(...)
        # enabled=False 또는 미설치 → 모든 메서드 no-op

    def start_span(self, name: str, attributes: dict) -> ContextManager:
        if not self._enabled:
            return _noop_span()  # 아무 일도 안 하는 컨텍스트 매니저
        return self._tracer.start_as_current_span(name, attributes=attributes)
```

### Phase B — 프레임워크 Child Span (v0.7.1 목표)

Phase A 안정화 후 진행.

**변경 범위:**

| 파일 | 변경 내용 |
|------|-----------|
| `integrations/langchain_integration.py` | `on_chain_start/end` 훅에 child span 추가 |
| `integrations/langgraph_integration.py` | 노드 진입/종료에 child span 추가 |
| `integrations/crewai_integration.py` | Task/Agent 실행에 child span 추가 |
| `integrations/autogen_integration.py` | `generate_reply` 래퍼에 child span 추가 |

**Phase B 스팬 구조 예시 (LangChain):**

```
ae.session (evaluation_session 루트)
  └─ ae.task  (task_id="task_001")
       └─ ae.framework.langchain
            ├─ ae.chain  (chain_type="ReActAgent")
            │    ├─ ae.tool_call  (tool="search", success=true)
            │    └─ ae.tool_call  (tool="calculator", success=true)
            └─ ae.llm  (model="gpt-4o", tokens=342)
```

### Phase C — JSON → Span 전환 (⚠️ 보류)

> **결정**: Phase C는 현재 대시보드 탭 절반이 동작 불능이 되므로 보류.
> `agent-eval dashboard` 탭들은 복잡한 중첩 JSON 구조에 의존하며,
> 이를 flat OTLP 속성으로 완전 대체하려면 대시보드 전면 재작성 필요.
>
> **대안**: Phoenix UI가 운영 트레이싱 전담, `agent-eval dashboard`는 개발/검증 전담.

---

## CLI 명세 {#cli-명세}

### 기본 사용법

```bash
# Phoenix 서버 기동 + OTEL exporter 설정
agent-eval monitor

# 포트 지정
agent-eval monitor --port 6006

# OTLP receiver 포트 지정 (기본 4318)
agent-eval monitor --otlp-port 4318

# 브라우저 자동 오픈 비활성화
agent-eval monitor --no-open

# 기존 Phoenix 서버에 연결 (자체 기동 안 함)
agent-eval monitor --attach http://localhost:6006

# 환경 상태 확인 (설치 여부, 포트 상태)
agent-eval monitor --check
```

### 옵션 상세

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--port` | `6006` | Phoenix 웹 UI 포트 |
| `--otlp-port` | `4318` | OTLP HTTP receiver 포트 |
| `--host` | `localhost` | Phoenix 바인딩 호스트 |
| `--no-open` | (플래그) | 브라우저 자동 오픈 비활성화 |
| `--attach <url>` | — | 자체 기동 없이 기존 Phoenix에 연결 |
| `--check` | (플래그) | 설치 상태 및 포트 점유 확인 |
| `--working-dir <path>` | `./` | Phoenix DB 저장 디렉토리 |

### 실행 시 터미널 출력

```
Agent Evaluator — 운영 모니터링

  Phoenix UI      http://localhost:6006
  OTLP Receiver   http://localhost:4318

  에이전트 코드에 아래를 추가하세요:
  ──────────────────────────────────────
  from agent_evaluator import setup_otel
  setup_otel(endpoint="http://localhost:4318")
  ──────────────────────────────────────

  Ctrl+C 로 종료
```

### `--check` 출력 예시

```
agent-eval monitor --check

✅ arize-phoenix         설치됨 (0.11.0)
✅ opentelemetry-sdk     설치됨 (1.24.0)
✅ opentelemetry-exporter-otlp-proto-http  설치됨
⚠️  포트 6006            사용 중 (다른 프로세스)
✅ 포트 4318             사용 가능

  설치 명령어:
  pip install "agent-evaluator[otel]"
```

---

## 신규 모듈 구조 {#신규-모듈-구조}

```
agent_evaluator/
├── core/
│   └── otel/                          ← 신규 서브패키지
│       ├── __init__.py                # setup_otel() 공개 API
│       ├── provider.py                # OTELProvider (TracerProvider 래퍼)
│       └── metrics.py                 # OTELMetrics (MeterProvider 래퍼)
│
└── cli/
    └── monitor.py                     ← 신규 — agent-eval monitor 구현
```

### `agent_evaluator/core/otel/__init__.py`

```python
"""
OpenTelemetry integration for Agent Evaluator.

Optional — only activated when [otel] extras are installed.
"""

from __future__ import annotations
from typing import Optional

_provider: Optional["OTELProvider"] = None


def setup_otel(
    endpoint: str = "http://localhost:4318",
    service_name: str = "agent-evaluator",
    enabled: bool = True,
) -> "OTELProvider":
    """
    OTELProvider를 초기화하고 전역 등록한다.

    PerformanceMonitor는 이 전역 provider를 자동으로 감지해
    record_task() 시 스팬을 발행한다.

    Args:
        endpoint: OTLP HTTP receiver 주소 (Phoenix 기본: http://localhost:4318)
        service_name: Phoenix UI에 표시될 서비스 이름
        enabled: False 시 no-op (테스트/개발 환경 비활성화 용도)

    Returns:
        OTELProvider 인스턴스

    Example:
        >>> from agent_evaluator import setup_otel
        >>> setup_otel(endpoint="http://localhost:4318")
        >>> # 이후 monitor.record_task()가 자동으로 스팬 발행
    """
    from agent_evaluator.core.otel.provider import OTELProvider

    global _provider
    _provider = OTELProvider(
        endpoint=endpoint,
        service_name=service_name,
        enabled=enabled,
    )
    return _provider


def get_provider() -> Optional["OTELProvider"]:
    """현재 활성화된 OTELProvider를 반환. 미설정 시 None."""
    return _provider
```

### `agent_evaluator/core/otel/provider.py`

```python
"""OTELProvider — TracerProvider + BatchSpanProcessor 래퍼."""

from __future__ import annotations

import contextlib
from typing import Any, Dict, Iterator, Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class OTELProvider:
    """
    OTEL TracerProvider 래퍼.

    opentelemetry-sdk 미설치 시 모든 메서드가 no-op으로 동작한다.
    기존 JSON 저장 경로에 일절 영향을 주지 않는다.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4318",
        service_name: str = "agent-evaluator",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled and _HAS_OTEL

        if not self._enabled:
            self._tracer = None
            return

        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(service_name)

    @contextlib.contextmanager
    def span(self, name: str, attributes: Dict[str, Any]) -> Iterator[Any]:
        """
        컨텍스트 매니저형 스팬. 미활성화 시 no-op.

        Example:
            with provider.span("ae.task", {"ae.task_id": "t1"}) as s:
                ...  # 평가 로직
        """
        if not self._enabled or self._tracer is None:
            yield None
            return

        with self._tracer.start_as_current_span(name) as s:
            for k, v in attributes.items():
                s.set_attribute(k, v)
            yield s

    @property
    def enabled(self) -> bool:
        return self._enabled
```

### `agent_evaluator/core/otel/metrics.py`

```python
"""OTELMetrics — MeterProvider 래퍼 (Phase A 지표 발행)."""

from __future__ import annotations
from typing import Dict, Optional

try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    _HAS_OTEL_METRICS = True
except ImportError:
    _HAS_OTEL_METRICS = False


class OTELMetrics:
    """
    OTEL MeterProvider 래퍼.

    주요 지표를 히스토그램/게이지로 Phoenix에 전송.
    미설치 시 no-op.
    """

    # 발행 지표 정의
    METRIC_DEFS = {
        "ae.tcr":              ("gauge",     "Task Completion Rate (%)"),
        "ae.accuracy":         ("gauge",     "Accuracy Score (0–1)"),
        "ae.latency_seconds":  ("histogram", "Task Execution Latency (s)"),
        "ae.tokens_total":     ("counter",   "Cumulative Token Usage"),
        "ae.error_rate":       ("gauge",     "Error Rate (%)"),
    }

    def __init__(self, endpoint: str, enabled: bool = True) -> None:
        self._enabled = enabled and _HAS_OTEL_METRICS
        self._instruments: Dict[str, Any] = {}

        if not self._enabled:
            return

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
            export_interval_millis=15_000,  # 15초마다 배치 전송
        )
        provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(provider)
        meter = metrics.get_meter("agent-evaluator")

        for name, (kind, desc) in self.METRIC_DEFS.items():
            if kind == "histogram":
                self._instruments[name] = meter.create_histogram(name, description=desc)
            elif kind == "counter":
                self._instruments[name] = meter.create_counter(name, description=desc)
            else:  # gauge → observable_gauge
                self._instruments[name] = meter.create_up_down_counter(name, description=desc)

    def record(self, name: str, value: float, attributes: Optional[Dict] = None) -> None:
        """지표 값 기록. 미활성화 시 no-op."""
        if not self._enabled or name not in self._instruments:
            return
        inst = self._instruments[name]
        attrs = attributes or {}
        try:
            inst.record(value, attrs)
        except Exception:  # noqa: BLE001
            pass  # OTEL 오류가 평가 로직을 중단시키지 않도록
```

### `agent_evaluator/cli/monitor.py`

```python
"""
agent-eval monitor — 운영 실시간 모니터링 (Phoenix + OTEL)

사용법:
    agent-eval monitor                    # Phoenix 기동 + 브라우저 오픈
    agent-eval monitor --port 6006        # 포트 지정
    agent-eval monitor --no-open          # 브라우저 비활성화
    agent-eval monitor --attach <url>     # 기존 Phoenix에 연결
    agent-eval monitor --check            # 설치 상태 확인
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import webbrowser
from typing import Optional


def _port_in_use(port: int, host: str = "localhost") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def _check_deps() -> dict:
    """필수 패키지 설치 여부 반환."""
    results = {}
    for pkg, import_name in [
        ("arize-phoenix", "phoenix"),
        ("opentelemetry-sdk", "opentelemetry.sdk"),
        ("opentelemetry-exporter-otlp-proto-http", "opentelemetry.exporter.otlp.proto.http"),
    ]:
        try:
            __import__(import_name)
            results[pkg] = True
        except ImportError:
            results[pkg] = False
    return results


def cmd_check_monitor() -> int:
    """--check: 설치 상태 및 포트 점유 확인."""
    deps = _check_deps()
    all_ok = True

    for pkg, installed in deps.items():
        if installed:
            print(f"  ✅ {pkg:<45} 설치됨")
        else:
            print(f"  ❌ {pkg:<45} 미설치")
            all_ok = False

    for port, label in [(6006, "Phoenix UI"), (4318, "OTLP Receiver")]:
        in_use = _port_in_use(port)
        status = "사용 중 ⚠️" if in_use else "사용 가능 ✅"
        print(f"  {'⚠️' if in_use else '✅'} 포트 {port:<8} ({label}) — {status}")

    if not all_ok:
        print("\n  설치 명령어:")
        print('  pip install "agent-evaluator[otel]"')
        return 1
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Phoenix 서버 기동 후 OTEL 연결 정보 출력."""
    if args.check:
        return cmd_check_monitor()

    # 의존성 확인
    deps = _check_deps()
    missing = [pkg for pkg, ok in deps.items() if not ok]
    if missing:
        print("  ❌ 필수 패키지가 설치되지 않았습니다.")
        print(f"     미설치: {', '.join(missing)}")
        print('\n  pip install "agent-evaluator[otel]"')
        return 1

    port: int = args.port
    otlp_port: int = args.otlp_port
    ui_url = f"http://{args.host}:{port}"
    otlp_url = f"http://{args.host}:{otlp_port}"

    # --attach 모드: 자체 기동 없이 기존 서버에 연결
    if args.attach:
        ui_url = args.attach
        _print_connect_info(ui_url, otlp_url)
        if not args.no_open:
            webbrowser.open(ui_url)
        return 0

    # Phoenix 포트 충돌 확인
    if _port_in_use(port):
        print(f"  ⚠️  포트 {port}가 이미 사용 중입니다.")
        print(f"     기존 서버에 연결하려면: agent-eval monitor --attach {ui_url}")
        return 1

    # Phoenix 서버 기동
    print(f"\n  Agent Evaluator — 운영 모니터링 기동 중...\n")
    try:
        import phoenix as px
    except ImportError:
        print("  ❌ arize-phoenix 패키지를 찾을 수 없습니다.")
        return 1

    # Phoenix를 별도 프로세스로 기동
    proc = subprocess.Popen(
        [sys.executable, "-m", "phoenix.server.main", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 서버 준비 대기 (최대 10초)
    import time
    for _ in range(20):
        if _port_in_use(port):
            break
        time.sleep(0.5)
    else:
        print("  ❌ Phoenix 서버 기동 시간 초과.")
        proc.terminate()
        return 1

    _print_connect_info(ui_url, otlp_url)

    if not args.no_open:
        webbrowser.open(ui_url)

    print("  Ctrl+C 로 종료\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  모니터링 서버 종료됨.")

    return 0


def _print_connect_info(ui_url: str, otlp_url: str) -> None:
    print(f"""
  ┌─────────────────────────────────────────────────────────┐
  │  Agent Evaluator — 운영 모니터링                        │
  ├─────────────────────────────────────────────────────────┤
  │  Phoenix UI      {ui_url:<40} │
  │  OTLP Receiver   {otlp_url:<40} │
  ├─────────────────────────────────────────────────────────┤
  │  에이전트 코드에 아래를 추가하세요:                      │
  │                                                         │
  │  from agent_evaluator import setup_otel                 │
  │  setup_otel(endpoint="{otlp_url}")        │
  └─────────────────────────────────────────────────────────┘
""")


def build_monitor_subparser(sub: argparse._SubParsersAction) -> None:
    """main.py에서 호출 — monitor 서브파서 등록."""
    p = sub.add_parser(
        "monitor",
        help="운영 실시간 모니터링 (Phoenix + OTEL)",
        description=(
            "Arize Phoenix 서버를 기동하고 OpenTelemetry 스팬 수신을 설정합니다.\n"
            "프로덕션 환경의 실시간 트레이싱·스팬 분석·오류 감지에 활용합니다.\n"
            "\n"
            "필요 패키지:\n"
            '  pip install "agent-evaluator[otel]"'
        ),
    )
    p.add_argument("--port",      type=int, default=6006,        help="Phoenix UI 포트 (기본: 6006)")
    p.add_argument("--otlp-port", type=int, default=4318,        help="OTLP HTTP receiver 포트 (기본: 4318)")
    p.add_argument("--host",      type=str, default="localhost",  help="바인딩 호스트 (기본: localhost)")
    p.add_argument("--no-open",   action="store_true",           help="브라우저 자동 오픈 비활성화")
    p.add_argument("--attach",    type=str, metavar="URL",       help="기존 Phoenix 서버 URL에 연결")
    p.add_argument("--check",     action="store_true",           help="설치 상태 및 포트 점유 확인")
    p.add_argument("--working-dir", type=str, default="./",      help="Phoenix DB 저장 디렉토리")
    p.set_defaults(func=cmd_monitor)
```

---

## 핵심 코드 인터페이스 {#핵심-코드-인터페이스}

### `monitor.py` 변경 — `record_task()` 훅

`core/trackers/monitor.py`의 `record_task()` 메서드 내부에 다음 훅을 삽입한다.
기존 `_update_trackers()` 호출 이후, JSON 저장 이전에 위치.

```python
# core/trackers/monitor.py  (변경 부분만)

def record_task(self, result: TaskResult) -> "PerformanceMonitor":
    with self._lock:
        self._update_trackers(result)   # 기존 — JSON 집계 (보존)
        self._emit_otel_span(result)    # 추가 — OTEL 스팬 (no-op if disabled)
    return self

def _emit_otel_span(self, result: TaskResult) -> None:
    """OTEL 스팬 발행. OTELProvider 미활성화 시 즉시 반환."""
    from agent_evaluator.core.otel import get_provider
    provider = get_provider()
    if provider is None or not provider.enabled:
        return

    attributes = {
        "ae.task_id":          result.task_id,
        "ae.task_type":        str(result.task_type),
        "ae.success":          result.success,
        "ae.completion_score": result.completion_score,
        "ae.accuracy_score":   result.accuracy_score,
        "ae.execution_time":   result.execution_time,
        "ae.tokens_used":      result.tokens_used,
        "ae.tool_calls_count": len(result.tool_calls),
        "ae.attempts":         result.attempts,
        "ae.framework":        getattr(result, "framework", "native"),
    }
    with provider.span("ae.task", attributes):
        pass  # 스팬 기록만, 평가 로직은 이미 완료
```

### `monitor_context.py` 변경 — 루트 스팬

```python
# core/monitor_context.py  (evaluation_session 변경 부분)

@contextlib.contextmanager
def evaluation_session(filename: str, **monitor_kwargs):
    from agent_evaluator.core.otel import get_provider
    provider = get_provider()

    monitor = PerformanceMonitor(**monitor_kwargs)
    with provider.span("ae.session", {"ae.session_file": filename}) \
         if provider and provider.enabled \
         else contextlib.nullcontext():
        try:
            yield monitor
        finally:
            monitor.save_to_file(filename)
```

### `__init__.py` 변경 — `setup_otel` 노출

```python
# agent_evaluator/__init__.py  (추가 항목)

# Lazy imports에 추가
_LAZY_IMPORTS = {
    ...
    "setup_otel": ("agent_evaluator.core.otel", "setup_otel"),
    "OTELProvider": ("agent_evaluator.core.otel.provider", "OTELProvider"),
}

_FRAMEWORK_EXTRA_MAP = {
    ...
    "setup_otel": "otel",
    "OTELProvider": "otel",
}
```

---

## 환경 설정 / 의존성 {#환경-설정--의존성}

### `pyproject.toml` 추가

```toml
[project.optional-dependencies]
# OpenTelemetry + Phoenix 운영 모니터링
otel = [
    "opentelemetry-sdk>=1.20.0,<2.0.0",
    "opentelemetry-exporter-otlp-proto-http>=1.20.0,<2.0.0",
    "opentelemetry-semantic-conventions>=0.41b0",
    "arize-phoenix>=0.11.0",
]

# [all] extras에 otel 포함 여부 → 선택적 (Phoenix가 무거우므로 별도 유지 권장)
# all = [...기존..., "agent-evaluator[otel]"]  # 필요 시 추가
```

### 설치 명령어 요약

```bash
# 운영 모니터링 단독 설치
pip install "agent-evaluator[otel]"

# 개발 환경 전체 + 운영 모니터링
pip install "agent-evaluator[all,otel]"

# 필수 패키지 버전 (참고)
# opentelemetry-sdk >= 1.20.0
# arize-phoenix >= 0.11.0 (0.13+ 권장)
```

### 환경변수 (선택)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP 엔드포인트 (표준 OTEL 변수) |
| `OTEL_SERVICE_NAME` | `agent-evaluator` | Phoenix UI 서비스 이름 |
| `AE_OTEL_ENABLED` | `false` | `setup_otel()` 없이 환경변수로 활성화 |

---

## 사용 예시 {#사용-예시}

### 기본 사용 패턴

```bash
# 터미널 1 — Phoenix 서버 기동
agent-eval monitor

# 터미널 2 — 에이전트 실행
python my_agent.py
```

```python
# my_agent.py
from agent_evaluator import PerformanceMonitor, create_taskresult, setup_otel

# OTEL 활성화 (agent-eval monitor 실행 후)
setup_otel(endpoint="http://localhost:4318", service_name="my-rag-agent")

monitor = PerformanceMonitor()

result = create_taskresult(
    task_id="task_001",
    question="서울의 인구는?",
    response="약 950만 명입니다.",
    ground_truth="950만 명",
    execution_time=1.2,
)

monitor.record_task(result)
# → JSON 저장 (기존 동작 유지)
# → ae.task 스팬 Phoenix에 전송 (신규)
```

### `evaluation_session`과 함께

```python
from agent_evaluator import evaluation_session, setup_otel

setup_otel(endpoint="http://localhost:4318")

with evaluation_session("run_2026_03_31") as monitor:
    # ae.session 루트 스팬 시작
    for task in tasks:
        result = agent.run(task)
        monitor.record_task(result)
        # 각 task → ae.task 자식 스팬
# 세션 종료: JSON 저장 + ae.session 스팬 종료
```

### 기존 Phoenix에 연결 (팀 공용 서버)

```bash
# 자체 기동 없이 팀 Phoenix 서버에 연결
agent-eval monitor --attach http://phoenix.internal:6006

# 이후 에이전트 코드에서:
setup_otel(endpoint="http://phoenix.internal:4318")
```

### CI/CD 파이프라인에서 비활성화

```python
import os
from agent_evaluator import setup_otel

# CI 환경에서는 OTEL 비활성화 (Phoenix 서버 없음)
if os.getenv("CI") != "true":
    setup_otel(endpoint="http://localhost:4318")
```

---

## 대시보드 UI 호환성 {#대시보드-ui-호환성}

Phase A/B OTEL 적용 후 `agent-eval dashboard` 탭별 동작:

| 탭 | Phase A/B 동작 | 비고 |
|----|---------------|------|
| 📊 Overview | ✅ 정상 | JSON 기반, 영향 없음 |
| 🎯 품질 | ✅ 정상 | JSON 기반 |
| 💬 멀티턴 대화 | ✅ 정상 | JSON 기반 |
| ⚡ 성능 | ✅ 정상 | JSON 기반 |
| 🤖 에이전틱 | ✅ 정상 | JSON 기반 |
| 🔒 보안 | ✅ 정상 | JSON 기반 |
| 🔍 인사이트 | ✅ 정상 | JSON 기반 |
| 📡 실시간 | ✅ 정상 | StreamingEvaluator 기반 (별개) |
| 🔔 알림 | ✅ 정상 | AlertEngine 기반 (별개) |
| 👍 사용자 반응 | ✅ 정상 | ImplicitFeedbackTracker 기반 |
| 🚨 이상 감지 | ✅ 정상 | AnomalyDetector 기반 |
| 💰 평가 비용 | ✅ 정상 | CostTracker 기반 |
| 🌟 골든 데이터셋 | ✅ 정상 | GoldenSetBuilder 기반 |
| 🔬 투명성 | ✅ 정상 | TestTransparencyManager 기반 |

**결론**: Phase A/B는 기존 대시보드 기능에 영향 없음.
OTEL 스팬은 순수 추가 경로로, JSON 생성 로직과 완전 독립.

---

## 구현 로드맵 {#구현-로드맵}

### Phase A — 스팬 익스포트 (v0.7.0)

예상 작업량: 4–5 라운드

| 라운드 | 작업 | 산출물 |
|--------|------|--------|
| R1 | `core/otel/` 서브패키지 신규 생성 | `provider.py`, `metrics.py`, `__init__.py` |
| R2 | `monitor.py` `record_task()` 훅 + `monitor_context.py` 루트 스팬 | 기존 756개 테스트 전원 통과 확인 |
| R3 | `__init__.py` lazy import + `setup_otel()` 공개 API | `from agent_evaluator import setup_otel` |
| R4 | `cli/monitor.py` 신규 + `cli/main.py` 서브커맨드 등록 | `agent-eval monitor` 동작 |
| R5 | `pyproject.toml` `[otel]` extras + 테스트 | 설치 검증, `--check` 동작 |

### Phase B — 프레임워크 Child Span (v0.7.1)

예상 작업량: 3–4 라운드 (Phase A 안정화 후)

| 라운드 | 작업 | 산출물 |
|--------|------|--------|
| R6 | LangChain/LangGraph child span | `on_chain_start/end` 훅 |
| R7 | CrewAI child span | Task/Agent 실행 래퍼 |
| R8 | AutoGen child span | `generate_reply` 래퍼 |
| R9 | Phoenix UI 검증 + 사용자 가이드 업데이트 | 트레이스 폭포수 스크린샷 포함 |

### Phase C — 보류

JSON → Span 완전 대체는 `agent-eval dashboard` 탭 반수 동작 불능 초래.
Phoenix UI가 운영 트레이싱 전담, `agent-eval dashboard`가 개발/검증 전담으로
역할 분리하는 현 설계가 더 적합하다는 판단으로 무기한 보류.

---

## 관련 문서

- [`01_QUICK_START.md`](01_QUICK_START.md) — SDK 기본 사용법
- [`08_DASHBOARD_GUIDE.md`](08_DASHBOARD_GUIDE.md) — `agent-eval dashboard` 상세 가이드
- [`06_DEPLOYMENT_GUIDE.md`](06_DEPLOYMENT_GUIDE.md) — 프로덕션 배포 가이드
- [`07_API_REFERENCE.md`](07_API_REFERENCE.md) — 공개 API 전체 목록
