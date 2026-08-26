# ctx 세션 검색 — 선택적 개인 워크플로우 (Agent-Evaluator 비의존성)

`ctx`(https://github.com/ctxrs/ctx)는 Claude Code·OpenCode 등 여러 코딩 에이전트 도구의 과거
세션을 로컬에서 인덱싱·검색하는 별도 오픈소스 CLI다. Agent-Evaluator의 Gate 채점·LiveGuardrail·
RCA(`diagnose`)·A/B(`abtest`) 중 어느 것도 ctx에 의존하지 않는다 — 이 문서는 그 네 기능을
**사람이 필요할 때만 수동으로 pivot하는 개인용 보조 워크플로우** 3가지를 기록한다.

> **범위**: 실시간(같은 세션 안) 문맥 보강은 검토 후 기각했다 — [하지 않는 것](#하지-않는-것-범위-제외--이유)
> 참고. 여기 남은 건 세션을 넘나드는 회고적(retrospective) 조사 용도 3가지뿐이다.

---

## 사전 확인된 사실 (이 프로젝트에서 실측, 2026-08-26 기준)

- ctx는 이미 이 프로젝트의 Claude Code 세션을 인덱싱하고 있다(`~/.claude/projects` 소스,
  provider `claude`) — 이 환경의 `ctx status` 기준 211개 세션·108,301개 이벤트.
- **[AOO_STACK.md의 "ctx self-correction feedback loop"](AOO_STACK.md#ctx-self-correction-feedback-loop)
  절이 이미 라이브 검증한 제약과 다른 provider라는 점에 주의**: 그 절은 ctx(v0.19.0 기준)의
  **OpenCode** 임포터가 세션 **메타데이터(제목·토큰 수)만** 가져오고 실제 메시지/tool_call
  내용은 가져오지 못한다는 걸 발견했다(그래서 `search_violations`가 그 갭을 대신 메운다). 이
  문서를 쓰기 위해 이 프로젝트의 로컬 인덱스(`~/.ctx/work.sqlite`)를 SQL로 직접 조회해 확인한
  결과, **Claude Code 임포터는 다르다** — `tool_call`/`message` 이벤트에 실제 명령어 텍스트·대화
  원문이 들어있다(메타데이터뿐만이 아니다).
- 다만 **전부 다 온전히 저장되는 건 아니다** — 이벤트마다 `content_retention` 값이 갈린다:
  - `message`(대화 원문): 약 절반 정도가 `full_text`로 온전히 남아있고, 나머지는 태그 없음.
  - `tool_call`(실행한 명령): 명령어 프리뷰는 들어있지만 `full_text` 라벨은 전혀 없다(길이 캡 있음).
  - `tool_output`(stdout/stderr 결과): `full_text`가 전혀 없고 `metadata_only`/실패 시 프리뷰뿐이다.
  - **결론**: "어떤 프롬프트·명령으로 이 코드를 썼는지" 검색·확인 용도로는 쓸 만하지만, **tool 실행
    결과(stdout) 전문을 ctx로 복원하는 건 기대하지 말 것** — 그게 필요하면 Agent-Evaluator 자체의
    `record_tool_call(output=...)`/`search_violations`(SPEC-031/024)를 쓴다.
  - 이 결과는 ctx 버전·설정이 바뀌면 달라질 수 있다 — 재검증 없이 그대로 신뢰하지 말 것.

## 사전 준비

- ctx CLI/MCP가 이미 설치·인덱싱돼 있어야 한다(`ctx status`로 확인). 미설치 시
  https://github.com/ctxrs/ctx 참고 — **Agent-Evaluator의 pip 설치 대상이 아니다**
  (`pip install agent-evaluator[...]` 어떤 extra에도 포함되지 않는다).
- Claude Code 세션 안에서 ctx가 MCP 서버로 연결돼 있으면 `search`/`show_event`/`show_session`/
  `sources`/`sql`/`status` 도구를 대화 중 바로 요청해 쓸 수 있다. CLI로 직접 쓰려면 `ctx search`/
  `ctx show session`/`ctx blame` 형태.

---

## 워크플로우 A — Gate 회귀 → git 커밋 → 원본 세션 역추적

`agent-eval diagnose`가 회귀 원인 후보를 지목한 뒤, "그 코드를 실제로 누가 어떤 판단으로 썼는지"
원문 대화까지 보고 싶을 때.

1. `agent-eval diagnose results/latest.json --baseline results/baseline.json --show-diff` 로
   회귀 원인 후보와 관련 git 커밋을 확인한다.
   ([05_QUALITY_GATE.md §8](05_QUALITY_GATE.md#8-gate-회귀-원인진단-agent-eval-diagnose))
2. 지목된 커밋이 건드린 파일/라인을 `git show <commit> --stat`으로 좁힌다.
3. `ctx blame file <path> --lines <start:end>` (또는 Claude Code 세션 안에서 ctx MCP 도구로
   동일 조회)로 그 라인을 쓴 세션을 찾는다.
4. `ctx show session <id>` 로 그 세션의 실제 대화를 확인한다 — 위 제약대로 tool 실행 결과 전문은
   기대하지 말고, 어떤 프롬프트·추론으로 그 코드를 썼는지(메시지 텍스트) 확인하는 용도로 쓴다.
5. 이 전체 과정은 **사람이 수동으로 진행하는 회고적 조사**다. `diagnose`는 ctx를 자동 호출하지
   않는다 — HOTL 원칙과 "외부 의존성 없는 코어" 원칙을 그대로 유지한다.

`agent_version="auto"`가 세션 실행 시점의 git commit SHA를 자동 태깅해두므로, Agent-Evaluator로
계측된 세션은 이미 `diagnose` 결과 안에 커밋 정보가 있다 — ctx가 필요한 지점은 딱 "그 커밋을 누가/
어떤 대화로 썼는지" 역추적할 때뿐이다.

---

## 워크플로우 B — 골든셋 원료 채굴 (계측 안 된 과거 세션에서)

`agent-eval dataset build --source results/`(`GoldenSetBuilder`)는 `PerformanceMonitor`로 이미
계측된 세션만 본다. `@agent_eval` 없이 진행된 일반 Claude Code 대화 중에서 좋은/나쁜 사례를 찾고
싶을 때.

1. `ctx search "<키워드>"`(또는 Claude Code 세션 안에서 ctx MCP `search` 도구)로 후보 세션을
   탐색한다.
2. 후보로 나온 세션을 `ctx show session <id>`로 열어 질문/답변/맥락을 사람이 직접 확인·발췌한다.
3. 발췌한 내용을 [04_DATA_GUIDE.md의 QAPair 구조](04_DATA_GUIDE.md#2-qapair-구조)
   (`qa_id`/`question`/`answer`/`context`/`ground_truth`/`metadata`)에 맞춰 **사람이 직접**
   `data/golden_datasets/*.json`에 항목으로 추가한다. ctx 결과가 `GoldenSetBuilder` 파이프라인에
   자동으로 들어가는 연결고리는 없다 — 만들지 않았고, 현재 계획도 없다.
4. 이후는 기존 파이프라인 그대로 따른다. `GoldenSetBuilder.extract(require_human_review=True)`가
   기본값인 것과 동일한 원칙으로, ctx로 채굴한 후보도 반드시 사람 검토를 거친 뒤 확정한다.

---

## 워크플로우 C — A/B 비교 후보 발굴

`agent-eval abtest`는 이미 `results/`에 있는 두 결과 JSON을 통계적으로 비교할 뿐, "비교할 만한 두
실행"을 찾아주지는 않는다.

1. `ctx search`로 같은 작업을 다른 시점/설정으로 반복한 세션 쌍의 후보를 찾는다.
2. 사람이 두 세션이 실제로 비교 가능한지(같은 태스크, 다른 프롬프트/설정) 확인한다.
3. 확인되면 그 두 실행을 `prompt_version`/`agent_version`을 다르게 지정해 `@agent_eval`/
   `PerformanceMonitor`로 정식 재계측하거나, 이미 결과 JSON이 있다면 그대로
   `agent-eval abtest v1.json v2.json --metric accuracy_score`로 통계 검증한다.

---

## 하지 않는 것 (범위 제외 — 이유 포함)

- **실시간 훅 문맥 보강(RCA 즉시 확인, LiveGuardrail 차단 직후 문맥)** — 검토 후 기각했다. Claude
  Code 공식 문서가 훅 시점 `transcript_path`는 "최신 턴이 누락될 수 있어 mid-turn 참조 비권장"이라고
  명시하며, ctx도 결국 세션 종료 후에야 인덱싱하는 오프라인 도구라 실시간 훅 안에서는 어차피 못 쓴다.
  실시간 차단 문맥은 `LiveGuardrail`이 이미 기록하는 `{tool_name, gate, reason, detail}`로 충분하다고
  판단했다.
- **Agent-Evaluator 코어에 ctx를 의존성으로 추가** — "레이어 독립성/외부 의존성 없는 코어" 원칙과
  충돌한다. 여기 문서화된 3가지는 전부 사람이 수동으로 pivot하는 개인 도구 워크플로우이며, 어떤
  Agent-Evaluator 코드도 ctx를 호출하지 않는다.
- **ctx 결과를 파이프라인에 자동 연결**(`diagnose --show-diff` 자동 확장, `GoldenSetBuilder` 자동
  소스 추가 등) — 코드 변경 없음. 근거가 아직 부족하다고 판단했다(필요해지면 재검토).

---

| 목적 | 문서 |
|------|------|
| Gate 회귀 원인진단 | [05_QUALITY_GATE.md §8](05_QUALITY_GATE.md#8-gate-회귀-원인진단-agent-eval-diagnose) |
| 골든 데이터셋 구조 | [04_DATA_GUIDE.md](04_DATA_GUIDE.md) |
| 통계적 A/B 테스트 | [08_API_REFERENCE.md](08_API_REFERENCE.md) |
| OpenCode 실시간 가드레일 + ctx 피드백 루프의 기존 라이브 검증 | [AOO_STACK.md](AOO_STACK.md#ctx-self-correction-feedback-loop) |
