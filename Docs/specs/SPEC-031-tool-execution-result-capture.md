# SPEC-031: 도구 실행 결과(exit code/output) 캡처 — Gate G 낙관 편향 해소 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~3 전체 완료(2026-07-07)** · **의존성:** SPEC-019(완료, `LiveGuardrail.record_tool_call()`) · SPEC-028(완료, `tool_calls`가 `TaskResult.tool_calls`로 승격돼 `ToolCallAnalyzer`가 소비하는 경로 확립)

> **구현 노트 (2026-07-07)**: 설계안 그대로 3개 REQ 전부 구현, 편차 없음.
> REQ-1: `LiveGuardrail.__init__`에 `max_tool_output_chars: int = 2000` 추가,
> `record_tool_call(task_id, tool_name, parameters=None, output=None)`에 `output`
> 파라미터 추가 — 허용 키(`_ALLOWED_OUTPUT_KEYS = ("success", "exit_code", "stdout",
> "stderr")`)만 골라 tool_call 항목에 병합, `stdout`/`stderr`는 `max_tool_output_chars`로
> truncate. `output=None`(기본값)이면 이전과 완전히 동일 — `ToolCallAnalyzer`는
> 신규 코드 없이 이미 `"success"` 키를 읽는다는 것을 `analyze_execution()` 직접
> 호출로 재확인(`failed_calls` 카운트가 정확히 반영됨). REQ-2:
> `live_guardrail_stdio.py`의 `{"op": "record", ...}`가 선택적 `"output"` 필드를
> 받아 그대로 전달, `{"op": "init", ...}`가 선택적 `"max_tool_output_chars"`를 받아
> `LiveGuardrail` 생성자에 전달. REQ-3: TS 플러그인에 `ToolExecutionOutput` 인터페이스와
> `extractToolExecutionOutput()` 헬퍼 추가 — `output.output`(타입 보장)을 `stdout`으로,
> `output.metadata`(any)에서 `exit`/`exitCode`/`code` 후보 키를 방어적으로 탐색해
> 숫자면 `exit_code`/`success`를 채우고 못 찾으면 필드 자체를 생략. `record()`
> 시그니처에 `output?: ToolExecutionOutput` 추가, `tool.execute.after` 핸들러가
> 그동안 버리던 `output` 파라미터를 받아 이 헬퍼에 넘기도록 배선.
>
> **TS 타입체크 실측 검증**: 이 머신에 실제 설치된 `@opencode-ai/plugin@1.17.9`
> 타입 선언(`.opencode/node_modules`)을 대상으로 `npx tsc --noEmit`을 직접
> 실행해 확인 — 모듈 해석이 정상적으로 이뤄지는 조건(`.opencode/` 디렉토리에서
> 실행 + node 내장 모듈 최소 스텁)에서 내 변경으로 인한 신규 타입 에러 0건
> (남은 에러 1건은 `node:readline` 스텁 자체의 한계로 이번 변경과 무관). 이로써
> `tool.execute.after`의 실제 훅 시그니처(`output: {title, output, metadata}`)와
> `extractToolExecutionOutput()`의 파라미터 타입이 구조적으로 정확히 일치함을
> 확인했다 — **단, `metadata`의 실제 런타임 키(exit code가 어느 필드에 담기는지)는
> 이번에도 라이브 세션으로 검증하지 못했다**(타입 수준에서 `any`이므로 타입체크로는
> 확인 불가능한 부분 — Risks에 명시된 대로 정직하게 미검증 상태로 남긴다).
>
> 테스트 10건 추가(`test_live_guardrail.py` 7건, `test_live_guardrail_stdio.py` 3건).
> 전체 스위트 **3,472 passed, 1 skipped, 회귀 0건**(기존 3,462 + 신규 10).
>
> 품질 래칫: `live_guardrail.py`(UP006 +4/UP045 +1)는 새 `Optional[Dict[str, Any]]`/
> `Dict[str, Any]` 타입힌트 2줄에서 나온 것으로 이 파일에 이미 지배적으로 존재하던
> 동일 규칙의 추가 인스턴스(SPEC-029/030과 동일한 선례). `live_guardrail_stdio.py`는
> 변화 없음. mypy 신규 findings 없음(기존 2건은 내가 건드리지 않은
> `analyze_privilege_chain` 호출부, 라인 번호만 밀렸을 뿐).
>
> **후속 권장 사항(구현에는 포함 안 됨)**: REQ-3을 실제 운영에 투입하기 전,
> `tool.execute.after`에 임시 `console.log(JSON.stringify(output))`을 추가해
> 실제 bash 도구 호출 1회를 라이브로 확인하고 `extractToolExecutionOutput()`의
> 후보 키 목록이 실제 스키마와 맞는지 검증할 것을 권장한다(Risks 참조 — 이번
> 스펙의 유일한 미해결 불확실성).

## Context (설계 시점 — 위 구현 노트가 최신 상태)

## Context

- `agent_evaluator/core/trackers/layer2.py:197`에서 `ToolCallAnalyzer`는 이미 `call.get("success", True)`로 **`tool_calls` 각 항목에 `"success"` 키가 있으면 그 값을 그대로 읽는다** — 직접 확인한 사실. 즉 Python SDK 스키마 변경은 필요 없다: 호출자가 `tool_calls` 항목에 `"success": bool`을 채워 넘기기만 하면 Gate G(`_tool_coverage`)가 오늘 당장 실제 성공/실패를 반영한다. 지금 이 키가 채워지지 않는 이유는 순전히 **호출부가 아직 이 값을 만들어 넘기지 않기 때문**이다.
- 그 호출부는 `LiveGuardrail.record_tool_call(task_id, tool_name, parameters)`(`gates/live_guardrail.py`)다 — 현재 시그니처에 실행 *결과*를 받을 자리 자체가 없다. `self._tool_calls.append({"name": tool_name, "arguments": parameters or {}})`가 유일한 대입 지점이며, 여기서 만들어진 리스트가 그대로 `snapshot()`/`to_task_extra()`를 거쳐 `TaskResult.tool_calls`가 된다(SPEC-028 REQ-1).
- OpenCode TS 플러그인(`agent-evaluator.ts`)의 `"tool.execute.after"` 훅은 실제 설치된 `@opencode-ai/plugin@1.17.9` 타입 선언(`node_modules/@opencode-ai/plugin/dist/index.d.ts:249-258`)을 직접 대조한 결과 `output: {title: string; output: string; metadata: any}` 형태다 — **`output.output`(문자열)는 타입으로 보장되고 항상 존재**하지만, **`output.metadata`는 `any`로 선언돼 있어 어떤 필드(exit code 등)가 들어있는지 공개 타입 수준에서 보장되지 않는다.** `@opencode-ai/sdk`의 `ToolStateCompleted`/`ToolStateError`(`types.gen.d.ts:231-261`) 판별 유니온을 보면 SDK 내부적으로는 성공/에러가 구분되지만, 이 구분이 `tool.execute.after` 훅의 `output` 인자에 그대로 노출되는지는 이번 세션에서 라이브로 검증하지 못했다 — 이 스펙은 이 사실을 정직하게 인정하고 최선 노력(best-effort) 탐지로 설계한다(Risks 참조).
- 지금 플러그인은 `input.args`만 읽어 `session.record()`에 넘기고, `tool.execute.after`의 `output` 파라미터 자체를 완전히 버린다(`agent-evaluator.ts:393` 부근) — 이미 훅이 받고 있는 데이터를 활용하지 않는 것이지, 새 훅 등록이 필요한 게 아니다.
- 현재 `"success"` 키가 없는 모든 tool_call은 `ToolCallAnalyzer`가 기본값 `True`(성공)로 간주한다 — 이는 SPEC-000 이전부터의 기존 동작이며, Gate G 점수가 실제보다 낙관적으로 나오는 근본 원인이다(§28.6에 이미 문서화된 알려진 한계).

## Goals

- `LiveGuardrail.record_tool_call()`이 도구 실행 **결과**(성공 여부, 종료 코드, 출력 텍스트)를 선택적으로 받아 `tool_calls` 항목에 반영하게 한다 — `ToolCallAnalyzer`가 이미 읽는 `"success"` 키를 실제 신호로 채운다.
- 도구 출력 텍스트(`stdout`/`stderr` 상당)를 저장하되, 무제한 누적으로 인한 스토리지 폭증을 막기 위해 길이를 제한(truncate)한다.
- OpenCode 플러그인이 이미 훅에서 받고 있는 `output.output`(타입으로 보장된 필드)을 캡처해 이 새 능력을 실사용에 연결한다 — exit code 탐지는 `metadata`가 `any`인 한계를 인정하고 최선 노력으로만 시도한다.
- `ToolCallAnalyzer`/Gate G 집계 로직 자체는 수정하지 않는다 — 이미 `"success"` 키를 읽으므로 입력 데이터만 채우면 된다(재해석 금지 원칙, SPEC-018/019와 동일).

## Non-Goals

- OpenCode `tool.execute.after`의 `metadata` 필드에서 exit code를 **확정적으로** 추출하는 것 — 공개 타입이 `any`라 필드명을 계약으로 보장할 수 없다. 이번 스펙은 후보 키(`exit`/`exitCode`/`code`) 몇 개를 방어적으로 시도하는 최선 노력 탐지만 제공하고, 신호가 없으면 기존과 동일하게 `success` 기본값 `True`로 안전하게 떨어진다. 정확한 스키마는 실제 라이브 OpenCode 세션에서 `console.log(JSON.stringify(output))`으로 직접 확인하는 후속 검증을 권장한다(Risks).
- `stdout`/`stderr`에 대한 PII 마스킹 — `redact_task_pii()`(SPEC-020)는 현재 `question`/`response`/`ground_truth`/`context`만 다루고 `tool_calls`는 건드리지 않는다(직접 확인). 도구 출력에 민감 정보가 포함될 위험은 이번 스펙 범위 밖 — Risks에서 명시적으로 인정하고 완화책만 제시한다.
- `ToolCallAnalyzer`/Gate G 집계 로직 변경 — 이미 `"success"` 키를 읽으므로 수정할 이유가 없다.
- 도구별로 다른 "성공"의 의미(예: `read`/`edit`는 예외 발생 여부, `bash`는 exit code)를 통합하는 범용 판정기 — 이번 스펙은 호출자가 이미 판단한 `success: bool`을 그대로 받아 저장할 뿐, SDK가 그 판단을 대신 내리지 않는다.

## Requirements

- **REQ-1**: `LiveGuardrail.__init__`에 `max_tool_output_chars: int = 2000` 파라미터를 추가한다(`judge_max_context_chars`와 동일한 길이 제한 원칙). `record_tool_call(task_id, tool_name, parameters=None, output=None)`에 새 옵션 파라미터 `output: Optional[Dict[str, Any]]`를 추가한다. `output`이 주어지면 허용된 키(`"success"`, `"exit_code"`, `"stdout"`, `"stderr"`)만 골라 tool_call 항목에 병합한다(그 외 키는 무시 — `name`/`arguments`를 실수로 덮어쓰지 않기 위한 allow-list 방식). `stdout`/`stderr`가 문자열이면 `max_tool_output_chars`로 truncate한다.
- **REQ-2**: `live_guardrail_stdio.py`의 `{"op": "record", ...}` 메시지에 선택적 `"output"` 필드를 추가 지원한다 — 있으면 `record_tool_call(..., output=msg.get("output"))`으로 전달한다. `init` 메시지에도 `max_tool_output_chars`를 전달할 수 있게 한다.
- **REQ-3**: OpenCode TS 플러그인의 `GuardrailSession.record()`가 `output: string`(캡처된 텍스트, `output.output` 그대로 truncate 없이 전체 전송 — truncate는 REQ-1의 Python 측 책임) 파라미터를 추가로 받아 `{"success", "exit_code", "stdout"}`을 구성해 stdio로 전달한다. `tool.execute.after`에서 `output.metadata`의 후보 키(`exit`/`exitCode`/`code`, 숫자 타입일 때만)를 방어적으로 조회해 `exit_code`/`success`를 채우고, 못 찾으면 `success`/`exit_code` 필드 자체를 생략한다(REQ-1의 allow-list가 없는 키는 무시하므로 안전).

## Interface

```python
# REQ-1 — 직접 Python 통합
guardrail = LiveGuardrail(
    tool_parameter_safety=ToolParameterSafetyConfig(),
    max_tool_output_chars=2000,  # 기본값
)
guardrail.record_tool_call(
    "t1", "bash", {"command": "pytest"},
    output={"success": False, "exit_code": 1, "stdout": "...", "stderr": "2 failed, 8 passed"},
)
snap = guardrail.snapshot()
# snap["tool_calls"][0] == {
#     "name": "bash", "arguments": {"command": "pytest"},
#     "success": False, "exit_code": 1,
#     "stdout": "...", "stderr": "2 failed, 8 passed",
# }
```

```python
# output 생략 시 기존과 100% 동일(회귀 없음)
guardrail.record_tool_call("t1", "search", {"q": "a"})
# -> {"name": "search", "arguments": {"q": "a"}}  (success 키 자체가 없음 — 기존 동작)
```

```typescript
// REQ-3 — TS 플러그인 (best-effort exit code 탐지)
"tool.execute.after": async (input, output) => {
  const meta = output.metadata as Record<string, unknown> | undefined
  const exitCode = [meta?.exit, meta?.exitCode, meta?.code]
    .find((v): v is number => typeof v === "number")
  await session.record(input.sessionID, input.tool, input.args, {
    stdout: output.output,
    ...(exitCode !== undefined ? { exit_code: exitCode, success: exitCode === 0 } : {}),
  })
}
```

## Acceptance

- **REQ-1**: `output=None`(기본값)으로 `record_tool_call()`을 호출하면 tool_call 항목에 `success`/`exit_code`/`stdout`/`stderr` 키가 전혀 없는지(기존 동작과 완전 동일 — 회귀 없음). `output={"success": False}`만 주면 `success` 키만 추가되고 나머지는 없는지. `output`에 `max_tool_output_chars`보다 긴 `stdout`을 주면 정확히 그 길이로 잘리는지. `output`에 `"name"`/`"arguments"` 키를 억지로 넣어도 무시되는지(allow-list 확인).
- **REQ-2**: stdio `{"op": "record", ..., "output": {"success": false, "exit_code": 1}}`을 보낸 뒤 `{"op": "snapshot"}`의 `extra.tool_calls`에 반영되는지. `output` 필드 없이 보낸 기존 방식의 `record` 메시지가 이전과 동일하게 동작하는지.
- **REQ-3**: (TS 변경 자체는 Python 테스트로 검증 불가 — 코드 리뷰 수준 확인) `output.metadata`에 `exit: 0`이 있으면 `success: true`가, `exit: 1`이면 `success: false`가 구성되는지 로직을 직접 대조. `metadata`에 후보 키가 전혀 없으면 `success`/`exit_code` 필드 자체를 생략해 REQ-1의 "회귀 없음" 경로를 그대로 타는지.
- **Gate G 통합**: `success=False`가 채워진 tool_call을 포함한 태스크를 `record_task()`한 뒤 `ToolCallAnalyzer`가 계산한 `success_rate`가 그 실패를 반영해 100% 미만으로 내려가는지(기존 `ToolCallAnalyzer` 테스트 스위트가 이미 검증한 로직 재확인 — 새 코드 아님).
- **회귀 없음**: `output` 파라미터를 전혀 쓰지 않는 기존 `record_tool_call()`/stdio `record` 호출부(SPEC-019/024/028/030 전체 테스트 스위트)가 무수정으로 통과하는지.

## Compatibility

- 100% additive — `output`/`max_tool_output_chars`는 새 옵트인 파라미터. 기본값(`None`/`2000`)에서는 `record_tool_call()`의 기존 시그니처·동작과 완전히 동일하다.
- `ToolCallAnalyzer`/Gate G 집계 로직은 전혀 수정하지 않는다 — 이미 `"success"` 키를 읽는 기존 코드가 무수정으로 새 데이터를 소비한다.
- TS 플러그인 변경은 `output.metadata`에서 신호를 못 찾으면 안전하게 아무 것도 전달하지 않으므로, 구버전 OpenCode나 다른 도구 타입에서도 예외 없이 동작한다(REQ-1의 allow-list가 없는 키를 무시).

## Rollout

1. REQ-1(`record_tool_call(output=...)` + truncation) — 가장 작고 독립적, Python 단독으로 완결.
2. REQ-2(stdio 브리지 확장) — REQ-1에 의존.
3. REQ-3(TS 플러그인 배선, best-effort exit code 탐지) — REQ-2에 의존, OpenCode 실사용 세션에서 실제로 이 데이터가 채워지는 마지막 조각. **착수 전 실제 OpenCode 세션에서 `output.metadata`의 진짜 스키마를 라이브로 확인할 것을 강력히 권장**(Risks 참조) — 확인 결과에 따라 후보 키 목록을 조정해야 할 수 있다.

## Risks

- **`metadata` 스키마 미검증**: 이 스펙에서 가장 중요한 리스크다 — `@opencode-ai/plugin`의 공개 타입이 `metadata: any`라, 실제 설치된 OpenCode 버전이 bash 도구의 exit code를 어떤 키로 노출하는지(혹은 노출하는지 여부조차) 이번 세션에서 라이브로 검증하지 못했다. REQ-3의 후보 키(`exit`/`exitCode`/`code`) 목록은 일반적인 관례에 근거한 추정이지 확인된 사실이 아니다. **완화책**: (a) 신호를 못 찾으면 기존과 동일하게 안전 폴백(success 필드 생략)하므로 최악의 경우에도 회귀는 없다 — 단지 기대한 개선이 안 나타날 뿐. (b) 팀이 실제 도입 전 `tool.execute.after`에 임시로 `console.log(JSON.stringify(output))`을 추가해 실제 세션 1회를 라이브 실행하고 진짜 스키마를 확인한 뒤 후보 키를 조정할 것을 권장.
- **PII 노출 확대**: `stdout`/`stderr`에 원치 않는 민감 정보(파일 내용, 환경 변수 덤프 등)가 그대로 저장될 수 있다 — `enable_pii_redaction`은 이 필드를 마스킹하지 않는다(확인됨). **완화책**: 문서에 "민감 정보가 포함될 수 있는 도구(예: `env`, `cat .env`)의 출력은 캡처하지 않도록 호출자가 선별할 것"을 권고. 자동 마스킹은 이번 스펙 범위 밖(Non-Goals) — 필요 시 별도 후속 스펙.
- **스토리지 증가**: 도구 호출마다 최대 `max_tool_output_chars`(기본 2000자) × 2(stdout/stderr)가 추가된다 — 세션이 도구를 많이 호출할수록 결과 파일이 커진다. **완화책**: 기본값을 보수적으로 낮게(2000자) 설정했고, 이미 `output=None`이면 전혀 저장되지 않는 완전 옵트인 기능이다.
- **`success` 판정 기준이 도구마다 다름**: `bash`류는 exit code가 자연스러운 기준이지만 `read`/`edit`류는 예외 발생 여부가 기준이라, REQ-3의 exit-code 전용 탐지 로직이 모든 도구 타입에 똑같이 유효하지 않을 수 있다 — Non-Goals에 명시한 대로 이번 스펙은 이 통합 판정 문제를 풀지 않는다.
