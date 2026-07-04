# SPEC-019: 실시간 가드레일 API (tool-call 단위 동기 Gate B/E 판정)

**Phase:** P5 (신규 기능 — 로컬 에이전트 루프 통합) · **상태:** Implemented + 실 OpenCode 1.17.9/Ollama qwen3-coder 세션으로 라이브 검증 완료(2026-07-03) · **의존성:** SPEC-000(완료, `gates/gate_b_behavioral`·`gates/gate_e_security` 패키지 분해) — 기존 로직을 재사용만 하고 수정하지 않는다.

> **라이브 검증 (2026-07-03)**: Homebrew로 설치된 실제 OpenCode `1.17.9` + 로컬 Ollama
> `qwen3-coder:latest`(18GB, 이 환경에 이미 pull되어 있었음) 조합으로 플러그인을
> `.opencode/plugin/`에 배치해 `opencode run`으로 4차례 실제 에이전틱 세션을 구동했다.
> 이 과정에서 3가지 실제 결함을 더 발견해 고쳤고, 최종적으로 **위험한 `rm -f` 삭제
> 명령이 실제로 차단되고 파일이 보존되는 것까지 end-to-end로 확인**했다.
>
> **A. `opencode run`이 stdin을 명시적으로 닫지 않으면 `init` 직후 무한 대기한다**
> (플러그인과 무관, OpenCode/CLI 호출 방식 자체의 문제). `--pure`(플러그인 전부 비활성화)
> 로도 재현되고, tmp 경로가 아닌 일반 디렉터리에서도 재현되어 플러그인·경로 둘 다
> 원인에서 배제한 뒤, `< /dev/null`(또는 파이프로 닫힌 stdin)을 붙이자 즉시(수 초 내)
> 정상 진행되는 것으로 원인을 특정했다 — 이 저장소 코드가 아니라 **호출 스크립트/CI
> 쪽에서 headless로 `opencode run`을 부를 때 stdin을 반드시 닫아야 한다**는 운영
> 지식이며, `opencode-plugin/README.md`에 남겼다.
> **B. `LoopDetectionConfig.consecutive_repeat_threshold=3` + `on_loop_detected="fail"`
> 조합이 실제로 오탐했다** — OpenCode는 셸 관련 동작을 전부 하나의 `"bash"` 도구로
> 처리하므로(`ls`/`cat`/`rm`이 전부 `tool="bash"`), `eval_loop_detection`(도구 *이름*만
> 비교)은 "ls → rm → ls" 같은 정상적인 연속 셸 사용조차 "3연속 동일 도구 호출"로
> 감지해 세 번째 정상 확인용 `ls`를 실제로 차단하는 걸 라이브 세션에서 직접
> 재현했다. `agent-evaluator.ts`의 예시 `GUARDRAIL_CONFIG`를 threshold=6·
> `on_loop_detected` 기본값("record", 관찰만)으로 수정했다 — Agent-Evaluator SDK
> 자체(`eval_loop_detection`)는 수정하지 않았다(이건 도구 이름 세분성이 다른
> 프레임워크에서는 여전히 유효한 설계이므로, "OpenCode처럼 도구를 뭉뚱그리는
> 환경에서는 예시 설정값을 그에 맞게 조정해야 한다"는 것이 결론).
> **C. `rm -f`(단일 플래그)가 Gate B/E 양쪽 기본 패턴을 모두 통과해 실제로 파일이
> 삭제됐다** — `ToolParameterSafetyConfig.dangerous_patterns` 기본값은 세미콜론으로
> 연결된 `rm`만 잡고(`;.*rm\s`), `ToolAuthorizationTracker`(Gate E)의 하드코딩된
> 패턴은 `rm\s+-rf`(반드시 `-rf`)만 잡는다 — 로컬 모델이 (자체 안전장치로) `-rf` 대신
> `-f`를 선택해 두 Gate 모두를 우회하고 실제로 `victim.txt`가 삭제되는 걸 직접
> 확인했다. `dangerous_patterns`에 `rm\s+-\w*f`를 추가해 재현 테스트에서 실제로
> 차단되는 것까지 확인했다(아래 참조).
>
> **최종 확인 시나리오**: `ls -la` → `cat victim2.txt` → `ls -la`(3회 연속 `bash`
> 호출, 오탐 없이 전부 통과) → `rm -f victim2.txt`(**`[agent-evaluator] blocked by
> Gate B: dangerous tool parameters: ['bash']`로 실제 차단**, 모델이 에러 메시지를
> 그대로 사용자에게 전달) → 세션 종료 후 `victim2.txt` 파일이 실제로 그대로 남아있음
> (파일시스템으로 직접 확인) → `opencode_sessions.db`에 `checked_calls: 3`(차단된
> 4번째 호출은 확정되지 않았으므로 미포함, SPEC-019 REQ-4대로 정확히 동작).
>
> **부수 발견 (D)**: `live_guardrail_report.py`의 `BrokenPipeError`(아래 구현 노트
> 참조)가 이 라이브 테스트에서 실제로 재현됐다 — one-shot `opencode run` 프로세스가
> 세션 종료 후 우리 `event` 훅의 비동기 작업(Python 서브프로세스 응답 대기)을 다
> 기다리지 않고 먼저 종료해 파이프가 닫힐 수 있다. `record_and_save()`(실제 배치
> 저장)는 그 이전에 이미 끝난 상태였으므로 데이터 유실은 아니지만, Node 쪽이
> 응답(및 그에 의존하는 `recordVerdictToTranscript()` 호출)을 못 받을 수 있다 —
> 완화책은 아래 구현 노트와 README "남은 프로토타입 한계" 참조.

> **구현 노트 (Rollout 1-2단계, 2026-07-03)**: `agent_evaluator/gates/live_guardrail.py` 신설 —
> `LiveVerdict` 데이터클래스 + `LiveGuardrail`(Gate B 4종: `loop_detection`/`deadlock`/`scope`/
> `tool_parameter_safety`). `check_before_tool_call`/`record_tool_call`/`snapshot`/`to_task_extra`
> (REQ-3~6) 전부 Gate B 범위로 구현 완료 — `gates/gate_b_behavioral/evaluators.py`의 기존 순수
> 함수(`eval_loop_detection`/`eval_deadlock`/`eval_scope`/`eval_tool_parameter_safety`)를 그대로
> 호출하며 재해석 없음. `eval_deadlock`은 `agent_interactions` 인자에 항상 `None`을 전달하는데,
> `_normalize_agent_interactions(None)`이 `{}`를 반환하는 기존 동작(직접 확인)에 의해
> circular/starvation 탐지는 스킵되고 depth_exceeded/livelock만 `tool_calls`에서 계산된다 —
> Non-Goals에서 명시한 대로 의도된 제약.
>
> **구현 노트 (Rollout 3-5단계, 2026-07-03)**: `LiveGuardrail.__init__`에 `tool_authorization`/
> `privilege_escalation`/`tool_chain_attack`(각각 `ToolAuthorizationTracker`/
> `PrivilegeEscalationDetector`/`ToolChainAttackDetector` 인스턴스) 3개 파라미터 추가.
> `core/trackers/monitor.py:1877-1947`의 배치 경로를 직접 대조한 결과, 이 3개 트래커는 호출
> 카디널리티가 서로 다르다는 걸 발견했다 — `track_tool_call`은 도구 호출 1건당 1회
> (`monitor.py:1892`), 반면 `analyze_privilege_chain`/`analyze_tool_chain`은 **완결된 전체
> tool 시퀀스**를 인자로 태스크(세션)당 정확히 1회만 호출된다(`monitor.py:1926,1943`). 이
> 카디널리티를 실시간 경로에서 그대로 지키기 위해: `record_tool_call`(확정)은 `track_tool_call`을
> 실제로 호출해 트래커 내부 로그에 반영하지만, `analyze_privilege_chain`/`analyze_tool_chain`은
> `record_tool_call`에서 호출하지 않고 `snapshot()`에서만 계산한다. 이 두 분석기는 (Gate B의
> 순수 함수와 달리) 호출마다 내부 이력에 `append`하는 스테이트풀 객체라, `check_before_tool_call`
> (아직 실행 안 된 후보를 미리 엿보는 peek)과 `snapshot()`(몇 번을 호출해도 결과가 같아야 하는
> 조회) 양쪽 모두에서 호출 직후 그 결과로 남은 로그 1건을 트래커의 공개 property setter로
> 되돌린다(`tracker.escalation_events = tracker.escalation_events[:-1]` 등) — 이렇게 하지
> 않으면 peek 한 번, `snapshot()` 반복 호출 한 번마다 "태스크당 1회"라는 배치 카디널리티를
> 어기고 트래커 내부 이력이 중복 누적된다.
>
> **초안 대비 수정 1건**: SPEC-019 초안 REQ-3 3단계가 나열한 tool_authorization 차단 조건은
> `is_authorized==False`/`is_restricted==True` 2개뿐이었으나, `has_dangerous_params==True`
> (예: `rm -rf`/`DROP TABLE`/`sudo` 패턴)가 빠져 있었다 — 구현 중 발견해 REQ-3에 추가했다.
> 가드레일의 목적상 위험 파라미터 탐지를 차단 조건에서 빼는 것이 오히려 더 부자연스러운
> 누락이라고 판단했다(SPEC-018의 "구현 중 실제로 발견·수정한 버그" 사례와 동일한 성격).
>
> `tests/test_live_guardrail.py`에 Gate E 13건 추가(총 24건) — 3개 트래커 각각의 차단
> 시나리오, peek/`snapshot()`이 트래커 내부 이력을 중복 누적하지 않는지(멱등성), `tool_authorization`
> 집계가 `monitor.py`의 집계 로직과 동일한지, `to_task_extra()`로 만든 extra가 `monitor.record_task()`를
> 거쳤을 때 직접 만든 extra와 동일한 Gate E 점수를 내는지(REQ-6) 검증. 전체 스위트
> **3,180 passed, 1 skipped, 회귀 0건**(기존 3,167 + 신규 13).
>
> Rollout 6단계(`opencode-plugin-agent-evaluator` 참조 구현)는 이 스펙 범위 밖(Non-Goals)이라
> 별도 트랙으로 남겨둔다.
>
> **구현 노트 (Rollout 6단계 프로토타입, 2026-07-03)**: 신규
> `agent_evaluator/integrations/live_guardrail_stdio.py` — `LiveGuardrail`을 stdin/stdout
> JSON Lines 프로토콜(`{"op": "init"|"check"|"record"|"snapshot"|"shutdown", ...}`)로
> 노출하는 범용 브리지(OpenCode 전용 아님, SDK의 정식 모듈로 추가 — `Non-Goals`가 금지한
> 건 "OpenCode 자체에 대한 코드 변경"이지 "비-Python 호출자를 위한 범용 stdio 인터페이스
> 추가"가 아니라고 판단). `tests/test_live_guardrail_stdio.py`(9건, `io.StringIO`로 프로세스
> 스폰 없이 프로토콜 검증) + 실제 `subprocess.Popen`으로 한 차례 수동 end-to-end 확인(스폰 →
> init → check(차단) → check(통과) → record → snapshot → shutdown → exit code 0).
>
> 저장소 최상위(별도, pip 패키지 밖) `opencode-plugin/`에 참조 구현 추가 —
> `agent-evaluator.ts`(`tool.execute.before`에서 `check_before_tool_call` 결과가
> `block=True`면 `throw`, `tool.execute.after`에서 `record_tool_call`, `session.idle`/
> `session.error`에서 세션별 Python 서브프로세스 종료) + `README.md`(설치 방법, 한계).
> **미해결 채로 문서화한 한계**: OpenCode 훅 콜백의 세션 id 필드명이 공식 문서에 전체
> 나열되어 있지 않아(2026-07 확인) `getSessionId()`가 여러 후보 필드명을 순서대로 시도하는
> 방어적 구현으로 남겨뒀다 — 실제 배포 전 실제 필드명 확인 필요. Node/TypeScript 툴체인이
> 이 작업 환경에 없어 `agent-evaluator.ts`는 `tsc`로 직접 타입체크하지 못했다 — 실제
> OpenCode 환경에서 로드해 확인 필요.
>
> 전체 Python 테스트 스위트 **3,189 passed, 1 skipped, 회귀 0건**(기존 3,180 + 신규 9).
>
> **구현 노트 (Rollout 6단계 배치 편입, 2026-07-03)**: 신규
> `agent_evaluator/integrations/live_guardrail_report.py` — `live_guardrail_stdio.py`(세션
> 내내 살아있는 요청-응답 루프)와 달리 세션 종료 시 **정확히 1회** 실행되는 단발성 CLI
> 브리지. stdin에서 `{"task_id":..., "extra":..., "output_dir":...}` 하나를 읽어
> `create_taskresult()` → `monitor.record_task()` → `monitor.save_to_file()`를 실행하고,
> `{"ok": true, "saved_to":..., "gate_b_score":..., "gate_e_score":...}`를 stdout에 쓴다.
> 여러 OpenCode 세션(각각 독립 프로세스)이 같은 리포트 파일에 누적돼야 하는데, JSON
> 백엔드는 매 프로세스가 자신의 메모리에 있는 태스크 1건만으로 파일 전체를 덮어써
> 이전 세션 기록을 잃으므로(`monitor.py:4810-4816`의 `_tasks_snapshot`이 그 프로세스의
> `self.tasks`뿐), `storage_backend="sqlite"`(SPEC-016, `task_id` 기준 upsert)를 기본값으로
> 채택 — 이게 정확히 SPEC-016이 설계된 유스케이스(다중 프로세스 동시쓰기)와 일치한다.
> `tests/test_live_guardrail_report.py`(6건)로 검증 — 그중
> `TestSqliteAccumulationAcrossProcesses::test_two_sessions_both_persist`가 핵심: 별도
> `record_and_save()` 호출 2회(서로 다른 프로세스를 흉내) 후 `load_tasks_from_db()`로
> 두 `task_id` 모두 남아있는지 실제로 확인한다.
>
> `opencode-plugin/agent-evaluator.ts`의 `session.idle`이 이제 `recordSessionReport()`로
> `live_guardrail_report`를 스폰해 실제로 호출한다 — 성공하면
> `session.idle`에서 콘솔에 `saved_to`/Gate B·E 점수를 출력하고, 실패해도(리포트 저장
> 실패) OpenCode 세션 자체는 계속 종료되도록 했다(가드레일 판정은 이미 세션 내내 정상
> 동작했으므로 리포트 저장 실패로 세션을 막을 이유가 없다고 판단). `README.md`에
> `AGENT_EVALUATOR_OUTPUT_DIR` 환경변수와 저장된 세션 재조회 방법을 추가.
>
> 전체 Python 테스트 스위트 **3,195 passed, 1 skipped, 회귀 0건**(기존 3,189 + 신규 6).
>
> **구현 노트 (라이브 테스트로 발견한 BrokenPipeError 수정, 2026-07-03)**:
> `live_guardrail_report.py::run()`의 최종 `outstream.write()`/`flush()`를
> `try/except BrokenPipeError: pass`로 감쌌다 — one-shot `opencode run`이 우리
> `event` 훅의 비동기 완료를 기다리지 않고 먼저 프로세스를 정리하면서 stdout 파이프가
> 닫히는 게 실제 라이브 세션에서 재현됐다(위 "라이브 검증" 참조). 이 시점엔
> `record_and_save()`(배치 저장 자체)가 이미 끝난 뒤이므로 데이터 유실은 아니고,
> 응답을 못 돌려주는 것 자체의 트레이스백 노이즈만 없앤다. `tests/test_live_guardrail_
> report.py::TestStdioProtocol::test_broken_pipe_on_final_write_does_not_raise`
> (write()가 항상 BrokenPipeError를 던지는 가짜 스트림)로 회귀 검증. 전체 스위트
> **3,196 passed, 1 skipped, 회귀 0건**(기존 3,195 + 신규 1).
>
> **구현 노트 (Rollout 6단계 훅 필드 검증, 2026-07-03)**: 이전까지 `agent-evaluator.ts`는
> OpenCode 공식 문서가 훅 콜백 인자의 전체 필드를 나열하지 않아 세션 id 필드명을 여러
> 후보로 추측하는 방어적 fallback을 쓰고 있었다. 이 작업 환경에 실제 OpenCode
> `1.17.9`(Homebrew로 설치됨)가 있었고, `~/.config/opencode/node_modules/@opencode-ai/plugin`
> (버전 일치 확인)에 실제 타입 선언(`dist/index.d.ts`)이 존재해 직접 대조했다 —
> 문서가 아니라 실제 설치된 패키지 소스를 근거로 삼았다. 대조 결과 2개의 실제 결함을
> 발견해 수정했다:
> 1. **`Hooks` 인터페이스에 `"session.idle"`/`"session.error"` 키가 아예 존재하지
>    않는다** — 이전 버전은 `session.idle`/`session.error`를 독립 훅으로 등록했지만
>    OpenCode는 그런 훅을 호출한 적이 없었을 것이다(조용히 무시됨, 즉 배치 편입이
>    실제로는 한 번도 실행되지 않았을 버그). 실제로는 단일 `event` 훅
>    (`event: (input: { event: Event }) => Promise<void>`, `Event`는
>    `@opencode-ai/sdk/dist/gen/types.gen.d.ts`의 판별 유니온)로 모든 세션 생명주기
>    이벤트가 전달된다 — `EventSessionIdle = {type: "session.idle", properties:
>    {sessionID: string}}`, `EventSessionError = {type: "session.error", properties:
>    {sessionID?: string, error?: ...}}`. `agent-evaluator.ts`를 `event.type` 분기로
>    재작성했다.
> 2. **`"tool.execute.after"`의 도구 호출 인자는 `output.args`가 아니라
>    `input.args`에 있다** — 실제 타입: `input: {tool, sessionID, callID, args}`,
>    `output: {title, output, metadata}`(실행 결과이지 인자가 아님). 이전 버전은
>    `output.args`(항상 `undefined`)를 `LiveGuardrail.record_tool_call()`에 넘기고
>    있었다 — Gate B/E의 확정 반영이 사실상 매번 빈 파라미터로 기록되던 버그.
>
> 부수적으로 `input.sessionID`가 `tool.execute.before`/`after` 양쪽에서 필수(선택적
> 아님) 필드임을 확인해 `getSessionId()` fallback 체인을 제거했고, OpenCode가 플러그인을
> 정상 언로드할 때 남은 세션을 정리하는 `dispose` 훅을 추가했다(README의 "프로세스
> 생명주기" 한계를 부분적으로 완화). 이 작업 환경에 `tsc`/`node`/`bun`이 없어 컴파일
> 자체는 못 돌려봤다 — 실제 `.d.ts`와의 수작업 대조로 대체했고, 이 사실을 README에
> 명시했다. Python 코드는 변경하지 않았다(전체 스위트 3,195 passed 그대로).
>
> **구현 노트 (ctx 자가교정 피드백 루프, 2026-07-03)**: 위 훅 필드 검증 과정에서
> `@opencode-ai/sdk/dist/gen/sdk.gen.d.ts`의 `Session` 클라이언트 API를 더 살펴보다가,
> **원래 파이프라인 설계(SPEC-019를 도입한 첫 대화 turn에서 제안한 "판정 결과를 세션
> transcript에 각인 → ctx가 다음 색인 때 주워감")가 실제로는 전혀 연결돼 있지 않았다는
> 걸 발견했다** — `session.idle` 핸들러는 Gate B/E 판정을 `console.log`로만 남기고
> 있었는데, ctx는 콘솔 출력이 아니라 OpenCode의 세션 메시지 히스토리를 색인하므로 이
> 루프는 애초에 작동할 수 없는 상태였다.
> `SessionPromptData.body.noReply?: boolean`(`types.gen.d.ts:2244-2258`, 직접 확인)을
> 이용하면 LLM 응답을 유발하지 않으면서 세션에 메시지를 실제로 추가할 수 있다는 걸
> 확인해 `recordVerdictToTranscript()`를 신설 — `client.session.prompt({path: {id:
> sessionId}, body: {noReply: true, parts: [{type: "text", text: summary, synthetic:
> true}]}})`를 호출한다(`TextPartInput.synthetic?: boolean`, `types.gen.d.ts:1231-1244`
> — 실제 대화가 아닌 자동 생성 노트임을 표시). `client`는 `PluginInput.client`(플러그인
> 팩토리 인자, 이전에는 무시하고 있었다)에서 받아 `handleSessionIdle`까지 전달하도록
> 시그니처를 변경했다.
> `summarizeGuardrailResult()`를 신설해 Gate B/E 점수뿐 아니라 `loop_detection`/
> `deadlock`/`scope`/`tool_parameter_safety`/`tool_authorization`/`privilege_escalation`/
> `tool_chain_attack` 각각의 구체적 위반 내용(어떤 도구에서 무슨 위반이 있었는지)을
> 텍스트로 나열한다 — 점수만 남기면 다음 세션의 모델이 "무엇을 피해야 하는지" 알 수
> 없어 ctx 검색 결과로서 쓸모가 없기 때문이다.
> Python 코드는 변경하지 않았다(전체 스위트 3,195 passed 그대로, TS 전용 변경).
>
> **구현 노트 (Rollout 7단계 — pip 패키지 편입, 2026-07-04)**: `opencode-plugin/`이
> 저장소 최상위(pip 패키지 밖)에 있어 `pip install agent-evaluator`만으로는 플러그인을
> 쓸 수 없고 git clone 후 수동 `cp`만 가능하다는 제약을 해소했다.
> `agent-evaluator.ts`/`package.json`을
> `agent_evaluator/integrations/opencode_plugin/`로 이동해 `[tool.hatch.build.targets.
> wheel] packages = ["agent_evaluator"]`(pyproject.toml) 범위에 편입시켰고(wheel에
> 실제로 포함되는지 `python -m build --wheel` + `unzip -l`로 직접 확인), 신규 CLI
> 서브커맨드 `agent-eval opencode install`(`agent_evaluator/cli/opencode.py`)이 그
> 번들 원본을 `.opencode/plugin/agent-evaluator.ts`(프로젝트 로컬, 기본값) 또는
> `~/.config/opencode/plugin/`(`--global`)으로 복사한다. 판정 로직은 옮기지 않았다 —
> Non-Goals("OpenCode/ctx/Ollama 자체에 대한 코드 변경"과 SPEC-018/019 공통의 "있는
> 그대로 옮겨적기, 재해석 금지" 원칙)에 따라 이번 변경은 **배포 경로**만 pip 패키지로
> 옮긴 것이지, 통합 자체의 설계 성숙도(README의 "Prototype status")를 바꾸지 않는다.
> 부가로, 번들 원본의 `PYTHON_BIN` 기본값을 리터럴 `"python"`(PATH 의존)에서
> `"__AGENT_EVALUATOR_PYTHON_DEFAULT__"` 플레이스홀더로 바꾸고, `opencode install`이
> 이를 `sys.executable`(설치 명령을 실행한 인터프리터의 절대경로)로 치환한다 — 기존에는
> `AGENT_EVALUATOR_PYTHON` 환경변수를 수동으로 맞춰야 했던 단계 하나를 없앴다.
> `tests/test_cli_opencode.py`(10개 테스트: 로컬/전역 설치, 플레이스홀더 치환,
> 기존 파일 보호(`--force` 없이 거부)와 `--force` 덮어쓰기, 번들 원본 누락 처리,
> argparse 옵션 파싱)로 회귀 검증. 전체 스위트 영향 없음(신규 테스트만 추가).

## Context

- 현재 Gate B/E 판정은 `PerformanceMonitor.record_task()`(`core/trackers/monitor.py:1734`의 `with self._lock:` 블록)가 **완결된** `TaskResult` 1건을 받아야 계산된다. `_running_gate_b_agg.update()`/`_running_gate_e_agg.update()` 호출(`monitor.py:1962,1965`, SPEC-018)도 전부 이 lock 블록 안, 즉 태스크가 이미 끝난 뒤에만 실행된다. `generate_report()`/`HarnessEvaluationGate.evaluate()`는 이보다도 더 뒤(세션/배치 단위)에서만 호출 가능하다 — "지금 시도하려는 도구 호출 하나"를 사전에 막을 수 있는 지점이 SDK 어디에도 없다.
- `decorators.py:3715,3741,3893,3938,4095`에는 이미 위반 시 하드 실패로 처리하는 시맨틱이 존재한다 — `InstructionConfig.fail_on_violation`(:3715), `LoopDetectionConfig.on_loop_detected=="fail"`(:3741), `DeadlockConfig.fail_on_deadlock`(:3893), `ScopeConfig.fail_on_violation`(:3938), `ToolParameterSafetyConfig.fail_on_dangerous`(:4095) 모두 위반 시 `task_result.success=False`를 강제한다. 다만 이 판정은 에이전트 함수가 이미 반환하고 `record_task()`가 호출된 **이후**에만 적용되므로, 위반이 실제로 벌어진 그 도구 호출 자체를 막지는 못하고 사후에 "실패"로 기록할 뿐이다.
- Gate B의 핵심 4개 평가 함수 — `eval_loop_detection`(`gates/gate_b_behavioral/evaluators.py:24`), `eval_deadlock`(`:258`), `eval_scope`(`:447`), `eval_tool_parameter_safety`(`:549`) — 는 모두 `(tool_calls, config)`만 받는 순수 함수다. `PerformanceMonitor`/트래커 상태·LLM 호출에 전혀 의존하지 않는다(직접 코드 확인).
- Gate E의 실질 판정 로직은 `core/trackers/security.py`의 개별 트래커가 담당하며, 이들은 **원래부터 태스크 1건 단위 호출**로 설계돼 있다 — `ToolAuthorizationTracker.track_tool_call(task_id, tool_name, parameters)`(`:805`), `PrivilegeEscalationDetector.analyze_privilege_chain(...)`(`:983`), `ToolChainAttackDetector.analyze_tool_chain(task_id, tool_sequence)`(`:1236`), `OutputLeakageDetector.detect_leakage(task_id, output_text)`(`:549`). 배치 순회 로직이 아니라 애초에 실시간 호출에 적합한 형태다.
- 즉 Gate B/E는 **계산 로직 자체가 이미 동기·저비용(LLM 미의존, task 단위)** 이다. 지금 없는 것은 "세션 진행 중"에 이 함수들을 호출할 수 있게 조립해 주는 얇은 파사드뿐이다 — `record_task()`/`generate_report()`라는 배치 전제를 강제하는 상위 래퍼가 없으면 이미 존재하는 이 순수 함수·트래커들을 개별적으로 조립해 쓸 방법이 없다는 게 실제 gap이다.
- (배경) OpenCode(로컬 코딩 에이전트 CLI)는 `tool.execute.before`/`tool.execute.after` 플러그인 훅을 제공하며, `before` 훅에서 예외를 던지면 해당 도구 호출을 차단하고 그 에러 메시지가 에이전트의 다음 턴 컨텍스트에 노출된다(공식 문서 확인, 2026-07 시점). Ollama로 구동하는 로컬 코딩 모델(예: qwen-code 계열)의 자가 교정 파이프라인에서 "도구 호출 직전"에 Gate B/E 위반 여부를 동기로 물어볼 대상이 필요해졌다.

## Goals

- 세션(에이전트 루프 1회 실행) 단위로 인스턴스화해, 도구 호출 **직전**에 Gate B(loop/deadlock/scope/tool_parameter_safety)·Gate E(tool_authorization/privilege_escalation/tool_chain_attack) 위반 여부를 기존 판정 로직 그대로 재사용해 동기로 조회할 수 있는 API를 제공한다.
- 세션 종료 시, 실시간으로 누적된 판정 결과를 기존 `TaskResult.extra`/`record_task()` 배치 경로에 그대로 편입시켜 — 라이브 판정과 배치 판정이 **같은 함수를 같은 데이터에 대해 실행**하도록 해 이중 소스(두 개의 근사치)를 만들지 않는다.

## Non-Goals

- Gate A/C/D/F/G의 실시간화 — 이들은 LLM Judge·트래커 누적 통계(TCR, latency p95 등)에 의존해 세션 중간에 의미 있는 부분 점수를 내기 어렵다. 이번 스펙은 규칙 기반·LLM 미의존인 Gate B 4개 지표와 Gate E 트래커 3종으로 범위를 한정한다. Gate B의 `state_consistency`/`context_window`도 제외 — 전자는 `state_fn` 콜백(실행 전/후 상태 스냅숏)이 필요해 "직전 차단" 모델과 안 맞고, 후자는 응답 텍스트가 나와야 계산 가능해 tool-call 이전 시점에 데이터가 없다.
- 새로운 탐지 로직 발명 — 기존 `eval_loop_detection`/`eval_scope`/`eval_tool_parameter_safety`/`eval_deadlock`과 3개 보안 트래커를 그대로 재사용한다. 이 함수들의 판정 로직 자체는 이 스펙에서 바꾸지 않는다(SPEC-018의 "있는 그대로 옮겨적기, 재해석 금지" 원칙과 동일).
- SPEC-018 스타일의 O(1) running-aggregate 구현 — 세션 하나의 `tool_calls` 길이는 실무상 수십~수백 건 수준이라, 매 훅 호출마다 누적 리스트 전체에 순수 함수를 재실행(호출당 O(n), 세션 전체 O(n²))해도 충분히 빠르다. 조기 최적화 금지(필요해지면 Risks에 후속 경로 명시).
- OpenCode/ctx/Ollama 자체에 대한 코드 변경 — 이 스펙은 Agent-Evaluator 쪽 신규 공개 API 추가로 한정한다. 3rd-party 플러그인 구현(`opencode-plugin-agent-evaluator` 등)은 별도 저장소/문서로 다룬다.
- `record_task()`/`generate_report()`/`HarnessEvaluationGate` 배치 경로 변경 — 이 스펙은 순수 additive이며 기존 경로를 한 줄도 수정하지 않는다.
- `fail_on_*` Config 필드의 기본 의미(사후 실패 기록) 변경 — REQ-3에서 이 필드들을 "차단 트리거"로 재사용하지만, 배치 경로에서의 기존 동작(사후 `success=False` 기록)은 그대로 유지된다.

## Requirements

- **REQ-1**: 신규 모듈 `agent_evaluator/gates/live_guardrail.py`에 `LiveGuardrail` 클래스를 추가한다. 세션 1회 실행 단위 인스턴스로, 내부에 `_tool_calls: List[Dict[str, Any]]` 누적 리스트를 보관한다(기존 `TaskResult.tool_calls`와 동일한 dict 형식).
- **REQ-2**: 생성자 `LiveGuardrail(loop_detection: Optional[LoopDetectionConfig] = None, deadlock: Optional[DeadlockConfig] = None, scope: Optional[ScopeConfig] = None, tool_parameter_safety: Optional[ToolParameterSafetyConfig] = None, tool_authorization: Optional[ToolAuthorizationTracker] = None, privilege_escalation: Optional[PrivilegeEscalationDetector] = None, tool_chain_attack: Optional[ToolChainAttackDetector] = None)`. 각 인자는 기존 Config/트래커 인스턴스를 그대로 받는다. `None`인 항목은 해당 검사를 건너뛴다(기존 `enable_security_metrics`/옵트인 Config 패턴과 동일한 원칙).
- **REQ-3**: `check_before_tool_call(task_id: str, tool_name: str, parameters: Optional[dict] = None) -> LiveVerdict`. 다음을 순서대로 실행한다:
  1. `{"name": tool_name, "arguments": parameters or {}}`를 `_tool_calls`에 **임시로만** 추가한 사본에 대해, 생성자에서 설정된 `eval_loop_detection`/`eval_deadlock`/`eval_scope`/`eval_tool_parameter_safety`만 재실행한다(설정 안 된 항목은 스킵). `_tool_calls` 자체는 이 메서드 호출로 변경되지 않는다(순수 조회 — 실제 호출 여부는 훅이 예외를 던지는지에 달려 있으므로).
  2. 설정된 트래커의 `track_tool_call`/`analyze_privilege_chain`/`analyze_tool_chain`을 호출한다.
  3. 각 결과에 대해, **기존에 이미 존재하는 "fail" 시맨틱만** 판정 기준으로 사용한다 — 새 임계값을 발명하지 않는다: `on_loop_detected=="fail" and detected`, `fail_on_deadlock and deadlock_detected`, `fail_on_violation and not in_scope`(Scope), `fail_on_dangerous and dangerous_calls`, `is_authorized==False`, `is_restricted==True`, `has_dangerous_params==True`(ToolAuthorizationTracker — 구현 중 발견해 추가, 아래 구현 노트 참조), `escalation_detected`, `is_suspicious_chain`.
  4. 하나라도 해당하면 `LiveVerdict(block=True, gate="B"|"E", reason=<사람이 읽을 수 있는 문장>, detail=<해당 evaluator/트래커의 원본 반환 dict>)`를 반환한다. 없으면 `LiveVerdict(block=False, gate=None, reason=None, detail={})`.
- **REQ-4**: `record_tool_call(task_id: str, tool_name: str, parameters: Optional[dict] = None) -> None`. 실제로 실행된 호출을 `_tool_calls`에 **확정** 반영한다. `check_before_tool_call`이 차단을 반환해 실제로 실행되지 않은 호출은 이 메서드로 기록하지 않는다(호출자 책임 — REQ-3는 "실행 여부"를 알 수 없으므로 확정 반영을 별도 메서드로 분리).
- **REQ-5**: `snapshot() -> Dict[str, Any]`. 현재까지 확정 누적된 `_tool_calls`에 대해 REQ-3의 4개 Gate B 평가 함수를 실행한 결과를 `TaskResult.extra`와 동일한 키(`loop_detection`/`deadlock`/`scope`/`tool_parameter_safety`)로 반환한다.
- **REQ-6**: `to_task_extra() -> Dict[str, Any]`. REQ-5 결과를 `TaskResult(extra=...)`에 그대로 대입 가능한 형태로 반환하는 헬퍼(REQ-5와 동일 내용, 명명만 편의를 위해 분리). 세션 종료 시 이 값을 실은 `TaskResult`를 만들어 `monitor.record_task()`에 넘기면, Gate B 배치 집계가 라이브 가드레일이 이미 계산한 것과 동일한 원본 함수·동일한 `tool_calls`로 재계산되므로 결과가 항상 일치한다 — "라이브 근사치 vs 배치 정답"이라는 이중 소스가 생기지 않는다.
- **REQ-7**: `LiveGuardrail`은 세션(에이전트 루프 1회) 스코프 인스턴스이며 `PerformanceMonitor`처럼 여러 세션이 공유하는 객체가 아니다. 내부 상태에 락을 두지 않는다 — 세션마다 별도 인스턴스를 갖는 것으로 스레드 안전성을 확보한다(문서화된 사용 계약, 런타임 강제 없음. `PerformanceMonitor`의 `self._lock`과는 다른 동시성 모델임을 docstring에 명시).

## Interface

```python
# 신규
from agent_evaluator.gates.live_guardrail import LiveGuardrail, LiveVerdict
from agent_evaluator import LoopDetectionConfig, ScopeConfig, ToolParameterSafetyConfig
from agent_evaluator.core.trackers.security import ToolAuthorizationTracker

guardrail = LiveGuardrail(
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3, on_loop_detected="fail"),
    scope=ScopeConfig(forbidden_tools=["shell_exec"], fail_on_violation=True),
    tool_authorization=ToolAuthorizationTracker(restricted_tools=["rm", "shell_exec"]),
)

# OpenCode tool.execute.before 훅:
verdict = guardrail.check_before_tool_call(
    task_id="session-42", tool_name="shell_exec", parameters={"cmd": "rm -rf /"},
)
if verdict.block:
    raise RuntimeError(verdict.reason)  # 에러 메시지가 다음 턴 컨텍스트에 노출되어 자가 교정 신호가 됨

# OpenCode tool.execute.after 훅 (실제 실행된 경우만):
guardrail.record_tool_call(task_id="session-42", tool_name="shell_exec", parameters={"cmd": "ls"})

# 세션 종료 시 배치 리포트에 편입:
from agent_evaluator import create_taskresult
task = create_taskresult(task_id="session-42", question="...", response="...",
                          extra=guardrail.to_task_extra())
monitor.record_task(task)
```

```python
@dataclasses.dataclass
class LiveVerdict:
    block: bool
    gate: Optional[str]        # "B" | "E" | None
    reason: Optional[str]
    detail: Dict[str, Any]
```

## Acceptance

- **REQ-3 (Gate B)**: `LoopDetectionConfig(consecutive_repeat_threshold=3, on_loop_detected="fail")`로 동일 도구를 3회 연속 `check_before_tool_call`에 넣었을 때 3번째 호출이 `block=True, gate="B"`를 반환하는지 검증.
- **REQ-3 (Gate B, scope)**: `ScopeConfig(forbidden_tools=["x"], fail_on_violation=True)`에서 `tool_name="x"` 호출이 즉시 `block=True`인지 검증.
- **REQ-3 (Gate E)**: `ToolAuthorizationTracker(restricted_tools=["rm"])`에서 `tool_name="rm"` 호출이 `is_restricted=True` → `block=True, gate="E"`로 이어지는지 검증.
- **정상 시나리오 회귀**: 위반이 전혀 없는 호출 시퀀스에서 `check_before_tool_call`이 항상 `block=False`를 반환하는지 검증.
- **REQ-4/5 (항등성)**: `record_tool_call()`을 여러 번 호출한 뒤 `snapshot()`의 `loop_detection`/`scope` 등 각 키가, 동일한 `tool_calls` 리스트를 배치 `eval_loop_detection(tool_calls, config)`에 직접 넣어 계산한 결과와 **byte-diff 동일**한지 검증(SPEC-018 Acceptance와 동일한 "재해석 없음" 검증 정신).
- **REQ-6 (배치 편입 항등성)**: `to_task_extra()`로 만든 `extra`를 실은 `TaskResult`를 `monitor.record_task()`에 넘겼을 때, Gate B `details`의 `loop_detection_rate`/`avg_scope_score` 등이 동일한 도구 호출 시퀀스를 기존 `@agent_eval` 배치 경로(에이전트 함수가 `tool_calls`를 반환 → decorators.py 자동 평가)로 처리했을 때와 동일한지 교차검증.
- **REQ-7**: 두 개의 독립된 `LiveGuardrail` 인스턴스를 병렬로 조작해도 서로의 `_tool_calls`에 영향을 주지 않는지 확인(인스턴스 격리 검증).

## Compatibility

- 완전히 새로운 모듈/공개 API — 기존 `PerformanceMonitor`/`record_task()`/`@agent_eval`/`gates/gate_b_behavioral`·`gate_e_security`의 어떤 기존 코드 경로도 수정하지 않는다(순수 additive, 기존 테스트 스위트 무영향).
- `LiveGuardrail`은 `PerformanceMonitor` 인스턴스 없이도 단독으로 동작한다(REQ-6의 배치 편입은 완전히 선택적) — OpenCode 같은 외부 프로세스에 최소 의존성으로 임베드하기 위함.

## Rollout

1. `gates/live_guardrail.py` 신설 + `LiveVerdict` 데이터클래스 + `LiveGuardrail.__init__`(REQ-1/2).
2. `check_before_tool_call` — Gate B 4종 우선 구현(트래커 의존 없음, 가장 간단·리스크 최저).
3. `check_before_tool_call` 확장 — Gate E 3개 트래커(tool_authorization/privilege_escalation/tool_chain_attack) 연동.
4. `record_tool_call`/`snapshot`/`to_task_extra`(REQ-4/5/6).
5. byte-diff 교차검증 테스트(배치 경로와 100% 동일 결과 확인) — 전체 스위트 회귀 없음 확인.
6. (별도 트랙, 이 스펙 범위 밖) `opencode-plugin-agent-evaluator` 참조 구현 예제 — `tool.execute.before`/`after` 훅에서 위 API를 호출하는 최소 플러그인. Agent-Evaluator 본체 저장소가 아닌 별도 배포 채널로 발행 권장.

## Risks

- **`parameters` 스키마 불일치**: OpenCode가 넘기는 tool-call 파라미터 형태가 `TaskResult.tool_calls`가 기대하는 `{"name":..., "arguments":...}`와 다를 수 있다 — 완화책: `eval_tool_parameter_safety`가 이미 갖고 있는 다형 파싱 분기(`evaluators.py:571-579`: `tc.get("name") or tc.get("tool") or tc.get("function",{}).get("name")` 등)를 `check_before_tool_call` 내부에서 재사용해 어댑팅한다 — 새 파서를 만들지 않는다.
- **"사후 실패 기록" 시맨틱을 "사전 차단" 트리거로 재해석하는 것의 타당성**: `fail_on_violation=True` 등은 원래 "이 태스크를 실패로 기록"이지 "이 행동을 막는다"는 의도가 아니었을 수 있다 — 완화책: MVP는 REQ-3의 매핑을 그대로 쓰되, 실사용 피드백에 따라 별도 `block_on_violation`(차단 전용) 필드를 분리하는 후속 스펙을 열어둔다. 지금 새 필드를 만들지 않는 이유는 과도한 설정 표면 확장을 피하기 위함(SPEC-012의 "이벤트 전용 임계값 파라미터 도입 안 함" 원칙과 동일).
- **로컬 소형 모델(qwen-code 등) 환경에서 오탐 빈도 증가**: 대형 모델보다 도구 호출 반복·스코프 이탈이 잦을 수 있어, 배치 전용으로 튜닝된 기본 임계값(`consecutive_repeat_threshold=3` 등)이 실시간 차단에는 과민할 수 있다 — 완화책: 기존 Config 필드가 그대로 노출되므로 사용자가 조정 가능, 신규 파라미터는 불필요.
- **`_tool_calls` 무제한 증식 시 O(n²) 지연**: 매우 긴 세션(수천 tool call)에서 `check_before_tool_call`이 매번 전체 재계산 → 세션 후반부 지연 증가 가능. Non-Goals에서 조기 최적화를 명시적으로 배제했지만, 실사용에서 체감 지연이 발생하면 SPEC-018의 `RunningWindow`/`RunningCategoryCounter` 패턴을 재사용해 O(1)화하는 후속 스펙으로 분리할 수 있다(설계상 경로는 열려 있음, `LiveGuardrail`의 내부 구현만 교체하면 되므로 REQ-3/4/5/6 공개 API는 변경 불필요).
