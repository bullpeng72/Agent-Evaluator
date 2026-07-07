# SPEC-032: `TeamConcurrencyConfig` — 축소 범위 다중 세션 스코프 충돌 감지 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙) · **상태:** **Implemented — REQ-1~6 전체 완료(2026-07-07)** · **의존성:** SPEC-019(완료, `LiveGuardrail`/`check_before_tool_call()`) · SPEC-024(완료, `.aoo/claims.jsonl` 그라운드 룰과 `Evaluator_Examples/ch28_local_ade_loop.py`의 `check_scope_claim()`/`append_claim()` 예제 코드 — 이번 스펙이 SDK로 승격하는 대상) · SPEC-030(완료, `record_blocked_attempt()` — 이 스펙이 만드는 새 차단 유형도 별도 코드 변경 없이 그대로 감사 이력에 남는다)

> **구현 노트 (2026-07-07)**: 설계안 그대로 6개 REQ 전부 구현, 편차 없음.
> REQ-1: 신규 모듈 `agent_evaluator/gates/team_concurrency.py`에 `load_active_claims()`
> (latest-per-`claim_id`, active만 필터링 — 기존 예제의 `latest_by_id` 로직을 그대로
> 추출), `check_scope_claim()`(공개 API 유지, 내부적으로 `load_active_claims()` 재사용),
> `append_claim()`을 승격. 로직 재해석 없음 — ch28 예제의 4가지 시나리오(클레임 없음/
> 겹침 감지/비겹침 통과/해제 후 재확인)를 테스트로 재확인. REQ-2: `TeamConcurrencyConfig`
> 데이터클래스(`claims_path`/`shared_files_path`/`scoped_tool_names=("read","edit","write")`/
> `path_param_candidates=("file","filePath","path")`/`fail_on_conflict=True`). REQ-3:
> `LiveGuardrail.__init__`이 `team_concurrency` 파라미터 주어지면 생성자 시점에
> `load_active_claims()`/`_load_shared_files()`를 **정확히 1회**만 호출해
> `self._team_claims`/`self._shared_files`에 캐싱 — 이후 재조회 없음(직접 테스트로
> "생성자 이후 추가된 클레임은 세션 중 반영 안 됨"을 확인). REQ-4:
> `check_before_tool_call()`의 기존 `scope` 검사 직후에 새 검사 추가 —
> `tool_name in scoped_tool_names`이고 `extract_path_param()`으로 경로를 찾으면
> 캐싱된 클레임/공유파일과 prefix 겹침 검사, 못 찾으면 조용히 건너뜀(안전한 폴백).
> `bash`는 `scoped_tool_names` 기본값에 없어 같은 경로를 인자로 줘도 이 검사로는
> 차단되지 않음을 테스트로 확인(Non-Goals와 정확히 일치). REQ-5: `record_blocked_attempt()`
> 가 새 차단 유형(`gate="B"`, `team_concurrency: ...` reason)에도 코드 변경 없이
> 동작함을 통합 테스트로 재확인 — 실제로 신규 코드 없음. REQ-6: `refresh_team_claims()`
> 메서드 추가, 자동 호출 없음(호출 전/후 동작 차이를 테스트로 직접 확인),
> `team_concurrency=None`일 때 아무 일도 하지 않음(no-op) 확인.
>
> 테스트 22건 추가(`test_spec032_team_concurrency.py` 신규 파일 — REQ-1 프로모션
> 검증 5건, `extract_path_param()` 단위 테스트 5건, `LiveGuardrail` 통합 9건,
> `record_blocked_attempt()` 통합 1건, `refresh_team_claims()` 2건). 전체 스위트
> **3,494 passed, 1 skipped, 회귀 0건**(기존 3,472 + 신규 22).
>
> 품질 래칫: `live_guardrail.py`의 신규 라인 중 실제로 100자를 넘는 2줄(genuinely
> new E501)을 발견해 로컬 변수 추출(`_tc_cfg = self._team_concurrency`) + 문자열
> 리터럴 줄바꿈으로 직접 수정 — 최종 E501 카운트는 원본과 완전히 동일(8건, 순증가
> 0). UP006/UP045 증가분(각 +7)은 신규 `Optional`/`Dict`/`List`/`Tuple` 타입힌트에서
> 나온 것으로, 이 파일과 신규 `team_concurrency.py` 둘 다 프로젝트의 py38 호환
> 컨벤션(`pyproject.toml`의 `target-version = "py38"`, `UP007`만 명시적으로
> ignore)을 그대로 따른 결과 — 새로운 위반 유형이 아니라 기존 지배적 스타일의
> 추가 인스턴스(SPEC-027 이후 동일 패턴). mypy 신규 findings 없음.

## Context (설계 시점 — 위 구현 노트가 최신 상태)

## Context

- Ch28 §28.2/§28.5의 그라운드 룰은 `.aoo/claims.jsonl`(append-only, `claim_id`/`developer`/`scope`/`branch`/`started_at`/`status`)로 "누가 어떤 스코프를 작업 중인지"를 팀 전체에 공표하지만, 이 확인은 **세션 시작 전 사람이 직접 `check_scope_claim()`을 호출하는 절차**일 뿐, `LiveGuardrail` 자체는 관여하지 않는다(`Evaluator_Examples/ch28_local_ade_loop.py:510-535`에 이미 구현·라이브 검증됨 — `latest_by_id` 최신 상태만 유효 처리, prefix 겹침 판정 `p1 == p2 or p1.startswith(p2) or p2.startswith(p1)`).
- 이 예제 코드는 잘 동작하지만 **SDK가 아니라 예제 파일에만 존재**한다 — 재사용하려면 각 프로젝트가 이 로직을 직접 복사해야 하고, `LiveGuardrail`의 `check_before_tool_call()`과 자동으로 연동되지 않는다(세션 시작 전 한 번 수동 확인 후 잊어버리면 세션 도중의 위반은 전혀 잡히지 않음).
- 1차 검토에서 "완전 자동화(매 도구 호출마다 `.aoo/claims.jsonl` 재조회 + `bash` 포함 모든 도구의 파일 경로 자동 추출)"를 제안했으나 두 가지 설계 문제가 확인됐다: (1) `bash` 같은 자유 형식 셸 명령에서 "어떤 파일 경로를 건드리는지" 안정적으로 파싱할 방법이 없다(`rm -rf {path}`, `sed -i ... {path}` 등 명령 구조가 도구마다 다름), (2) `check_before_tool_call()`마다 클레임 파일을 재조회하면 `LiveGuardrail`의 "세션마다 별도 인스턴스, 락 없음, 순수 인메모리 판정" 계약이 외부 공유 파일 I/O에 의존하게 된다(SPEC-019 Context). 이번 스펙은 이 두 문제를 **범위를 좁혀** 우회한다 — `bash`는 대상에서 제외하고, 클레임은 세션 시작 시 1회만 로드한다.
- `record_blocked_attempt()`(SPEC-030)는 `LiveVerdict(block=True, gate, reason)`를 받는 범용 API라, 이번 스펙이 만드는 새 차단 유형도 **코드 변경 없이 그대로** 감사 이력(`blocked_violations`)에 남는다 — 이미 검증된 조합이다.

## Goals

- `.aoo/claims.jsonl` 기반 팀 스코프 겹침 감지를 `Evaluator_Examples/ch28_local_ade_loop.py`의 예제 전용 코드에서 **재사용 가능한 SDK 함수**로 승격한다(로직은 그대로, 위치만 이동).
- `LiveGuardrail`이 **세션 시작 시 1회** 클레임을 로드해, `read`/`edit`/`write`처럼 구조화된 파일 경로 파라미터를 갖는 도구 호출에 한해 다른 개발자의 활성 클레임과 겹치면 자동으로 차단하게 한다.
- `.aoo/shared_files.txt`(항상 조율이 필요한 파일 목록)도 같은 매칭 로직으로 지원한다 — 클레임 여부와 무관하게 걸리면 차단.
- `check_before_tool_call()`의 "순수 조회, 매 호출 시 외부 I/O 없음" 계약을 지킨다 — 클레임/공유파일 목록은 `__init__` 시점 1회만 읽는다.

## Non-Goals

- `bash` 등 자유 형식 도구 호출에서 파일 경로를 파싱하는 것 — 1차 검토에서 확인된 미해결 문제. `scoped_tool_names`(기본값 `("read", "edit", "write")`)로 명시적으로 범위를 좁히고, 다른 도구는 이번 체크에서 완전히 제외한다.
- 세션 진행 중 실시간으로 클레임 변경을 반영하는 것 — 세션 시작 시 1회 로드한 스냅숏만 사용한다. 세션 도중 다른 개발자가 새로 클레임한 스코프는 이 세션이 끝날 때까지 반영되지 않는다(Risks 참조 — Ch28 §28.2 원칙 4 "세션은 짧고, 브랜치는 전용이다"로 이 위험을 완화하는 것을 전제로 한다).
- 파일 경로 추출 실패 시 대체 휴리스틱(예: 명령 문자열 자체를 검색) — 후보 파라미터 키(`file`/`filePath`/`path`)에서 못 찾으면 조용히 건너뛴다(신호 없음 = 차단 안 함, SPEC-031과 동일한 원칙).
- 클레임 로그 자체의 무결성 검증(동시 쓰기 충돌, 파일 락 등) — `.aoo/claims.jsonl`은 이미 Ch29 §29.2가 다루는 팀 인프라 영역이고, 이번 스펙은 그 파일을 읽기만 한다.

## Requirements

- **REQ-1**: `Evaluator_Examples/ch28_local_ade_loop.py`의 `check_scope_claim()`/`append_claim()` 로직을 신규 모듈 `agent_evaluator/gates/team_concurrency.py`로 승격한다 — `load_active_claims(claims_path) -> List[Dict[str, Any]]`(latest-per-`claim_id`, `status == "active"`만 필터링), `check_scope_claim(proposed_scope, claims_path) -> List[Dict[str, Any]]`(세션 시작 전 수동 확인용, 기존 예제와 동일한 공개 함수로 유지), `append_claim(claims_path, **fields)`. 로직은 예제 코드와 완전히 동일 — 재해석 없음.
- **REQ-2**: `TeamConcurrencyConfig` 데이터클래스를 같은 모듈에 추가한다 — `claims_path: str = ".aoo/claims.jsonl"`, `shared_files_path: Optional[str] = None`, `scoped_tool_names: Tuple[str, ...] = ("read", "edit", "write")`, `path_param_candidates: Tuple[str, ...] = ("file", "filePath", "path")`(파라미터 dict에서 파일 경로를 찾을 후보 키, 순서대로 시도 — 못 찾으면 검사를 건너뜀), `fail_on_conflict: bool = True`.
- **REQ-3**: `LiveGuardrail.__init__`에 `team_concurrency: Optional[TeamConcurrencyConfig] = None`을 추가한다. 주어지면 생성자 시점에 `load_active_claims(team_concurrency.claims_path)`(1회)로 `self._team_claims`를, `shared_files_path`가 있으면 그 파일의 비어있지 않은 줄들을 `self._shared_files`(1회)로 캐싱한다. 이후 재조회하지 않는다(REQ-6의 명시적 새로고침 메서드 호출 시에만 예외).
- **REQ-4**: `check_before_tool_call()`에 새 검사를 추가한다(기존 `scope` 검사 직후) — `team_concurrency`가 설정되고 `tool_name in scoped_tool_names`이면, `parameters`에서 `path_param_candidates` 순서로 첫 문자열 값을 찾는다. 못 찾으면 검사를 건너뛴다. 찾으면: (a) `self._team_claims`의 각 클레임 `scope` 리스트와 prefix 겹침(`path == s or path.startswith(s) or s.startswith(path)`, REQ-1의 기존 로직 재사용)을 확인해 겹치면 `fail_on_conflict=True`일 때 `block=True, gate="B", reason="team_concurrency: scope claimed by {developer} (claim_id={claim_id})"`를 반환한다. (b) 겹치지 않으면 `self._shared_files`에 같은 방식으로 매칭되는 항목이 있는지 확인해, 있으면 `block=True, gate="B", reason="team_concurrency: shared file requires coordination: {path}"`를 반환한다.
- **REQ-5**: `record_blocked_attempt()`(SPEC-030)가 이 새 차단 유형에도 코드 변경 없이 동작하는지 통합 테스트로 확인한다(신규 로직 아님 — 기존 API 재사용 검증).
- **REQ-6**: `LiveGuardrail.refresh_team_claims()` 메서드를 추가한다 — 호출하면 `self._team_claims`/`self._shared_files`를 `claims_path`/`shared_files_path`에서 다시 읽어 갱신한다. 자동 호출 없음(순수 조회 계약 유지) — 장시간 세션에서 호출자가 필요하다고 판단할 때만 명시적으로 사용.

## Interface

```python
from agent_evaluator.gates.team_concurrency import TeamConcurrencyConfig
from agent_evaluator.gates.live_guardrail import LiveGuardrail

guardrail = LiveGuardrail(
    scope=ScopeConfig(allowed_tools=["read", "edit"], fail_on_violation=True),
    team_concurrency=TeamConcurrencyConfig(
        claims_path=".aoo/claims.jsonl",
        shared_files_path=".aoo/shared_files.txt",
        fail_on_conflict=True,
    ),
)

# 다른 개발자가 이미 이 경로를 클레임한 상태라면 차단된다
verdict = guardrail.check_before_tool_call(
    "t1", "edit", {"file": "agent_evaluator/gates/gate_d_performance/aggregate.py"},
)
# verdict.block == True (겹치는 활성 클레임이 있을 때)
# verdict.reason == "team_concurrency: scope claimed by sungwoo (claim_id=c-demo-01)"

# bash는 이 검사 대상이 아니다 — scoped_tool_names 기본값에 없음
guardrail.check_before_tool_call("t1", "bash", {"command": "rm -rf agent_evaluator/gates/gate_d_performance/"})
# team_concurrency 검사는 건너뛰고 기존 scope/tool_parameter_safety 등만 평가된다

# 장시간 세션에서 클레임 상태를 다시 확인하고 싶을 때만 명시적으로
guardrail.refresh_team_claims()
```

```python
# REQ-1 — 기존 check_scope_claim()/append_claim() 사용법은 그대로(승격 위치만 이동)
from agent_evaluator.gates.team_concurrency import check_scope_claim, append_claim

conflicts = check_scope_claim(["agent_evaluator/gates/gate_d_performance/"], ".aoo/claims.jsonl")
```

## Acceptance

- **REQ-1**: 승격된 `check_scope_claim()`/`append_claim()`이 `Evaluator_Examples/ch28_local_ade_loop.py`의 기존 데모 시나리오(개발자 B 겹침 감지/개발자 C 통과/해제 후 재확인)와 동일한 결과를 내는지.
- **REQ-3/4**: 활성 클레임과 겹치는 경로로 `edit`을 호출하면 차단되는지. 겹치지 않으면 통과하는지. `scoped_tool_names`에 없는 도구(`bash` 등)는 겹치는 경로를 인자에 담아도 이 검사로는 차단되지 않는지(다른 검사에는 여전히 걸릴 수 있음). `path_param_candidates` 중 어느 키도 없는 `parameters`를 주면 예외 없이 검사를 건너뛰는지. `team_concurrency=None`(기본값)이면 기존 동작과 완전히 동일한지(회귀 없음).
- **REQ-4(shared_files)**: `.aoo/shared_files.txt`에 있는 경로로 `edit`을 호출하면 클레임 여부와 무관하게 차단되는지.
- **REQ-5**: `check_before_tool_call()`이 이 새 차단을 반환한 뒤 `record_blocked_attempt()`로 기록하면 `blocked_violations`에 정상적으로 남는지(코드 변경 없이 재사용 확인).
- **REQ-6**: `refresh_team_claims()` 호출 전에는 세션 시작 후 새로 추가된 클레임이 반영되지 않다가, 호출 후에는 반영되는지.
- **회귀 없음**: `team_concurrency`를 쓰지 않는 기존 `LiveGuardrail` 사용 코드가 이전과 완전히 동일하게 동작하는지 — 기존 SPEC-019/024/028/030/031 테스트 스위트 전체가 무수정으로 통과하는지 확인.

## Compatibility

- 100% additive — `team_concurrency`는 새 옵트인 생성자 파라미터. 기본값 `None`에서는 이번 스펙의 모든 로직이 완전히 비활성화된다.
- `agent_evaluator/gates/team_concurrency.py`는 신규 모듈이라 기존 코드와 충돌하지 않는다. `Evaluator_Examples/ch28_local_ade_loop.py`의 기존 로컬 함수 정의는 이번 스펙에서 건드리지 않는다(원한다면 이후 별도 문서화 작업으로 SDK import로 교체 가능 — 이번 스펙 범위 밖).
- 새 차단 유형은 기존 `gate="B"` 체계를 그대로 쓰므로 Gate B 점수 집계 로직 변경이 필요 없다.

## Rollout

1. REQ-1(모듈 승격) — 가장 작고 독립적, 기존 예제 로직의 순수 이동.
2. REQ-2(`TeamConcurrencyConfig`) — REQ-1에 의존.
3. REQ-3(`LiveGuardrail.__init__` 연동, 1회 로드) — REQ-2에 의존.
4. REQ-4(`check_before_tool_call()` 검사 로직) — REQ-3에 의존, 이번 스펙의 핵심 가치.
5. REQ-5(`record_blocked_attempt()` 통합 재확인) — REQ-4에 의존, 신규 코드 없음.
6. REQ-6(`refresh_team_claims()`) — REQ-3에 의존, 독립적으로 병행 가능.

## Risks

- **세션 시작 후 생기는 새 클레임을 못 봄**: Non-Goals에 명시한 대로 의도적 트레이드오프다 — Ch28 §28.2 원칙 4(짧은 세션)로 위험 구간을 최소화하고, 필요하면 REQ-6의 `refresh_team_claims()`를 수동으로 호출하는 것으로 완화한다.
- **`path_param_candidates` 미검증**: `file`/`filePath`/`path` 세 후보 키는 이 SDK 예제(`file`)와 일반적인 관례에 근거한 추정이다 — 실제 OpenCode 내장 도구가 다른 키를 쓴다면(SPEC-031의 `metadata` 필드명 불확실성과 동일한 종류의 리스크) 신호를 못 찾아 검사를 건너뛸 뿐, 오탐/크래시는 없다(안전한 폴백).
- **`scoped_tool_names` 밖 도구로 우회 가능**: `bash`로 같은 파일을 건드리면 이번 체크로는 잡히지 않는다 — 팀에는 "구조화된 파일 도구(`read`/`edit`/`write`)만 이 자동 검사의 보호를 받는다"는 점을 명확히 안내해야 한다(완전한 해결책이 아니라 부분적 완화책임을 문서에 명시).
- **다중 세션 동시 실행 시 클레임 파일 자체의 쓰기 경합**: 이번 스펙은 읽기 전용이라 직접적인 리스크는 없지만, `append_claim()`을 여러 프로세스가 동시에 호출하면 OS 수준의 append 원자성에 의존한다 — 기존 Ch28/29 문서가 이미 인지하고 있는 한계이며 이번 스펙이 새로 만든 문제는 아니다.
