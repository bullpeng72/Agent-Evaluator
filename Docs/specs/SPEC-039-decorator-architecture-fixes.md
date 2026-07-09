# SPEC-039: 데코레이터 아키텍처 결함 수정 + LiveGuardrail 비침습 데코레이터

## Context

2026-07-09 세션에서 `agent_evaluator/decorators.py`(8,474줄)와 `agent_evaluator/gates/live_guardrail.py`(499줄)를
직접 대조해 발견한 6건. 모두 이 세션에서 실제 코드를 읽고(필요한 것은 직접 실행해) 확인했다.

1. **preset/explicit 파라미터 충돌 시 sentinel 패턴 오작동** — `agent_eval`(`decorators.py:5306-5311`):
   ```python
   _effective_sample_rate = sample_rate if sample_rate != 1.0 else _preset_vals.get("sample_rate", sample_rate)
   ```
   `sample_rate`(과 `timeout`/`flush_every`/`enabled`/`enable_anomaly_detection`/`enable_hallucination_detection`)의
   "미지정"을 "파이썬 기본값과 값이 같음"으로 판정한다 — 호출자가 `preset="production"`(sample_rate=0.1)과 함께
   **명시적으로** `sample_rate=1.0`을 줘도 기본값과 우연히 같아 preset의 0.1로 조용히 덮어써진다. 동일 패턴이
   `batch_eval`(`6907-6916`)·`conversation_eval`(`6443-6451`)에 각각 독립 복붙돼 있다(3곳).

2. **async 경로에 `ReproducibilityConfig` 추가 실행 로직이 없음(의도된 설계, 미문서화)** —
   sync `wrapper`(`5543-5556`)는 `reproducibility` 설정 시 함수를 `reproducibility.runs - 1`회 추가 실행해
   `_repro_responses`를 채우지만, `async_wrapper`는 이 블록 자체가 없고 `_build_and_record` 호출부에
   `reproducibility_responses=None,  # async reproducibility는 미지원`(`5831`)이라고 명시돼 있다.
   `_build_and_record`(`4078`)는 `reproducibility_responses is not None`일 때만 점수를 계산하므로, async
   에이전트에 `reproducibility=ReproducibilityConfig(...)`를 줘도 예외 없이 조용히 Gate C 재현성 지표가
   전혀 채워지지 않는다. docstring Args(`5156-5186`)에는 이 제약이 언급되지 않는다.

3. **Generator wrapper(`gen_wrapper`, `5870-`)에 재시도 루프 자체가 없음** — `_n_tries`/`while` 루프가
   전혀 존재하지 않는다. `retry=RetryConfig(...)`를 스트리밍 에이전트 함수에 줘도 예외 없이 조용히 무시된다.

4. **Harness Config 파라미터 목록이 4곳에 손으로 복붙** — `agent_eval`(~50개 kwargs, `5055-5130`),
   `batch_eval`(~60개, `6787-6859`), `conversation_eval`(~38개, `6335-6400`)가 33개 Harness Config 중
   상당수를 각자 시그니처에 `Optional[XConfig] = None`으로 반복 선언한다. `EvalDecorator`(`7953-`)는
   `_COMMON_PARAMS`/`_BATCH_PARAMS`/`_CONV_PARAMS` frozenset(`7994-8063`)으로 "어느 데코레이터가 어느
   파라미터를 받는지"를 손으로 재관리하며, 그 옆에 "새 파라미터 추가 시 … 시그니처와 함께 이 frozenset도
   업데이트 필요"라는 유지보수 경고 주석이 있다(`7993`, `8009`).

5. **`conversation_eval`이 받는 27개 Harness Config 파라미터가 전부 죽은 코드** — `instructions`부터
   `latency_attribution`까지 27개 `Optional[XConfig] = None` 파라미터가 시그니처(`6367-6399`)에 있지만,
   함수 본문(`6400-6790`) 어디에서도 참조되지 않는다(`grep -n "\binstructions\b"`로 6400-6790 범위 확인 —
   매치 0건). 실제 기록 경로는 `_do_flush()`(`6227-6332`)의 `with stored_monitor.conversation(session_id)
   as conv: conv.turn(user=..., agent=..., metadata=...)`이며, `agent_eval`/`batch_eval`/`eval_context`가
   공유하는 `_build_and_record()`(호출 지점 `5584/5789/5922/6046/7093/7796`)를 전혀 거치지 않는다.
   즉 `conversation_eval(monitor, sla=SLAConfig(...))`처럼 써도 `sla`는 받아들여지기만 하고 아무 효과가 없다.

6. **`LiveGuardrail`은 SDK의 다른 데코레이터 인프라와 완전히 단절** — `agent_eval`은 이미
   `contextvars.ContextVar`(`_eval_ctx_var`, `497`) + `_push_ctx()`/`_pop_ctx()`(`538`/`548`)로 "현재 실행
   컨텍스트"를 암묵 전달하고, `eval_context`(`7494-7843`)는 "데코레이터를 못 쓰는 코드"를 위해 같은 인프라
   위에 만든 `with`-블록 대안이다. 반면 `LiveGuardrail`(`live_guardrail.py`, 499줄)은 `contextvars`를
   전혀 import하지 않고, 모든 메서드(`check_before_tool_call`/`record_tool_call`/`record_blocked_attempt`)가
   `task_id`를 명시 인자로 받는 순수 인스턴스 메서드다. `grep -rn "tool_guard\|LiveGuardrailDecorator"
   agent_evaluator/`는 0건 — 도구 함수 단위 데코레이터가 존재하지 않는다. `agent_evaluator/__init__.py`에도
   `LiveGuardrail` 자체가 노출돼 있지 않다(사용자는 항상 `from agent_evaluator.gates.live_guardrail import
   LiveGuardrail`로 직접 import — Ch27 예제와 동일 패턴).

## Goals

- G1: preset과 명시적 파라미터가 충돌할 때 명시적 값이 항상 이기게 한다(REQ-1).
- G2: async 에이전트 함수에서 `ReproducibilityConfig`가 sync와 동등하게 동작하게 한다(REQ-2).
- G3: 지원되지 않는 조합(retry+generator)을 조용히 무시하는 대신 즉시 알린다(REQ-3).
- G4: Harness Config 파라미터 목록이 어긋나면 CI가 즉시 잡아내게 한다(REQ-4).
- G5: `conversation_eval`의 죽은 Harness Config 파라미터를 눈에 보이게 한다(REQ-5).
- G6: 자체 Python 에이전트 루프에서 `LiveGuardrail`을 도구 함수당 반복적인 명시 호출 없이 적용할 수 있는
  contextvars 기반 데코레이터를 제공한다(REQ-6).

## Non-Goals

- `conversation_eval`이 27개 Harness Config를 **실제로 평가**하게 만드는 것(REQ-5는 "죽은 파라미터를
  경고로 드러낸다"까지만 — 실제 턴 단위 Harness 평가 배선은 `ConversationSession`/`conv.turn()` 내부
  구조를 새로 설계해야 하는 별도 스펙 대상이다).
- 스트리밍 generator 함수에 대한 실제 재시도 실행(이미 일부 청크를 호출자에게 yield한 뒤 "재시도"가
  무엇을 의미하는지 자체가 정의되지 않음 — REQ-3은 명시적 경고까지만).
- `agent_eval`/`batch_eval`/`conversation_eval`의 공개 시그니처를 `**kwargs`/`TypedDict`로 바꾸는 것
  (IDE 자동완성·`EvalDecorator`의 `inspect.signature()` 기반 필터링을 깨뜨리는 하위호환 파괴적 변경).
- `LiveGuardrail`이 커버하는 위험 탐지 로직 자체의 변경(REQ-6은 순수 적용 방식 개선 — 새 판정 로직 없음).
- OpenCode 플러그인(TypeScript) 변경.

## Requirements

### REQ-1 — preset/explicit 파라미터 sentinel 충돌 수정

`agent_eval`/`batch_eval`/`conversation_eval` 세 곳에서, `sample_rate`/`timeout`/`flush_every`/`enabled`/
`enable_anomaly_detection`/`enable_hallucination_detection`(`agent_eval`만 해당) 중 preset이 정의하는
필드는, 호출자가 **명시적으로 값을 전달했는지 여부**로 override 우선순위를 판정해야 한다 — 파이썬
기본값과 우연히 같은 값을 "미지정"으로 오인해서는 안 된다.

### REQ-2 — async `ReproducibilityConfig` 지원

`async_wrapper`가 sync `wrapper`와 동등하게, `reproducibility is not None`이고 에러가 없을 때
`reproducibility.runs - 1`회 `await func(*args, **kwargs)`를 추가 실행해 `_repro_responses`를 채우고
`_build_and_record`에 전달해야 한다. `skip_side_effects=True`일 때 추가 실행을 건너뛰는 sync 동작도
동일하게 따른다.

### REQ-3 — retry+generator 조합 명시적 경고

`agent_eval(retry=RetryConfig(...), ...)`로 데코레이트된 함수가 sync/async generator function일 때,
데코레이션 시점(함수 정의 직후, 호출 전)에 `UserWarning`을 발생시켜 "retry는 generator/스트리밍
함수에서 지원되지 않으며 무시된다"는 사실을 알려야 한다. 동작 자체(재시도 없이 그대로 실행)는 변경하지
않는다.

### REQ-4 — Harness Config 파라미터 목록 drift 방지

`EvalDecorator`의 `_COMMON_PARAMS`/`_BATCH_PARAMS`/`_CONV_PARAMS`는 `inspect.signature()`로 `agent_eval`/
`batch_eval`/`conversation_eval`의 실제 시그니처에서 프로그래밍적으로 유도해야 한다(손으로 나열한
frozenset 리터럴 제거). 추가로, 세 함수가 공통으로 가져야 하는 Harness Config 파라미터 집합이
어긋나면 실패하는 테스트를 추가한다(`agent_eval`에는 있는데 `batch_eval`에는 없는 Harness Config
파라미터가 생기면 CI가 즉시 잡는다 — `conversation_eval`은 REQ-5로 인해 일부 최신 Config가 의도적으로
빠져 있을 수 있으므로 "완전히 동일"이 아니라 "`agent_eval`에 있는 각 Config가 `batch_eval`에도
있는가"를 편도로 검사).

### REQ-5 — `conversation_eval`의 죽은 Harness Config 파라미터 경고

`conversation_eval`이 받는 27개 Harness Config 파라미터(`instructions`~`latency_attribution`) 중
하나라도 `None`이 아니면, 데코레이션 시점에 `UserWarning`으로 "이 파라미터는 `conversation_eval`에서
현재 평가에 반영되지 않는다"는 사실과 그 파라미터 이름 목록을 알려야 한다. docstring에도 이 제약을
명시한다.

### REQ-6 — `LiveGuardrail` contextvars 세션 + `tool_guard` 데코레이터

`agent_evaluator/gates/live_guardrail.py`에 다음을 추가한다:

- `live_guardrail_session(guardrail, task_id)` — `contextvars.ContextVar` 기반 컨텍스트 매니저.
  진입 시 `(guardrail, task_id)`를 현재 컨텍스트에 설정하고, 이탈 시 원복한다(`_push_ctx`/`_pop_ctx`와
  동일한 토큰 기반 패턴, `_eval_ctx_var`와는 별개의 새 `ContextVar`).
- `tool_guard(tool_name=None, *, audit_blocked=False, fail_closed=False, capture_output=None)` —
  sync/async 함수 모두 지원하는 데코레이터(`asyncio.iscoroutinefunction`로 자동 감지). 활성 세션이
  없으면 `fail_closed=False`(기본)일 때 `RuntimeWarning`과 함께 가드 없이 원본 함수를 실행하고,
  `fail_closed=True`일 때 `RuntimeError`를 발생시킨다. 활성 세션이 있으면 `inspect.signature(func).bind()`로
  파라미터 dict를 만들어 `check_before_tool_call()`을 호출하고, `block=True`면 `GuardrailBlockedError`를
  발생시키며(`audit_blocked=True`일 때 `record_blocked_attempt()`도 호출), `block=False`면 원본 함수를
  실행한 뒤 `record_tool_call()`을 호출한다(`capture_output` 콜백이 있으면 반환값을 `output=` dict로
  변환해 함께 전달).
- `class GuardrailBlockedError(Exception)` — `.verdict: LiveVerdict` 속성을 가짐.

## Interface

### REQ-1 (변경 없음, 동작만 수정)
```python
# 변경 전: sample_rate=1.0(preset 기본값과 동일한 명시적 호출)이 preset에 덮어써짐
# 변경 후: sample_rate가 명시적으로 전달됐는지를 별도로 추적해 항상 우선
```
공개 시그니처는 그대로 유지 — 내부 병합 로직만 수정.

### REQ-2
```python
@agent_eval(monitor, task_type="qa", reproducibility=ReproducibilityConfig(runs=3))
async def agent(question: str, ground_truth: str = "") -> str: ...
# 변경 전: Gate C avg_reproducibility 항상 None
# 변경 후: sync와 동일하게 2회 추가 await 실행 후 점수 계산
```

### REQ-3
```python
@agent_eval(monitor, task_type="qa", retry=RetryConfig(max_retries=3))
def stream_agent(question: str):
    yield "chunk1"
    yield "chunk2"
# 변경 후: 데코레이션 시점에 UserWarning 발생 ("retry ignored for generator functions")
```

### REQ-4
```python
# decorators.py 내부, EvalDecorator 위
_COMMON_PARAMS = frozenset(inspect.signature(agent_eval).parameters) & frozenset(inspect.signature(batch_eval).parameters)
# 기존의 손으로 나열한 frozenset 리터럴 대체
```

### REQ-5
```python
@conversation_eval(monitor, sla=SLAConfig(p95_ms=2000))
def chat(question: str, session_id: str = "s1") -> str: ...
# 변경 후: 데코레이션 시점에 UserWarning ("sla is not applied by conversation_eval yet")
```

### REQ-6 (신규 공개 API, additive)
```python
from agent_evaluator.gates.live_guardrail import (
    LiveGuardrail, live_guardrail_session, tool_guard, GuardrailBlockedError,
)

guardrail = LiveGuardrail(tool_parameter_safety=ToolParameterSafetyConfig(...))

@tool_guard()
def bash(command: str) -> str:
    ...
    return result

with live_guardrail_session(guardrail, task_id="session-1"):
    bash("ls -la")          # 자동으로 check_before_tool_call → 실행 → record_tool_call
    bash("rm -rf /")        # GuardrailBlockedError 발생
```
기존 `check_before_tool_call()`/`record_tool_call()`/`record_blocked_attempt()`/`snapshot()` 시그니처는
무수정 — `tool_guard`는 그 위에 얹는 순수 추가 계층이다.

## Acceptance

| REQ | 테스트 케이스 |
|---|---|
| REQ-1 | `preset="production"`(sample_rate=0.1) + 명시적 `sample_rate=1.0` → 실제 100% 샘플링됨을 확인(다수 호출 후 기록된 태스크 수로 검증). `timeout`/`enabled`도 동일 패턴 1건씩. `batch_eval`/`conversation_eval` 각 1건. preset 없이 기존 동작(미지정 시 preset 값 적용) 회귀 없음도 함께 확인. |
| REQ-2 | async 에이전트 + `ReproducibilityConfig(runs=3)` → `harness_groups.C.details.avg_reproducibility`가 `None`이 아님을 확인. `skip_side_effects=True` 시 추가 실행 없이 `run_count=1` 확인. |
| REQ-3 | sync/async generator 각각에 `retry=RetryConfig(...)` 부여 → 데코레이션 시점 `pytest.warns(UserWarning)` 확인, 함수는 정상 동작(재시도 없이). |
| REQ-4 | `inspect.signature(agent_eval)`에만 있고 `batch_eval`에 없는 Harness Config 파라미터가 있으면 실패하는 테스트. 정상 상태에서는 통과 확인. |
| REQ-5 | `conversation_eval(monitor, sla=SLAConfig(...))` → `pytest.warns(UserWarning, match="sla")`. Harness Config 없이 호출 시 경고 없음. |
| REQ-6 | (a) 세션 내 `tool_guard` 함수 호출이 정상 통과 시 `guardrail.snapshot()["tool_calls"]`에 반영됨. (b) 차단 시 `GuardrailBlockedError` 발생 + 원본 함수 미실행(부작용 없음을 mock으로 확인) + `audit_blocked=True`면 `blocked_attempts`에 반영. (c) 세션 밖 호출 시 `fail_closed=False`면 경고+통과, `fail_closed=True`면 `RuntimeError`. (d) async 도구 함수 지원. (e) 중첩 `asyncio.create_task()`에서 서로 다른 세션이 섞이지 않음(contextvars 격리 확인). |

## Compatibility

- REQ-1~5: 전부 기존 공개 시그니처 무수정. REQ-1/2는 이전에 조용히 틀리거나 비어있던 값이 이제 채워지는
  **동작 변경**이지만, "버그 수정"이므로 하위호환 파괴로 간주하지 않는다(단, 이전에 preset의 낮은
  sample_rate에 암묵적으로 의존해 비용을 절감하던 코드가 있다면 REQ-1 수정 후 실제 sample_rate가
  올라갈 수 있음 — Risks에 기재).
- REQ-3/5: 새 `UserWarning` 발생은 하위호환 파괴가 아니나, `-W error`로 경고를 예외로 승격해둔 CI가
  있다면 실패할 수 있음(Risks에 기재).
- REQ-4: 내부 구현 세부사항(`_COMMON_PARAMS` 등)만 변경 — 공개 API 영향 없음.
- REQ-6: 완전 additive — 기존 `LiveGuardrail` 사용 코드(Ch27~29 예제 포함)는 무수정으로 계속 동작.

## Rollout

1. REQ-1(가장 명확한 버그) → REQ-2(다음으로 명확한 기능 누락) → REQ-3/REQ-5(경고 추가, 저위험) →
   REQ-4(테스트 인프라) → REQ-6(신규 기능, 가장 큰 추가 표면) 순서로 구현·테스트·전체 스위트 회귀 확인을
   반복한다.
2. 각 REQ 완료 후 `pytest`(관련 test_spec039_*.py) + 전체 스위트를 실행해 회귀 0건을 확인하고 다음 REQ로
   진행한다.
3. 전체 완료 후 이 README의 상태를 갱신한다.

## Risks

- **REQ-1**: preset의 낮은 `sample_rate`에 암묵적으로 의존해 LLM Judge 비용을 절감하던 기존 코드가,
  실수로 `sample_rate=1.0`(또는 다른 기본값)을 명시하고 있었다면 수정 후 비용이 실제로 올라갈 수 있다.
  완화책: CHANGELOG에 "이전에는 이 경우 조용히 무시됐다"는 동작 변경을 명시.
- **REQ-2**: async 에이전트에 `reproducibility=ReproducibilityConfig(runs=N)`을 부여하면 실제로 함수를
  N배 더 호출한다(sync와 동일한 기존 트레이드오프이지만 지금까지 async에서는 발생하지 않았던 비용) —
  부작용이 있는 async 함수(실제 API 호출 등)에 `skip_side_effects=False`로 잘못 적용하면 side effect가
  N배로 늘어난다. sync 경로도 동일한 문서화된 위험을 이미 안고 있으므로 새로운 리스크 유형은 아니다.
- **REQ-3/REQ-5**: `-W error::UserWarning` 등으로 경고를 예외로 취급하는 CI 설정이 있으면 기존에
  조용히 통과하던 호출이 실패로 바뀔 수 있다. 완화책: 경고 메시지에 `stacklevel`을 정확히 지정해 호출자
  코드를 가리키게 하고, 새 경고 클래스(`ConversationEvalConfigIgnoredWarning` 등) 도입은 과도한 스코프로
  판단해 표준 `UserWarning`으로 최소화.
- **REQ-6**: `tool_guard`가 세션 컨텍스트 없이 호출됐을 때 기본값(`fail_closed=False`)이 "경고 후 통과"이므로,
  "무사고" 목표로 이 데코레이터를 도입하는 사용자가 기본값을 확인하지 않으면 여전히 사각지대가 생길 수
  있다 — docstring과 Ch27 문서 갱신 시 `fail_closed=True`를 프로덕션 권장값으로 명시해야 한다(이 스펙은
  코드 구현까지만, 책 갱신은 별도 후속 작업).
