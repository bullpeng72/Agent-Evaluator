# SPEC-017: 공급망 위생 (CI, 취약점 스캔, Dependabot, pre-commit, SBOM)

**Phase:** P4 · **상태:** Implemented (2026-07-03) · **의존성:** 없음

> **구현 노트**: `.github/workflows/ci.yml`(REQ-1) — `pytest`를 Python 3.8~3.13 매트릭스로
> 실행하는 `test` 잡(hard-block)과, `ruff check`/`mypy`를 실행하는 `lint-and-typecheck`
> 잡(REQ-1 원안대로 도입하되 **Rollout 1단계에서 로컬 baseline을 실제로 측정한 결과**
> `ruff check agent_evaluator/`가 4,063건, `mypy agent_evaluator/`가 305건의 기존 경고를
> 낸다는 것을 확인했다 — 처음부터 hard-block으로 켜면 CI가 이번 스펙과 무관한 기존 부채로
> 인해 즉시 영구적으로 실패한다. Risks에서 이미 서술해 둔 완화책("초기엔 경고 모드로
> 도입")을 그대로 적용해 두 도구 모두 `continue-on-error: true`로 report-only 실행하도록
> 조정했다 — `pytest`(3,095 passed 확인됨)만 hard-block. `.github/workflows/security.yml`
> (REQ-2/5) — `pip-audit`을 push/PR/매주 월요일 스케줄로 실행(동일한 이유로 report-only —
> 로컬에서 실제로 20건의 알려진 취약점이 발견됨을 확인), `v*` 태그 push 시에만 별도
> `sbom` 잡이 `pip-audit --format=cyclonedx-json`으로 SBOM을 생성해 아티팩트로 업로드한다
> (로컬에서 실제로 유효한 CycloneDX JSON이 생성되는지 검증 완료). `.github/dependabot.yml`
> (REQ-3) — `pip`/`github-actions` 두 생태계 모두 주간 스케줄로 등록. `.pre-commit-config.yaml`
> (REQ-4) — 이미 dev 의존성으로 선언만 되어 있던 `pre-commit`을 실제로 동작하게 만드는
> 최소 훅 구성(`ruff`/`ruff-format`/`trailing-whitespace`/`end-of-file-fixer`/`check-yaml`/
> `check-toml`/`check-merge-conflict`/`check-added-large-files`). `SECURITY.md`(REQ-6) —
> 최소 취약점 제보 절차. 위 항목 모두 기존 수동 릴리스 절차(`python -m build`/
> `twine upload`)를 변경하지 않는다(REQ-7).
>
> **구현 중 겪은 사고와 교훈**: Acceptance 검증 차 `pre-commit run --all-files`를 실행했더니
> (신설한 `.pre-commit-config.yaml`이 리포지토리 전체에 처음 적용되는 것이었으므로) 928건의
> `ruff --fix` 자동수정과 191개 파일의 `ruff-format` 재포맷, 다수 파일의 trailing-whitespace/
> end-of-file 수정이 **의도치 않게 전체 코드베이스(199개 추적 파일)에 실제로 적용**됐다.
> 이는 SPEC-017의 스코프(CI/설정 파일 추가)를 크게 벗어나는, 리뷰 불가능한 대규모 diff였고
> 마침 이전 턴에서 커밋되지 않은 SPEC-015/016의 실제 코드 변경(`alerts/engine.py`,
> `core/trackers/monitor.py`)과 섞여버렸다. `git stash`(비파괴적)로 안전하게 격리한 뒤,
> SPEC-015/016에서 실제로 적용했던 편집만 정확히 재현하는 방식으로 복구했다 — 전체
> 되돌리기(`git checkout --`)가 안전 분류기에 의해 두 차례 차단된 것도 적절한 제동이었다.
> **교훈**: `pre-commit run --all-files`처럼 리포지토리 전체에 쓰기 효과가 있는 명령은,
> 새 pre-commit 설정을 막 추가한 시점에는 "설정 문법이 유효한지"와 "실제로 전체 코드베이스에
> 적용했을 때 무엇이 바뀌는지"가 완전히 다른 질문이라는 것 — Acceptance 항목 "pre-commit
> run --all-files가 에러 없이 실행되는지 확인"은 문법·훅 실행 자체의 검증으로 충분했고,
> 결과물을 실제로 커밋 대상에 반영하는 것은 별도의, 사람이 명시적으로 승인해야 하는 결정이다.
> 이번 구현에서는 초기 대규모 리포맷을 적용하지 않고 신규 설정 파일 자체만 추가하는 것으로
> 범위를 좁혔다 — 코드베이스 전체 리포맷은 필요하다면 별도 PR로 분리해 진행할 것을 권장한다.
>
> 전체 스위트 3,095 passed, 1 skipped, 회귀 0건(신규 인프라 파일 추가만으로는 pytest에
> 영향 없음 — 예상대로).

## Context

- 리포지토리에 `.github/` 디렉토리 자체가 존재하지 않는다(직접 확인 — `.github/workflows`,
  `.github/dependabot.yml` 모두 부재). `git remote -v`로 `origin`이
  `git@github.com:bullpeng72/Agent-Evaluator.git`로 실제 설정돼 있어 GitHub Actions를
  바로 활용 가능한 상태인데도 CI 워크플로우가 0건이다 — PR/push 시 `pytest`/`ruff`/`mypy`가
  전혀 자동 실행되지 않는다.
- `pyproject.toml`의 `dependencies`(`:43-51`)와 `[project.optional-dependencies]`
  각 그룹은 전부 `>=X.Y.Z,<MAJOR.0.0` 형태의 넓은 범위 핀을 사용한다(예:
  `"numpy>=1.20.0,<3.0.0"`). 라이브러리 패키지로서 넓은 범위 자체는 합리적인 선택이지만,
  이를 보완할 **알려진 취약점(CVE) 자동 스캔이 전혀 없다** — `pip-audit`/`safety` 등 어떤
  도구도 CI나 로컬 훅에 연결되어 있지 않음(grep으로 확인, `pyproject.toml`/워크플로우
  어디에도 언급 없음).
- 리포지토리 루트에 lockfile(`*.lock`, `requirements*.txt` 등)이 전혀 없다 — 재현 가능한
  빌드 환경을 보장할 방법이 없다(확인됨, `find . -maxdepth 1` 결과 0건).
- `pyproject.toml`의 `dev` extras(`:239-248`)에 **`pre-commit>=3.0.0`이 이미 dev 의존성으로
  선언**돼 있지만, `.pre-commit-config.yaml` 파일 자체가 리포지토리에 없다 — 설치는
  안내되지만 실제로 훅이 하나도 구성되어 있지 않아 이 의존성이 사실상 아무 효과가 없다
  (SPEC-011의 "선언은 됐지만 실제로 연결 안 됨" 패턴과 동일한 종류의 공백).
- `SECURITY.md`(취약점 제보 정책)도 리포지토리에 없다(확인됨).
- 이 프로젝트는 `python -m build` + `twine upload dist/*`(`CLAUDE.md` Build 섹션에 이미
  문서화)로 PyPI에 실제 배포되는 공개 패키지다 — SBOM(소프트웨어 구성 명세)이나 릴리스
  아티팩트의 구성요소 목록화가 전혀 없어, 다운스트림 사용자가 이 패키지의 정확한 의존성
  트리를 감사하려면 직접 `pip show`를 반복하는 수밖에 없다.
- `pyproject.toml`에 `[tool.ruff]`(`:280-282`, `line-length=100`, `target-version="py38"`),
  `[tool.mypy]`(`:288-291`), `[tool.pytest.ini_options]`(`:295-298`) 설정이 이미 모두
  존재한다 — 즉 CI가 필요로 하는 도구 설정 자체는 이미 준비돼 있고, 이를 자동 실행할
  워크플로우만 없는 상태(신규 설정 작업이 아니라 순수 "연결" 작업).

## Goals

- push/PR 시 테스트·린트·타입체크가 자동으로 실행되어, 사람이 로컬에서 잊고 건너뛴 경우에도
  회귀를 잡는다.
- 알려진 취약점이 있는 의존성을 자동으로 탐지한다(신규 CVE 공시에 대해서도 주기적으로).
- 의존성 업데이트가 사람이 수동으로 `pyproject.toml`을 편집하는 것에만 의존하지 않고
  자동 PR로 제안된다.
- 이미 선언만 되어 있던 `pre-commit` 의존성을 실제로 동작하게 만든다.
- 릴리스 아티팩트에 대해 SBOM을 생성해 다운스트림 사용자가 의존성 구성을 감사할 수 있게 한다.

## Non-Goals

- GitHub 브랜치 보호 규칙(필수 리뷰어, 필수 상태 체크 등) 설정 — 이는 코드가 아니라
  리포지토리 관리자 설정(GitHub 웹 UI/API)이며 이번 스펙의 파일 기반 변경 범위 밖이다.
- `twine upload`를 CI로 자동화하는 것 — PyPI API 토큰을 GitHub Secrets로 등록해야 하는
  별도의, 더 높은 리스크의 결정이므로 "위생" 스펙에 묶지 않는다. 배포는 계속 `CLAUDE.md`에
  문서화된 수동 절차(`python -m build` + `twine upload dist/*`)를 따른다.
- 완전한 SLSA/공급망 출처 증명(provenance attestation) 체계 구축 — SBOM 생성까지만
  다루고, 그 이상의 서명/증명 인프라는 별도 스코프로 남긴다.
- `pyproject.toml`의 기존 넓은 버전 범위 정책 자체를 더 엄격한 고정 핀으로 바꾸는 것 —
  라이브러리 패키지로서 의도된 선택이며, 이번 스펙은 그 위에 취약점 스캐너를 추가하는
  것이지 핀 정책을 재설계하는 것이 아니다.

## Requirements

- **REQ-1**: `.github/workflows/ci.yml` 신설 — push/PR 시 이미 `pyproject.toml`에 설정된
  `pytest`(`--no-cov` 또는 기존 `[tool.pytest.ini_options]` 기준)/`ruff check
  agent_evaluator/`/`mypy agent_evaluator/`를 `classifiers`에 명시된 지원 버전
  (3.8, 3.9, 3.10, 3.11, 3.12, 3.13) 매트릭스로 실행한다.
- **REQ-2**: `.github/workflows/security.yml`(또는 REQ-1 워크플로우에 잡 추가) —
  `pip-audit`를 push/PR 시 실행하고, 추가로 `schedule`(예: 매주 1회) 트리거로도 실행해
  PR 시점 이후 새로 공시된 CVE도 주기적으로 탐지한다.
- **REQ-3**: `.github/dependabot.yml` 신설 — `pip` 생태계(주기적 의존성 업데이트 PR)와
  `github-actions` 생태계(REQ-1/2 워크플로우가 참조하는 액션 자체의 공급망 리스크 관리)
  둘 다 등록한다.
- **REQ-4**: `.pre-commit-config.yaml` 신설 — 이미 dev 의존성으로 선언된 `pre-commit`이
  실제로 동작하도록 최소 훅 구성(`ruff check --fix`, `ruff format`, trailing-whitespace/
  end-of-file-fixer 등 표준 훅)을 추가한다.
- **REQ-5**: 릴리스 시(예: `v*` 태그 push 트리거) SBOM을 생성해 워크플로우 아티팩트로
  첨부하는 CI 잡을 추가한다(예: `pip-audit --format=cyclonedx-json` 또는 `cyclonedx-bom`).
  일반 PR/push에는 실행하지 않아 CI 비용을 늘리지 않는다.
- **REQ-6**: `SECURITY.md` 추가 — 취약점 제보 절차(연락처, 예상 응답 기한)를 최소한으로 명시한다.
- **REQ-7**: 위 항목 전부는 기존 수동 릴리스 절차(`python -m build`/`twine upload`,
  `CLAUDE.md` Build 섹션)에 어떤 변경도 강제하지 않는다 — 추가적인 자동화이지 절차 교체가 아니다.

## Interface

파일 기반 변경이므로 API 시그니처 변경은 없다. 신규 파일:

```
.github/workflows/ci.yml
.github/workflows/security.yml
.github/dependabot.yml
.pre-commit-config.yaml
SECURITY.md
```

## Acceptance

- CI 워크플로우가 실제 PR에서 트리거되어 `pytest`/`ruff`/`mypy` 잡이 모두 green으로
  통과하는지 확인(기존 코드 기준 — 새 워크플로우 도입으로 인한 신규 실패가 없어야 함).
- `pip-audit` 잡이 현재 `pyproject.toml`의 의존성 세트에 대해 실행되어 알려진 취약점이
  없으면 통과, 있으면 실패로 리포트되는지 확인(현재 의존성 기준 실제 실행 결과를 스펙
  구현 노트에 기록).
- Dependabot 설정 파일이 GitHub의 `dependabot.yml` 스키마에 맞게 검증되는지 확인(GitHub이
  invalid 설정을 감지하면 Insights 탭에 오류가 표시됨 — 머지 후 확인).
- `pre-commit run --all-files`가 로컬에서 에러 없이 실행되는지 확인(신규 훅 설정 검증).
- 태그 push 시 SBOM 아티팩트가 실제로 생성되는지(테스트 태그로 1회 검증).

## Compatibility

- 전부 신규 파일 추가이며 기존 코드/테스트/빌드 절차에 영향 없음.
- CI가 처음 도입되므로, 만약 기존 코드에 이미 잠재된 lint/type 경고가 있다면 CI가
  "새로 깨뜨린" 것처럼 보일 수 있음 — 도입 시점에 `ruff check`/`mypy`를 로컬에서 먼저
  실행해 사전에 확인(Rollout 1단계).

## Rollout

1. 로컬에서 `ruff check agent_evaluator/`, `mypy agent_evaluator/`, `pytest`를 먼저 실행해
   CI 도입 시점 기준 baseline이 green인지 확인(아니라면 CI가 아니라 기존 코드 문제이므로
   별도로 먼저 정리).
2. REQ-1: `ci.yml` 추가.
3. REQ-2: `security.yml` 추가(또는 `ci.yml`에 잡 추가).
4. REQ-3: `dependabot.yml` 추가.
5. REQ-4: `.pre-commit-config.yaml` 추가, README/CLAUDE.md에 `pre-commit install` 안내 추가.
6. REQ-5/6: SBOM 릴리스 잡, `SECURITY.md`.

## Risks

- CI 매트릭스(6개 Python 버전)가 처음부터 전부 켜지면 기존에 발견되지 않았던 버전별
  비호환성이 한꺼번에 드러날 수 있음 — 완화책: Rollout 1단계에서 로컬 검증 후, 필요하면
  매트릭스를 단계적으로 확장(예: 3.11만 필수로 먼저 시작, 나머지는 `continue-on-error`로
  경고만).
- Dependabot이 자동으로 여는 PR이 너무 잦으면(모든 사소한 patch 업데이트마다) 리뷰
  피로가 쌓일 수 있음 — 완화책: `dependabot.yml`에 `schedule.interval: weekly`로 설정해
  빈도를 조절.
- `pip-audit`가 오탐(false positive, 실제로는 이 프로젝트 사용 패턴에 영향 없는 CVE)을
  낼 수 있음 — 완화책: `pip-audit`의 ignore 목록 기능으로 검토 후 예외 처리, 무조건
  CI 실패로 이어지지 않도록 초기엔 경고 모드로 도입 후 안정화되면 강제 실패로 전환하는
  단계적 적용을 고려.
