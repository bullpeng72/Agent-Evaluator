---
name: liveguardrail-standard-config
description: 새 프로젝트에 LiveGuardrail을 설치할 때 팀 표준 설정(위험 패턴, 스코프, 브랜치 보호)을 그대로 적용한다. 프로젝트 초기 설정 또는 기존 설정 점검 시 사용한다.
aoo_dependency: full
---

# LiveGuardrail 표준 설정 레시피

《하니스 메서드》 Part III(§10–13)와 SDK 가이드 Chapter 22(보안 관련 실시간 제어)가 검증한 설정을 팀 표준값으로 그대로 옮긴 레시피다. `branch_guard`·`team_concurrency`처럼 여러 세션을 조율하는 설정은 SDK 가이드 §22의 범위 밖(단일 세션 보안 통제만 다룬다)이라 이 책 Part III에만 있다.

## 기본 위험 패턴 (1.0.0 이후 기준)

```python
tool_parameter_safety=ToolParameterSafetyConfig(
    dangerous_patterns=[
        r"\brm\s+-rf\s+/", r";\s*rm\s+-rf", r"mkfs", r"dd\s+if=.*of=/dev/",
        r"curl.*\|\s*sh", r":\(\)\s*\{\s*:\s*\|\s*:",   # fork bomb
        r"--no-verify", r"git\s+push\s+.*--force", r"git\s+reset\s+--hard",
    ],
    scope_tool_names=["Bash"],          # 대소문자 무시 — Claude "Bash" / OpenCode "bash" 공용
    max_argument_length=100000,         # 파일 본문(Write/Edit 인자)이 arg_too_long으로 오탐되지 않도록
    fail_on_dangerous=True,
),
```

> ⚠️ 이 목록은 정규식 기반 안전망이지 완전한 보안 경계가 아니다(《하니스 메서드》 §3 참고). 배포 전 팀 상황에 맞게 항목을 검토·추가할 것.

> **1.0.0에서 바뀐 것.** 초기 참조 구현이 기본으로 넣던 `r"&&"`·`r"\|\|"`·`r"\.\./"`·단독 `rm`은 **뺐다** — 정상적인 코딩 세션(`mkdir a && cd a`, 상대경로 `../x`, 단일 파일 삭제)을 오탐해 세션이 잠기는 원인이었다(§8.4). 재귀+강제 삭제·`mkfs`·`dd of=/dev/`·fork bomb·파이프-투-셸만 남긴다. `scope_tool_names`·`max_argument_length`도 위 값이 `agent-eval claude install`의 **설치 기본값**이므로, 여기서 다시 적는 것은 "이 프로젝트가 이 동작에 의존한다"를 명시적으로 고정하려는 것이다(§34.4의 "버전 고정").

## 실시간 경로 안전장치 (기본값 — 보통 그대로 둔다)

```python
# guardrail_config.json 최상위 키. 아래는 전부 기본값이므로 명시 안 해도 동일하게 동작한다.
{
  "live_loop_window": 15,                       # 실시간 루프 판정은 최근 15호출만 — latch 방지
  "live_loop_blocking_types": ["consecutive_repeat"],  # 하드 차단은 '완전 동일 호출 반복'만.
                                               #  window_duplicate/response_similarity는 배치에만
  "circuit_breaker_after": 5,                   # 연속 5회 차단 → 남은 세션 관찰 전용(위반은 계속 감사)
  "circuit_breaker_recover_after": 10           # 트립 뒤 10회 연속 정상 실행 → 관찰 전용 자동 해제
                                               #  (기본 = circuit_breaker_after × 2, 0이면 세션 내내 sticky)
}
```

- [ ] 무한 루프를 실시간에서 하드 차단하고 싶지 않다면(개발·저작 세션) `loop_detection.on_loop_detected`를 `"warn"`으로 낮추고, 무한 루프 채점은 배치 Gate B(`LoopDetectionConfig`)에 맡긴다(원칙③).
- [ ] `guardrail_config.json`은 첫 `PreToolUse`에서 해석돼 세션에 고정된다 — 세션 도중 고쳐도 **다음 세션부터** 적용된다.
- [ ] 서킷 브레이커가 트립되면 그 자체가 에스컬레이션 신호다(《하니스 메서드》 §8.4). `circuit_breaker_recover_after`는 세션 도중 스스로 풀린 일시적 오설정이 세션의 나머지를 무방비로 두지 않게 하는 안전장치일 뿐 — 트립 기록은 남고, 왜 트립됐는지는 세션 종료 후 확인한다.

## 범주적 되돌림 — `human_only_patterns` (필요한 경우만)

```python
# guardrail_config.json 최상위 키. 비우면 꺼진 상태(옵트인).
{
  "human_only_patterns": ["terraform apply", "alembic upgrade", "kubectl apply -f"]
}
```

- [ ] 배포·마이그레이션처럼 **범주 자체를 에이전트에게 맡기지 않기로** 한 명령의 부분 문자열만 넣는다. 매치되면 그 호출을 차단하고 "사람이 직접 하라"고 되돌려 보낸다 — 사람 승인을 기다리는 게 아니다(《하니스 메서드》 §13).
- [ ] 자유 형식 셸 인자를 부분 문자열로만 보므로 보수적으로 넣는다. `terraform`만 넣으면 `terraform plan`(안전)까지 막힌다 — `terraform apply`처럼 되돌리기 어려운 동작을 특정한다.

## 브랜치 보호 (《하니스 메서드》 §12 기준)

```python
branch_guard=BranchGuardConfig(
    protected_branches=["main", "master"],
)
```

- [ ] 이 설정은 에이전트의 git 명령만 막는다 — 사람이 직접 커밋하는 경로는 pre-commit 훅(별도 설정)으로 메운다.

## 팀 동시성 (《하니스 메서드》 §11 기준, 필요한 경우만)

```python
team_concurrency=TeamConcurrencyConfig(
    owner="auto",
)
```

- [ ] `owner`를 절대 생략하지 않는다 — 생략하면 자기 자신이 정당하게 건 클레임까지 충돌로 잡혀 자기 세션이 차단된다(《하니스 메서드》 §11.2의 함정 경고 참고). `owner="auto"`는 `git config user.name`을 자동 조회하므로 이 실수 자체를 없앤다.

## AOO·AC 표준 설치에서 branch_guard·team_concurrency 켜기

`branch_guard`·`team_concurrency`는 **AOO·AC 어느 쪽 훅 브리지에도 꽂혀 있다**(《하니스 메서드》 §12.1 참고) — `agent-eval claude install`(AC)이든 `agent-eval opencode install`(AOO)이든, 표준 설치 명령이 등록하는 훅에 아래 값만 채우면 이 두 Config가 자동으로 켜진다. 둘 다 `live_guardrail_stdio.build_guardrail()`을 공유하는 같은 판정 파이프라인이라, 키 이름은 완전히 동일하다.

- [ ] **AC**: `.claude/.agent-evaluator/guardrail_config.json`에 `branch_guard`/`team_concurrency` 키를 추가한다(예: `{"branch_guard": {"protected_branches": ["main"]}, "team_concurrency": {"owner": "auto"}}`) — 파일이 없으면 `agent-eval claude install`이 만든 기본값을 그대로 복사한 뒤 이 두 키를 얹는다.
- [ ] **AOO**: `.opencode/plugin/agent-evaluator.ts`의 `GUARDRAIL_CONFIG` 상수에 같은 두 키를 TS 객체로 추가한다.
- [ ] 이렇게 설정한 값은 `agent-eval claude install`/`agent-eval opencode install`이 등록한 표준 훅 안에서 그대로 동작한다 — 별도 래퍼 스크립트나 직접 `LiveGuardrail()` 생성이 더 이상 필요 없다.
- [ ] 여러 세션·프레임워크를 조율해야 해서 훅 브리지를 아예 거치지 않는 커스텀 통합(§12.2.1의 `LiveGuardrail(branch_guard=..., team_concurrency=...)` 직접 생성 패턴)이 필요한 경우라면 그 방법도 여전히 유효하다 — 다만 AOO·AC 표준 설치를 쓰는 대부분의 팀에는 위 두 항목으로 충분하다.

## 적용 체크리스트

- [ ] 위 설정을 프로젝트의 `guardrail_config.json`(AC) 또는 `GUARDRAIL_CONFIG`(AOO)에 반영했다.
- [ ] `agent-eval claude doctor`(또는 `opencode doctor`)로 설치가 실제로 무해 명령→allow, 위험 명령→deny 하는지 라이브 검증했다.
- [ ] CI에 `agent-eval claims audit`(팀 동시성 사용 시)를 추가했다 — `claims-audit-ci` 스킬.
- [ ] 이 스킬의 기본 패턴이 프로젝트 특성과 안 맞는 부분(예: 이 프로젝트에서만 위험한 명령)이 있는지 검토했다.
