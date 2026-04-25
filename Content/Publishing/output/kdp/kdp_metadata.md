# Amazon KDP 메타데이터 — AI 에이전트 Harness Engineering 실무 가이드

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| 제목 | AI 에이전트 Harness Engineering 실무 가이드 |
| 부제목 | Agent-Evaluator로 구현하는 프로덕션 AI 품질 시스템 |
| 저자 | Sungwoo Kim |
| 언어 | Korean (Korean) |
| 출판사 | Self-Published |
| BISAC 1 | COM051000 |
| BISAC 2 | COM004000 |
| eBook 가격 | $9.99 USD |
| Print 가격 | $29.99 USD |

---

## 책 설명 (HTML — KDP 복사·붙여넣기용)

```html
```html
<h2>assert result == expected — 이 한 줄이 AI 에이전트에게 통하지 않는 이유</h2>

<p>기존 소프트웨어는 결정론적입니다. 같은 입력에는 항상 같은 출력이 나오고, <b>assert</b> 한 줄이면 테스트가 완성됐습니다. 그런데 AI 에이전트는 다릅니다. 같은 질문에도 매번 다른 경로로 답에 도달하고, 환각(hallucination)으로 틀린 정보를 자신감 있게 전달하며, 때로는 허가되지 않은 도구를 실행하거나 민감한 데이터를 응답에 포함시키기도 합니다.</p>

<p><b>"잘 동작하는가"와 "배포해도 되는가"는 다른 질문입니다.</b> 이 책은 두 번째 질문에 코드로 답하는 방법, 즉 <b>Harness Engineering</b>을 실무 중심으로 다룹니다.</p>

<h2>이 책이 해결하는 문제</h2>

<p>AI 에이전트를 프로덕션에 배포하기 전, 팀은 반드시 이 질문들을 마주하게 됩니다.</p>

<ul>
<li>이 에이전트가 사용자 지시를 충실히 따르고 있는가?</li>
<li>무한 루프나 범위 이탈 없이 안정적으로 동작하는가?</li>
<li>P95 응답시간이 SLA 계약을 만족하는가?</li>
<li>프롬프트 인젝션·민감 데이터 유출 위험은 없는가?</li>
<li>다중 에이전트 환경에서 역할 충돌이 발생하지 않는가?</li>
</ul>

<p>이 질문들은 문서나 사람의 감각이 아닌 <b>실행 가능한 코드</b>로 답해야 합니다. 그래야 LLM 모델이 교체되어도, 프롬프트가 수정되어도 배포 기준이 흔들리지 않습니다. 이 책은 그 체계를 처음부터 끝까지 구축하는 방법을 보여줍니다.</p>

<h2>Harness Engineering — 7개 Gate로 배포 준비도를 판정한다</h2>

<p>이 책의 핵심 도구인 오픈소스 <b>Agent-Evaluator SDK</b>는 7개 Harness Gate(A–G)와 58개 지표로 AI 에이전트의 프로덕션 배포 준비도를 종합 판정합니다. AI 에이전트 평가의 모든 차원을 하나의 일관된 프레임워크 안에 담았습니다.</p>

<ul>
<li><b>Gate A — 목표 달성:</b> 지시 이행률, 목표 정렬 점수, 컨텍스트 유지율</li>
<li><b>Gate B — 행동 무결성:</b> 루프 탐지, 범위 이탈 감지, 도구 파라미터 안전성</li>
<li><b>Gate C — 신뢰성:</b> 재현 가능성, 오류 복구율, 멱등성 검증</li>
<li><b>Gate D — 성능 계약:</b> SLA 위반율, 토큰 효율, 비용 예측 가능성</li>
<li><b>Gate E — 보안 경계:</b> 위협 심각도 분류, 규정 준수, 프롬프트 인젝션 탐지</li>
<li><b>Gate F — 다중 에이전트 조율:</b> 에이전트 간 합의율, 역할 준수, 충돌 해결</li>
<li><b>Gate G — 운영 관측성:</b> 추론 설명 가능성, 오류 진단 정확도, 지연 원인 분석</li>
</ul>

<p>배포 기준은 단 몇 줄의 코드로 선언하고, 기준 미달 시 CI/CD 파이프라인이 자동으로 배포를 차단합니다.</p>

<p><b>eval.gate(tcr=85, accuracy=70)</b> — 이것이 Harness Engineering의 핵심 패턴, Config-as-Code입니다.</p>

<h2>이 책에서 배우는 것</h2>

<p>26개 챕터와 실전 예제를 통해 다음을 단계적으로 익힙니다.</p>

<ul>
<li>LLM 품질 측정의 4가지 핵심 알고리즘(Token F1, Jaccard, LCS, Levenshtein)과 환각 탐지 구현</li>
<li>QuickEval 원스톱 Facade로 5분 만에 첫 번째 AI 에이전트 평가 완성</li>
<li><b>@agent_eval</b> 데코레이터와 33개 Harness Config를 활용한 Config-as-Code 선언 패턴</li>
<li>LangChain, LangGraph, CrewAI, AutoGen 등 21개 LLM 프레임워크 자동 어댑터</li>
<li>LLM-as-Judge(G-Eval, RAG Faithfulness)로 ground truth 없이 자동 채점하는 방법</li>
<li>Arize Phoenix + OpenTelemetry 기반 실시간 AI 에이전트 평가 운영 관측성 구축</li>
<li>GitHub Actions 연동 CI/CD 품질 게이팅 — 기준 미달 시 배포 자동 차단</li>
<li>기존 프로젝트에 평가를 무침습으로 이식하는 실전 가이드 (Part VI, 5챕터)</li>
</ul>

<h2>이런 분께 추천합니다</h2>

<ul>
<li>AI 에이전트를 프로덕션에 배포하려는 Python 개발자 및 AI 엔지니어</li>
<li>팀에 LLM 품질 관리 체계와 AI 에이전트 평가 자동화를 도입하려는 리드 개발자</li>
<li>"잘 동작한다"와 "배포해도 된다"를 명확히 구분하고 싶은 백엔드 개발자</li>
<li>AI Native 환경에서 평가 기술 부채를 줄이고 싶은 ML 엔지니어</li>
</ul>

<h2>지금 바로 시작하세요</h2>

<p><b>Agent = Model + Harness.</b> 모델은 에이전트의 능력을 담당하고, Harness는 그 능력이 프로덕션 기준을 실제로 충족했는지를 판정합니다. AI 에이전트 시대의 품질 기준은 문서가 아닌 코드로 작성됩니다.</p>

<p><b>AI 에이전트 Harness Engineering 실무 가이드</b>와 함께 프로덕션 AI 품질 시스템을 지금 구축하세요. "Look Inside" 기능으로 첫 번째 챕터를 바로 미리 읽어보실 수 있습니다.</p>
```
```

---

## 검색 키워드 (7개)

KDP → Book Details → Keywords 7개 칸에 각각 입력:

1. AI 에이전트 평가 프레임워크 실무 가이드
2. LLM 에이전트 프로덕션 배포 품질 관리
3. AI 에이전트 테스트 자동화 파이썬
4. 생성형 AI 시스템 품질 게이트 설계
5. AI 에이전트 성능 모니터링 운영
6. LLM 평가 지표 할루시네이션 탐지
7. 멀티 에이전트 시스템 안전성 검증

---

## 저자 소개

Sungwoo Kim is the Head of AI Innovation Center (Executive Director) at KT DS, where he leads the company's enterprise-wide AI transformation strategy and AI-driven work environment initiatives. Over more than nine years at KT DS, he has served as Head of Technology Innovation and Head of Digico Development Center, spearheading 5G/AI new business development, MSA migration consulting, and Agile culture adoption across the organization. Prior to KT DS, he spent four years at Samsung SDS as a Principal Engineer, leading the PMO for Samsung Electronics' Big Data platform enhancement and delivering global retail solution consulting in Germany (Kaufland), the United Kingdom (Countrywide), and China (Mercedes-Benz). He holds a Master's degree in Artificial Intelligence from Sogang University (GPA 4.14/4.3, 2023), where his thesis focused on stock price prediction using Many-to-Many sequence modeling, and a Bachelor's degree in Electronic Engineering from Dankook University. A prolific internal educator, he has delivered technical lectures on deep learning, CNN, RNN/LSTM, and CrewAI, and has authored practical AI e-books used company-wide. He is the creator and maintainer of agent-evaluator, an open-source SDK on PyPI for evaluating AI agents in production using a 7-Gate Harness Engineering framework covering 58 metrics.

---


## KDP 등록 준비 체크리스트

### 필수 파일
- [ ] EPUB 파일 (build_epub.py로 생성)
- [ ] 표지 이미지 (2560×1600px, JPG, 300 DPI, 파일크기 50MB 이하)
- [ ] 저자 사진 (선택)

### KDP 등록 순서 (kdp.amazon.com)
1. **계정 생성** → kdp.amazon.com → 세금 정보 입력 (W-8BEN 양식)
2. **새 제목 추가** → Kindle eBook / Paperback 선택
3. **Book Details 입력**
   - Language: Korean
   - Book Title / Subtitle
   - Series (선택): AI 에이전트 Harness Engineering 시리즈
   - Edition: 1
   - Author: Sungwoo Kim
   - Description: (아래 생성된 HTML 붙여넣기)
   - Publishing Rights: ✅ I own the copyright
   - Keywords: (아래 7개 붙여넣기)
   - Categories: 2개 선택
   - Age / Grade Range: 해당 없음
4. **Content 업로드**
   - Manuscript: EPUB 파일 업로드
   - Book Cover: JPG 업로드
   - 미리보기 확인 (Kindle Previewer 권장)
5. **Rights & Pricing**
   - Territory: All territories (전 세계)
   - Royalty: 70% (Kindle, $2.99~$9.99 범위)
   - List Price: $9.99 USD
   - KDP Select 등록 (선택 — 90일 독점, Kindle Unlimited 포함)
6. **Publish** → 검토 72시간 → Amazon 스토어 노출

### 가격 전략
| 형식 | 가격 | 로열티 | 정산 예상 |
|------|------|--------|---------|
| Kindle eBook | $9.99 | 70% | $6.99/권 |
| Paperback (POD) | $29.99 | 60%* | $12.99/권 |

*인쇄 비용 차감 후 실수령 기준 (200페이지 기준 약 $5 인쇄비)

### 한국어 책 판매 최적화
- Amazon.co.jp (일본 → 한국어 독자 접근 가능)
- Amazon.com → Korean Books 카테고리
- Goodreads 등록 (Author Program)
- 블로그/GitHub에 Amazon 링크 추가
