# SPEC-021: 코드 품질 부채 래칫 (ruff/mypy)

**Phase:** P6 (SDK 전반 성숙도 — 엔지니어링 거버넌스) · **상태:** Implemented (2026-07-04) · **의존성:** SPEC-017(완료, `.github/workflows/ci.yml`의 report-only ruff/mypy 잡을 이번 스펙이 대체)

> **구현 노트 (2026-07-04)**: 신규 `scripts/quality_ratchet.py` — `ruff check --output-format=json`
> 출력 배열 길이와 mypy stdout의 `": error:"` 라인 수를 세어 `.github/quality-baseline.json`
> 과 비교, 하나라도 늘어나면 종료 코드 1. `.github/workflows/ci.yml`의 `lint-and-typecheck`
> 잡이 이제 이 스크립트 1개 스텝만 실행(기존 `continue-on-error: true` 2-스텝 report-only
> 구성 대체). `.github/quality-baseline.json`을 오늘 시점 실제 측정값(ruff 4,120건 / mypy
> 318건 — SPEC-017 도입 시점 baseline 4,063/305에서 이번 세션의 신규 파일들
> `live_guardrail.py`/`live_guardrail_stdio.py`/`live_guardrail_report.py`/
> `pii_redaction.py` 추가로 증가)으로 새로 캡처. `scripts/quality_ratchet.py`를 baseline보다
> 늘어난 상태(1건 추가)와 그렇지 않은 상태 양쪽으로 로컬 실행해 실패/통과 분기가 실제로
> 작동함을 확인.

## Context

- `.github/workflows/ci.yml`의 `lint-and-typecheck` 잡(SPEC-017)은 `ruff check`/`mypy`를 각각
  `continue-on-error: true`로 실행한다 — 도입 시점(2026-07-03) 기존 부채(ruff 4,063건 / mypy
  305건)를 hard-block으로 걸면 CI가 즉시 영구 실패하므로 채택한 임시 조치였고, 문서(SPEC-017
  구현 노트, `Docs/specs/README.md`)에 "정리 완료 후 강제 실패로 전환할 것"이라고 명시돼 있다.
- 문제는 이 report-only 상태가 "부채가 늘어나도 아무도 모른다"는 뜻이기도 하다 — 새 PR이
  린트/타입 오류를 추가해도 CI가 초록불이다. 이번 세션에서 추가한 신규 파일 4개
  (`agent_evaluator/gates/live_guardrail.py`, `agent_evaluator/integrations/
  live_guardrail_stdio.py`, `agent_evaluator/integrations/live_guardrail_report.py`,
  `agent_evaluator/utils/pii_redaction.py`)만으로도 실측 결과 ruff 4,063→4,120(+57), mypy
  305→318(+13)로 실제로 늘어났다(직접 `ruff check agent_evaluator/ --output-format=json`/
  `mypy agent_evaluator/`로 재측정, 이 세션에서 확인).
- 기존 4,120/318건을 전부 정리하는 건 이번 스펙 범위 밖의 별도 대규모 작업이다 — 대신
  "이번 변경이 baseline보다 늘렸는가"만 검사하는 게 SPEC-017이 예고한 "정리 완료 후"를
  기다리지 않고도 지금 바로 부채 증가를 막는 가장 작은 개입이다.
- `ruff check --output-format=json`은 위반 1건당 배열 원소 1개를 반환하므로 `len(json.load(...))`
  으로 정확한 오류 수를 셀 수 있음을 직접 확인했다(4,120건 재현). mypy는 별도 JSON 출력
  모드가 없어 stdout에서 `": error:"` 포함 라인 수를 세는 방식으로 근사한다(주석/설명
  라인이 아닌 실제 오류 라인만 이 패턴을 갖는 것을 mypy 출력 포맷 관례상 신뢰할 수 있음).

## Goals

- 새 PR이 ruff 오류 수 또는 mypy 오류 수를 baseline보다 늘리면 CI가 실패한다.
- 기존 부채(4,120/318)는 그대로 둬도 CI가 통과한다 — "더 나빠지지만 않으면 통과"라는
  래칫(ratchet) 원칙.
- baseline을 낮추는 것(부채를 실제로 줄인 뒤)은 사람이 `.github/quality-baseline.json`을
  수동으로 갱신하는 명시적 행위로 남긴다(자동 하향 없음 — 실수로 일시적 개선을 영구
  기준으로 고정하는 걸 방지).

## Non-Goals

- 기존 4,120/318건의 실제 정리(리팩터링) — 별도의, 훨씬 큰 작업이다.
- ruff/mypy 규칙 자체의 추가/완화 — `pyproject.toml`의 기존 설정을 그대로 쓴다.
- pytest 잡(`test`)의 hard-block 여부 변경 — 이미 hard-block이며 이 스펙과 무관.
- baseline 자동 하향(오류가 baseline보다 적어지면 자동으로 파일을 갱신하는 것) — 사람이
  의도를 갖고 갱신하는 걸 원칙으로 한다(Goals 참조).

## Requirements

- **REQ-1**: 신규 `scripts/quality_ratchet.py` — `ruff check agent_evaluator/
  --output-format=json`을 서브프로세스로 실행해 stdout을 JSON 배열로 파싱, 길이를
  `ruff_errors` 카운트로 삼는다.
- **REQ-2**: 같은 스크립트에서 `mypy agent_evaluator/`를 서브프로세스로 실행해, stdout의
  각 줄 중 `": error:"`를 포함하는 줄의 개수를 `mypy_errors` 카운트로 삼는다.
- **REQ-3**: 신규 `.github/quality-baseline.json` — `{"ruff_errors": int, "mypy_errors": int}`
  형식. 이번 스펙 도입 시점 실측값으로 초기화한다.
- **REQ-4**: `scripts/quality_ratchet.py`는 baseline을 읽어 두 카운트 각각을 비교한다 —
  하나라도 baseline보다 크면 그 항목을 `FAIL: ... (+N)` 형식으로 stderr/stdout에 출력하고
  최종 종료 코드 1. 전부 baseline 이하면 `OK: ...` 출력과 종료 코드 0.
- **REQ-5**: `.github/workflows/ci.yml`의 `lint-and-typecheck` 잡을 `continue-on-error: true`
  2-스텝 구성에서 `python scripts/quality_ratchet.py` 단일 스텝(기본 hard-block, `continue-
  on-error` 없음)으로 교체한다.
- **REQ-6**: 실패 메시지에 "baseline을 의도적으로 낮추려면 `.github/quality-baseline.json`을
  직접 갱신하라"는 안내를 포함해, 부채를 줄인 기여자가 다음 절차를 바로 알 수 있게 한다.

## Interface

```bash
# 로컬 실행
python scripts/quality_ratchet.py
# OK: ruff_errors = 4120 (baseline 4120)
# OK: mypy_errors = 318 (baseline 318)
# (모두 통과 시 종료 코드 0)

# 부채가 늘어난 경우
# FAIL: ruff_errors increased from 4120 to 4121 (+1)
#
# Quality ratchet failed — this change increased lint/type debt.
# If you intentionally reduced debt, update .github/quality-baseline.json to the new lower count.
# (종료 코드 1)
```

```json
// .github/quality-baseline.json
{"ruff_errors": 4120, "mypy_errors": 318}
```

## Acceptance

- baseline과 정확히 같은 카운트로 실행 → 종료 코드 0, 모든 항목 `OK`.
- baseline 파일을 실제 카운트보다 1 작게 임시 수정한 뒤 실행 → 해당 항목만 `FAIL: ... (+1)`,
  종료 코드 1 — 로컬에서 실제로 재현해 확인했다.
- baseline 파일을 실제 카운트보다 크게 수정 → 종료 코드 0(부채가 baseline보다 적으므로 통과,
  자동으로 baseline을 낮추지는 않음 — Non-Goals 확인).
- CI: 기존 `test` 잡(pytest)은 무변경, 계속 hard-block.

## Compatibility

- `test` 잡(pytest matrix)은 전혀 건드리지 않는다.
- `lint-and-typecheck` 잡의 동작 방식이 "항상 초록불(report-only)"에서 "baseline 초과 시
  빨간불"로 바뀐다 — 이건 의도된 동작 변경이다(Goals). 현재 baseline 이하로 유지하는 PR은
  영향 없음.

## Rollout

1. `scripts/quality_ratchet.py` 작성(REQ-1~4).
2. `.github/quality-baseline.json` 초기 캡처(REQ-3, 이 세션의 실측값).
3. `.github/workflows/ci.yml`의 `lint-and-typecheck` 잡 교체(REQ-5~6).
4. 로컬에서 통과/실패 양쪽 시나리오 재현 확인(Acceptance).
5. `Docs/specs/README.md` 인덱스 갱신.

## Risks

- **mypy 오류 카운팅이 근사치**: `": error:"` 문자열 매칭은 mypy가 출력 포맷을 바꾸면(예:
  `--output=json` 도입 등 향후 버전) 깨질 수 있다 — 완화책: mypy 버전을 고정하는 기존
  `pyproject.toml`/`requirements` 관리에 의존하고, 포맷이 바뀌면 스크립트도 함께 갱신.
- **baseline 파일을 아무도 안 낮추면 부채가 영원히 고정된다**: 이 스펙은 "늘어나지 않게"만
  보장하지 "줄어들게" 강제하지 않는다 — 실제 부채 정리는 여전히 별도의, 사람이 주도하는
  작업으로 남는다(Non-Goals에 명시).
- **ruff/mypy 버전 업그레이드로 새 규칙이 추가돼 카운트가 오르는 경우**: 코드 변경 없이도
  CI가 실패할 수 있다 — 이 경우 baseline을 새 카운트로 갱신하는 게 정당한 대응이다(REQ-6
  안내 메시지가 이 경로를 커버).
