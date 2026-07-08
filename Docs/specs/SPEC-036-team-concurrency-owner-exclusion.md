# SPEC-036: `TeamConcurrencyConfig.owner` — 자기 자신의 클레임을 충돌로 오판하지 않기

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~3 전체 완료(2026-07-08)** · **의존성:** SPEC-032(완료) 버그 수정

> **구현 노트 (2026-07-08)**: 설계 그대로 편차 없이 구현했다. `TeamConcurrencyConfig`에
> `owner: Optional[str] = None` 추가(REQ-1). `live_guardrail.py`의 `_conflicts` 계산식에
> `_tc_cfg.owner is None or c.get("developer") != _tc_cfg.owner` 조건을 추가해, `owner`
> 미설정 시 필터가 전혀 적용되지 않도록(기존 동작 100% 보존, `developer` 필드가 없는
> malformed 클레임까지 실수로 제외되는 회귀도 방지) 구현(REQ-2). `shared_files_path`
> 검사는 수정하지 않음(REQ-3).
>
> 직접 실행으로 확인: `owner="수아"` 설정 시 수아 자신의 클레임과 겹치는 자기 스코프
> 편집이 통과(`block=False`)하고, 태호의 클레임과 겹치면 여전히 차단(`block=True`)됨을
> 확인. `owner` 미설정(기본값)에서는 자기 자신의 클레임도 여전히 차단되는 옛 동작이
> 그대로 보존됨을 확인(의도된 회귀 테스트). `shared_files_path`는 `owner` 설정과
> 무관하게 항상 차단됨을 확인.
>
> 테스트 5건 추가(`tests/test_spec036_team_concurrency_owner.py`). 전체 스위트
> 3,538 passed·회귀 0건(SPEC-035까지의 스위트 그대로, `owner` 미지정 사용처 전부
> 영향 없음).
>
> 품질 래칫: `team_concurrency.py` UP045 +1(신규 `Optional[str]` 필드 — 기존
> 지배적 컨벤션과 일치). `live_guardrail.py` E501 순증가 0건. mypy 신규 findings 없음.
>
> **후속 조치**: 이 버그는 Ch27 §27.2 TeamConcurrencyConfig 예제 코드, Ch28 §28.5
> 예제 코드를 실제로 실행 가능한 캡스톤 시나리오(Ch29 §29.10)로 검증하는 과정에서
> 발견했다 — 두 예제 코드 모두 `owner`를 지정하도록 갱신하고, `owner`를 생략하면
> 자기 자신의 클레임도 충돌로 잡힌다는 경고를 추가했다.

## Context

- Ch29 §29.10(캡스톤 실습) 작성을 위해 3인 팀 시나리오(수아=`configs.py` 담당, 태호=`evaluators.py` 담당)를 실제로 실행하며 검증하던 중 발견했다: 수아가 `.aoo/claims.jsonl`에 자기 스코프(`configs.py`)를 클레임한 뒤, 그 스코프 안에서 `edit`을 시도하면 `TeamConcurrencyConfig`가 이걸 **차단**한다.
- 원인: `check_before_tool_call()`의 team_concurrency 검사(`live_guardrail.py`)는 `self._team_claims`(클레임 파일에 있는 **모든** 활성 클레임)와 겹치는지만 확인하고, "이 세션을 누가 운영하는지"는 전혀 모른다. `LiveGuardrail`은 애초에 "현재 세션의 개발자가 누구인지"를 받는 파라미터가 없다 — 그래서 자기 자신이 정당하게 건 클레임도 무조건 "충돌"로 잡힌다.
- 이건 §28.5/§29.2가 설명하는 의도된 워크플로우("클레임을 걸고 나서 그 스코프 안에서 세션을 진행한다")를 **문자 그대로 따르면 항상 자기 자신에게 막히는** 실제 버그다. 기존 SPEC-032/034 데모(Ch27 섹션 6-B, Ch28 §28.5)는 전부 "다른 개발자(alice)가 클레임을 쥐고 있고, 이 세션은 그 클레임과 무관한 제3자"인 경우만 시연했다 — "자기 자신의 클레임과 자기 세션"을 함께 테스트한 적이 없어서 지금까지 발견되지 못했다.

## Goals

- `TeamConcurrencyConfig`에 `owner: Optional[str] = None`을 추가한다. 설정되면, `developer` 필드가 `owner`와 일치하는 클레임은 충돌 검사에서 제외된다 — 자기 자신의 클레임은 자기 세션을 막지 않는다.
- 다른 개발자의 클레임은 `owner` 설정 여부와 무관하게 계속 정확히 잡아낸다 — 이 수정은 "자기 자신 예외"만 추가할 뿐 겹침 판정 로직 자체를 바꾸지 않는다.
- `owner` 미설정(기본값 `None`)이면 기존 동작과 100% 동일 — 회귀 없음.

## Non-Goals

- 클레임에 `developer` 필드가 없는(malformed) 경우를 위한 새로운 검증 로직 — 기존과 동일하게 처리한다(그 클레임은 계속 충돌 후보로 남는다, `owner` 매칭 대상이 아니므로).
- `shared_files_path` 검사에 같은 예외를 적용하지 않는다 — 공유 파일은 정의상 "본인 포함 모두가 조율해야 하는" 자원이라, 본인이라고 예외를 주면 그 파일의 존재 이유가 없어진다(Risks에 명시).

## Requirements

- **REQ-1**: `TeamConcurrencyConfig`에 `owner: Optional[str] = None` 필드를 추가한다.
- **REQ-2**: `live_guardrail.py`의 team_concurrency 충돌 검사를, `_tc_cfg.owner`가 `None`이 아니면 `c.get("developer") == _tc_cfg.owner`인 클레임을 `_conflicts` 계산에서 제외하도록 수정한다. `_tc_cfg.owner`가 `None`이면(기본값) 필터를 적용하지 않는다 — 기존 동작과 완전히 동일(REQ-2는 조건문을 `_tc_cfg.owner is None or c.get("developer") != _tc_cfg.owner`처럼 작성해, `owner` 미설정 시 `developer` 필드가 아예 없는 malformed 클레임까지 실수로 제외되는 회귀를 만들지 않는다).
- **REQ-3**: `shared_files_path` 기반 검사는 이 예외의 영향을 받지 않는다 — 수정하지 않는다.

## Interface

```python
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig

# 수아의 세션 — 자기 자신의 클레임(developer="수아")은 충돌로 잡히지 않는다
guardrail = LiveGuardrail(
    team_concurrency=TeamConcurrencyConfig(claims_path=".aoo/claims.jsonl", owner="수아"),
)
verdict = guardrail.check_before_tool_call(
    "suah-session", "edit", {"file": "agent_evaluator/gates/gate_f_multiagent/configs.py"},
)
# 이 파일을 "수아"가 클레임했다면 verdict.block == False (자기 자신)
# 다른 개발자가 클레임했다면 여전히 verdict.block == True
```

## Acceptance

- **REQ-1/2**: `owner`가 설정된 상태에서, `owner`와 같은 `developer`의 클레임과 겹치는 스코프 편집이 차단되지 않는지. 다른 `developer`의 클레임과 겹치면 여전히 차단되는지. `owner` 미설정(기본값)에서 자기 자신의 클레임도 여전히(기존과 동일하게) 차단되는지(회귀 확인용 — 고쳐지지 않은 옛 동작이 `owner` 미지정 시 그대로 보존됨을 검증).
- **REQ-3**: `owner`가 설정돼도 `shared_files_path`에 등록된 파일은 여전히 차단되는지(본인 예외가 적용되지 않음을 확인).
- **회귀 없음**: 기존 SPEC-032/034/035 테스트 스위트 전체가 무수정으로 통과하는지.

## Compatibility

- 100% additive — 신규 옵트인 필드 하나만 추가. 기존 `TeamConcurrencyConfig`/`LiveGuardrail` 사용 코드(Ch27/28/29 기존 예제 포함)는 `owner`를 지정하지 않으므로 전부 기존 동작 그대로 유지된다.
- Ch27/28/29에 이미 있는 `TeamConcurrencyConfig` 사용 권장 패턴에는 이 필드를 명시적으로 추가하는 문서 보강이 필요하다 — 지금까지의 문서는 이 버그의 존재를 몰랐으므로 "클레임을 걸고 그 안에서 작업한다"는 워크플로우가 실제로는 항상 자기 자신에게 막힌다는 사실을 언급하지 않았다.

## Rollout

1. REQ-1(`owner` 필드) — 가장 작고 독립적.
2. REQ-2(충돌 검사 예외 로직) — REQ-1에 의존, 이 스펙의 핵심.
3. REQ-3은 "수정하지 않음"이 요구사항이므로 별도 구현 없음 — 회귀 테스트로만 확인.

## Risks

- **`owner` 문자열이 클레임의 `developer` 필드와 정확히 일치해야 한다.** 오타(`"Suah"` vs `"수아"`)가 있으면 예외가 적용되지 않아 여전히 자기 자신에게 막힌다 — 새로운 실패 모드는 아니지만(기존에도 항상 막혔으므로), 이 필드를 도입한 이후에는 "왜 아직도 막히지?"라는 새로운 디버깅 포인트가 될 수 있다. Ch27/28/29 문서에 `owner`는 클레임 로그에 기록한 `developer` 문자열과 정확히 같아야 한다는 점을 명시해야 한다.
- **이 수정 전에 작성된 클레임 로그**에 `developer` 필드가 일관되지 않게 기록돼 있었다면(예: 팀원마다 다른 표기), `owner` 도입 이후에도 자기 자신 예외가 제대로 동작하지 않을 수 있다 — 새 워크플로우를 팀에 도입할 때 `developer` 표기를 통일하도록 권장.
