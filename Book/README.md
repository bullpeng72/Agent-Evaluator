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
> **권장 읽기 순서**: Chapter 13(평가 데이터 설계) → Chapter 11(데코레이터) → Chapter 12(프레임워크 통합)  
> 지표를 이해한 뒤 평가 데이터를 먼저 설계하고, 그 다음 데코레이터와 프레임워크를 익히는 순서가 가장 효율적입니다.

- [Chapter 11. 데코레이터 완전 정복](Part_III_개발자가이드/Chapter_06_데코레이터_완전정복.md)
- [Chapter 12. 21개 프레임워크 통합](Part_III_개발자가이드/Chapter_07_프레임워크_통합.md)
- [Chapter 13. 평가 데이터 설계](Part_III_개발자가이드/Chapter_08_평가데이터_설계.md) ← **Part II 직후 읽기 권장**

### Part IV — QA 관리자 가이드: Harness 기준을 세우고 지속적으로 모니터링하다
- [Chapter 14. 임계값 설정과 품질 기준 수립](Part_IV_QA관리자가이드/Chapter_09_임계값설정_품질기준.md)
- [Chapter 15. 대시보드와 시각화](Part_IV_QA관리자가이드/Chapter_10_대시보드_시각화.md)
- [Chapter 16. 알림 시스템 운영](Part_IV_QA관리자가이드/Chapter_11_알림시스템_운영.md)
- [Chapter 17. 주간·월간 품질 리뷰](Part_IV_QA관리자가이드/Chapter_12_주간월간_품질리뷰.md)

### Part V — 프로덕션 운영: Harness Gate로 배포하고 지속적으로 개선하다
- [Chapter 18. CI/CD Harness Gate 운영](Part_V_프로덕션운영/Chapter_13_CICD_품질게이팅.md)
- [Chapter 19. OpenTelemetry와 Phoenix 실시간 모니터링](Part_V_프로덕션운영/Chapter_14_Phoenix_OTEL_모니터링.md)
- [Chapter 20. 프로덕션 배포 전략](Part_V_프로덕션운영/Chapter_15_프로덕션_배포전략.md)
- [Chapter 21. 지속 평가·자기개선 파이프라인](Part_V_프로덕션운영/Chapter_16_종합_실무파이프라인.md)

### 부록 — 이론 심화 (먼저 읽어도 좋습니다)
> **추천**: Appendix G→H→I는 Part II를 읽기 전에 먼저 보면 "왜 이 지표인가"에 대한 이론적 근거를 갖출 수 있습니다.

- [Appendix G. AI 품질 평가 이론적 기초](Appendix/G_AI평가_이론적기초.md) — BLEU→LLM Judge 역사, Harness Engineering 이론, AI Native 평가 이론
- [Appendix H. 지표 알고리즘 수학적 상세 레퍼런스](Appendix/H_알고리즘_수학적_레퍼런스.md) — 58개 지표 수식, 의사코드, 계산 예시, 엣지케이스
- [Appendix I. 지표 비교 분석 및 선택 가이드](Appendix/I_지표_비교분석_선택가이드.md) — BLEU vs Token F1, 환각 탐지 3종 비교, LLM Judge 편향 분석, 비용 프로파일

### 부록 — 실무 레퍼런스
- [Appendix A. 58개 지표 완전 레퍼런스](Appendix/A_58개지표_레퍼런스.md)
- [Appendix B. CLI 명령어 레퍼런스](Appendix/B_CLI_명령어_레퍼런스.md)
- [Appendix C. 환경변수 & 설정 레퍼런스](Appendix/C_환경변수_설정_레퍼런스.md)
- [Appendix D. 프레임워크 호환성 매트릭스](Appendix/D_프레임워크_호환성_매트릭스.md)
- [Appendix E. 에러 코드 & 트러블슈팅](Appendix/E_에러코드_트러블슈팅.md)
- [Appendix F. 용어 사전](Appendix/F_용어사전.md)

---

## 독자별 읽기 경로

| 독자 유형 | 권장 읽기 경로 |
|---|---|
| AI 에이전트 개발자 | Part I → Part II (Ch3~10) → Ch13 → Ch11 → Ch12 → Part V |
| QA 관리자 / Harness 담당 엔지니어 | Part I → Part II (Ch3~5 필수) → Part IV → Ch18 |
| DevOps / MLOps 엔지니어 | Part I (Ch2만) → Ch18 → Ch19 → Ch21 |
| 평가 이론 연구자 | Appendix G → Appendix H → Appendix I → Part II 전체 |
| 이미 운영 중인 팀 (빠른 시작) | Ch2 → Ch13 → Ch11 → Ch14 → Ch18 |
| 프로덕션 품질 위기 대응 | Ch21 §21.3 (Runbook) → Ch16 → Ch18 |
| Harness Config 레퍼런스만 필요 | Appendix A §Part 2 |
| 전체 | Part I → II → Ch13 → Ch11 → Ch12 → IV → V → 부록 |

> **QA 관리자 참고**: Ch10(Group G/LLM Judge)는 Chapter 14에서 LLM Judge 비용 설정을 다룰 때 필요합니다. Part II를 Ch3~9만 읽을 경우 Chapter 14의 §14.7 이전에 Ch10을 보완하세요.

> **Appendix I 활용**: 지표 선택을 아직 결정하지 않았다면 Part I 직후 Appendix I를 먼저 읽는 것이 효율적입니다. 어떤 지표를 쓸지 알고 나서 Part II를 읽으면 이해 속도가 크게 높아집니다.

---

## Harness Engineering 58개 지표 구조

```
Group A — 목표달성     (Tracker 6종 + Config 6종)  ← 에이전트가 지시를 완수했는가?
Group B — 행동무결성   (Tracker 5종 + Config 4종)  ← 의도치 않은 행동이 없었는가?
Group C — 신뢰성       (Tracker 6종 + Config 5종)  ← 일관되고 재현 가능한가?
Group D — 성능계약     (Tracker 5종 + Config 5종)  ← SLA/비용 계약을 지켰는가?
Group E — 보안경계     (Tracker 4종 + Config 4종)  ← 공격·유출을 차단했는가?
Group F — 다중에이전트 (Tracker 5종 + Config 5종)  ← 교착 없이 협력했는가?
Group G — 운영관측성   (Tracker 4종 + Config 4종)  ← 실패 원인을 즉시 추적할 수 있는가?
────────────────────────────────────────────────────────
합계: Tracker 35종 + Config 33종 = 58개 지표
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
| Part I — 2개 챕터 | ✅ Harness 7차원 개정 완료 |
| Part II — 8개 챕터 (Ch03~10) | ✅ Group A-G 챕터 신규 작성 완료 |
| Part III — 3개 챕터 | ✅ Harness Config 통합 절 추가 완료 |
| Part IV — 4개 챕터 | ✅ Harness Config 임계값 절 추가 완료 |
| Part V — 4개 챕터 | ✅ HarnessEvaluationGate CI/CD + 자기개선 루프 추가 완료 |
| Appendix A–I | ✅ AI Native 연결·Config-as-Code 정합성 개선 완료 |
