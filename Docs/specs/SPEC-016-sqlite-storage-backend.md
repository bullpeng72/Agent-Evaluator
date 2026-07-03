# SPEC-016: 영속성 저장소 옵션 — SQLite 백엔드 (JSON 파일 전용의 동시쓰기/규모 한계)

**Phase:** P4 · **상태:** Implemented (2026-07-03) · **의존성:** 없음

> **구현 노트**: 신규 패키지 `agent_evaluator/storage/`(`__init__.py` + `sqlite_backend.py`)를
> 신설했다. 원래 REQ-2가 제안한 "스칼라 필드는 컬럼, 나머지는 필드별 JSON 컬럼" 설계 대신,
> 구현 중 `TaskResult.to_dict()`/`TaskResult.from_dict()`(`core/trackers/base.py`)가 이미
> 전체 필드를 JSON-safe dict로 왕복 직렬화하는 기존 유틸리티임을 확인하고 이를 재사용하는
> 더 단순한 하이브리드 스키마로 정제했다 — 쿼리 가능성을 위한 최소 스칼라 컬럼
> (`task_id` PK, `task_type`, `success`, `timestamp`) + 전체 상태를 담는 단일 `data_json`
> 컬럼. `TaskResult`에 향후 필드가 추가돼도 스키마 자체를 바꿀 필요가 없다(REQ-2 달성,
> 더 낮은 유지비용으로). `save_tasks_to_db()`가 `INSERT ... ON CONFLICT(task_id) DO
> UPDATE`로 upsert하고(REQ-2), `_connect()`가 `PRAGMA journal_mode=WAL`을 설정한다(REQ-3).
> `schema_version` 테이블(REQ-4)이 버전 불일치 시 `RuntimeError`를 낸다(자동 마이그레이션은
> Non-Goals). `load_tasks_from_db()`가 `TaskResult.from_dict()`로 왕복 직렬화한다(REQ-5).
> stdlib `sqlite3`만 사용, 추가 pip 의존성 없음(REQ-6).
>
> `PerformanceMonitor(storage_backend: Literal["json", "sqlite"] = "json")` 신규 파라미터
> 추가 — 기본값 `"json"`은 기존 `save_to_file()` 동작과 100% 동일(REQ-1). `"sqlite"`면
> `save_to_file()`이 `.db` 확장자로 `storage.sqlite_backend.save_tasks_to_db()`를 호출하고
> 즉시 반환한다 — JSON 전용 직렬화·HTML 리포트 생성 경로는 타지 않는다(대시보드는 계속
> JSON 파일을 읽으므로, HTML 리포트를 `.db` 옆에 만들어도 대시보드가 참조하지 않아 무의미).
> 지원되지 않는 `storage_backend` 값은 `__init__`에서 즉시 `ValueError`.
>
> 신규 테스트 `tests/test_spec016_sqlite_storage_backend.py`(14건 — 왕복 직렬화, upsert
> 갱신/추가, `schema_version` 검증 및 불일치 에러, WAL 모드 실제 확인, 스레드 2개의 동시
> 쓰기가 전부 유실 없이 반영되는지 실제 동시성 테스트, `PerformanceMonitor` 통합 — 잘못된
> backend 값, json 기본값 무변경, sqlite 저장/증분 upsert). 기존
> `tests/test_flush_and_extras.py`(15건) 등 전체 스위트 무수정 통과. 전체 스위트 3,095
> passed, 1 skipped, 회귀 0건.
>
> **의도적으로 다루지 않은 것**: `serve/loader.py`가 `.db` 파일을 읽도록 배선하는 것(Non-Goals
> 그대로 유지 — 대시보드는 JSON 결과 파일만 스캔), 기존 JSON 파일의 SQLite 자동 마이그레이션.

## Context

- `agent_evaluator/core/trackers/monitor.py::save_to_file()`(`:4691-4869`)는 매 호출마다
  `self.tcr_tracker._tasks` **전체**를 스냅샷해(`:4722-4723`) 하나의 JSON 파일로 통째로
  직렬화한다. 원자적 쓰기(임시 파일에 쓴 뒤 `os.replace()`, `:4823-4836`)로 프로세스가
  쓰기 도중 죽어도 부분 손상 파일이 남지 않도록 보호하지만, 이는 **단일 writer의 크래시
  안전성**만 다룰 뿐 **여러 writer가 동시에 같은 파일을 대상으로 쓰는 상황**(예: 같은
  `output_dir`/`auto_save_filename`을 가리키는 여러 프로세스/`PerformanceMonitor` 인스턴스)은
  다루지 않는다 — 마지막에 `os.replace()`한 writer가 이전 writer의 데이터를 완전히 덮어쓴다
  (머지 없음, 프로세스 간 락 없음).
- `_task_count >= _STREAMING_THRESHOLD`(`monitor.py:98`, 기본 5000개)이면
  `_write_json_streaming()`(`:4829-4833`)으로 전환해 직렬화 문자열을 메모리에 한 번에
  들고 있지 않도록 최적화하지만, **파일 전체를 매번 처음부터 다시 쓰는 구조 자체는
  동일**하다 — 태스크가 100만 개 누적된 세션에서 `auto_save`가 10개 태스크마다
  (`_auto_save_interval` 기본값, `monitor.py:628`) 트리거될 때마다 100만 개 전체를
  다시 직렬화해 디스크에 쓴다(신규 태스크 10개만 추가하면 되는 상황에서도).
- `agent_evaluator/serve/loader.py::load_results()`(SPEC-013으로 mtime 기반 증분 캐싱은
  이미 적용됨, `:1299-`)는 이 JSON 파일들을 디렉토리 스캔으로 읽는 소비자 중 하나다 —
  이번 스펙은 **쓰기 쪽**(`save_to_file`) 한계를 다루며, 대시보드 읽기 쪽 성능은 SPEC-013이
  이미 별도로 처리했다(중복 스코프 아님, 직접 재확인).
- 이 프로젝트의 Architecture Principles(`CLAUDE.md`)는 "Layer independence — Layer 1/2는
  외부 의존성 없이 동작해야 한다"를 명시한다 — `sqlite3`는 Python stdlib이므로 이 원칙을
  위반하지 않고 대안 백엔드를 추가할 수 있는 유일한 실질적 선택지다(Postgres/MySQL 등은
  외부 서버·드라이버 의존성을 요구하므로 이 스펙의 범위 밖).
- `TaskResult`(`core/trackers/base.py:25-`)는 `frozen=True` 유사 불변 dataclass이며,
  `tokens_used`/`tool_calls`/`errors`/`agent_interactions`/`chain_steps`/`graph_traversal`/
  `conversation_turns`/`expected_tools`/`state_transitions`/`llm_judge`/`extra` 등 다수의
  중첩 dict/list 필드를 갖는다 — 관계형 스키마로 1:1 매핑하기보다, 스칼라 필드(task_id,
  task_type, success, completion_score, accuracy_score, execution_time, attempts, timestamp,
  framework, partial_reason, question, response, ground_truth, context)는 실제 컬럼으로,
  나머지 중첩 필드는 JSON TEXT 컬럼(`extra_json`, `tool_calls_json` 등)으로 저장하는
  하이브리드 스키마가 현실적이다.

## Goals

- 동일 `output_dir`을 대상으로 하는 다중 writer 상황에서 JSON 파일의 "마지막 쓰기가 이전
  것을 덮어쓰는" 문제 없이 태스크를 안전하게 누적할 수 있는 옵트인 대안을 제공한다.
- 매 저장마다 전체 히스토리를 재직렬화하는 대신, 신규/변경된 태스크만 증분 쓰기하는
  경로를 제공해 대규모(수십만~수백만 태스크) 장기 세션의 저장 비용을 낮춘다.

## Non-Goals

- Postgres/MySQL 등 외부 DB 서버 지원 — SQLite(stdlib, 파일 기반)만 다룬다.
- `serve/loader.py`(대시보드)가 SQLite를 기본/유일 소스로 읽도록 재작성 — 대시보드는
  계속 JSON 결과 파일을 읽는다(SPEC-013이 이미 그 경로를 최적화). 이번 스펙은 SQLite에서
  프로그래밍 방식으로 태스크를 다시 읽어오는 유틸리티 함수만 제공한다.
- 기존 JSON 결과 파일을 SQLite로 자동 마이그레이션하는 도구 — 이번 스펙 범위 밖(향후
  별도 스크립트로 다룰 수 있음).
- 기본 저장 방식 변경 — JSON 파일이 계속 기본값이며, 기존 사용자는 아무 변경 없이 동일하게 동작한다.

## Requirements

- **REQ-1**: `PerformanceMonitor(storage_backend: str = "json")` 생성자 파라미터를 추가한다.
  `"json"`(기본값)은 기존 `save_to_file()` 동작과 100% 동일. `"sqlite"`를 지정하면 REQ-2의
  경로를 사용한다. 다른 값은 `ValueError`.
- **REQ-2**: `storage_backend="sqlite"`일 때 `save_to_file()`이 `output_dir`/파일명 기준
  `.db` 확장자의 SQLite 파일에 태스크를 **`task_id` 기준 upsert**(INSERT ... ON CONFLICT
  task_id DO UPDATE)로 기록한다 — 이미 저장된 태스크는 스킵/갱신하고 신규 태스크만
  추가하므로, JSON 방식처럼 매번 전체를 재직렬화하지 않는다. 스키마는 Context에서 식별한
  스칼라 필드를 컬럼으로, 나머지 중첩 필드는 JSON TEXT 컬럼(`extra_json`,
  `tool_calls_json` 등)으로 저장한다.
- **REQ-3**: SQLite 연결은 `PRAGMA journal_mode=WAL`을 사용해 다중 프로세스가 동시에
  같은 `.db` 파일에 쓸 때 SQLite 자체의 파일 락으로 안전하게 직렬화되도록 한다(REQ-1의
  "여러 writer" Goal을 충족하는 핵심 메커니즘 — 애플리케이션 레벨 락을 새로 만들지 않고
  SQLite의 기존 동시성 제어를 그대로 활용).
- **REQ-4**: 신규 모듈 `agent_evaluator/storage/sqlite_backend.py`에 스키마 버전 테이블
  (`schema_version`)을 두어, 향후 스키마 변경 시 기존 `.db` 파일을 열었을 때 버전 불일치를
  감지하고 명확한 에러(자동 마이그레이션은 Non-Goals)를 내도록 한다.
- **REQ-5**: 같은 모듈에 읽기 헬퍼 `load_tasks_from_db(path: Path) -> List[TaskResult]`를
  제공해, 저장된 `.db` 파일에서 `TaskResult` 객체 리스트를 재구성할 수 있게 한다(분석
  스크립트 등에서 사용 — `serve/loader.py`에 배선하는 것은 Non-Goals).
- **REQ-6**: `storage_backend="sqlite"`는 추가 pip 의존성 없이 stdlib `sqlite3`만
  사용한다(Layer independence 원칙 준수).

## Interface

```python
# 변경 전
monitor = PerformanceMonitor(output_dir="results/")
monitor.save_to_file("run1.json")  # 매번 전체 재직렬화

# 변경 후 (하위호환 — storage_backend 기본값 "json"이면 기존과 동일)
monitor = PerformanceMonitor(output_dir="results/", storage_backend="sqlite")
monitor.save_to_file("run1")  # → results/run1.db, task_id 기준 upsert 증분 쓰기

from agent_evaluator.storage.sqlite_backend import load_tasks_from_db
tasks = load_tasks_from_db(Path("results/run1.db"))
```

## Acceptance

- `storage_backend="json"`(기본값, 미지정 포함)으로 생성한 `PerformanceMonitor`의
  `save_to_file()` 동작·출력 파일이 이번 변경 전후 byte-diff 동일한지 검증(하위호환 회귀 테스트).
- `storage_backend="sqlite"`로 태스크 100개를 기록 후 `save_to_file()` 호출 → `.db` 파일에
  100개 행이 존재하는지 확인.
- 동일 `task_id`로 두 번째 `save_to_file()` 호출(값이 달라진 동일 태스크 재기록) → 행 수는
  여전히 100개(중복 삽입 없음)이고 최신 값으로 갱신됐는지 확인.
- 두 개의 별도 `PerformanceMonitor` 프로세스(또는 스레드)가 같은 `.db` 파일에 서로 다른
  `task_id`로 동시에 `save_to_file()`을 호출해도 두 세트의 태스크가 모두 유실 없이
  저장되는지 확인(WAL 모드 동시쓰기 검증).
- `load_tasks_from_db()`로 읽은 `TaskResult` 리스트가 원본 기록 태스크와 필드 단위로
  동일한지 검증(왕복 직렬화 정합성).
- 지원되지 않는 `storage_backend` 값 지정 시 `ValueError` 발생 확인.

## Compatibility

- 기존 `PerformanceMonitor(...)` 호출(`storage_backend` 미지정)은 100% 동일하게 동작 —
  신규 옵트인 파라미터 추가일 뿐.
- `sqlite3`는 Python stdlib이므로 `pyproject.toml`의 extras 그룹 변경 불필요.

## Rollout

1. REQ-1/2/3: `storage/sqlite_backend.py` 신설 — 스키마 설계, upsert 쓰기, WAL 모드 설정.
2. REQ-4: 스키마 버전 테이블.
3. REQ-5: 읽기 헬퍼.
4. `PerformanceMonitor.__init__`/`save_to_file()`에 `storage_backend` 분기 배선.
5. 대용량(10만+ 태스크) 벤치마크로 JSON 전체재직렬화 대비 개선 폭을 문서화.

## Risks

- SQLite의 WAL 모드도 네트워크 파일시스템(NFS 등) 위에서는 락 보장이 약해질 수 있음 —
  로컬 디스크 사용을 전제로 문서에 명시.
- 스키마가 `TaskResult`의 필드 변경(신규 필드 추가 등)을 따라가지 못하면 JSON 백엔드와
  기능 격차가 생길 수 있음 — REQ-4의 스키마 버전 테이블로 최소한 "조용한 데이터 손실"은
  방지하고 명시적 에러로 전환.
- 이 스펙은 신규 저장소 백엔드를 추가하는 것으로, 다른 스펙들에 비해 스코프가 크다 —
  Rollout을 REQ 단위로 순차 구현하고, 각 단계마다 전체 테스트 스위트 회귀를 확인해
  기존 JSON 경로에 영향이 없음을 보장한다.
