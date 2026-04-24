# Chapter 23. Gate 매핑: 프로젝트의 언어를 Harness로 번역하는 기술

> **이 챕터에서 배우는 것**
> - "실패 모드"에서 출발해 Gate Config를 결정하는 역방향 매핑 방법론
> - 어떤 프로젝트에도 통하는 범용 실패 모드 → Gate 매핑 템플릿
> - 비즈니스 영향도 기준으로 Gate 가중치를 설계하는 방법
> - Lecture_forge 12-에이전트 파이프라인의 전체 Gate A–G 매핑 실습
> - 매핑 결과를 팀과 공유하는 방법

> **독자별 읽기 가이드**
> - **👨‍💻 개발자**: §23.2(범용 템플릿)를 먼저 읽고, §23.4(Lecture_forge 매핑 실습)를 따라 자신의 프로젝트에 동시에 적용해 보면 가장 빠릅니다.
> - **📋 QA 관리자**: §23.1(왜 실패 모드에서 시작하는가) → §23.5(Gate 가중치 설계) 순으로 읽으면 팀 품질 기준 수립의 근거가 됩니다.
> - **이 챕터는 Ch22(분석)과 Ch24(이식) 사이의 다리입니다.** Ch22의 분석 결과를 손에 들고 읽어야 합니다.

---

## 23.1 번역의 올바른 방향

Gate 매핑에서 가장 흔한 실수는 **Gate A–G를 먼저 펼쳐놓고** "우리 시스템에 해당하는 Gate가 뭘까"를 고민하는 것이다. 이 방향은 두 가지 문제를 일으킨다.

### 문제 1: 피상적인 매핑

"Goal Achievement니까 목표가 있는 건 다 Gate A"라는 식으로 Gate 이름에서 연상한 항목을 채우게 된다. 결과는 이렇게 된다.

```python
# ✗ Gate를 먼저 보고 만든 매핑 — Lecture_forge 사례
# "강의 생성이 목표이니까 Gate A" → 파라미터를 채울 근거가 없어 기본값만 남는다

@agent_eval(monitor,
    task_type="document_creation",
    instructions=InstructionConfig(
        required_keywords=[],          # 뭘 넣어야 할지 모름
        fail_on_violation=False,       # 그냥 기본값
    ),
    goal_alignment=GoalAlignmentConfig(
        alignment_threshold=0.7,       # 0.7이 맞는 수치인지 근거 없음
    ),
)
def content_writer_agent(section_title, ground_truth=""): ...
```

`required_keywords=[]`는 아무것도 검사하지 않는다. `alignment_threshold=0.7`은 "0.7이 합리적일 것 같아서" 쓴 숫자다. 이 Config는 통과/실패 판정이 실제 품질과 무관하게 나온다.

### 문제 2: 중요한 실패 모드를 놓침

Gate를 먼저 보면 자연스럽게 Gate 이름이 연상시키는 케이스만 찾게 된다. **어떤 Gate에도 깔끔하게 맞지 않아 보이는 실패 모드를 건너뛰게 된다.**

Lecture_forge의 실제 사례: ContentWriter는 섹션 하나를 쓸 때 내부적으로 최대 3회 루프를 돈다. 섹션이 10개라면 최대 30회 LLM 호출이 발생한다. 이것은 순수하게 "비용 문제"처럼 보여서 Gate D를 떠올리게 된다. 그런데 같은 루프가 탈출 조건에 도달하지 못하면 무한 루프로 발전한다. 이것은 Gate B이기도 하다. Gate를 먼저 펼쳐놓으면 D에 올려놓거나 B에 올려놓거나 한쪽을 놓친다.

올바른 접근은 "ContentWriter 확장 루프"를 실패 모드로 먼저 기술한 다음, 이 하나의 실패 모드가 Gate B **와** Gate D **두 곳에 동시에 매핑된다**고 인식하는 것이다. 실패 모드 하나가 여러 Gate에 걸칠 수 있다는 것을 Gate 중심 사고는 보여주지 않는다.

### 올바른 방향: 실패 모드에서 출발

```
✗ 잘못된 방향:
   Gate A–G 목록 열기
     → "우리 시스템은 어디에 해당하는가?" 고민
       → Config 파라미터 채우기 (근거 없이)

✅ 올바른 방향:
   "우리 시스템이 망가지는 시나리오는 무엇인가?" 나열
     → 각 시나리오가 어느 Gate에 해당하는지 역매핑
       → Gate·Config 파라미터를 시나리오의 실제 수치로 채우기
```

같은 Lecture_forge, 올바른 방향으로 접근하면 이렇게 달라진다.

```python
# ✅ 실패 모드에서 출발한 매핑

# 실패 모드: "ContentWriter가 audience_level 필드를 무시하고 글을 쓴다"
#   → 이것은 CurriculumDesigner가 설정한 값이 ContentWriter에 전파되지 않는 문제
#   → Gate F PropagationConfig: key_facts에 "audience_level" 명시
#   → Gate A InstructionConfig: required_keywords에 실제 audience_level 값 주입

# 실패 모드: "ContentWriter 루프가 비용 상한 없이 실행된다"
#   → 루프 자체는 Gate B LoopDetectionConfig로 횟수 제한
#   → 비용 누적은 Gate D ResourceBudgetConfig로 상한 설정
#   → 하나의 실패 모드 → 두 Gate 동시 매핑

@agent_eval(monitor,
    task_type="document_creation",
    # Gate A — 실제 실패 시나리오에서 뽑은 키워드
    instructions=InstructionConfig(
        required_keywords=["학습목표", "예시", "실습"],  # 커리큘럼에서 가져온 실제 기준
        fail_on_violation=True,
    ),
    # Gate B — 루프 탈출 실패 시나리오
    loop_detection=LoopDetectionConfig(
        consecutive_repeat_threshold=3,  # 실제 max_retry=3 설정값에서 파생
    ),
    # Gate D — 비용 폭발 시나리오 ($0.035/강의 목표에서 역산)
    resource_budget=ResourceBudgetConfig(
        max_tokens=2000,   # 섹션당 예산: 강의당 $0.035 / 섹션 8개 / 토큰 단가에서 역산
    ),
    # Gate F — audience_level 미전파 시나리오
    propagation=PropagationConfig(
        key_facts=["audience_level", "section_count", "learning_outcomes"],
    ),
)
def content_writer_agent(section_title, ground_truth=""): ...
```

`required_keywords=["학습목표", "예시", "실습"]`는 실제 커리큘럼 요구사항에서 가져왔다. `max_tokens=2000`은 비즈니스 목표($0.035/강의)를 역산한 값이다. 모든 파라미터에 근거가 있다.

**실패 모드가 번역의 원재료다.** Gate는 그것을 분류하는 체계일 뿐이다. 실패 모드 없이 Gate를 먼저 채우면, 숫자는 나오지만 아무것도 감지하지 못하는 평가 시스템이 만들어진다.

---

## 23.2 실패 모드 카탈로그 작성법

### 세 가지 질문으로 실패 모드 찾기

실패 모드를 찾는 출발점은 세 가지 질문이다. 이 질문들은 서로 다른 레이어의 실패를 드러낸다.

**질문 1: "이 시스템이 망했다는 것을 어떻게 아는가?"**

최종 출력의 실패를 찾는다. 사용자가 직접 경험하는 실패다. 이것은 주로 Gate A와 Gate C와 연결된다.

예시: "생성된 강의가 학습 목표와 관련 없는 내용을 담고 있다" → Gate A

**질문 2: "이 시스템이 잘못된 방향으로 가고 있다는 것을 어떻게 아는가?"**

중간 과정의 실패를 찾는다. 최종 출력은 나왔지만 내부에서 뭔가 잘못되고 있는 경우다. Gate B, F, G와 연결된다.

예시: "ContentWriter가 3회 이상 루프를 돌고 있다는 것을 아무도 모른다" → Gate B

**질문 3: "겉으로는 돌아가지만 내부에서 문제가 생기는 경우는 무엇인가?"**

숨겨진 실패를 찾는다. 시스템은 출력을 내지만, 그 과정에서 비용이 폭발하거나 보안이 침해되는 경우다. Gate D와 Gate E와 연결된다.

예시: "외부 PDF에 프롬프트 인젝션이 포함되어 있어도 아무도 모른다" → Gate E

### 팀이 있다면: 사후 분석(Post-mortem)을 활용하라

실패 모드 카탈로그를 처음 만들 때 막힌다면, 팀에게 "지금까지 가장 큰 장애나 이슈가 무엇이었는가"를 물어라. 과거 장애 목록이 실패 모드 카탈로그의 80%를 채워준다.

혼자 개발한 프로젝트라면, "내가 걱정하지만 아직 일어나지 않은 것"들을 적는다. 걱정된다는 것 자체가 실패 가능성을 인식하고 있다는 증거다.

---

## 23.3 실패 모드 → Gate 매핑 범용 템플릿

다음 표는 어떤 프로젝트에도 적용할 수 있는 범용 매핑 템플릿이다. 왼쪽에서 자신의 프로젝트 실패 모드를 찾고, 오른쪽의 Gate와 Config를 연결한다.

@@HTML_START@@
<style>
.mapping-table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;}
.mapping-table th{padding:10px 14px;text-align:left;font-size:13px;}
.mapping-table td{padding:9px 14px;border-bottom:1px solid #eceff1;vertical-align:top;line-height:1.6;}
.gate-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;color:#fff;}
.config-name{font-family:monospace;font-size:11px;background:#f5f5f5;padding:2px 6px;border-radius:4px;display:inline-block;margin:1px 2px;}
</style>

<table class="mapping-table">
<thead>
<tr style="background:#37474f;color:#fff;">
  <th style="width:38%;">실패 모드</th>
  <th style="width:12%;">Gate</th>
  <th style="width:50%;">핵심 Config</th>
</tr>
</thead>
<tbody>
<tr style="background:#e8f5e9;">
  <td>최종 출력이 지정한 키워드·요구사항을 충족하지 못함</td>
  <td><span class="gate-badge" style="background:#2e7d32;">A</span></td>
  <td><span class="config-name">InstructionConfig(required_keywords=...)</span></td>
</tr>
<tr style="background:#e8f5e9;">
  <td>계획한 단계 수와 실제 완료된 단계 수가 다름</td>
  <td><span class="gate-badge" style="background:#2e7d32;">A</span></td>
  <td><span class="config-name">PlanConfig(min_steps=3, max_steps=15)</span></td>
</tr>
<tr style="background:#e8f5e9;">
  <td>목표와 실제 출력의 정렬 점수가 낮음</td>
  <td><span class="gate-badge" style="background:#2e7d32;">A</span></td>
  <td><span class="config-name">GoalAlignmentConfig(target_score=0.80)</span></td>
</tr>
<tr style="background:#e3f2fd;">
  <td>에이전트가 반복 루프에 빠져 종료되지 않음</td>
  <td><span class="gate-badge" style="background:#1565c0;">B</span></td>
  <td><span class="config-name">LoopDetectionConfig(consecutive_repeat_threshold=3)</span></td>
</tr>
<tr style="background:#e3f2fd;">
  <td>에이전트가 허가되지 않은 도구를 호출하거나 범위를 벗어남</td>
  <td><span class="gate-badge" style="background:#1565c0;">B</span></td>
  <td><span class="config-name">ScopeConfig(allowed_tools=[...])</span></td>
</tr>
<tr style="background:#e3f2fd;">
  <td>이전 단계에서 설정한 불변값이 중간에 바뀜</td>
  <td><span class="gate-badge" style="background:#1565c0;">B</span></td>
  <td><span class="config-name">StateConsistencyConfig(unchanged_keys=[...])</span></td>
</tr>
<tr style="background:#e3f2fd;">
  <td>도구 파라미터에 위험한 값이 들어갈 수 있음 (path traversal, SSRF 등)</td>
  <td><span class="gate-badge" style="background:#1565c0;">B</span></td>
  <td><span class="config-name">ToolParameterSafetyConfig(dangerous_patterns=[...], fail_on_dangerous=True)</span></td>
</tr>
<tr style="background:#fff3e0;">
  <td>API 오류 발생 후 작업 전체가 중단되고 부분 결과도 없음</td>
  <td><span class="gate-badge" style="background:#e65100;">C</span></td>
  <td><span class="config-name">FaultToleranceConfig(partial_success_threshold=0.5, check_fallback_attempts=True)</span></td>
</tr>
<tr style="background:#fff3e0;">
  <td>일부 리소스(이미지, 외부 API) 없이도 핵심 기능은 완성되어야 함</td>
  <td><span class="gate-badge" style="background:#e65100;">C</span></td>
  <td><span class="config-name">FaultToleranceConfig(partial_success_threshold=0.6)</span><!-- GracefulDegradationConfig는 존재하지 않음 — FaultToleranceConfig로 대체 --></td>
</tr>
<tr style="background:#fff3e0;">
  <td>동일 입력을 재실행했을 때 결과가 너무 달라짐</td>
  <td><span class="gate-badge" style="background:#e65100;">C</span></td>
  <td><span class="config-name">ReproducibilityConfig(max_variance=0.15)</span></td>
</tr>
<tr style="background:#fce4ec;">
  <td>응답 시간이 SLA를 초과함</td>
  <td><span class="gate-badge" style="background:#c62828;">D</span></td>
  <td><span class="config-name">SLAConfig(p95_ms=..., p99_ms=...)</span></td>
</tr>
<tr style="background:#fce4ec;">
  <td>토큰 사용량 또는 비용이 예산을 초과함</td>
  <td><span class="gate-badge" style="background:#c62828;">D</span></td>
  <td><span class="config-name">ResourceBudgetConfig(max_tokens=50_000, max_cost_usd=0.10, warn_at_pct=0.7)</span></td>
</tr>
<tr style="background:#fce4ec;">
  <td>토큰 효율이 낮고 완료 대비 비용이 과다함</td>
  <td><span class="gate-badge" style="background:#c62828;">D</span></td>
  <td><span class="config-name">EfficiencyConfig(cost_unit="tokens", target_cost_per_completion=500)</span></td>
</tr>
<tr style="background:#f3e5f5;">
  <td>외부 입력(파일, URL, 사용자 입력)에 프롬프트 인젝션이 포함될 수 있음</td>
  <td><span class="gate-badge" style="background:#6a1b9a;">E</span></td>
  <td><span class="config-name">ThreatSeverityConfig(severity_weights={"critical":10.0,"high":6.0}, fail_score=7.0, fail_on_critical=True)</span></td>
</tr>
<tr style="background:#f3e5f5;">
  <td>출력에 개인정보나 금지된 내용이 포함될 수 있음</td>
  <td><span class="gate-badge" style="background:#6a1b9a;">E</span></td>
  <td><span class="config-name">ComplianceConfig(pii_categories=["ssn","phone"], forbidden_data_patterns=[...])</span></td>
</tr>
<tr style="background:#e8eaf6;">
  <td>앞 에이전트의 중요한 정보가 뒤 에이전트에게 전달되지 않거나 왜곡됨</td>
  <td><span class="gate-badge" style="background:#283593;">F</span></td>
  <td><span class="config-name">PropagationConfig(key_facts=["audience_level","learning_objectives"], similarity_threshold=0.7)</span></td>
</tr>
<tr style="background:#e8eaf6;">
  <td>에이전트가 자신의 역할 범위를 넘어서 다른 에이전트의 결과를 수정함</td>
  <td><span class="gate-badge" style="background:#283593;">F</span></td>
  <td><span class="config-name">AgentRoleConfig(role_name="content_writer", forbidden_action_keywords=["modify_curriculum"])</span></td>
</tr>
<tr style="background:#e0f2f1;">
  <td>어느 단계에서 지연이 발생하는지 알 수 없음</td>
  <td><span class="gate-badge" style="background:#00695c;">G</span></td>
  <td><span class="config-name">LatencyAttributionConfig(max_tool_time_ratio=0.7, max_unattributed_ratio=0.2)</span></td>
</tr>
<tr style="background:#e0f2f1;">
  <td>LLM이 어떤 근거로 이 답변을 생성했는지 설명이 부족함</td>
  <td><span class="gate-badge" style="background:#00695c;">G</span></td>
  <td><span class="config-name">ExplainabilityConfig(min_reasoning_length=50, require_citations=True)</span></td>
</tr>
</tbody>
</table>
@@HTML_END@@

하나의 실패 모드가 여러 Gate에 걸쳐 있어도 된다. "에이전트가 무한 루프를 도는 동안 비용이 폭발한다"는 Gate B(루프 탐지)와 Gate D(비용 예산) 모두에 해당한다. 중요한 것은 **어떤 실패도 측정되지 않는 상태로 남지 않는 것**이지, 하나의 실패가 정확히 하나의 Gate에만 속해야 한다는 것이 아니다.

---

## 23.4 Lecture_forge 매핑 실습: 실패 모드에서 Config까지

Ch22에서 발굴한 Lecture_forge의 실패 모드를 이제 Gate Config로 번역한다.

### 실패 모드 카탈로그

먼저 세 가지 질문을 Lecture_forge에 적용한다.

**"이 시스템이 망했다는 것을 어떻게 아는가?"**

- 생성된 강의가 사용자가 지정한 학습 목표를 다루지 않는다
- 커리큘럼에 계획된 섹션 5개 중 3개만 완성됐다
- 전체 품질 점수가 80 미만이어서 수업에 쓸 수 없다

**"잘못된 방향으로 가고 있다는 것을 어떻게 아는가?"**

- ContentWriter가 확장 루프를 3회 이상 돌고 있다 (`MAX_EXPANSION_ITERATIONS=3` 위반)
- ContentWriter 프롬프트에서 `audience_level`이 누락되어 있다 (`curriculum.audience_level` 전파 실패)
- RevisionAgent가 수정을 시도했지만 품질 점수가 오히려 내려갔다

**"겉으로는 돌아가지만 내부에서 문제가 생기는 경우는?"**

- 외부 PDF에 "ignore previous instructions"가 포함되어 있어도 아무도 모른다
- 강의 1건 생성 비용이 $0.035 목표를 초과해도 알림이 없다
- ContentAnalyzer가 추출한 `key_topics`가 ContentWriter에 전달되지 않아도 발견되지 않는다

### Gate A — Goal Achievement

가장 먼저 매핑할 Gate는 A다. 이것은 제품의 존재 이유와 직결된다.

> **📌 Config 적용 방법**: 이 섹션의 Config 코드는 `@agent_eval` 데코레이터에 전달합니다.

```python
@agent_eval(monitor, task_type="document_creation",
    instructions=InstructionConfig(...),
    plan=PlanConfig(...),
    context_retention=ContextRetentionConfig(...),
)
def content_writer_agent(section_title: str, ground_truth: str = "") -> str: ...
```

```python
# 실패 모드: "학습 목표가 본문에 반영되지 않는다"
InstructionConfig(
    required_keywords=lecture_request.learning_objectives,
    fail_on_violation=True,
    # 학습 목표 키워드가 생성된 본문에 등장하지 않으면 Gate A 실패
)

# 실패 모드: "계획된 섹션이 모두 완성되지 않는다"
PlanConfig(
    min_steps=3,    # 최소 도입+본문+마무리
    max_steps=15,   # 60분 강의 최대 섹션 수
    # step_completion_threshold 파라미터는 존재하지 않음
    # 섹션 완성 여부는 TCR(Task Completion Rate)로 측정된다
)

# 실패 모드: "섹션 간 주제 흐름이 끊긴다"
ContextRetentionConfig(
    retention_threshold=0.80,
    key_entities=["topic", "audience_level"],  # 유지 확인할 핵심 엔티티
    # window_size 파라미터는 존재하지 않음 — context_arg로 컨텍스트 필드 지정
)
```

### Gate B — Behavioral Integrity

에이전트가 "제 역할 범위 안에서만" 동작하는지 확인한다.

```python
# 실패 모드: "ContentWriter 확장 루프가 3회를 초과한다"
# MAX_EXPANSION_ITERATIONS = 3 이 코드에 이미 있다 → 직접 매핑
LoopDetectionConfig(
    consecutive_repeat_threshold=3,  # 코드 상수와 동일값
    window_size=5,
)

# 실패 모드: "audience_level이 ContentWriter 프롬프트에서 누락된다"
StateConsistencyConfig(
    unchanged_keys=[
        "curriculum.topic",
        "curriculum.duration",
        "curriculum.audience_level",  # ← 이 값이 파이프라인 전체에서 불변이어야 함
    ],
)

# 실패 모드: "Web Scraper에 내부 URL이 들어갈 수 있다"
ToolParameterSafetyConfig(
    # dangerous_patterns: 도구 파라미터에 이 패턴이 감지되면 경고/차단
    dangerous_patterns=["file://", "127.0.0.1", "localhost", "metadata."],
    fail_on_dangerous=True,   # critical 패턴 감지 시 Gate B 실패로 처리
    # param_names 파라미터는 존재하지 않음 — tool_schemas 또는 forbidden_argument_keys 사용
)
```

### Gate C — Reliability

오류가 났을 때 어떻게 회복하는가를 측정한다.

```python
# 실패 모드: "API Rate Limit 오류 후 전체 섹션이 누락된다"
FaultToleranceConfig(
    partial_success_threshold=0.5,  # 50% 이상 부분 완성 = 복구 인정
    check_fallback_attempts=True,   # fallback 도구 호출 시도를 추적
    # expected_recovery_rate, max_recovery_time_ms, tracked_error_types 파라미터 없음
    # 오류 후 복구 여부는 TaskResult.has_error + fallback_tools 조합으로 판정
)

# 실패 모드: "이미지 서버가 다운돼도 텍스트 강의는 완성되어야 한다"
# GracefulDegradationConfig 는 API에 존재하지 않음
# → FaultToleranceConfig(partial_success_threshold=0.6)으로 대체:
#   텍스트 섹션이 60% 이상 완성되면 이미지 부재에도 불구하고 복구 성공으로 간주
FaultToleranceConfig(
    partial_success_threshold=0.6,
    check_fallback_attempts=True,
)
```

### Gate D — Performance Contract

`$0.035/강의`라는 비즈니스 계약이 코드에 명시된 목표다. 이것을 Config로 옮긴다.

```python
# 실패 모드: "섹션 생성이 2분을 넘어간다"
SLAConfig(
    p95_ms=120_000,    # 섹션 1개 P95 2분
    p99_ms=300_000,    # P99 5분 (Vision AI + RAG 포함)
    # sla_budget_ms 파라미터는 존재하지 않음 — budget_usd 또는 token_limit 사용
)

# 실패 모드: "강의 1건 비용이 $0.035를 초과한다"
# $0.035 목표 × 3배 = $0.10 상한 (초기에는 여유 있게 설정)
ResourceBudgetConfig(
    max_tokens=50_000,          # 섹션당 토큰 상한 (max_tokens_per_task → max_tokens)
    max_cost_usd=0.10,
    warn_at_pct=0.7,            # 70% 도달 시 경고 (warn_threshold_ratio → warn_at_pct)
)

# 실패 모드: "RAG 쿼리 대비 완료 효율이 낮다"
EfficiencyConfig(
    cost_unit="tokens",
    target_cost_per_completion=500,   # 섹션당 500토큰 목표
    # target_tool_calls_per_completion 파라미터는 존재하지 않음
)
```

### Gate E — Security Boundary

Lecture_forge는 **외부 입력이 LLM 프롬프트에 직접 삽입되는 구조**다. Gate E 우선순위가 가장 높은 이유다.

```python
# 실패 모드: "PDF에 삽입된 프롬프트 인젝션을 탐지하지 못한다"
ThreatSeverityConfig(
    # severity_weights: 위협 유형별 가중 점수 (합산 점수 기반으로 fail_score 초과 시 실패)
    severity_weights={"critical": 10.0, "high": 6.0, "medium": 3.0},
    fail_score=7.0,          # 이 점수 이상이면 Gate E 실패
    fail_on_critical=True,   # critical 위협이 1건만 있어도 즉시 실패
    # critical_threshold, high_threshold, block_on_critical 파라미터는 존재하지 않음
)

# 실패 모드: "수집된 콘텐츠에 개인정보나 인젝션 패턴이 있어도 모른다"
ComplianceConfig(
    pii_categories=["ssn", "phone"],  # 탐지할 PII 카테고리
    forbidden_data_patterns=[         # 금지 패턴 (forbidden_patterns → forbidden_data_patterns)
        r"ignore previous instructions",
        r"system:\s*(you are|act as)",
        r"(?i)jailbreak",
        r"\d{6}-\d{7}",           # 주민등록번호 패턴
        r"(?i)confidential",      # 기밀 문서 표시
    ],
    # scan_fields 파라미터는 존재하지 않음 — InputSanitizationTracker로 필드별 스캔 처리
)

# 실패 모드: "위협 탐지 후 파이프라인이 중단되는지 확인이 안 된다"
ThreatResponseConfig(
    abort_markers=["abort_collection", "THREAT_BLOCKED"],  # 차단 응답 마커
    isolation_markers=["sanitize", "skip_chunk"],          # 격리 응답 마커
    score_clean_tasks=True,
    # expected_responses, response_timeout_ms 파라미터는 존재하지 않음
)
```

### Gate F — Multi-Agent Coordination

12개 에이전트가 정보를 손실 없이 이어받는지 측정한다.

```python
# 실패 모드: "ContentAnalyzer의 분석 결과가 ContentWriter에 완전히 전달되지 않는다"
PropagationConfig(
    source_agent="curriculum_designer",   # 정보를 보내는 에이전트
    key_facts=[                           # 전파 확인할 핵심 사실 (expected_fields → key_facts)
        "topic",
        "audience_level",
        "learning_objectives",
    ],
    similarity_threshold=0.7,    # 수신 응답에 key_facts가 이 유사도 이상으로 포함돼야 통과
    penalize_distortion=True,
    # propagation_chain, max_distortion_rate 파라미터는 존재하지 않음
)

# 실패 모드: "ContentWriter가 CurriculumDesigner의 결과를 무시하고 임의로 재설계한다"
AgentRoleConfig(
    role_name="content_writer",               # role_name (agent_id → role_name)
    allowed_action_keywords=["generate_content", "query_rag"],
    forbidden_action_keywords=["modify_curriculum", "skip_rag_query"],
    allowed_tools=["rag_query"],
    forbidden_tools=["curriculum_edit"],
    # agent_id, allowed_roles, forbidden_actions 파라미터는 존재하지 않음
)

# 실패 모드: "RevisionAgent와 QualityEvaluator가 수정 방향에 합의하지 못한다"
ConflictResolutionConfig(
    conflict_markers=["contradiction", "inconsistent", "disagree"],
    resolution_markers=["resolved", "agreed", "accepted"],
    check_resolution_quality=True,
    # expected_resolution_patterns, max_resolution_time_ms 파라미터는 존재하지 않음
)
```

### Gate G — Observability

어느 에이전트가 병목인지 즉시 알 수 있어야 한다.

```python
# 실패 모드: "전체 생성 시간 120초 중 어느 단계가 몇 초를 쓰는지 모른다"
LatencyAttributionConfig(
    max_tool_time_ratio=0.7,        # 도구 호출 시간이 전체의 70% 초과 시 경고
    max_unattributed_ratio=0.2,     # 출처 불명 지연이 20% 초과 시 경고
    # tool_latency_key/model_latency_key/network_latency_key로 EvalMetadata 필드 매핑 가능
    # segments, track_per_segment 파라미터는 존재하지 않음
)

# 실패 모드: "ContentWriter가 어떤 RAG 결과를 근거로 이 내용을 썼는지 모른다"
ExplainabilityConfig(
    min_reasoning_length=50,
    require_citations=True,         # require_source_citation → require_citations
)

# 실패 모드: "어느 에이전트가 실행 중인지, 현재 몇 번째 섹션인지 실시간으로 알 수 없다"
ObservabilityConfig(
    required_span_attributes=[      # OTEL 스팬에 반드시 있어야 하는 속성
        "task_id",
        "agent_name",
        "section_index",
        "quality_score",
    ],
    audit_events=["section_start", "section_complete", "retry_triggered"],
    min_coverage=0.95,
    # track_internal_state, state_fields 파라미터는 존재하지 않음
)
```

---

## 23.5 Gate 가중치: 모든 Gate는 동등하지 않다

Gate 판정은 7개 Gate의 가중 평균이다. 기본 가중치는 모두 1.0이지만, 이것을 그대로 쓰면 비즈니스에서 중요한 Gate와 그렇지 않은 Gate가 동등하게 취급된다.

### 가중치 설계 원칙

가중치를 결정하는 질문은 하나다: **이 Gate가 실패했을 때 비즈니스에 어떤 영향을 주는가?**

이것을 세 가지 기준으로 점수화한다.

@@HTML_START@@
<style>
.weight-table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0;}
.weight-table th{background:#37474f;color:#fff;padding:10px 14px;}
.weight-table td{padding:9px 14px;border-bottom:1px solid #eceff1;vertical-align:top;}
.score-bar{display:inline-block;height:8px;border-radius:4px;margin-right:6px;vertical-align:middle;}
</style>

<table class="weight-table">
<tr>
  <th>기준</th>
  <th>가중치 높임 (×1.5–×3.0)</th>
  <th>가중치 보통 (×1.0)</th>
  <th>가중치 낮춤 (×0.5)</th>
</tr>
<tr>
  <td><strong>회복 어려움</strong></td>
  <td>보안 사고, 데이터 유출, 서비스 다운</td>
  <td>품질 저하, 느린 응답</td>
  <td>로깅 누락, 모니터링 공백</td>
</tr>
<tr>
  <td><strong>발생 빈도</strong></td>
  <td>매 실행마다 관여하는 Gate</td>
  <td>간헐적으로 관여하는 Gate</td>
  <td>특정 조건에서만 관여하는 Gate</td>
</tr>
<tr>
  <td><strong>사용자 가시성</strong></td>
  <td>사용자가 즉시 체감하는 실패</td>
  <td>운영자만 아는 실패</td>
  <td>내부 메트릭에만 나타나는 실패</td>
</tr>
</table>
@@HTML_END@@

### Lecture_forge 가중치 설계

| Gate | 기본 가중치 | Lecture_forge 가중치 | 근거 |
|------|-----------|-------------------|------|
| A — Goal Achievement | 1.0 | **2.0** | 학습 목표 미달성은 제품의 존재 이유 부정. 사용자가 즉시 체감 |
| B — Behavioral Integrity | 1.0 | 1.0 | 루프·범위 위반은 중요하지만 즉각적 비즈니스 영향은 간접적 |
| C — Reliability | 1.0 | 1.0 | API 복구는 중요하지만 이미 `@make_api_retry`로 1차 방어됨 |
| D — Performance Contract | 1.0 | **1.2** | $0.035 비용 목표가 명시적 비즈니스 제약. 선형 초과 위험 |
| E — Security Boundary | 1.0 | **3.0** | 프롬프트 인젝션은 보안 사고. 발생 시 회복 어려움. 최고 우선 |
| F — Multi-Agent Coord. | 1.0 | **1.5** | 12에이전트 체인에서 왜곡이 증폭됨. 중간 실패 발견 어려움 |
| G — Observability | 1.0 | 1.0 | 관측성은 중요하지만 다른 Gate 실패의 직접 원인은 아님 |

```bash
# CI/CD에서 이 가중치로 판정
agent-eval gate results/latest.json \
    --min-gate-score 0.75 \
    --group-weights A:2.0,E:3.0,F:1.5,D:1.2
```

---

## 23.6 매핑 결과 정리: 한 눈에 보는 Config 전체

지금까지 작업한 Lecture_forge의 Gate 매핑 전체를 하나로 정리한다. 이것이 Ch25에서 `build_lecture_monitor()` 함수의 뼈대가 된다.

> **⚠️ 핵심 구조 원칙**
>
> Harness Gate Config(InstructionConfig, LoopDetectionConfig 등 33개)는 **`PerformanceMonitor.__init__()`이 아니라 `@agent_eval` 데코레이터에 전달**한다.
>
> `PerformanceMonitor`는 `output_dir`, `enable_*` 플래그, `auto_save` 같은 **기록 설정**만 받는다.
> Gate Config는 에이전트 함수를 감싸는 데코레이터에서 태스크별로 적용된다.

```python
# Lecture_forge Gate A–G 전체 매핑 요약
# ① PerformanceMonitor — 기록 설정만 (Gate Config 없음)

monitor = PerformanceMonitor(
    output_dir="lecture_eval_results/",
    enable_security_metrics=True,   # Gate E 보안 트래커 활성화
    auto_save=True,
    auto_save_interval=5,
)

# ② Gate Config는 @agent_eval 데코레이터에 전달
#    (실제 에이전트 함수에 붙인다 — Ch25에서 전체 구현)

@agent_eval(monitor,
    task_type="document_creation",

    # ── Gate A: 학습목표·섹션구조 달성 ──────────────────────────────
    instructions=InstructionConfig(
        required_keywords=lecture_request.learning_objectives,
        fail_on_violation=True,
    ),
    plan=PlanConfig(
        min_steps=3, max_steps=15,
    ),
    context_retention=ContextRetentionConfig(
        retention_threshold=0.80,
        key_entities=["topic", "audience_level"],
    ),

    # ── Gate B: 루프 제어·상태 불변성 ───────────────────────────────
    loop_detection=LoopDetectionConfig(consecutive_repeat_threshold=3),
    state_consistency=StateConsistencyConfig(
        unchanged_keys=["curriculum.topic", "curriculum.audience_level"],
    ),
    tool_param_safety=ToolParameterSafetyConfig(
        dangerous_patterns=["file://", "127.0.0.1", "localhost", "metadata."],
        fail_on_dangerous=True,
    ),

    # ── Gate C: 오류 복구·부분 완성 보장 ────────────────────────────
    fault_tolerance=FaultToleranceConfig(
        partial_success_threshold=0.5,
        check_fallback_attempts=True,
    ),
    retry_consistency=RetryConsistencyConfig(
        improvement_threshold=0.1,
        penalize_degradation=True,
    ),

    # ── Gate D: $0.035 비용 계약·레이턴시 SLA ───────────────────────
    sla=SLAConfig(p95_ms=120_000, p99_ms=300_000),
    resource_budget=ResourceBudgetConfig(
        max_tokens=50_000,
        max_cost_usd=0.10,
        warn_at_pct=0.7,
    ),
    efficiency=EfficiencyConfig(
        cost_unit="tokens",
        target_cost_per_completion=500,
    ),

    # ── Gate E: 외부 콘텐츠 보안·인젝션 방어 ────────────────────────
    threat_severity=ThreatSeverityConfig(
        severity_weights={"critical": 10.0, "high": 6.0, "medium": 3.0},
        fail_score=7.0,
        fail_on_critical=True,
    ),
    compliance=ComplianceConfig(
        pii_categories=["ssn", "phone"],
        forbidden_data_patterns=[
            r"ignore previous instructions",
            r"system:\s*(you are|act as)",
            r"\d{6}-\d{7}",
        ],
    ),
    threat_response=ThreatResponseConfig(
        abort_markers=["abort_collection", "THREAT_BLOCKED"],
        isolation_markers=["sanitize", "skip_chunk"],
        score_clean_tasks=True,
    ),

    # ── Gate F: 12에이전트 정보 전파 무결성 ─────────────────────────
    propagation=PropagationConfig(
        source_agent="curriculum_designer",
        key_facts=["topic", "audience_level", "learning_objectives"],
        similarity_threshold=0.7,
    ),
    agent_role=AgentRoleConfig(
        role_name="content_writer",
        allowed_action_keywords=["generate_content", "query_rag"],
        forbidden_action_keywords=["modify_curriculum", "skip_rag_query"],
        allowed_tools=["rag_query"],
        forbidden_tools=["curriculum_edit"],
    ),

    # ── Gate G: 병목 진단·근거 추적 ─────────────────────────────────
    latency_attribution=LatencyAttributionConfig(
        max_tool_time_ratio=0.7,
        max_unattributed_ratio=0.2,
    ),
    explainability=ExplainabilityConfig(
        min_reasoning_length=50,
        require_citations=True,
    ),
    observability=ObservabilityConfig(
        required_span_attributes=["task_id", "agent_name", "section_index", "quality_score"],
        audit_events=["section_start", "section_complete", "retry_triggered"],
        min_coverage=0.95,
    ),
)
def content_writer_agent(section_title: str, ground_truth: str = "") -> str:
    """실제 구현은 Ch25에서 완성된다."""
    ...
```

---

## 23.7 일반화: 어떤 프로젝트에도 이 방법을 쓸 수 있다

### Config 파라미터에 프로젝트 상수를 직접 연결하라

매핑에서 가장 중요한 원칙은 **코드에 이미 있는 상수를 Config에 그대로 연결하는 것**이다.

Lecture_forge의 `MAX_EXPANSION_ITERATIONS = 3`이 `LoopDetectionConfig(consecutive_repeat_threshold=3)`이 된 것처럼, 프로젝트의 제한값과 Config 파라미터를 1:1로 대응시키면 Config가 코드의 두 번째 명세서가 된다.

```python
# 좋은 예: 프로젝트 상수와 Config 파라미터가 같은 값
from your_project.config import MAX_RETRIES, COST_BUDGET_USD, QUALITY_THRESHOLD
from agent_evaluator.decorators import agent_eval

# PerformanceMonitor는 기록 설정만
monitor = PerformanceMonitor(
    output_dir="eval_results/",
    enable_security_metrics=True,
)

# Gate Config는 @agent_eval 데코레이터에 — 프로젝트 상수와 1:1 연결
@agent_eval(monitor,
    task_type="qa",
    loop_detection=LoopDetectionConfig(
        consecutive_repeat_threshold=MAX_RETRIES,   # 코드 상수와 동일값
    ),
    resource_budget=ResourceBudgetConfig(
        max_cost_usd=COST_BUDGET_USD * 3,           # 목표의 3배 = 상한
        max_tokens=50_000,
    ),
    fault_tolerance=FaultToleranceConfig(
        partial_success_threshold=QUALITY_THRESHOLD / 100,
        check_fallback_attempts=True,
    ),
)
def my_agent(question: str, ground_truth: str = "") -> str: ...
```

### Gate 매핑이 안 되는 경우

매핑 작업을 하다 보면 "이 실패 모드는 어떤 Gate에도 맞지 않는다"는 경우가 생긴다. 이럴 때는 두 가지를 확인한다.

첫째, 그 실패 모드가 정말 AI 에이전트의 동작 실패인가? 데이터베이스 연결 실패, 네트워크 장애 같은 인프라 실패는 agent-evaluator가 아니라 인프라 모니터링 도구의 영역이다.

둘째, 실패 모드가 너무 추상적으로 정의되어 있는 것은 아닌가? "품질이 나쁘다"는 Gate A에 맞지 않는다. "학습 목표 키워드가 3개 이상 누락됐다"는 `InstructionConfig`에 바로 매핑된다. 구체화하면 반드시 매핑된다.

---

> **이 챕터에서 배운 것**
>
> Gate 매핑은 Gate를 먼저 보는 것이 아니라, 프로젝트의 실패 모드를 먼저 나열하는 것에서 시작한다. 세 가지 질문 — "망했다는 것을 어떻게 아는가", "잘못된 방향을 어떻게 아는가", "겉으로는 돌아가지만 내부에서 문제가 생기는 경우는 무엇인가" — 이 실패 모드의 세 레이어를 드러낸다.
>
> Lecture_forge 매핑의 핵심 발견은 두 가지였다. 코드에 이미 있는 상수(`MAX_EXPANSION_ITERATIONS=3`)가 Config 파라미터와 1:1로 대응된다. Gate E의 가중치를 3.0으로 높인 이유는 외부 PDF·URL이 LLM 프롬프트에 직접 삽입되는 구조적 취약점 때문이다.
>
> **다음 챕터**에서는 이 매핑 결과를 손에 들고 실제 코드에 첫 번째 측정점을 삽입한다. 목표는 30분 안에 첫 측정값을 얻는 것이다.

```
# 출처: Evaluator_Examples/ch23_gate_mapping.py
```
