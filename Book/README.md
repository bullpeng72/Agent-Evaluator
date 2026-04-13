# AI 에이전트 품질 평가 실무 가이드
## Agent-Evaluator로 구현하는 프로덕션 AI 품질 시스템

**저자**: Sungwoo Kim  
**버전**: 1.0 (Agent-Evaluator v0.8.0 기준)  
**언어**: 한국어

---

## 목차

### 머리말
- [서문](00_서문.md)

### Part I — 기초: AI 에이전트 평가를 시작하며
- [Chapter 1. AI 에이전트 품질 평가란 무엇인가](Part_I_기초/Chapter_01_AI에이전트_평가란_무엇인가.md)
- [Chapter 2. Agent-Evaluator 첫 시작](Part_I_기초/Chapter_02_Agent-Evaluator_첫_시작.md)

### Part II — 지표 시스템: 25개 지표를 이해하다
- [Chapter 3. Layer 1 — 모든 에이전트의 기반 지표 6종](Part_II_지표시스템/Chapter_03_Layer1_기반지표_6종.md)
- [Chapter 4. Layer 2 — 에이전틱 행동 지표와 보안 탐지](Part_II_지표시스템/Chapter_04_Layer2_에이전틱지표_보안.md)
- [Chapter 5. Layer 3 — 외부 평가 도구 통합](Part_II_지표시스템/Chapter_05_Layer3_외부평가도구_통합.md)

### Part III — 개발자 가이드: 코드로 평가를 심다
> **권장 읽기 순서**: Chapter 8(평가 데이터 설계) → Chapter 6(데코레이터) → Chapter 7(프레임워크 통합)  
> 지표를 이해한 뒤 평가 데이터를 먼저 설계하고, 그 다음 데코레이터와 프레임워크를 익히는 순서가 가장 효율적입니다.

- [Chapter 6. 데코레이터 완전 정복](Part_III_개발자가이드/Chapter_06_데코레이터_완전정복.md)
- [Chapter 7. 21개 프레임워크 통합](Part_III_개발자가이드/Chapter_07_프레임워크_통합.md)
- [Chapter 8. 평가 데이터 설계](Part_III_개발자가이드/Chapter_08_평가데이터_설계.md) ← **Part II 직후 읽기 권장**

### Part IV — QA 관리자 가이드: 기준을 세우고 지속적으로 모니터링하다
- [Chapter 9. 임계값 설정과 품질 기준 수립](Part_IV_QA관리자가이드/Chapter_09_임계값설정_품질기준.md)
- [Chapter 10. 대시보드와 시각화](Part_IV_QA관리자가이드/Chapter_10_대시보드_시각화.md)
- [Chapter 11. 알림 시스템 운영](Part_IV_QA관리자가이드/Chapter_11_알림시스템_운영.md)
- [Chapter 12. 주간·월간 품질 리뷰](Part_IV_QA관리자가이드/Chapter_12_주간월간_품질리뷰.md)

### Part V — 프로덕션 운영: 배포하고 지속적으로 개선하다
- [Chapter 13. CI/CD 품질 게이팅](Part_V_프로덕션운영/Chapter_13_CICD_품질게이팅.md)
- [Chapter 14. OpenTelemetry와 Phoenix 실시간 모니터링](Part_V_프로덕션운영/Chapter_14_Phoenix_OTEL_모니터링.md)
- [Chapter 15. 프로덕션 배포 전략](Part_V_프로덕션운영/Chapter_15_프로덕션_배포전략.md)
- [Chapter 16. 종합 실무 파이프라인](Part_V_프로덕션운영/Chapter_16_종합_실무파이프라인.md)

### 부록 — 이론 심화 (먼저 읽어도 좋습니다)
> **추천**: Appendix G→H→I는 Part II를 읽기 전에 먼저 보면 "왜 이 지표인가"에 대한 이론적 근거를 갖출 수 있습니다.

- [Appendix G. AI 품질 평가 이론적 기초](Appendix/G_AI평가_이론적기초.md) — BLEU→LLM Judge 역사, 에이전트 평가 특수성, 타당도·신뢰도 이론
- [Appendix H. 지표 알고리즘 수학적 상세 레퍼런스](Appendix/H_알고리즘_수학적_레퍼런스.md) — 25개 지표 수식, 의사코드, 계산 예시, 엣지케이스
- [Appendix I. 지표 비교 분석 및 선택 가이드](Appendix/I_지표_비교분석_선택가이드.md) — BLEU vs Token F1, 환각 탐지 3종 비교, LLM Judge 편향 분석, 비용 프로파일

### 부록 — 실무 레퍼런스
- [Appendix A. 25개 지표 완전 레퍼런스](Appendix/A_25개지표_레퍼런스.md)
- [Appendix B. CLI 명령어 레퍼런스](Appendix/B_CLI_명령어_레퍼런스.md)
- [Appendix C. 환경변수 & 설정 레퍼런스](Appendix/C_환경변수_설정_레퍼런스.md)
- [Appendix D. 프레임워크 호환성 매트릭스](Appendix/D_프레임워크_호환성_매트릭스.md)
- [Appendix E. 에러 코드 & 트러블슈팅](Appendix/E_에러코드_트러블슈팅.md)
- [Appendix F. 용어 사전](Appendix/F_용어사전.md)

---

## 독자별 읽기 경로

| 독자 유형 | 권장 읽기 경로 |
|---|---|
| AI 에이전트 개발자 | Part I → Part II → Ch.8 → Ch.6 → Ch.7 → Part V |
| QA 관리자 | Part I → Part II (Ch.3~5) → Part IV → Part V (Ch.13만) |
| DevOps 엔지니어 | Part I (Ch.2만) → Part V 전체 |
| 평가 이론 연구자 | Appendix G → Appendix H → Appendix I → Part II 전체 |
| 이미 운영 중인 팀 (빠른 시작) | Ch.2 → Ch.8 → Ch.6 → Ch.9 → Ch.13 |
| 프로덕션 품질 위기 대응 | Ch.16 §16.3(Runbook) → Ch.11 → Ch.13 |
| 전체 | Part I → II → Ch.8 → Ch.6 → Ch.7 → IV → V → 부록 |

> **QA 관리자 참고**: Ch.5(Layer 3/LLM Judge)는 Chapter 9에서 LLM Judge 비용 설정을 다룰 때 필요합니다. Part II를 Ch.3~4만 읽을 경우 Chapter 9의 §9.7 이전에 Ch.5를 보완하세요.

> **Appendix I 활용**: 지표 선택을 아직 결정하지 않았다면 Part I 직후 Appendix I를 먼저 읽는 것이 효율적입니다. 어떤 지표를 쓸지 알고 나서 Part II를 읽으면 이해 속도가 크게 높아집니다.

---

## 실습 환경

```bash
pip install agent-evaluator           # 기본 설치 — LLMJudge · 대시보드 · OTEL · PDF 포함 (권장)
pip install "agent-evaluator[full]"   # 전체 (⚠️ crewai/autogen 포함, 10분+)
```

- Python 3.8+
- (선택) OpenAI 또는 Anthropic API 키 — LLM Judge 사용 시
