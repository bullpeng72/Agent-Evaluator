# Content — 미디어 콘텐츠 자동화 파이프라인

**저서**: AI 에이전트 Harness Engineering 실무 가이드  
**구성**: YouTube · Blog · Publishing(리디북스 · KDP · 부크크) 세 채널의 콘텐츠를 Book 챕터에서 자동 생성한다.  
**실행 방법**: Claude Code Skill 전용 (`/youtube`, `/blog`, `/publish`) — 별도 API 키 불필요.

---

## 매체별 역할 분담

각 채널은 독자가 던지는 질문이 다르다. 겹치는 주제도 **묻는 방식**으로 역할을 나눈다.

| 매체 | 독자의 질문 | 콘텐츠 성격 | 주요 진입 경로 |
|------|-----------|------------|--------------|
| **YouTube 메인** | "어떻게 동작하는가" | 개념 설명 + 라이브 코드 데모 | YouTube 검색·구독 |
| **YouTube Shorts** | "이게 뭔가, 1분만" | 단일 개념 훅 | Shorts 추천 피드 |
| **Blog (Velog)** | "직접 해보려면" | 실행 가능한 코드 + 깊이 있는 배경 | Google SEO |
| **단행본 (리디/KDP)** | "전체 체계를 알고 싶다" | 26개 Chapter + 13개 Appendix 완전판 | 리디·교보·예스24 검색 |
| **GitHub** | "코드만 보자" | ch01~ch26 예제 26개 파일 | GitHub 검색·PyPI 링크 |

> **핵심 원칙**: Blog는 YouTube가 다루는 "동작 원리"를 반복하지 않는다. Blog는 "직접 실행"을 위한 코드와 판단 근거를 제공한다. Book은 두 채널이 제공하지 못하는 "전체 맥락"과 "레퍼런스"다.

---

## 독자 경로별 유입 깔때기

책은 6가지 독자 경로를 정의한다(README 명시). 각 경로별로 첫 접점·심화·전환을 설계한다.

### 개발자 경로 (가장 큰 타겟)

```
구글 "LangChain 평가 붙이기"
  → [Blog] retrofit_30min — 코드 0줄 수정, 30분 이식
  → [YouTube] S6E3 — 동일 내용 라이브 데모
  → pip install agent-evaluator → QuickEval 실습
  → [YouTube] S6E1~E5 구독 (이식 시리즈 완주)
  → [Blog] decorator — @agent_eval 데코레이터 심화
  → [Book] 리디/KDP 구매 (26챕터 + Appendix A·B 레퍼런스)
```

### QA 관리자 경로

```
구글 "AI 에이전트 임계값 설정"
  → [Blog] gate_a / gate_b ... gate_g — Gate별 Config 코드
  → [YouTube] S2E1~E8 — Gate 개념 + 데모 (주 1편)
  → [Blog] cicd — GitHub Actions 게이팅
  → [Book] 리디/KDP 구매 (Part IV QA 가이드 + Appendix J·L)
```

### 보안팀 경로 (고가치, 경쟁 낮음)

```
구글 "OWASP LLM Top 10 평가"
  → [Blog] security_owasp — 31개 패턴 코드 검증 (신규)
  → [YouTube] R1~R4 — 레드팀 시리즈 (독립 SEO)
  → [Blog] gate_e — Gate E 심층 분석
  → [Book] 리디/KDP 구매 (Appendix K 전체)
```

### DevOps / MLOps 경로

```
구글 "AI CI/CD 품질 게이팅"
  → [Blog] cicd — GitHub Actions YAML 코드
  → [YouTube] S5E1 — CI/CD 게이팅 데모
  → [YouTube] S5E2 — Phoenix OTEL 모니터링
  → [Book] 리디/KDP 구매 (Part V 프로덕션 운영)
```

### 스타트업 / 빠른 시작 경로

```
구글 "AI 에이전트 평가 시작"
  → [Blog] quickstart — QuickEval 5분 시작
  → [YouTube] S1E1~E2 — 입문 편
  → [Blog] retrofit_30min or decorator
  → [Book] 리디 구매 (Ch2→Ch11→Ch12→Ch14→Ch18 경로)
```

---

## 대표 콘텐츠 (Flagship)

세 채널 각각의 관문 역할을 하는 콘텐츠. **모든 CTA가 여기로 수렴**한다.

| 채널 | 대표 콘텐츠 | 이유 |
|------|-----------|------|
| **YouTube** | S6E3 "30분 이식 실습" | 검색 수요 최상위, 실용성 즉시 증명, narration 완료 상태 |
| **Blog** | `retrofit_30min` "LangChain 30분 가이드" | Google SEO 최우선 키워드, 생성 완료 |
| **Book** | Part VI 전체 (Ch22~26 이식 가이드) | 타 도서에 없는 차별화 챕터 |

---

## 콘텐츠 생성 계획

### 현재 상태 (2026-04-25)

| 채널 | 전체 | 완료 | 미완료 |
|------|------|------|--------|
| YouTube 메인 (S1–S6) | 26편 | 1편 (S6E3 naration·slides·srt·meta) | 25편 |
| YouTube 특별 (F·R) | 11편 | 0편 | 11편 |
| Blog | 22개 (목표) | 1개 (retrofit_30min) | 21개 |
| 리디북스 | 메타데이터 + EPUB | 메타데이터 완료 | EPUB |
| Amazon KDP | 메타데이터 + EPUB | 메타데이터 완료 | EPUB |
| 부크크 | 메타데이터 + PDF | 메타데이터 완료 | PDF |

---

### Phase 1 — 대표 콘텐츠 + 보안 선발대 (1~2주)

```
# YouTube: S6 시리즈 완성 (대표 채널 구축)
/youtube S6E3 --force --skip-audio     # narration 검토 완료 → 슬라이드/자막/메타데이터 완성
/youtube S6E1 --skip-audio             # 나레이션 생성 → 검토 → --force
/youtube S6E2 --skip-audio
/youtube S6E4 --skip-audio
/youtube S6E5 --skip-audio

# Blog: 개발자·보안팀 선발대
/blog failure_loop                     # Appendix J — 무한루프 사례 (이미 episode map 있음)
/blog failure_hallucination            # Appendix J — RAG 환각 사례
# + post_map에 아래 3개 추가 후 생성:
/blog security_owasp                   # Appendix K — OWASP LLM Top 10 코드 검증 (신규)
/blog project_anatomy                  # Ch22 — 기존 프로젝트 해부 4단계 (신규)
/blog gate_mapping                     # Ch23 — Gate 매핑 전략 (신규)
```

**완료 기준**: `output/S6E*/` 5개 폴더 완성, 블로그 6개 파일 생성

---

### Phase 2 — 입문 편 + QA 시리즈 착수 (2~3주)

```
# YouTube: S1 (채널 관문)
/youtube S1E1 --skip-audio             # "배포해도 된다"는 어떻게 아는가 — 채널 소개
/youtube S1E2 --skip-audio             # QuickEval 5분 실습

# YouTube: R 시리즈 (보안팀 독립 SEO — F 시리즈보다 먼저)
/youtube R1 --skip-audio               # OWASP LLM Top 10 코드 테스트
/youtube R2 --skip-audio               # Prompt Injection 31가지 패턴
/youtube R3 --skip-audio               # 5단계 레드팀 방법론
/youtube R4 --skip-audio               # 에이전트 유형별 보안 Harness

# Blog: 입문 + QA 선발대
/blog intro
/blog quickstart
/blog harness_basics
/blog gate_a
/blog gate_e                           # 보안팀 유입 연결
```

> R 시리즈를 F보다 먼저 올리는 이유: "OWASP LLM", "Prompt Injection 방어", "AI 레드팀" 키워드는 YouTube 검색 경쟁이 낮고 전환율이 높다. F 시리즈(실패 사례)는 이미 블로그 2개가 커버한다.

---

### Phase 3 — Gate 시리즈 완성 (4~6주)

```
# YouTube: S2 Gate A–G (주 1편, 8주)
/youtube --season 2 --skip-audio       # S2E1~E8 일괄 생성 후 주 1편 업로드

# Blog: Gate 시리즈 + 심화
/blog gate_b  /blog gate_c  /blog gate_d
/blog gate_f  /blog gate_g
/blog decorator
/blog frameworks
/blog metrics_101                      # Appendix H/I — BLEU vs Token F1 비교 (신규)
/blog framework_matrix                 # Appendix D — 21개 프레임워크 비교 (신규)
```

---

### Phase 4 — 프로덕션 운영 + 단행본 EPUB (7~10주)

```
# YouTube: S3~S5
/youtube --season 3 --skip-audio
/youtube --season 4 --skip-audio
/youtube --season 5 --skip-audio

# Blog: 운영 편
/blog cicd
/blog budget_optimization              # Appendix L — 평가 예산 최적화 (신규)

# 출판: EPUB + PDF 빌드
/publish --platform ridi --cover cover.jpg    # 리디북스 1순위
/publish --platform kdp  --cover cover.jpg
/publish --platform bookk --cover cover.jpg  # 교보·예스24·알라딘 유통
```

---

### Phase 5 — F 시리즈 + Shorts (11주 이후)

```
# YouTube: F1~F7 (구독자 기반 형성 후)
/youtube F1 --skip-audio  ...  /youtube F7 --skip-audio

# YouTube Shorts (별도 제작, 9편 소재)
```

**Shorts 소재 목록** (각 30초~1분, OBS 직접 녹화):

| # | 제목 | 기반 콘텐츠 |
|---|------|-----------|
| 1 | TCR 100%인데 왜 프로덕션이 실패하나 | Ch1 서론 |
| 2 | Gate A–G 30초 전체 소개 | Ch3 |
| 3 | QuickEval 설치부터 첫 결과까지 30초 | Ch2 |
| 4 | Prompt Injection을 코드 1줄로 막는 법 | Ch8 / Appendix K |
| 5 | P95 레이턴시란 무엇인가 | Ch7 |
| 6 | 에이전트 무한루프 탐지하는 법 | Ch5 / Appendix J |
| 7 | 데코레이터 1줄로 58개 지표 수집 | Ch12 |
| 8 | LLM Judge vs BLEU — 뭐가 다른가 | Appendix I |
| 9 | AI CI/CD 게이팅 30초 데모 | Ch18 |

---

## 블로그 포스트 전체 목록 (22개)

현재 `post_map.json`에는 16개 정의. **6개를 추가**해야 아래 표와 일치한다.

| ID | 유형 | 기반 챕터 | 독자 경로 | 생성 |
|----|------|---------|---------|------|
| `intro` | 개념 | Ch1 | 스타트업·QA | · |
| `quickstart` | 튜토리얼 | Ch2 | 스타트업·개발자 | · |
| `harness_basics` | 개념 | Ch3 | 전체 | · |
| `gate_a` | 심층분석 | Ch4 | QA | · |
| `gate_b` | 심층분석 | Ch5 | QA·DevOps | · |
| `gate_c` | 심층분석 | Ch6 | QA | · |
| `gate_d` | 심층분석 | Ch7 | DevOps | · |
| `gate_e` | 심층분석 | Ch8 | 보안팀 | · |
| `gate_f` | 심층분석 | Ch9 | 개발자 | · |
| `gate_g` | 심층분석 | Ch10 | DevOps | · |
| `decorator` | 튜토리얼 | Ch12 | 개발자 | · |
| `frameworks` | 튜토리얼 | Ch13 | 개발자 | · |
| `cicd` | 튜토리얼 | Ch18 | DevOps | · |
| `retrofit_30min` | 튜토리얼 | Ch24 | 개발자 | ✅ |
| `failure_loop` | 사례연구 | Appendix J | 전체 | · |
| `failure_hallucination` | 사례연구 | Appendix J | QA·개발자 | · |
| `security_owasp` ★신규 | 튜토리얼 | Appendix K | 보안팀 | · |
| `project_anatomy` ★신규 | 튜토리얼 | Ch22 | 개발자 | · |
| `gate_mapping` ★신규 | 튜토리얼 | Ch23 | 개발자·QA | · |
| `metrics_101` ★신규 | 개념 | Appendix H·I | 개발자·연구자 | · |
| `framework_matrix` ★신규 | 비교분석 | Appendix D | 개발자 | · |
| `budget_optimization` ★신규 | 튜토리얼 | Appendix L | QA관리자·DevOps | · |

---

## 단행본 플랫폼 전략

**리디북스를 1순위**로 설정한다. 한국어 IT 기술서 독자의 검색·구매 빈도가 리디 > KDP이며, 부크크를 통한 교보·예스24·알라딘 유통이 오프라인 검색 노출을 담당한다.

| 플랫폼 | 우선순위 | 형식 | 로열티 | 유통 범위 | 전략 포인트 |
|--------|---------|------|--------|---------|-----------|
| **리디북스** | 1순위 | EPUB | ₩6,750/권 (50%) | 리디북스 + 리디 셀렉트 | 한국 IT 독자 주력. 셀렉트 구독 등록으로 노출 극대화 |
| **부크크** | 2순위 | PDF + EPUB | ~₩6,650/권 (종이, 35%) | 교보·예스24·알라딘 자동 유통 | ISBN 발급 → 오프라인 서점 검색 노출 |
| **Amazon KDP** | 3순위 | EPUB | $6.99/권 (70%) | 전 세계 Amazon | 해외 한국어 독자, 일본 Amazon.co.jp |

> **KDP 후순위 이유**: 한국어 도서의 Amazon 검색 노출은 일본 Amazon을 경유하는 구조로, 리디·교보 대비 초기 트래픽이 낮다. 단, 70% 로열티는 $2.99 이상 책정 시 적용되므로 영문 독자 확장 단계에서 재우선화한다.

---

## Claude Code Skill 실행 방법

별도 API 키 없이 Claude Code CLI 인증으로 모든 파이프라인을 실행한다.

```
Content/skills/
├── youtube.md    ← /youtube Skill 정의
├── blog.md       ← /blog Skill 정의
└── publish.md    ← /publish Skill 정의
```

### 다른 PC에서 Skill 설치

```bash
# macOS / Linux
mkdir -p .claude/commands && cp Content/skills/*.md .claude/commands/

# Windows PowerShell
New-Item -ItemType Directory -Force .claude\commands
Copy-Item Content\skills\*.md .claude\commands\
```

Claude Code 재시작 후 `/youtube`, `/blog`, `/publish` 즉시 사용 가능.  
Skill 파일 수정 시 양쪽 동기화: `cp Content/skills/*.md .claude/commands/`

---

### `/youtube` 명령

```
/youtube --list
/youtube S6E3 --skip-audio             # ① 나레이션 생성 → 검토 대기
/youtube S6E3 --force --skip-audio     # ② 검토 완료 → 슬라이드·자막·메타데이터
/youtube S6E3 --force                  # ③ 음성까지 (TTS API 필요)
/youtube --season 2 --skip-audio       # 시즌 전체 일괄
```

### `/blog` 명령

```
/blog --list
/blog retrofit_30min                   # 단일 포스트 (Velog 기본 + SEO)
/blog gate_a --platform all            # Velog + Tistory + Medium 동시
/blog --all                            # 전체 일괄
```

### `/publish` 명령

```
/publish --check                       # 의존성 점검
/publish --meta-only                   # 메타데이터 검토 (첫 실행)
/publish --platform ridi --cover cover.jpg   # 리디 EPUB 빌드 (1순위)
/publish --platform bookk --cover cover.jpg  # 부크크 PDF (2순위)
/publish --platform kdp --cover cover.jpg    # KDP (3순위)
```

---

## 디렉토리 구조

```
Content/
├── README.md                        ← 이 파일 (전략 + 계획)
├── skills/
│   ├── youtube.md
│   ├── blog.md
│   └── publish.md
│
├── YouTube/
│   ├── episode_map.json             # 37편 정의 (S1~S6, F1~F7, R1~R4)
│   ├── output/
│   │   └── S6E3/ ✅                 # narration · slides · srt · metadata 완료
│   └── pipeline/
│       ├── llm.py                   # Claude Code CLI / SDK 자동 선택
│       ├── chapter_to_narration.py
│       ├── narration_to_slides.py
│       ├── narration_to_audio.py
│       ├── narration_to_srt.py
│       ├── generate_metadata.py
│       └── run_all.py
│
├── Blog/
│   ├── post_map.json                # 16개 정의 (22개로 확장 예정)
│   ├── output/
│   │   └── retrofit_30min/ ✅       # post_velog.md · seo.json 완료
│   └── pipeline/
│       ├── llm.py
│       ├── chapter_to_blog.py
│       ├── generate_seo.py
│       └── run_all.py
│
└── Publishing/
    ├── output/
    │   ├── kdp/ ✅                  # kdp_metadata.md · description.html · keywords.txt
    │   ├── ridibooks/ ✅            # ridi_metadata.md · description.txt
    │   └── bookk/ ✅               # bookk_metadata.md · description.txt
    └── pipeline/
        ├── llm.py
        ├── generate_kdp_metadata.py
        ├── generate_ridibooks_metadata.py
        ├── generate_bookk_metadata.py
        ├── build_epub.py
        ├── build_pdf_bookk.py
        └── run_all.py
```

---

## 공통 설정

### 환경변수 (TTS만 필수)

```bash
# Anthropic API 키 — 없으면 Claude Code CLI 인증으로 자동 대체 (선택 사항)
ANTHROPIC_API_KEY=sk-ant-...

# TTS: --skip-audio 없이 음성 파일을 생성할 때만 필요
TTS_PROVIDER=elevenlabs               # elevenlabs | clova | none
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Naver CLOVA (대안)
CLOVA_CLIENT_ID=...
CLOVA_CLIENT_SECRET=...
CLOVA_SPEAKER=nara

# 블로그 기본 플랫폼
BLOG_PLATFORM=velog
```

### 의존성 설치

```bash
pip install -r Content/YouTube/requirements.txt   # YouTube
pip install anthropic python-dotenv               # Blog / Publishing
brew install pandoc                               # EPUB 빌드 (필수)
pip install weasyprint                            # 부크크 종이책 PDF (선택)
npm install -g @marp-team/marp-cli               # 슬라이드 PDF (선택)
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| Claude 응답 없음 / 수 분 이상 대기 | `CLAUDECODE` 환경변수 충돌 | Skill로 실행 (자동 해결됨) |
| 슬라이드 내용 모두 비어 있음 | 나레이션 `## [TAG]` 형식 불일치 | narration.md 헤더가 `## [INTRO]` 형식인지 확인 |
| `Book chapter not found` | 챕터 파일 경로 불일치 | `episode_map.json` / `post_map.json`의 `chapter_file` 확인 |
| `pandoc not found` | pandoc 미설치 | `brew install pandoc` |
| `marp: command not found` | marp CLI 미설치 | `npm install -g @marp-team/marp-cli` |
| ElevenLabs 422 오류 | voice ID 오류 또는 텍스트 초과 | `ELEVENLABS_VOICE_ID` 재확인 |
| CLOVA 401 오류 | 클라이언트 ID/Secret 오류 | Naver Cloud Console 재발급 |
| EPUB 한국어 깨짐 | 폰트 미포함 | `build_epub.py` CSS 폰트 경로 확인 |
| weasyprint 없음 | PDF 빌드 의존성 | `pip install weasyprint` (부크크 종이책만) |
