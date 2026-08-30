# CLAUDE.md — Agent-Evaluator

## Project Overview

**Agent-Evaluator** is a Harness Engineering-based AI agent deployment readiness evaluation SDK that determines whether an agent is ready for production via **7 Harness Gates (A–G)**.

- **Gate A** — Goal Achievement | **Gate B** — Behavioral Integrity | **Gate C** — Reliability
- **Gate D** — Performance Contract | **Gate E** — Security Boundary | **Gate F** — Multi-Agent Coordination | **Gate G** — Observability

**25 Native Trackers + 33 Harness Config = 58 metrics** across 3 layers (Foundation / Agentic / Hybrid).

- **Version:** 1.0.0-rc4 | **Python:** 3.8+ | **License:** MIT | **Author:** Sungwoo Kim

---

## Common Commands

```bash
# Dev environment
pip install -e ".[dev]"
pip install -e ".[sdk]"       # dashboard + OTEL + LLMJudge + PDF (recommended)
pip install -e ".[examples]"  # all examples runnable (sdk + eval)
pip install -e ".[mcp]"       # search_violations MCP server (agent_evaluator.integrations.violation_search_mcp)

# CLI
agent-eval init                                           # API key setup wizard
agent-eval check                                          # config status
agent-eval --version                                      # version info
agent-eval dashboard                                      # FastAPI dashboard (port 8765)
agent-eval gate result.json --tcr 85 --accuracy 70        # CI/CD quality gating
agent-eval gate result.json --baseline-version v2-cot --fail-on-regression 10   # per-version baseline
agent-eval gate result.json --golden-set data/golden_datasets/golden_1.json --fail-on-golden-regression  # golden-set gate, exit 3
agent-eval diagnose result.json --baseline baseline.json   # Gate regression RCA (not a CI gate, informational only)
agent-eval abtest v1.json v2.json --metric accuracy_score   # statistical A/B (Welch's t-test), not a CI gate
agent-eval abtest v1.json v2.json --sequential --tau 0.05   # mSPRT always-valid inference (safe to peek)
agent-eval abtest v1.json v2.json v3.json                   # 3+ files -> N-way + Benjamini-Hochberg FDR
agent-eval dataset build --source results/ --max-cases 30 # golden dataset
agent-eval monitor                                        # Arize Phoenix + OTLP
agent-eval opencode install                               # LiveGuardrail OpenCode plugin (--global/--force)
agent-eval opencode install --with-violation-search       # + register search_violations MCP server (requires [mcp] extra)
agent-eval opencode install --with-recommend-fix           # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval opencode upgrade                               # re-copy the plugin .ts after a package update (keeps agent-evaluator.config.json)
agent-eval opencode doctor                                # verify the install works: plugin freshness + Python stdio-bridge round-trip (--json/--no-live/--strict)
agent-eval opencode uninstall                             # remove plugin file + opencode.json mcp entries (run BEFORE pip uninstall; --purge/--dry-run/--yes)
agent-eval claude install                                 # LiveGuardrail Claude Code CLI hooks (--global/--force)
agent-eval claude install --with-violation-search         # + register search_violations MCP server (requires [mcp] extra)
agent-eval claude install --with-recommend-fix             # + register recommend_fix MCP server (requires [mcp] extra)
agent-eval claude upgrade                                 # refresh hooks/matchers + deep-merge NEW guardrail_config.json keys (keeps your edits); --with-* re-registers MCP
agent-eval claude doctor                                  # verify the install works: static checks + live hook round-trip (allow/deny/batch-report) + MCP handshake (--json/--no-live/--strict)
agent-eval claude uninstall                               # remove our hooks from settings.json + deregister MCP + delete session state (run BEFORE pip uninstall; --keep-config/--purge/--dry-run/--yes)
agent-eval trend results/ --fail-on-regression            # trend analysis (회귀 시 첫/마지막 run의 lineage.git_commit 사이 코드 diff 자동 첨부, --repo-path)
agent-eval trend results/ --output-json trend.json
agent-eval claims add src/ --developer auto                # open a .aoo/claims.jsonl scope claim
agent-eval claims list                                     # show active claims
agent-eval claims release c-a1b2c3d4                       # release a claim
agent-eval claims audit --ttl-hours 8                      # CI: flag TTL-exceeded/overlapping claims

# Quality
pytest
ruff check agent_evaluator/
ruff format agent_evaluator/
mypy agent_evaluator/

# Build
python -m build
twine upload dist/*
```

---

## Architecture

### 3-Layer Structure

```
Layer 1 — Foundation (no external deps)
  TaskCompletionTracker · AccuracyEvaluator · HallucinationDetector
  ResponseQualityEvaluator · LatencyTracker · TokenEconomyTracker
  MultimodalMetricsTracker

Layer 2 — Agentic (no external deps)
  ToolCallAnalyzer · RetryCorrectionTracker · ToolSelectionTracker
  AgentCoordinationTracker · WorkflowExecutionTracker
  Security: InputSanitizationTracker · OutputLeakageDetector
           ToolAuthorizationTracker · PrivilegeEscalationDetector · ToolChainAttackDetector

Layer 3 — Hybrid (optional deps: DeepEval / Ragas)
  HybridPerformanceMonitor · DeepEvalAdapter · RagasAdapter
  LLMJudge (native — faithfulness, G-Eval replacement, 5-dim scoring)
```

**25 Native Tracker inventory** (Layer 1/2 above = 17 Gate-relevant trackers + 8 operational-support trackers below):

```
Operational support (8, no direct Gate score contribution — report/ops only)
  ImplicitFeedbackTracker · ConversationSession · ConversationMetrics · AnomalyDetector
  CostTracker · AdaptivePolicy · SamplingStage · StreamingEvaluator
```

> 7 (Layer 1) + 5 (Layer 2 agentic) + 5 (Layer 2 security) + 8 (operational support) = **25**.
> `LLMJudge` (Layer 3/Hybrid) and `AlertEngine` (`alerts/` — alerting infra, not a tracker) are **not** among
> the 25 — a common miscount. `Media/Book/Appendix/A_58개지표_레퍼런스.md` is the reader-facing enumeration
> of all 25 — keep it in sync with this list.

### Key Files

```
agent_evaluator/
├── decorators.py          # agent_eval · batch_eval · conversation_eval
│                          # 33개 Harness Config는 gates/gate_x/configs.py에 정의되고 여기는 re-export만 함
│                          # EvalMetadata · TurnMetadata · EvalDecorator · AlertRuleBuilder
├── gates/                 # Gate 단위 패키지 — A~G 전체 7개 Gate
│   ├── base.py            # 전 Gate 공유 인프라 — _min_sample_warning · _status · _g ·
│   │                       #  _gate_pass_verdict()(단일 Gate pass/fail 공식) ·
│   │                       #  evaluate_gate_scores()(HarnessEvaluationGate·QuickEval.gate()·
│   │                       #  cli/gate.py가 공유하는 Gate 판정 루프 — 아래 HarnessEvaluationGate 참고)
│   ├── shared_metrics.py  # RunningAverage 등 7개 running-aggregate 원시 타입 + Gate별 8개 SharedAgg 클래스
│   ├── live_guardrail.py  # LiveVerdict · LiveGuardrail — 배치 Gate와 동일한 Behavioral/Security
│   │                       #  체크를 실행 전 단일 tool call 단위로 동기 호출
│   │                       #  LiveVerdict.remediation(SPEC-041 P1.3) — block=True이고 미지정이면
│   │                       #  __post_init__이 reason에서 자동 도출한다(_derive_remediation:
│   │                       #  reason 접두어→COMPONENT_GUIDANCE 키 매핑 + "반복 말고 접근 바꿔라 +
│   │                       #  recommend_fix/search_violations MCP 써라" 꼬리말). block=False면 항상
│   │                       #  None. dataclasses.asdict로 stdio 브리지·Claude 훅
│   │                       #  (permissionDecisionReason)·OpenCode 에러 메시지에 그대로 실려 나가
│   │                       #  "무엇이 막혔나"에 더해 "그래서 뭘 하라"를 에이전트에 전달한다.
│   │                       #  record_blocked_attempt() — check_before_tool_call()이 block=True를
│   │                       #  반환한 시도를 호출자가 명시적으로 감사 이력(blocked_violations)에 기록
│   │                       #  record_tool_call(output=...) — success/exit_code/stdout/stderr
│   │                       #  옵트인 전달, max_tool_output_chars로 truncate. 미지정 시 회귀 없음
│   │                       #  live_loop_window(기본 15) — check_before_tool_call()의 루프
│   │                       #  판정을 최근 N호출 트레일링 윈도우로만 한정(세션 초반 반복 하나가
│   │                       #  세션 전체를 막는 latch 방지). None이면 전체 이력(구 동작).
│   │                       #  snapshot()/배치 경로는 항상 전체 이력을 본다 — 이 축소는 실시간 전용
│   │                       #  live_loop_blocking_types(기본 ("consecutive_repeat",)) —
│   │                       #  on_loop_detected="fail"이어도 이 타입만 차단. window_duplicate/
│   │                       #  response_similarity는 소프트 신호라 fail이어도 통과(snapshot엔 남음)
│   │                       #  SPEC-041: 루프 판정은 도구 *이름*이 아니라 (이름 + 정렬된 인자
│   │                       #  JSON, 길면 전체 SHA1)으로 동일성을 따진다 — Claude "Bash"/"Edit",
│   │                       #  OpenCode "bash"처럼 굵은 도구를 서로 다른 인자로 8번 이어 호출한
│   │                       #  정상 작업(npm test→git status→ls, 연속 편집)이 consecutive_repeat로
│   │                       #  오탐되던 것 방지. *완전히 동일한* 호출 반복만 루프. 실시간
│   │                       #  (check)뿐 아니라 snapshot()/배치 리포트도 같은 식별자를 쓴다
│   │                       #  — 이름 기준이면 정상 세션이 loop_detection.detected=True로 잡혀
│   │                       #  Gate B 점수를 떨어뜨려 CI `agent-eval gate`가 오탈락시켰다.
│   │                       #  긴 인자는 앞부분만 자르지 않고 전체 SHA1(접두어만 같고 뒤가
│   │                       #  다른 연속 편집의 오탐 collision 방지). _loop_call_identity() 참고.
│   │                       #  합성 식별자는 verdict.detail·snapshot 출력에 새지 않도록
│   │                       #  _clean_loop_result()가 loop_tool·detected_loops[].loop_tool을
│   │                       #  사람이 읽을 이름으로 되돌린다(check + snapshot 공유).
│   │                       #  auth_scan_skip_keys(기본: Claude Write/Edit/NotebookEdit의
│   │                       #  content/old_string/new_string/new_source, OpenCode edit/patch의
│   │                       #  oldString/newString/patchText, MCP의 file_text/edits/diff/oldText/
│   │                       #  newText, TodoWrite의 todos 등) — tool_authorization 하드코딩 백스톱
│   │                       #  (rm -rf/sudo/eval(/DROP TABLE…, 커스터마이즈 불가)이 모든 파라미터
│   │                       #  JSON을 스캔하는데, *파일 본문*에 위 문자열이 있으면(README의 sudo,
│   │                       #  배포 스크립트의 rm -rf, SQL의 DROP TABLE 등) 정상 파일 생성이 통째로
│   │                       #  차단되던 걸 막는다. 이 키들의 값은 백스톱 스캔에서 제외(check + record
│   │                       #  양쪽). ()면 옛 동작. 파일에 위험 명령을 쓰는 것 자체는 무해(실행돼야
│   │                       #  위험, 실행은 Bash에서 잡힘)
│   │                       #  SPEC-041: check_before_tool_call()의 tool_parameter_safety 검사는
│   │                       #  *이번 호출만* 스캔한다(과거 _candidate 전체 아님) — 세션 길이에
│   │                       #  비례한 O(n²) 재스캔과, 과거 위험 호출 하나가 이후 전부를 막는 latch
│   │                       #  방지. scope도 forbidden_tools/allowed_tools만이면 이번 호출만 보고,
│   │                       #  max_tool_calls/max_unique_tools(누적 상한)가 설정된 경우에만 이력
│   │                       #  전체를 본다. deadlock/privilege_escalation/tool_chain_attack은
│   │                       #  체인 전체가 필요해 이력 기준 유지(오탐 시 circuit breaker가 해제).
│   │                       #  snapshot()/배치는 여전히 전체 이력을 본다.
│   │                       #  lenient_shell_file_write(기본 True) — cat/tee/echo/printf가
│   │                       #  리다이렉트(>,>>)·heredoc(<<)·`producer | tee [-a] FILE`(1단계
│   │                       #  파이프, `| sudo tee /etc/…` 포함)로 파일을 만들고, 껍데기(heredoc
│   │                       #  본문·따옴표·fd리다이렉트·`>/dev/null` 제거, `|` 분리 후 세그먼트)에
│   │                       #  `` ` `` `$(` `;` `&&` `||` `<(` `>(` 백그라운드 `&`가 하나도 없으면,
│   │                       #  명령 안의 rm -rf/sudo/DROP TABLE 등은 파일 *내용*이므로
│   │                       #  dangerous_patterns/백스톱을 건너뛴다(Write와 동일 취급). 따옴표 없는
│   │                       #  <<EOF 본문의 $( )·백틱은 실행되므로 예외. `echo x | tee f | sh`(2단계
│   │                       #  파이프)·`cat > >(sh)`(프로세스치환)은 여전히 스캔·차단.
│   │                       #  _is_benign_shell_file_write() 참고. record_tool_call은 benign
│   │                       #  write에 _benign_write=True 표식 → snapshot()의 tool_parameter_safety
│   │                       #  스캔에서 제외(실시간 allow와 배치 리포트 점수 일치). loop 식별자는
│   │                       #  원본 arguments 그대로 사용.
│   │                       #  team_concurrency/branch_guard의 scoped_tool_names 매칭은 대소문자
│   │                       #  무시(_tool_in) — OpenCode "bash"/"edit" ↔ Claude "Bash"/"Edit".
│   │                       #  기본 scoped_tool_names·path_param_candidates도 양쪽 표기 모두 포함
│   │                       #  (file_path/notebook_path 등). 과거엔 소문자 기본값이라 Claude Code
│   │                       #  훅에서 두 기능이 조용히 미발화했다.
│   │                       #  privilege_escalation/tool_chain_attack의 peek-후-복원은 [:-1] 대신
│   │                       #  호출 전 길이로 슬라이스 — analyze_*가 safe-workflow whitelist 등으로
│   │                       #  조기 반환해 append 안 할 때 이전 항목이 지워지던 버그 수정.
│   │                       #  protected_write_paths(기본: ~/.ssh·셸 rc(.bashrc/.zshrc/.profile)·
│   │                       #  ~/.aws/credentials·~/.gnupg·/etc·/usr·/bin·크론·LaunchAgents 등
│   │                       #  regex 리스트) — 파일 *위치*가 민감하면 도구·내용과 무관하게
│   │                       #  Gate E로 차단(benign 셸 쓰기여도). Write/Edit/NotebookEdit/MCP-write는
│   │                       #  파라미터 키(file_path/filePath/path/notebook_path)에서, 순수 셸
│   │                       #  쓰기는 `> TARGET`/`tee TARGET`을 파싱해 대상 추출. 프로젝트
│   │                       #  `.git/hooks/`는 의도적으로 목록에서 제외(정상 셋업). None/[]이면 끔.
│   │                       #  _extract_write_targets()/_protected_write_hit() 참고.
│   │                       #  대상 파싱: `> "..."` `> '...'` `> $HOME/x` `tee "..."` +
│   │                       #  `sed -i FILE`/`perl -pi FILE`/`cp x DEST`/`mv x DEST`/`dd of=DEST`/
│   │                       #  `ln -sf t LINK`/`install ... DEST`/`truncate FILE`/`rsync ... DEST`
│   │                       #  (`> FILE` 대신 이걸로 민감 경로에 쓰는 우회를 잡음). `a;b&&c`는
│   │                       #  세그먼트별 검사, `sudo`/`time`/`env X=y` 접두 허용. cp/mv는 목적지
│   │                       #  (마지막 인자)만 봐서 `cp ~/.ssh/config /tmp`(read from protected)는 통과.
│   │                       #  견고성(SPEC-041): tool_name이 None/비-str이어도 str로 정규화(.lower
│   │                       #  크래시 방지), record_tool_call의 output이 dict가 아니면 무시
│   │                       #  ('stdout' in "…stdout…" substring 후 TypeError 나던 것), branch_guard
│   │                       #  json.dumps는 default=str+try/except. load_active_claims는 손상된
│   │                       #  claims.jsonl 줄을 건너뛴다(한 줄 오류가 LiveGuardrail 생성을 안 깬다).
│   │                       #  team_concurrency=TeamConcurrencyConfig(...) — 생성자 시점 1회
│   │                       #  로드한 .aoo/claims.jsonl로 read/edit/write 스코프 겹침 자동 차단
│   │                       #  (bash 제외), refresh_team_claims()로 수동 재조회
│   │                       #  branch_guard=BranchGuardConfig(...) — 현재 git 브랜치가
│   │                       #  protected_branches(기본 main/master)이거나 require_branch_prefix와
│   │                       #  불일치하면 git commit/push 자동 차단(fail-open). recheck_branch=True
│   │                       #  (기본)면 커밋/푸시 직전에 브랜치를 다시 조회 — OpenCode 상주
│   │                       #  프로세스에서 세션 중 `git checkout main` 후 커밋이 통과되던 구멍 방지
│   │                       #  (Claude 훅은 호출마다 새 프로세스라 어느 쪽이든 항상 최신).
│   │                       #  tool_guard() 데코레이터 + live_guardrail_session() 컨텍스트
│   │                       #  매니저 — 도구 함수에 @tool_guard를 붙이면 세션 블록 안에서 호출될 때
│   │                       #  check_before_tool_call() → 실행 → record_tool_call()이 자동으로
│   │                       #  이어진다(새 탐지 로직 아님, 순수 적용 계층). 차단 시 GuardrailBlockedError
│   │                       #  (.verdict에 판정 담김), audit_blocked=True로 record_blocked_attempt()
│   │                       #  자동 연결, fail_closed=False(기본)면 세션 밖 호출을 RuntimeWarning만
│   │                       #  내고 가드 없이 통과(다른 fail_on_*와 반대로 fail-open이 기본값).
│   │                       #  SPEC-041: 감싼 함수가 예외를 던져도 record_tool_call(output=
│   │                       #  {"success":False})로 이력에 남긴다(같은 실패 명령 반복을 루프로
│   │                       #  잡고 Gate G 성공률 정확화). _bind_call_params는 이름 바인딩 실패 시
│   │                       #  {} 대신 {"_args":..,"_kwargs":..}를 넘겨 인자 값이 스캔되게 한다.
│   ├── team_concurrency.py # TeamConcurrencyConfig · load_active_claims() · check_scope_claim() ·
│   │                       #  append_claim() — .aoo/claims.jsonl 클레임 로그 파싱·기록
│   │                       #  audit_claims() — load_active_claims()/_scopes_overlap() 재사용해
│   │                       #  TTL 초과·겹치는 active 클레임을 CI가 소비할 위반 리스트로 반환(sys.exit 없음)
│   │                       #  TeamConcurrencyConfig.owner — 지정 시 developer==owner인
│   │                       #  자기 자신의 클레임을 충돌 후보에서 제외(미지정 시 옛 동작 그대로 보존)
│   │                       #  owner="auto" 예약 센티널 — resolve_owner()가 LiveGuardrail
│   │                       #  생성 시점에 git config user.name을 1회 조회해 치환(agent_version="auto"와
│   │                       #  동일 패턴), 조회 실패 시 예외 없이 None으로 폴백(기존 동작 유지)
│   ├── branch_guard.py     # BranchGuardConfig · get_current_branch() · is_branch_protected() ·
│   │                       #  matches_git_mutation() — "보호된 브랜치에 직접 커밋 금지" 같은 팀
│   │                       #  그라운드 룰을 LiveGuardrail이 실행 전 자동으로 강제
│   ├── gate_a_goal/       # Gate A(Goal Achievement)
│   │   ├── configs.py      # InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig ·
│   │   │                   # ContextRetentionConfig · KnowledgeRetentionConfig
│   │   ├── evaluators.py   # eval_instruction_adherence · eval_goal_alignment · eval_plan_coherence ·
│   │   │                   # eval_context_retention · eval_subtask_completion · eval_knowledge_retention
│   │   │                   # (+ Gate A 전용 private 헬퍼: _is_fact_retained_in_text · _kr_strip_particle 등)
│   │   └── aggregate.py    # Gate A 집계 로직 (TCR+AccuracyEvaluator 블렌딩+ResponseQualityEvaluator;
│   │                       #  details에 avg_goal_alignment/avg_plan_coherence 노출 — Gate B가 진단용 재참조)
│   ├── gate_b_behavioral/ # Gate B(Behavioral Integrity)
│   │   ├── configs.py      # LoopDetectionConfig · StateConsistencyConfig · DeadlockConfig ·
│   │   │                   # ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig
│   │   ├── evaluators.py   # eval_loop_detection · eval_state_consistency · eval_deadlock · eval_scope ·
│   │   │                   # eval_tool_parameter_safety · eval_context_window (+ _normalize_agent_interactions)
│   │   │                   # _extract_decoded_candidates() — ToolParameterSafetyConfig
│   │   │                   #  (decode_encodings=True) 옵트인 시 base64/hex로 인코딩된 위험 명령을
│   │   │                   #  디코드해 기존 dangerous_patterns로 재매치(새 탐지 규칙 아님, printable
│   │   │                   #  90% 필터로 오탐 방지, max_depth=2까지 재귀)
│   │   │                   # eval_tool_parameter_safety: scope_tool_names(SPEC-024)는 이제
│   │   │                   #  dangerous_patterns뿐 아니라 길이 검사(max_argument_length)까지
│   │   │                   #  게이트한다(SPEC-041) — Write/Edit처럼 인자=파일 본문인 도구를
│   │   │                   #  스코프에서 빼면 큰 파일 생성이 arg_too_long으로 오탐되지 않는다.
│   │   │                   #  scope_tool_names=None(기본값)이면 기존과 동일하게 전체 검사.
│   │   │                   #  SPEC-041: dangerous_patterns 매칭은 args_str에서 이스케이프된
│   │   │                   #  \n/\t/\r을 공백으로 되돌린 _scan_str에 대고 한다 — json.dumps가
│   │   │                   #  개행을 '\'+'n'으로 이스케이프해, 여러 줄 셸 명령의 2번째 줄
│   │   │                   #  이후 토큰 앞에 'n'이 붙어 \b(단어경계) 앵커가 깨지던 것 수정
│   │   │                   #  (기본 패턴이 전부 \brm/\bmkfs/\bdd/\bcurl로 시작). 길이 검사는
│   │   │                   #  원본 args_str 길이 유지.
│   │   │                   #  SPEC-041: eval_scope의 forbidden_tools/allowed_tools 매칭과
│   │   │                   #  eval_tool_parameter_safety의 scope_tool_names 매칭은 이제
│   │   │                   #  대소문자를 무시한다(_tool_name_in) — OpenCode "bash"/"webfetch" ↔
│   │   │                   #  Claude "Bash"/"WebFetch". 하나의 guardrail_config.json을 두 런타임
│   │   │                   #  공용으로 쓸 수 있게 하기 위함. 과거엔 정확 문자열 매치라
│   │   │                   #  forbidden_tools=["WebFetch"]가 OpenCode에서 조용히 미발효하고
│   │   │                   #  scope_tool_names=["Bash"]가 OpenCode bash 호출의 dangerous_patterns
│   │   │                   #  스캔을 통째로 스킵했다. violations 문자열엔 실제 표기를 그대로 남긴다.
│   │   └── aggregate.py    # Gate B 집계 로직 (loop+state_consistency+deadlock+scope+tps+context_window;
│   │                       #  avg_goal_alignment/avg_plan_coherence는 Gate A에서 파라미터로 전달받아 진단용 재참조)
│   ├── gate_c_reliability/ # Gate C(Reliability)
│   │   ├── configs.py      # ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig ·
│   │   │                   # RetryConsistencyConfig · IdempotencyConfig
│   │   ├── evaluators.py   # eval_fault_tolerance · compute_reproducibility_score · eval_graceful_degradation ·
│   │   │                   # eval_retry_consistency · eval_idempotency
│   │   └── aggregate.py    # Gate C 집계 로직 (TCR+SLA breach+reproducibility+fault_tolerance+
│   │                       #  graceful_degradation+retry_consistency+idempotency+LLM faithfulness/hallucination).
│   │                       #  compute_sla_shared_data(tasks)가 SLA 공유 데이터(Gate D가 소비)의 원천;
│   │                       #  compute()는 (group_dict, shared_raw) 튜플 반환 — shared_raw에 반올림 없는
│   │                       #  hall_rate/avg_llm_faithfulness를 담아 Gate G가 재사용. sla_window_penalty/
│   │                       #  sla_budget_penalty도 이 함수가 계산해 Gate D로 전달하지만 Gate C 자신의
│   │                       #  details에는 sla_breach_rate/sla_breach_count만 노출되고 두 penalty 값
│   │                       #  자체는 노출되지 않는다 — 역추적하려면 harness_groups.D.details의
│   │                       #  sla_window_penalty/sla_budget_penalty/perf_score_pre_sla_penalty를 볼 것
│   ├── gate_g_observability/ # Gate G(Observability)
│   │   ├── configs.py      # ObservabilityConfig · ExplainabilityConfig · ErrorDiagnosisConfig ·
│   │   │                   # LatencyAttributionConfig
│   │   ├── evaluators.py   # eval_observability · eval_explainability · eval_error_diagnosis ·
│   │   │                   # eval_latency_attribution
│   │   └── aggregate.py    # Gate G 집계 로직 (tool_coverage+hallucination+observability+
│   │                       #  explainability+error_diagnosis+latency_attribution). hall_rate/
│   │                       #  avg_llm_faithfulness는 Gate C의 shared_raw를 파라미터로 전달받음.
│   │                       #  monitor.py는 self.tool_analyzer(ToolCallAnalyzer)를 전달한다 — 과거
│   │                       #  존재하지 않는 속성명(self.tool_call_analyzer)으로 참조하던 오탈자가 있었으니
│   │                       #  새 코드에서 이 이름을 다시 틀리지 않도록 주의. details의 "tool_coverage"는
│   │                       #  실제로는 ToolCallAnalyzer.get_efficiency_stats()["success_rate"](도구 호출
│   │                       #  성공률)다 — trace_continuity 등 "관측 커버리지"와는 다른 개념이므로
│   │                       #  ObservabilityConfig(check_trace_continuity=...)와 혼동하지 말 것
│   ├── gate_f_multiagent/ # Gate F(Multi-Agent Coordination)
│   │   ├── configs.py      # ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig
│   │   ├── evaluators.py   # eval_consensus · eval_propagation · eval_role_adherence · eval_conflict_resolution
│   │   └── aggregate.py    # Gate F 집계 로직 (monitor.py가 위임 호출)
│   ├── gate_e_security/   # Gate E(Security Boundary)
│   │   ├── configs.py      # ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig
│   │   ├── evaluators.py   # eval_threat_severity · eval_compliance · eval_threat_response (+ _PII_PATTERNS)
│   │   └── aggregate.py    # Gate E 집계 로직 (5개 보안 트래커 + CVSS + compliance + threat_response)
│   └── gate_d_performance/ # Gate D(Performance Contract)
│       ├── configs.py      # SLAConfig · EfficiencyConfig(fallback_reference_cost_per_completion —
│       │                   #  target_cost_per_completion 미설정 시 efficiency_ratio 폴백 정규화 기준
│       │                   #  비용. None(기본값)이면 cost_unit별 레거시 하드코딩값 tokens/time_ms=1000.0,
│       │                   #  usd=0.01 유지) · ResourceBudgetConfig · TTFTVariabilityConfig ·
│       │                   #  CostPredictabilityConfig
│       ├── evaluators.py   # eval_sla · eval_efficiency(fallback_reference_cost_per_completion을
│       │                   #  결과의 "_config" 서브딕셔너리에 실어 aggregate.py로 전달) · eval_resource_budget
│       └── aggregate.py    # Gate D 집계 로직 (latency+efficiency+budget+TTFT+cost predictability;
│                           #  SLA 공유 데이터는 gate_c_reliability.aggregate.compute_sla_shared_data()에서
│                           #  전달받음). details에 perf_score_pre_sla_penalty/sla_window_penalty/
│                           #  sla_budget_penalty(SLA 감점 역추적용)·efficiency_ratio_reference_cost
│                           #  (폴백 정규화 경로에서 실제 사용된 기준 비용) 노출
├── quick_eval.py          # QuickEval facade + HarnessEvaluationGate
├── config.py              # get_settings · init_from_app · load_env
├── exceptions.py          # AgentEvaluatorError hierarchy
├── core/
│   ├── trackers/
│   │   ├── base.py        # BaseTracker, TaskResult, EvaluationReport, TaskType
│   │   ├── layer1.py      # Layer 1 trackers (pandas/numpy는 SPEC-041 B45로 지연 로딩 —
│   │   │                  #  Claude Code 훅 콜드스타트에서 eager import pandas ~135ms 제거.
│   │   │                  #  pd/np 사용처는 전부 get_*_stats() 등 배치 리포트 메서드 안이고
│   │   │                  #  실시간 판정 경로는 안 건드림. 패턴: `if TYPE_CHECKING: import
│   │   │                  #  pandas as pd / else: pd = _LazyModule("pandas")` — 런타임엔
│   │   │                  #  프록시(무료), 타입 체커엔 실제 모듈로 보여 `-> pd.DataFrame`
│   │   │                  #  어노테이션이 해석된다(Pylance reportInvalidTypeForm 회피).
│   │   │                  #  from __future__ import annotations라 런타임 어노테이션 평가도 없음)
│   │   ├── layer2.py      # Layer 2 trackers (pd도 동일 TYPE_CHECKING/LazyModule 패턴)
│   │   ├── security.py    # Security trackers (pd도 동일 TYPE_CHECKING/LazyModule 패턴)
│   │   ├── monitor.py     # PerformanceMonitor (central orchestrator)
│   │   │                  #  rehydrate_from_storage() — SQLite 이력 재생으로 재시작 생존 이상탐지 기준선
│   │   │                  #  agent_version="auto" — 캐싱된 self._git_commit 앞 8자 +
│   │   │                  #  미커밋 변경(git diff HEAD) 해시 접미사로 자동 태깅, 읽기 전용
│   │   │                  #  monitor.agent_version 프로퍼티로 최종 해석값 노출
│   │   │                  #  iteration_note — agent_version="auto"의 불투명한 dirty-hash
│   │   │                  #  태그에 사람이 읽을 수 있는 한 줄 메모를 붙임. _build_lineage()가
│   │   │                  #  extra_metrics.lineage.iteration_note로 그대로 실어 보냄(새 계산 없음)
│   │   ├── conversation.py# ConversationSession, ConversationMetrics, ConversationTurn
│   │   └── feedback.py    # ImplicitFeedbackTracker
│   ├── monitor_context.py # evaluation_session · hybrid_evaluation_session · async_evaluation_session
│   └── hybrid_monitor.py  # HybridPerformanceMonitor (DeepEval/Ragas integration)
├── integrations/
│   ├── llm_judge.py       # LLMJudge (native) · judge_pairwise() — A/B 응답 맞대결
│   │                       #  (swap-check로 포지션 편향 완화), self.pairwise_results에 별도 축적
│   ├── llm_judge_calibration.py  # LLMJudgeCalibration — judge-vs-human 골든셋 일치도
│   │                       #  (MAE · Pearson · Cohen's weighted kappa, scikit-learn 무의존 자체 구현)
│   ├── live_guardrail_stdio.py   # LiveGuardrail용 범용 stdio 브리지 (non-Python 호출자용)
│   │                       #  build_guardrail이 받는 키: 4개 Config + tracker 3종 +
│   │                       #  max_tool_output_chars/live_loop_window/live_loop_blocking_types/
│   │                       #  auth_scan_skip_keys/lenient_shell_file_write/protected_write_paths.
│   │                       #  SPEC-041: 한 Config/tracker 블록에 오타 키·잘못된 값이 있으면 그
│   │                       #  블록만 건너뛰고(stderr 경고) 나머지로 빌드 — 과거엔 오타 하나가
│   │                       #  전체 빌드를 깨서 가드레일이 통째로 fail-open 됐다.
│   │                       #  SPEC-041: 요청에 "id"가 있으면 응답에 그대로 되돌려 실어 준다
│   │                       #  (_write의 _req_id) — 비-Python 호출자가 응답을 FIFO가 아니라
│   │                       #  id로 매칭해, 타임아웃으로 취소된 요청의 늦은 응답이 다음 요청에
│   │                       #  잘못 배정되는 영구 데스싱크를 피한다. id 없으면 응답에도 안 붙음
│   │                       #  (구 호출자 100% 호환). 프로토콜은 여전히 "1요청→1응답, 순서 보존".
│   ├── opencode_plugin/agent-evaluator.ts  # OpenCode tool.execute.before/after 훅 → stdio 브리지.
│   │                       #  SPEC-041 P1.3: LiveVerdict.remediation(Python이 채움)을 차단
│   │                       #  Error 메시지 끝에 "\n→ "로 덧붙이고, synthetic transcript 요약도
│   │                       #  search_violations + recommend_fix 두 MCP 도구를 모두 안내한다.
│   │                       #  SPEC-041 P2.4: circuit breaker 이식(Claude 훅과 대칭) —
│   │                       #  GuardrailSession.consecutiveBlocks/circuitTripped. 연속
│   │                       #  CIRCUIT_BREAKER_AFTER(기본 5, config의 circuit_breaker_after로
│   │                       #  오버라이드, init 브리지엔 안 넘김)회 차단 시 sticky하게 관찰 전용
│   │                       #  전환(recordBlocked는 계속, throw는 안 함). tool.execute.after의
│   │                       #  성공 실행이 consecutiveBlocks를 0으로 리셋.
│   │                       #  SPEC-041: tool.execute.before/after·GuardrailSession(stdio 콜백·
│   │                       #  stdin write·process error/exit)를 전부 try/catch로 감싸 브리지가
│   │                       #  죽거나 비-JSON을 뱉어도 fail-open(도구 통과) — 과거엔 예외가
│   │                       #  그대로 전파돼 파이썬 미설치 시 세션의 모든 도구가 막혔다
│   │                       #  (claude_code_hook.run()의 fail-open과 반대였음). 요청마다
│   │                       #  5초 타임아웃(SEND_TIMEOUT_MS) — hang한 브리지가 세션을 통째로
│   │                       #  멈추지 않고 {error}로 resolve → fail-open.
│   │                       #  SPEC-041: GuardrailSession.pending은 id→resolver Map(구:FIFO
│   │                       #  배열) — 응답을 요청 id로 매칭한다. 타임아웃난 요청은 pending에서
│   │                       #  빠지고, 그 요청의 늦은 응답(id 존재하나 pending에 없음)은 조용히
│   │                       #  버린다(FIFO 폴백 금지 — 그게 데스싱크의 원인). id 없는 응답만
│   │                       #  (구 브리지) 가장 오래된 pending으로 폴백.
│   │                       #  SPEC-041: session.idle은 세션당 여러 번(턴마다) 발생 — 예전엔
│   │                       #  idle마다 endSession()으로 브리지를 죽여 다음 턴이 빈 이력으로
│   │                       #  시작(턴 가로지르는 loop/scope 탐지·max_tool_calls 누적 상한 리셋,
│   │                       #  task_id upsert라 최종 리포트가 "마지막 턴"만 반영해 앞 턴 위반이
│   │                       #  지워짐). 이제 브리지는 세션 내내 살려두고 idle마다 스냅숏+리포트
│   │                       #  upsert만. 회수는 dispose/session.error/MAX_LIVE_SESSIONS(64) LRU
│   │                       #  상한. synthetic transcript 요약은 위반 총계가 늘었을 때만 덧붙임
│   │                       #  (countGuardrailViolations, 매 턴 "위반 없음" 컨텍스트 부풀림 방지).
│   │                       #  SPEC-041: 프로젝트 설정은 .ts 인라인 GUARDRAIL_CONFIG를 편집하는
│   │                       #  대신 옆에 두는 agent-evaluator.config.json(JSON 객체)으로 오버라이드
│   │                       #  — resolveGuardrailConfig()가 최상위 키를 인라인 기본값 위에 *얕게*
│   │                       #  병합(EFFECTIVE_GUARDRAIL_CONFIG). 파일 없거나 깨졌으면 인라인 그대로.
│   │                       #  Claude 훅의 guardrail_config.json과 동일 분리 원칙 — `opencode
│   │                       #  install`이 .ts(코드)를 갱신해도 config는 안 건드린다.
│   ├── live_guardrail_report.py  # SQLite 기반 배치 리포트 브리지 (다중 세션 동시 기록)
│   │                       #  tool_calls를 TaskResult.tool_calls로 승격(Gate G) ·
│   │                       #  execution_time/success 옵트인 필드(Gate D/A, success 미지정 시
│   │                       #  completion_score=0.5 중립값 — None은 TaskResult 검증에 막혀 불가) ·
│   │                       #  agent_version 기본값 "auto"(자동 태깅 연결)
│   ├── claude_code_hook.py       # Claude Code CLI 훅(PreToolUse/PostToolUse/SessionEnd) →
│   │                       #  LiveGuardrail 브리지. Claude Code 훅은 호출마다 별도 프로세스라
│   │                       #  메모리를 공유하지 않으므로(live_guardrail_stdio.py의 상주
│   │                       #  프로세스 모델과 다름), 세션별 상태 파일(.claude/.agent-evaluator/
│   │                       #  sessions/<id>.json)에 확정 tool_call 이력을 남기고 매 호출마다
│   │                       #  record_tool_call()로 재생(replay)해 판정 상태를 복원한다 — 새
│   │                       #  SPEC-041: <id>는 _safe_session_id()로 [A-Za-z0-9._-]만 남기고
│   │                       #  앞쪽 점을 제거한다(방어적) — session_id가 그대로 상태 파일
│   │                       #  경로에 쓰이므로 `/`·`..`가 sessions/ 밖으로 새는 것 차단.
│   │                       #  Claude Code는 UUID만 넘기지만 4개 상태 파일 헬퍼가 모두 동일 적용.
│   │                       #  탐지 로직 없음, live_guardrail_stdio.build_guardrail()과
│   │                       #  live_guardrail_report.record_and_save()를 그대로 재사용.
│   │                       #  team_concurrency/branch_guard도 build_guardrail()이 다루는 키라
│   │                       #  guardrail_config.json에 채우면 그대로 지원된다(과거엔 미지원이었으나
│   │                       #  live_guardrail_stdio.py의 _CONFIG_CLASSES에 두 키가 등록되며 해소됨).
│   │                       #  예외는 항상 fail-open(판정 없음 반환) — 브리지 버그가 모든
│   │                       #  도구 호출을 막아버리면 안 되므로.
│   │                       #  load_config() 탐색 순서(SPEC-041): <cwd>/.claude/.agent-evaluator/
│   │                       #  guardrail_config.json → cwd 상위로 walk-up → ~/.claude/.agent-
│   │                       #  evaluator/guardrail_config.json → DEFAULT_GUARDRAIL_CONFIG.
│   │                       #  과거엔 <cwd>만 봐서 `claude install --global` 설정이 무시됐다.
│   │                       #  SPEC-041 P2.1: handle_session_end가 _session_end_summary()로
│   │                       #  한 문단 요약(Gate B/E 점수 + 위반 종류 + 차단 건수 + 리포트 경로)을
│   │                       #  만들어 result["systemMessage"]로 반환한다(배치 저장 성공 시에만).
│   │                       #  OpenCode의 synthetic transcript 요약과 대칭 — 그전엔 Claude는
│   │                       #  SessionEnd가 디스크에만 남기고 아무 요약도 안 냈다.
│   │                       #  SPEC-041: _session_config()가 첫 PreToolUse에서 해석한 설정을
│   │                       #  sessions/<id>.config.json에 고정한다 — 훅이 호출마다 별도
│   │                       #  프로세스라, 세션 도중 config 파일이 바뀌면 PreToolUse들이 서로
│   │                       #  다른 설정으로 판정하고 SessionEnd 리포트도 세션이 실제 강제한
│   │                       #  것과 다른 설정으로 점수를 내던 것 방지. SessionEnd는 고정본을
│   │                       #  읽고(없으면 만들지 않음) 세션 종료 시 삭제. config 변경은
│   │                       #  새 세션부터 적용(OpenCode는 .ts const라 원래 세션 시작 고정).
│   │                       #  circuit_breaker_after(기본 5, 0/null이면 끔) — 한 세션에서 연속
│   │                       #  N회 차단되면 남은 세션 동안 관찰 전용(allow+systemMessage)으로
│   │                       #  전환. 지속 차단은 공격보다 오설정일 확률이 압도적이라 무기한
│   │                       #  락아웃을 막는다. 위반은 계속 감사(sessions/<id>.circuit.json
│   │                       #  카운터 + blocked.json에 enforced=false로 기록), PostToolUse가
│   │                       #  성공 실행 시 연속 카운터 리셋. build_guardrail 전에 pop되는
│   │                       #  브리지 전용 키(output_dir와 동일 패턴).
│   │                       #  DEFAULT_GUARDRAIL_CONFIG(SPEC-041): dangerous_patterns에서
│   │                       #  `../`·`&&`·`||`·단일 `rm foo` 제거(코딩 세션 오탐), 재귀+강제
│   │                       #  삭제/mkfs/dd of=dev/fork bomb/curl|sh만 유지. tool_parameter_safety를
│   │                       #  scope_tool_names=["Bash"] + max_argument_length=100000으로 좁혀
│   │                       #  Write/Edit 파일 본문이 arg_too_long으로 차단되지 않게 함.
│   │                       #  이력 파일은 JSON 배열→JSON Lines(append-only) — read-modify-write
│   │                       #  제거로 O(n²) I/O를 O(n)으로, 병렬 PostToolUse 레코드 유실 방지.
│   │                       #  _load_json_list는 레거시 배열 파일·잘린 마지막 줄도 관대하게 읽음.
│   │                       #  PostToolUse 결과 성공 판정: Claude Code는 성공에 type="text"를
│   │                       #  보낸다(에러는 "error"/"failure") — 과거 type=="success"만 성공으로
│   │                       #  봐서 모든 성공 호출을 실패로 기록하고 stdout을 stderr로 넣던 버그 수정.
│   │                       #  run()은 int 반환 — PreToolUse deny면 JSON(permissionDecision=deny)
│   │                       #  + exit 2 + stderr 사유를 함께 낸다(구버전/다른 하네스가 JSON을
│   │                       #  파싱 안 해도 차단이 먹도록). __main__은 sys.exit(run()).
│   │                       #  SPEC-041 P1.3: deny 시 permissionDecisionReason에 verdict.reason
│   │                       #  + "\n→ " + verdict.remediation(조치 지침)을 함께 싣는다.
│   │                       #  circuit breaker systemMessage는 기존대로.
│   │                       #  서브에이전트(Task) tool 호출은 부모 session_id로 오되 payload에
│   │                       #  agent_id가 있으면 PostToolUse가 세션 이력에 그대로 남긴다(리포트용).
│   │                       #  DEFAULT dangerous_patterns에 파이프-투-셸 `\|\s*(sh|bash|zsh|ksh)\b`
│   │                       #  와 프로세스치환-투-셸 `[<>]\(\s*(sh|bash|zsh|ksh)\b` 추가.
│   ├── violation_search_mcp.py   # search_violations() 도구 1개를 노출하는 stdio MCP 서버
│   │                       #  (옵트인 `pip install "agent-evaluator[mcp]"`) — opencode mcp add로 등록
│   │                       #  include_blocked=True로 호출하면 완전 차단된("관찰"이 아닌) 이력까지
│   │                       #  함께 검색, [차단됨]/[관찰됨] 접두어로 구분
│   │                       #  SPEC-041 P3.2: format_results가 결과 요약에서 위반 유형을 감지하면
│   │                       #  (_VIOLATION_TO_GATE_METRIC) 끝에 `recommend_fix(gate=…, metric=…)`
│   │                       #  호출 힌트를 붙인다 — 두 MCP 도구를 체이닝(찾기→고치기).
│   ├── recommend_fix_mcp.py      # recommend_fix(gate, metric=None, value=None) 도구 1개를
│   │                       #  노출하는 stdio MCP 서버(옵트인, violation_search_mcp.py와 나란히
│   │                       #  등록) — ontology.metric_registry(GATE_GUIDANCE/NATIVE_METRIC_RULES/
│   │                       #  ANOMALY_METRIC_SUGGESTIONS)·ontology.mast_taxonomy(Gate F)를 그대로
│   │                       #  읽는 정적 지식 조회, 새 판정 로직 없음. 결과 파일 불필요 —
│   │                       #  rca.diagnose()(Gate F만 처방)와 달리 Gate A-G 전체에 답한다.
│   │                       #  SPEC-041: metric은 canonical_metric_name()으로 정규화한다 —
│   │                       #  diagnose()가 주는 필드명(hall_rate, avg_role_compliance,
│   │                       #  p95_latency_ms, tcr_pct…)을 규칙/제안/MAST 키로 매핑해 "규칙 있는데
│   │                       #  없다"고 답하던 어휘 불일치 제거. 이름이 바뀌면 사용자에게 고지.
│   │                       #  main()은 [mcp] extra 미설치 시 bare ImportError 대신 설치 안내
│   │                       #  (stderr) + exit 1(violation_search_mcp.py도 동일).
│   ├── metric_adapters.py # DeepEvalAdapter · RagasAdapter
│   ├── framework_integrations.py  # EvaluatorProtocol · to_graph_state · to_crew_inputs
│   ├── dspy_integration.py
│   └── pydanticai_integration.py
├── anomaly/               # AnomalyDetector · AnomalyEvent — 6개 체크(feedback_negativity가
│                          #  monitor.feedback_tracker의 is_positive 신호를 재사용).
│                          #  SPEC-041: AnomalyEvent.to_dict()가 event_id(type+시각+값 sha1
│                          #  프리픽스)·metric(=type)을 실는다 — 옛 저장본은 둘 다 없어서 serve
│                          #  explain 엔드포인트가 항상 404/"unknown"이었다. explain_event()는
│                          #  로컬 _suggestions 사본을 버리고 ontology.anomaly_suggestion_for()
│                          #  를 읽는다(Phase 2 통합 완성).
├── ontology/              # 진단/추천 지식을 모으는 순수 데이터 레지스트리(PyYAML 등 외부
│                          #  의존성 없이 Python dataclass로 관리, core dependency 원칙 유지)
│                          # metric_registry.py — GATE_GUIDANCE(Gate 7종 라벨+안내문)·
│                          #  NATIVE_METRIC_RULES(절대 임계값 기반 — SPEC-041: tcr/accuracy/
│                          #  hallucination_rate 전부 퍼센트(0-100) 규약. hallucination_rate
│                          #  threshold는 20.0(옛 0.2 분수는 모든 호출자가 퍼센트를 넘기는데
│                          #  0.2%만 넘어도 "exceeds 20%" 추천이 뜨는 오탐이었다). latency만
│                          #  절대 단위(초).)·ANOMALY_METRIC_SUGGESTIONS
│                          #  (AnomalyEvent.type 6종 키: latency_trend/accuracy_drift/token_spike/
│                          #  error_surge/feedback_negativity/security_pattern — SPEC-041에서
│                          #  잘못된 accuracy/latency/error_rate 3키를 바로잡음) — comprehensive_report.py의
│                          #  _build_recommendations()·serve/routers/data.py의 explain_anomaly_event()·
│                          #  anomaly/detector.py의 explain_event()·recommend_fix_mcp가 소비.
│                          #  rca.diagnose()와는 미연결(Gate F만 mast_taxonomy로 처방).
│                          #  canonical_metric_name(metric) — Gate details 필드명·RCA 출력
│                          #  필드명을 규칙/제안/MAST canonical 키로 정규화(_METRIC_ALIASES +
│                          #  avg_ 접두·_ms/_pct/_rate/_score/_count 접미사 제거). 모르면 원본
│                          #  그대로(없는 규칙 안 만듦). recommend_fix_mcp가 소비.
│                          #  anomaly_suggestion_for(name) — name이 AnomalyEvent.type
│                          #  ("latency_trend")이든 canonical 지표명("latency")이든 받아 제안
│                          #  반환(_METRIC_TO_ANOMALY_TYPE로 후자를 매핑). 안 맞으면 None.
│                          #  COMPONENT_GUIDANCE + component_guidance_for(field)(SPEC-041 P1.2) —
│                          #  GATE_GUIDANCE(Gate 1줄)와 NATIVE_METRIC_RULES(절대 임계값 4개)의 틈:
│                          #  Gate details 세부 컴포넌트(subtask_completion/budget_score/
│                          #  loop_detection…, ~36개)별 구체 조치. 키는 canonical 필드명
│                          #  (avg_ 접두 + _rate/_score/_pct/_ms/_s 접미사 벗겨 조회). 소비:
│                          #  _build_recommendations(diagnosis=)·live_guardrail._derive_remediation·
│                          #  cli/gate(_print_rca_explain)·recommend_fix_mcp.
│                          #  _COMPONENT_CONFIG_HINT + config_hint_for(field)(SPEC-041 P8.1) —
│                          #  컴포넌트→{slot, config, example}. 붙여넣을 수 있는 @agent_eval
│                          #  데코레이터 스니펫 생성용(산문 조치의 코드 레벨 짝). cost_predictability/
│                          #  ttft_variability는 데코레이터 슬롯이 아니라 PerformanceMonitor 인자라
│                          #  일부러 제외(잘못된 스니펫보다 없는 게 낫다).
│                          # mast_taxonomy.py — MAST(Cemri et al., NeurIPS 2025, arXiv:2503.13657)
│                          #  14개 실패모드 원문 시드 데이터, Gate F(다중 에이전트) 전용.
│                          #  rca.diagnose()가 Gate F 감지 시 related_gate_f_metric으로 후보를
│                          #  붙인다(자동 판정 아님, HOTL 원칙상 후보 제시까지만)
├── cost/                  # CostTracker · AdaptivePolicy · SamplingStage
├── datasets/              # GoldenSetBuilder · korean_rag_dataset_generator
├── alerts/                # AlertEngine · AlertRule · SlackHandler · WebhookHandler · EmailHandler
│                          # dispatch_anomaly_events() — AnomalyEvent를 type별 캐시된
│                          #  AlertRule(self._anomaly_rules, evaluate()의 self._rules와 분리)로 발송
├── storage/               # sqlite_backend.py — save_tasks_to_db · load_tasks_from_db
│                          # (PerformanceMonitor(storage_backend="sqlite") 옵트인 대안, 기본값 "json")
│                          # violation_search(FTS5) + search_violations() —
│                          #  Gate B/E 위반 이력 전문 검색
│                          # blocked_violations(FTS5) — 완전 차단돼 tasks/
│                          #  violation_search 어디에도 안 남는 시도의 감사 이력. search_violations
│                          #  (..., include_blocked=True)로 관찰 모드 위반과 함께 조회(blocked 필드로 구분)
├── streaming/             # StreamingEvaluator · AgentEvalMiddleware — anomaly_detector/
│                          #  anomaly_scan_interval/anomaly_alert_handler로 기존 flush 스레드에
│                          #  주기적 이상탐지 스캔 + AlertEngine.dispatch_anomaly_events 자동 연결
├── cli/main.py            # CLI entry point (subcommands: init·check·version·dashboard·gate·
│                          #  diagnose·abtest·dataset·monitor·opencode·claude·trend·claims —
│                          #  서브파서는 각각 cli/gate.py·cli/diagnose.py·cli/abtest.py·
│                          #  cli/dataset.py·cli/monitor.py·cli/opencode.py·cli/claude.py·
│                          #  cli/trend.py·cli/claims.py에 위임)
│                          # opencode install --with-violation-search/--with-recommend-fix:
│                          #  각각 search_violations/recommend_fix MCP 서버 자동 등록(옵트인)
│                          # opencode/claude 공통 서브커맨드(cli/_integration_health.py 공유):
│                          #  install(설치) · upgrade(패키지 업데이트 후 현행화, 사용자 config 보존) ·
│                          #  doctor(설치가 실제로 도는지 정적+라이브 검증, --json/--no-live/--strict) ·
│                          #  uninstall(훅·플러그인·MCP 제거 — `pip uninstall` *전에* 실행,
│                          #  --purge/--dry-run/--yes). opencode uninstall은 `opencode mcp`에 remove가
│                          #  없어 opencode.json의 mcp.<name>을 직접 편집(.jsonc는 수동 안내).
│                          #  MCP add "already exists"는 이제 실패가 아니라 "nothing to change"로 출력.
│                          # gate --baseline-version/--golden-set/--fail-on-golden-regression:
│                          #  버전별 독립 baseline + 골든셋 회귀 게이트(exit 3)
│                          # gate --explain/--no-explain(SPEC-041 P2.2) — 실패 시
│                          #  _print_rca_explain(data): rca.diagnose() + component_guidance_for()로
│                          #  fail/warn Gate마다 최약 컴포넌트 2개 + 조치를 CI 로그에 3줄 출력.
│                          #  기본은 실패 시 자동, --explain 항상, --no-explain 억제. exit code 불변.
├── cli/claude.py          # claude install [--global/--force/--with-violation-search/
│                          #  --with-recommend-fix] — .claude/settings.json(또는 --global 시
│                          #  ~/.claude/settings.json)에 PreToolUse/PostToolUse/SessionEnd 훅을
│                          #  병합(기존 훅 보존, 재설치해도 중복 추가 안 됨) + 기본
│                          #  guardrail_config.json 복사. SPEC-041: 재설치 시 우리 훅의 커맨드가
│                          #  정확한 canonical 형태("<python> -m <_HOOK_MODULE>")면 죽은 옛
│                          #  인터프리터 경로를 현재 sys.executable로 갱신한다(_refresh_hook_command)
│                          #  — venv 재생성·pipx reinstall 후 재설치만으로 고쳐짐. 래핑된 커맨드
│                          #  (추가 인자·파이프)는 사용자 의도로 보고 그대로 둔다.
│                          #  OpenCode installer(cli/opencode.py)와
│                          #  달리 훅 스크립트 자체는 파일 복사가 필요 없음(설치된 패키지를
│                          #  python -m agent_evaluator.integrations.claude_code_hook로 직접
│                          #  호출) — 재설치 보호 대상은 guardrail_config.json 하나뿐.
│                          #  SessionEnd 훅의 matcher는 도구 이름이 아니라 세션종료 사유를
│                          #  필터링하므로 PreToolUse/PostToolUse와 다른 matcher("*")를 쓴다 —
│                          #  실제로 이 차이를 놓쳐 배치저장이 발화 안 하는 회귀를 만들었다가
│                          #  라이브 테스트로 잡은 이력 있음(회귀 방지 테스트 존재).
│                          #  SPEC-041: Claude Code는 [A-Za-z0-9_\-, |\s]만 있는 matcher를
│                          #  *정확 이름*(또는 |-구분 정확 리스트)으로, 그 밖의 문자가 있으면
│                          #  비앵커 regex로 해석한다(docs 확인). 그래서 옛 "Bash|Edit|Write"는
│                          #  정확 리스트 — NotebookEdit·MultiEdit·WebFetch·모든 MCP 도구를 조용히
│                          #  놓쳤다(MCP 파일 생성은 PreToolUse 검사도, PostToolUse 이력도 없었음).
│                          #  _TOOL_MATCHER는 메타문자를 넣어 regex로 만들고 ^(...)$로 완전 앵커
│                          #  (re.search/match/fullmatch 동일). 커버: Bash|Write|Edit|MultiEdit|
│                          #  NotebookEdit|WebFetch + mcp__<server>__<verb>…(verb 앞 "_" 필수).
│                          #  WebFetch를 넣어야 기본 scope.forbidden_tools=["WebFetch"]가 발효.
│                          #  _merge_settings가 재설치 시 우리 훅의 stale matcher만 갱신
│                          #  (command·타 훅 불변). 읽기 전용 MCP(search/list/get)는 훅
│                          #  서브프로세스 비용 때문에 제외. 기존 설치도 `agent-eval claude install`
│                          #  재실행하면 matcher가 자동 갱신된다 — _our_hook_entries()가 훅을
│                          #  matcher가 아니라 command 문자열(_HOOK_MODULE 포함 여부)로 식별하므로
│                          #  옛 "Bash|Edit|Write" 설치도 "우리 것"으로 인식돼 matcher가 bump된다
│                          #  (SPEC-041; "재설치해도 갱신 안 됨"이라는 옛 서술은 틀렸다).
│                          #  claude upgrade — install과 달리 사용자가 편집한 guardrail_config.json을
│                          #  보존한다: 훅 matcher/인터프리터만 갱신 + _integration_health.
│                          #  deep_merge_defaults()로 DEFAULT_GUARDRAIL_CONFIG의 *새 키만* 추가
│                          #  (기존 값 절대 안 건드림, 추가된 키 경로를 출력). --with-violation-search/
│                          #  --with-recommend-fix를 줬을 때만 해당 MCP를 remove→add로 재등록
│                          #  (스코프 사고 방지 — get으로 자동 감지 안 함).
│                          #  claude uninstall — install의 역함수: _our_hook_entries()로 우리 훅만
│                          #  settings.json에서 제거(타 훅·설정 보존, 우리만 있던 이벤트 키는 삭제),
│                          #  claude mcp remove로 두 MCP 해제(_deregister_mcp_server, "not found"는
│                          #  무시), sessions/ 상태 삭제. guardrail_config.json은 기본 보존
│                          #  (--purge면 state dir 통째 삭제, --keep-config면 명시적 보존).
│                          #  --dry-run/--yes/-y. `pip uninstall` 후엔 agent-eval 엔트리포인트가
│                          #  사라지므로 반드시 그 전에 실행(도움말에 순서 명시).
│                          #  claude doctor — 설치가 실제로 도는지 검증. 정적: settings.json 파싱·
│                          #  훅 3개 등록·matcher 최신·훅 인터프리터 생존·그 인터프리터로 패키지
│                          #  import·guardrail_config가 build_guardrail()됨(SKIPPED 경고 수집)·
│                          #  MCP 등록(claude mcp get). 라이브(임시 sandbox cwd, output_dir도
│                          #  sandbox로 오버라이드해 hermetic): settings.json에 등록된 *실제 커맨드*를
│                          #  subprocess로 돌려 무해 Bash→allow, rm -rf→deny(exit 2), WebFetch→deny,
│                          #  PostToolUse+SessionEnd→배치 리포트 파일 생성 + 세션 상태 정리 확인.
│                          #  MCP: 등록된 서버에 initialize+tools/list 핸드셰이크(mcp_initialize_probe).
│                          #  --no-live(정적만)·--json(CI)·--strict(경고도 exit 1). 에러 있으면 exit 1.
├── cli/_integration_health.py  # claude/opencode의 doctor·upgrade·uninstall이 공유하는 헬퍼
│                          #  (새 판정 로직 없음, 순수 운영 계층). DoctorReport(체크 누적 + 텍스트/
│                          #  JSON 렌더 + exit_code(strict)) · deep_merge_defaults(사용자 값 보존
│                          #  deep-merge, 추가된 키 경로 반환, 리스트는 leaf) · interpreter_from_command
│                          #  (nice/env VAR=v 접두 건너뛰고 첫 실행 토큰) · probe_import(서브프로세스
│                          #  import 성공 여부) · validate_guardrail_config(build_guardrail() 호출 +
│                          #  stderr의 SKIPPED 경고 캡처) · mcp_initialize_probe(init→initialized→
│                          #  tools/list 3메시지를 한 번에 쓰고 communicate로 전부 읽어 파싱 —
│                          #  버퍼 파이프에서 select 한 줄 읽기보다 견고. MCP는 opt-in이라 실패는
│                          #  항상 warn, [mcp] extra 미설치는 안내 메시지로 구분).
├── cli/diagnose.py        # diagnose — agent_evaluator.rca.diagnose()를 감싸는 얇은 터미널
│                          #  출력 레이어(새 판정 로직 없음). CI 게이트 아님 — 항상 exit 0
│                          #  (결과 파일을 못 읽을 때만 exit 1), pass/fail 판정하지 않고
│                          #  후보 원인·근거만 출력(HOTL). --show-diff로 lineage.git_commit
│                          #  기반 실제 git diff까지 연결(§rca/ 참고).
│                          #  baseline 없이 호출하면(absolute_threshold) delta 표 대신
│                          #  finding["component_shortfalls"](약한 스코어 컴포넌트 우선 +
│                          #  NATIVE_METRIC_RULES 처방)를 출력한다 — §rca/ 참고
├── cli/abtest.py          # abtest — QuickEval.ab_test()/ab_test_nway()/ab_test_sequential()을
│                          #  감싸는 얇은 터미널 레이어(새 통계 로직 없음). CI 게이트 아님 —
│                          #  유의성/효과크기/표본경고만 출력, pass/fail 판정 없음. 결과 JSON
│                          #  파일 2개 → Welch's t-test(--sequential 시 mSPRT), 3개 이상 →
│                          #  N-way + Benjamini-Hochberg FDR 보정으로 자동 전환. 파일 로딩은
│                          #  PerformanceMonitor.load_from_file()로 TaskResult를 복원한 뒤
│                          #  QuickEval._monitor에 주입 — 새 파싱 로직 없음
├── cli/claims.py          # claims add/list/release/audit — append_claim()/load_active_claims()/
│                          #  audit_claims()를 감싸는 얇은 터미널 래퍼, 새 판정 로직 없음
├── rca/                   # Gate 회귀 원인진단(RCA) + 개선 이력 추적 — Media/Book Part VII
│                          #  (Ch28–31)가 다루는 기능의 실제 구현. quick_eval.py/gates/base.py의
│                          #  기존 판정 로직을 재사용할 뿐 새 판정 공식은 만들지 않는다
│                          # diagnose.py — diagnose(current, baseline=None, ...): 3단계
│                          #  (감지→원인귀속→교차확인). _compute_gate_regressions()(기존 baseline
│                          #  회귀 공식) 재사용. Gate C·D 동시 감지 시 SLA 공유데이터로 공유원인
│                          #  체크. Gate F는 ontology.mast_taxonomy로 MAST 후보 추가(§ontology 참고)
│                          #  SPEC-041: _numeric_detail_deltas는 동점(baseline 없는
│                          #  absolute_threshold 모드는 전부 delta=None이라 전부 동점)을 field
│                          #  이름 오름차순으로 tiebreak한다 — 안 하면 set 순회 순서(PYTHONHASHSEED
│                          #  랜덤화)로 top_detail_deltas[0]가 실행마다 바뀌어 step-3 교차검색
│                          #  쿼리·Gate F MAST 후보가 비결정적이 된다.
│                          #  SPEC-041: _ranking_scale은 접미사별 스케일 보정표(_RANKING_SCALE_BY_SUFFIX)
│                          #  — _pct→100, _ms→2000, _count→10, _latency_s→5. 예전엔 _pct만
│                          #  처리해서 ttft_p95_ms(밀리초)·sla_breach_count(정수)가 원시 delta
│                          #  크기로 0-1 score 필드를 수백~수천배 눌러, RCA가 예산 붕괴 대신
│                          #  미미한 지연 변동을 원인 1순위로 지목했다. 반환값(current/baseline/
│                          #  delta)은 원래 단위 보존, 정렬 기준에만 보정.
│                          #  SPEC-041: newly_unmeasured_gates — baseline엔 숫자 점수가 있었는데
│                          #  current엔 None인 Gate. _compute_gate_regressions(3개 게이트 경로
│                          #  공유 공식)가 current=None을 조용히 건너뛰므로, Config 실수로 빼서
│                          #  Gate가 통째로 사라지는 커버리지 손실을 별도 신호로 낸다. CLI가
│                          #  ⚠ 경고로 출력.
│                          #  finding["component_shortfalls"] — baseline 없는 absolute_threshold
│                          #  모드에선 top_detail_deltas가 전부 delta=None이라 field 이름
│                          #  알파벳 나열로 퇴화한다(설정 상수 gate_a_tcr_weight까지 지표인 척
│                          #  올라옴). component_shortfalls는 현재 details만으로 "지금 이 Gate
│                          #  점수를 깎는 컴포넌트"를 health(0-1, _shortfall_health로 정규화,
│                          #  높을수록 건강) 오름차순으로 답한다 — _weight(설정 상수)·_count·
│                          #  _penalty 접미사와 perf_score_pre_sla_penalty 제외, 확신 있게
│                          #  정규화 가능한 필드만 포함(추측 금지). regression 모드에서도 채우되
│                          #  거긴 보조 신호. cli/diagnose.py·comprehensive_report._build_diagnosis()가
│                          #  absolute 모드에서 이걸로 렌더(Baseline/Delta 열 대신 Component/
│                          #  Current/Health, GATE_GUIDANCE + NATIVE_METRIC_RULES 처방 첨부,
│                          #  섹션 제목도 "Gate Failure Diagnosis"로 바뀜).
│                          # experiment_metadata.py — derive_experiment_metadata(): 두 리포트의
│                          #  extra_metrics.lineage.git_commit을 대조해 순수 git 명령만으로 코드
│                          #  diff 해석 — gh CLI/GitHub API 미의존. SPEC-041: changed_files는
│                          #  `git diff --name-only`로 뽑는다(요약줄만 --stat) — 비-tty 서브프로세스
│                          #  에서 --stat은 폭 80으로 긴 경로를 "...abbrev/"로 자르고 rename을
│                          #  "a => b"로 뭉개서 파일명이 손상됐다.
│                          # verify.py — verify_recommendation_outcome(): 조치 적용 후 재평가
│                          #  결과가 실제로 개선됐는지 confirmed/refuted/inconclusive 판정
│                          # recommendation_tracking.py — record_/load_/summarize_
│                          #  recommendation_outcomes(): .aoo/claims.jsonl과 동일한 append-only
│                          #  JSONL 패턴으로 조치 이력 기록
├── reporting/                # 출력 표면 전체 지도·정보 계층(L1~L6)·역할별 워크플로우는
│                             #  docs/09_OUTPUTS.md에 정리(결과 JSON·HTML 리포트·CLI·대시보드·
│                             #  AI 런타임 출력). 새 출력 섹션/필드를 추가하면 그 문서도 갱신.
│   ├── insights.py           # build_insights(current, baseline=None, *, recommendation_log_path=None)
│   │                          #  — 머신 판독 인사이트 계층(L5/L6)을 JSON 직렬화 가능한 한 객체로.
│   │                          #  rca.diagnose()·utils.confidence·ontology.metric_registry·
│   │                          #  rca.recommendation_tracking/verify 재사용, 새 판정 없음, 절대
│   │                          #  raise 안 함. monitor.save_to_file()가 extra_metrics.insights로
│   │                          #  자동 첨부, serve/routers/diagnose.py가 result["insights"]로 반환.
│   │                          #  스키마·필드는 §"Harness Gate Config Groups" 아래 참조.
│   └── comprehensive_report.py  # generate_comprehensive_html_report(monitor)·
│                          #  generate_html_from_result_file(rf) — 단일 결과 HTML 리포트
│                          #  (agent-eval gate 저장/대시보드 export_html 공용).
│                          #  generate_comparison_html_report(compare_result) —
│                          #  compare_results()의 반환 dict를 그대로 렌더링(새 비교 로직 없음).
│                          #  _build_failure_cases(tasks)(SPEC-041 P1.1) — 두 진입점 모두
│                          #  worst-N 실패/저점 태스크를 question→response 요약 + score(C/A) +
│                          #  "likely reason"(partial_reason→errors[0]→저점 사유)으로 표에 낸다.
│                          #  실패 태스크 우선, 없으면 _is_low(acc<0.7 or comp<0.4 or judge<6)만,
│                          #  전부 건강하면 섹션 생략. 지금까지 집계값만 보이던 리포트에 "어느
│                          #  태스크가 왜"를 추가(개선 착수의 전제). monitor.tasks / rf.tasks에서.
│                          #  _build_executive_summary(SPEC-041 P3.1) — 리포트 최상단(헤더 다음):
│                          #  배포 준비도 한 줄 판정(fail→❌ / warn→⚠️ / pass→✅) + 병목 Gate +
│                          #  "Next actions" 1·2·3(fail 먼저, 각 Gate의 component_shortfalls[0] +
│                          #  조치). 새 판정 없음 — Gate status·diagnosis 재배열.
│                          #  _build_operational_signals(SPEC-041 P3.4) — AnomalyDetector 결과
│                          #  (monitor 경로는 enable_anomaly_detection 시 즉석 scan, rf 경로는
│                          #  rf.raw["anomaly_data"])를 type/severity/detail/value + anomaly_
│                          #  suggestion_for() 조치 표로. 그전엔 이상탐지는 대시보드에만 있었다.
│                          #  _build_recommendations(..., diagnosis=)(SPEC-041 P1.2) — 진입점이
│                          #  rca.diagnose()를 1회 계산해 넘기면, 각 fail/warn Gate rec에
│                          #  finding["component_shortfalls"] 상위 2개 + component_guidance_for()
│                          #  조치를 "Biggest measured shortfalls"로 덧붙인다(Gate 1줄 일반론 →
│                          #  측정된 병목 지목). diagnosis=None이면 기존 동작.
│                          #  P5(통계적 정직성): _metric_ci_data(tasks)가 per-task
│                          #  completion/accuracy_score로 TCR/Accuracy 95% 부트스트랩 CI를
│                          #  구해 헤더·Executive Summary·Conclusion에 표시. Exec Summary에
│                          #  utils.confidence.verdict_confidence() 기반 HIGH/MEDIUM/LOW
│                          #  CONFIDENCE 배지(표본 수·CI 폭·측정 컴포넌트 수·임계값 여유).
│                          #  _build_score_breakdown이 전 Gate에 대해 insufficient_data_warnings를
│                          #  렌더(전엔 Gate D만). Conclusion Grade에 확신도 병기.
│                          #  P6(실패 인텔리전스): _build_failure_cases가 표 위에 (1)
│                          #  _build_failure_clusters — 실패를 (_reason_signature × task_type)로
│                          #  군집화해 count·영향도(~%p) 순 (2) _build_failure_lineage —
│                          #  baseline tasks[]와 대조해 📉Regressed/♻️Persistent/🆕New/✅Fixed.
│                          #  _effective_fail(): success 플래그 + acc<0.7/comp<0.4 기준.
│                          #  P8(개선 루프 폐쇄): _rec_code_snippet(config_hint_for) 붙여넣을
│                          #  @agent_eval 스니펫 · _rec_past_outcomes(recommendation_log_path,
│                          #  gate) "이전에 뭐가 통했나"(confirmed/refuted/avg Δ) ·
│                          #  _rec_experiment_block 예측 델타+권장 표본+abtest 명령 ·
│                          #  _rec_baseline_verdict(verify_recommendation_outcome) baseline 대비
│                          #  confirmed/refuted. _build_recommendations(recommendation_log_path=,
│                          #  baseline=, current=)로 주입.
│                          #  _build_diagnosis()는 rca.diagnose() 출력의 newly_unmeasured_gates도
│                          #  경고로 렌더링한다(SPEC-041, CLI cli/diagnose.py와 동일) — 커버리지
│                          #  손실이 있으면 "no detection" 안심 메시지를 안 띄운다.
│                          #  detection_mode로 분기: regression_vs_baseline(baseline 전달)이면
│                          #  기존 Metric/Baseline/Current/Delta 표 + "Gate RCA Diagnosis
│                          #  (Improve)" 제목 그대로. absolute_threshold(배치 단발, baseline
│                          #  없음)이면 가짜 n/a 열 대신 finding["component_shortfalls"]로
│                          #  Component/Current/Health 표(약한 컴포넌트 우선) + GATE_GUIDANCE
│                          #  + NATIVE_METRIC_RULES 처방을 렌더하고 제목도 "Gate Failure
│                          #  Diagnosis"로 바꾼다(§rca/ component_shortfalls 참고).
│                          #  _build_recommendations()의 hallucination_rate는 퍼센트(0-100)를
│                          #  NATIVE_METRIC_RULES(threshold 20.0)에 그대로 넘긴다(§ontology 참고).
│                          #  P4.1: _build_score_breakdown이 측정 컴포넌트 ≤2 & score<90이면
│                          #  "이 점수는 대표성이 낮다"(만점 항목이 문제를 희석할 수 있음) 경고.
│                          #  P4.2: _not_tested(reason, kind=) — kind로 config(⚙️ Not Configured)/
│                          #  data(📉 Insufficient Data)/n/a(➖ Not Applicable)/generic 구분.
└── serve/
    ├── server.py          # FastAPI dashboard (111 routes). SPEC-041: create_app이
    │                      #  results_dir를 Path로 강제 — str로 호출해도 라우터의
    │                      #  `results_dir / "..."`(예: routers/diagnose.py의
    │                      #  recommendation_outcomes.jsonl)가 500 나지 않는다.
    ├── templates/         # dashboard2.html.j2 · slides.html.j2 · sdk_docs.html.j2
    │   └── dashboard2.html.j2  # `/dashboard` 라우트의 유일한 대시보드 템플릿
    │                      #  (한국어 UI 레거시 dashboard.html.j2는 삭제됨). File Compare 탭: group_by
    │                      #  드롭다운·⚖️ Pairwise Judge 서브탭·📄 Export HTML 버튼
    │                      #  Metric Comparison 표 상단에 agent_version/iteration_note
    │                      #  메타데이터 행 — 새 API 호출 없이 이미 로드된 compareData에서 직접 렌더링
    │                      #  SPEC-041 P2.3: Improve 탭 finding 카드 — baseline 있으면 기존
    │                      #  top_detail_deltas(Baseline/Current/Δ) 표, baseline 없으면
    │                      #  component_shortfalls(Component/Current/Health, 약한 순) 표를 렌더.
    │                      #  정적 HTML 리포트/`agent-eval diagnose`와 동일한 rca.diagnose() 필드.
    └── routers/           # alerts · anomaly · config · conversation · cost · data · diagnose
                           # export · feedback · golden · stream · transparency · webhook
                           # data.py: list_results(prompt_version=/agent_version=)·
                           #  compare_results(group_by=/pairwise=)
                           # diagnose.py: GET /api/diagnose/{file_id}(rca.diagnose() 호출,
                           #  baseline_id=/regression_threshold=/show_diff=) · GET /api/diagnose/
                           #  (recommendation_outcomes.jsonl 읽기) — 대시보드 🔧 Improve 탭이 소비
                           # export.py: GET /html/compare — ids 또는 group_by +
                           #  선택적 pairwise → generate_comparison_html_report(). `/html/{file_id}`
                           #  보다 먼저 등록해야 정적 경로가 파라미터 경로에 삼켜지지 않는다
```

### Harness Gate Config Groups (33 total)

| Gate | Configs |
|------|---------|
| A — Goal Achievement (6) | InstructionConfig · GoalAlignmentConfig · PlanConfig · SubtaskConfig · ContextRetentionConfig · KnowledgeRetentionConfig |
| B — Behavioral Integrity (6) | LoopDetectionConfig · ScopeConfig · ToolParameterSafetyConfig · ContextWindowConfig · StateConsistencyConfig · DeadlockConfig |
| C — Reliability (5) | ReproducibilityConfig · FaultToleranceConfig · GracefulDegradationConfig · RetryConsistencyConfig · IdempotencyConfig |
| D — Performance Contract (5) | SLAConfig · EfficiencyConfig · ResourceBudgetConfig · TTFTVariabilityConfig · CostPredictabilityConfig |
| E — Security Boundary (3) | ThreatSeverityConfig · ComplianceConfig · ThreatResponseConfig |
| F — Multi-Agent Coordination (4) | ConsensusConfig · PropagationConfig · AgentRoleConfig · ConflictResolutionConfig |
| G — Observability (4) | ExplainabilityConfig · ObservabilityConfig · ErrorDiagnosisConfig · LatencyAttributionConfig |

Gate A–G results stored under `extra_metrics.harness_groups` in JSON result files.
결과 JSON 최상위에 `schema_version`("1.1", SPEC-041 P4.3) — 소비자가 필드 형태 변화에 대응하도록. breaking change 시 major 증가.

**`extra_metrics.insights`** (SPEC-041 P9) — 머신 판독 인사이트 계층(L5/L6). `reporting/insights.py::build_insights()`가
`rca.diagnose()`·`utils.confidence`·`ontology.metric_registry`·`rca.recommendation_tracking`/`verify`의 출력을
JSON 직렬화 가능한 한 객체로 재구성한다(새 판정 로직 없음, 절대 raise 안 함 — 실패 섹션은 비거나 생략).
`monitor.save_to_file()`가 저장 시 자동 첨부(baseline 없는 absolute 모드, output_dir의
`recommendation_outcomes.jsonl` 자동 픽업), `serve/routers/diagnose.py`의 `/api/diagnose/{id}`도
`result["insights"]`로 반환(대시보드 Improve 탭이 소비). 스키마:
`{schema_version, detection_mode, verdict{level: not_ready|caution|ready|unknown, headline, failing_gates,
warning_gates, confidence, confidence_reasons, next_actions[]}, metric_confidence{n_tasks, tcr_pct, tcr_ci_pct,
accuracy_pct, accuracy_ci_pct}, gate_findings[]{gate, score, component_shortfalls[]{field, value, health,
guidance, config_hint}, top_detail_deltas[]}, failure_clusters[]{signature, task_type, count, impact_pct,
example_task_ids}, failure_lineage{regressed, persistent, new, fixed}|null, recommendations[]{gate, status,
label, guidance, shortfalls[], code_snippet, experiment{predicted_gate_delta, recommended_tasks, command}|null,
past_outcomes{confirmed, refuted, avg_delta}|null, baseline_verdict{verdict, delta}|null},
latency_budget{n_tasks, tool_ms, model_ms, network_ms, unattributed_ms, *_ratio, bottleneck, bottleneck_share}|null
(SPEC-041 P7 — eval_latency_attribution의 per-task span 분해를 평균낸 것, 모달 bottleneck),
shared_cause_explanations, newly_unmeasured_gates, experiment_metadata}`. 정적 HTML 리포트는 여전히 자체
`_build_*` 헬퍼로 같은 내용을 렌더한다(콘텐츠 동등, `insights`는 머신 판독 채널).

**SPEC-041 P7 (궤적 가시성)** — `reporting/comprehensive_report.py`:
`_build_latency_budget(tasks, p95)`(Gate D 섹션) — "P95 4.0s"를 model/tool/network/unattributed 스택바 +
"Bottleneck: model" 한 줄로 분해. `insights.aggregate_latency_attribution()` 재사용.
`_build_trajectory(case)`(실패 케이스 표의 각 행에 `<details>`) — `tool_calls`→`chain_steps`→`agent_interactions`
순으로 step→tool→인자/출력 요약→✓/✗ + 스텝별 duration/토큰. 스텝 데이터 없는 태스크(순수 QA)는 "".
`_norm_task_for_case`가 tool_calls/chain_steps/agent_interactions도 담는다. `_build_gate_d`가 `tasks` 인자 추가.

### Native Tracker → Gate Score Contribution (`_compute_harness_groups`)

| Tracker | Gate | 기여 방식 | 조건 |
|---------|------|-----------|------|
| `TaskCompletionTracker` | A, C | `_a_vals[0]` (TCR 컴포넌트), `_rel_vals` | always |
| `AccuracyEvaluator` | **A** | `_a_vals[0]` 블렌딩 (`0.6×TCR + 0.4×Accuracy`) | `_evaluations` count > 0 |
| `ResponseQualityEvaluator` | **A** | `_a_vals` 추가 (relevance+completeness 평균 / 5, 0→1 정규화) | quality dims 측정 시 |
| `LatencyTracker` | D | `_perf_vals` | always |
| `TokenEconomyTracker` | — | (gate score 미기여) | 토큰 비용 추적·보고 전용 |
| `HallucinationDetector` | **C + G** | `_rel_vals`, `_obs_vals` | LLM Judge faithfulness 없을 때 폴백 (`1 − rate`) |
| `LLMJudge` (faithfulness) | **C** | `_rel_vals` | per-task faithfulness 기록 시 우선 적용 (`score / 5` 정규화); HallucinationDetector 대체 |
| `RetryCorrectionTracker` | — | (gate score 미기여) | 재시도 횟수·패턴 추적 전용 |
| `ToolCallAnalyzer` | G | `_obs_vals` — `success_rate / 100` (0→1 정규화) | tool_calls 기록 시 |
| `WorkflowExecutionTracker` | — | (gate score 미기여) | chain_steps 추적·분석 전용 |
| Security Trackers (5) | E | `_all_e_scores` | `enable_security_metrics=True` |
| `AgentCoordinationTracker` | F | `_f_vals` — `calculate_coordination_score().overall_score / 10` (0→1 정규화) | agent_interactions 기록 시 |
| `ToolSelectionTracker` | F | `_f_vals` — `avg_f1_score / 100` (0→1 정규화) | expected_tools 지정 시 |

> **Gate A 가중치 구조**: `_a_score = gate_a_tcr_weight × _a_vals[0] + (1 − gate_a_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_a_tcr_weight=0.4` — `PerformanceMonitor(gate_a_tcr_weight=...)` 으로 조정 가능.  
> **Gate B 가중치 구조**: `gate_b_loop_weight > 0.0` 이면 루프 점수에 가중치 부여, `0.0`(기본값)이면 가용 지표 단순 평균.  
> 기본값 `gate_b_loop_weight=0.0` — `PerformanceMonitor(gate_b_loop_weight=...)` 으로 조정 가능.  
> **Gate C 가중치 구조**: `_rel_score = gate_c_tcr_weight × _rel_vals[0] + (1 − gate_c_tcr_weight) × mean(나머지)`.  
> 기본값 `gate_c_tcr_weight=0.4` — `PerformanceMonitor(gate_c_tcr_weight=...)` 으로 조정 가능.  
> Gate B details에 `avg_goal_alignment` / `avg_plan_coherence`가 표시되지만, 이는 Gate A 계산값을 재참조하는 진단용이며 Gate B **점수에는 포함되지 않는다**.  
> **`AgentCoordinationTracker` 스케일**: `calculate_coordination_score().overall_score`는 0–10 스케일 → Gate F에서 `/10`으로 정규화.  
> **`ConsensusConfig.consensus_method`**: `"majority"` = 동의 쌍 비율; `"unanimity"` = 모든 쌍 동의 시만 1.0, 아니면 0.0; `"weighted"` = `agent_weights` 기반 가중 비율.  
> **`eval_conflict_resolution` 충돌 카운팅**: `agent_interactions`가 있으면 interaction 기반으로만 집계, 없으면 response 텍스트 폴백 (이중 카운팅 방지).  
> **RCA 상호참조(Gate F ↔ Gate B)**: Gate F(`gate_f_multiagent`)와 Gate B(`gate_b_behavioral`)는 서로를 참조하지 않는 완전 독립 슬라이스지만, 멀티에이전트 배포에서 둘 다 동시에 낮다면 조율 실패라는 같은 근본원인일 확률이 높다. Gate F 점수가 낮을 때는 `harness_groups.B.details.deadlock_by_type`/`deadlock_count`도 함께 확인할 것 — Gate B의 데드락이 Gate F의 낮은 `avg_conflict_resolution`/`coordination_score`를 설명하는 경우가 흔하다. 반대로 Gate C(신뢰성)와 Gate D(성능)가 동시에 하락했다고 해서 원인이 하나(예: SLA)라고 성급히 가정하지 말 것 — 같은 배포에 여러 변경이 우연히 겹친 경우가 더 흔하므로, `harness_groups.C.details.sla_breach_rate`와 `harness_groups.D.details.sla_window_penalty`/`sla_budget_penalty`를 먼저 대조해 실제로 SLA가 두 Gate 모두의 원인인지부터 확인한다.

---

## Key Usage Patterns

### QuickEval (one-stop facade)

```python
from agent_evaluator import QuickEval

eval = QuickEval("results/")

@eval.qa
def agent(question, ground_truth=""): ...

@eval.rag
def rag_agent(question, context="", ground_truth=""): ...

eval.save()
eval.gate(tcr=85, accuracy=70)  # sys.exit(1) on failure

# Factories
QuickEval.for_rag("results/")
QuickEval.for_security("results/")
QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")
```

### PerformanceMonitor

```python
from agent_evaluator import PerformanceMonitor

monitor = PerformanceMonitor(
    output_dir="results/",
    enable_hallucination_detection=False,  # default False
    enable_security_metrics=False,         # default False
    enable_llm_judge=False,
    judge_model=None,          # auto-determined from API key
    judge_sample_rate=0.1,
)
monitor.record_task(task_result)
monitor.save_to_file("evaluation")  # JSON + HTML
```

> Use `PerformanceMonitor` for new projects. Use `HybridPerformanceMonitor` only when integrating DeepEval/Ragas.

> **`agent_version="auto"`**: reserved sentinel — resolves to the current git commit's short
> SHA (`git rev-parse HEAD`, cached once at `__init__`), with a `-dirty-<hash>` suffix appended when
> tracked files have uncommitted changes (`git diff HEAD`, hashed — distinguishes iterations run without
> committing between them). Falls back to `None` on any git failure. Read the resolved value back via the
> read-only `monitor.agent_version` property (no setter — same "fixed at construction" contract as
> `model_name`). Any other literal string (or `None`, the default) behaves exactly as before — `"auto"` is
> the only reserved value.

### Harness Config in Decorator

```python
from agent_evaluator import (
    PerformanceMonitor, agent_eval,
    InstructionConfig, LoopDetectionConfig, SLAConfig, ExplainabilityConfig,
)

@agent_eval(monitor, task_type="qa",
    instructions=InstructionConfig(required_keywords=["Seoul"], fail_on_violation=True),
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    sla=SLAConfig(p95_ms=3000),
    explainability=ExplainabilityConfig(min_reasoning_length=20),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### EvalMetadata — Injecting Metadata from Inside the Function

```python
from agent_evaluator import agent_eval
from agent_evaluator.decorators import EvalMetadata

@agent_eval(monitor, task_type="qa")
def agent(question: str, ground_truth: str = "") -> tuple:
    response = f"Answer: {question}"
    return response, EvalMetadata(
        extra={"ttft_ms": 120.5},
        tokens_used={"input": 50, "output": 100, "total": 150},
    )
```

### Context Manager

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("results/eval.json") as monitor:
    task = create_taskresult(task_id="t1", question="...", response="...", execution_time=1.2)
    monitor.record_task(task)
```

### LLMJudge

```python
from agent_evaluator import LLMJudge

judge = LLMJudge(model="claude-haiku-4-5-20251001", sample_rate=0.1)
result = judge.judge("t1", question="...", response="...", context="...")
# result["scores"]["overall"] · ["faithfulness"] · ["criteria_overall"]

# async path + concurrency/backoff (max_concurrent_judge_calls=5, max_retries=3 defaults)
judge = LLMJudge(model="claude-haiku-4-5-20251001", max_concurrent_judge_calls=5, max_retries=3)
result = await judge.ajudge("t1", question="...", response="...", context="...")
# ajudge() is bounded by an internal asyncio.Semaphore; provider 429s retry with 1s/2s/4s backoff.
# agent_eval's async wrapper uses ajudge() automatically. batch_eval(..., concurrent_judge=True)
# opts into asyncio.gather-based concurrent judge processing (default False = sequential, unchanged).

# Accessing LLMJudge results from monitor
summary = monitor.llm_judge.get_summary()
# → {"avg_scores": {"overall": float, "criteria_scores": {...}}, "sample_count": int}
```

### create_taskresult Helper

```python
from agent_evaluator import create_taskresult

result = create_taskresult(
    task_id="task_001", question="...", response="...",
    ground_truth="...", execution_time=1.23, task_type="qa",
)
```

### HarnessEvaluationGate

```python
from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate

report = monitor.generate_report()
gate = HarnessEvaluationGate(report)
result = gate.evaluate()   # no arguments
# result: {"passed": bool, "groups": {"A": {"score": float|None, "status": str, "passed": bool,
#              "threshold": float, "not_measured": bool (score=None일 때만),
#              "insufficient_data_warnings": list[str] (있을 때만)}},
#          "violations": [...], "summary": {"total_groups": int, "passed_groups": int, "overall_score": float|None}}

# Gate별 개별 임계값 + 미측정 Gate 강제 실패(둘 다 기본 False/미지정 시 기존 동작과 100% 동일)
gate = HarnessEvaluationGate(
    report,
    required_groups=["A", "E"],
    group_thresholds={"E": 0.95},   # Security는 더 엄격하게 — QuickEval.gate(gate_thresholds=...)/
                                     # CLI --gate-thresholds와 동일 개념을 이 클래스에도 대칭 추가
    strict_required=True,            # required_groups에 명시한 Gate가 score=None(설정 자체를 안 함)이면
                                      # 실패 처리 — 기본값(False)은 "꺼진 Gate는 조용히 통과"인 기존 동작 유지
)
```

> **주의**: `HarnessEvaluationGate.evaluate()`(Python API), `QuickEval.gate()`, `cli/gate.py`(`agent-eval gate`)는
> Gate A-G 임계값 판정을 세 곳에서 각각 호출하는 서로 다른 진입점이다 — `_compute_gate_regressions()`
> (베이스라인 회귀 판정 공식)와 `gates/base.py::evaluate_gate_scores()`(Gate별 score/threshold/status →
> passed 판정 루프)를 셋 다 공유한다. 남은 차이는 진입점별 고유 기능뿐이다(`HarnessEvaluationGate`의
> `strict_required`, CLI의 `--baseline-version`/`--golden-set`). 세 진입점 모두 `score is None`인
> Gate는 기본적으로 통과 처리한다(`HarnessEvaluationGate`는 `strict_required=True`로만 opt-out 가능,
> 나머지 둘은 항상 통과). 판정 루프 자체(`evaluate_gate_scores()`)를 고치면 세 곳 모두 자동으로
> 반영되지만, 진입점별 고유 기능을 바꿀 때는 해당 진입점만 확인하면 된다.

---

## Valid Parameter Reference

### PerformanceMonitor Valid Parameters

```
output_dir, pricing, model_name, session_label
enable_transparency, enable_hallucination_detection, enable_security_metrics
security_config, enabled_security_trackers
enable_llm_judge, judge_model, judge_sample_rate, judge_criteria
judge_budget_per_day, judge_budget_storage_path
judge_max_context_chars, judge_escalation_model, judge_escalation_threshold, judge_seed
use_korean_tokenizer, use_semantic_hallucination, semantic_weight
enable_anomaly_detection, anomaly_baseline_window, anomaly_detection_window
auto_save, auto_save_interval, auto_save_filename
enable_otel_child_spans, ttft_variability_config, cost_predictability_config
gate_a_tcr_weight, gate_c_tcr_weight, gate_b_loop_weight
min_samples_default
prompt_version, agent_version, iteration_note
retention_mode, window_size
storage_backend
enable_pii_redaction, pii_redaction_categories
```

### @agent_eval Valid Parameters

```
task_type, question_arg, ground_truth_arg, task_id_prefix, context_arg
expected_tools_arg, expected_tools, framework, model_name
score_fn, completion_fn, task_id_fn, sample_rate
on_record, on_error, timeout, enabled
alert_rules, flush_every, preset
retry (RetryConfig), llm_judge (LLMJudgeConfig), security (SecurityConfig)
custom_parser, enable_hallucination_detection, rag_mode
enable_anomaly_detection, ttft_seconds, alert_error_mode
instructions, loop_detection, goal_alignment, reproducibility, fault_tolerance, plan_tracking
sla, threat_severity, efficiency, state_consistency, deadlock, observability
consensus, scope, context_retention, explainability, subtask_tracking, propagation
agent_role, graceful_degradation, compliance, resource_budget, conflict_resolution
tool_parameter_safety, knowledge_retention, retry_consistency, error_diagnosis, idempotency
threat_response, context_window, latency_attribution
```

---

## Gate A Tracker Attribution (Common Mistakes)

| Tracker | Attribution | Notes |
|---------|-------------|-------|
| `TaskCompletionTracker` | Gate A + C | `_a_vals[0]` TCR 컴포넌트 직접 기여 |
| `AccuracyEvaluator` | **Gate A** | `_a_vals[0]` 블렌딩 — `0.6×TCR + 0.4×Accuracy` (별도 항목이 아님) |
| `ResponseQualityEvaluator` | **Gate A** | relevance + completeness 평균 / 5 → `_a_vals` 추가 항목 |
| `HallucinationDetector` | **Gate C + G** | **not** Gate A |

**GoalAlignmentConfig 주의사항**: 기본값 `ignore_no_tool_tasks=True` — 도구 호출이 없는 태스크는 goal_alignment 평가에서 제외된다. QA·대화형 에이전트처럼 tool을 호출하지 않는 경우 `avg_goal_a = None`이 되어 Gate A 점수에 전혀 반영되지 않는다. 비도구 에이전트에 GoalAlignmentConfig를 사용하려면 `ignore_no_tool_tasks=False`로 설정해야 한다.

**AccuracyEvaluator `task_type` 매핑**: `"coding"` → `"code_generation"`으로 자동 정규화되어 AST 비교 평가가 적용된다. 두 값 모두 `_code_accuracy`로 라우팅된다.

---

## Coding Conventions

- **Formatter:** ruff, line-length=100
- **Python target:** 3.8+ (f-string, dataclass, typing)
- **Type hints:** required for all public functions; comment required when using `Any`
- **Docstrings:** include Args / Returns / Example sections
- **Error handling:** optional dependencies via `try/except ImportError`
- **Zero-division:** guard required in all ratio calculations
- **NaN handling:** `pd.isna()` check before pandas statistical calculations
- **API keys:** always `os.getenv()`, never hardcode
- **`enable_*` flags:** expensive operations (hallucination, security) default to `False`
- **Output-message language (SPEC-041):** every message Agent-Evaluator *emits at runtime*
  is **English** — CLI stdout/stderr, HTML report text, `logger.*` / `warnings.warn` /
  exception messages, MCP tool return strings, LiveGuardrail block/remediation text,
  hook messages, dashboard API `detail`/`message`, and any auto-generated
  `partial_reason` / recommendation / alert / insight text. **Exceptions (stay as-is):**
  (a) the *evaluated agent's own content* — task question/response/ground_truth, mock
  responses in demo helpers; (b) Korean-text-processing internals — particle/stopword
  sets and regexes in `gate_a_goal`/`gate_e_security`/`gate_f_multiagent`/`conversation`
  evaluators, the Korean RAG dataset generators (`datasets/`, `serve/routers/golden.py`,
  `korean_rag_*`); (c) source-only text — docstrings, `# comments`, `configs.py` field
  help. New user-facing strings must be written in English.

---

## Architecture Principles

1. **Layer independence** — Layer 1/2 must operate without external dependencies
2. **Harness independence** — 33 Configs defined in `gates/gate_x/configs.py`, aggregated in `monitor.py`
3. **Tracker isolation** — each tracker must be independently testable
4. **Minimal side effects** — no `sys.path`, `os.chdir()`, or global state modification
5. **Security metric isolation** — security trackers are opt-in due to performance impact
6. **Serve separation** — `serve/` is optional FastAPI; core logic must not depend on it

---

## Known Dependency Constraints

| Item | Status | Note |
|------|--------|------|
| `ragas>=0.4.0` | ✅ | EvaluationDataset, SingleTurnSample API supported |
| `[crewai,autogen]` pydantic conflict | 🟡 | Silently downgrades to pydantic 2.11.x |
| `arize-phoenix>=15.4.0` | ✅ | pydantic-ai compatibility resolved (previous `<14.7.0` pin removed) |
| `AnswerRelevancy` embeddings | 🟡 | Auto-configured only with OpenAI key |

---

## Testing

**117 files, 4,120+ test functions** in `tests/`.

```bash
pytest  # configured in pyproject.toml (testpaths, cov)
```

Note: `agent_evaluator/utils/transparency_manager.py` contains `TestTransparencyManager` — a **production class**, not a test file.

`agent_evaluator/utils/confidence.py` (SPEC-041 P5) — 단일 run 지표의 신뢰구간·표본 적정성·판정 확신도 순수 함수(stdlib만, numpy 무의존, seed 고정 결정적): `wilson_interval` · `bootstrap_mean_ci` · `required_n_for_halfwidth` · `verdict_confidence`. 소비: `reporting/comprehensive_report.py`.

---

## Accuracy Evaluation (AccuracyEvaluator)

| Metric | Weight | Method |
|--------|--------|--------|
| Token Overlap | 40% | F1 token matching |
| Jaccard Similarity | 30% | Set intersection/union |
| LCS Ratio | 20% | Longest Common Subsequence |
| Char Similarity | 10% | Levenshtein |

- `code_generation`/`coding`: 1.0 on successful AST parse
- `tool_use`: 0.6 if `tool_calls` is empty
