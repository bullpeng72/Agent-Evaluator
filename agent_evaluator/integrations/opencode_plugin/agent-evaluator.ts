/**
 * SPEC-019 Rollout 6단계 프로토타입 — Agent-Evaluator의 LiveGuardrail(Gate B/E 실시간
 * 가드레일)을 OpenCode의 tool.execute.before/after 훅에 연결하는 참조 구현.
 *
 * Agent-Evaluator는 Python SDK다. 이 플러그인은 Node/Bun 쪽에서 직접 그 로직을
 * 재구현하지 않고, 세션당 하나의 Python 서브프로세스
 * (`python -m agent_evaluator.integrations.live_guardrail_stdio`)를 띄운 뒤
 * stdin/stdout으로 JSON Lines 프로토콜을 주고받는다. 프로토콜 상세는 그 모듈의
 * docstring과 Docs/specs/SPEC-019-live-guardrail-api.md 참조.
 *
 * 설치:
 *   1. `pip install agent-evaluator` (또는 `pip install -e .`)로 이 패키지가 설치된
 *      Python 환경을 준비한다.
 *   2. `agent-eval opencode install` 을 실행한다 — 이 파일(패키지에 번들된 원본)을
 *      `.opencode/plugin/agent-evaluator.ts`(프로젝트 로컬, 기본값)에 복사하고
 *      아래 PYTHON_BIN 기본값을 설치 시점의 인터프리터 절대경로로 채워 넣는다.
 *      전역 설치는 `--global`, 이미 있는 파일을 덮어쓰려면 `--force`.
 *   3. 프로젝트별 설정은 `.ts` 파일을 편집하는 대신 옆에 두는
 *      `agent-evaluator.config.json`(JSON 객체)에 적는다 — 최상위 키가
 *      `GUARDRAIL_CONFIG` 위에 얕게 병합된다. 이렇게 하면 `agent-eval opencode
 *      install`을 다시 실행해 이 `.ts`(코드)를 최신으로 갱신해도 설정이 살아남는다
 *      (Claude Code 훅의 guardrail_config.json과 동일한 분리 원칙). `resolveGuardrailConfig()`
 *      참조. 파일이 없으면 위 인라인 GUARDRAIL_CONFIG가 그대로 쓰인다.
 *
 * 훅 필드는 실제 설치된 `@opencode-ai/plugin@1.17.9`의 타입 선언
 * (`node_modules/@opencode-ai/plugin/dist/index.d.ts`,
 * `node_modules/@opencode-ai/sdk/dist/gen/types.gen.d.ts`)을 직접 대조해 확정했다
 * (2026-07-03 — 이전 버전은 문서 부재로 세션 id 필드를 추측하는 방어적 폴백을 썼으나,
 * 실제 타입 확인 후 아래 두 가지를 바로잡았다):
 *
 *   1. `"tool.execute.before"`/`"tool.execute.after"`의 `input.sessionID`는 항상
 *      존재하는 필드다(선택적 아님) — 후보 필드명을 순서대로 시도하는 fallback이
 *      필요 없다.
 *   2. `"tool.execute.after"`의 도구 호출 인자는 `output.args`가 아니라
 *      **`input.args`**에 있다(`output`은 `{title, output, metadata}` — 실행
 *      *결과*이지 인자가 아니다). 이전 버전은 이 필드를 잘못 읽고 있었다.
 *
 * 또한 `"session.idle"`/`"session.error"`는 `Hooks` 인터페이스에 **독립된 훅 키로
 * 존재하지 않는다** — 세션 생명주기 이벤트는 전부 단일 `event` 훅
 * (`event: (input: { event: Event }) => Promise<void>`)으로 전달되며, `Event`는
 * `type` 필드로 구분되는 판별 유니온이다(`EventSessionIdle`/`EventSessionError` 등,
 * `@opencode-ai/sdk`). 아래 코드는 `event.type`으로 분기한다.
 *
 * ── ctx 자가교정 피드백 루프 (2026-07-03 추가) ──────────────────────────────
 * 최초 프로토타입은 session.idle에서 Gate B/E 판정을 `console.log`로만 남겼는데,
 * 이건 터미널/opencode 로그에만 남을 뿐 ctx가 색인하는 세션 메시지 히스토리에는
 * 전혀 반영되지 않는 결함이었다 — "판정 결과가 세션 transcript에 남아야 ctx가
 * 다음 세션에서 그걸 찾아준다"는 자가교정 루프의 핵심 전제가 비어 있었다.
 * `@opencode-ai/sdk`의 `SessionPromptData.body.noReply?: boolean`(실제 타입 확인,
 * `types.gen.d.ts:2244-2258`)을 이용하면 LLM 응답을 유발하지 않으면서 세션에
 * 메시지를 실제로 추가할 수 있다 — `recordVerdictToTranscript()` 참조. `TextPartInput`
 * 의 `synthetic?: boolean` 필드(`types.gen.d.ts:1231-1244`)로 이게 실제 대화가 아닌
 * 자동 생성 노트임을 표시한다.
 */

import type { Event } from "@opencode-ai/sdk"
import type { Plugin, PluginInput } from "@opencode-ai/plugin"
import { spawn, type ChildProcessByStdio } from "node:child_process"
import type { Writable, Readable } from "node:stream"
import * as readline from "node:readline"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

// ── 프로젝트별 설정 ──────────────────────────────────────────────────────────
// 각 키의 전체 필드는 다음을 참조:
//   - loop_detection/deadlock/scope/tool_parameter_safety:
//     agent_evaluator/gates/gate_b_behavioral/configs.py
//   - tool_authorization/privilege_escalation/tool_chain_attack:
//     agent_evaluator/core/trackers/security.py
//   - branch_guard: agent_evaluator/gates/branch_guard.py (BranchGuardConfig)
//   - team_concurrency: agent_evaluator/gates/team_concurrency.py (TeamConcurrencyConfig)
interface GuardrailInitConfig {
  loop_detection?: Record<string, unknown>
  deadlock?: Record<string, unknown>
  scope?: Record<string, unknown>
  tool_parameter_safety?: Record<string, unknown>
  tool_authorization?: Record<string, unknown>
  privilege_escalation?: Record<string, unknown>
  tool_chain_attack?: Record<string, unknown>
  // 두 필드 모두 stdio 브리지(live_guardrail_stdio.build_guardrail())가 이제 받아들인다 —
  // 기본 GUARDRAIL_CONFIG는 비워둔다(옵트인), 필요한 프로젝트만 값을 채워 넣는다.
  branch_guard?: Record<string, unknown>
  team_concurrency?: Record<string, unknown>
  // SPEC-041: 실시간 루프 판정을 최근 N호출로만 한정(latch 방지). null이면 전체 이력.
  live_loop_window?: number | null
  // SPEC-041: on_loop_detected="fail"일 때 실제로 차단할 루프 타입(기본 consecutive_repeat만).
  live_loop_blocking_types?: string[]
  // SPEC-041: tool_authorization 백스톱 스캔에서 제외할 파일 본문 키.
  auth_scan_skip_keys?: string[]
  // SPEC-041: cat/tee/echo/printf 리다이렉트·heredoc으로 파일을 만드는 순수 쓰기는
  // 명령 안의 위험 문자열을 "파일 내용"으로 보고 차단하지 않는다(기본 true).
  lenient_shell_file_write?: boolean
}

// 아래 설정은 실제 OpenCode 1.17.9 + Ollama qwen3-coder 세션으로 라이브 테스트한 뒤
// 3가지를 바로잡았다(2026-07-03, 상세 근거는 SPEC-019 구현 노트 참조):
//
// 1. OpenCode는 셸 관련 동작을 전부 하나의 "bash" 도구로 처리한다("shell_exec" 같은
//    이름은 존재하지 않는다 — 실 세션 로그로 확인). `ls`/`rm`/`cat`이 전부 tool="bash"로
//    기록되므로, `eval_loop_detection`(도구 *이름*만 비교)의
//    `consecutive_repeat_threshold`를 낮게 잡으면 "ls → rm → ls" 같은 완전히 정상적인
//    연속 셸 사용도 "루프"로 오탐된다 — threshold=3, on_loop_detected="fail" 조합에서
//    정상 확인 절차(`ls`)가 실제로 차단되는 걸 라이브 테스트로 직접 재현했다.
//    threshold를 올리고, 기본값은 차단 대신 관찰만 하는 "record"로 낮췄다 — "fail"로
//    실제 차단하려면 사용 중인 에이전트의 도구 세분성이 이 가정에 맞는지 먼저 확인할 것.
// 2. `ScopeConfig.forbidden_tools=["bash"]`처럼 "bash" 자체를 막으면 코딩 에이전트의
//    정상 동작이 전부 막힌다 — 도구 전체를 통째로 막는 예시로는 네트워크 접근
//    ("webfetch", 실 세션 로그에서 확인된 실제 도구명)이 더 현실적이다.
// 3. dangerous_patterns(Gate B, 커스터마이즈 가능)는 SPEC-041(2026-08-27)에서
//    재정비했다 — 과거엔 `\brm\s+\S`로 플래그 유무와 무관하게 모든 `rm <인자>`를
//    잡았으나, `rm dist/bundle.js`처럼 정상적인 빌드 산출물 정리까지 하드 차단해
//    코딩 세션 마찰이 컸다. 이제는 **재귀+강제 삭제**(`rm -rf`/`-fr`/`-Rf` 등),
//    체이닝된 `; rm -`, mkfs, 디바이스로의 dd, fork bomb, `curl|sh`만 잡는다.
//    단일 파일 `rm foo`/`rm -f foo`는 통과시킨다(되돌리기 쉬움, 대개 git으로 복구).
//    `rm -rf`는 Gate E 하드코딩 백스톱(ToolAuthorizationTracker, 커스터마이즈 불가)도
//    계속 잡으므로 이중 방어다.
// 4. dangerous_patterns는 도구 이름과 무관하게 모든 도구 호출의 파라미터 전체를
//    검사하므로, 위 rm 패턴을 그대로 두면 셸과 무관한 도구(예: 검색·메모리 도구가
//    "rm 시도가 차단됨" 같은 결과 텍스트를 반환하는 경우)까지 오탐할 수 있다.
//    scope_tool_names로 이 검사를 실제 셸 실행 도구("bash")로만 한정해 이 문제를
//    막는다. SPEC-041에서 길이 검사(max_argument_length)도 같은 스코프를 따르게 돼,
//    write/edit로 쓰는 큰 파일 본문이 arg_too_long으로 차단되지 않는다.
// loop_detection intentionally omits on_loop_detected here, which falls back to
// LoopDetectionConfig's own default ("record", observe-only) — the false-positive risk
// described above (single coarse-grained "bash" tool) means "fail" (block) would be too
// aggressive by default. The Claude Code hook bridge's DEFAULT_GUARDRAIL_CONFIG
// (agent_evaluator/integrations/claude_code_hook.py) deliberately sets "fail" instead,
// because Claude Code's tools are already fine-grained (Bash/Read/Edit/Write/WebFetch),
// so that false-positive path is far narrower there. Not a bug — see that file's comment
// for the full reasoning.
// SPEC-041 (2026-08-27): `\.\./`(상대 경로)·`&&`·`||`(셸 체이닝)은 정상 코딩 세션에서
// 흔하고 그 자체로 파괴적이지 않아 dangerous_patterns에서 뺐다(Claude Code 훅의
// DEFAULT_GUARDRAIL_CONFIG와 동일한 정리) — `cd src && make`, `cat ../x.json` 같은
// 정상 명령이 차단되던 것을 없앴다. 남긴 건 되돌리기 어려운 실제 파괴 명령뿐이고,
// Gate E 하드코딩 백스톱(tool_authorization)이 sudo/rm -rf/chmod 777 등을 계속 잡는다.
// consecutive_repeat_threshold는 6→8, live_loop_window=15(latch 방지)를 추가했다.
// on_loop_detected는 여전히 생략한다 — OpenCode는 셸 동작 전체가 단일 "bash" 도구라
// 정상 연속 사용도 루프로 오탐될 수 있어 차단("fail") 대신 관찰("record")이 안전하다.
const GUARDRAIL_CONFIG: GuardrailInitConfig = {
  loop_detection: { consecutive_repeat_threshold: 8 },
  live_loop_window: 15,
  scope: { forbidden_tools: ["webfetch"], fail_on_violation: true },
  tool_parameter_safety: {
    dangerous_patterns: [
      "\\brm\\s+-[a-zA-Z]*r[a-zA-Z]*f", "\\brm\\s+-[a-zA-Z]*f[a-zA-Z]*r",
      ";\\s*rm\\s+-", "\\bmkfs\\b", "\\bdd\\s+if=.*of=/dev/",
      ":\\(\\)\\s*\\{\\s*:\\s*\\|",
      "\\|\\s*(sh|bash|zsh|ksh)\\b", "[<>]\\(\\s*(sh|bash|zsh|ksh)\\b",
      "__import__", "eval\\(", "exec\\(",
    ],
    scope_tool_names: ["bash"],
    max_argument_length: 100000,
    fail_on_dangerous: true,
  },
  tool_authorization: {},
}

// SPEC-041: 프로젝트별 설정은 이 파일(코드)을 편집하는 대신 옆에 두는
// `agent-evaluator.config.json`(JSON 객체)으로 오버라이드할 수 있다. 그러면
// `agent-eval opencode install`이 이 .ts(코드)를 최신으로 덮어써도 설정이 살아남는다
// (Claude Code 훅의 guardrail_config.json과 동일한 분리 원칙). JSON의 최상위 키는
// 위 GUARDRAIL_CONFIG 위에 *얕게* 병합된다 — 예: `{"scope": {...}}`만 적으면 scope
// 블록만 교체되고 나머지 기본값(tool_parameter_safety 등)은 그대로 유지된다.
// 파일이 없거나 JSON이 깨졌으면 위 인라인 기본값을 그대로 쓴다(회귀 없음).
function resolveGuardrailConfig(): GuardrailInitConfig {
  let overridePath: string
  try {
    overridePath = join(dirname(fileURLToPath(import.meta.url)), "agent-evaluator.config.json")
  } catch {
    return GUARDRAIL_CONFIG
  }
  try {
    const parsed = JSON.parse(readFileSync(overridePath, "utf-8"))
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      console.error(`[agent-evaluator] applying guardrail config override: ${overridePath}`)
      return { ...GUARDRAIL_CONFIG, ...parsed }
    }
    console.error(`[agent-evaluator] ${overridePath} is not a JSON object — using built-in defaults`)
  } catch (err) {
    const code = (err as NodeJS.ErrnoException)?.code
    if (code !== "ENOENT") {
      console.error(`[agent-evaluator] ignoring invalid ${overridePath}: ${err}`)
    }
  }
  return GUARDRAIL_CONFIG
}

const EFFECTIVE_GUARDRAIL_CONFIG: GuardrailInitConfig = resolveGuardrailConfig()

// 기본값 "__AGENT_EVALUATOR_PYTHON_DEFAULT__"는 `agent-eval opencode install`이 설치
// 시점의 인터프리터 절대경로로 치환한다(이 번들 원본에는 리터럴 플레이스홀더로 남는다).
// 다른 인터프리터를 쓰려면 환경변수로 오버라이드.
const PYTHON_BIN = process.env.AGENT_EVALUATOR_PYTHON ?? "__AGENT_EVALUATOR_PYTHON_DEFAULT__"

// live_guardrail_report.py가 세션 리포트를 누적할 output_dir.
const REPORT_OUTPUT_DIR = process.env.AGENT_EVALUATOR_OUTPUT_DIR ?? "results/opencode_live_guardrail"

interface LiveVerdict {
  block: boolean
  gate: "B" | "E" | null
  reason: string | null
  detail: Record<string, unknown>
}

// SPEC-031 REQ-3: record_tool_call(output=...)에 실어 보낼 실행 결과. success/exit_code는
// 찾지 못하면 필드 자체를 생략한다(Python 쪽 allow-list가 없는 키를 무시하므로 안전).
interface ToolExecutionOutput {
  stdout?: string
  success?: boolean
  exit_code?: number
}

// "tool.execute.after"의 output.metadata는 @opencode-ai/plugin 타입 선언상 `any`다 —
// 실제로 exit code가 어느 키에 담기는지 공개 타입으로 보장되지 않는다(SPEC-031 Risks에
// 명시된 미검증 사항). 몇 가지 흔한 후보 키를 방어적으로 시도하고, 못 찾으면 success/
// exit_code 필드를 아예 만들지 않는다 — 최악의 경우에도 기존 동작(success 미기록)으로
// 안전하게 떨어진다.
function extractToolExecutionOutput(output: { output: string; metadata: unknown }): ToolExecutionOutput {
  const meta = output.metadata as Record<string, unknown> | undefined
  const exitCode = [meta?.exit, meta?.exitCode, meta?.code]
    .find((v): v is number => typeof v === "number")
  return {
    stdout: output.output,
    ...(exitCode !== undefined ? { exit_code: exitCode, success: exitCode === 0 } : {}),
  }
}

interface ReportResult {
  ok: boolean
  saved_to?: string
  gate_b_score?: number | null
  gate_e_score?: number | null
  error?: string
}

/** 세션 종료 시 정확히 1회 실행되는 단발성 브리지 — live_guardrail_stdio(세션
 * 내내 살아있는 요청-응답 루프)와 달리 매번 새 프로세스를 스폰하고 종료한다
 * (SPEC-019 REQ-6, agent_evaluator.integrations.live_guardrail_report 참조).
 *
 * executionTime(SPEC-028 REQ-2): 세션 실제 경과 시간(초) — live_guardrail_report.py의
 * 입력 스키마가 이미 이 필드를 받아들이도록 설계돼 있어(execution_time, 기본값 0.0)
 * Python 쪽 변경 없이 여기서 실측값만 채워 넣는다. Gate D(성능계약)의 latency 기반
 * 지표가 이전처럼 상수 0.0이 아니라 실제 세션 길이를 반영하게 된다. */
function recordSessionReport(
  sessionId: string,
  extra: Record<string, unknown>,
  executionTime: number,
): Promise<ReportResult> {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON_BIN, ["-m", "agent_evaluator.integrations.live_guardrail_report"], {
      stdio: ["pipe", "pipe", "inherit"],
    })
    let stdout = ""
    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString()
    })
    proc.on("error", reject)
    proc.on("close", () => {
      try {
        resolve(JSON.parse(stdout.trim()))
      } catch (err) {
        reject(new Error(`[agent-evaluator] live_guardrail_report produced no valid JSON: ${stdout}`))
      }
    })
    proc.stdin.write(
      JSON.stringify({
        task_id: sessionId, extra, output_dir: REPORT_OUTPUT_DIR, execution_time: executionTime,
      }) + "\n",
    )
    proc.stdin.end()
  })
}

/** 세션 하나당 Python 브리지 서브프로세스 하나 — LiveGuardrail의 "세션 스코프
 * 인스턴스, 락 없음" 설계(SPEC-019 REQ-7)와 1:1 대응시킨다. */
class GuardrailSession {
  // stdio: ["pipe", "pipe", "inherit"] — stderr는 부모로 상속되어 파이프되지 않으므로
  // stderr 스트림 타입은 null(ChildProcessWithoutNullStreams가 아님).
  private readonly proc: ChildProcessByStdio<Writable, Readable, null>
  // SPEC-041: id → resolver. 예전엔 순수 FIFO 배열이라, 한 요청이 SEND_TIMEOUT_MS로
  // 취소되면서 pending에서 빠진 뒤 브리지가 (느렸을 뿐) 그 요청의 응답을 늦게 뱉으면
  // shift()가 그걸 *다음* 요청에 배정 → 이후 모든 응답이 한 칸씩 밀려 세션 내내
  // 데스싱크됐다. 이제 요청마다 id를 붙이고 응답의 id로 매칭한다. Map은 삽입 순서를
  // 보존하므로, id 없는(구 브리지) 응답은 가장 오래된 pending으로 FIFO 폴백한다.
  private readonly pending = new Map<number, (msg: any) => void>()
  private seq = 0
  private initPromise: Promise<void>
  // SPEC-041: 브리지가 응답을 안 주고 hang하면 세션이 통째로 멈춘다 — 요청마다
  // 타임아웃을 걸어 {error}로 resolve하고 호출부의 fail-open으로 흘려보낸다.
  private static readonly SEND_TIMEOUT_MS = 5000
  // SPEC-028 REQ-2: 세션 생성 시각 — session.idle 시점에 경과 시간을 계산하는 데 쓴다.
  readonly startedAt: number = Date.now()
  // SPEC-041: 마지막 도구 호출/스냅숏 시각 — 브리지 서브프로세스가 무한정 쌓이지
  // 않도록 getOrCreateSession()에서 가장 오래 논 세션부터 회수하는 데 쓴다.
  lastActivity: number = Date.now()
  // SPEC-041: 직전에 transcript로 알린 위반/차단 건수 — session.idle이 턴마다 오므로,
  // 새 위반이 생겼을 때만 synthetic 요약을 transcript에 덧붙여 컨텍스트 부풀림을 막는다.
  reportedViolationCount = 0

  constructor() {
    this.proc = spawn(PYTHON_BIN, ["-m", "agent_evaluator.integrations.live_guardrail_stdio"], {
      stdio: ["pipe", "pipe", "inherit"],
    })
    // SPEC-041: 브리지가 죽거나 stdout에 비-JSON 줄(스택트레이스 등)을 뱉어도
    // 콜백에서 throw하지 않게 방어한다 — 대기 중인 요청은 파싱 실패를 그대로
    // resolve해서 호출부의 fail-open 경로로 흘려보낸다.
    const rl = readline.createInterface({ input: this.proc.stdout })
    rl.on("line", (line) => {
      let msg: any
      try {
        msg = JSON.parse(line)
      } catch {
        msg = { error: `non-JSON bridge output: ${line.slice(0, 200)}` }
      }
      // 응답에 숫자 id가 있으면(현행 브리지) 오직 그 id로만 매칭한다 — 이미 타임아웃
      // 처리돼 pending에서 빠진 요청의 늦은 응답은 여기서 조용히 버린다(FIFO로
      // 폴백하면 그 늦은 응답이 다음 요청에 잘못 배정되는 바로 그 데스싱크가 난다).
      // id가 아예 없을 때만(구 브리지) 가장 오래된 pending으로 FIFO 폴백한다.
      let key: number | undefined
      if (msg && typeof msg.id === "number") {
        key = this.pending.has(msg.id) ? msg.id : undefined
      } else {
        key = this.pending.keys().next().value
      }
      if (key === undefined) return
      const resolve = this.pending.get(key)!
      this.pending.delete(key)
      resolve(msg)
    })
    const failPending = (reason: string) => {
      for (const resolve of this.pending.values()) resolve({ error: reason })
      this.pending.clear()
    }
    this.proc.on("error", (err) => failPending(`bridge spawn error: ${err}`))
    this.proc.on("exit", (code) => failPending(`bridge exited (code ${code})`))
    // init 실패 시 throw하지 않는다 — initPromise가 reject되면 unhandled rejection이
    // 되거나 check()가 매번 터진다. 대신 로그만 남기고, 이후 check/record send가
    // 죽은 브리지로부터 {error}를 받아 호출부의 fail-open으로 흐르게 둔다.
    this.initPromise = this.send({ op: "init", ...EFFECTIVE_GUARDRAIL_CONFIG }).then((res) => {
      if (!res?.ok) {
        console.error(
          `[agent-evaluator] guardrail init failed — checks will fail-open: ${JSON.stringify(res)}`,
        )
      }
    })
  }

  private send(payload: Record<string, unknown>): Promise<any> {
    const id = ++this.seq
    return new Promise((resolve) => {
      let settled = false
      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        this.pending.delete(id)
        resolve({ error: "bridge response timeout" })
      }, GuardrailSession.SEND_TIMEOUT_MS)
      const entry = (msg: any) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        resolve(msg)
      }
      this.pending.set(id, entry)
      try {
        this.proc.stdin.write(JSON.stringify({ ...payload, id }) + "\n")
      } catch (err) {
        // stdin이 닫혔으면(브리지 사망) 이 요청을 즉시 실패로 resolve — 위 check()의
        // try/catch가 fail-open으로 처리한다.
        clearTimeout(timer)
        this.pending.delete(id)
        if (!settled) {
          settled = true
          resolve({ error: `bridge stdin write failed: ${err}` })
        }
      }
    })
  }

  async check(taskId: string, toolName: string, parameters: unknown): Promise<LiveVerdict> {
    await this.initPromise
    return this.send({ op: "check", task_id: taskId, tool_name: toolName, parameters })
  }

  async record(
    taskId: string, toolName: string, parameters: unknown,
    output?: ToolExecutionOutput,
  ): Promise<void> {
    await this.initPromise
    await this.send({ op: "record", task_id: taskId, tool_name: toolName, parameters, output })
  }

  // SPEC-030 REQ-6: check()가 block=true를 반환했고 이 도구를 실제로 실행하지
  // 않기로 했을 때만 호출한다 — 완전 차단된 시도를 감사 이력에 남긴다.
  async recordBlocked(taskId: string, toolName: string, verdict: LiveVerdict): Promise<void> {
    await this.initPromise
    await this.send({
      op: "record_blocked", task_id: taskId, tool_name: toolName,
      gate: verdict.gate, reason: verdict.reason,
    })
  }

  async snapshot(): Promise<Record<string, unknown>> {
    await this.initPromise
    const res = await this.send({ op: "snapshot" })
    return res.extra
  }

  shutdown(): void {
    this.send({ op: "shutdown" }).finally(() => this.proc.kill())
  }
}

const sessions = new Map<string, GuardrailSession>()

// SPEC-041: OpenCode의 session.idle은 세션당 *여러 번* 발생한다(턴이 끝날 때마다).
// 예전엔 idle마다 endSession()으로 브리지를 죽여, 다음 턴이 빈 이력으로 새 브리지를
// 스폰했다 — 턴을 가로지르는 loop/scope/deadlock 탐지와 max_tool_calls 누적 상한이
// 리셋되고, task_id upsert라 최종 리포트가 "마지막 턴"만 반영(앞 턴의 위반이 지워짐)
// 됐다. 이제 브리지는 세션 내내 살려두고(누적 상태 유지가 원래 설계) idle마다
// 스냅숏+리포트만 upsert한다. 진짜 회수는 dispose/session.error, 그리고 아래
// LRU 상한(장기 데몬에서 브리지 프로세스 무한 증식 방지)에서만 한다.
const MAX_LIVE_SESSIONS = 64

function getOrCreateSession(sessionId: string): GuardrailSession {
  let session = sessions.get(sessionId)
  if (!session) {
    if (sessions.size >= MAX_LIVE_SESSIONS) {
      let oldestId: string | undefined
      let oldest = Infinity
      for (const [id, s] of sessions) {
        if (s.lastActivity < oldest) { oldest = s.lastActivity; oldestId = id }
      }
      if (oldestId !== undefined) {
        console.error(`[agent-evaluator] MAX_LIVE_SESSIONS reached — reaping idle session ${oldestId}`)
        endSession(oldestId)
      }
    }
    session = new GuardrailSession()
    sessions.set(sessionId, session)
  }
  session.lastActivity = Date.now()
  return session
}

function endSession(sessionId: string): void {
  const session = sessions.get(sessionId)
  if (session) {
    session.shutdown()
    sessions.delete(sessionId)
  }
}

/** snapshot extra에서 세션 누적 "나쁜 신호" 총계 — session.idle이 턴마다 오므로,
 * 이 값이 지난번보다 늘었을 때만 synthetic 요약을 transcript에 덧붙인다(SPEC-041). */
function countGuardrailViolations(extra: Record<string, any>): number {
  let n = 0
  n += Array.isArray(extra?.blocked_attempts) ? extra.blocked_attempts.length : 0
  if (extra?.loop_detection?.detected) n += 1
  if (extra?.deadlock?.deadlock_detected) n += 1
  if (extra?.scope && extra.scope.in_scope === false) {
    n += Array.isArray(extra.scope.violations) ? extra.scope.violations.length : 1
  }
  n += Array.isArray(extra?.tool_parameter_safety?.dangerous_calls)
    ? extra.tool_parameter_safety.dangerous_calls.length : 0
  n += typeof extra?.tool_authorization?.total_violations === "number"
    ? extra.tool_authorization.total_violations : 0
  if (extra?.privilege_escalation?.escalation_detected) n += 1
  if (extra?.tool_chain_attack?.is_suspicious_chain) n += 1
  return n
}

/** Gate B/E extra에서 실제 위반/이상 신호만 뽑아 사람이 읽을 수 있는 요약을 만든다.
 * 점수만 남기면 다음 세션의 모델이 "무엇이 잘못됐는지" 알 수 없으므로, 위반 종류·
 * 대상 도구까지 구체적으로 적는다 — ctx가 이 텍스트를 그대로 색인해 다음 세션
 * 검색 결과로 노출한다. */
function summarizeGuardrailResult(
  sessionId: string,
  extra: Record<string, any>,
  report: ReportResult,
): string {
  const lines: string[] = [
    `[agent-evaluator] Gate B/E guardrail summary (session ${sessionId})`,
    `Gate B score: ${report.gate_b_score ?? "n/a"} / Gate E score: ${report.gate_e_score ?? "n/a"}`,
  ]

  const loop = extra.loop_detection
  if (loop?.detected) {
    lines.push(`- loop_detection: ${loop.loop_type} on tool "${loop.loop_tool}"`)
  }
  const deadlock = extra.deadlock
  if (deadlock?.deadlock_detected) {
    lines.push(`- deadlock: ${deadlock.deadlock_type}`)
  }
  const scope = extra.scope
  if (scope && scope.in_scope === false) {
    lines.push(`- scope violation: ${JSON.stringify(scope.violations)}`)
  }
  const tps = extra.tool_parameter_safety
  if (tps?.dangerous_calls?.length) {
    lines.push(`- dangerous tool parameters: ${JSON.stringify(tps.dangerous_calls)}`)
  }
  const ta = extra.tool_authorization
  if (ta && ta.total_violations > 0) {
    lines.push(
      `- tool_authorization violations: ${ta.total_violations} ` +
        `(unauthorized=${ta.unauthorized_calls}, restricted=${ta.restricted_calls}, ` +
        `dangerous_params=${ta.dangerous_param_calls})`,
    )
  }
  const pe = extra.privilege_escalation
  if (pe?.escalation_detected) {
    lines.push(`- privilege_escalation: ${pe.initial_privilege} -> ${pe.max_privilege} (path: ${JSON.stringify(pe.escalation_path)})`)
  }
  const tc = extra.tool_chain_attack
  if (tc?.is_suspicious_chain) {
    lines.push(`- tool_chain_attack: ${JSON.stringify(tc.attack_patterns_detected)}`)
  }

  if (lines.length === 2) {
    lines.push("- no violations detected")
  } else {
    // SPEC-024 REQ-5: 로컬 소형 모델은 도구 이름이 프롬프트에 명시적으로 언급돼야
    // 자율 호출을 신뢰할 수 있음을 라이브 검증으로 확인했다(2026-07-05, ctx skill
    // 재검증 — 언급 없이는 스킵/MCP 도구를 전혀 안 씀). 이 문구를 transcript 자체에
    // 심어 다음 세션의 컨텍스트에 도구 이름을 자연스럽게 노출시켜 이 제약을 완화한다.
    lines.push("- 다음 세션에서 유사한 시도를 하기 전에 search_violations 도구로 이 사유를 검색해 확인하라.")
  }
  if (!report.ok) {
    lines.push(`- (batch report save failed: ${report.error})`)
  }
  return lines.join("\n")
}

/** Gate B/E 판정 요약을 실제 세션 메시지 히스토리에 synthetic 텍스트 파트로 기록한다
 * (`noReply: true`라 LLM 응답을 유발하지 않는다). 이게 세션 transcript로 영구
 * 저장되므로 ctx가 다음 색인 시 그대로 주워간다 — SPEC-019가 원래 의도한 자가교정
 * 피드백 루프의 핵심 고리. */
async function recordVerdictToTranscript(
  client: PluginInput["client"],
  sessionId: string,
  summaryText: string,
): Promise<void> {
  try {
    const result = await client.session.prompt({
      path: { id: sessionId },
      body: {
        noReply: true,
        parts: [{ type: "text", text: summaryText, synthetic: true }],
      },
    })
    if (result.error) {
      console.error(`[agent-evaluator] failed to write verdict to session ${sessionId} transcript:`, result.error)
    }
  } catch (err) {
    console.error(`[agent-evaluator] failed to write verdict to session ${sessionId} transcript:`, err)
  }
}

/** session.idle: 세션의 현재까지 누적된 Gate B/E extra를 스냅숏해 배치 리포트로
 * upsert하고, 새 위반이 있으면 그 요약을 세션 transcript에 덧붙인다(SPEC-019 REQ-6 +
 * ctx 피드백 루프). session.idle은 턴마다 오므로 여기서 세션을 종료하지 않는다
 * (SPEC-041) — 브리지는 dispose/session.error/LRU 상한에서만 회수한다. */
async function handleSessionIdle(client: PluginInput["client"], sessionId: string): Promise<void> {
  const session = sessions.get(sessionId)
  if (!session) return
  session.lastActivity = Date.now()
  try {
    const extra = await session.snapshot()
    // SPEC-028 REQ-2: 세션 전체 경과 시간(초) — 도구 호출 사이 유휴 시간을 포함한
    // 세션 생성~종료 시점 간 차이다(정확한 순수 실행 시간이 아님, 문서 참고).
    const executionTime = (Date.now() - session.startedAt) / 1000
    const result = await recordSessionReport(sessionId, extra, executionTime)
    if (result.ok) {
      console.log(
        `[agent-evaluator] session ${sessionId} recorded to ${result.saved_to} ` +
          `(Gate B=${result.gate_b_score ?? "n/a"}, Gate E=${result.gate_e_score ?? "n/a"})`,
      )
    } else {
      console.error(`[agent-evaluator] failed to record session ${sessionId}: ${result.error}`)
    }
    // session.idle은 턴마다 오므로, 깨끗한 세션에 매 턴 "위반 없음" synthetic 파트를
    // 붙이면 컨텍스트만 부풀린다. 차단/위반 총계가 지난번보다 늘었을 때만 기록한다.
    const violationCount = countGuardrailViolations(extra)
    if (violationCount > session.reportedViolationCount) {
      session.reportedViolationCount = violationCount
      const summary = summarizeGuardrailResult(sessionId, extra, result)
      await recordVerdictToTranscript(client, sessionId, summary)
    }
  } catch (err) {
    console.error(`[agent-evaluator] failed to record session ${sessionId}:`, err)
  }
  // SPEC-041: endSession()을 여기서 하지 않는다 — session.idle은 턴마다 오므로
  // 브리지를 살려둬야 다음 턴이 누적 이력을 이어받는다. 회수는 dispose /
  // session.error / getOrCreateSession()의 LRU 상한에서만.
}

export const AgentEvaluatorGuardrail: Plugin = async ({ client }) => {
  return {
    "tool.execute.before": async (input, output) => {
      const sessionId = input.sessionID
      let verdict: LiveVerdict
      try {
        const session = getOrCreateSession(sessionId)
        verdict = await session.check(sessionId, input.tool, output.args)
      } catch (err) {
        // SPEC-041: fail-open — 파이썬 브리지 인프라 오류(패키지 미설치, 서브프로세스
        // 사망, 손상된 응답 등)가 세션의 *모든* 도구 호출을 막아버리면 안 된다.
        // claude_code_hook.run()의 예외=fail-open 원칙과 동일. verdict.block==true인
        // "실제 판정"일 때만 차단한다.
        console.error(`[agent-evaluator] guardrail check failed — allowing tool "${input.tool}": ${err}`)
        return
      }
      if (verdict.block) {
        // SPEC-030 REQ-6: 이 시도를 실제로 실행하지 않기로 확정하는 지점 —
        // 에러를 던지기 전에 감사 이력에 기록한다.
        try {
          await getOrCreateSession(sessionId).recordBlocked(sessionId, input.tool, verdict)
        } catch (err) {
          console.error(`[agent-evaluator] recordBlocked failed: ${err}`)
        }
        // 이 에러 메시지가 다음 턴 컨텍스트에 노출되어 로컬 모델(qwen-code 등)의
        // 자가 교정 신호가 된다 — SPEC-019 Context 참조.
        throw new Error(`[agent-evaluator] blocked by Gate ${verdict.gate}: ${verdict.reason}`)
      }
    },

    "tool.execute.after": async (input, output) => {
      // input.args (output.args 아님) — 위 파일 상단 주석 2번 참조.
      // SPEC-031 REQ-3: output.output(타입 보장)을 stdout으로, output.metadata(any —
      // 미검증, extractToolExecutionOutput() 주석 참조)에서 best-effort로 exit code를
      // 뽑아 Gate G(ToolCallAnalyzer)가 실제 성공/실패를 반영하게 한다.
      // SPEC-041: 기록 실패가 세션을 깨면 안 되므로 삼킨다(fail-open).
      try {
        const sessionId = input.sessionID
        const session = getOrCreateSession(sessionId)
        await session.record(sessionId, input.tool, input.args, extractToolExecutionOutput(output))
      } catch (err) {
        console.error(`[agent-evaluator] tool.execute.after record failed: ${err}`)
      }
    },

    // session.idle/session.error는 독립 훅이 아니라 이 단일 event 훅으로 전달된다.
    event: async ({ event }: { event: Event }) => {
      if (event.type === "session.idle") {
        await handleSessionIdle(client, event.properties.sessionID)
      } else if (event.type === "session.error") {
        const sessionId = event.properties.sessionID
        if (sessionId) endSession(sessionId)
      }
    },

    // OpenCode가 플러그인을 정상 언로드할 때 남아있는 세션 서브프로세스를 전부 정리한다.
    dispose: async () => {
      for (const sessionId of [...sessions.keys()]) {
        endSession(sessionId)
      }
    },
  }
}

export default AgentEvaluatorGuardrail
