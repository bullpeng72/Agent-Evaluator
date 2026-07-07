# SPEC-028: AOO 배치 Gate A–G 통합 — 실시간 가드레일과 오프라인 종합평가의 단일 파이프라인화

**Phase:** P9 (AOO ADE 연동 트랙 — SPEC-027과 함께 로컬 개발 루프를 완성) · **상태:** **Implemented — REQ-1~5 전체 완료(2026-07-07)** · **의존성:** SPEC-019(완료, `LiveGuardrail`/OpenCode 플러그인/stdio·report 브리지) · SPEC-016(완료, `storage_backend="sqlite"` 다중 프로세스 upsert) · SPEC-027(**완료**, `agent_version="auto"` — REQ-5가 이 스펙의 산출물을 그대로 소비)

> **구현 노트 (REQ-4, 2026-07-07)**: `Evaluator_Examples/ch28_local_ade_loop.py`에
> "섹션 5"를 추가했다 — OpenCode 플러그인의 `session.idle` 훅이 호출하는
> `live_guardrail_report.record_and_save()`를 예제에서 직접 호출해, 섹션 1의
> `make_repo_guardrail()`을 재사용한 정상 리팩토링 세션(도구 호출 3건)을
> 시뮬레이션한다. `execution_time=47.3`(REQ-2, 의도적으로 SLA 기본 임계값을
> 넘는 값 — Gate D가 "fail"로 나오는 것 자체가 상수 0.0이 아니라 실측값에 실제로
> 반응한다는 증거임을 주석으로 설명), `success=True`(REQ-3), `agent_version`
> 미지정(REQ-5 기본값 `"auto"`)으로 호출한 뒤, 저장된 JSON을 직접 열어
> Gate A/D/G 점수와 `agent_version`을 출력한다. 마지막으로 `subprocess.run(["agent-eval",
> "gate", ...])`(REQ-4, `ch21_pipeline.py:193`의 기존 패턴 재사용 — 새 CLI 서브커맨드
> 없음)로 기존 CLI가 이 파일을 그대로 받아들이는지 확인한다.
>
> **실행 검증(직접 실행)**: `python Evaluator_Examples/ch28_local_ade_loop.py`
> 정상 종료, 출력에서 확인:
> - `섹션 5 세션의 확정 tool_calls 개수(REQ-1): 3` — 이전에는 이 필드 자체가 없었음.
> - `Gate A: 0.7042 (pass)` — 이전에는 placeholder 텍스트로 항상 `1.0`.
> - `Gate D: 0.0 (fail)` — 이전에는 항상 상수 `0.0`이지만 "성공(=매우 빠름)"으로 보였음; 이제는 같은 `0.0` 점수라도 실측 47.3초가 SLA 임계값을 초과해 실제로 "fail" 판정이 나옴(다른 원인의 동일 숫자 — 우연히 헷갈릴 수 있어 예제 주석에 명시).
> - `Gate G: 1.0 (pass)` — 이전에는 항상 `None`(not tested).
> - `agent_version(REQ-5, SPEC-027 자동 태깅): b8ff65cf-dirty-...` — 실행할 때마다
>   해시 접미사가 실제로 바뀌는 것까지 확인(스펙 작업 중 파일을 계속 수정했기
>   때문 — REQ-2 dirty-diff 감지가 실제로 작동한다는 예상치 못한 실증).
> - `agent-eval gate 실행 결과: exit 0 (정상)` — REQ-4 Acceptance 충족.
>
> 예제 파일 자체의 ruff 순변화 **0**(HEAD 대비 E501 9건으로 동일 — 신규 라인에서
> 발생한 E501 2건은 즉시 줄바꿈으로 정리). `Evaluator_Examples/`는 SDK 품질
> 래칫(agent_evaluator/) 범위 밖이라 mypy 대상도 아니다. 전체 pytest 스위트
> **3,432 passed, 1 skipped**(예제 실행은 pytest 컬렉션에 포함되지 않으므로
> 테스트 수 변화 없음 — 검증은 위 직접 실행으로 갈음).
>
> **SPEC-028 전체 완료.** REQ-1(tool_calls 노출)→REQ-2(execution_time 실측)→
> REQ-3(success 옵트인 + Gate A 오도 정정)→REQ-5(agent_version 자동 태깅 연결)→
> REQ-4(문서화·예제 실증)까지 5개 요구사항 모두 실제 실행 검증과 품질 래칫
> 순증가 최소화(REQ-3의 `UP006` +1, 전부 파일 기존 컨벤션과 일치)를 확인하며
> 구현했다. SPEC-025(비교 파이프라인)+SPEC-027(자동 태깅)+SPEC-028(배치 신호
> 보강)이 이제 실제로 하나의 개발자 여정으로 연결됐다 — 로컬 ADE 루프에서
> 커밋 없이 반복 실행해도 iteration마다 자동 구분되고, Gate A/D/G까지 의미
> 있게 채워진 채 기존 `agent-eval gate`/`dashboard`의 group_by/pairwise 비교에
> 곧바로 들어간다.

> **구현 노트 (REQ-5, 2026-07-06)**: `record_and_save()`(`live_guardrail_report.py`)의
> `PerformanceMonitor(output_dir=..., storage_backend=...)` 생성 호출에
> `agent_version=payload.get("agent_version", "auto")`를 추가했다 — 기본값 `"auto"`가
> SPEC-027의 자동 태깅(커밋 SHA + 미커밋 변경 해시)을 그대로 활성화하고, 페이로드에
> 다른 문자열을 명시하면 그 값이 그대로 쓰인다(override). 설계안 그대로 구현,
> 편차 없음 — SPEC-027이 이미 완성돼 있어 새 로직을 추가하지 않고 파라미터
> 전달만 했다. 입력 스키마 문서에도 `agent_version` 필드를 추가.
>
> `tests/test_live_guardrail_report.py`에 REQ-5 전용 테스트 3건 추가(기본값이 실제로
> SPEC-027 자동 태깅을 거치는지 — `subprocess.run`을 SPEC-027 테스트와 동일한
> 패턴으로 mock, 명시 override가 그대로 쓰이는지, dirty 상태에서 `-dirty-` 접미사가
> 붙는지). 전체 스위트 **3,432 passed, 1 skipped, 회귀 0건**(기존 3,429 + 신규 3).
> 품질 래칫 순변화 **0**(REQ-3에서 이미 발생한 `UP006` +1에서 변화 없음, mypy 0,
> 테스트 파일 신규 E501 1건은 즉시 줄바꿈으로 정리).
>
> 이로써 SPEC-025(비교 파이프라인)+SPEC-027(자동 태깅)+SPEC-028(배치 신호 보강)이
> 실제로 하나로 연결됐다 — OpenCode 세션을 커밋 없이 반복 실행해도 서로 다른
> iteration이 `agent_version`으로 자동 구분되고, Gate G/D/A까지 의미 있게 채워진
> 상태로 `agent-eval gate`/`agent-eval dashboard`의 group_by/pairwise 비교에
> 바로 들어간다.

> **구현 노트 (REQ-3, 2026-07-06)**: **설계안 대비 중요한 수정 1건.** 원 설계는
> `success` 미지정 시 `completion_score=None, accuracy_score=None`을 명시 전달해
> Gate A를 "not tested"로 만들 계획이었다. 실제로 구현하며 `create_taskresult(...,
> completion_score=None)`을 직접 실행해보니 `TaskResult.__post_init__`이
> `0.0 <= completion_score <= 1.0`을 강제 검증해 **`TypeError`로 즉시 크래시**했다
> (`core/trackers/base.py:88`). 게다가 `completion_score`는 Gate A의 TCR 컴포넌트
> (`_a_vals[0]`, `gates/gate_a_goal/aggregate.py:185`)에 **무조건** 반영되므로 —
> 태스크가 하나라도 기록되면 TCR은 항상 어떤 값을 갖는다 — 애초에 Gate A를
> "not tested"로 만드는 것 자체가 이 아키텍처에서는 불가능함을 확인했다(다른
> 선택적 컴포넌트(goal_alignment 등)와 달리 TCR은 옵트아웃 지점이 없음).
>
> 대안으로, `success` 미지정 시 `completion_score`를 **중립값 0.5**로 override했다
> (성공도 실패도 아님을 명시 — 기존 버그였던 "항상 1.0(완벽)"과 "항상 0.0(완전
> 실패)"이라는 두 극단 모두 똑같이 오도임을 검토 후, 최소 커밋인 방향으로 결정).
> `accuracy_score`는 미지정 시 손대지 않았다 — `ground_truth`가 애초에 전달되지
> 않아 기존에도 자연 계산값이 이미 정직한 `0.0`(측정 불가)이었기 때문에(직접 실행해
> 확인, `calculate_accuracy_score()`가 `ground_truth` 없으면 무조건 `0.0` 반환)
> 별도 override가 불필요했다. `success` 지정 시에는 `completion_score`/
> `accuracy_score`를 `1.0`/`0.0`으로, `TaskResult.success`도 그 값으로 일관되게
> 맞췄다.
>
> 부수적으로 중요한 발견: Gate A의 `AccuracyEvaluator` 블렌딩(`0.6×TCR + 0.4×Accuracy`)은
> `TaskResult.accuracy_score`를 직접 읽는 게 아니라 별도 `AccuracyEvaluator._evaluations`
> 카운트로 활성화되는데, `record_task()`는 이를 자동 호출하지 않는다(`grep`으로
> 전수 확인) — 즉 OpenCode 세션에서는 `accuracy_score`를 무엇으로 설정하든 Gate A
> **점수 자체**에는 전혀 영향이 없고(TCR만 반영), 대시보드 표시 필드로서의 의미만
> 있다. 이 사실이 "accuracy_score는 손대지 않아도 된다"는 판단의 근거가 됐다.
>
> 최초 구현은 mypy 신규 에러 4건을 발생시켰다(`**({...} if ... else {})` 인라인
> dict 언패킹을 mypy가 `dict[str, float]`로 좁혀 추론해 `create_taskresult`의
> `**extra_fields: Any` 시그니처와 충돌) — `Dict[str, Any]`로 명시 타입한 지역
> 변수로 리팩터링해 즉시 0건으로 해소.
>
> `tests/test_live_guardrail_report.py`에 REQ-3 전용 테스트 5건 추가(success=True/False
> 각각의 점수, 미지정 시 중립값 0.5 + 크래시 없음, **핵심 회귀**: 서로 다른
> placeholder 텍스트를 줘도 미지정 시 completion_score가 항상 동일함(더는 텍스트
> 길이에 좌우되지 않는다는 증거), Gate A 점수가 크래시 없이 계산됨). 전체 스위트
> **3,429 passed, 1 skipped, 회귀 0건**(기존 3,424 + 신규 5). 품질 래칫
> `live_guardrail_report.py` 순변화 `UP006` +1(이 파일에 이미 있는 `Dict[...]`
> 컨벤션과 일치), mypy 0.

> **구현 노트 (REQ-2, 2026-07-06)**: `agent-evaluator.ts`의 `GuardrailSession`에
> `readonly startedAt: number = Date.now()` 필드를 추가했다(생성 시점 1회 기록).
> `recordSessionReport()`에 `executionTime: number` 파라미터를 추가해 stdin 페이로드에
> `execution_time`으로 실어 보낸다(`live_guardrail_report.py`의 입력 스키마는 이미 이
> 필드를 받아들이도록 설계돼 있어 Python 쪽 변경 불필요 — 설계안 그대로). `handleSessionIdle()`이
> `recordSessionReport()` 호출 직전 `(Date.now() - session.startedAt) / 1000`으로
> 경과 시간(초)을 계산해 전달한다. 설계안 그대로 구현, 편차 없음.
>
> TS 파일 자체는 이 저장소에 타입체크 파이프라인이 없어(`tsconfig.json`/설치된
> `node_modules` 부재), 별도 스크래치 디렉토리에 `typescript`+`@types/node`와
> `@opencode-ai/{sdk,plugin}`의 최소 stub 타입 선언을 설치해 `tsc --noEmit`으로
> 직접 검증했다 — 신규 에러 0건(남은 에러 2종은 HEAD 버전에도 동일하게 존재하는
> `ChildProcessByStdio` 타입 좁힘 이슈 및 stub 선언의 한계로 인한 암시적 `any`이며,
> 둘 다 이번 변경과 무관함을 HEAD 버전 대조로 확인).
>
> `tests/test_live_guardrail_report.py`에 `execution_time` 통과 테스트 2건 추가
> (명시적 값 반영, 미지정 시 하위 호환 기본값 `0.0`) — REQ-2 자체는 TS 쪽 변경이라
> Python 테스트가 직접 검증하는 것은 아니지만, 이 값이 실려 오면 Python 쪽이 정확히
> 소비한다는 전제가 실제로 성립함을 확인. 전체 스위트 **3,424 passed, 1 skipped,
> 회귀 0건**(기존 3,422 + 신규 2). 품질 래칫 `tests/test_live_guardrail_report.py`
> 순변화 **0**(신규 테스트 작성 중 발견한 E501 2건은 즉시 줄바꿈으로 정리).

> **구현 노트 (REQ-1, 2026-07-06)**: `LiveGuardrail.snapshot()`(`gates/live_guardrail.py:260`)의
> 반환 dict 최상단에 `"tool_calls": list(self._tool_calls)`를 추가했다 — 설정된
> Config와 무관하게 항상 포함(다른 Gate B/E 파생 키와 달리 조건부가 아님). 얕은
> 복사라 호출자가 반환값을 통해 내부 `self._tool_calls`를 변형할 수 없다.
> `live_guardrail_report.py:record_and_save()`(`:66-81`)는 `extra = dict(payload["extra"])`로
> 복사한 뒤 `extra.pop("tool_calls", [])`로 꺼내 `create_taskresult(..., tool_calls=...)`에
> 최상위 필드로 전달한다 — `dict(...)` 복사 덕분에 `pop()`이 호출자의 원본 payload를
> 변형하지 않는다(직접 테스트로 확인). 설계안 그대로 구현, 편차 없음.
>
> 기존 SPEC-019 테스트 3건이 `snapshot()`/`to_task_extra()`의 반환 dict를 정확히
> 일치(`==`) 비교하고 있어(`tests/test_live_guardrail.py`) 새 `tool_calls` 키
> 추가로 실제로 깨졌다 — `test_snapshot_only_includes_configured_metrics`(키
> 집합에 `"tool_calls"` 추가)와 Gate B/E 각각의 `to_task_extra()` 배치 일치성
> 테스트 2건(예상 dict에 `"tool_calls"` 항목 추가)을 의도된 동작 변경으로 갱신했다
> — 우연한 회귀가 아니라 이 REQ가 명시적으로 의도한 변경임을 테스트로 문서화.
>
> `tests/test_live_guardrail_report.py`에 REQ-1 전용 테스트 4건 추가(tool_calls가
> 최상위 필드로 옮겨지고 extra에는 안 남는지, Gate G `tool_coverage`가 실제로
> `None`이 아닌 값을 내는지 — 이전에는 절대 채워지지 않던 것, `tool_calls` 키가
> 없는 구형 페이로드도 빈 리스트로 안전하게 처리되는지, 원본 payload가 변형되지
> 않는지). 전체 스위트 **3,422 passed, 1 skipped, 회귀 0건**(기존 3,418 + 신규 4,
> 기존 3건은 의도된 동작 변경 반영 갱신). 품질 래칫 `live_guardrail.py`+
> `live_guardrail_report.py` 순변화 **0**(HEAD 대비 ruff 카운트 완전 동일 —
> `UP045` 13/`UP006` 10/`E501` 9). mypy 신규 에러 2건은 `live_guardrail.py:180,291`의
> 기존 `PrivilegeEscalationDetector` 타입 불일치로, 이번 변경과 무관한 완전
> 사전 존재 이슈임을 HEAD 버전과 직접 대조해 확인.

## Context — 지금 SDK의 두 축과 AOO의 위치

Agent-Evaluator는 이미 두 가지 서로 다른 사용 방식을 지원한다:

1. **비침투적 SDK 통합** — `@agent_eval`/`@batch_eval` 데코레이터 또는 `PerformanceMonitor.record_task()`를 기존 에이전트 코드에 최소한으로 끼워 넣고, Config(기준 선언) × Tracker(실측) × Gate(A–G 판정)의 조합으로 품질을 평가한다. 결과는 대시보드(`agent-eval dashboard`)·터미널 출력·HTML 리포트(`save_to_file()`)로 나오고, 운영 단계에서는 OTEL 연동(`setup_otel()`)으로 Phoenix UI와 이어진다. **이번 스펙은 이 네 가지 출력 채널을 전혀 바꾸지 않는다** — 새 채널을 만들지 않고 기존 채널에 흘러들어가는 데이터만 넓힌다.
2. **LiveGuardrail 실시간 통합**(SPEC-019) — OpenCode+Ollama 로컬 코딩 에이전트의 `tool.execute.before/after` 훅에 붙어, 도구 호출 1건 단위로 Gate B(행동무결성)/E(보안경계)만 동기 판정한다. 세션 종료(`session.idle`) 시 그 판정을 배치 리포트(SQLite)에 편입하는 다리도 이미 있다(`live_guardrail_report.py`).

**문제**: 이 두 축이 코드 레벨에서는 이미 같은 파이프라인을 공유하고 있다 — `live_guardrail_report.py:record_and_save()`(`:53-89`)가 실제로 호출하는 건 `PerformanceMonitor.record_task()`/`generate_report()`/`save_to_file()`(`:71,79-80,82`)로, 데코레이터 경로가 쓰는 것과 **완전히 동일한 함수**다. `generate_report()`는 어떤 태스크가 들어오든 Gate A–G 전체(`harness_groups`)를 계산하므로(`:82-83`), **인프라는 이미 Gate A–G 배치 평가를 지원한다.** 그런데 실제로 OpenCode 세션에서 넘어오는 데이터는 Gate B/E 외의 5개 Gate를 의미 있게 채우지 못한다 — 직접 확인한 구체적 원인 3가지:

- **Gate G(관측성) — 데이터가 있는데 안 넘어간다**: `LiveGuardrail.record_tool_call()`(`live_guardrail.py:203-223`)이 매 확정 호출마다 `self._tool_calls.append({"name": tool_name, "arguments": parameters})`로 실제 도구 사용 이력을 이미 누적한다. 하지만 `snapshot()`/`to_task_extra()`(`:248-300`)는 이 원본 리스트에서 **파생된 Gate B/E 지표만** 반환하고(`loop_detection`/`deadlock`/`scope`/`tool_parameter_safety`/`tool_authorization`/`privilege_escalation`/`tool_chain_attack`), 원본 `self._tool_calls`는 어디로도 노출하지 않는다. `live_guardrail_report.py:72-78`의 `create_taskresult(..., extra=extra)` 호출도 `extra=` 인자로만 넘기므로 `TaskResult.tool_calls`(ToolCallAnalyzer가 Gate G `tool_coverage`를 계산할 때 읽는 실제 필드)에는 아무것도 들어가지 않는다 — Gate G가 항상 "not tested"다.
- **Gate D(성능계약) — 아예 상수 0.0이 들어간다**: `agent-evaluator.ts:161`의 `recordSessionReport()` 페이로드는 `{task_id, extra, output_dir}`뿐, `execution_time`을 아예 안 보낸다. `live_guardrail_report.py:76`은 `execution_time=float(payload.get("execution_time", 0.0))`로 조용히 `0.0`을 기본값 삼는다 — 모든 OpenCode 세션이 "0초짜리 실행"으로 기록된다는 뜻이고, Gate D의 latency 기반 지표는 존재하되 전부 무의미한 상수다.
- **Gate A(목표달성) — 없는 게 아니라 "오도하는 값"이 생긴다**: `live_guardrail_report.py:74-75`가 `question`/`response`에 고정 placeholder `"<opencode session>"`를 넘긴다. `create_taskresult`(`taskresult_helpers.py:634-641`)는 이 텍스트로 `completion_score`를 **항상 동적으로 계산**한다(재정의 없이는 스킵 경로가 없음, `:684-710` 확인) — 즉 세션이 실제로 목표를 달성했는지와 무관하게, 고정 문자열 하나의 텍스트 길이 휴리스틱이 만들어낸 숫자가 마치 실제 완료도인 것처럼 Gate A에 들어간다. "차단된 위반이 없음"이 "목표를 완벽히 달성함"으로 둔갑하는 셈이다 — 데이터 없음보다 나쁜, 조용히 틀린 신호다.
- 반면 `taskresult_helpers.py:629-631`(`if "tool_calls" in extra_fields: tool_calls = extra_fields["tool_calls"]`)과 `:704-708`(`extra_fields` 중 `TaskResult` 필드명과 일치하는 키는 동적 계산값을 그대로 override)을 직접 확인한 결과, **`tool_calls`/`completion_score`/`accuracy_score`/`success`를 명시적으로 넘기면 그 값이 우선 적용된다** — 새 재정의 메커니즘을 만들 필요 없이 기존 override 경로를 그대로 쓸 수 있다.
- `ToolCallAnalyzer.analyze()`(`core/trackers/layer2.py:180`)는 도구 이름 키로 `"tool_name"`/`"tool"`/`"name"`을 전부 허용하므로, `LiveGuardrail._tool_calls`의 기존 `"name"` 키는 별도 변환 없이 바로 호환된다(`success` 키가 없으면 `:197`에서 `True`로 기본 처리 — Risks 참고).
- SPEC-025/027이 이미 `agent_version`을 소비하는 비교 파이프라인(`compare_results(group_by="agent_version")`, `gate --baseline-version`, 대시보드 Group by 드롭다운)을 완성해 뒀지만, `live_guardrail_report.py:71`의 `PerformanceMonitor(output_dir=output_dir, storage_backend=storage_backend)` 생성 호출에는 `agent_version`이 아예 전달되지 않는다 — OpenCode 세션들은 아직 버전 비교 파이프라인에 연결돼 있지 않다.

## 개발자 여정(Developer Journey) — 이번 스펙이 완성하려는 그림

```
① 로컬에서 OpenCode+Ollama로 에이전트/코드를 반복 개발
   → 실시간: LiveGuardrail이 위험한 행동을 즉시 차단 (SPEC-019, 기존, 무수정)

② session.idle — 위반 요약이 세션 transcript에 남고(ctx 자가교정, 기존),
   배치 리포트(SQLite)에 편입됨
   → REQ-1/2/3 이후: 이 시점에 Gate G(도구 사용)·D(세션 길이)·
     A(선택적 완료 신호)도 함께 의미 있게 채워짐
   → REQ-5 이후: agent_version="auto"(SPEC-027)로 현재 git 상태가 자동 태깅됨

③ 개발자가 원하는 시점에(세션 1개든, N개 누적 후든) 완전히 기존 명령으로
   Gate A–G 종합 확인:
     agent-eval gate results/opencode_live_guardrail/opencode_sessions.json
     agent-eval dashboard --results results/opencode_live_guardrail/
   → REQ-4: 이 워크플로우를 예제/문서로 명시화(새 CLI 불필요 — 이미 동작)

④ 여러 iteration(커밋 여부 무관) 사이의 품질 변화는 SPEC-025의
   compare_results(group_by="agent_version")/⚖️ Pairwise Judge/Export HTML로 확인
   → REQ-5가 자동 태깅을 연결해야 group_by가 서로 다른 iteration을 구분함
```

**핵심 통찰**: "실시간"과 "배치"는 서로 다른 두 아키텍처가 아니다 — `PerformanceMonitor.record_task()`/`generate_report()`라는 같은 파이프라인에 흘러들어가는 데이터의 풍부함 차이일 뿐이다. 이번 스펙은 새 평가 로직이나 새 출력 채널을 만들지 않고, OpenCode 세션이 이 파이프라인에 이미 흘려보낼 수 있었던(그러나 지금은 누락되거나 오도하는) 데이터를 바로잡는다.

## Goals

- LiveGuardrail이 이미 추적 중인 도구 호출 이력을 Gate G(관측성)가 실제로 읽을 수 있는 형태로 배치 리포트에 편입한다.
- OpenCode 세션의 실제 경과 시간을 Gate D(성능계약)에 반영해, 상수 `0.0` 대신 의미 있는 latency 신호를 만든다.
- 목표 달성 신호(Gate A)가 없을 때 placeholder 텍스트 기반의 오도하는 값 대신 "신호 없음"을 정직하게 반영하고, 개발자가 원하면(예: 자동화된 검증 스크립트 결과) 실제 완료 신호를 옵트인으로 전달할 수 있게 한다.
- OpenCode 세션 배치 리포트가 이미 `agent-eval gate`/`agent-eval dashboard`로 완전히 동작한다는 것을 예제·문서로 명시해, "실시간 차단"과 "배치 종합평가"가 하나의 자연스러운 개발자 여정임을 드러낸다.
- SPEC-027의 `agent_version="auto"`를 OpenCode 배치 리포트 생성 지점에 연결해, 커밋 여부와 무관하게 서로 다른 iteration이 SPEC-025의 버전 비교 파이프라인에서 자동으로 구분되게 한다.

## Non-Goals

- Gate F(다중에이전트 협력) 신호 확보 — OpenCode 단일 에이전트 세션에서는 대부분 해당 사항이 없다(min-sample-guard로 "not tested" 유지가 올바른 동작). 서브에이전트 위임을 쓰는 OpenCode 워크플로우가 실사용에서 확인되면 별도 후속.
- 도구 호출의 **실제 실행 성공/실패**(exit code 등) 세분화 추적 — `tool.execute.after` 훅 시그니처를 바꿔 도구 자체의 출력을 `record()`까지 전달해야 하는 더 큰 변경이라 범위 밖. 이번 스펙은 "차단되지 않고 실행됨 = success 기본값 True"라는 알려진 한계를 그대로 두고 문서화만 한다(Risks 참고).
- OpenCode 세션 성공 여부를 **자동으로 추론**하는 것(예: 세션 종료 이벤트 타입만으로 판정) — `session.error` 이벤트는 세션 자체의 비정상 종료만 알려줄 뿐 "코드 변경이 실제로 목표를 달성했는가"와는 다른 질문이다. ch28의 `verify_before_declaring_done()` 패턴과 동일하게, 실제 검증(pytest 등)은 개발자/파이프라인이 수행하고 그 결과만 옵트인으로 전달받는다.
- `prompt_version`에 대한 동등한 자동화 — SPEC-027의 Non-Goals와 동일한 이유로 범위 밖.
- 새 CLI 서브커맨드(예: `agent-eval opencode report`) 추가 — `agent-eval gate`/`agent-eval dashboard`가 이미 이 파일 형식을 그대로 소비하므로 새 명령을 만들 필요가 없다(REQ-4는 순수 문서화/예제).

## Requirements

- **REQ-1**: `LiveGuardrail.snapshot()`(`gates/live_guardrail.py:248-292`)의 반환 dict에 `"tool_calls": list(self._tool_calls)` 키를 추가한다(원본 리스트의 얕은 복사 — 호출부가 실수로 내부 상태를 변형하지 못하게). `live_guardrail_report.py:record_and_save()`(`:53-89`)는 이 키를 `extra` dict에서 pop한 뒤 `create_taskresult(..., tool_calls=popped_list, extra=remaining_extra)`로 최상위 `TaskResult.tool_calls`에 전달한다(`taskresult_helpers.py:629-631`의 기존 override 경로 재사용, 새 파싱 로직 없음). `extra` dict의 나머지 Gate B/E 키는 그대로 유지된다.
- **REQ-2**: `agent-evaluator.ts`의 `GuardrailSession` 클래스(`:168-215`)가 생성 시점(`constructor`)에 `this.startedAt = Date.now()`를 기록한다. `handleSessionIdle()`(`:326-347`)이 `recordSessionReport()`를 호출하기 직전, 경과 시간(`(Date.now() - session.startedAt) / 1000`, 초 단위)을 계산해 페이로드에 `execution_time`으로 추가한다. `live_guardrail_report.py`의 입력 스키마는 이미 이 필드를 받아들이도록 설계돼 있으므로(`:34-36`) Python 쪽 변경은 불필요하다.
- **REQ-3**: `live_guardrail_report.py`의 입력 스키마에 선택적 `success: Optional[bool] = None` 필드를 추가한다. `success`가 주어지면 `create_taskresult(..., completion_score=1.0 if success else 0.0, accuracy_score=1.0 if success else 0.0, success=success)`로 실제 완료 판정을 명시적으로 반영한다. `success`가 주어지지 않으면(기존 호출부 전부 포함 — 하위 호환) `completion_score`를 **중립값 `0.5`**로 override해(`accuracy_score`는 건드리지 않음 — `ground_truth` 부재로 이미 자연스럽게 `0.0`), `response="<opencode session>"` placeholder 텍스트 길이 기반 휴리스틱이 항상 `1.0`(완벽)을 만들어내던 기존의 오도 가능한 기본 동작을 막는다. **(구현 시 발견: `completion_score=None`은 `TaskResult.__post_init__`의 `[0,1]` 범위 검증에 걸려 `TypeError`로 크래시하고, `completion_score`는 Gate A TCR 컴포넌트에 무조건 반영돼 애초에 "not tested"로 만들 수 없음을 확인 — 구현 노트 참고, 위 설계는 최초 초안이며 실제 구현은 중립값 방식으로 수정됨.)** 이 부분은 새 기능이 아니라 기존 동작의 정정이다.
- **REQ-4**: `Evaluator_Examples/ch28_local_ade_loop.py`(또는 신규 절)에 "이렇게 누적된 OpenCode 세션 배치 리포트를 `agent-eval gate`/`agent-eval dashboard`로 확인하는 법"을 실행 가능한 예제와 함께 문서화한다. 새 코드/새 CLI 서브커맨드를 추가하지 않는다 — REQ-1~3 이후 이 두 기존 명령이 실제로 Gate A/D/G까지 의미 있게 채워진 리포트를 보여준다는 것만 시연·검증한다.
- **REQ-5**: `live_guardrail_report.py:71`의 `PerformanceMonitor(output_dir=output_dir, storage_backend=storage_backend)` 생성 호출에 `agent_version="auto"`(SPEC-027)를 추가한다 — SPEC-027이 구현돼 있어야 이 REQ가 의미 있게 동작한다(의존 관계, Rollout 참고). 입력 스키마에 `agent_version`을 오버라이드할 수 있는 선택적 필드도 추가해(기본값 `"auto"`), 필요 시 사용자가 다른 태깅 전략을 쓸 수 있게 한다.

## Interface

```python
# REQ-1 — LiveGuardrail.snapshot()/to_task_extra() 반환값에 tool_calls 추가
guardrail.snapshot()
# {..., "tool_calls": [{"name": "bash", "arguments": {...}}, ...]}
```

```
# REQ-2/3/5 — live_guardrail_report.py 입력 스키마 확장 (전부 선택적, 하위 호환)
{
  "task_id": str,
  "extra": {...},                  # REQ-1: 이제 tool_calls 키를 포함할 수 있음
  "execution_time": float,         # REQ-2: 세션 실제 경과 시간(초) — 기존 0.0 기본값 대체
  "success": bool | null,          # REQ-3: 신규, 선택 — 없으면 completion_score=0.5(중립)
  "agent_version": str,            # REQ-5: 신규, 기본값 "auto"
  ...
}
```

```bash
# REQ-4 — 새 명령 없음, 기존 명령이 그대로 Gate A/D/G까지 채워진 리포트를 읽는다
agent-eval gate results/opencode_live_guardrail/opencode_sessions.json
agent-eval dashboard --results results/opencode_live_guardrail/
```

## Acceptance

- **REQ-1**: 도구 호출 3건(그중 1건은 차단됨 — `record_tool_call()` 미호출)을 시뮬레이션한 뒤 `snapshot()["tool_calls"]`에 정확히 확정된 2건만 담기는지. `record_and_save()`로 저장한 `TaskResult.tool_calls`가 `ToolCallAnalyzer.analyze()`에 그대로 먹혀 Gate G `tool_coverage`가 `None`이 아닌 실제 값을 내는지.
- **REQ-2**: `execution_time`을 명시적으로 넘겼을 때 저장된 `TaskResult.execution_time`이 그 값과 일치하는지, 넘기지 않았을 때(하위 호환) 기존처럼 `0.0`인지.
- **REQ-3**: `success=True`/`success=False`/미지정 3가지 경우 각각 저장된 `TaskResult.completion_score`/`accuracy_score`/`success`가 설계대로(`1.0`/`0.0`/`0.5`·미변경) 나오는지, 크래시 없이 처리되는지. `success` 미지정 시 Gate A 관련 harness score가 placeholder 텍스트 길이에 좌우되지 않는지(같은 `success` 미지정 페이로드를 `question`/`response` placeholder만 다르게 두 번 호출해도 `completion_score`가 동일해야 함 — 텍스트 내용과 무관해졌다는 증거).
- **REQ-4**: 예제 실행 후 `agent-eval gate`가 exit code를 정상 반환하고(오류 없음), `agent-eval dashboard`로 연 리포트에서 Gate G/D 값이 "not tested"가 아닌 실제 숫자로 표시되는지(REQ-1/2 선행 확인).
- **REQ-5**: `agent_version` 미지정(기본값 `"auto"`) 시 저장된 리포트의 `agent_version`이 SPEC-027의 자동 태깅 값과 일치하는지. 명시적으로 다른 문자열을 넘기면 그 값이 그대로 쓰이는지(override 확인).
- **회귀 없음**: 기존 SPEC-019/024 테스트 스위트(LiveGuardrail 차단/기록/검색 전체)가 무수정으로 통과하는지.

## Compatibility

- REQ-1/2/3/5 전부 선택적 필드 추가 — 기존 페이로드(신규 필드 없이 `task_id`/`extra`만 보내는 호출)는 정확히 이전과 동일하게 동작한다(단, REQ-3의 `completion_score` 기본값이 "텍스트 휴리스틱 계산값(항상 1.0)"에서 "중립값 0.5"로 바뀌는 것은 의도된 동작 변경이다 — Gate A 관련 값이 실제로 달라지지만, 이는 "항상 완벽으로 오도 → 중립"으로의 개선이라 하위 호환 파괴로 취급하지 않는다. `accuracy_score`는 건드리지 않아 그대로 `0.0`. Risks에 명시).
- SPEC-025/026이 완성한 `compare_results`/`gate`/대시보드/HTML export는 전혀 수정하지 않는다 — 전부 이미 완성된 `agent_version`/Gate 소비 경로를 그대로 재사용한다.
- `agent-evaluator.ts`의 `GuardrailSession`에 `startedAt` 필드 하나만 추가된다 — 기존 `check`/`record`/`snapshot`/`shutdown` 메서드 시그니처는 무변경.

## Rollout

1. REQ-1(tool_calls 노출) — 독립적, Python 쪽만 변경(`live_guardrail.py`+`live_guardrail_report.py`), 가장 리스크 낮음.
2. REQ-2(execution_time 실측) — 독립적, TS 쪽 작은 변경(`startedAt` 필드 1개).
3. REQ-3(success 옵트인 + Gate A 오도 방지) — 독립적, Python 쪽만 변경. **REQ-1/2와 무관하게 가장 먼저 처리해도 되는 후보** — "조용히 틀린 값"을 고치는 것이라 우선순위가 높다.
4. REQ-5(agent_version="auto" 연결) — **SPEC-027 구현 완료 후에만 착수**(선행 의존).
5. REQ-4(문서화/예제) — REQ-1~3(및 가능하면 5)이 실제로 동작한 뒤 마지막에 작성해야 예제가 진짜로 채워진 Gate 값을 보여줄 수 있다.

## Risks

- **`success` 키 부재 시 tool_calls의 기본 성공 처리**: `ToolCallAnalyzer.analyze()`(`layer2.py:197`)는 `call.get("success", True)`로 `success` 키가 없으면 성공으로 간주한다 — `LiveGuardrail._tool_calls`는 "차단되지 않고 실행됨"만 알 뿐 도구 자체의 실행 결과(exit code 등)는 모르므로, Gate G의 `tool_coverage`(success_rate)가 실제보다 낙관적으로 나올 수 있다 — 완화책: 문서에 이 한계를 명시하고, 도구 실행 결과 세분화는 Non-Goals로 명시된 후속 스펙으로 남긴다.
- **REQ-3의 기본 동작 변경**: `success` 미지정 시 Gate A(TCR 기반) 값이 이전에는 항상 `1.0`(완벽, 오도)이었는데 이제는 `0.5`(중립)로 바뀐다 — `TaskResult.completion_score`는 `[0,1]` 범위 검증 때문에 `None`(not-tested)으로 만들 수 없고, TCR 컴포넌트는 태스크가 하나라도 있으면 항상 계산되므로(구현 노트 참고) 완전한 "not tested"는 애초에 불가능했다 — 완화책: `0.5`가 "성공도 실패도 아닌 불명"임을 문서에 명시하고, 의미 있는 Gate A 신호가 필요하면 `success`를 명시적으로 전달하라고 안내한다.
- **REQ-2의 세션 경과 시간과 "실제 작업 시간"의 괴리**: `startedAt`은 세션이 생성된 시점(첫 도구 호출 직전)부터 재므로, 사용자가 세션을 열어두고 한참 딴짓하다 돌아온 경우 `execution_time`이 실제 작업 시간보다 크게 부풀 수 있다 — 완화책: 문서에 "이 값은 도구 호출 사이 유휴 시간을 포함한 세션 전체 경과 시간"이라고 명시(정확한 순수 실행 시간이 필요하면 도구별 duration 합산이 필요하나 이는 Non-Goals의 "실행 성공/실패 세분화 추적"과 같은 범위의 더 큰 후속 작업).
- **SPEC-027 의존성 지연 리스크**: REQ-5는 SPEC-027이 Draft 상태에서 Implemented로 넘어가야 의미가 있다 — SPEC-027 없이 REQ-5만 먼저 병합하면 `agent_version="auto"`가 아무 자동 태깅 로직 없이 그냥 리터럴 문자열 `"auto"`로 저장돼 조용히 잘못된 값이 쌓인다 — 완화책: Rollout 순서를 명시적으로 강제(REQ-5는 SPEC-027 완료 후에만 시작).
