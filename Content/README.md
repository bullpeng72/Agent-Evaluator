# Content — 미디어 콘텐츠 자동화 파이프라인

**저서**: AI 에이전트 Harness Engineering 실무 가이드  
**구성**: YouTube · Blog · Publishing(Amazon KDP) 세 채널의 콘텐츠를 Book 챕터에서 자동 생성한다.

---

## 디렉토리 구조

```
Content/
├── README.md                        ← 이 파일
│
├── YouTube/                         ← 유튜브 영상 재료 자동 생성
│   ├── episode_map.json             # 40편 에피소드 정의 (S1E1~S6E5, F1~F7, R1~R4)
│   ├── requirements.txt
│   ├── output/                      # 생성 산출물 (에피소드 ID별 폴더)
│   └── pipeline/
│       ├── config.py                # API 키·경로·TTS 설정
│       ├── chapter_to_narration.py  # Step 1: 챕터 → 나레이션 스크립트
│       ├── narration_to_slides.py   # Step 2: 나레이션 → Marp 슬라이드
│       ├── narration_to_audio.py    # Step 3: 나레이션 → 음성 파일
│       ├── narration_to_srt.py      # Step 4: 나레이션 → SRT 자막
│       ├── generate_metadata.py     # Step 5: YouTube 메타데이터 생성
│       └── run_all.py               # 전체 파이프라인 실행기
│
├── Blog/                            ← 블로그 포스트 자동 생성
│   ├── post_map.json                # 16개 포스트 정의
│   ├── output/                      # 생성 산출물 (포스트 ID별 폴더)
│   └── pipeline/
│       ├── config.py                # 플랫폼·경로 설정
│       ├── chapter_to_blog.py       # 챕터 → 블로그 포스트 (Velog/Tistory/Medium)
│       ├── generate_seo.py          # SEO 메타데이터 자동 생성
│       └── run_all.py               # 전체 파이프라인 실행기
│
└── Publishing/                      ← Amazon KDP 출판 자동화
    ├── output/                      # 생성 산출물 (kdp/ 폴더)
    ├── guide/
    │   └── publishing_guide.md      # 블로그·KDP 전략 및 운영 가이드
    └── pipeline/
        ├── config.py                # 도서 정보·KDP 설정
        ├── generate_kdp_metadata.py # KDP 설명·키워드·저자소개 생성
        ├── build_epub.py            # pandoc EPUB3 빌드
        └── run_kdp.py               # 전체 KDP 파이프라인 실행기
```

---

## 준비 상태 확인

### 콘텐츠 규모

| 채널 | 항목 수 | 상태 |
|------|---------|------|
| YouTube 메인 에피소드 | 29편 (S1E1–S6E5) | ✅ episode_map.json 정의 완료 |
| YouTube 특별 시리즈 | 11편 (F1–F7, R1–R4) | ✅ episode_map.json 정의 완료 |
| YouTube Shorts | 23편 (기획) | 📋 별도 제작 (자동화 미적용) |
| 블로그 포스트 | 16개 | ✅ post_map.json 정의 완료 |
| Amazon KDP | Kindle + 페이퍼백 | ✅ 파이프라인 준비 완료 |

### 자동화 범위

| 작업 | 자동화 | 수동 |
|------|--------|------|
| 나레이션 스크립트 초안 | ✅ Claude API | 저자 검토·교정 |
| Marp 슬라이드 생성 | ✅ 파싱 자동화 | 디자인 조정 (선택) |
| 음성 파일 생성 | ✅ ElevenLabs / CLOVA | — |
| SRT 자막 생성 | ✅ 문자 수 추정 / Whisper | — |
| YouTube 메타데이터 | ✅ Claude API | 업로드 |
| 블로그 포스트 | ✅ Claude API | 플랫폼 게시 |
| SEO 메타데이터 | ✅ Claude API | — |
| KDP 설명·키워드 | ✅ Claude API | KDP 등록 |
| EPUB 빌드 | ✅ pandoc | — |
| 영상 편집 | ❌ | DaVinci Resolve |
| 화면 녹화 | ❌ | OBS Studio |

---

## 공통 설정

### 1. 환경변수 설정

프로젝트 루트(`Agent-Evaluator/`)에 `.env` 파일을 생성한다:

```bash
# Claude API (필수 — 나레이션·블로그·메타데이터 생성에 사용)
ANTHROPIC_API_KEY=sk-ant-...

# TTS 음성 생성 (YouTube 파이프라인만 해당, 둘 중 하나 선택)
TTS_PROVIDER=elevenlabs          # elevenlabs | clova | none

# ElevenLabs (TTS_PROVIDER=elevenlabs 시 필요)
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM   # 기본값: Rachel
ELEVENLABS_MODEL_ID=eleven_multilingual_v2

# Naver CLOVA Voice (TTS_PROVIDER=clova 시 필요)
CLOVA_CLIENT_ID=...
CLOVA_CLIENT_SECRET=...
CLOVA_SPEAKER=nara               # nara(여성) | nminsang(남성)

# 블로그 플랫폼 (Blog 파이프라인)
BLOG_PLATFORM=velog              # velog | tistory | medium | all
```

### 2. 의존성 설치

```bash
# YouTube 파이프라인
pip install -r Content/YouTube/requirements.txt

# Blog / Publishing (공통 의존성)
pip install anthropic python-dotenv

# EPUB 빌드 (Publishing)
brew install pandoc              # macOS
# 또는: apt install pandoc (Linux)

# 슬라이드 PDF 변환 (선택)
npm install -g @marp-team/marp-cli
```

---

## YouTube 파이프라인

### 에피소드 구성 (40편)

| 시즌 | 편수 | 대응 챕터 | 화면 유형 |
|------|------|---------|---------|
| S1 — 왜 측정해야 하는가 | 2편 | Ch 1–2 | 슬라이드, 코드 |
| S2 — 58개 지표를 Gate로 | 8편 | Ch 3–10 | 슬라이드, 슬라이드→코드 |
| S3 — 코드로 심다 (개발자) | 3편 | Ch 11–13 | 코드, 슬라이드→코드 |
| S4 — 품질 기준 세우기 (QA) | 4편 | Ch 14–17 | 슬라이드, 코드 |
| S5 — 프로덕션 배포 | 4편 | Ch 18–21 | 코드, 슬라이드→코드 |
| S6 — 기존 프로젝트 이식 ★ | 5편 | Ch 22–26 | 코드, 슬라이드 |
| F 시리즈 — 실패 사례 | 7편 | Appendix J | 슬라이드 |
| R 시리즈 — 레드팀 | 4편 | Appendix K | 슬라이드→코드 |

### 사용법

```bash
cd Content/YouTube

# 에피소드 목록 및 생성 상태 확인
python pipeline/run_all.py --list

# 단일 에피소드 실행 (음성 제외, 첫 테스트 권장)
python pipeline/run_all.py S6E3 --skip-audio

# 슬라이드 PDF까지 생성 (marp CLI 필요)
python pipeline/run_all.py S2E2 --pdf

# 음성 포함 전체 실행
python pipeline/run_all.py S6E3

# 시즌 전체 일괄 실행
python pipeline/run_all.py --season 2 --skip-audio

# 이미 생성된 파일 덮어쓰기
python pipeline/run_all.py S6E3 --force --skip-audio
```

### 산출물 구조 (에피소드별)

```
output/S6E3/
├── narration.md     ← ① 저자 검토 후 수정 → ②③④⑤ 실행
├── slides.md        ← Marp 슬라이드 소스
├── slides.pdf       ← --pdf 옵션 시 생성
├── narration.mp3    ← AI 음성 파일
├── narration.srt    ← 자막
├── metadata.txt     ← YouTube 복붙용 텍스트
└── metadata.json    ← 구조화 메타데이터
```

### 권장 실행 순서

```
1. python pipeline/run_all.py S6E3 --skip-audio
   → narration.md 확인·수정 (기술 오류, 어색한 표현 교정)

2. python pipeline/run_all.py S6E3 --force
   → 수정된 narration.md로 나머지 산출물 재생성

3. OBS로 코드/슬라이드 화면 녹화
4. DaVinci Resolve에서 화면 + narration.mp3 + narration.srt 합성
5. YouTube 업로드 (metadata.txt에서 제목·설명·태그 복사)
```

---

## Blog 파이프라인

### 포스트 구성 (16개)

| 포스트 ID | 유형 | 대응 챕터 |
|---------|------|---------|
| intro | 개념 | Ch 1 |
| quickstart | 튜토리얼 | Ch 2 |
| harness_basics | 개념 | Ch 3 |
| gate_a ~ gate_g | 심층분석 × 7 | Ch 4–10 |
| decorator | 튜토리얼 | Ch 12 |
| frameworks | 튜토리얼 | Ch 13 |
| cicd | 튜토리얼 | Ch 18 |
| retrofit_30min | 튜토리얼 | Ch 24 |
| failure_loop | 사례연구 | Appendix J |
| failure_hallucination | 사례연구 | Appendix J |

### 사용법

```bash
cd Content/Blog

# 단일 포스트 생성 (Velog 형식)
python pipeline/run_all.py gate_a

# 플랫폼 지정
python pipeline/run_all.py gate_a --platform tistory
python pipeline/run_all.py gate_a --platform all    # 세 플랫폼 동시

# SEO 메타데이터 생성 포함
python pipeline/run_all.py gate_a                   # 기본으로 SEO 포함
python pipeline/run_all.py gate_a --skip-seo        # SEO 제외

# 전체 16개 포스트 일괄 생성
python pipeline/run_all.py --all

# 유형별 필터
python pipeline/run_all.py --type 튜토리얼          # 튜토리얼만
python pipeline/run_all.py --type 사례연구          # 실패 사례만
```

### 산출물 구조 (포스트별)

```
output/gate_a/
├── post_velog.md    ← Velog 게시용 (#태그 포함 Markdown)
├── post_tistory.md  ← Tistory 게시용
├── post_medium.md   ← Medium 게시용
├── seo.json         ← SEO 메타데이터 (구조화)
└── seo.txt          ← SEO 복붙용 텍스트
```

### Velog 게시 방법

```
1. output/gate_a/post_velog.md 열기
2. 상단 #태그 확인 (자동 생성)
3. Velog 에디터에 전체 붙여넣기
4. seo.txt에서 meta_description 복사 → 포스트 설명에 입력
5. 발행
```

---

## Publishing 파이프라인 (KDP · 리디북스 · 부크크)

세 플랫폼을 지원한다. 공통 Book 챕터에서 각 플랫폼에 최적화된 산출물을 자동 생성한다.

| 플랫폼 | 형식 | 로열티 | 유통 범위 |
|--------|------|--------|---------|
| Amazon KDP | EPUB (Kindle) | $6.99/권 (70%) | 전 세계 Amazon |
| 리디북스 | EPUB (리디 뷰어) | ₩6,750/권 (50%) | 리디북스 |
| 부크크 종이책 | PDF (A5 POD) | ~₩6,650/권 (35%) | 교보·예스24·알라딘 |
| 부크크 전자책 | EPUB | ~₩5,200/권 (40%) | 부크크 자체 |

### 의존성 설치

```bash
brew install pandoc                   # EPUB + HTML 변환 (공통)
pip install weasyprint                # PDF 변환 (부크크 종이책만)
```

### 통합 실행기 (권장)

```bash
cd Content/Publishing

# 의존성 전체 확인
python pipeline/run_all.py --check

# 세 플랫폼 전체 실행 (메타데이터 + EPUB + PDF)
python pipeline/run_all.py

# 특정 플랫폼만
python pipeline/run_all.py --platform kdp
python pipeline/run_all.py --platform ridi
python pipeline/run_all.py --platform bookk
python pipeline/run_all.py --platform kdp,ridi     # 여러 개 조합

# 메타데이터만 먼저 생성해서 내용 검토 후 빌드
python pipeline/run_all.py --meta-only
python pipeline/run_all.py --epub-only             # 검토 후 EPUB 빌드

# 표지 이미지 공통 지정
python pipeline/run_all.py --cover cover.jpg

# 부크크 판형 변경 (기본: A5)
python pipeline/run_all.py --platform bookk --size b5
```

### 플랫폼별 개별 실행기

```bash
# Amazon KDP
python pipeline/run_kdp.py --meta-only
python pipeline/run_kdp.py --epub-only --cover cover.jpg
python pipeline/run_kdp.py                         # 메타데이터 + EPUB

# 리디북스
python pipeline/run_ridibooks.py --meta-only
python pipeline/run_ridibooks.py --epub-only
python pipeline/run_ridibooks.py                   # 메타데이터 + EPUB

# 부크크
python pipeline/run_bookk.py --meta-only
python pipeline/run_bookk.py --pdf-only --size a5  # 종이책 PDF만
python pipeline/run_bookk.py --epub-only           # 전자책 EPUB만
python pipeline/run_bookk.py                       # 전체 (메타+PDF+EPUB)
```

### 산출물 구조

```
output/
├── kdp/
│   ├── ..._kdp.epub          ← Amazon KDP 업로드용 (Noto Serif KR CSS)
│   ├── kdp_metadata.md       ← 등록 가이드 + 체크리스트
│   ├── description.html      ← KDP 책 설명 HTML (복붙용)
│   └── keywords.txt          ← 검색 키워드 7개
│
├── ridibooks/
│   ├── ..._ridi.epub         ← 리디북스 업로드용 (KoPub 폰트 CSS)
│   ├── ridi_metadata.md      ← 등록 가이드 + 체크리스트
│   └── description.txt       ← 책 소개 텍스트 (복붙용)
│
└── bookk/
    ├── ..._bookk.pdf         ← 부크크 종이책 업로드용 (A5, weasyprint)
    ├── bookk_metadata.md     ← 등록 가이드 + 체크리스트
    └── description.txt       ← 책 소개 텍스트 (복붙용, 교보·예스24 공용)
```

### EPUB 차이점: KDP vs 리디북스

| 항목 | KDP EPUB | 리디북스 EPUB |
|------|----------|------------|
| CSS 폰트 1순위 | Noto Serif KR | KoPubWorldBatang |
| 줄간격 | 1.8 | 1.9 |
| 문단 들여쓰기 | 없음 | 1em |
| 코드 폰트 크기 | 0.85em | 0.82em |

자세한 등록 절차는 각 산출물 폴더의 `*_metadata.md` 파일 참조.

---

## 권장 시작 순서

### 1단계 — 첫 에피소드 테스트 (오늘)

```bash
# .env 파일에 ANTHROPIC_API_KEY 설정 후
python Content/YouTube/pipeline/run_all.py S6E3 --skip-audio
```

`output/S6E3/narration.md`를 열어 품질 확인. Claude가 생성한 초안이 기술적으로 정확한지, 구어체가 자연스러운지 검토한다.

### 2단계 — 블로그 포스트 선발대 (이번 주)

```bash
python Content/Blog/pipeline/run_all.py retrofit_30min
python Content/Blog/pipeline/run_all.py failure_loop
```

검색 수요가 높은 두 포스트를 먼저 게시해 SEO 베이스를 구축한다.

### 3단계 — KDP 등록 준비 (다음 주)

```bash
python Content/Publishing/pipeline/run_kdp.py --check   # pandoc 확인
python Content/Publishing/pipeline/run_kdp.py           # 메타데이터 + EPUB 생성
```

### 4단계 — YouTube 본격 제작

S6E3 나레이션 검토 완료 후 OBS로 화면 녹화 → DaVinci Resolve 편집 → 업로드.

---

## 채널 연결 전략

```
Amazon KDP 도서
    ↑ "책으로 더 깊이 알고 싶다면"
    │
블로그 (Velog) ←──────────────── YouTube 영상 설명
    │ "관련 영상 보기"              │ "블로그에서 코드 전문 확인"
    ▼                              ▼
   독자가 GitHub → PyPI → pip install agent-evaluator
```

각 채널 말미에 다른 채널로의 CTA를 배치해 상호 유입을 만든다:
- **블로그 CTA**: "유튜브에서 실행 영상 보기 →" + "Amazon에서 전체 가이드 구매 →"
- **YouTube 설명**: "블로그 전문 →" + "GitHub 코드 →"
- **KDP 도서 소개**: GitHub URL 명시

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `ANTHROPIC_API_KEY not set` | `.env` 미설정 | 프로젝트 루트에 `.env` 생성 |
| `Book chapter not found` | 챕터 파일 경로 불일치 | `episode_map.json`의 `chapter_file` 확인 |
| `pandoc not found` | pandoc 미설치 | `brew install pandoc` |
| `marp: command not found` | marp CLI 미설치 | `npm install -g @marp-team/marp-cli` |
| ElevenLabs 422 오류 | 텍스트 너무 길거나 voice ID 오류 | `ELEVENLABS_VOICE_ID` 재확인 |
| CLOVA 401 오류 | 클라이언트 ID/Secret 오류 | Naver Cloud Console에서 재발급 |
| EPUB 한국어 깨짐 | 폰트 미포함 | `build_epub.py`의 CSS 폰트 경로 확인 |
