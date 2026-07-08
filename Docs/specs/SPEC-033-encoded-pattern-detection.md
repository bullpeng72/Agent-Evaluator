# SPEC-033: 인코딩 우회 탐지 — `dangerous_patterns`의 base64/hex 디코드 전처리 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~4 전체 완료(2026-07-08)** · **의존성:** 없음(`gate_b_behavioral/evaluators.py`의 기존 `eval_tool_parameter_safety()` 순수 확장)

> **구현 노트 (2026-07-08)**: 설계안 그대로 구현했으나, 후보 문자열 최소 길이를
> **설계 시점보다 낮춰야 했다** — 유일한 편차. 원래 base64 최소 16자/hex 최소
> 8바이트로 설계했으나, 실제로 `"rm -rf /"`(8바이트)를 base64로 인코딩하면
> 12자밖에 되지 않아 16자 기준으로는 검증 예제 자체가 통과하지 못하는 것을
> 직접 실행해 발견했다 — base64 8자(≈6바이트)/hex 6그룹(6바이트)으로 하향
> 조정(`_BASE64_CANDIDATE_RE = r"[A-Za-z0-9+/]{8,}={0,2}"`,
> `_HEX_CANDIDATE_RE = r"(?:[0-9a-fA-F]{2}){6,}"`) — 오탐 방지는 길이 기준이
> 아니라 REQ-2의 printable 90% 필터가 담당하도록 설계를 그대로 유지했다.
> REQ-1: `ToolParameterSafetyConfig.decode_encodings: bool = False`. REQ-2:
> `_extract_decoded_candidates()` 순수 함수 — base64/hex 후보 탐색 → 디코드 →
> printable 90% 필터 → `max_depth`(기본 2) 재귀. REQ-3:
> `eval_tool_parameter_safety()`의 기존 `dangerous_patterns` 매칭 루프 직후에
> `config.decode_encodings`가 True일 때만 실행되는 두 번째 루프 추가, 위반 키에
> `:decoded` 접미사. REQ-4는 별도 코드 없이 REQ-2의 길이 제한(`max_argument_length`
> 상속)·`max_depth`로 충족.
>
> 직접 실행으로 확인: (a) `"rm -rf /"`의 base64/hex 인코딩이 `decode_encodings=True`
> 에서 정확히 차단됨, `False`(기본값)에서는 통과함(회귀 없음). (b) 32바이트 무작위
> 토큰(API 키 시뮬레이션)이 디코드는 되지만 대부분 비출력 바이트라 후보에서
> 자동 배제 — 오탐 없음을 직접 확인. (c) 이중 인코딩(base64(base64(...)))이
> `max_depth=2`에서 정확히 복구됨. (d) git SHA 스타일 hex 문자열이 디코드 후
> 비printable이라 후보에서 배제됨.
>
> 테스트 11건 추가(`TestToolParameterSafetyDecodeEncodings` 5건 — 기본값 회귀
> 없음/base64 차단/hex 차단/정상 명령 통과/무작위 토큰 오탐 없음,
> `TestExtractDecodedCandidates` 6건 — base64·hex 왕복/무작위 바이트 배제/이중
> 인코딩 복구/`max_depth=0`/인코딩 없는 입력). 전체 스위트 **3,505 passed, 1 skipped,
> 회귀 0건**(기존 3,494 + 신규 11).
>
> 품질 래칫: `configs.py` 순변화 0(E501/UP006/UP045 전부 동일). `evaluators.py`
> UP006 +3(신규 `List[str]` 타입힌트 3곳 — 이 파일에 이미 지배적인 컨벤션과 일치,
> SPEC-027 이후 동일 패턴). mypy 신규 findings 없음(`Success: no issues found`).

## Context

- `ToolParameterSafetyConfig.dangerous_patterns`는 도구 호출 인자를 JSON 직렬화한 문자열(`args_str`)에 정규식을 직접 매치한다(`gate_b_behavioral/evaluators.py:604-629`). 이 방식은 `rm -rf`처럼 패턴이 **그 문자열 안에 평문으로 존재**할 때만 잡는다.
- 외부 검토(2026-07-08)에서 `echo "cm0gLXJmIC8=" | base64 -d | sh`(base64로 인코딩된 `rm -rf /`)처럼 평문 우회를 지적받았다 — 정확한 관찰이다. Ch27 §27.5/§27.6이 이미 "블랙리스트 패턴 매칭이지 완전한 보안 경계가 아니다"라고 여러 차례 명시하지만, 이 특정 우회 형태(흔한 인코딩)는 **정적 전처리만으로 상당 부분 완화 가능**하다 — 별도 샌드박스·syscall 추적 없이도 base64/hex로 인코딩된 하위 문자열을 디코드해 같은 `dangerous_patterns`로 재매치하면 잡을 수 있다.
- 검토 과정에서 "샌드박스 내 dry-run으로 syscall을 가로채 차단한다"는 대안도 제시됐으나 기각했다 — dry-run은 실제로는 격리 환경에서의 **진짜 실행**이라 "실행 전 차단"이라는 `LiveGuardrail`의 순수 조회 모델과 근본적으로 다른 아키텍처이고, 이 SDK의 범위를 벗어난다(Non-Goals 참조).

## Goals

- `ToolParameterSafetyConfig`에 옵트인 필드를 추가해, 인자 문자열에서 base64/hex로 보이는 하위 문자열을 찾아 디코드한 뒤 그 결과에도 기존 `dangerous_patterns`를 재매치한다.
- 새 탐지 규칙을 만들지 않는다 — 기존 `dangerous_patterns` 목록을 그대로 재사용하되, **검사 대상 텍스트를 하나 더(디코드된 버전) 추가**하는 순수 전처리 계층이다.
- 기본값은 기존 동작과 100% 동일(회귀 없음) — 옵트인.

## Non-Goals

- 샌드박스/컨테이너 내 실제 실행(dry-run) 기반 탐지 — 아키텍처가 근본적으로 다르고(순수 조회가 아니라 격리 실행), 이 SDK의 범위 밖. LiveGuardrail이 필요로 하는 "부작용 없는 순수 조회" 계약을 지킬 수 없다.
- base64/hex 이외의 인코딩(URL 인코딩 체인, ROT13, XOR, 커스텀 난독화) — 가장 흔한 두 가지만 다룬다. 다른 인코딩까지 다루려면 후보 인코딩 목록을 확장하는 후속 스펙이 필요하다.
- 실행 시점에 환경변수·네트워크 응답에 따라 내용이 달라지는 페이로드 탐지 — 정적 분석의 근본적 한계이며 이번 스펙이 풀 수 있는 문제가 아니다. 이 한계는 정직하게 문서화한다(Risks).
- 완전한 보안 경계로의 격상 — 이 스펙 적용 후에도 `LiveGuardrail`은 여전히 블랙리스트 방어이며, Ch27 §27.6의 샌드박스·격리 권고는 그대로 유효하다.

## Requirements

- **REQ-1**: `ToolParameterSafetyConfig`에 `decode_encodings: bool = False`를 추가한다. `True`면 REQ-2의 디코드 전처리가 활성화된다.
- **REQ-2**: `gate_b_behavioral/evaluators.py`에 `_extract_decoded_candidates(text: str, max_depth: int = 2) -> List[str]`를 추가한다 — `text`에서 base64로 보이는 하위 문자열(`[A-Za-z0-9+/]{8,}={0,2}`, 길이 8자 이상 — `"rm -rf /"`처럼 짧은 위험 명령의 인코딩 결과까지 잡을 수 있는 최소값, 구현 중 검증 예제로 직접 확인)과 hex로 보이는 하위 문자열(`(?:[0-9a-fA-F]{2}){6,}`, 6바이트 이상)을 찾아 디코드를 시도한다. 디코드 결과가 (a) 성공하고 (b) 대부분 출력 가능한 문자(printable, 최소 90%)로 구성되면 후보 문자열로 채택한다 — 오탐 방지는 길이 기준이 아니라 이 printable 필터가 담당한다. 채택된 각 후보에 대해 재귀적으로 같은 탐지를 반복하되 `max_depth`(기본 2)로 깊이를 제한한다(이중 인코딩까지만 — DoS 방지).
- **REQ-3**: `eval_tool_parameter_safety()`에서 `config.decode_encodings`가 `True`이면, 기존 `args_str` 매치에 더해 `_extract_decoded_candidates(args_str)`가 반환한 각 후보 문자열에도 `dangerous_patterns`를 재매치한다. 매치되면 위반 키를 `dangerous_pattern:{name}:{pattern}:decoded`로 남겨(기존 `dangerous_pattern:{name}:{pattern}`과 구분되는 접미사) 감사 시 "평문이 아니라 디코드된 내용에서 발견됨"을 알 수 있게 한다. `dangerous_calls`/`fail_on_dangerous` 등 기존 흐름은 그대로 재사용한다(새 차단 경로를 만들지 않음).
- **REQ-4**: 디코드 후보 탐색·재귀는 `config.max_argument_length`로 이미 길이가 제한된 `args_str`을 입력으로 받으므로 별도 길이 상한이 필요 없다 — 다만 `max_depth` 기본값(2)을 넘는 깊이는 시도하지 않는다.

## Interface

```python
from agent_evaluator.gates.gate_b_behavioral.configs import ToolParameterSafetyConfig

config = ToolParameterSafetyConfig(
    dangerous_patterns=[r"\brm\s+\S", r"&&", r"\|\|"],  # 기존 패턴 그대로 재사용
    scope_tool_names=["bash"],
    fail_on_dangerous=True,
    decode_encodings=True,  # 신규 — base64/hex로 인코딩된 하위 문자열도 같은 패턴으로 검사
)

# echo "cm0gLXJmIC8=" | base64 -d | sh  ("rm -rf /"의 base64 인코딩)
verdict = guardrail.check_before_tool_call(
    "t1", "bash", {"command": 'echo "cm0gLXJmIC8=" | base64 -d | sh'},
)
# decode_encodings=False(기본값)면 평문에 "rm -rf"가 없으므로 통과
# decode_encodings=True면 "cm0gLXJmIC8="를 디코드해 "rm -rf /"를 얻고 \brm\s+\S에 매치 → block=True
```

## Acceptance

- **REQ-1**: `decode_encodings` 생략 시 기존 `ToolParameterSafetyConfig()`와 완전히 동일하게 동작(회귀 없음).
- **REQ-2**: 알려진 base64 인코딩 문자열(`"cm0gLXJmIC8="` → `"rm -rf /"`)을 넣으면 후보 목록에 디코드 결과가 포함되는지. 무작위 바이트로 디코드되는(비출력 문자 비율 높은) base64 유사 문자열은 후보에서 제외되는지(오탐 방지 확인). 2단계까지 중첩 인코딩된 문자열도 `max_depth=2`에서 잡히는지, 3단계는 잡히지 않는지(깊이 제한 확인).
- **REQ-3**: `decode_encodings=True`에서 인코딩된 위험 명령이 `fail_on_dangerous=True`와 함께 실제로 `block=True`를 만드는지(엔드투엔드). 위반 키에 `:decoded` 접미사가 붙는지. `decode_encodings=False`(기본값)에서는 같은 입력이 차단되지 않는지(옵트인 확인).
- **회귀 없음**: `decode_encodings`를 쓰지 않는 기존 `ToolParameterSafetyConfig`/`eval_tool_parameter_safety()` 사용 코드(Ch27/28 예제 포함)가 이전과 완전히 동일하게 동작하는지 — 기존 테스트 스위트 전체가 무수정으로 통과하는지 확인.

## Compatibility

- 100% additive — `decode_encodings`는 새 옵트인 필드, 기본값 `False`에서는 이번 스펙의 모든 로직이 완전히 비활성화된다.
- 새 위반 키 포맷(`:decoded` 접미사)은 기존 `dangerous_pattern:{name}:{pattern}` 포맷의 확장이라 `_summarize_violations()`(SPEC-024)·`search_violations()` 등 기존 소비자가 이미 처리하는 문자열 포맷과 호환된다 — 별도 파싱 로직 변경이 필요 없다(그냥 더 긴 문자열일 뿐).

## Rollout

1. REQ-1(`decode_encodings` 필드) — 가장 작고 독립적.
2. REQ-2(`_extract_decoded_candidates()`) — REQ-1과 독립적으로 단위 테스트 가능한 순수 함수.
3. REQ-3(`eval_tool_parameter_safety()` 연동) — REQ-1/2에 의존, 이번 스펙의 핵심 가치.
4. REQ-4는 REQ-2 구현에 포함(별도 롤아웃 단계 아님).

## Risks

- **이중 인코딩을 넘어서는 우회는 여전히 못 잡는다.** `max_depth=2`를 넘는 인코딩, base64/hex 외의 인코딩, 실행 시점에 결정되는 페이로드는 이 스펙의 범위 밖이다 — "이제 완전히 안전하다"는 인상을 주면 안 된다. Ch27 §27.5/§27.6의 기존 경고(블랙리스트 방어, 샌드박스 병행 필요)는 이 스펙 적용 후에도 그대로 유효하다.
- **오탐 가능성**: 정상적인 인자에 우연히 base64/hex처럼 보이는 문자열(해시값, 토큰, ID 등)이 포함될 수 있다 — 디코드 성공 + printable 비율 90% 기준으로 대부분 걸러지지만, 완전히 배제되지는 않는다. `decode_encodings`를 켤 때는 실제 사용 중인 도구 인자에 이런 문자열이 흔한지 먼저 확인할 것을 권장(§27.5에 안내 추가).
- **성능**: 옵트인이므로 기본 경로에는 영향이 없다. 켜져 있을 때는 도구 호출마다 정규식 탐색 + 디코드 시도가 추가되지만, `args_str`이 이미 `max_argument_length`(기본 2000자)로 제한돼 있어 비용이 크지 않다.
