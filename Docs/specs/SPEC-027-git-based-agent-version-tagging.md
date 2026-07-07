# SPEC-027: Git 커밋 기반 `agent_version` 자동 태깅 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 — 로컬 개발 루프와 SPEC-025 버전 비교 파이프라인을 잇는 첫 조각) · **상태:** **Implemented — REQ-1~3 전체 완료(2026-07-06)** · **의존성:** SPEC-007(완료, `self._git_commit` 1회 캐싱 로직 재사용) · SPEC-025(완료, `agent_version`을 소비하는 `ResultFile.agent_version`/`compare_results(group_by=...)`/`gate --baseline-version`/대시보드 UI가 이미 "임의의 문자열"이라는 전제로 완성돼 있음 — 이번 스펙은 그 문자열을 어떻게 만드는가만 다룬다)

> **구현 노트 (REQ-3, 2026-07-06)**: `PerformanceMonitor`에 읽기 전용
> `@property def agent_version(self) -> Optional[str]`를 추가했다(`monitor.py:723-731`,
> `golden_datasets`/`thresholds` 등 기존 프로퍼티 바로 앞) — `self._agent_version`을
> 그대로 반환할 뿐이며, `model_name`과 동일하게 setter는 두지 않았다(설계안 그대로,
> 편차 없음). 테스트 5건 추가(리터럴 문자열 반환, 기본값 `None`, `"auto"` clean/dirty
> 해석값 반영 각 1건, setter 없음을 `pytest.raises(AttributeError)`로 확인). 전체
> 스위트 **3,418 passed, 1 skipped, 회귀 0건**(기존 3,413 + 신규 5). 품질 래칫
> `monitor.py` 순변화 `UP045` +1(신규 프로퍼티의 `Optional[str]` 반환 타입 — 이
> 파일에 이미 81건 존재하는 지배적 컨벤션과 정확히 일치, 나머지 규칙은 전부 0)
> — REQ-1/2와 동일한 검증 방식(HEAD 대비 diff)으로 확인. mypy 신규 라인 에러 없음.
>
> **SPEC-027 전체 완료.** REQ-1(커밋 SHA 자동 태깅)→REQ-2(dirty diff 해시 접미사)→
> REQ-3(읽기 전용 프로퍼티)까지 3개 요구사항 모두 실제 테스트 통과와 품질 래칫
> 순증가 사실상 0(REQ-3의 파일 기존 컨벤션과 일치하는 UP045 +1 제외)을 확인하며
> 구현했다. SPEC-028 REQ-5(`live_guardrail_report.py`의 `agent_version="auto"` 연결)가
> 이 산출물에 의존한다.

> **구현 노트 (REQ-2, 2026-07-06)**: REQ-1의 `if self._agent_version == "auto":` 분기
> 안에 dirty-diff 해시 로직을 추가했다(`monitor.py:504-524`) — `self._git_commit`이
> 있으면 `git diff HEAD`를 1회 호출해(2초 타임아웃, 독립된 try/except) 출력이
> 비어 있으면 REQ-1의 커밋-only 태그(`commit[:8]`)를 그대로 쓰고, 출력이 있으면
> 그 텍스트를 `hashlib.sha256`으로 해시해 앞 6자를 `f"{commit[:8]}-dirty-{hash}"`
> 형태로 접미사를 붙인다. `git diff` 호출이 실패해도(타임아웃 등) 예외 전파 없이
> 커밋-only 태그로 폴백한다. 설계안 그대로 구현, 편차 없음. diff 원문 텍스트는
> 해시 계산에만 쓰이고 어디에도 저장되지 않는다(지역 변수 `_diff_text`가 함수
> 반환 없이 스코프를 벗어나며 폐기됨).
>
> `tests/test_spec027_git_agent_version_tagging.py`에 REQ-2 전용 테스트 4건을
> 추가(핵심 케이스: 같은 커밋+다른 미커밋 변경 → 다른 태그, 같은 커밋+동일 변경 →
> 재현되는 동일 태그, 클린 상태 → 접미사 없음, `git diff` 실패 → 커밋-only 폴백) —
> 기존 REQ-1 테스트 2건은 `git diff HEAD`도 같은 patch로 모킹되던 것을 command별로
> 분기하는 `_fake_run()` 헬퍼로 교체해 클린 상태를 명시적으로 고정했다(그렇지 않으면
> `git rev-parse`용 mock 응답이 `git diff` 호출에도 그대로 반환돼 의도와 다르게
> dirty로 판정됨 — 테스트 작성 중 직접 발견하고 수정).
>
> 전체 스위트 **3,413 passed, 1 skipped, 회귀 0건**(기존 3,409 + 신규 4). 품질 래칫
> 순변화 **0**(`monitor.py` ruff before/after 카운트 완전 동일, mypy도 신규 라인에
> 에러 없음 직접 확인 — REQ-1과 동일한 검증 방식).

> **구현 노트 (REQ-1, 2026-07-06)**: `PerformanceMonitor.__init__`의 `self._git_commit`
> 계산 블록(`monitor.py:491-502`) 바로 뒤에 `agent_version == "auto"` 분기를
> 추가했다(`:504-508`) — `self._git_commit`이 있으면 앞 8자를, 없으면(비-git 환경 등)
> `None`을 `self._agent_version`에 대입한다. 설계안 그대로 구현, 편차 없음 — 이미
> 계산돼 있던 `self._git_commit`을 재사용할 뿐 새 서브프로세스 호출을 추가하지
> 않았다. `tests/test_spec027_git_agent_version_tagging.py`(8건: 커밋 SHA 정상 해석 +
> lineage 반영, git 없음/비정상 종료 코드/타임아웃 3가지 실패 시나리오 각각 `None`
> 폴백, 리터럴 문자열·`None`·빈 문자열 3가지 회귀 없음 케이스) 추가. 전체 스위트
> **3,409 passed, 1 skipped, 회귀 0건**(기존 3,401 + 신규 8). 품질 래칫 순변화
> **0**(ruff `monitor.py` before/after 카운트 완전 동일 — `E501` 189/`UP006` 129/
> `UP045` 81/`UP037` 26/`I001` 3, mypy도 신규 라인에 에러 없음 직접 확인).

## Context

- `PerformanceMonitor.__init__`은 `agent_version: Optional[str] = None`(`agent_evaluator/core/trackers/monitor.py:281`)을 받아 `self._agent_version`에 그대로 저장한다(`:485`) — 사용자가 매 실행마다 값을 직접 넘겨야 하며, SDK 어디에도 이 값을 자동으로 채우는 로직이 없다(`grep -n "_agent_version"` 전수 확인, 대입 지점은 `:485` 단 한 곳).
- 바로 옆에서 `self._git_commit`은 `__init__` 시점에 `git rev-parse HEAD`를 서브프로세스로 1회 호출해 캐싱된다(`:491-499`, SPEC-007 REQ-3 — "save_to_file 매 호출마다 서브프로세스를 띄우지 않는다"는 원칙으로 인스턴스 생성 시 1회만 조회). 이 값은 `_build_lineage()`(`:2971`)를 통해 `extra_metrics.lineage.git_commit`에 감사 목적으로만 기록되고, `agent_version` 결정에는 전혀 관여하지 않는다.
- SPEC-025의 Non-Goals가 이미 이 격차를 명시적으로 지목했다: *"`prompt_version`/`agent_version` 값 자체의 자동 생성(git commit SHA, 프롬프트 파일 해시 등)... 로컬 ADE(OpenCode) 세션에서 git 정보를 자동으로 태깅하는 것은 별도 후속 스펙(AOO ADE 연동 트랙) 범위."* — 이번 스펙이 바로 그 후속이다.
- `Evaluator_Examples/ch28_local_ade_loop.py`(SPEC-024)가 보여주듯, AOO ADE(Agent-Evaluator + Ollama + OpenCode) 로컬 반복 개발 루프는 **커밋 없이 코드를 고치고 바로 eval을 재실행하는 패턴이 일반적**이다. `git rev-parse HEAD`만 태그로 쓰면, 커밋 전 여러 iteration이 전부 같은 SHA로 뭉개져 `compare_results(group_by="agent_version")`(SPEC-025 REQ-2)도, `judge_pairwise`(SPEC-025 REQ-4/5)도 서로 다른 iteration을 구분하지 못한다 — 정확히 이번 스펙이 풀어야 할 문제다.
- `ResultFile.agent_version`(`serve/loader.py`, SPEC-025 REQ-1)·`compare_results(group_by=...)`(`serve/routers/data.py`, SPEC-025 REQ-2)·`agent-eval gate --baseline-version`(`cli/gate.py`, SPEC-025 REQ-3)·대시보드 `dashboard2.html.j2`의 Group by 드롭다운은 전부 "`agent_version`은 임의의 문자열"이라는 전제로 이미 완성돼 있다 — 이번 스펙이 그 문자열의 생성 방식만 바꾸면, 아래 파이프라인 전체가 **무수정으로** 자동 태깅 값을 소비한다.
- `PerformanceMonitor`는 현재 `agent_version`/`prompt_version`을 반환하는 공개 read-only 프로퍼티가 없다(`grep -n "@property"` 확인 결과 `golden_datasets`/`thresholds` 등 다른 필드에만 존재) — "auto"가 실제로 무엇으로 해석됐는지 호출자가 확인할 방법이 없다.

## Goals

- `PerformanceMonitor(agent_version="auto")`를 넘기면 현재 git 저장소 상태(커밋 + 미커밋 변경 여부)를 반영하는 태그를 자동 계산해 `self._agent_version`에 저장한다 — 사용자가 커밋 SHA를 손으로 넘기거나 iteration마다 바꿔줄 필요를 없앤다.
- **커밋되지 않은 변경사항이 있는 상태로 반복 실행해도**(AOO ADE 로컬 루프의 가장 흔한 패턴) 변경 내용이 다르면 다른 태그가, 완전히 동일하면 같은 태그가 나오게 한다 — `git commit SHA`만으로는 이 구분이 원천적으로 불가능하다.
- 이미 완성된 SPEC-025의 `group_by`/`pairwise`/`--baseline-version`/대시보드 UI 파이프라인을 **전혀 수정하지 않고**, 오직 "`agent_version`에 넣을 문자열을 어떻게 만드는가"만 바꾼다 — 새 비교 로직·새 API 엔드포인트를 만들지 않는다.

## Non-Goals

- `prompt_version`에 동일한 `"auto"` 메커니즘을 확장하는 것 — 프롬프트는 보통 파일이 아니라 함수 인자/상수로 존재해 git 커밋과 1:1 대응이 애매하다. 필요성이 실사용에서 확인되면 별도 후속 스펙.
- **untracked(아직 `git add` 안 된 새 파일)의 내용을 dirty 해시에 반영하는 것** — `git diff HEAD`는 tracked 파일 변경만 잡는다. 이번 스펙은 이 한계를 해소하지 않고 문서화만 한다(Risks 참고).
- CLI/환경변수 레벨 진입점(예: `AGENT_EVALUATOR_AGENT_VERSION=auto`) — 이번 스펙은 Python 생성자 파라미터(`PerformanceMonitor(agent_version="auto")`) 레벨만 다룬다.
- OpenCode 플러그인(`agent-evaluator.ts`)과의 실제 배선(세션-idle 훅에 "직전 변경이 골든셋을 회귀시켰다" 힌트를 노출하는 것) — 이건 "`agent_version`을 어떻게 만드는가"가 아니라 "그 값으로 뭘 비교해서 어떻게 보여주는가"의 문제라 완전히 별개인 후속 스펙(golden-set-gate/`--baseline-version`을 OpenCode 훅에 연결) 범위다. 이번 스펙은 그 후속의 전제조건(안정적으로 구분되는 `agent_version` 값)만 놓는다.
- 3개 이상 버전의 상대적 순위(Elo/TrueSkill) — SPEC-025의 기존 Non-Goal을 그대로 유지.

## Requirements

- **REQ-1**: `PerformanceMonitor.__init__`의 `self._git_commit` 계산 블록(`monitor.py:491-499`) 직후에 `"auto"` sentinel 처리를 추가한다. `agent_version == "auto"`이면: `self._git_commit`이 `None`이면(비-git 환경, git 미설치 등) `self._agent_version = None`으로 조용히 떨어뜨린다(예외 전파 없음 — SPEC-007과 동일한 그레이스풀 디그레이드 원칙). `self._git_commit`이 있으면 앞 8자(`self._git_commit[:8]`)를 기본 태그로 삼는다.
- **REQ-2**: REQ-1의 `"auto"` 분기에서 `git diff HEAD`(타임아웃 2초, tracked 파일의 staged+unstaged 변경 전체)를 1회 호출한다. 출력이 비어 있으면(클린 상태) REQ-1의 커밋-only 태그를 그대로 쓴다. 출력이 있으면(dirty 상태) 그 텍스트를 `hashlib.sha256`으로 해시해 앞 6자를 취하고, 최종 태그를 `f"{commit[:8]}-dirty-{diff_hash}"` 형태로 만든다. `git diff` 호출이 어떤 이유로든 실패하면(타임아웃·git 없음 등) 예외 전파 없이 REQ-1의 커밋-only 태그로 폴백한다. diff 원문 텍스트 자체는 해시 계산 후 즉시 버리고 어디에도 저장/노출하지 않는다(모노레포 등에서 매우 커질 수 있음).
- **REQ-3**: `PerformanceMonitor`에 읽기 전용 `@property def agent_version(self) -> Optional[str]`를 추가해 `self._agent_version`을 반환한다 — 사용자가 리터럴 문자열을 넘겼든 `"auto"`가 해석한 결과든, 최종적으로 어떤 값이 태그로 쓰였는지 확인할 수 있게 한다(로깅/디버깅, 향후 OpenCode 훅 연동의 전제조건). setter는 추가하지 않는다 — `model_name`과 동일하게 생성 시점에 결정되고 이후 불변인 필드로 취급한다.

## Interface

```python
# REQ-1/2 — 자동 태깅
monitor = PerformanceMonitor(output_dir="results/", agent_version="auto")

# REQ-3 — 읽기 전용 프로퍼티로 실제 해석된 값 확인
monitor.agent_version
# -> "a1b2c3d4"                  (git 커밋 클린 상태)
# -> "a1b2c3d4-dirty-f3a91c"     (동일 커밋에서 tracked 파일 미커밋 변경 있음)
# -> None                        (git 정보 없음 — 비-git 디렉토리 등)
```

```python
# 기존 사용법은 100% 그대로 — "auto"는 새로 예약된 리터럴일 뿐, 다른 값의 의미는 무변화
monitor = PerformanceMonitor(output_dir="results/", agent_version="v2-cot")
monitor.agent_version  # -> "v2-cot" (REQ-3, 그대로 반환)
```

## Acceptance

- **REQ-1**: git 저장소 안에서 `agent_version="auto"` 지정 시 `monitor.agent_version`이 `git rev-parse HEAD`의 앞 8자와 일치하는지(클린 상태). git 정보가 없는 환경(예: git 저장소 밖 임시 디렉토리로 cwd 변경)에서 `agent_version="auto"`를 줘도 예외 없이 `monitor.agent_version is None`으로 떨어지는지.
- **REQ-2** (핵심 케이스): 같은 커밋에서 파일을 두 가지 다른 내용으로 수정하고 각각 `agent_version="auto"`로 모니터를 만들었을 때 서로 다른 태그가 나오는지. 같은 커밋 + 완전히 동일한 미커밋 변경으로 두 번 실행했을 때 동일한 태그가 나오는지(재현성). 변경 후 커밋해 클린 상태로 되돌아가면 `-dirty-` 접미사 없이 커밋 SHA만 나오는지. `git diff` 서브프로세스가 실패(mock으로 시뮬레이션)해도 REQ-1의 커밋-only 태그로 안전하게 폴백하는지.
- **REQ-3**: `agent_version="v2-cot"`처럼 리터럴 문자열을 넘겼을 때 `monitor.agent_version`이 그 값을 그대로 반환하는지(회귀 없음). `"auto"` 지정 시 `monitor.agent_version`이 REQ-1/2가 계산한 값과 정확히 일치하는지. `agent_version=None`(기본값)일 때 `monitor.agent_version is None`인지.
- **회귀 없음**: `agent_version=None` 또는 `"auto"`가 아닌 임의의 리터럴 문자열을 넘겼을 때 이번 스펙 이전과 완전히 동일하게 동작하는지 — 기존 SPEC-007/SPEC-025 테스트 스위트 전체가 무수정으로 통과하는지 확인.

## Compatibility

- 100% additive — 기존 `agent_version` 파라미터의 기본값(`None`)과 리터럴 문자열 사용 방식은 전혀 바뀌지 않는다. `"auto"`라는 특정 문자열 리터럴을 이미 다른 의미로(예: 어떤 배포 환경의 이름으로) 쓰고 있던 극소수 호출자만 이번 변경으로 영향받을 수 있다(Risks 참고).
- SPEC-025가 완성한 `ResultFile.agent_version`/`compare_results(group_by=...)`/`gate --baseline-version`/대시보드 UI(`dashboard2.html.j2`의 Group by 드롭다운, `⚖️ Pairwise Judge` 탭, `📄 Export HTML`)는 전혀 수정하지 않는다 — `"auto"`가 만들어낸 문자열도 그 파이프라인 입장에서는 그냥 하나의 일반 `agent_version` 값일 뿐이다.

## Rollout

1. REQ-1(커밋 SHA 기반 기본 태깅) — 가장 리스크 낮음, 다른 REQ의 전제.
2. REQ-2(dirty 상태 해시 접미사) — REQ-1에 의존, 이번 스펙의 핵심 가치(커밋 없는 반복 iteration 구분).
3. REQ-3(읽기 전용 프로퍼티) — 독립적, 언제든 병행 가능.

## Risks

- **`"auto"` 문자열 리터럴과의 우연한 충돌**: 극히 낮은 확률이지만 사용자가 이미 실제 버전 이름으로 `"auto"`라는 문자열을 쓰고 있었다면 이번 변경으로 의미가 바뀐다 — 완화책: SDK가 아직 0.9.x(Beta)이고, `CLAUDE.md`/`Docs/`에 `"auto"`를 예약어로 명시한다.
- **untracked 파일 미반영**: 새로 추가된(아직 `git add` 안 된) 파일의 내용 변경은 `git diff HEAD`에 잡히지 않아 dirty 해시에 반영되지 않는다 — 완화책: 문서에 "새 파일을 추가하는 iteration은 자동 태깅만으로는 구분되지 않을 수 있다, 필요하면 `git add`로 스테이징하거나 명시적 `agent_version`을 쓰라"고 명시.
- **git 서브프로세스 추가 호출에 따른 `__init__` 오버헤드**: REQ-2가 `git diff HEAD` 1회를 추가한다 — 기존 REQ(SPEC-007)와 동일하게 인스턴스 생성 시 1회만 호출하고(반복 오버헤드 없음), 동일한 2초 타임아웃을 적용해 대형 저장소에서도 `__init__`이 무한정 지연되지 않게 한다.
- **대형 diff의 메모리/시간 비용**: 모노레포 등에서 `git diff HEAD` 출력이 매우 클 수 있다 — 완화책: 해시만 계산하고 diff 원문 자체는 저장·노출하지 않으며, 해시 계산 직후 참조를 버린다(가비지 컬렉션 대상).
- **후속 스펙과의 경계**: 이번 스펙이 만드는 안정적인 `agent_version` 값 자체는 OpenCode 훅에 "회귀했다"는 힌트를 노출하는 것과는 별개다 — 그 배선은 명시적으로 Non-Goals에 남겨, 스코프 누수를 방지한다.
