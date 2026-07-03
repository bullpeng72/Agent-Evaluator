# SPEC-015: 알림 핸들러 재시도/백오프 및 알림 폭풍 방지

**Phase:** P3 · **상태:** Implemented (2026-07-03) · **의존성:** 없음

> **구현 노트**: `alerts/engine.py`에 모듈 레벨 `_send_with_retry(handler, event,
> max_retries=3)`를 추가했다(REQ-1) — `LLMJudge._call_with_retry()`(SPEC-006)와 동일한
> 1s/2s/4s 백오프 패턴, rate-limit 구분 없이 모든 예외를 재시도 대상으로 취급(알림 핸들러엔
> rate-limit 전용 신호가 없어 구분할 근거가 없음). `AlertEngine`에 `_failed_send_count`/
> `_suppressed_count` 카운터와 `get_failed_send_count()`/`get_suppressed_count()`를
> 추가했다(REQ-2). 재시도 소진 시 `logger.warning()`으로 격상(기존 `debug`에서).
> `AlertEngine(async_dispatch=False)`(REQ-3, 기본값 유지 — 기존 `test_evaluate_calls_
> handler_send` 등 21개 기존 테스트 무수정 통과) — `True`이면 `_dispatch()`
> (재시도-백오프 포함)를 `threading.Thread(daemon=True)`로 백그라운드 디스패치해
> `evaluate()`가 네트워크 I/O를 기다리지 않는다. `rule.mark_fired()` 호출 시점은
> 그대로 유지(REQ-4 — 발송 성공/실패와 무관하게 발송 이전, 이미 장애 중인 핸들러에
> 재시도를 추가로 쌓지 않기 위함). `AlertEngine(max_alerts_per_window=None,
> window_seconds=60)`(REQ-5, 기본값 `None`=비활성) — 트레일링 윈도우 내 발송 상한
> 초과 시 `history.record(event)`(감사 이력)는 그대로 남기고 `handler.send()` 디스패치만
> 건너뛴다.
>
> 신규 테스트 `tests/test_spec015_alert_retry_backoff.py`(13건 — 재시도 성공/소진,
> 실패 카운터, `async_dispatch` 기본값 동기 유지 검증, `async_dispatch=True`에서
> `evaluate()`가 재시도 대기로 블로킹되지 않는지 실측(`time.monotonic()` 측정),
> `mark_fired()` 타이밍 불변, 알림 폭풍 억제 3종 시나리오). 기존
> `tests/test_alerts_engine.py`(21건) 무수정 통과. 전체 스위트 3,081 passed, 1 skipped,
> 회귀 0건.

## Context

- `agent_evaluator/alerts/handlers.py`의 3개 핸들러(`SlackHandler.send`(`:35-60`),
  `WebhookHandler.send`(`:79-91`), `EmailHandler.send`(`:116-129`))는 재시도/백오프/내부
  예외 처리가 전혀 없다 — `urllib.request.urlopen(req, timeout=10)`(Slack/Webhook)와
  `smtplib.SMTP(self.smtp_host, self.smtp_port)`(Email, **타임아웃 인자 자체가 없음**)이
  네트워크 오류·타임아웃 시 그대로 예외를 던진다(직접 코드 대조로 확인 — 3개 클래스 어디에도
  `try/except`가 없음).
- `agent_evaluator/alerts/engine.py::AlertEngine.evaluate()`(`:167-218`)는
  `rule.handler.send(event)`(`:213-216`) 호출을 `try/except Exception`으로 감싸 **모든
  실패를 `logger.debug()` 레벨로만 기록하고 조용히 무시**한다 — 재시도 없음, 운영자가
  알림 발송 실패 자체를 알 방법이 없음(debug 로그는 기본 설정에서 보이지 않음).
- `rule.mark_fired()`(`:211`)가 `handler.send()` 호출 **이전**에 실행된다 — 즉 전송이
  실패해도 규칙은 즉시 쿨다운(기본 300초, `AlertRule.cooldown`)에 들어간다. 일시적 네트워크
  장애 한 번으로 최대 5분간 해당 규칙의 알림이 재시도 기회 없이 완전히 유실된다.
- `AlertEngine.evaluate()`는 `agent_evaluator/streaming/evaluator.py::StreamingEvaluator.record()`
  (`:159-162`)에서 **태스크가 기록될 때마다 동기적으로 호출**된다. `SlackHandler`/
  `WebhookHandler.send()`는 최대 10초까지 블로킹될 수 있고, `EmailHandler.send()`는
  타임아웃 자체가 없어 SMTP 서버가 응답하지 않으면 무한정 블로킹될 수 있다 — 이 모든 것이
  에이전트의 태스크 처리 hot path(`record()`) 안에서 동기적으로 실행된다.
- 규칙(`AlertRule`)별 `cooldown`은 있지만, **규칙 간 전역 레이트리밋이 없다** — 하나의
  장애가 여러 규칙을 동시에 트리거하면(예: TCR 급락 + 지연 급증 + 오류율 급증이 같은
  근본 원인으로 동시 발생), 서로 다른 규칙 각각의 쿨다운만 통과하면 개별적으로 알림을
  보내 짧은 시간에 여러 건의 알림이 중복 발송될 수 있다("알림 폭풍").
- 이 코드베이스에 이미 존재하는 재시도/백오프 선례: `integrations/llm_judge.py::
  LLMJudge._call_with_retry()`(`:492-512`, SPEC-006) — rate-limit 오류 시 1초/2초/4초
  간격, `max_retries=3` 기본값. 일관성을 위해 이번 스펙도 동일한 패턴을 재사용한다.
- 기존 테스트 `tests/test_alerts_engine.py::test_evaluate_calls_handler_send`(`:160-165`)는
  `engine.evaluate(...)` 호출 직후 **동기적으로** `handler.send.assert_called_once()`를
  검증한다 — 알림 발송을 백그라운드 스레드로 옮기면 이 테스트가 레이스 컨디션으로 깨질 수
  있음을 미리 확인(직접 코드 대조).
- `handler.send(event)`를 직접 호출하는 곳은 `alerts/engine.py`가 유일하다(grep으로 확인
  — 사용자가 `SlackHandler`/`WebhookHandler`/`EmailHandler`를 직접 인스턴스화해 `AlertEngine`
  없이 `.send()`를 호출하는 코드는 리포지토리 내에 없음). `decorators.py`의
  `SimpleTaskAlertRule`(`:2896-`)은 핸들러 시그니처가 `(message, task_result) -> None`으로
  완전히 다른 별도 경로이며, `AlertRule.handler.send(event)`와 무관하다.

## Goals

- 일시적 전송 실패가 재시도 없이 규칙의 전체 쿨다운 기간(기본 5분) 동안 알림을 완전히
  유실시키지 않게 한다.
- 재시도를 모두 소진한 최종 실패는 운영자가 감지할 수 있는 레벨(warning)로 기록되고,
  카운트로 조회 가능해야 한다.
- 지연/장애 중인 알림 채널이 에이전트의 태스크 처리 hot path(`StreamingEvaluator.record()`)를
  블로킹하지 않는 방법을 제공한다(옵트인).
- 여러 규칙이 동시에 트리거되는 상황에서 전역 발송 건수를 제한할 수 있는 옵트인 스로틀을
  제공한다("알림 폭풍 방지").

## Non-Goals

- `SimpleTaskAlertRule`의 사용자 제공 핸들러 콜백(`(message, task_result) -> None`)에
  재시도를 추가하는 것 — 이 경로는 `AlertRule.handler.send(event)`와 별개의 인터페이스이며,
  재시도 책임은 사용자 콜백 자체에 있다.
- 실패한 알림을 영속 저장했다가 프로세스 재시작 후 재전송하는 dead-letter 큐 — 이번
  스펙은 프로세스 생존 중의 bounded in-memory 재시도만 다룬다.
- `AlertEngine`/`StreamingEvaluator` 전체를 `asyncio` 기반으로 재작성 — `record()`는
  동기 메서드로 유지되므로, REQ-3은 별도 스레드 디스패치로 해결하며 async/await 전환은
  다루지 않는다.
- `AlertRule.cooldown`의 규칙별 의미 변경 — REQ-5의 전역 스로틀은 기존 쿨다운 위에
  추가되는 레이어이며 대체가 아니다.

## Requirements

- **REQ-1**: `alerts/engine.py`에 공유 재시도 헬퍼(예: `_send_with_retry(handler, event,
  max_retries=3)`)를 추가해 `AlertEngine.evaluate()`의 `rule.handler.send(event)` 호출을
  감싼다. `LLMJudge._call_with_retry()`(SPEC-006)와 동일하게 1초/2초/4초 간격으로 최대
  `max_retries`회 재시도한다. `handlers.py`의 3개 `send()` 메서드 자체는 수정하지 않는다
  (재시도 정책은 `engine.py`에 집중, 핸들러는 단일 책임 유지).
- **REQ-2**: 재시도를 모두 소진해도 실패하면 `logger.warning()`(기존 `debug()`에서 격상)으로
  규칙 이름과 최종 예외를 기록하고, `AlertEngine`에 실패 횟수 카운터를 추가해 새 메서드
  (예: `get_failed_send_count() -> int`)로 조회 가능하게 한다.
- **REQ-3**: `AlertEngine(async_dispatch: bool = False)` 생성자 파라미터를 추가한다.
  기본값 `False`는 기존과 100% 동일한 동기 발송을 유지한다(REQ-1의 재시도-백오프는 적용되되,
  `evaluate()` 반환 전에 완료됨 — `test_evaluate_calls_handler_send` 등 기존 테스트 그대로
  통과). `True`이면 `_send_with_retry(...)` 호출을 `threading.Thread(daemon=True)`로
  백그라운드 디스패치해 `evaluate()`가 네트워크 I/O를 기다리지 않고 즉시 반환한다.
  `history.record(event)`는 두 모드 모두 기존과 동일하게 동기적으로 유지한다(로컬 파일
  I/O이므로 감사 이력은 즉시 일관성 유지).
- **REQ-4**: `rule.mark_fired()`의 호출 시점(전송 이전, 성공/실패와 무관)은 이번 스펙에서
  변경하지 않는다 — 이미 장애 중인 핸들러에 재시도 폭탄을 추가로 던지지 않기 위함(REQ-1의
  단일 `evaluate()` 호출 내 재시도로 일시적 장애는 커버, 지속적 장애는 기존처럼 쿨다운으로
  자연 감쇠).
- **REQ-5**: `AlertEngine(max_alerts_per_window: Optional[int] = None, window_seconds: int = 60)`
  파라미터를 추가한다. 기본값 `None`은 전역 스로틀 비활성(기존 동작과 100% 동일). 값이
  설정되면, 트레일링 윈도우 내 이미 디스패치된 알림 수가 한도에 도달했을 때 이후 발화된
  규칙은 `history.record(event)`(감사 이력)는 그대로 남기되 `handler.send()` 디스패치만
  건너뛰고, 억제된 횟수를 `get_suppressed_count() -> int`로 조회 가능하게 한다.
- **REQ-6**: REQ-1~5는 모두 기본값 기준 하위호환 — `AlertEngine()`을 인자 없이 생성하면
  실패 시 재시도(성공 케이스는 동작 변화 없음, 실패 케이스만 이전엔 즉시 포기 → 이제
  최대 ~7초 재시도 후 포기)만 추가되고, 비동기 디스패치·전역 스로틀은 명시적으로 켜야만
  동작이 바뀐다.

## Interface

```python
# 변경 전
engine = AlertEngine(history_dir=None)

# 변경 후 (하위호환 — 신규 파라미터 전부 기본값 유지 시 기존과 동일)
engine = AlertEngine(history_dir=None)  # REQ-1/2만 적용 (재시도 + 실패 카운터)
engine = AlertEngine(async_dispatch=True)  # REQ-3: hot path 논블로킹
engine = AlertEngine(max_alerts_per_window=10, window_seconds=60)  # REQ-5: 알림 폭풍 방지

engine.get_failed_send_count()  # 신규
engine.get_suppressed_count()   # 신규
```

## Acceptance

- 핸들러 `send()`가 첫 2회 실패 후 3회째 성공하도록 mock하면, `evaluate()`가 해당 알림을
  최종적으로 성공 처리하고(`get_failed_send_count()`가 증가하지 않음) 1초+2초 대기가
  발생했는지 확인(`time.sleep` mock으로 실제 대기 없이 호출 인자만 검증).
- 3회 모두 실패하면 `logger.warning()`이 호출되고 `get_failed_send_count()`가 1 증가하는지 확인.
- `async_dispatch=False`(기본)에서 `test_evaluate_calls_handler_send`가 무수정 통과하는지 회귀 검증.
- `async_dispatch=True`에서 `evaluate()` 호출이 (재시도 백오프 시간과 무관하게) 즉시 반환하고,
  이후 백그라운드 스레드에서 `handler.send()`가 호출되는지(스레드 join 후 mock 검증) 확인.
- `max_alerts_per_window=2`로 설정하고 짧은 시간 내 3개 서로 다른 규칙을 발화시키면, 처음
  2건만 `handler.send()`가 호출되고 3번째는 `history.record()`는 호출되지만 `send()`는
  호출되지 않으며 `get_suppressed_count() == 1`인지 확인.
- `max_alerts_per_window=None`(기본) 시 기존 `test_alerts_engine.py` 전체가 무수정 통과하는지 검증.

## Compatibility

- 기본 생성자(`AlertEngine()`, 인자 없음)는 성공 경로에서 동작 변화 없음. 실패 경로는
  "즉시 포기"에서 "최대 ~7초 재시도 후 포기"로 바뀌므로, 핸들러가 실제로 장애 중일 때
  `evaluate()`의 동기 호출 지연이 늘어날 수 있음(REQ-3으로 `async_dispatch=True`를 켜면
  이 지연이 hot path에서 제거됨) — CHANGELOG에 명시.
- `async_dispatch=True`를 사용하는 호출자는 `evaluate()` 반환 직후 `handler.send()`가
  아직 호출되지 않았을 수 있음을 인지해야 한다(테스트 작성 시 스레드 join 또는 polling 필요).

## Rollout

1. REQ-1/2: `engine.py`에 `_send_with_retry()` + 실패 카운터 추가 — 기본값 변경 없이도
   즉시 이득(재시도로 일시 장애 복원력 향상).
2. REQ-3: `async_dispatch` 옵트인 파라미터 + 백그라운드 스레드 디스패치.
3. REQ-5: `max_alerts_per_window`/`window_seconds` 옵트인 전역 스로틀.
4. `tests/test_alerts_engine.py`에 신규 테스트 클래스 추가, 기존 테스트는 무수정 유지 확인.

## Risks

- 재시도 로직이 핸들러의 성공을 오탐(예: Slack이 5xx를 반환했지만 실제로는 메시지가
  전달된 경우 — Slack Incoming Webhook은 이런 이중 전달을 유발할 수 있음)하면 동일 알림이
  중복 발송될 수 있음 — Slack/Webhook 응답 바디를 검증하지 않고 HTTP 예외 발생 여부만으로
  재시도 여부를 판단하므로, 이 스펙의 재시도는 "네트워크 계층 실패"만 다루고 "논리적
  중복 발송" 문제는 별도 스코프로 남긴다(멱등키 등은 Non-Goals).
- `async_dispatch=True`에서 데몬 스레드가 과도하게 누적될 가능성(짧은 시간에 매우 많은
  알림이 발화되는 극단적 상황) — 완화책: REQ-5의 전역 스로틀을 함께 사용하도록 문서에
  권장(두 옵션을 함께 켜는 것이 프로덕션 스트리밍 사용의 권장 조합).
