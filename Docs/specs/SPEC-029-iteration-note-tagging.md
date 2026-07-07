# SPEC-029: `iteration_note` — 로컬 반복 실험에 사람이 읽을 수 있는 메모 남기기 (AOO ADE 연동 트랙)

**Phase:** P9 (AOO ADE 연동 트랙 — SPEC-025/027/028이 완성한 버전 비교 파이프라인의 UX 보강) · **상태:** **Implemented — REQ-1~5 전체 완료(2026-07-07)** · **의존성:** SPEC-007(완료, `_build_lineage()` 재사용) · SPEC-025(완료, `ResultFile`/`compare_results(group_by=...)`/대시보드 Group by UI가 이번 스펙이 얹히는 기반) · SPEC-027(완료, `agent_version="auto"`가 만드는 dirty-hash 태그를 사람이 읽을 수 있게 보완하는 것이 이번 스펙의 동기)

> **구현 노트 (2026-07-07)**: 설계안 그대로 5개 REQ 전부 구현, 편차 없음.
> REQ-1/2: `PerformanceMonitor.__init__`에 `iteration_note: Optional[str] = None` 추가
> (`monitor.py:283-285`, `prompt_version`/`agent_version` 바로 옆) + `self._iteration_note`
> 저장(`:490`) + `_build_lineage()` 반환 dict에 `"iteration_note"` 키 추가(`:3016-3018`,
> `agent_version` 바로 다음). REQ-3: `ResultFile.iteration_note` 읽기 전용 프로퍼티를
> `agent_version` 프로퍼티(`serve/loader.py`) 바로 뒤에 동일 패턴으로 추가. REQ-4:
> `record_and_save()`가 `payload.get("iteration_note")`(기본값 `None`)를 읽어
> `PerformanceMonitor(..., iteration_note=...)`에 전달 + 모듈 docstring 입력 스키마
> 표에 항목 추가. REQ-5: `dashboard2.html.j2`의 File Compare "Metric Comparison" 표
> 헤더 바로 아래에 `agent_version`/`iteration_note` 메타데이터 행을 추가(`x-if`로 둘
> 다 없으면 행 자체를 숨김, `title` 속성으로 긴 메모는 hover 시 전체 표시) — 새 API
> 호출 없이 이미 로드된 `compareData`(원본 결과 JSON)의 `extra_metrics.lineage`에서
> 직접 읽는다. Jinja2 `Environment().get_template().render()`로 템플릿 파싱 자체가
> 깨지지 않았음을 직접 확인.
>
> 테스트 8건 추가: `test_lineage_capture.py`(`TestIterationNotePassthrough` 3건 —
> 단독 지정/agent_version과 병행/기본값 None) + `test_live_guardrail_report.py`
> (`TestIterationNotePassthrough` 2건 — payload passthrough/미지정 시 None) +
> 신규 `test_spec029_iteration_note.py`(`TestResultFileIterationNote` 3건 —
> agent_version과 함께 노출/구버전 파일에서 None/`extra_metrics` 키 자체가 없는
> raw dict에서도 에러 없이 None, SPEC-025 `TestResultFileVersionProperties`와
> 동일한 3-케이스 구조를 그대로 재사용). 전체 스위트 **3,440 passed, 1 skipped,
> 회귀 0건**(기존 3,432 + 신규 8). `TestLineageAlwaysPresent`의 기존 어설션에
> `assert lineage["iteration_note"] is None`을 추가해 "lineage는 항상 이 키를
> 포함한다"는 계약을 명시적으로 검증.
>
> 품질 래칫: ruff/mypy 신규 findings 확인 결과, `live_guardrail_report.py`의
> E501/UP006 4건과 `loader.py`의 mypy no-any-return 2건 전부 **내가 건드리지 않은
> 기존 줄**(`Dict[str, Any]` 타입힌트 등, 수정 전부터 있던 코드) 또는 **기존
> `agent_version` 프로퍼티가 이미 갖고 있던 것과 동일한 패턴**(같은 `no-any-return`
> 스타일을 그대로 복제)이라 순증가 0 — git diff로 정확한 라인 번호를 대조해 확인
> (대규모 미커밋 변경이 이미 트리에 쌓여 있어 `git stash`로 전체 비교하는 대신
> 라인 단위 대조로 검증).

## Context (설계 시점 — 위 구현 노트가 최신 상태)

## Context

- `agent_version="auto"`(SPEC-027)는 커밋 없이 반복 실행해도 iteration마다 `commit[:8]-dirty-{hash}` 형태로 자동 구분되는 태그를 만든다. 하지만 이 태그 자체는 **의미를 담지 않는 불투명한 해시**다 — 대시보드 File Compare 탭에서 `agent_version`으로 그룹핑해 여러 iteration을 나열해도, `a1b2c3d4-dirty-f3a91c`와 `a1b2c3d4-dirty-9e02b1` 중 어느 쪽이 "플랜 단계를 먼저 세우게 한 시도"였고 어느 쪽이 "예시를 3개로 늘린 시도"였는지 사람이 구분할 방법이 없다.
- `PerformanceMonitor.__init__`은 이미 `prompt_version`/`agent_version`(둘 다 `Optional[str] = None`)을 받아 `_build_lineage()`(`monitor.py:2987`)를 통해 `extra_metrics.lineage`에 그대로 노출하는 패턴이 있다(`monitor.py:484-485`, `:3008-3011`) — 사용자가 지정한 임의 문자열을 그대로 감사 메타데이터에 실어 보내는 구조가 이미 검증돼 있다.
- `ResultFile`(`serve/loader.py:203-215`)은 `prompt_version`/`agent_version` 프로퍼티를 `raw["extra_metrics"]["lineage"]`에서 읽기만 하는 얇은 접근자로 이미 두 개 구현해 뒀다 — 같은 패턴을 하나 더 추가하는 것은 새 파싱 로직이 필요 없다.
- 대시보드의 File Compare 비교 테이블(`dashboard2.html.j2` `compareData`)은 `group_by` API(`/api/compare?group_by=agent_version`)로 파일 목록만 추리고, 실제 렌더링은 각 파일의 `/api/results/{id}`(원본 JSON 그대로) 응답을 그대로 쓴다 — 즉 `extra_metrics.lineage`에 새 필드를 추가하기만 하면, 이미 프론트엔드가 그 원본 데이터를 전부 갖고 있으므로 **백엔드 API 재설계 없이 템플릿에 렌더링 행 하나만 추가**하면 노출할 수 있다.
- `live_guardrail_report.py`의 `record_and_save()`는 이미 `payload.get("agent_version", "auto")` 패턴으로 옵트인 필드를 읽어 `PerformanceMonitor` 생성자에 그대로 넘기는 구조이므로(`:93`, `:117`), 같은 자리에 `iteration_note`를 하나 더 읽어 넘기는 것으로 AOO 로컬 세션(OpenCode 플러그인)에서도 별도 배선 없이 즉시 쓸 수 있다.

## Goals

- 개발자가 로컬에서 프롬프트/설정을 반복 실험할 때, 각 iteration에 사람이 읽을 수 있는 한 줄 메모(예: `"플랜 단계를 먼저 세우게 지시문 추가"`)를 남길 수 있게 한다 — 커밋 메시지를 쓸 필요 없이(SPEC-027의 "커밋 없이 반복" 전제를 유지).
- 대시보드 File Compare 탭에서 `agent_version`으로 그룹핑한 여러 iteration을 나열할 때, 해시값 옆에 이 메모가 함께 보이게 해 "어떤 시도가 무엇을 바꾼 것인지" 데이터 기반 판단 속도를 높인다.
- 기존 `prompt_version`/`agent_version` 패턴(생성자 파라미터 → `_build_lineage()` → `ResultFile` 프로퍼티)을 그대로 재사용한다 — 새 저장 메커니즘·새 스키마 마이그레이션을 만들지 않는다.

## Non-Goals

- 여러 태스크가 서로 다른 `iteration_note`를 갖는 것 — `agent_version`과 마찬가지로 이 값은 `PerformanceMonitor` 인스턴스(≈ 결과 파일) 단위의 lineage 메타데이터다. 태스크마다 다른 메모가 필요하면 `TaskResult.extra`에 개별적으로 담는 것은 이 스펙 범위 밖(호출자가 원하면 이미 가능).
- 메모의 이력 관리(같은 `agent_version`으로 여러 번 저장되며 메모가 바뀐 경우, 이전 메모를 보존하는 것) — `_latest_file_ids_by_group()`이 이미 그룹당 최신 파일 1개만 선택하는 기존 동작을 그대로 따른다. 최신 메모만 보인다.
- `compare_results()`의 회귀/개선 판정 로직에 `iteration_note`를 반영하는 것 — 이 필드는 순수 표시용 메타데이터이지, 점수 계산에 관여하지 않는다.
- CLI에서 `iteration_note`를 직접 입력받는 새 플래그 — 이번 스펙은 `PerformanceMonitor` 생성자와 `record_and_save()` 페이로드 레벨만 다룬다.

## Requirements

- **REQ-1**: `PerformanceMonitor.__init__`에 `iteration_note: Optional[str] = None` 파라미터를 추가한다(`prompt_version`/`agent_version` 바로 옆, `monitor.py:281` 부근). `self._iteration_note = iteration_note`로 저장한다.
- **REQ-2**: `_build_lineage()`(`monitor.py:2987`)가 반환하는 dict에 `"iteration_note": self._iteration_note`를 추가한다(`agent_version` 키 바로 다음) — 새 계산 로직 없이 그대로 실어 보낸다.
- **REQ-3**: `ResultFile`(`serve/loader.py`)에 읽기 전용 프로퍼티 `iteration_note`를 추가한다 — `agent_version` 프로퍼티(`:211-215`)와 동일한 패턴으로 `extra_metrics.lineage.iteration_note`를 읽는다. 필드가 없는 구버전 결과 파일에서는 `None`(에러 아님).
- **REQ-4**: `live_guardrail_report.py`의 `record_and_save()`가 `payload.get("iteration_note")`(기본값 `None`)를 읽어 `PerformanceMonitor(..., iteration_note=...)`에 그대로 전달한다. 모듈 docstring의 입력 스키마 표에 `"iteration_note": str | null` 항목을 추가한다.
- **REQ-5**: 대시보드 File Compare 비교 테이블(`dashboard2.html.j2`)에 `agent_version`/`iteration_note`를 보여주는 메타데이터 행을 추가한다 — 위치는 기존 "Metric Comparison" 표 헤더(`d.name||d.id`) 바로 아래, 지표 행들 위. `iteration_note`가 없으면 `—`로 표시한다. 새 API 호출을 추가하지 않는다(이미 로드된 `compareData`의 `extra_metrics.lineage`에서 직접 읽는다).

## Interface

```python
# REQ-1/2 — 생성자에서 메모 지정
monitor = PerformanceMonitor(
    output_dir="results/",
    agent_version="auto",
    iteration_note="플랜 단계를 먼저 세우게 지시문 추가",
)
# monitor.generate_report().to_dict()["extra_metrics"]["lineage"]["iteration_note"]
# -> "플랜 단계를 먼저 세우게 지시문 추가"
```

```python
# REQ-4 — record_and_save() 페이로드에서 옵트인
record_and_save({
    "task_id": "session-1",
    "extra": guardrail.to_task_extra(),
    "iteration_note": "루프 탐지 threshold를 6으로 완화",
    # agent_version 미지정 시 기존과 동일하게 "auto" 기본값
})
```

```python
# REQ-3 — 대시보드/API 소비 측
rf.iteration_note  # -> "플랜 단계를 먼저 세우게 지시문 추가" | None
```

## Acceptance

- **REQ-1/2**: `PerformanceMonitor(iteration_note="foo")`로 생성 후 `generate_report().to_dict()["extra_metrics"]["lineage"]["iteration_note"] == "foo"`. `iteration_note` 미지정(기본값 `None`) 시 같은 키가 `None`인지(회귀 없음 — 기존 `_build_lineage()` 반환 dict에 새 키가 하나 늘었을 뿐 다른 키는 전혀 안 바뀌는지).
- **REQ-3**: `iteration_note`가 있는 결과 파일을 로드했을 때 `ResultFile.iteration_note`가 그 값을 정확히 반환하는지. `extra_metrics.lineage`에 그 키가 아예 없는(이번 스펙 이전에 저장된) 구버전 결과 파일에서 `None`을 반환하고 예외를 던지지 않는지.
- **REQ-4**: `record_and_save({"task_id": ..., "extra": ..., "iteration_note": "foo"})` 호출 후 저장된 파일의 lineage에 `"foo"`가 그대로 들어있는지. `iteration_note` 키를 아예 안 준 페이로드(기존 모든 호출부 포함)가 이전과 동일하게 동작하는지(`None`으로 떨어져 기존 동작과 구분 불가).
- **회귀 없음**: `iteration_note`를 전혀 쓰지 않는 기존 `PerformanceMonitor`/`record_and_save()` 사용 코드가 이번 변경 이전과 완전히 동일하게 동작하는지 — 기존 SPEC-007/025/027/028 테스트 스위트 전체가 무수정으로 통과하는지 확인.

## Compatibility

- 100% additive — `iteration_note`는 새 옵트인 파라미터/키일 뿐, 기존 `prompt_version`/`agent_version`/그 외 어떤 파라미터의 기본값·의미도 바꾸지 않는다.
- SPEC-025가 완성한 `compare_results(group_by=...)`/대시보드 Group by 드롭다운/`⚖️ Pairwise Judge`/`📄 Export HTML` 파이프라인은 전혀 수정하지 않는다 — REQ-5의 템플릿 변경은 순수 표시 추가이며 기존 비교 로직(delta·regression_tasks·pairwise)에는 관여하지 않는다.
- 구버전 결과 파일(이 필드가 없는 `extra_metrics.lineage`)을 읽어도 `ResultFile.iteration_note`가 `None`으로 안전하게 떨어지므로 하위 호환이 100% 유지된다.

## Rollout

1. REQ-1/2(`PerformanceMonitor` 생성자 + `_build_lineage()`) — 가장 작고 독립적, 다른 REQ의 전제.
2. REQ-3(`ResultFile` 프로퍼티) — REQ-2가 만든 lineage 키를 읽기만 함, 즉시 병행 가능.
3. REQ-4(`record_and_save()` 연결) — REQ-1에 의존, AOO 로컬 세션에서 실사용 가능해지는 지점.
4. REQ-5(대시보드 렌더링) — REQ-3에 의존, 이번 스펙의 최종 가치(사람이 실제로 보는 지점)가 드러나는 단계.

## Risks

- **메모 없이 저장된 iteration과의 혼동**: `iteration_note=None`인 파일이 섞여 있으면 비교 테이블에 `—`가 나열돼 여전히 해시만으로 구분해야 하는 iteration이 남는다 — 완화책: SDK가 강제할 수 없는 부분이므로, Ch28 §28.7(TDD-AI 스타일 A/B 검증)에 "iteration_note를 습관적으로 남기라"는 개발자 TIP을 추가해 문서 차원에서 유도한다.
- **긴 메모의 UI 잘림**: 비교 테이블 셀 폭이 좁아 긴 메모가 잘릴 수 있다 — 완화책: REQ-5 렌더링에 `title` 속성(hover 시 전체 텍스트 표시)을 함께 넣는다.
- **`iteration_note`에 민감 정보 기입**: 자유 텍스트 필드이므로 개발자가 실수로 비밀값 등을 적을 위험은 이론적으로 존재한다 — 다른 lineage 필드(`git_commit`, `sdk_version`)와 동일한 신뢰 수준으로 취급하고, `enable_pii_redaction`의 마스킹 대상 확장은 이번 스펙 범위 밖(별도 검토 필요 시 후속 스펙).
