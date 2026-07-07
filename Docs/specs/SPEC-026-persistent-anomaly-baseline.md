# SPEC-026: 영속 이상탐지 기준선 — SQLite 재수화 + 상시 스캔 + 알림 자동 연결

**Phase:** P8 (신규 기능 확장 — 운영 루프 "실행 품질 확인·드리프트·이상징후" 격차 해소) · **상태:** **Implemented — REQ-1~5 전체 완료(2026-07-06)** · **의존성:** SPEC-016(완료, `storage/sqlite_backend.py::load_tasks_from_db`를 재수화에 그대로 재사용) · SPEC-015(완료, `AlertEngine`의 재시도/백오프/쿨다운/알림폭풍 방지 인프라를 이상탐지 알림에도 재사용)

> **구현 노트 (REQ-4, 2026-07-06)**: `streaming/evaluator.py`의 `StreamingEvaluator`에
> `anomaly_alert_handler: Optional[Any] = None` 파라미터를 추가하고, `_maybe_scan_anomalies()`
> (REQ-2)가 스캔에 성공하면 곧바로 신규 `_maybe_dispatch_anomalies()`를 호출해
> `self.alert_handler.dispatch_anomaly_events(self._last_anomalies, handler=
> self.anomaly_alert_handler)`(REQ-3)로 이어지게 배선했다. `_last_anomalies`가
> 비어 있거나 `alert_handler`/`anomaly_alert_handler` 중 하나라도 없으면 아무것도
>하지 않는다 — 셋 다 설정해야만 실제 발송까지 이어지는 완전 옵트인 구조.
>
> **설계안 대비 명확화 1건**: 원 설계 문구("`handler=<기존에 등록된 기본 핸들러>`")는
> 그 핸들러가 어디서 오는지 구체화돼 있지 않았다. `AlertEngine`에 "기본 핸들러"
> 개념 자체가 없고(규칙마다 각자의 `handler`만 있음), REQ-3에서 이미 `handler`를
> 필수 인자로 구현해뒀으므로, `AlertEngine` API를 건드리지 않고 `StreamingEvaluator`
> 쪽에 명시적 생성자 파라미터(`anomaly_alert_handler`)를 추가하는 쪽을 택했다 —
> "어느 핸들러가 이상탐지 알림을 받는지"가 호출부에서 바로 보이는 것이 암묵적으로
> "첫 번째 규칙의 핸들러" 같은 걸 추론하는 것보다 안전하다고 판단했다.
>
> `tests/test_spec026_persistent_anomaly_baseline.py`에 `TestStreamingEvaluatorDispatchWiring`
> (8건) 추가 — 이상 없음/두 핸들러 중 하나라도 없음 시 미발송, 정상 발송(이벤트·핸들러
> 인자 검증), 발송 예외 무시, 실제 `AnomalyDetector`→실제 `AlertEngine`→`handler.send()`
> 까지 이어지는 end-to-end 통합(REQ-2→REQ-3→REQ-4), 이상 없을 때 미발송, 기본값
> `None` 확인. 기존 `test_streaming_evaluator.py`(29건)·`test_alerts_engine.py`(21건)·
> `test_anomaly_detector.py`(33건) 회귀 없음 확인. 전체 스위트 **3,388 passed, 1
> skipped, 회귀 0건**(기존 3,380 + 신규 8). 품질 래칫 순변화: mypy 0, ruff는 UP045 +1
> (같은 `__init__` 시그니처의 기존 `Optional[...]` 파라미터들과 동일한 스타일).
>
> **SPEC-026 전체 완료.** REQ-1(SQLite 재수화)→REQ-5(feedback_negativity 체크,
> Rollout 2순위로 먼저 완료)→REQ-2(StreamingEvaluator 주기적 스캔)→REQ-3
> (AlertEngine.dispatch_anomaly_events)→REQ-4(스캔→발송 배선)까지 5개 요구사항 모두
> 실제 테스트 통과와 품질 래칫 순증가 거의 0(sibling 스타일 일치를 위한 의도적
> 예외 몇 건 제외)을 확인하며 구현했다. 개발 루프(SPEC-025)에 이어, 운영 루프에서
> "인메모리 전용이라 재시작에 살아남지 못하던 이상탐지 기준선"이라는 격차도 해소됐다.

> **구현 노트 (REQ-3, 2026-07-06)**: `alerts/engine.py`에 `AlertEngine.dispatch_anomaly_events(
> events, handler, cooldown=300) -> List[AlertEvent]`를 추가했다. `AnomalyEvent.type`별로
> `AlertRule`을 캐시하는 `_get_or_create_anomaly_rule()`을 통해 기존 `AlertRule.is_on_cooldown()`/
> `mark_fired()`(쿨다운)와 기존 `_dispatch()`(SPEC-015 재시도-백오프)·`_should_suppress_for_storm()`
> (SPEC-015 알림폭풍 방지)를 그대로 재사용했다 — 새 쿨다운·재시도 로직 없음.
>
> **구현 중 발견해 회피한 위험 1건(설계안에 없던 내용)**: 최초 설계 그대로 캐시된
> `AlertRule`을 `self._rules`(`evaluate()`가 매 폴링마다 순회하는 리스트)에 추가했다면,
> 이 규칙의 `condition`이 "이미 트리거된 이벤트를 그대로 발송하기 위한 더미"라 항상
> `True`를 반환해야 하는데, 그러면 그 이후의 모든 `evaluate()` 호출에서 같은 이상탐지
> 알림이 조건 없이 재발화되는 버그가 생긴다. 이를 피하기 위해 별도의
> `self._anomaly_rules: Dict[str, AlertRule]` 캐시를 신설해 `self._rules`와 완전히
> 분리했다 — `get_rules()`에도 노출되지 않는다. 이 분리가 실제로 유효한지
> `test_does_not_trigger_via_evaluate`로 직접 확인했다(dispatch 후 `evaluate()`를
> 호출해도 재발화되지 않음).
>
> `tests/test_spec026_persistent_anomaly_baseline.py`에 `TestDispatchAnomalyEvents`
> (10건) 추가 — handler.send 호출, type별 독립 쿨다운, zero-cooldown 반복 발화,
> `self._rules`/`get_rules()` 오염 없음, `evaluate()`를 통한 재발화 없음(핵심
> 회귀 방지 테스트), 빈 이벤트 리스트, 히스토리 기록, 알림폭풍 억제 시에도 `fired`에는
> 남지만 `handler.send`는 억제됨(`evaluate()`와 동일한 기존 동작). 기존
> `test_alerts_engine.py`(21건)·`test_spec015_alert_retry_backoff.py`(13건) 회귀
> 없음 확인. 전체 스위트 **3,380 passed, 1 skipped, 회귀 0건**(기존 3,371 + 신규 9).
> 품질 래칫 순변화: mypy 0, ruff는 UP006 +4·UP037 +1 — 전부 이 파일의 기존 sibling
> 코드(`self._rules: List[AlertRule]`, `condition: Callable[["StreamingEvaluator"], bool]`
> 등)가 이미 쓰는 것과 동일한 스타일(E501/I001은 전부 해소).

> **구현 노트 (REQ-2, 2026-07-06)**: `streaming/evaluator.py`의 `StreamingEvaluator.__init__`에
> `anomaly_detector: Optional["AnomalyDetector"] = None`, `anomaly_scan_interval: int = 300`을
> 추가했다. 새 스레드를 만들지 않고 기존 `_flush_loop()`(`flush_interval`마다 도는 루프) 안에
> `_maybe_scan_anomalies()` 호출을 추가하는 형태로 구현했다 — `_maybe_scan_anomalies()`는
> `anomaly_detector`가 없으면 즉시 반환하고, 있으면 `time.time() - _last_anomaly_scan_time`이
> `anomaly_scan_interval` 이상일 때만 `anomaly_detector.scan(self.monitor)`을 호출해 결과를
> `self._last_anomalies`에 저장한다. 실제 스캔 간격은 `flush_interval`의 배수로 근사된다는
> 것을 docstring에 명시했다(예: flush_interval=60·anomaly_scan_interval=300이면 5회 flush마다
> 1회 스캔). 스캔 실패는(기존 `_flush()` 실패 처리와 동일한 관례로) 조용히 무시하고 **직전
> 스캔 결과를 그대로 유지**한다 — 실패했다고 유효했던 이전 결과를 빈 리스트로 지우지 않는다
> (설계안에 없던 세부 결정, 테스트로 고정). `start()` 시점을 기준선으로 `_last_anomaly_scan_time`을
> 설정해, 첫 스캔도 객체 생성 시점이 아니라 실제 가동 시점부터 `anomaly_scan_interval`을
> 온전히 기다리게 했다.
>
> `tests/test_spec026_persistent_anomaly_baseline.py`에 `TestStreamingEvaluatorAnomalyScan`
> (9건) 추가 — 기본값 `None`, 미설정 시 스킵, 간격 경과 시 실행, 미경과 시 스킵, 예외 발생 시
> 무시 + 직전 결과 유지, `start()`의 기준시각 설정, 실제 백그라운드 스레드(매우 짧은 간격 +
> 폴링)로 주기적 스캔이 실제로 트리거되는지 통합 확인, 실제 `AnomalyDetector`와의 통합.
> 기존 `test_streaming_evaluator.py`(29건)·`test_alerts_engine.py`(21건) 회귀 없음 확인.
> 전체 스위트 **3,371 passed, 1 skipped, 회귀 0건**(기존 3,362 + 신규 9). 품질 래칫
> 순변화: mypy 0, ruff는 UP006 +1·UP037 +2·UP045 +1 — 전부 이 `__init__` 시그니처의
> 기존 파라미터(`monitor: "PerformanceMonitor"`, `alert_handler: Optional["AlertEngine"]`)가
> 이미 쓰고 있는 것과 동일한 TYPE_CHECKING 따옴표 forward-ref 스타일을 그대로 따른 결과
> (같은 시그니처 안에서 신규 파라미터만 다른 문법을 쓰면 오히려 일관성이 깨짐).

> **구현 노트 (REQ-5, 2026-07-06)**: `anomaly/detector.py`에 `_get_feedback_negativity_rate()`
> + `_check_feedback_negativity()`를 추가하고 `scan()`의 6번째 체크로 등록했다.
> `monitor.feedback_tracker.feedbacks`(이미 자동 수집됨, `record_task()`가 `extra`의
> 피드백 신호를 감지할 때마다 채움)의 각 항목에 이미 계산돼 있는 `is_positive` bool을
> 그대로 신뢰해 부정 신호(`NEGATIVE_TYPES`의 여집합)를 판별한다 — `NEGATIVE_TYPES`
> 집합을 별도로 다시 import해 멤버십을 재확인하지 않는다(이미 저장 시점에 계산된
> 값을 재사용, 이중 판정 로직 없음). 판정 로직은 설계 그대로 `_check_error_surge`/
> `_get_error_rate`의 윈도우 구조(최근 `detection_window`개 vs 그 이전
> `baseline_window`개, 기준선 대비 2배 이상 + 절대 임계값 0.20 초과)를 그대로
> 복제했다 — 새 알고리즘을 만들지 않았다. `explain_event()`의 `_suggestions` dict에도
> `feedback_negativity` 항목을 추가했다.
>
> `monitor.feedback_tracker`가 없거나(`getattr` 기본값 `None`) 접근 중 예외가 나면
> (기존 4개 체크와 동일한 관례로) 조용히 `(0.0, 0.0)`으로 폴백한다 — `test_anomaly_detector.py`의
> 기존 `MagicMock` 기반 monitor 픽스처(bare `_make_monitor()`, `feedback_tracker` 미설정)로
> 회귀 테스트를 돌려 이 폴백이 실제로 크래시 없이 동작함을 직접 확인했다(기존 스위트
> 33건 그대로 통과).
>
> `tests/test_spec026_persistent_anomaly_baseline.py`에 `TestCheckFeedbackNegativity`
> (8건) 추가 — 무신호 시 무이상, 부정 급증 탐지, 낮은 부정율 무시, critical 심각도
> (>30%), `feedback_tracker` 부재 시 안전 폴백, 기존 `test_anomaly_detector.py`
> 스타일 bare `MagicMock`과의 호환성, `scan()`에 정상 등록됐는지, `explain_event()`에
> 제안 문구가 있는지. 전체 스위트 **3,362 passed, 1 skipped, 회귀 0건**(기존 3,354 +
> 신규 8). 품질 래칫 순변화: mypy 0, ruff는 UP006 +1·UP037 +2 — 둘 다 이
> 클래스의 기존 5개 체크 메서드 전부가 동일한 스타일(`List[AnomalyEvent]` 반환 타입,
> `monitor: "PerformanceMonitor"` 따옴표 forward-ref)을 쓰고 있어, 새 메서드 2개만
> 최신 문법으로 바꾸면 오히려 같은 클래스 안에서 스타일이 갈리는 쪽을 택하지 않고
> 기존 관례를 그대로 따랐다(E501은 전부 해소).

> **구현 노트 (REQ-1, 2026-07-06)**: `PerformanceMonitor.rehydrate_from_storage(path,
> limit=None) -> int`(`core/trackers/monitor.py`, `restore_from_snapshot()` 바로
> 뒤에 위치)를 추가했다. `storage.sqlite_backend.load_tasks_from_db()`(SPEC-016,
> 그대로 재사용)로 불러온 `TaskResult` 목록을 `self.record_task(task)` 루프로
> 재생한다 — 이미 존재하는 `load_from_file()`(JSON 복원 경로)의 "record_task 루프
> 재생" 패턴과 동일한 원칙.
>
> **구현 중 발견한 위험 1건(설계안에 없던 내용)**: `record_task()`는 LLM Judge·
> 할루시네이션 탐지·보안 메트릭 등 여러 자동 평가 트리거를 갖고 있는데
> (`self.enable_llm_judge`/`enable_hallucination_detection`/`enable_security_metrics`
> 조건부), 재수화 대상 `TaskResult`는 이미 원래 실행 시점에 채점이 끝난 상태다.
> 재수화 시점에 이 플래그들이 켜져 있으면 각 태스크가 **재평가**된다(LLM Judge라면
> 비용도 재발생) — 이미 `load_from_file()`에도 동일하게 존재하는 특성이라 이 REQ가
> 새로 만든 문제는 아니지만, 몰랐다면 재수화 자체가 예상외의 API 비용을 유발할 수
> 있어 docstring에 `Warning` 섹션으로 명시했다(재수화 전용 모니터는 이 플래그들을
> 꺼둔 채 생성할 것을 권장).
>
> `tests/test_spec026_persistent_anomaly_baseline.py`에 `TestRehydrateFromStorage`
> (6건) 추가 — 전체 재생, 빈 DB, `limit`(타임스탬프 오름차순 마지막 N개), 재수화
> 직후(신규 `record_task` 호출 전) `AnomalyDetector.scan()`이 이미 과거 데이터를
> 기준선으로 사용 가능함을 확인, `enable_llm_judge=False`(기본값)에서 기존
> `task.llm_judge` 값이 재평가 없이 보존됨을 확인, 재수화 후 신규 태스크 기록이
> 정상 누적됨을 확인. 전체 스위트 **3,354 passed, 1 skipped, 회귀 0건**(기존 3,348 +
> 신규 6). 품질 래칫 순변화 **0**.

## Context

- `AnomalyDetector.scan(monitor)`(`agent_evaluator/anomaly/detector.py:114-129`)의 5개 체크(`_check_latency_trend`/`_check_accuracy_drift`/`_check_token_spike`/`_check_error_surge`/`_check_security_pattern`)는 전부 `monitor.latency_tracker.latencies`/`monitor.accuracy_evaluator.evaluations`/`monitor.token_tracker.usage_log`/`monitor.tcr_tracker.tasks`(`detector.py:131-181`) 같은 **인메모리 리스트**만 읽는다.
- `PerformanceMonitor.__init__`은 SQLite/JSON에서 과거 이력을 자동으로 다시 불러오는 로직이 전혀 없다 — `grep -rn "load_tasks_from_db" agent_evaluator/`가 `storage/sqlite_backend.py`(정의부)와 `storage/__init__.py`(재노출)만 반환하고, `monitor.py`의 `__init__`이나 그 어떤 생성 경로에서도 호출되지 않는다. 즉 프로세스가 재시작되면(컨테이너 롤링 배포, 크래시, 오토스케일링) `baseline_window=100`/`detection_window=20`(`detector.py:106-112`)의 기준선이 **완전히 리셋**된다.
- `enable_anomaly_detection`(`monitor.py:257`)은 `save_to_file()` 호출 시점에 **1회**만 스캔한다(`monitor.py:4919-4926`) — 상시 감시가 아니라 "리포트를 저장하는 순간의 스냅숏"이라, 저장 주기가 길면 이상 탐지도 그만큼 늦다.
- `StreamingEvaluator`(`agent_evaluator/streaming/evaluator.py:79-`)는 이미 `PerformanceMonitor`를 감싸고(`:97`), `flush_interval`마다 도는 백그라운드 스레드(`start()`/`_flush_loop`, `:115-121`)와 `record()`마다 `self.alert_handler.evaluate(self)`를 호출하는 경로(`:157-161`)를 갖고 있다. 그런데 이 스레드가 도는 대상은 `AnomalyDetector`가 읽는 것과 전혀 다른 자료구조 — 자체 `StreamingRecord`(`success`/`execution_time`/`tokens_used`/`accuracy_score`만 있음, `:24-32`)를 담는 `SlidingWindow`(`:35-`)다. `AnomalyDetector`가 보는 정확도/토큰/보안 상세 데이터는 여기 없다 — 두 메커니즘이 완전히 분리된 두 섬이다.
- `AlertEngine.evaluate(evaluator)`(`agent_evaluator/alerts/engine.py:254-`)의 `AlertRule.condition`은 `Callable[["StreamingEvaluator"], bool]` 타입이고(`:88`), 트리거 시 기본 메시지 생성이 `evaluator.get_stats("5m")`을 무조건 호출한다(`engine.py:275` 부근) — `AlertEngine`은 `StreamingEvaluator` 모양의 객체만 받도록 설계돼 있어, `AnomalyDetector.scan(monitor)`이 반환하는 `AnomalyEvent` 목록을 그대로 넘길 수 없다. `AlertEvent`(`engine.py:57-72`)는 `rule_name`/`severity`/`message`/`value`만 있는 단순 dataclass라 변환 자체는 쉽지만, 이걸 이어주는 코드가 없다.
- `ImplicitFeedbackTracker`(`core/trackers/feedback.py`)는 `monitor.feedback_tracker`(`monitor.py:641-644`)로 이미 모든 `PerformanceMonitor`에 기본 부착돼 있고, `record_task()`가 `task.extra`에 피드백 신호가 있으면 자동으로 기록한다(`monitor.py:2097-2106`, 이미 배선되어 있음 — 신규 구현 불필요). 하지만 `AnomalyDetector.scan()`의 5개 체크 어디에도 이 트래커를 읽는 코드가 없다 — 사용자가 반복적으로 응답을 재생성/거부하는 강한 품질 저하 신호가 수집만 되고 판정에는 전혀 쓰이지 않는다.

## Goals

- 프로세스 재시작 이후에도 `AnomalyDetector`의 기준선이 과거 이력을 반영하도록, 기존 SQLite 백엔드(SPEC-016)에서 이력을 재수화하는 경로를 추가한다.
- 이미 존재하는 `StreamingEvaluator`의 주기적 flush 스레드에 `AnomalyDetector`를 연결해, "저장 시점 1회"가 아니라 "설정된 주기마다" 이상탐지가 돌게 한다.
- `AnomalyEvent`를 기존 `AlertEngine`(재시도/백오프/쿨다운/알림폭풍 방지, SPEC-015)을 거쳐 Slack/Webhook/Email로 자동 발송할 수 있는 다리를 놓는다.
- 이미 수집되고 있는 `ImplicitFeedbackTracker`의 부정 신호를 `AnomalyDetector`의 6번째 체크로 편입한다.

## Non-Goals

- 입력/트래픽 분포 드리프트(신규 질문 유형·도메인 이탈 등 classic data/concept drift) 탐지 — 이번 스펙의 5+1개 체크는 전부 출력/실행 지표(정확도·지연·토큰·에러·보안·피드백)이며, 입력 분포 자체를 보는 건 임베딩 등 신규 의존성이 필요한 별도 후속 스펙 범위로 남긴다.
- `PerformanceMonitor` 자체에 새 백그라운드 스레드를 추가하는 것 — 이미 존재하는 `StreamingEvaluator`의 flush 스레드(`evaluator.py:115-121`)를 재사용하며, `StreamingEvaluator`를 쓰지 않는 배치/오프라인 사용자는 기존과 동일하게 `save_to_file()` 시점 1회 스캔만 받는다(하위 호환, 변경 없음).
- `AlertEngine`/`AlertRule`의 기존 공개 API(`add_rule`, `evaluate(evaluator)` 시그니처) 변경 — 이번 스펙은 `AnomalyEvent`를 처리하는 **별도의 신규 메서드**를 추가할 뿐, 기존 스트리밍 알림 경로는 무수정.
- 재수화 시 SQLite 스키마 변경 — `load_tasks_from_db()`(SPEC-016)를 그대로 호출만 한다.

## Requirements

- **REQ-1**: `PerformanceMonitor`에 `rehydrate_from_storage(path: Union[str, Path], limit: Optional[int] = None) -> int` 메서드를 추가한다. 내부에서 `storage.sqlite_backend.load_tasks_from_db(path)`(SPEC-016, 기존 함수 그대로 재사용)로 `List[TaskResult]`를 불러온 뒤, (지정 시 최근 `limit`개로 자르고) 각 태스크를 `self.record_task(task)`로 재생(replay)한다 — 새 누적 로직을 만들지 않고 기존 `record_task()`가 모든 트래커(`tcr_tracker`/`latency_tracker`/`accuracy_evaluator`/`token_tracker`/`feedback_tracker`)에 일관되게 반영하는 경로를 그대로 재사용한다. 반환값은 실제로 재생된 태스크 수.
- **REQ-2**: `StreamingEvaluator.__init__`(`streaming/evaluator.py:95-`)에 `anomaly_detector: Optional["AnomalyDetector"] = None`, `anomaly_scan_interval: int = 300`(초) 파라미터를 추가한다. 지정되면 기존 `_flush_loop`(`:115-121`이 시작시키는 스레드)가 매 `anomaly_scan_interval`마다 `anomaly_detector.scan(self.monitor)`을 호출하고, 결과를 `self._last_anomalies: List[AnomalyEvent]`에 저장한다 — 새 스레드를 만들지 않고 기존 flush 스레드의 루프 안에 조건부 호출을 추가하는 형태.
- **REQ-3**: `AlertEngine`(`alerts/engine.py`)에 `dispatch_anomaly_events(events: List["AnomalyEvent"], handler: Any, cooldown: int = 300) -> List[AlertEvent]` 메서드를 추가한다. 각 `AnomalyEvent`를 `AlertEvent(rule_name=f"anomaly:{event.type}", severity=event.severity, message=event.detail, value=event.value)`로 변환하고, `event.type`별로 내부에 캐시된 `AlertRule`(없으면 최초 호출 시 생성)을 통해 기존 쿨다운(`AlertRule.is_on_cooldown()`/`mark_fired()`, `engine.py:96-102`)과 기존 재시도/백오프 디스패치 경로(SPEC-015 `_dispatch()`)를 그대로 재사용한다 — 새 쿨다운/재시도 로직을 만들지 않는다.
- **REQ-4**: `StreamingEvaluator`가 REQ-2의 주기적 스캔에서 얻은 `_last_anomalies`가 비어있지 않고 `self.alert_handler`가 설정돼 있으면, `self.alert_handler.dispatch_anomaly_events(self._last_anomalies, handler=<기존에 등록된 기본 핸들러>)`(REQ-3)를 자동 호출한다 — REQ-2/3을 실제로 이어 붙이는 배선.
- **REQ-5**: `AnomalyDetector.scan()`(`anomaly/detector.py:114-129`)에 `_check_feedback_negativity(monitor)` 체크를 6번째로 추가한다. `monitor.feedback_tracker.feedbacks`(이미 자동 수집됨, `monitor.py:2097-2106`)에서 최근 `detection_window`개 대비 부정 신호(`NEGATIVE_TYPES = {"regenerate", "thumbs_down", "abandon", "correction"}`, `feedback.py:15`) 비율을 계산해, 기존 `_check_error_surge`(`detector.py:251-263`)와 동일한 비율 기반 임계값 로직(baseline 대비 2배 이상 + 절대 임계값 초과)을 그대로 적용한 `AnomalyEvent(type="feedback_negativity", algorithm="ratio", ...)`를 반환한다.

## Interface

```python
# REQ-1 — 재시작 후 기준선 재수화 (프로세스 시작 시 1회)
monitor = PerformanceMonitor(output_dir="results/", enable_anomaly_detection=True)
n = monitor.rehydrate_from_storage("results/production_sessions.db", limit=500)
# n -> 재생된 과거 태스크 수 (예: 500). 이후 monitor.record_task(...)로 신규 트래픽 기록 시작.
```

```python
# REQ-2/3/4 — StreamingEvaluator에 상시 이상탐지 + 자동 알림 연결
from agent_evaluator.anomaly import AnomalyDetector
from agent_evaluator.alerts.engine import AlertEngine
from agent_evaluator.alerts.handlers import SlackHandler
from agent_evaluator.streaming import StreamingEvaluator

alert_engine = AlertEngine()
evaluator = StreamingEvaluator(
    monitor=monitor,
    alert_handler=alert_engine,
    anomaly_detector=AnomalyDetector(baseline_window=200, detection_window=20),
    anomaly_scan_interval=300,  # 5분마다 스캔
)
evaluator.start()
# 이후 evaluator.record(...)가 계속 들어오는 동안, 5분마다 백그라운드에서
# AnomalyDetector.scan(monitor) 실행 → 이상 발견 시 SlackHandler로 자동 발송
# (신규 쿨다운/재시도 로직 없이 기존 AlertEngine/SPEC-015 인프라 재사용)
```

```python
# REQ-5 — 신규 6번째 체크 (기존 5개와 동일한 scan() 호출로 자동 포함)
events = AnomalyDetector().scan(monitor)
# [..., AnomalyEvent(type="feedback_negativity", severity="warning",
#        detail="Negative feedback rate 35.0% (surge vs baseline 10.0%)", algorithm="ratio")]
```

## Acceptance

- **REQ-1**: SQLite DB에 100개 태스크가 저장돼 있을 때 `rehydrate_from_storage(path)` 호출 후 `monitor.tcr_tracker.tasks`의 길이가 100(또는 `limit` 지정 시 그 값)인지, `AnomalyDetector.scan(monitor)`이 재수화 직후 즉시 의미 있는 기준선(빈 리스트 아님)으로 동작하는지 확인. 빈 DB 경로에 대해서는 `n == 0`, 에러 없이 반환되는지 확인.
- **REQ-2**: `anomaly_detector`가 지정된 `StreamingEvaluator`를 `anomaly_scan_interval=1`(테스트용 짧은 값)로 실행했을 때, 1초 후 `_last_anomalies`가 갱신되는지 확인. `anomaly_detector=None`(기본값)일 때는 기존 `_flush_loop` 동작이 회귀 없이 그대로인지 확인.
- **REQ-3**: 인위적으로 만든 `AnomalyEvent` 2건(같은 `type` 1건 포함)을 `dispatch_anomaly_events()`에 넘겼을 때, 같은 `type`의 두 번째 이벤트가 쿨다운 내에서는 발송되지 않는지(기존 `AlertRule.is_on_cooldown()` 재사용 확인), 서로 다른 `type`은 각각 독립적으로 발송되는지 확인.
- **REQ-4**: REQ-2의 주기적 스캔이 이상을 발견했을 때 `alert_handler.dispatch_anomaly_events`가 정확히 그 이상 목록으로 호출되는지(mock으로 호출 인자 검증), 이상이 없을 때는 호출되지 않는지 확인.
- **REQ-5**: `feedback_tracker`에 부정 신호 비율이 baseline 대비 급증하도록 fixture를 구성했을 때 `feedback_negativity` 타입 이벤트가 반환되는지, 정상 범위에서는 반환되지 않는지 확인 — 기존 5개 체크가 회귀 없이 그대로 동작하는지(기존 테스트 스위트 통과)도 함께 확인.

## Compatibility

- REQ-1은 `PerformanceMonitor`에 대한 순수 additive 메서드 추가 — 호출하지 않으면 기존 동작(빈 상태로 시작)과 100% 동일.
- REQ-2/4는 `StreamingEvaluator.__init__`에 신규 옵트인 파라미터(`anomaly_detector=None`이 기본값)만 추가 — 기존 `StreamingEvaluator(monitor=..., flush_interval=...)` 호출은 무변경.
- REQ-3은 `AlertEngine`에 신규 메서드 추가 — 기존 `add_rule()`/`evaluate()` 시그니처·동작 무변경.
- REQ-5는 `AnomalyDetector.scan()`의 반환 리스트에 새 이벤트 타입이 **추가될 수 있을 뿐**(feedback_tracker가 없거나 신호가 없으면 기존과 동일하게 5개 이하) — 기존 5개 체크의 판정 로직·반환 형식은 무변경.

## Rollout

1. REQ-1(`rehydrate_from_storage`) — 가장 독립적, SPEC-016 함수 재사용만 하면 되므로 리스크 최저.
2. REQ-5(`feedback_negativity` 체크) — REQ-1/2/3과 독립적으로 병행 가능, `AnomalyDetector` 단일 파일 내부 변경.
3. REQ-2(`StreamingEvaluator` 주기적 스캔) — REQ-1 완료 후(재수화된 상태에서 스캔이 의미를 가지므로) 착수 권장.
4. REQ-3(`AlertEngine.dispatch_anomaly_events`) — REQ-2와 독립적으로 병행 가능.
5. REQ-4(둘을 잇는 배선) — REQ-2/3 모두 완료 후 마지막.

## Risks

- **재수화 중복 재생 위험**: `rehydrate_from_storage()`를 프로세스 수명 중 반복 호출하면(예: 재시작이 아닌데 실수로 다시 호출) 같은 태스크가 두 번 `record_task()`되어 통계가 왜곡될 수 있다 — 완화책: docstring에 "프로세스 시작 시 정확히 1회만 호출할 것"을 명시하고, 이번 스펙은 중복 호출 방지 가드(예: 재수화 여부 플래그)를 추가하지 않는다(사용 패턴 문서화로 충분하다고 판단 — 필요하면 별도 후속 REQ).
- **대용량 SQLite 재수화의 시작 지연**: `limit` 없이 매우 큰 DB를 재수화하면 프로세스 시작 시간이 길어질 수 있다 — 완화책: `limit` 파라미터 기본 권장값(예: `detection_window`+`baseline_window`에 여유를 더한 수준)을 문서에 예시로 제공, 자동 제한은 강제하지 않는다(호출자 책임).
- **`anomaly_scan_interval`이 `flush_interval`과 다른 주기로 설정될 때의 혼란**: 두 값이 독립적이라 사용자가 헷갈릴 수 있다 — 완화책: `StreamingEvaluator` docstring에 두 값의 관계와 기본값 차이(스트리밍 지표 flush vs 이상탐지 스캔)를 명시.
- **`dispatch_anomaly_events`의 동적 `AlertRule` 캐시 무한 증가**: `AnomalyEvent.type`은 5(+1)종으로 유한하므로 실질적 위험은 낮지만, 향후 체크가 계속 늘어나면 캐시도 늘어난다 — 완화책: 현재 유한한 타입 집합을 문서에 명시하고, 별도 정리 로직은 이번 스펙 범위 밖으로 둔다.
- **입력 분포 드리프트 미탐지는 이번 스펙으로 해소되지 않음**: Non-Goals에 명시한 대로, 이번 스펙의 6개 체크는 여전히 출력/실행 지표에 한정된다 — 완화책 없음(후속 스펙 범위로 명시적으로 이연).
