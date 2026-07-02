# SPEC-006: LLM Judge 동시성 및 백오프

**Phase:** P2 · **상태:** Implemented (2026-07-02) · **의존성:** 없음 (SPEC-001 완료 후 진행 권장 — 우선순위상)

> **구현 노트**: `llm_judge.py`에 `LLMJudge.__init__(max_concurrent_judge_calls=5, max_retries=3)` 파라미터를 추가하고, `ajudge()`가 실행 중인 이벤트 루프에 lazy 바인딩되는 `asyncio.Semaphore`(`_get_semaphore()`)로 감싸이도록 배선(REQ-1). `_call_claude`/`_call_openai`의 실제 provider 호출을 `_call_with_retry()`로 감싸 rate-limit(429) 예외 시 1s/2s/4s 지수 백오프로 최대 `max_retries`회 재시도하고, 소진 시 기존과 동일한 catch-all 예외 처리 경로로 재전파(REQ-2). rate-limit 판별은 `_is_rate_limit_error()`가 Anthropic/OpenAI SDK의 `RateLimitError` isinstance 체크를 우선하고, SDK 미설치·mock 예외 대응으로 `status_code==429` 및 클래스명 `"ratelimiterror"` 포함 여부를 폴백으로 사용(Risks 대응). `decorators.py`의 `_build_and_record()`에 `use_async_judge`/`async_judge_targets` 파라미터를 추가해, `@agent_eval`의 `async_wrapper`에서는 이 호출에 한해 monitor(s)의 `enable_llm_judge`를 일시 억제(동기 `judge()` 호출 방지)하고 대신 신규 공용 헬퍼 `_process_async_judge_targets()`가 `await ajudge()`로 채점 후 기록된 task를 tracker 리스트에서 in-place로 갱신(REQ-3; 동기 경로는 무변경 — 회귀 테스트로 스코어링 동등성 확인). `batch_eval`에 옵트인 파라미터 `concurrent_judge=False`(기본값)를 추가해 `True`일 때만 배치 항목들의 judge 호출을 `asyncio.gather`(REQ-1 세마포어로 자연 제한)로 동시 처리하고, 기본값에서는 기존과 동일한 순차 처리 유지(REQ-4; 동기 batch 함수는 `asyncio.run()`으로 경유). 기존 `batch_eval` 파라미터 수 고정 테스트(`test_param_cleanup.py`)를 62→63으로 갱신. 신규 `tests/test_llm_judge_concurrency.py`(20건: rate-limit 판별 5건, 백오프/재시도 5건, 세마포어 동시성 3건, REQ-3 async 배선/동등성 4건, REQ-4 batch 옵트인(async+sync 경유) 3건) 추가, 전체 스위트 2,967 passed, 1 skipped, 회귀 0건(순수 추가 20건 반영).

## Context

- `agent_evaluator/integrations/llm_judge.py:429` `async def ajudge(...)`가 존재하지만, repo 전체 grep 결과 **자기 docstring 예시(`:443`, `>>> result = await judge.ajudge(...)`) 외에는 어디에서도 호출되지 않는다** — 완전한 dead code (2026-07-02 세션에서 직접 재확인).
- `decorators.py`의 동기 경로에서만 동기 `judge()`(`llm_judge.py:326`)가 호출된다.
- `decorators.py:8388-8401`의 `batch_eval` `ThreadPoolExecutor`는 **에이전트 함수 호출(`func`)만** 감싸고, judge/record_task 처리는 이 executor 블록 **바깥**에서 순차 처리된다(직접 코드 확인 완료) — 즉 배치 동시성 옵션이 judge 호출에는 전혀 관여하지 않는다.
- judge 호출 경로에 세마포어/동시 호출 제한이나 provider 429(rate limit) 대응 재시도/백오프 로직이 없다.

## Goals

- 대량 배치 평가에서 judge 호출이 순차 처리로 인해 전체 처리 시간을 좌우하는 병목을 완화한다.
- provider rate limit(429)에 대한 복원력을 확보한다.

## Non-Goals

- judge 모델 자체의 결정성 개선(온도/시드 관련)은 별도 스펙 후보.
- 동기 경로(`judge()`)의 시그니처 변경.

## Requirements

- **REQ-1**: judge 호출 경로에 `asyncio.Semaphore(max_concurrent_judge_calls)`를 도입한다. 기본값은 5이며 `LLMJudge` 생성자 파라미터로 노출한다.
- **REQ-2**: provider의 rate-limit 예외(429/`RateLimitError` 등) 발생 시 지수 백오프(예: 1s, 2s, 4s)로 최대 3회 재시도한다. 3회 초과 실패 시 기존과 동일하게 예외를 전파한다.
- **REQ-3**: 비동기 에이전트 함수(`@agent_eval`의 `is_async=True` 경로)에서 judge 평가가 필요한 경우, 기존 동기 `judge()` 대신 `ajudge()`를 사용하도록 `decorators.py`를 배선한다. 동기 경로는 변경하지 않는다.
- **REQ-4**: `batch_eval`에서 다수 태스크에 judge 평가를 적용할 때, REQ-1의 세마포어 한도 내에서 `asyncio.gather` 기반 동시 처리를 지원하는 옵션을 추가한다(옵트인, 기본 동작은 기존 순차 처리 유지).

## Interface

```python
# 변경 전
judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.1)

# 변경 후 (하위호환 — 신규 파라미터는 기본값 제공)
judge = LLMJudge(
    model="claude-haiku-4-5-20251001",
    sample_rate=0.1,
    max_concurrent_judge_calls=5,   # 신규
    max_retries=3,                  # 신규
)
```

## Acceptance

- mock provider가 429를 5연속 반환하는 시나리오에서 REQ-2의 백오프 후 성공 처리되는 통합 테스트.
- `max_concurrent_judge_calls=N` 설정 시 동시에 진행 중인 judge 호출 수가 N을 초과하지 않는지(mock 지연 응답 + 카운터로) 검증.
- REQ-3 적용 후 비동기 에이전트 경로의 judge 결과가 기존 동기 경로와 동일한 스코어링 로직을 거치는지(동일 입력 → 동일 출력) 회귀 검증.

## Compatibility

- 동기 경로는 시그니처·동작 변경 없음.
- 신규 파라미터는 기본값이 있어 기존 `LLMJudge(...)` 생성 코드는 수정 없이 그대로 동작.

## Rollout

1. `LLMJudge`에 세마포어/재시도 로직 추가(REQ-1, REQ-2) — 동기·비동기 양쪽에서 공유 가능한 형태로 구현.
2. `decorators.py`의 비동기 에이전트 경로에서 `ajudge()` 배선(REQ-3).
3. `batch_eval`에 옵트인 동시 judge 처리 옵션 추가(REQ-4).

## Risks

- 세마포어 기본값(5)이 너무 낮으면 대량 배치 처리 시간이 기대만큼 줄지 않을 수 있음 → 설정 가능하게 노출하고 문서에 provider별 권장값 안내.
- 재시도 로직이 provider별 예외 타입에 의존하므로, Anthropic/OpenAI 등 provider별 rate-limit 예외 클래스를 정확히 식별해야 함(잘못 식별 시 재시도가 발동하지 않거나 불필요한 예외까지 재시도).
