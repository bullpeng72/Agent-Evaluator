# SPEC-037: `TeamConcurrencyConfig.owner="auto"` — git config user.name 자동 주입

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — 전체 완료(2026-07-08)** · **의존성:** SPEC-036(완료), SPEC-027(`agent_version="auto"` 패턴 재사용)

> **구현 노트 (2026-07-08)**: 설계 그대로 편차 없이 구현했다. `team_concurrency.py`에
> `resolve_owner(owner: Optional[str]) -> Optional[str]` 함수를 추가 — `"auto"`가 아니면
> 그대로 반환하는 순수 변환이고, `"auto"`이면 `git config user.name`을 1회 조회한다.
> `live_guardrail.py`의 `LiveGuardrail.__init__()`에서 `team_claims` 로딩과 같은 시점에
> `self._team_concurrency_owner = resolve_owner(team_concurrency.owner)`로 1회만 해석해
> 캐싱하고, `_conflicts` 계산식은 `_tc_cfg.owner` 대신 이 캐싱된 값을 참조하도록 수정했다.
> 원본 `TeamConcurrencyConfig` 객체는 변경하지 않는다(`owner="auto"` 문자열 그대로 보존) —
> 같은 config 객체를 여러 `LiveGuardrail`에 재사용해도 안전하다.
>
> 직접 실행으로 확인: `owner="auto"`가 실제 `git config user.name`("Sungwoo Kim")으로
> 해석되어 자기 자신의 클레임을 예외 처리하고, 다른 개발자의 클레임은 여전히 차단함을
> 확인. git 조회 실패(mock으로 `FileNotFoundError` 재현) 시 `None`으로 조용히 떨어져
> SPEC-036 이전의 옛 동작(자기 클레임도 차단)이 그대로 보존됨을 확인 — 새 기능이
> 실패해도 "차단 안 해야 할 걸 차단"하는 방향으로만 안전하게 무너진다.
>
> 테스트 13건 추가(`tests/test_spec037_owner_auto.py`) — `resolve_owner()` 단위
> 테스트(정상/비정상 종료 코드/빈 문자열/예외/타임아웃 5건), 패스스루 테스트(`None`/명시적
> 이름 3건), `LiveGuardrail` 통합 테스트(자기 클레임 제외/타인 클레임 차단/조회 실패 시
> 폴백/원본 config 불변/owner 미지정 시 subprocess 미호출 5건). 전체 스위트 3,588 passed
> (SPEC-034의 사전 존재하던 시간 의존 테스트 2건 제외 — 본 스펙과 무관, 아래 Risks 참고),
> 회귀 0건.
>
> **후속 조치**: SPEC-036이 `owner` 필드로 "자기 자신의 클레임" 오탐을 고쳤지만, `owner`를
> 빼먹으면 다시 같은 함정에 빠진다는 점이 외부 검토에서 지적됐다 — Ch27 §27.3/Ch28 §28.5/
> Ch29 §29.10 예제 코드를 전부 `owner="auto"` 권장으로 갱신하고, `agent-eval claims add`
> CLI(SPEC-038)의 `--developer` 기본 동작도 동일한 `resolve_owner()`를 재사용해 일관성을
> 맞췄다.

## Context

- SPEC-036 Context가 기록한 실제 버그(§29.10 캡스톤 실행 중 발견) — `owner`를 지정하지
  않으면 `TeamConcurrencyConfig`가 자기 자신의 클레임도 충돌로 잡아 자기 세션을 막는다 —
  는 `owner` 필드 도입으로 고쳐졌지만, `owner="수아"`처럼 매번 문자열을 직접 타이핑해야
  하는 사용자 경험은 그대로 남았다. 오타나 누락이 있으면 SPEC-036 이전과 동일한 증상이
  재발한다.
- SDK에는 이미 같은 형태의 문제를 해결한 선례가 있다 — `PerformanceMonitor(agent_version=
  "auto")`(SPEC-027)는 `git rev-parse HEAD`를 1회 조회해 커밋 SHA를 자동 태깅한다. `owner`
  필드에도 동일한 `"auto"` 센티널 패턴(`git config user.name` 조회, fail-open on 예외)을
  적용하면 새 개념을 추가하지 않고 기존 SDK 관용구를 그대로 확장할 수 있다.
- 외부 검토(AOO Stack 기능 개선 분석)가 "owner 누락 버그에 대한 경고 고도화 — pre-commit
  훅이나 CLI에서 owner를 자동으로 주입하는 루틴을 추가해야 한다"는 개선 항목으로 이 문제를
  다시 지적했다 — 경고 문구를 강화하는 대신, 애초에 실수할 수 없게 만드는 이 스펙으로
  대응한다.

## Goals

- `TeamConcurrencyConfig.owner`에 `"auto"` 예약 센티널을 추가한다 — 설정 시 `LiveGuardrail`
  생성 시점에 `git config user.name`을 1회 조회해 자동 치환한다.
- git 조회가 어떤 이유로든 실패하면(git 미설치·`user.name` 미설정·비-git 환경 등) 예외
  없이 `None`으로 떨어진다 — 이 경우 SPEC-036 이전의 기존 동작(자기 클레임도 차단)이
  그대로 유지된다(fail-open, 새로운 실패 모드 아님).
- `"auto"` 외의 다른 문자열이나 `None`은 기존과 100% 동일하게 동작한다 — 회귀 없음.
- 원본 `TeamConcurrencyConfig` 객체는 변경하지 않는다 — 해석된 값은 `LiveGuardrail` 내부에만
  캐싱한다.

## Non-Goals

- `agent-eval claims add`의 `--developer` 인자 자체를 이 스펙에서 구현하지 않는다(SPEC-038의
  범위) — 다만 SPEC-038은 이 스펙이 만드는 `resolve_owner()`를 재사용한다.
- git 사용자 이름을 클레임 로그의 `developer` 필드와 강제로 동기화하는 검증 로직을 추가하지
  않는다 — 여전히 팀이 `developer` 표기를 통일해야 `owner="auto"`가 의미 있게 매칭된다
  (SPEC-036 Risks와 동일한 한계).

## Requirements

- **REQ-1**: `team_concurrency.py`에 `resolve_owner(owner: Optional[str]) -> Optional[str]`
  함수를 추가한다. `owner != "auto"`이면 그대로 반환한다.
- **REQ-2**: `owner == "auto"`이면 `subprocess.run(["git", "config", "user.name"], ...)`을
  호출해 `stdout.strip()`을 반환한다. `returncode != 0`이거나 결과가 빈 문자열이면 `None`을
  반환한다.
- **REQ-3**: REQ-2의 조회가 어떤 예외(FileNotFoundError, TimeoutExpired 등)를 던지든
  전파하지 않고 `None`을 반환한다(`agent_version="auto"`의 git 조회와 동일한 fail-open
  원칙).
- **REQ-4**: `LiveGuardrail.__init__()`은 `team_concurrency`가 설정되면 생성자 시점에
  `resolve_owner(team_concurrency.owner)`를 1회 호출해 `self._team_concurrency_owner`에
  캐싱한다 — `team_claims` 로딩과 동일한 "1회만 조회" 원칙(순수 조회 계약 유지).
- **REQ-5**: 충돌 판정 로직(`_conflicts` 계산)은 `_tc_cfg.owner` 대신
  `self._team_concurrency_owner`를 참조하도록 수정한다.
- **REQ-6**: 원본 `TeamConcurrencyConfig` 객체의 `owner` 필드는 수정하지 않는다.

## Interface

```python
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig

guardrail = LiveGuardrail(
    team_concurrency=TeamConcurrencyConfig(claims_path=".aoo/claims.jsonl", owner="auto"),
)
# git config user.name == "Sungwoo Kim"이면, 그 이름으로 건 클레임과 겹치는
# 자기 자신의 편집은 차단되지 않는다. 다른 개발자의 클레임은 여전히 차단된다.
```

## Acceptance

- `resolve_owner("auto")`가 mock된 `git config user.name` 출력을 그대로 반환하는지.
- `resolve_owner("auto")`가 비정상 종료 코드/빈 문자열/예외/타임아웃 각각에서 `None`을
  반환하는지.
- `resolve_owner(None)`/`resolve_owner("명시적 이름")`이 그대로 반환되는지(subprocess 호출
  없음).
- `owner="auto"`가 해석된 `LiveGuardrail`에서 자기 자신의 클레임은 통과, 다른 개발자의
  클레임은 여전히 차단되는지.
- git 조회 실패 시 SPEC-036 이전 동작(자기 클레임도 차단)이 보존되는지.
- 원본 `TeamConcurrencyConfig.owner`가 `LiveGuardrail` 생성 후에도 `"auto"` 그대로인지.
- `owner` 미지정(기본값 `None`)일 때 `subprocess.run`이 전혀 호출되지 않는지("auto" 경로를
  타지 않음을 확인).

## Compatibility

- 100% additive — `"auto"`는 새 예약 문자열일 뿐, 기존에 이 문자열을 `owner`로 실제 사용하던
  코드는 없었다(있었다면 이제 자동 해석 대상이 되므로 이 점을 changelog에 명시). `None`과
  다른 명시적 문자열의 동작은 완전히 그대로다.

## Rollout

1. `resolve_owner()` 함수(REQ-1~3) — 가장 작고 독립적, `team_concurrency.py`에만 영향.
2. `LiveGuardrail.__init__()` 연동(REQ-4~6) — REQ-1에 의존.
3. Ch27/28/29 문서에 `owner="auto"` 권장 반영(SPEC-038과 함께 처리).

## Risks

- **`git config user.name`이 클레임 로그의 `developer` 필드와 정확히 일치해야 한다.** 팀원이
  로컬 git 설정과 다른 이름으로 클레임을 기록했다면(예: 닉네임), `owner="auto"`가 매칭되지
  않아 여전히 자기 자신에게 막힌다 — SPEC-036의 동일한 리스크가 그대로 적용된다. `agent-eval
  claims add --developer auto`(SPEC-038)를 함께 쓰면 클레임 기록과 owner 해석이 같은 소스
  (`git config user.name`)를 쓰게 되어 이 리스크가 실질적으로 줄어든다.
- **CI 환경 등 `git config user.name`이 설정되지 않은 곳에서는 `None`으로 떨어진다.** 이는
  fail-open 설계이므로 크래시는 없지만, "왜 owner="auto"가 안 먹히지?"라는 디버깅 포인트가
  될 수 있다 — 개인 로컬 개발 루프를 위한 기능임을 문서에 명시해야 한다(CI 자동화 세션에는
  명시적 `owner` 문자열 사용을 권장).
