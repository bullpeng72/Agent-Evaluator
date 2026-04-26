# Content — 콘텐츠 자동화 파이프라인

**Book(42챕터)**을 단일 원천으로 삼아 **4개 채널**에 자동 배포한다.  
모든 파이프라인은 Claude Code CLI Skill로 실행하며 별도 API 키가 없어도 동작한다.

| 채널 | 언어 | Skill | 자동화 |
|------|------|-------|--------|
| **Velog 블로그** | 한국어 | `/blog` | 생성 + 발행 완전 자동 |
| **YouTube** | 한국어 | `/youtube` | 나레이션·슬라이드·자막·메타 자동 (음성은 수동) |
| **부크크** | 한국어 | `/publish` | EPUB/PDF + 메타데이터 자동 |
| **Amazon KDP** | 영어 | `/publish` | 번역 + EPUB + 메타데이터 자동 |

---

## 1. 환경 구성

### 1-1. 필수 도구

```bash
# Python 패키지
pip install anthropic python-dotenv

# EPUB 빌더 (부크크 · KDP)
brew install pandoc          # macOS
sudo apt install pandoc      # Ubuntu/Debian
```

### 1-2. API 키 (`.env`)

프로젝트 루트에 `.env` 파일을 만든다.

```bash
# Claude API — 없으면 Claude Code CLI 인증으로 자동 대체 (선택)
ANTHROPIC_API_KEY=sk-ant-...

# Velog 자동 발행 (/blog --publish 사용 시 필수)
# 방법: 브라우저에서 velog.io 로그인 → F12 → Application → Cookies → access_token 값 복사
VELOG_ACCESS_TOKEN=eyJ...

# TTS 음성 합성 (--skip-audio 없이 음성 파일을 만들 때만 필요)
TTS_PROVIDER=elevenlabs        # elevenlabs | clova
ELEVENLABS_API_KEY=...
```

### 1-3. Skill 설치 (다른 PC에서)

```bash
# macOS / Linux
mkdir -p .claude/commands && cp Content/skills/*.md .claude/commands/

# Windows PowerShell
New-Item -ItemType Directory -Force .claude\commands
Copy-Item Content\skills\*.md .claude\commands\
```

Claude Code를 재시작하면 `/content`, `/blog`, `/youtube`, `/publish` 즉시 사용 가능.

---

## 2. 30일 콘텐츠 계획

`Content/day_plan.json`에 30일치 계획이 정의되어 있다.  
`/content --day_01` 한 명령으로 해당 날의 블로그 + YouTube 콘텐츠를 자동 생성한다.

```
/content --list               # 30일 전체 계획 + 현황 확인
/content --day_01             # Day 1 콘텐츠 생성 (retrofit_30min + S6E3 나레이션)
/content --day_01 --status    # Day 1 생성 현황만 확인
/content --day_01 --force     # 기존 파일 덮어쓰기
```

| 기간 | Day | 주제 |
|------|-----|------|
| 1주차 | 1–4 | 대표 콘텐츠·보안 선발대 (retrofit, OWASP, 레드팀) |
| 2주차 | 5–8 | 실패 사례 + Harness 기초 + Gate A·B |
| 3주차 | 9–12 | Gate C–G 완성 |
| 4주차 | 13–16 | 실전 이식 + 평가 데이터·데코레이터 |
| 5주차 | 17–20 | 프레임워크·임계값·대시보드·알림 |
| 6주차 | 21–25 | 주간리뷰·CI/CD·Phoenix·배포·전체 통합 |
| 7주차 | 26–28 | 실패 시리즈 완성 + 부크크 출판 |
| 8주차 | 29–30 | KDP 영문 EPUB + 크로스 프로모션 |

---

## 3. Velog 블로그

### 기본 사용법

```
/blog --list                          # 22개 포스트 현황
/blog <post_id>                       # 포스트 생성
/blog <post_id> --publish             # 생성 + Velog 즉시 발행
/blog <post_id> --publish --draft     # 생성 + 임시저장
```

### 수동 실행

```bash
cd Content/Blog/pipeline
python run_all.py <post_id>                  # 포스트 생성
python publish_to_velog.py <post_id>         # Velog 발행
python publish_to_velog.py <post_id> --draft # 임시저장
```

### 포스트 22개

| ID | 기반 챕터 | 유형 |
|----|---------|------|
| `intro` | Ch1 | 개념 |
| `quickstart` | Ch2 | 튜토리얼 |
| `harness_basics` | Ch3 | 개념 |
| `gate_a` ~ `gate_g` | Ch4–Ch10 | 심층분석 (7개) |
| `decorator` | Ch12 | 튜토리얼 |
| `frameworks` | Ch13 | 튜토리얼 |
| `metrics_101` | Appendix H·I | 개념 |
| `framework_matrix` | Appendix D | 비교분석 |
| `cicd` | Ch18 | 튜토리얼 |
| `budget_optimization` | Appendix L | 튜토리얼 |
| `retrofit_30min` ✅ | Ch24 | 튜토리얼 |
| `failure_loop` | Appendix J | 사례연구 |
| `failure_hallucination` | Appendix J | 사례연구 |
| `security_owasp` | Appendix K | 튜토리얼 |
| `project_anatomy` | Ch22 | 튜토리얼 |
| `gate_mapping` | Ch23 | 튜토리얼 |

### Velog 토큰 발급 방법 (초보자)

1. 브라우저에서 [velog.io](https://velog.io) 로그인
2. **F12** 키 → **Application** 탭 → **Cookies** → `https://velog.io`
3. `access_token` 행의 **Value** 전체 복사
4. `.env` 파일에 붙여넣기: `VELOG_ACCESS_TOKEN=복사한값`

---

## 4. YouTube

### 기본 사용법

```
/youtube --list                            # 37편 현황
/youtube <episode_id>                      # 1단계: 나레이션 생성 (검토 대기)
/youtube <episode_id> --force --skip-audio # 2단계: 슬라이드·자막·메타데이터 생성
```

### 2단계 워크플로

나레이션을 먼저 검토한 뒤 나머지를 생성한다.

```bash
# 1단계: 나레이션 생성
/youtube S1E1
# → Content/YouTube/output/S1E1/narration.md 생성 → 내용 검토

# 2단계: 검토 완료 후
/youtube S1E1 --force --skip-audio
# → slides.md + narration.srt + metadata.txt 생성
```

### 에피소드 37편 구성

```
Season 1 (2편) — 입문: 채널 소개, QuickEval 실습
Season 2 (8편) — Gate A–G: Harness 7개 Gate 심층 데모
Season 3 (3편) — 개발자 실전: 평가 데이터, 데코레이터, 프레임워크
Season 4 (4편) — QA 관리자: 임계값, 대시보드, 알림, 주간리뷰
Season 5 (4편) — 프로덕션: CI/CD, Phoenix, 배포 전략, 파이프라인
Season 6 (5편) — 이식 실전: 기존 프로젝트 4단계 이식 (S6E3 ✅)
Special F (7편) — 실패 사례: 무한루프, 환각, 비용 폭발 등
Special R (4편) — 레드팀: OWASP LLM Top 10, Prompt Injection 방어
```

### YouTube 업로드 체크리스트 (수동 — 자동화 불가)

`Content/YouTube/output/<episode_id>/metadata.txt` 파일에서 복사:

1. Studio.youtube.com 접속 → **업로드** 클릭
2. 영상 파일 업로드 (OBS·Zoom 녹화본)
3. **제목** → metadata.txt의 `제목` 행 복사
4. **설명** → metadata.txt의 `설명` 전체 복사 (해시태그 포함)
5. **태그** → metadata.txt의 `태그` 10개 복사
6. **썸네일** → `slides.md` 첫 슬라이드를 캡처해 업로드

---

## 5. 부크크 (한국어 전자책)

### 기본 사용법

```
/publish --platform bookk          # EPUB + PDF + 메타데이터 생성
/publish --platform bookk --check  # 의존성 확인 (pandoc 등)
```

### 생성 파일

```
Content/Publishing/output/bookk/
├── AI_에이전트_Harness_Engineering_실무_가이드_bookk.epub
├── AI_에이전트_Harness_Engineering_실무_가이드_bookk.pdf
└── bookk_metadata.md    ← 등록 정보 (제목·가격·분류·설명)
```

### 부크크 등록 절차 (수동 — 20~30분)

1. [bookk.co.kr](https://bookk.co.kr) 접속 → 로그인 → **책 만들기** → **전자책**
2. `bookk_metadata.md` 열기 → **제목, 저자, 분류** 복붙
3. **책 설명** 칸 → `bookk_metadata.md`의 설명 전체 복붙
4. **가격**: 13,000원 (권장)
5. **표지 이미지** 업로드 (1600×2400px JPG — 별도 제작 필요)
6. EPUB 또는 PDF 파일 업로드
7. **심사 신청** → 승인 후 리디북스·교보·예스24 자동 유통 (2~4주)

> 표지 이미지는 Canva나 Adobe Express로 무료 제작 가능. 사이즈: 1600×2400px.

---

## 6. Amazon KDP (영어 전자책)

### 기본 사용법

```
/publish --platform kdp-en                # 전체 (번역 + EPUB + 메타데이터)
/publish --platform kdp-en --meta-only    # 메타데이터만 먼저 확인
```

### 수동 단계별 실행

```bash
cd Content/Publishing/pipeline

# Step 1: 번역 현황 확인 및 실행 (36챕터, 수 시간 소요 — 중단 후 재시작 가능)
python translate_to_en.py --list          # 진행률 확인
python translate_to_en.py --all           # 전체 번역 시작

# Step 2: 영문 메타데이터 생성
python generate_kdp_en_metadata.py

# Step 3: 영문 EPUB 빌드
python build_epub_en.py
```

### 생성 파일

```
Content/Publishing/output_en/kdp/
├── AI_Agent_Harness_Engineering_kdp.epub
├── kdp_metadata_en.md    ← 등록 정보 (영문)
├── description_en.html   ← KDP 책 설명 (HTML 포맷)
└── keywords_en.txt       ← 검색 키워드 7개
```

### KDP 등록 절차 (수동 — 30~40분)

1. [kdp.amazon.com](https://kdp.amazon.com) 접속 → 로그인 → **Bookshelf** → **+ Kindle eBook**
2. **Kindle eBook Details** 탭:
   - Book Title: `kdp_metadata_en.md` 에서 복사
   - Author: Sungwoo Kim
   - Description: `description_en.html` 전체를 **HTML 모드**로 붙여넣기
3. **Kindle eBook Content** 탭:
   - Manuscript: `AI_Agent_Harness_Engineering_kdp.epub` 업로드
   - Book Cover: 표지 이미지 업로드
4. **Kindle eBook Pricing** 탭:
   - Territories: Worldwide
   - Royalty: **70%** 선택
   - List Price: **$9.99**
5. **Publish Your Kindle eBook** 클릭 → 심사 24~72시간

---

## 7. 크로스 프로모션 (Day 30 — 수동)

모든 채널이 완성된 후 서로 연결한다.

### Velog 포스트 하단 추가

각 포스트 끝에 다음 블록을 추가:
```markdown
---
📺 **관련 YouTube**: [에피소드 제목](YouTube 링크)  
📖 **책 구매**: [부크크](부크크 링크) | [Amazon KDP](KDP 링크)  
🔧 **SDK**: `pip install agent-evaluator`
```

### YouTube 설명란 하단 추가

```
📝 관련 블로그: velog.io/@bullpeng72
📖 책 구매: [부크크 링크] | [Amazon KDP 링크]
🔧 SDK: pip install agent-evaluator
🐙 GitHub: github.com/bullpeng72/agent-evaluator
```

### GitHub README 업데이트

`README.md` 상단 배지 아래에 책 링크 추가:
```markdown
📖 [부크크](링크) · [Amazon KDP](링크) · [Velog](https://velog.io/@bullpeng72)
```

---

## 8. 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| `ANTHROPIC_API_KEY` 없음 | `.env` 미설정 | Claude Code CLI로 실행하면 자동 해결 |
| Velog 발행 401 오류 | 토큰 만료 | 브라우저에서 access_token 재발급 |
| `pandoc not found` | pandoc 미설치 | `brew install pandoc` |
| 번역 중단 후 재시작 | — | `python translate_to_en.py --all` 재실행 (체크포인트 자동 이어서) |
| EPUB 한글 깨짐 | 폰트 미포함 | CSS 폰트 스택 확인 (`build_epub.py`) |
| `marp: command not found` | marp 미설치 | `npm install -g @marp-team/marp-cli` |
| 슬라이드 내용 비어 있음 | narration.md 형식 오류 | `## [INTRO]` 형식 헤더인지 확인 |

---

## 9. 파일 구조

```
Content/
├── README.md                    ← 이 파일 (가이드 통합본)
├── day_plan.json                ← 30일 콘텐츠 계획
├── skills/
│   ├── content.md               ← /content Skill 정의
│   ├── blog.md                  ← /blog Skill 정의
│   ├── youtube.md               ← /youtube Skill 정의
│   └── publish.md               ← /publish Skill 정의
├── pipeline/
│   └── run_day.py               ← /content --day_XX 실행 엔진
├── Blog/
│   ├── post_map.json            ← 22개 포스트 정의
│   ├── output/<post_id>/        ← 생성 결과
│   └── pipeline/
│       ├── run_all.py
│       ├── chapter_to_blog.py
│       ├── generate_seo.py
│       └── publish_to_velog.py
├── YouTube/
│   ├── episode_map.json         ← 37편 정의
│   ├── output/<episode_id>/     ← 생성 결과
│   └── pipeline/
│       ├── run_all.py
│       ├── chapter_to_narration.py
│       ├── narration_to_slides.py
│       ├── narration_to_audio.py
│       ├── narration_to_srt.py
│       └── generate_metadata.py
└── Publishing/
    ├── output/bookk/            ← 부크크 출판 파일
    ├── output_en/kdp/           ← KDP 영문 출판 파일
    └── pipeline/
        ├── run_all.py           ← /publish 실행 엔진
        ├── build_epub.py        ← 한국어 EPUB
        ├── build_epub_en.py     ← 영문 EPUB
        ├── build_pdf_bookk.py   ← 부크크 PDF
        ├── translate_to_en.py   ← 한→영 번역
        ├── generate_bookk_metadata.py
        ├── generate_kdp_en_metadata.py
        └── run_kdp_en.py
```
