# SPEC-035: `BranchGuardConfig` — 보호 브랜치 git 변경 차단 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~5 전체 완료(2026-07-08)** · **의존성:** 없음(`LiveGuardrail`의 기존 "생성자 시점 1회 조회" 패턴 재사용 — SPEC-032/SPEC-027과 동일 원칙)

> **구현 노트 (2026-07-08)**: 설계 그대로 편차 없이 구현했다. 신규 모듈
> `gates/branch_guard.py` — `BranchGuardConfig`(REQ-1), `get_current_branch()`
> (REQ-2, `monitor.py`의 `agent_version="auto"`와 동일한 `subprocess.run(...,
> timeout=2)` + 예외 시 `None` 폴백 패턴), `is_branch_protected()`(REQ-3, `branch=None`
> 이면 fail-open으로 차단하지 않음), `matches_git_mutation()`(REQ-5 헬퍼). `LiveGuardrail`에
> `branch_guard` 파라미터 추가, 생성자 시점 `get_current_branch()` 1회 캐싱(REQ-4).
> `check_before_tool_call()`의 `team_concurrency` 검사 직후에 새 체크 추가(REQ-5).
>
> 직접 실행으로 확인: 이 저장소(현재 브랜치가 `main`/`master`가 아님)에서
> `require_branch_prefix` 없이는 통과, `require_branch_prefix="feature/"`를 주면
> 현재 브랜치가 그 접두어와 불일치해 차단됨을 확인. `monkeypatch`로 브랜치를
> `"main"`으로 고정한 통합 테스트에서 `git commit`/`git push` 차단, 비-git-변경
> 명령(`pytest`) 통과, `scoped_tool_names` 밖 도구 미차단, `fail_on_violation=False`
> 시 미차단을 각각 확인. 비-git 디렉토리(`/tmp`)에서 `get_current_branch()`가
> 예외 없이 `None`을 반환하고, `is_branch_protected(None, ...)`이 `False`(차단
> 안 함)임을 직접 실행해 확인 — fail-open 설계가 실제로 동작함을 검증.
>
> `record_blocked_attempt()`는 예상대로 코드 변경 없이 이 새 차단 유형을 그대로
> 받아들였다(범용 `LiveVerdict(block=True, gate=...)` 인터페이스 재사용 확인).
>
> 테스트 19건 추가(`tests/test_spec035_branch_guard.py`). 전체 스위트 **3,538
> passed, 회귀 0건**(기존 3,519 + 신규 19).
>
> 품질 래칫: `branch_guard.py`(신규 파일)는 이 저장소의 py38-호환 컨벤션(`Tuple`/
> `Optional` 타입힌트)을 그대로 따름. `live_guardrail.py` E501 순증가 0건(초안에서
> 새 E501 1건 발생 → 줄바꿈으로 해결), UP045 +2(기존 지배적 컨벤션과 일치). mypy
> 신규 findings 없음(기존에 있던 무관한 findings 1건은 라인 번호만 이동, 재확인함).

## Context

- 외부 검토(2026-07-08, ADE 팀 협업 리스크 분석)가 지적한 "무단/깜깜이 코드 수정" + "AI 전용 격리 브랜치 강제"는, Ch28 §28.2 그라운드 룰 4번("세션은 짧고, 브랜치는 전용이다")과 §28.2 체크리스트("전용 브랜치 — 메인 브랜치·다른 사람과 공유 중인 브랜치에서 직접 세션을 돌리지 않는다")로 이미 **문서화**돼 있다.
- 하지만 직접 grep으로 확인한 결과, 이 규칙을 실제로 검사하는 코드는 어디에도 없다 — `LiveGuardrail`의 어떤 체크도 현재 git 브랜치를 조회하지 않고, `git commit`/`git push` 자체를 막는 것도 사람이 `ToolParameterSafetyConfig.dangerous_patterns`에 직접 정규식을 넣어야만 가능하다(기본 제공 아님). 즉 "전용 브랜치에서만 작업한다"는 지금까지 **사람이 기억해야 하는 습관**이지, 기계적으로 강제되는 가드레일이 아니다.
- 같은 검토에서 제시된 나머지 3개 문제(문맥 불일치, 스타일 위반, Git 동시 수정 충돌)는 각각 배치 LLMJudge 평가, ESLint/Prettier 같은 표준 린터(Agent-Evaluator가 재구현할 영역이 아님), `TeamConcurrencyConfig`(SPEC-032)+`audit_claims()`(SPEC-034)로 이미 커버되고 있음을 확인했다 — 이 스펙은 실제로 비어 있는 지점(브랜치 격리 강제)만 다룬다.

## Goals

- AI 세션이 보호 브랜치(기본값 `main`/`master`)에서 `git commit`/`git push` 같은 git 변경 명령을 시도하면 **실행 전에** 자동으로 차단한다.
- `TeamConcurrencyConfig`(SPEC-032)와 동일한 원칙 — 현재 브랜치는 `LiveGuardrail` 생성 시점에 1회만 조회한다(매 호출 재조회 없음, `check_before_tool_call()`의 순수 조회 계약 유지).
- 옵트인 — 설정하지 않으면(기본값 `None`) 기존 동작과 100% 동일.

## Non-Goals

- **세션 도중 브랜치 전환 자동 재조회** — `TeamConcurrencyConfig.refresh_team_claims()` 같은 수동 재조회 메서드를 이번 스펙에서는 제공하지 않는다. 브랜치 전환은 클레임 갱신보다 훨씬 드문 이벤트라고 보고 범위를 좁힌다 — 필요성이 확인되면 후속 스펙에서 추가.
- **`git merge`/`git rebase`/`git reset` 등 다른 git 변경 명령 탐지** — 기본 패턴은 `commit`/`push`만 다룬다. 다른 명령이 필요하면 `git_mutation_patterns`를 사용자가 직접 확장하면 된다(설계상 이미 가능, 새 코드 불필요).
- **브랜치 이름 규칙 강제**(예: `feature/`로 시작해야 함) 자체를 별도 기능으로 만들지 않는다 — `require_branch_prefix` 옵션으로 같은 체크 안에 통합한다(REQ-3).
- **비-git 환경에서의 에러** — git이 없거나 저장소가 아니면 브랜치를 `None`으로 간주하고 **차단하지 않는다**(fail-open). 이 SDK를 git 저장소 밖에서 쓰는 기존 사용자에게 새로운 실패를 강제하지 않기 위함(Risks에 명시).

## Requirements

- **REQ-1**: `gates/branch_guard.py`(신규 모듈)에 `BranchGuardConfig` dataclass를 추가한다 — `protected_branches: Tuple[str, ...] = ("main", "master")`, `git_mutation_patterns: Tuple[str, ...] = (r"git\s+commit", r"git\s+push")`, `require_branch_prefix: Optional[str] = None`, `scoped_tool_names: Tuple[str, ...] = ("bash",)`, `fail_on_violation: bool = True`.
- **REQ-2**: 같은 모듈에 `get_current_branch() -> Optional[str]`를 추가한다 — `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=2)`를 실행하고, `monitor.py`의 `agent_version="auto"`가 이미 쓰는 것과 동일한 패턴으로 어떤 실패(git 미설치, 비-git 디렉토리, 타임아웃 등)든 예외 전파 없이 `None`을 반환한다.
- **REQ-3**: 같은 모듈에 `is_branch_protected(branch: Optional[str], config: BranchGuardConfig) -> bool`를 추가한다 — `branch`가 `None`이면 `False`(차단하지 않음, fail-open). `branch`가 `protected_branches`에 있으면 `True`. `config.require_branch_prefix`가 설정됐고 `branch`가 그 접두어로 시작하지 않으면 `True`. 그 외 `False`.
- **REQ-4**: `LiveGuardrail.__init__`에 `branch_guard: Optional[BranchGuardConfig] = None` 파라미터를 추가한다. 설정되면 생성자 시점에 `self._current_branch = get_current_branch()`를 1회만 호출해 캐싱한다(`TeamConcurrencyConfig`가 클레임을 1회 로드하는 것과 동일 원칙).
- **REQ-5**: `check_before_tool_call()`에 `team_concurrency` 검사 직후, `tool_parameter_safety` 검사 이전에 새 검사를 추가한다 — `tool_name`이 `scoped_tool_names`에 있고, 인자를 JSON 직렬화한 문자열이 `git_mutation_patterns` 중 하나와 매치하고, `is_branch_protected(self._current_branch, config)`가 `True`이고, `config.fail_on_violation`이 `True`이면 `LiveVerdict(block=True, gate="B", reason=...)`를 반환한다. `record_blocked_attempt()`는 기존 그대로 재사용한다(새 코드 불필요 — 어떤 `LiveVerdict(block=True, gate=...)`든 이미 받아들이는 범용 인터페이스).

## Interface

```python
from agent_evaluator.gates.live_guardrail import LiveGuardrail
from agent_evaluator.gates.branch_guard import BranchGuardConfig

guardrail = LiveGuardrail(
    branch_guard=BranchGuardConfig(
        protected_branches=("main", "master"),
        require_branch_prefix="feature/",  # 선택 — "feature/"로 시작하지 않는 모든 브랜치도 보호 대상
    ),
)

# main 브랜치에서 실행 중이라면:
verdict = guardrail.check_before_tool_call("t1", "bash", {"command": "git commit -m 'wip'"})
# verdict.block == True, verdict.reason == "branch_guard: git mutation blocked on branch 'main' (task_id=t1)"

# 같은 브랜치에서 git과 무관한 명령은 그대로 통과:
verdict2 = guardrail.check_before_tool_call("t1", "bash", {"command": "pytest tests/"})
# verdict2.block == False
```

## Acceptance

- **REQ-1/2/3**: `get_current_branch()`가 실제 git 저장소에서 현재 브랜치 이름을 정확히 반환하는지(이 저장소 자체에서 직접 실행해 확인). 비-git 디렉토리(임시 디렉토리)에서 호출하면 예외 없이 `None`을 반환하는지. `is_branch_protected()`가 `protected_branches` 매치, `require_branch_prefix` 불일치, `branch=None`(차단 안 함) 세 경우를 정확히 판정하는지.
- **REQ-4/5**: `branch_guard` 미설정(기본값 `None`) 시 기존 동작과 완전히 동일한지(회귀 없음). 보호 브랜치에서 `git commit`/`git push` 포함 명령이 차단되는지. 보호 브랜치가 아닌(또는 `require_branch_prefix`와 일치하는) 브랜치에서는 같은 명령이 통과하는지. `scoped_tool_names`에 없는 도구(예: `read`)의 인자에 우연히 "git commit" 문자열이 들어있어도 차단되지 않는지(스코프 확인). `fail_on_violation=False`면 매치돼도 차단하지 않는지. `record_blocked_attempt()`가 이 새 차단 유형에도 코드 변경 없이 동작하는지.
- **회귀 없음**: 기존 `LiveGuardrail`/SPEC-019~034 테스트 스위트 전체가 무수정으로 통과하는지.

## Compatibility

- 100% additive — 신규 모듈, 신규 옵트인 파라미터. 기존 `LiveGuardrail` 생성자·`check_before_tool_call()` 시그니처의 다른 부분을 변경하지 않는다.

## Rollout

1. REQ-1~3(`branch_guard.py` 모듈 — `BranchGuardConfig`/`get_current_branch()`/`is_branch_protected()`) — 독립적으로 단위 테스트 가능.
2. REQ-4(`LiveGuardrail.__init__` 연동, 1회 캐싱) — REQ-1~3에 의존.
3. REQ-5(`check_before_tool_call()` 체크 추가) — REQ-4에 의존.

## Risks

- **Fail-open이 유일하게 안전한 기본값이다.** 브랜치를 알 수 없을 때 차단하는 쪽(fail-closed)을 택하면, git이 없는 CI 컨테이너·비-git 디렉토리에서 이 SDK를 쓰는 기존 사용자의 모든 `bash` 호출이 이유 없이 막힐 위험이 있다 — 이 스펙은 명시적으로 fail-open을 채택한다.
- **정규식 기반 탐지의 한계** — `ToolParameterSafetyConfig.dangerous_patterns`와 동일한 성격의 한계를 그대로 가진다(§27.5/27.6에 이미 문서화된 블랙리스트 방어의 한계). 셸 별칭(`alias gc='git commit'`)이나 SPEC-033의 인코딩 우회 형태로는 이 체크도 우회될 수 있다 — `decode_encodings`가 필요하면 `ToolParameterSafetyConfig` 쪽에 이미 있는 것을 별도로 적용해야 한다(이번 스펙은 그 기능을 재사용하지 않는다 — Non-Goals 범위 밖).
- **브랜치 전환 미반영** — 세션 도중 사람이 수동으로 브랜치를 바꿔도 `LiveGuardrail`은 생성 시점 브랜치를 계속 쓴다(Non-Goals). 장시간 세션에서 이 갭이 문제가 되면 `LiveGuardrail`을 재생성해야 한다.
