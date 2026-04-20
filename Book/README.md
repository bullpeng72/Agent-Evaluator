# AI 에이전트 Harness Engineering 실무 가이드
## Agent-Evaluator로 구현하는 프로덕션 AI 품질 시스템

**저자**: Sungwoo Kim  
**버전**: 2.0 (Agent-Evaluator v0.8.2 기준)  
**언어**: 한국어

> **핵심 전환**: "25개 지표를 측정하는 도구" → "58개 지표 기반 Harness Engineering 배포 판단 시스템"  
> Tracker(관찰/측정) × Config(기준 선언) × Gate(배포 판정) — 3요소가 하나의 Harness를 구성한다.

---

## 목차

### 머리말
- [서문](00_서문.md)

### Part I — 기초: AI 에이전트 Harness Engineering을 시작하며
- [Chapter 1. AI 에이전트 품질 평가란 무엇인가](Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md)
- [Chapter 2. Agent-Evaluator 첫 시작](Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md)

### Part II — Harness 지표 체계: 58개 지표를 Group A-G로 이해하다

> **Harness 3요소**: Tracker(측정) × Config(기준 선언) × Gate(배포 판정)  
> 각 챕터는 하나의 품질 차원(Group)을 담당하며, Tracker와 Config를 함께 다룬다.

- [Chapter 3. Harness Engineering 기초](Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md)
- [Chapter 4. Group A — 목표달성 지표](Part_II_지표시스템/Chapter_04_GroupA_목표달성.md)
- [Chapter 5. Group B — 행동무결성 지표](Part_II_지표시스템/Chapter_05_GroupB_행동무결성.md)
- [Chapter 6. Group C — 신뢰성 지표](Part_II_지표시스템/Chapter_06_GroupC_신뢰성.md)
- [Chapter 7. Group D — 성능계약 지표](Part_II_지표시스템/Chapter_07_GroupD_성능계약.md)
- [Chapter 8. Group E — 보안경계 지표](Part_II_지표시스템/Chapter_08_GroupE_보안경계.md)
- [Chapter 9. Group F — 다중에이전트 협업 지표](Part_II_지표시스템/Chapter_09_GroupF_다중에이전트.md)
- [Chapter 10. Group G — 운영관측성 지표](Part_II_지표시스템/Chapter_10_GroupG_운영관측성.md)

### Part III — 개발자 가이드: 코드로 Harness를 심다

- [Chapter 11. 평가 데이터 설계](Part_III_개발자가이드/Chapter_11_평가데이터_설계.md) ← **Part II 직후 읽기 권장**
- [Chapter 12. 데코레이터 완전 정복](Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md)
- [Chapter 13. 21개 프레임워크 통합](Part_III_개발자가이드/Chapter_13_프레임워크_통합.md)

### Part IV — QA 관리자 가이드: Harness 기준을 세우고 지속적으로 모니터링하다
- [Chapter 14. 임계값 설정과 품질 기준 수립](Part_IV_QA관리자가이드/Chapter_14_임계값설정_품질기준.md)
- [Chapter 15. 대시보드와 시각화](Part_IV_QA관리자가이드/Chapter_15_대시보드_시각화.md)
- [Chapter 16. 알림 시스템 운영](Part_IV_QA관리자가이드/Chapter_16_알림시스템_운영.md)
- [Chapter 17. 주간·월간 품질 리뷰](Part_IV_QA관리자가이드/Chapter_17_주간월간_품질리뷰.md)

### Part V — 프로덕션 운영: Harness Gate로 배포하고 지속적으로 개선하다
- [Chapter 18. CI/CD Harness Gate 운영](Part_V_프로덕션운영/Chapter_18_CICD_품질게이팅.md)
- [Chapter 19. OpenTelemetry와 Phoenix 실시간 모니터링](Part_V_프로덕션운영/Chapter_19_Phoenix_OTEL_모니터링.md)
- [Chapter 20. 프로덕션 배포 전략](Part_V_프로덕션운영/Chapter_20_프로덕션_배포전략.md)
- [Chapter 21. 지속 평가·자기개선 파이프라인](Part_V_프로덕션운영/Chapter_21_종합_실무파이프라인.md)

### 부록 — 이론 심화 (먼저 읽어도 좋습니다)
> **추천**: Appendix G→H→I는 Part II를 읽기 전에 먼저 보면 "왜 이 지표인가"에 대한 이론적 근거를 갖출 수 있습니다.

- [Appendix G. AI 품질 평가 이론적 기초](Appendix/G_AI평가_이론적기초.md) — BLEU→LLM Judge 역사, Harness Engineering 이론, AI Native 평가 이론, 보정(Calibration), 공정성, 출력 구조 검증
- [Appendix H. 지표 알고리즘 수학적 상세 레퍼런스](Appendix/H_알고리즘_수학적_레퍼런스.md) — 58개 지표 수식, 의사코드, 계산 예시, 엣지케이스
- [Appendix I. 지표 비교 분석 및 선택 가이드](Appendix/I_지표_비교분석_선택가이드.md) — BLEU vs Token F1, 환각 탐지 3종 비교, LLM Judge 편향 분석, 비용 프로파일

### 부록 — 실무 레퍼런스
- [Appendix A. 58개 지표 완전 레퍼런스](Appendix/A_58개지표_레퍼런스.md)
- [Appendix B. CLI 명령어 레퍼런스](Appendix/B_CLI_명령어_레퍼런스.md)
- [Appendix C. 환경변수 & 설정 레퍼런스](Appendix/C_환경변수_설정_레퍼런스.md)
- [Appendix D. 프레임워크 호환성 매트릭스](Appendix/D_프레임워크_호환성_매트릭스.md)
- [Appendix E. 에러 코드 & 트러블슈팅](Appendix/E_에러코드_트러블슈팅.md)
- [Appendix F. 용어 사전](Appendix/F_용어사전.md)

### 부록 — 고급 실무 심화
> **추천**: 프로덕션 장애 대응, 보안 레드팀, 예산 제약 환경이라면 이 부록들을 Part V와 병행해서 읽으세요.

- [Appendix J. 프로덕션 실패 패턴 카탈로그](Appendix/J_프로덕션_실패패턴_카탈로그.md) — 20가지 실제 장애 시나리오 × 탐지 코드 × 대응 전략, Gate별 Early Warning 시스템
- [Appendix K. 적대적 강건성과 레드팀 평가](Appendix/K_적대적_강건성과_레드팀_평가.md) — OWASP LLM Top 10 매핑, 31개 공격 패턴, 5단계 레드팀 방법론, 에이전트 유형별 보안 Harness Config
- [Appendix L. 예산 최적화 평가 설계](Appendix/L_예산최적화_평가설계.md) — 25개 Tracker 비용 프로파일, 3단계 예산 모델, Pareto 최적 조합, LLMJudge 지식 증류, ROI 프레임워크

---

## 지표를 이해하는 두 가지 관점

Harness Engineering의 58개 지표는 **두 가지 관점**에서 바라볼 수 있다. 어느 쪽이 맞고 틀리냐의 문제가 아니라, **독자의 역할**에 따라 진입점이 다르다는 의미다.

### 관점 1 — Gate A–G (품질 차원별 분류)
"에이전트가 목표를 달성했는가? 보안 경계를 지켰는가? 배포해도 되는가?"

7개 Gate는 **품질 관리자·의사결정자**가 에이전트를 평가하는 방식이다. 각 Gate는 하나의 품질 차원을 대표하며, 통과/경고/실패 세 가지 판정으로 배포 가능 여부를 명확히 제시한다.

```
Gate A — 목표달성   Gate B — 행동무결성   Gate C — 신뢰성
Gate D — 성능계약   Gate E — 보안경계     Gate F — 다중에이전트
Gate G — 운영관측성
→ "어떤 차원에서 문제가 있는가?" 를 한눈에 파악
```

### 관점 2 — Tracker + Config (구현 단위별 분류)
"어떻게 측정할 것인가? 어떤 기준을 코드로 선언할 것인가?"

25개 Tracker와 33개 Harness Config는 **개발자**가 평가를 구현하는 방식이다. Tracker는 자동으로 데이터를 수집하고, Config는 데코레이터에 선언하는 기준서다.

```python
# 개발자 관점: Tracker(자동 측정) + Config(기준 선언)
@agent_eval(monitor,
    sla=SLAConfig(p95_ms=2000),        # Group D Config
    scope=ScopeConfig(allowed_tools=["search"]),  # Group B Config
)
def my_agent(question, ground_truth=""): ...
# → Tracker가 자동으로 latency, tool_calls 등을 기록
```

### 두 관점의 연결고리

두 관점은 **같은 데이터를 서로 다른 언어로 설명**한다.

| 개발자가 선언하는 것 | QA 관리자가 보는 것 |
|-------------------|--------------------|
| `SLAConfig`, `EfficiencyConfig`, `ResourceBudgetConfig` | Gate D — 성능계약 점수 |
| `ToolCallAnalyzer` Tracker + `ScopeConfig`, `LoopDetectionConfig` | Gate B — 행동무결성 점수 |
| `InputSanitizationTracker` + `ThreatSeverityConfig` | Gate E — 보안경계 점수 |

**개발자**는 Tracker와 Config를 통해 "어떤 데이터를 어떤 기준으로 측정할지" 선언한다.  
**QA 관리자**는 Gate A–G를 통해 "어떤 차원에서 배포 가능한지" 판단한다.  
같은 시스템, 두 가지 언어 — 이 책의 Part II는 그 둘을 동시에 설명한다.

> **읽기 전략**: Gate A–G 관점이 먼저 필요하다면 Part II의 각 챕터를 §X.1(개요)과 §X.4(Config 설정) 중심으로 읽는다. Tracker 구현이 필요하다면 §X.2(Tracker 상세)와 §X.3(코드 예제)를 깊이 읽는다.

---

## 독자별 읽기 경로

| 독자 유형 | 권장 읽기 경로 |
|---|---|
| AI 에이전트 개발자 | Part I → Part II (Ch3~10) → Ch11 → Ch12 → Ch13 → Part V → Appendix L |
| QA 관리자 / Harness 담당 엔지니어 | Part I → Part II (Ch3~5 필수) → Part IV → Ch18 → Appendix J |
| DevOps / MLOps 엔지니어 | Part I (Ch2만) → Ch18 → Ch19 → Ch21 → Appendix J §J.4 |
| 보안 엔지니어 / 레드팀 | Ch8 → Appendix K → Ch18 §Gate E 설정 |
| 평가 이론 연구자 | Appendix G → Appendix H → Appendix I → Part II 전체 |
| 이미 운영 중인 팀 (빠른 시작) | Ch2 → Ch11 → Ch12 → Ch14 → Ch18 |
| 프로덕션 품질 위기 대응 | Appendix J → Ch21 §21.3 (Runbook) → Ch18 |
| 예산 제약 스타트업 | Appendix L → Ch12 (필수 Config만) → Ch18 |
| Harness Config 레퍼런스만 필요 | Appendix A §Part 2 |
| 전체 | Part I → II → Ch11 → Ch12 → Ch13 → IV → V → 부록 G~L |

> **QA 관리자 참고**: Ch10(Group G/LLM Judge)는 Chapter 14에서 LLM Judge 비용 설정을 다룰 때 필요합니다. Part II를 Ch3~9만 읽을 경우 Chapter 14의 §14.7 이전에 Ch10을 보완하세요.

> **Appendix I 활용**: 지표 선택을 아직 결정하지 않았다면 Part I 직후 Appendix I를 먼저 읽는 것이 효율적입니다. 어떤 지표를 쓸지 알고 나서 Part II를 읽으면 이해 속도가 크게 높아집니다.

> **Appendix J·K·L 활용**: J(실패 패턴 카탈로그)는 장애 사후 분석 시, K(레드팀 평가)는 보안 강화·출시 전 검증 시, L(예산 최적화)는 평가 비용이 제약될 때 바로 꺼내는 실무 레퍼런스입니다.

---

## Harness Engineering 58개 지표 구조

```
Group A — 목표달성     (Tracker 6종 + Config 6종)  ← 에이전트가 지시를 완수했는가?
Group B — 행동무결성   (Tracker 5종 + Config 6종)  ← 의도치 않은 행동이 없었는가?
Group C — 신뢰성       (Tracker 6종 + Config 5종)  ← 일관되고 재현 가능한가?
Group D — 성능계약     (Tracker 5종 + Config 5종)  ← SLA/비용 계약을 지켰는가?
Group E — 보안경계     (Tracker 4종 + Config 3종)  ← 공격·유출을 차단했는가?
Group F — 다중에이전트 (Tracker 5종 + Config 4종)  ← 교착 없이 협력했는가?
Group G — 운영관측성   (Tracker 4종 + Config 4종)  ← 실패 원인을 즉시 추적할 수 있는가?
────────────────────────────────────────────────────────
합계: Native Tracker 25종 + Harness Config 33종 = 58개 지표
```

배포 판정은 `HarnessEvaluationGate`가 7개 Group을 한 번에 평가한다.

---

## 실습 환경

```bash
pip install agent-evaluator           # 기본 설치 — LLMJudge · 대시보드 · OTEL · PDF 포함 (권장)
pip install "agent-evaluator[full]"   # 전체 (⚠️ crewai/autogen 포함, 10분+)
```

- Python 3.8+
- (선택) OpenAI 또는 Anthropic API 키 — LLM Judge 사용 시

---

## 집필 현황

Agent-Evaluator v0.8.2 기준. 전체 완료.

| 파일 | 상태 |
|------|------|
| Part I — 2개 챕터 | ✅ Harness 7차원 개정 + AI Native 5대 도전 매핑 완료 |
| Part II — 8개 챕터 (Ch03~10) | ✅ Group A-G 챕터 + 개발자↔QA 협업 브리지 완료 |
| Part III — 3개 챕터 | ✅ Harness Config 통합 + 데코레이터→Gate 영향표 완료 |
| Part IV — 4개 챕터 | ✅ Harness Config 임계값 + Gate 데이터 원천 설명 완료 |
| Part V — 4개 챕터 | ✅ HarnessEvaluationGate CI/CD + 자기개선 루프 완료 |
| Appendix A — 58개 지표 레퍼런스 | ✅ 챕터 역참조(↗ Chapter X §X.X) 추가 완료 |
| Appendix F — 용어 사전 | ✅ AI Native·Gate·Tracker·Harness Engineering 정의 확장 완료 |
| Appendix G — AI 평가 이론적 기초 | ✅ Calibration(ECE)·Fairness·출력 구조 검증 추가 완료 |
| Appendix H–I | ✅ 수식 레퍼런스·비교 가이드 완료 |
| Appendix J — 프로덕션 실패 패턴 카탈로그 | ✅ 20개 패턴·탐지 코드·대응 전략 신규 작성 완료 |
| Appendix K — 적대적 강건성과 레드팀 평가 | ✅ OWASP LLM Top 10·31개 공격 패턴·5단계 방법론 신규 작성 완료 |
| Appendix L — 예산 최적화 평가 설계 | ✅ 비용 프로파일·Pareto 조합·지식 증류·ROI 신규 작성 완료 |
