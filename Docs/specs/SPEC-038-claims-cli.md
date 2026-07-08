# SPEC-038: `agent-eval claims` CLI — 클레임 로그 터미널 관리

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — 전체 완료(2026-07-08)** · **의존성:** SPEC-032(`append_claim`/`load_active_claims`), SPEC-034(`audit_claims`), SPEC-037(`resolve_owner`)

> **구현 노트 (2026-07-08)**: 설계 그대로 편차 없이 구현했다. `agent_evaluator/cli/claims.py`를
> 신설해 `add`/`list`/`release`/`audit` 4개 서브-서브커맨드를 두었다 — 각각
> `append_claim()`/`load_active_claims()`/`audit_claims()`(전부 기존 SDK 함수)를 얇게 감쌀
> 뿐, 새 판정 로직은 추가하지 않았다. `main.py`에 `build_claims_subparser(sub)` 호출과
> `"claims": cmd_claims` 핸들러 등록만 추가했다(`trend`/`opencode`/`monitor` 서브커맨드와
> 동일한 기존 배선 패턴).
>
> 구현 중 실제 버그 1건을 스모크 테스트로 발견·수정했다: `_cmd_claims_add`의 초안이
> `args.developer or resolve_owner("auto")`로 작성돼 있었는데, `--developer auto`를
> **명시적으로** 넘기면 `args.developer`가 이미 truthy(`"auto"`)라 `or`가 단락 평가되어
> `resolve_owner()`가 아예 호출되지 않고 `developer="auto"`라는 리터럴 문자열이 그대로
> 클레임 로그에 저장되는 버그였다. `resolve_owner(args.developer or "auto")`로 수정해
> "생략"과 "명시적 auto" 두 경우 모두 같은 해석 경로를 타도록 고쳤다 — 이 버그는 자동
> 테스트로도 재현·고정했다(`test_add_developer_auto_literal_resolves_via_git`).
>
> 실제 실행으로 확인: `agent-eval claims add/list/release/audit` 전체 흐름(임시 디렉터리에서
> 클레임 개설 → 목록 조회 → 해제 → 감사)이 CLI를 통해 정확히 동작. TTL 초과 케이스에서
> `audit`가 종료 코드 1과 위반 상세를 정확히 출력함을 확인.
>
> 테스트 21건 추가(`tests/test_cli_claims.py`) — add(명시적/자동/명시적 auto 리터럴/생성 실패/
> 디렉터리 자동 생성/다중 스코프 8건), list(빈 상태/표시/해제 제외/파싱 실패 내성 4건),
> release(정상/미존재+force 없음/미존재+force 3건), audit(정상/TTL/겹침 3건), dispatcher(정상
> 라우팅/누락/미상 3건). 전체 스위트 3,596 passed(SPEC-034의 사전 존재하던 시간 의존 테스트
> 2건 제외, SPEC-037 참고), 회귀 0건.
>
> **후속 조치**: `scripts/pre_commit_claim_check.py`(문서 전용, 별도 SPEC 없음)가 이
> CLI와 나란히 Ch29 §29.2에 pre-commit 훅 층으로 추가됐다 — `agent-eval claims audit`가
> CI 사후 감사를, pre-commit 훅이 커밋 시점 로컬 확인을 담당하는 역할 분담이다.

## Context

- SPEC-032/034/036/037까지 `TeamConcurrencyConfig`/`append_claim()`/`load_active_claims()`/
  `audit_claims()`/`resolve_owner()`는 전부 **파이썬 코드로 직접 임포트해 호출**하는 것만
  지원했다 — 클레임을 걸거나 해제하려면 매번 짧은 스크립트나 `python -c "..."` 한 줄을
  작성해야 했다.
- 외부 검토(AOO Stack 기능 개선 분석)가 "Claim 관리 CLI/IDE 플러그인 — claim init/acquire/
  release 명령어를 제공하는 경량 CLI 개발"을 개선 항목으로 제시했다 — 다른 `agent-eval`
  서브커맨드(`dataset`, `trend`, `opencode`)와 동일한 패턴으로 확장 가능한 지점이었다.
- `agent_evaluator/cli/` 디렉터리는 이미 `monitor.py`/`opencode.py`/`trend.py`처럼 기능별
  독립 파일 + `build_X_subparser()`/`cmd_X()` 두 함수를 `main.py`에 등록하는 확립된 컨벤션이
  있다 — 새 아키텍처를 도입하지 않고 이 컨벤션을 그대로 따랐다.

## Goals

- `agent-eval claims add <scope...> [--developer NAME] [--claims-path PATH] [--claim-id ID]`
  — 새 클레임 개설.
- `agent-eval claims list [--claims-path PATH]` — 활성 클레임을 사람이 읽기 쉬운 형태로 표시
  (경과 시간 포함).
- `agent-eval claims release <claim_id> [--claims-path PATH] [--force]` — 클레임 해제.
- `agent-eval claims audit [--claims-path PATH] [--ttl-hours N]` — CI 친화적 감사, 위반 시
  종료 코드 1(`agent-eval gate`와 동일한 CI 관용구).
- `--developer`를 생략하거나 명시적으로 `auto`를 지정하면 SPEC-037의 `resolve_owner()`로
  `git config user.name`을 자동 조회한다.
- 새 판정/파싱 로직을 추가하지 않는다 — 전부 기존 SDK 함수 호출로 구현한다.

## Non-Goals

- 클레임 로그를 위한 새로운 저장 백엔드(SQLite 등)를 도입하지 않는다 — 기존 JSONL 그대로.
- IDE 플러그인(VSCode/OpenCode 확장)은 이 스펙의 범위가 아니다 — CLI만.
- `check_scope_claim()`(세션 시작 전 스코프 겹침 확인)을 위한 서브커맨드는 추가하지 않는다
  — `add`가 클레임을 걸기 전 사람이 `list`로 먼저 확인하는 것으로 충분하고, 자동 사전 확인은
  `TeamConcurrencyConfig`(세션 도중)와 역할이 겹친다.

## Requirements

- **REQ-1**: `agent_evaluator/cli/claims.py`를 신설하고 `build_claims_subparser(sub)`,
  `cmd_claims(args)`를 export한다. `main.py`에 다른 서브커맨드와 동일한 방식으로 등록한다.
- **REQ-2**: `add` 서브커맨드는 `scope`(nargs="+"), `--developer`/`-d`(기본값 `None`),
  `--claims-path`(기본값 `.aoo/claims.jsonl`), `--claim-id`(기본값 `None` → `c-<8자리 hex>`
  자동 생성)를 받는다. `developer`는 `resolve_owner(args.developer or "auto")`로 해석한다 —
  생략과 명시적 `"auto"` 모두 같은 경로를 타야 한다. 해석 결과가 falsy면 에러 메시지 출력 후
  종료 코드 1.
- **REQ-3**: `list` 서브커맨드는 `load_active_claims()`로 활성 클레임만 표시한다. 각 클레임의
  `started_at` 기준 경과 시간을 계산해 함께 표시하되, 파싱 실패 시 크래시하지 않고 대체
  텍스트를 표시한다.
- **REQ-4**: `release` 서브커맨드는 `append_claim(..., status="released")`을 호출한다.
  대상 `claim_id`가 현재 활성 클레임 목록에 없으면 경고를 출력하고 `--force` 없이는 이벤트를
  기록하지 않은 채 종료 코드 1을 반환한다.
- **REQ-5**: `audit` 서브커맨드는 `audit_claims()`를 호출해 위반 목록을 사람이 읽기 쉬운
  형태로 출력하고, 위반이 있으면 종료 코드 1, 없으면 0을 반환한다.
- **REQ-6**: 서브커맨드가 지정되지 않으면(`agent-eval claims`만 실행) 도움말을 출력하고
  종료 코드 1을 반환한다(`agent-eval dataset`과 동일한 패턴).

## Interface

```bash
agent-eval claims add agent_evaluator/gates/configs.py --developer auto
# ✅ 클레임 개설: claim_id=c-a1b2c3d4  developer=Sungwoo Kim

agent-eval claims list
#   c-a1b2c3d4  Sungwoo Kim  [agent_evaluator/gates/configs.py]  (0.1h 경과)

agent-eval claims release c-a1b2c3d4
# ✅ 클레임 해제: claim_id=c-a1b2c3d4

agent-eval claims audit --ttl-hours 8
# ✅ 클레임 로그 위반 없음 (.aoo/claims.jsonl)
```

## Acceptance

- `add`: 명시적 developer/명시적 claim_id/자동 생성 claim_id/명시적 `"auto"` 리터럴/생략된
  developer/git 조회 실패 시 에러/부모 디렉터리 자동 생성/다중 스코프 각각을 커버.
- `list`: 빈 로그/활성 클레임 표시/해제된 클레임 제외/파싱 불가능한 `started_at` 내성.
- `release`: 활성 클레임 정상 해제/미존재 ID(`--force` 없이 거부)/미존재 ID(`--force`로 강제
  기록).
- `audit`: 위반 없음/TTL 초과/스코프 겹침 각각 올바른 종료 코드와 메시지.
- dispatcher: 정상 라우팅/서브커맨드 누락/미상 서브커맨드 각각 올바른 종료 코드.
- CLI 스모크 테스트(실제 `agent-eval` 실행)로 4개 서브커맨드 전체 흐름 확인.

## Compatibility

- 100% additive — 새 서브커맨드 하나만 추가, 기존 `agent-eval` 서브커맨드·SDK 함수는 무수정.

## Rollout

1. `agent_evaluator/cli/claims.py` 4개 핸들러 구현(REQ-2~5).
2. `main.py` 배선(REQ-1, REQ-6).
3. Ch27/28/29 문서에 CLI 사용법을 기존 raw 함수 호출 예제 옆에 TIP으로 추가(SPEC-037과 함께
   처리).

## Risks

- **CLI가 raw 함수 호출과 별도의 진입점이라는 점을 팀에 문서화하지 않으면 두 가지 방식이
  혼용되어 혼란을 줄 수 있다.** Ch28 §28.5에 "스크립트에 녹여 넣을 때는 raw 함수, 터미널
  즉석 사용은 CLI"라는 사용 기준을 명시해 완화했다.
- **`--force` 없는 `release`가 실수로 이미 해제된 클레임을 다시 해제하려 할 때도 경고를
  띄운다** — 활성 목록에 없다는 사실만으로는 "이미 해제됨"과 "애초에 존재한 적 없음"을
  구분하지 못한다. 사용자에게는 두 경우 모두 같은 경고와 `--force` 안내가 출력되므로 실질적
  피해는 없다(멱등한 재해제를 허용하고 싶으면 `--force`를 쓰면 된다).
