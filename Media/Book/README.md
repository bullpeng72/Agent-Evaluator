# AI 에이전트 Harness Engineering 실무 가이드
## Agent-Evaluator로 구현하는 프로덕션 AI 품질 시스템

**저자**: Sungwoo Kim  
**버전**: 2.0 (Agent-Evaluator v0.9.7 기준)  
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

### Part II — Harness 지표 체계: 58개 지표를 Gate A-G로 이해하다

> **Harness 3요소**: Tracker(측정) × Config(기준 선언) × Gate(배포 판정)  
> 각 챕터는 하나의 품질 차원(Gate)을 담당하며, Tracker와 Config를 함께 다룬다.

- [Chapter 3. Harness Engineering 기초](Part_II_지표시스템/Chapter_03_Harness_Engineering_기초.md)
- [Chapter 4. Gate A — 목표달성 지표](Part_II_지표시스템/Chapter_04_GroupA_목표달성.md)
- [Chapter 5. Gate B — 행동무결성 지표](Part_II_지표시스템/Chapter_05_GroupB_행동무결성.md)
- [Chapter 6. Gate C — 신뢰성 지표](Part_II_지표시스템/Chapter_06_GroupC_신뢰성.md)
- [Chapter 7. Gate D — 성능계약 지표](Part_II_지표시스템/Chapter_07_GroupD_성능계약.md)
- [Chapter 8. Gate E — 보안경계 지표](Part_II_지표시스템/Chapter_08_GroupE_보안경계.md)
- [Chapter 9. Gate F — 다중에이전트 협업 지표](Part_II_지표시스템/Chapter_09_GroupF_다중에이전트.md)
- [Chapter 10. Gate G — 운영관측성 지표](Part_II_지표시스템/Chapter_10_GroupG_운영관측성.md)

### Part III — 개발자 가이드: 코드로 Harness를 심다

- [Chapter 11. 평가 데이터 설계](Part_III_개발자가이드/Chapter_11_평가데이터_설계.md) ← **Part II 직후 읽기 권장**
- [Chapter 12. 데코레이터 완전 정복](Part_III_개발자가이드/Chapter_12_데코레이터_완전정복.md)
- [Chapter 13. 24개 프레임워크 통합](Part_III_개발자가이드/Chapter_13_프레임워크_통합.md)

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

### Part VI — 실전 이식 가이드: 기존 프로젝트에 평가를 붙이는 방법
> Lecture_forge(12-에이전트 멀티 에이전트 시스템)를 케이스 스터디로, 기존 프로젝트를 깨지 않고 단계적으로 측정 가능한 시스템으로 만드는 5단계 방법론을 다룹니다.

- [파트 서문](Part_VI_실전이식가이드/00_파트_서문.md)
- [Chapter 22. 기존 프로젝트 해부](Part_VI_실전이식가이드/Chapter_22_기존_프로젝트_해부.md)
- [Chapter 23. Gate 매핑 전략](Part_VI_실전이식가이드/Chapter_23_Gate_매핑_전략.md)
- [Chapter 24. 첫 번째 이식](Part_VI_실전이식가이드/Chapter_24_첫번째_이식.md)
- [Chapter 25. 전체 통합](Part_VI_실전이식가이드/Chapter_25_전체_통합.md)
- [Chapter 26. CI/CD 완성](Part_VI_실전이식가이드/Chapter_26_CICD_완성.md)

### Part VII — 실시간 가드레일: 로컬 코딩 에이전트에 개입하다
> 배치 채점(Gate B/E)과 같은 평가 로직을, 세션 종료 후가 아니라 도구 호출 직전에 동기 호출해 위반을 차단하는 `LiveGuardrail`과 그 참고 구현인 OpenCode 플러그인을 다룹니다.

- [Chapter 27. LiveGuardrail과 OpenCode — 실시간 가드레일 연동](Part_VII_실시간가드레일/Chapter_27_LiveGuardrail_OpenCode_연동.md)
- [Chapter 28. 로컬 자가교정 ADE 구축 — OpenCode + ctx + Ollama + Agent-Evaluator](Part_VII_실시간가드레일/Chapter_28_로컬_ADE_구축.md)

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
- [Appendix M. 프로덕션 운영 체크리스트](Appendix/M_프로덕션_운영_체크리스트.md) — 배포 전 100개 점검 항목 (Gate A–G × 인프라 × 운영 준비), CI/CD GitHub Actions 통합, 배포 당일 런북
