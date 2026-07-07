# agent-evaluator OpenCode plugin (prototype)

`SPEC-019` Rollout 6단계 — Agent-Evaluator의 `LiveGuardrail`(Gate B/E 실시간 가드레일,
`agent_evaluator/gates/live_guardrail.py`)을 OpenCode(로컬 코딩 에이전트 CLI)의
`tool.execute.before`/`tool.execute.after` 훅에 연결하는 참조 구현 프로토타입입니다.

**플러그인 본체(`agent-evaluator.ts`, `package.json`)는
`agent_evaluator/integrations/opencode_plugin/`으로 이동해 pip 패키지에 번들되어
배포됩니다** — `pip install agent-evaluator` 후 `agent-eval opencode install`로 설치할
수 있습니다(아래 "설치" 참조). **이 디렉터리(`opencode-plugin/`)에는 이제 이 문서만
남아 있습니다** — 판정 로직이 없는 얇은 stdio 클라이언트라는 설계(`SPEC-019`
Non-Goals)는 그대로이며, 소스 위치만 SDK 패키지 트리 안으로 옮겨 pip으로 배포 가능하게
한 것입니다(`Docs/specs/SPEC-019-live-guardrail-api.md` 참조).

## 왜 서브프로세스인가

Agent-Evaluator는 Python SDK이고 OpenCode 플러그인은 Node/Bun에서 실행됩니다. 이
플러그인은 Gate B/E 판정 로직을 TypeScript로 재구현하지 않고, 세션당 Python
서브프로세스 하나(`python -m agent_evaluator.integrations.live_guardrail_stdio`)를 띄워
stdin/stdout으로 JSON Lines 프로토콜을 주고받습니다 — 판정 로직의 유일한 소스는 항상
Python 쪽 `LiveGuardrail`이며, 이 플러그인은 그걸 호출하는 얇은 클라이언트입니다.

```
OpenCode (Node/Bun)                     Python
┌───────────────────────┐  stdin/stdout  ┌──────────────────────────────────┐
│ agent-evaluator.ts     │◄──────────────►│ live_guardrail_stdio.py          │
│  tool.execute.before   │   JSON Lines   │  → gates/live_guardrail.py       │
│  tool.execute.after    │   (세션 내내   │    (Gate B 순수 함수 +           │
│                        │    지속)       │     Gate E 트래커, SPEC-019)     │
│                        │                └──────────────────────────────────┘
│  session.idle/error    │  stdin/stdout  ┌──────────────────────────────────┐
│  (recordSessionReport) │◄──────────────►│ live_guardrail_report.py         │
│                        │  1회성 프로세스 │  → PerformanceMonitor.record_task│
│                        │                │    + save_to_file(sqlite upsert) │
└───────────────────────┘                └──────────────────────────────────┘
```

세션 도중에는 `live_guardrail_stdio.py`(세션 내내 살아있는 요청-응답 루프)가
`tool.execute.before`/`after`를 처리하고, 세션이 끝나면(`session.idle` 이벤트)
`live_guardrail_report.py`(1회성 프로세스)가 그 세션의 최종 `extra`를 배치 리포트에
편입합니다 — 서로 생명주기가 다른 두 개의 별도 브리지입니다.

## ctx 자가교정 피드백 루프

`session.idle`에서 계산한 Gate B/E 판정 요약은 `console.log`뿐 아니라
**`client.session.prompt({ body: { noReply: true, ... } })`로 실제 세션 메시지
히스토리에도 기록됩니다**(`recordVerdictToTranscript()`). `noReply: true`라 LLM 응답을
새로 유발하지 않으면서도 OpenCode의 세션 저장소에 영구히 남는 메시지가 되므로, ctx가
다음 색인 시 이 판정 내용을 그대로 주워갈 수 있습니다 — "이 도구 조합은 지난 세션에서
Gate B 루프 위반에 걸렸다" 같은 사실을 다음 세션이 `ctx search`로 찾아낼 수 있게
됩니다. 요약 텍스트는 점수뿐 아니라 `loop_detection`/`scope`/`tool_authorization` 등
구체적으로 어떤 위반이 있었는지까지 적습니다(`summarizeGuardrailResult()` 참조) —
점수만으로는 다음 세션의 모델이 "무엇을 피해야 하는지" 알 수 없기 때문입니다.

이전 버전(초기 프로토타입)은 `console.log`만 남겨서, 실제로는 이 피드백 루프가 전혀
동작하지 않았습니다 — ctx는 콘솔 출력이 아니라 세션 메시지 히스토리를 색인하기
때문입니다. `client.session.prompt()`가 실제 설치된 `@opencode-ai/sdk` 타입 선언에
`noReply` 옵션을 지원한다는 걸 확인한 뒤(`types.gen.d.ts:2244-2258`) 이 결함을
바로잡았습니다.

## SPEC-024: ctx 없이 자체 SQLite 백엔드로 위반 이력 검색하기

위 ctx 피드백 루프는 ctx가 실제로 OpenCode 세션의 대화·도구 호출 내용을 색인할 수
있어야 완성됩니다 — 그런데 라이브 검증(2026-07-05, ctx 0.19.0) 결과 ctx의 OpenCode
임포터는 세션 메타데이터(제목·토큰 수)만 가져오고 실제 내용은 가져오지 못하는 것을
확인했습니다(`ctx show session --mode full`로 직접 조회해도 생명주기 알림 2건뿐,
판정 텍스트는 없음). Agent-Evaluator는 이미 `session.idle`마다 `live_guardrail_report.py`
를 통해 이 판정 상세를 자체 SQLite 백엔드(`storage_backend="sqlite"`)에 저장하고
있으므로, ctx의 이 한계를 우회해 **같은 데이터를 자체적으로 검색 가능하게** 만드는
경로가 SPEC-024로 추가됐습니다.

```bash
pip install "agent-evaluator[mcp]"   # mcp>=1.0.0 (옵트인 의존성)

opencode mcp add agent-evaluator-violations -- \
    python -m agent_evaluator.integrations.violation_search_mcp
```

등록하면 모델이 세션 중 `search_violations` 도구를 스스로 호출해, 과거 세션에서
Gate B/E 위반으로 차단된 이력을 자연어로 검색할 수 있습니다. `db_path`를 생략하면
`AGENT_EVALUATOR_OUTPUT_DIR`(기본값 `results/opencode_live_guardrail`) 아래의
`opencode_sessions.db`를 사용합니다 — `live_guardrail_report.py`가 기본으로 저장하는
경로와 동일합니다. 다른 경로를 쓰려면 `opencode mcp add` 명령의 마지막 인자로
db 경로를 추가하세요.

> **주의 — 자율 호출은 여전히 보장이 아니라 성향입니다.** 위 등록만으로는 모델이
> 알아서 검색을 시도하지 않을 수 있습니다(2026-07-05 라이브 검증에서 확인 — 도구
> 이름을 프롬프트에서 언급하지 않으면 로컬 소형 모델이 아예 이 도구를 안 씀).
> 확실한 효과가 필요하면 프롬프트에 `search_violations`를 직접 언급하세요.

## SPEC-027/028: 배치 Gate A–G 통합 + agent_version 자동 태깅

`session.idle`이 만드는 배치 리포트는 원래 Gate B/E만 의미 있게 채웠습니다 —
`PerformanceMonitor.record_task()`/`generate_report()`는 어떤 태스크가 들어오든
Gate A–G 7개 전부를 계산하지만(`live_guardrail_report.py:record_and_save()`가
호출하는 함수는 데코레이터 경로와 완전히 동일), 실제로 넘어오는 데이터가
B/E 외의 5개 Gate를 채우지 못했습니다. 2026-07-06~07 코드 감사에서 정확한
원인 3가지를 확인하고 바로잡았습니다:

- **Gate G(관측성) — 데이터는 있는데 안 넘어갔습니다.** `LiveGuardrail.record_tool_call()`이
  매 확정 호출마다 원본 도구 호출 이력을 이미 누적하는데, `snapshot()`/`to_task_extra()`는
  거기서 **파생된** Gate B/E 지표만 반환하고 원본 리스트는 어디로도 노출하지
  않았습니다. 이제 `snapshot()`이 `"tool_calls"` 키로 원본 확정 호출 로그(얕은
  복사)를 항상 포함하고, `live_guardrail_report.py`가 이를 `extra`에서 꺼내
  `TaskResult.tool_calls`(ToolCallAnalyzer가 실제로 읽는 최상위 필드)로 옮깁니다.
- **Gate D(성능계약) — 상수 `0.0`이 들어갔습니다.** `recordSessionReport()` 페이로드가
  `execution_time`을 아예 안 보냈습니다 — 모든 세션이 "0초짜리 실행"으로
  기록됐다는 뜻입니다. 이제 `GuardrailSession`이 생성 시점(`readonly startedAt: number
  = Date.now()`)을 기록하고, `handleSessionIdle()`이 `(Date.now() - session.startedAt) / 1000`으로
  실제 경과 시간(초)을 계산해 보냅니다 — 도구 호출 사이 유휴 시간을 포함한 세션
  전체 경과 시간이며, 순수 실행 시간은 아닙니다.
- **Gate A(목표달성) — 없는 게 아니라 조용히 틀린 값이 나왔습니다.** `question`/`response`가
  고정 placeholder(`"<opencode session>"`)라, `completion_score`가 세션 내용과
  무관하게 **항상 `1.0`(완벽)**으로 계산됐습니다. `TaskResult.completion_score`는
  `[0,1]` 범위가 강제돼(벗어나면 `TypeError`) `None`으로 "not tested"를 만들 수
  없고, Gate A의 TCR 컴포넌트는 태스크가 하나라도 있으면 무조건 계산되므로
  애초에 완전한 "not tested"는 불가능함을 확인했습니다 — 대신 신호가 없을 때는
  중립값 `0.5`(성공도 실패도 아님)로 바꿨습니다. 자동화된 검증(예: "방금 고친
  코드로 pytest가 통과하는가")이 있으면 페이로드에 `"success": true|false`를
  추가로 보내 실제 판정을 반영할 수 있습니다 — 그러면 `completion_score`/
  `accuracy_score`가 `1.0`/`0.0`으로, `TaskResult.success`도 그 값으로 맞춰집니다.

추가로, `record_and_save()`가 만드는 `PerformanceMonitor`에 `agent_version=payload.get("agent_version",
"auto")`를 연결했습니다 — 기본값 `"auto"`는 현재 git 커밋 SHA 앞 8자 + 커밋되지
않은 tracked 파일 변경이 있으면 그 diff를 해시한 접미사(`-dirty-<hash>`)로
자동 태깅합니다. 커밋 없이 코드를 고치고 바로 세션을 재시작하는 게 흔한 이
로컬 개발 루프에서, git commit SHA만 쓰면 커밋 전 여러 iteration이 전부 같은
태그로 뭉개져 SPEC-025의 `compare_results(group_by="agent_version")`/⚖️ Pairwise
Judge 비교가 무의미해지는 문제를 해소합니다.

이 변경들은 새 CLI 서브커맨드나 새 비교 로직을 만들지 않았습니다 — 이미
존재하는 `agent-eval gate`/`agent-eval dashboard`가 그대로 이 데이터를 읽습니다.
`Evaluator_Examples/ch28_local_ade_loop.py`(섹션 5)에서 `record_and_save()`를
직접 호출해 Gate A/D/G가 실제로 채워지는 것과 `agent-eval gate`가 exit 0으로
통과하는 것을 실행 검증했습니다. 상세는 `Docs/specs/SPEC-027-git-based-agent-version-tagging.md`/
`Docs/specs/SPEC-028-aoo-batch-harness-integration.md` 참조.

> **한계**: `ToolCallAnalyzer.analyze()`(`layer2.py:197`)는 `success` 키가 없는
> tool_call을 기본 성공으로 간주합니다 — `LiveGuardrail`은 "차단되지 않고 실행됨"만
> 알 뿐 도구 자체의 실행 결과(exit code 등)는 모르므로, Gate G의 성공률이 실제보다
> 낙관적일 수 있습니다. 도구 실행 결과 세분화 추적은 `tool.execute.after` 훅
> 시그니처를 확장해야 하는 더 큰 후속 작업으로 남겨뒀습니다.

## 훅 필드는 실제 설치된 패키지 타입 선언으로 검증했습니다

이전 버전은 OpenCode 공식 문서가 훅 콜백 인자의 전체 필드를 나열하지 않아 추측성
방어 코드를 썼습니다. 2026-07-03에 실제 설치된 `@opencode-ai/plugin@1.17.9`의 타입
선언(`~/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts`,
`@opencode-ai/sdk/dist/gen/types.gen.d.ts`)을 직접 대조해 다음 두 가지를 바로잡았습니다:

1. **`session.idle`/`session.error`는 독립 훅이 아닙니다.** `Hooks` 인터페이스에 그런
   키는 존재하지 않습니다 — 모든 세션 생명주기 이벤트는 단일 `event` 훅
   (`event: (input: { event: Event }) => Promise<void>`)으로 전달되고, `Event`는
   `type` 필드(`"session.idle"`/`"session.error"`/`"session.created"`/...)로 구분되는
   판별 유니온입니다. `agent-evaluator.ts`는 이제 `event.type`으로 분기합니다.
2. **`tool.execute.after`의 도구 호출 인자는 `output.args`가 아니라 `input.args`에
   있습니다.** `output`은 `{title, output, metadata}` — 실행 *결과*이지 인자가
   아닙니다. 이전 버전은 이 필드를 잘못 읽고 있었습니다(실제로는 항상
   `undefined`였을 버그).
3. (부수 확인) `input.sessionID`는 `tool.execute.before`/`after` 양쪽 모두 선택적이
   아닌 필수 필드입니다 — 이전 버전의 `getSessionId()` 후보 필드명 순차 시도(fallback
   chain)는 더 이상 필요 없어 제거했습니다.

이 작업 환경에는 Node/TypeScript 컴파일러가 없어 `tsc`로 직접 컴파일 검증은
못했지만, 실제 설치된 `.d.ts` 파일과 한 줄씩 대조하는 수작업 리뷰는 마쳤습니다.

## 실제 OpenCode 세션으로 라이브 검증했습니다 (2026-07-03)

Homebrew로 설치된 실제 OpenCode `1.17.9` + 로컬 Ollama `qwen3-coder:latest`(이 환경에
이미 pull되어 있었음) 조합으로 이 플러그인을 실제로 로드해 여러 차례 에이전틱 세션을
구동했습니다. `pip install -e .`로 설치한 agent-evaluator, `.opencode/plugin/`에 둔
플러그인, 실제 OpenCode CLI 조합이 통합 자체는 잘 동작함을 확인했습니다. 이 과정에서
아래 3가지를 추가로 발견해 고쳤습니다.

### `opencode run`은 stdin이 열려 있으면 무한 대기합니다 (플러그인과 무관)

headless로 `opencode run "..."`을 호출할 때 stdin을 명시적으로 닫지 않으면(터미널에
연결된 채로 두면) `init` 로그 직후 응답 없이 멈춥니다. `--pure`(플러그인 전부
비활성화)로도 재현되고 일반 디렉터리에서도 재현되어, 플러그인·작업 디렉터리 둘 다
원인이 아님을 먼저 배제했습니다. `< /dev/null`(또는 닫힌 파이프)을 붙이면 수 초 내
정상 진행됩니다 — CI나 스크립트에서 이 플러그인이 설치된 프로젝트에 대해 headless로
`opencode run`을 호출할 때는 **반드시 stdin을 닫아야 합니다.**

```bash
opencode run --dir /path/to/project "your message" \
  --dangerously-skip-permissions < /dev/null
```

### `GUARDRAIL_CONFIG` 예시값이 실제 OpenCode 도구 세분성과 맞지 않았습니다

라이브 세션 로그로 직접 확인한 결과, OpenCode는 셸 관련 동작을 전부 하나의 `"bash"`
도구로 처리합니다(`"shell_exec"` 같은 이름은 존재하지 않습니다). 이 때문에 원래
예시값(`consecutive_repeat_threshold: 3, on_loop_detected: "fail"`)은 `ls → cat →
ls`처럼 완전히 정상적인 연속 셸 사용조차 "루프"로 오탐해 세 번째 확인용 `ls`를 실제로
막는 걸 라이브 테스트로 재현했습니다. 지금 `agent-evaluator.ts`의 `GUARDRAIL_CONFIG`는
threshold를 6으로 올리고 기본 동작을 차단이 아닌 관찰("record")로 낮췄습니다 — 자세한
근거는 파일 내 주석과 `Docs/specs/SPEC-019-live-guardrail-api.md`의 "라이브 검증"
섹션 참조.

### `rm -f`가 기본 위험 패턴을 전부 통과해 실제로 파일이 삭제됐습니다

로컬 모델(qwen3-coder)이 처음엔 `rm -rf` 실행을 스스로 거부했지만, 그다음 `rm -f`(단일
플래그)로 우회해 실제로 파일을 삭제하는 걸 확인했습니다 — `ToolParameterSafetyConfig`
기본 패턴도, `ToolAuthorizationTracker`(Gate E)의 하드코딩된 패턴(`rm\s+-rf`, `-rf`
필수)도 `rm -f`는 잡지 못했습니다. `tool_parameter_safety.dangerous_patterns`에
`rm\s+-\w*f`를 추가해 재현 테스트로 실제 차단을 확인했습니다:

```
ls -la → cat victim2.txt → ls -la  (3회 연속 "bash" 호출, 전부 정상 통과)
rm -f victim2.txt → [agent-evaluator] blocked by Gate B: dangerous tool parameters: ['bash']
→ 세션 종료 후 victim2.txt 파일이 실제로 그대로 남아있음(파일시스템 직접 확인)
```

## 설치

1. Agent-Evaluator를 설치합니다:
   ```bash
   pip install agent-evaluator   # 또는 이 저장소 루트에서: pip install -e .
   ```

2. 플러그인을 설치합니다 — 기본값은 프로젝트 로컬입니다:
   ```bash
   agent-eval opencode install            # .opencode/plugin/agent-evaluator.ts (프로젝트 로컬, 기본값)
   agent-eval opencode install --global   # ~/.config/opencode/plugin/agent-evaluator.ts (전역)
   agent-eval opencode install --force    # 이미 설치된 파일을 덮어쓰기
   ```
   이 명령은 `agent-eval` CLI를 실행 중인 인터프리터의 절대경로를 `agent-evaluator.ts`의
   `PYTHON_BIN` 기본값에 자동으로 채워 넣습니다 — 대부분의 경우 `AGENT_EVALUATOR_PYTHON`
   환경변수를 따로 설정할 필요가 없습니다. 다른 인터프리터를 써야 하면 그 환경변수로
   덮어쓸 수 있습니다.

   설치 여부는 `python -m agent_evaluator.integrations.live_guardrail_stdio`가 오류 없이
   뜨는지로 확인할 수 있습니다(아무 입력도 주지 않으면 대기 상태가 됩니다 — Ctrl+C로 종료).

3. 설치된 `.opencode/plugin/agent-evaluator.ts`(패키지 번들 원본이 아니라 복사본) 상단의
   `GUARDRAIL_CONFIG`를 프로젝트 상황에 맞게 조정합니다 — `agent-eval opencode install`을
   다시 실행하면 이 파일은 번들 원본으로 덮어써지므로(`--force` 필요), 커스터마이즈한
   내용은 별도로 백업하거나 팀 공유 저장소로 관리하세요(Chapter 27 §27.7 참조).
   각 필드의 전체 옵션은 다음을 참조하세요:
   - `loop_detection`/`deadlock`/`scope`/`tool_parameter_safety`:
     `agent_evaluator/gates/gate_b_behavioral/configs.py`
   - `tool_authorization`/`privilege_escalation`/`tool_chain_attack`:
     `agent_evaluator/core/trackers/security.py`

4. 세션 리포트가 쌓일 위치를 바꾸고 싶으면 환경변수로 지정합니다(기본값
   `results/opencode_live_guardrail/opencode_sessions.db`, SQLite):
   ```bash
   export AGENT_EVALUATOR_OUTPUT_DIR=results/my_project
   ```
   여러 OpenCode 세션(각각 독립 프로세스)이 같은 파일에 `task_id` 기준 upsert로
   누적됩니다(SPEC-016) — 세션이 끝날 때마다 콘솔에
   `[agent-evaluator] session <id> recorded to <path> (Gate B=..., Gate E=...)`가 출력됩니다.
   저장된 세션들을 다시 불러오려면:
   ```python
   from agent_evaluator.storage.sqlite_backend import load_tasks_from_db
   tasks = load_tasks_from_db("results/opencode_live_guardrail/opencode_sessions.db")
   ```

## 남은 프로토타입 한계

- **one-shot `opencode run`에서 세션 종료 직후 파이프가 닫히는 경쟁 상태(라이브
  테스트로 실제 재현)**: `session.idle` → `recordSessionReport()`가 Python
  서브프로세스를 스폰하고 응답을 기다리는데, `opencode run`은 마지막 응답 텍스트가
  나온 뒤 우리 `event` 훅의 비동기 완료를 다 기다리지 않고 프로세스 정리를 시작할 수
  있습니다 — 이 경우 stdout 파이프가 일찍 닫혀 Python 쪽이 `BrokenPipeError`를 낸
  걸 실제로 확인했습니다. `record_and_save()`(배치 저장 자체)는 그 이전에 이미 끝난
  뒤라 데이터 유실은 아니지만(파일시스템으로 직접 확인), Node 쪽이 확인 응답을 못
  받으면 `recordVerdictToTranscript()`(ctx 피드백 루프)가 실행되지 않을 수 있습니다 —
  `opencode serve`/TUI처럼 프로세스가 오래 살아있는 모드에서는 이 경쟁이 훨씬 덜
  발생할 것으로 예상되지만 별도로 확인하지 않았습니다.
- **프로세스 생명주기**: `event` 훅(`session.idle`/`session.error`)과 `dispose` 훅
  (플러그인 정상 언로드 시 남은 세션 전부 정리)에서 `live_guardrail_stdio` 서브프로세스를
  종료합니다. 다만 OpenCode 프로세스 자체가 비정상 종료(kill -9 등)되는 경우는
  `dispose`도 호출되지 않으므로 좀비 프로세스가 남을 수 있습니다.
- **`live_guardrail_report` 실패 처리**: 배치 편입이 실패해도(예: output_dir 쓰기 권한
  없음) 세션 자체는 계속 종료됩니다(`console.error`로만 남김) — 가드레일 판정 자체는
  이미 세션 내내 정상 동작했으므로, 리포트 저장 실패 때문에 OpenCode 세션을 막을 이유는
  없다고 판단했습니다.
- **`tool.execute.before`에서 차단된 시도는 세션 transcript에 즉시 기록되지 않습니다**:
  차단 이유는 `throw`된 에러 메시지로 그 턴의 모델에게는 바로 노출되지만(자가 교정
  신호로 실제 동작 확인 — 라이브 테스트에서 모델이 "the rm command was blocked due to
  security restrictions"라고 스스로 인지하고 답했다), 세션 transcript에 대한
  `client.session.prompt()` 기록은 `session.idle` 시점 한 번만 일어납니다. 세션이
  중간에 비정상 종료돼 `session.idle`이 발생하지 않으면 ctx 피드백 루프 자체가 빠질
  수 있습니다.
- **`GUARDRAIL_CONFIG` 예시값은 시작점일 뿐입니다**: `dangerous_patterns`를
  `rm\s+-\w*f`로 넓혔지만, 이건 여전히 화이트리스트가 아니라 알려진 패턴과의
  블랙리스트 매칭입니다 — 라이브 테스트로 모델이 `-rf`→`-f`로 우회를 시도하는 걸
  실제로 목격한 만큼, 다른 패턴으로도 우회될 수 있다는 걸 전제하고 사용하세요.

## 관련 문서

- `Docs/specs/SPEC-019-live-guardrail-api.md` — 전체 설계, Non-Goals, Risks.
- `Docs/specs/SPEC-027-git-based-agent-version-tagging.md` — `agent_version="auto"` 설계.
- `Docs/specs/SPEC-028-aoo-batch-harness-integration.md` — 배치 Gate A–G 통합 설계.
- `agent_evaluator/gates/live_guardrail.py` — 실제 Gate B/E 판정 로직 + `tool_calls` 노출(SPEC-028 REQ-1).
- `agent_evaluator/integrations/live_guardrail_stdio.py` — 세션 내내 살아있는
  Python 브리지(OpenCode 전용이 아닌 범용 stdio 프로토콜).
- `agent_evaluator/integrations/live_guardrail_report.py` — 세션 종료 시 1회
  실행되는 배치 편입 브리지 + `success`/`execution_time`/`agent_version` 옵트인 필드(SPEC-028).
- `Evaluator_Examples/ch28_local_ade_loop.py`(섹션 5) — 배치 Gate A–G 통합 실행 예제.
