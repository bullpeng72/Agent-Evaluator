# SPEC-013: 대시보드 로더 증분 캐싱 (watch 모드 요청당 전량 재파싱 제거)

**Phase:** P2 · **상태:** Implemented (2026-07-02) · **의존성:** 없음

> **구현 노트**: `ResultFile`에 `mtime: float = 0.0` 필드 추가, `parse_file()`이 파싱 시점에
> `path.stat().st_mtime`을 기록(REQ-1). `load_results(results_dir, previous=None)`으로 확장 —
> `previous`가 주어지면 `{path: ResultFile}` 캐시를 구성해 mtime이 동일한 파일은 `parse_file()`을
> 건너뛰고 캐시된 객체를 그대로(identity 재사용) 반환한다(REQ-2). `routers/data.py::list_results()`
> 의 watch-모드 무조건 재로드와 `server.py::reload_results()`(FileWatcher 콜백)를 각각
> `previous=`기존 `result_set` 전달 방식으로 전환(REQ-3/4). `previous` 생략 시 동작 100% 동일
> 확인(REQ-5). 신규 테스트 `tests/test_spec013_loader_incremental_cache.py`(10건 — mtime 기록,
> 무변경 시 재파싱 0회, 1개 수정 시 재파싱 정확히 1회, 신규 파일만 파싱, 삭제 파일 제외, 캐시
> 객체 identity 재사용, `reload_results()`의 `previous=` 전달 검증, `TestClient`로 실제
> `GET /api/results` 연속 2회 호출 시 두 번째 호출에서 `parse_file` 미호출 확인 — 이 통합
> 테스트가 Non-Goals에서 지적한 "응답 페이지네이션과 로딩 비용은 별개"라는 구분을 실제로
> 검증한다). 기존 `tests/test_loader_parsers.py`(14건)·`tests/test_serve_routers.py`(다수)·
> `tests/test_dashboard_auth.py`(12건) 무수정 통과. 전체 스위트 3,056 passed, 1 skipped,
> 회귀 0건. Rollout 4번(대용량 디렉토리 수동 벤치마크)은 진행하지 않음 — 정확성 검증(캐시가
> 실제로 재파싱을 스킵하는지)은 위 테스트로 충분히 확인됐고, 정량적 벤치마크는 실사용 환경에서
> 별도로 측정 권장.

## Context

- `agent_evaluator/serve/loader.py::load_results()`(`:1288-1314`)는 `results_dir.rglob("*.json")`
  (`:1295`)로 전체 디렉토리를 스캔하고, 매칭되는 모든 파일에 대해 `parse_file()`(`:1198-1259`)을
  호출한다. `parse_file()`은 JSON을 다시 읽어(`path.read_text()`) 파싱하고 `_parse_advanced`/
  `_parse_harness_data`/`_parse_tasks`/`_parse_security_l1`/`_parse_security_l2`/`_parse_agentic`/
  `_parse_quality_detail`/`_parse_hallucination_detail`/`_parse_llm_judge`/
  `_parse_conversation_sessions`/`_parse_feedback_data`/`_parse_anomaly_data`/`_parse_cost_data`/
  `_parse_streaming_data` 등 10개 이상의 하위 파서를 거쳐 `ResultFile` 데이터클래스를 새로 구성한다
  — 파일 하나당 결코 가볍지 않은 연산이며, 캐싱 없이 매번 처음부터 다시 수행된다.
- `agent_evaluator/serve/server.py::create_app()`(`:231`)은 앱 시작 시 `load_results()`를 한 번
  호출해 `app.state.result_set`에 캐싱하고, `watch=True`일 때만 `FileWatcher`가 변경을 감지하면
  `reload_results(app)`(`:159-161`)를 통해 재로드한다 — 여기까지는 합리적인 캐싱이다.
- 그러나 `agent_evaluator/serve/routers/data.py::list_results()`(`:176-208`)는 **watch 모드일 때
  마다 매 HTTP 요청 시점에 `load_results()`를 다시 통째로 호출**한다(`:203-208`, 주석: "watch
  모드: 항상 디스크에서 직접 읽어 최신 파일 목록 보장"). 대시보드는 보통 폴링(2~5초 간격) 또는
  사용자 인터랙션으로 이 엔드포인트를 자주 호출하므로, `watch=True`(기본 대시보드 실행 옵션)로
  띄운 상태에서는 **결과 디렉토리의 모든 JSON 파일이 요청마다 다시 통째로 재파싱**된다 — 응답
  자체는 `page`/`limit` 쿼리 파라미터로 페이지네이션되지만(`:178-179`), 그 페이지네이션은
  이미 전량 로드된 리스트에 대한 사후 슬라이싱일 뿐 로딩 비용 자체를 줄이지 않는다(직접 코드
  대조로 확인 — 백로그 제목의 "페이지네이션"이 실제로 가리켜야 할 문제는 응답 페이지네이션이
  아니라 **로더의 무조건 전량 재파싱**이다).
- 별도로 `agent_evaluator/serve/watcher.py::FileWatcher._snapshot()`(`:58-66`)도 `poll_interval`
  (기본 2.0초, `:20`)마다 자체적으로 `rglob("*.json")` + `stat()`을 수행해 변경 감지용 mtime
  스냅샷을 만든다 — 이쪽은 `stat()`만 하므로(JSON 파싱 없음) 상대적으로 저렴하지만, 결과
  디렉토리 파일 수가 매우 많아지면(수천 개) 이마저도 2초마다 누적되는 I/O 비용이다.
- `ResultFile`(`:137-160`)에는 파일의 mtime을 담는 필드가 없다 — 캐시 유효성 판단에 필요한
  정보가 현재 데이터 모델에 없다.

## Goals

- watch 모드에서 대시보드 API 요청이 **변경되지 않은 파일까지 매번 재파싱**하는 것을 없앤다 —
  변경이 없으면 이전에 파싱된 `ResultFile`을 재사용한다.
- 정말 새로 생기거나 수정된 파일만 `parse_file()`을 호출하도록 증분 로딩으로 전환한다.

## Non-Goals

- `routers/data.py::list_results()`의 기존 응답 페이지네이션(`page`/`limit`/`sort_by`/필터
  쿼리 파라미터) 로직 변경 — 이미 잘 동작하며 이번 스펙과 무관하다.
- `FileWatcher`의 폴링 방식 자체를 `watchdog` 전용으로 전환하는 등의 감시 메커니즘 교체 —
  이번 스펙은 로더의 재파싱 비용만 다룬다.
- 결과 파일 수가 극단적으로 많은 경우(수십만 개)를 위한 별도 인덱스 DB 도입 — 이는 백로그의
  "영속성 DB 백엔드 옵션" 항목과 겹치는 훨씬 큰 스코프이므로 분리한다.

## Requirements

- **REQ-1**: `ResultFile`에 `mtime: float` 필드를 추가하고, `parse_file()`이 파싱 시점에
  `path.stat().st_mtime`을 기록한다.
- **REQ-2**: `load_results(results_dir, previous: Optional[ResultSet] = None)`로 확장한다.
  `previous`가 주어지면 `{path: ResultFile}` 캐시를 구성해, 각 발견된 파일에 대해 캐시에 동일
  경로가 있고 현재 `path.stat().st_mtime`이 캐시된 `ResultFile.mtime`과 같으면 `parse_file()`을
  건너뛰고 캐시된 `ResultFile`을 재사용한다. 캐시에 없거나 mtime이 다르면(신규/수정) 새로 파싱한다.
  삭제된 파일(캐시에는 있으나 더 이상 디스크에 없는 경로)은 자연스럽게 결과에서 제외된다(현재
  rglob 기반 순회가 이미 이 성질을 보장하므로 추가 처리 불필요).
- **REQ-3**: `routers/data.py::list_results()`의 watch-모드 무조건 재로드(`:203-208`)를
  `load_results(results_dir, previous=request.app.state.result_set)`로 교체한다 — "매 요청마다
  통째로" 재파싱하던 것을 "매 요청마다 변경분만" 재파싱하는 것으로 전환한다(요청마다 최신
  파일 목록을 보장해야 한다는 기존 의도는 유지 — `rglob` 자체는 여전히 매 요청 수행되지만,
  비용이 큰 `parse_file()` 호출만 스킵 대상이 된다).
- **REQ-4**: `server.py::reload_results()`(`FileWatcher`의 변경 감지 콜백)도
  `load_results(app.state.results_dir, previous=app.state.result_set)`로 전환해 동일한
  증분 이득을 얻는다.
- **REQ-5**: `previous` 생략 시(기본값 `None`) 기존 동작과 100% 동일 — 모든 파일을 처음부터
  파싱한다(하위호환, 앱 최초 기동 시 사용되는 경로).

## Interface

```python
# 변경 전
def load_results(results_dir: Path) -> ResultSet: ...

# 변경 후 (하위호환 — previous 생략 시 기존과 동일)
def load_results(results_dir: Path, previous: Optional[ResultSet] = None) -> ResultSet: ...
```

```python
# routers/data.py::list_results() 변경 전
if getattr(request.app.state, "watcher", None) is not None:
    request.app.state.result_set = load_results(request.app.state.results_dir)

# 변경 후
if getattr(request.app.state, "watcher", None) is not None:
    request.app.state.result_set = load_results(
        request.app.state.results_dir, previous=request.app.state.result_set,
    )
```

## Acceptance

- 파일 100개 픽스처 디렉토리에서 두 번째 `load_results(dir, previous=result_set)` 호출 시,
  파일 내용이 전혀 바뀌지 않았다면 `parse_file()` 호출 횟수가 0회여야 한다(mock/spy로 검증).
- 파일 100개 중 1개만 수정(mtime 변경)한 뒤 재호출하면 `parse_file()`이 정확히 1회만
  호출되어야 한다.
- 새 파일 1개 추가 시 해당 파일만 파싱되고 나머지 99개는 캐시에서 재사용되는지 검증.
- 파일 1개 삭제 시 결과 `ResultSet.files`에서 해당 파일이 제외되는지 검증.
- `previous` 생략 시 기존 `load_results()` 테스트(있다면) 전량 무수정 통과 — 회귀 없음.
- watch 모드 대시보드 통합 테스트: 연속 2회 `GET /api/results` 호출 사이에 파일 변경이 없으면
  두 번째 호출에서 `parse_file`이 호출되지 않는지 확인(`unittest.mock.patch`로 spy).

## Compatibility

- `ResultFile`에 새 필드(`mtime`) 추가 — 데이터클래스 필드 추가이므로 기존 코드가 `ResultFile(...)`을
  위치 인자로 전체 생성하는 경우가 아니라면(현재 `parse_file()` 내부에서만 키워드 인자로 생성,
  직접 확인) 하위호환 유지.
- `load_results()`/`reload_results()`는 신규 선택 인자 추가이므로 호출부 수정 없이 그대로 동작.

## Rollout

1. REQ-1: `ResultFile`에 `mtime` 필드, `parse_file()`에 기록 로직 추가.
2. REQ-2: `load_results()`에 `previous` 기반 캐시 재사용 로직 추가.
3. REQ-3/4: `routers/data.py`/`server.py`의 호출부를 `previous=` 전달 방식으로 교체.
4. 대용량(수천 개) 결과 디렉토리로 수동 벤치마크(재파싱 스킵 전/후 응답 시간 비교)를 진행해
   개선 폭을 문서화.

## Risks

- 파일 내용이 변경됐는데 파일시스템이 mtime을 갱신하지 않는 극단적 케이스(일부 네트워크
  파일시스템, 클록 정밀도 이슈)에서는 캐시가 stale한 `ResultFile`을 반환할 수 있음 — 완화책:
  이 스펙의 캐시는 "최적화"일 뿐 정확성 보장 메커니즘이 아니므로, 사용자가 명시적으로 새로고침할
  수 있는 기존 수동 리로드 경로(있다면)를 유지하고 문서에 이 제약을 명시한다.
- `previous.files`가 매우 큰 경우 `{path: ResultFile}` 캐시 dict 구성 자체가 매 요청마다
  O(n) 비용 — 그러나 이는 `parse_file()`의 전체 JSON 파싱+다중 하위 파서 비용에 비해 훨씬
  저렴하므로(단순 dict 구성) 순이익이 명확하다.
