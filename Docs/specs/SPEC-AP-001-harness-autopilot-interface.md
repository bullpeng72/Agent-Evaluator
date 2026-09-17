# SPEC-AP-001: Harness Autopilot ↔ agent-evaluator 인터페이스 경계

- **상태**: ✅ 경계 정리 완료 (2026-09-17) — 코드 동작 변경 없음, 계약 명시·리팩터만
- **범위**: 이 문서는 Harness Autopilot 전체 설계서가 **아니다**. 전체 설계(Phase 0–8
  파이프라인, UI, 로드맵 M0–M4)는 claude.ai Artifact로만 존재한다(저장소 밖).
  이 문서가 다루는 건 딱 하나 — **Autopilot이 지금 `agent_evaluator/` 패키지
  안에 얹혀 있지만, 두 코드베이스 사이에 이미 그어져 있는 경계선이 어디인지**다.
- **이 트랙과 SPEC-000~044의 관계**: 이 문서는 위 README.md의 Phase(P0–P12)
  로드맵에 속하지 않는다. SPEC-000~044는 agent-evaluator 코어 SDK(Gate A–G ·
  25 트래커 · 33 Config) 자체의 구조 개선 프로그램이고, Harness Autopilot은
  그 위에 얹힌 별개 워크플로 도구(하니스 메서드론 도서의 동반 자동화, 한국어
  독자 대상, 아직 M0~M4 부분 구현)다. 번호 체계(`SPEC-AP-001`)만 같은 디렉토리
  관례를 따를 뿐, 코어 로드맵 표에는 올리지 않는다.

---

## 0. 왜 이 문서가 존재하는가

Autopilot은 지금 `agent_evaluator/gates/autopilot_state.py` ·
`agent_evaluator/cli/autopilot.py` · `agent_evaluator/serve/autopilot_app.py`로
코어 SDK와 한 저장소·한 배포판에 같이 있다. 하지만 성격은 다르다 — 코어
SDK는 프레임워크 불문·언어 불문 범용 평가 도구고, Autopilot은 특정 방법론
(하니스 메서드론)의 특정 팀 워크플로를 자동화하는 도구다. 지금 당장 별도
패키지로 쪼갤 필요는 없지만(1인 유지보수 체제에서 리포 두 개를 운영하는
비용이 지금 얻는 가치보다 크다), **나중에 쪼개기 쉽도록 지금 경계를
명시적으로 그어 두는 것**이 이 문서와 관련 코드 변경의 목적이다.

경계는 세 곳에 있다:

1. Autopilot이 기대는 코어 SDK 내부 함수 두 개 (§1)
2. `.aoo/*.jsonl` 파일 포맷 자체 (§2) — 사실 이게 진짜 인터페이스다
3. `agent-eval` CLI에 서브커맨드가 등록되는 방식 (§3)

---

## 1. SDK 내부 함수 계약

Autopilot은 자기가 직접 만들지 않는 데이터 두 종류를 읽는다 — 팀 클레임과
게이트 실행 결정 원장. 둘 다 코어 SDK가 이미 갖고 있던 append-only JSONL
모듈을 그대로 재사용한다(새 판정 로직을 만들지 않는다는 원칙 그대로).

| 함수 | 위치 | Autopilot 소비처 | 반환 계약 |
|---|---|---|---|
| `load_active_claims(claims_path)` | `agent_evaluator/gates/team_concurrency.py` | `serve/autopilot_app.py::_safe_claims()` (운영 현황 페이지) | `list[dict]`, 각 dict에 `developer`/`scope`/`claim_id` 포함, 파일 없으면 `[]` |
| `load_decisions(log_path)` | `agent_evaluator/rca/decision_ledger.py` | `gates/autopilot_state.py::detect_repeated_undecided()`, `serve/autopilot_app.py::_ops_body()` | `list[dict]`, `kind`가 `"gate_run"`/`"outcome"`, gate_run 항목에 `id`/`exit_code`/`undecided_reason?`/`verdict_level`, 파일 없으면 `[]` |

두 함수의 docstring에 `.. important::` 블록으로 "Autopilot이 이 반환 모양에
직접 의존한다"는 경고를 달아 뒀다 — 이 함수들을 고치는 사람이 그 자리에서
바로 계약을 보게 하려는 목적이다.

**이 계약을 코드로 고정한 테스트**: `tests/test_autopilot_sdk_contract.py`.
Autopilot 자체 테스트(`test_gates_autopilot_state.py`, `test_cli_autopilot.py`)와
분리된 별도 파일이다 — team_concurrency.py나 decision_ledger.py를 고치는
사람이 "Autopilot용 테스트가 있는지" 몰라도, 이 파일 이름만 보면 바로
이해할 수 있게 하려는 의도다. 이 테스트가 실패하면 Autopilot도 같이
손봐야 한다는 신호다.

**나중에 분리된다면**: 이 두 함수(와 그 반환 스키마)가 그대로 `harness-autopilot`
패키지가 기대는 `agent-evaluator`의 공개 API가 된다. 지금부터 이 두 함수의
반환 모양을 바꿀 때는 하위호환을 고려해야 한다는 뜻이다.

---

## 2. `.aoo/*.jsonl` 파일 포맷 — 진짜 인터페이스

Autopilot과 코어 SDK를 가장 느슨하게 묶어 두는 건 함수 호출이 아니라
**파일 포맷**이다. Autopilot이 이 포맷만 지키면, 코어 SDK의 내부 구현이
어떻게 바뀌든(심지어 Python이 아닌 다른 언어로 다시 짜여도) Autopilot은
영향받지 않는다. 이게 두 코드베이스가 언젠가 정말로 분리될 때 실질적인
경계선이 될 파일이다.

### 2.1 공통 관례 — append-only JSONL

`claims.jsonl` / `decisions.jsonl` / `approvals.jsonl` 세 파일 전부 같은
규칙을 따른다:

- 한 줄 = 이벤트 하나(JSON 객체, `ensure_ascii=False`, 줄마다 `\n`으로 끝남).
- 기존 줄은 절대 수정·삭제하지 않는다 — 상태를 바꾸려면 같은 식별 필드
  (`claim_id`/`id`/`id`)를 가진 새 줄을 뒤에 추가한다.
- "현재 상태"는 **같은 id의 마지막 줄**이다 — 별도 인덱스나 상태 컬럼을
  두지 않는다. 리더(`load_active_claims`/`load_decisions`/`load_approvals`)는
  전체를 순서대로 읽으며 `{id: 마지막 줄}` 맵을 만든 뒤 그 값만 반환한다.
- 손상된 줄(부분 write, 수동 편집 실수)은 그 줄만 건너뛴다 — 파일 전체
  로드를 깨지 않는다.
- 파일이 아예 없으면 빈 리스트를 반환한다(예외를 던지지 않는다).

이 관례 자체가 `sync-drift-check` 스킬(`Skills/sync-drift-check/SKILL.md`)이
전제하는 것이기도 하다 — GitHub 라벨 같은 "다른 저장소"와 이 JSONL을
대조할 때, "마지막 줄이 진실"이라는 규칙이 흔들리면 그 스킬 자체가
무의미해진다.

### 2.2 `.aoo/claims.jsonl` — 코어 SDK 소유, Autopilot은 읽기만

코어 SDK의 `agent-eval claims` 서브커맨드가 쓴다(`gates/team_concurrency.py`).
Autopilot은 절대 여기에 쓰지 않는다 — 오직 `load_active_claims()`를 통해
읽기만 한다(§1). 필드 스키마는 `team_concurrency.py`가 원 소유자이므로
이 문서에서 다시 정의하지 않는다.

### 2.3 `.aoo/decisions.jsonl` — 코어 SDK 소유, Autopilot은 읽기만

코어 SDK의 `agent-eval gate --decision-log` / `agent-eval decisions record`가
쓴다(`rca/decision_ledger.py`). Autopilot은 여기에도 쓰지 않는다 — 오직
`load_decisions()`를 통해 읽고, `kind == "gate_run" and exit_code == 75`인
줄에서 `undecided_reason` 반복을 센다(`detect_repeated_undecided()`).

### 2.4 `.aoo/approvals.jsonl` — Autopilot 소유

이건 Autopilot이 직접 쓰고 읽는 자기 소유 파일이다(`gates/autopilot_state.py`).
줄 하나의 모양:

```jsonc
{
  "id": "ap-a1b2c3d4",             // 없으면 자동 생성(ap-<hex8>)
  "task_id": "ST-014",             // 또는 PORTFOLIO_TASK_ID("PORTFOLIO") — 특정
                                    // 과제가 아니라 포트폴리오 전체에 걸친 패턴일 때
  "kind": "spec_review",           // VALID_APPROVAL_KINDS 중 하나 —
                                    // spec_review · adr_review · skill_merge ·
                                    // release_hold · deploy · threshold_review
  "phase": 1,                      // PHASE_LABELS(0~8) 중 하나
  "title": "ST-014 SPEC 검토",
  "opened_at": "2026-09-17T00:00:00+00:00",
  "status": "pending",             // pending | draft | approved | rejected |
                                    // changes_requested
  "checklist": [{"label": "...", "status": "ok"}],
  "gate_on_checklist": true,       // false면 checklist는 표시용 — 승인 게이트 아님
  "needs_clarification": [],       // 본문의 [NEEDS CLARIFICATION: ...] 태그
  "checklist_score": {"total": 1, "ok_count": 1, "blocking": [], "ready_for_review": true},
  "required_approvals": 1,         // deploy/release_hold는 기본 2
  "approvals_recorded": [],        // required_approvals > 1일 때 쌓이는 부분 승인
  "decision": null,
  "decided_by": null,
  "rationale": null
}
```

이 스키마를 바꾸려면 §1의 계약 테스트와 마찬가지로,
`tests/test_gates_autopilot_state.py`·`tests/test_cli_autopilot.py`가 이
모양을 그대로 assert하고 있다는 걸 기억해야 한다.

### 2.5 `.aoo/tasks/<task_id>.json` · `.aoo/team.json`

과제 하나당 파일 하나(`tasks/`), 팀 전체가 파일 하나(`team.json`,
`{"members": [...]}`) — 둘 다 append-only가 아니라 통째로 덮어쓰는 방식이다
(별도 인덱스 없이 디렉토리/파일 자체가 진실 소스). `task_id`는 그대로
파일명이 되므로 `_SLUG_RE`(`^[A-Za-z0-9][A-Za-z0-9_.-]*$`)로 검증된다 —
경로 조작 방지가 이 포맷의 일부다.

---

## 3. CLI 서브커맨드 등록 — entry-points 플러그인

`agent-eval` CLI의 대부분 서브커맨드(gate/dashboard/claims/...)는
`cli/main.py`가 직접 import한다 — 전부 코어 SDK 자체 기능이라 바꿀 이유가
없다. Autopilot만 다르게 등록된다:

- `pyproject.toml`의 `[project.entry-points."agent_evaluator.cli_plugins"]`가
  `autopilot = "agent_evaluator.cli.autopilot:register"`를 선언한다.
- `cli/main.py::_load_cli_plugins(sub)`가 `importlib.metadata.entry_points(group="agent_evaluator.cli_plugins")`로
  이 그룹을 찾아 각 엔트리 포인트의 `register(sub) -> Callable[[Namespace], int]`를
  호출한다 — 서브파서를 등록하고 핸들러를 돌려받는다.
- `cli/main.py`는 `agent_evaluator.cli.autopilot` 모듈 이름을 어디에도
  하드코딩하지 않는다.

**나중에 분리된다면**: `agent_evaluator/cli/autopilot.py`(와
`gates/autopilot_state.py`, `serve/autopilot_app.py`, `Skills/`)를 통째로
새 배포판(예: `harness-autopilot`, `agent-evaluator`를 의존성으로 선언)으로
옮기고, 이 entry-points 선언만 그 패키지의 `pyproject.toml`로 옮기면 된다.
`cli/main.py`는 코드 변경이 필요 없다 — `pip install harness-autopilot`이
설치돼 있기만 하면 `agent-eval autopilot ...`이 그대로 동작한다.

⚠️ **entry_points는 소스가 아니라 빌드 메타데이터(`*.dist-info/entry_points.txt`)에서
읽힌다** — `pyproject.toml`을 고친 뒤 `pip install -e .`을 다시 실행하지
않으면 반영되지 않는다. `tests/test_cli_autopilot.py::TestEntryPointRegistration::
test_installed_entry_point_metadata_resolves_to_register`가 이 실수를 잡는다.

---

## 4. 분리 준비 상태 체크리스트

| 항목 | 상태 |
|---|---|
| SDK 내부 함수 의존이 명시적 계약(docstring + 별도 테스트 파일)으로 고정됨 | ✅ §1 |
| `.aoo/*.jsonl` 포맷이 문서화됨(스키마 + append-only 관례) | ✅ §2 |
| CLI 등록이 하드코딩 import 대신 entry-points 플러그인 방식 | ✅ §3 |
| Autopilot 코드가 자기만의 하위 디렉토리로 격리됨(`gates/autopilot_state.py` 등은
  아직 다른 `gates/*.py`와 같은 디렉토리에 있음) | ❌ 아직 |
| 별도 pip extra(`agent-evaluator[autopilot]`)로 설치 여부를 가를 수 있음 | ❌ 아직 |
| 실제 사용자가 코어 SDK와 무관하게 Autopilot만 원하는 사례가 확인됨 | ❌ 아직 — 실행 조건 |

마지막 두 항목은 지금 당장 할 필요 없다 — §0에서 밝혔듯 지금은 "쪼갤 수
있게 경계만 그어 두는" 단계고, 실제로 쪼개는 건 사용 패턴이 그걸
요구할 때(별도 릴리스 주기가 필요해질 때, 코어 SDK만 쓰고 싶은 사용자의
피드백이 실제로 들어올 때)로 미룬다.
