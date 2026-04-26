# 콘텐츠 생산 가이드

Claude Code CLI Skill 기반 콘텐츠 자동화 파이프라인.
**Book(42개 챕터·1.7MB)** 을 단일 원천으로 삼아 4개 채널에 자동 배포한다.

---

## 채널 구성

| 채널 | 언어 | Skill | 자동화 수준 |
|------|------|-------|------------|
| **Velog** | 한국어 | `/blog` | ✅ 생성 + 발행 완전 자동 |
| **YouTube** | 한국어 | `/youtube` | ✅ 나레이션·슬라이드·자막 자동 (음성 수동) |
| **부크크** | 한국어 | `/publish` | ✅ EPUB + 메타데이터 자동 |
| **Amazon KDP** | 영어 | `/publish` | ✅ 번역 + EPUB + 메타데이터 자동 |

---

## 1. 환경 구성

### 1-1. 필수 도구 설치

```bash
# Python 패키지
pip install anthropic python-dotenv

# EPUB 빌더
brew install pandoc          # macOS
sudo apt install pandoc      # Ubuntu/Debian
```

### 1-2. API 키 설정 (`.env`)

프로젝트 루트의 `.env` 파일에 아래를 추가한다.

```bash
# Claude API (필수 — 모든 콘텐츠 생성)
ANTHROPIC_API_KEY=sk-ant-...

# Velog 자동 발행 (선택 — /blog --publish 사용 시)
# Chrome → velog.io → F12 → Application → Cookies → access_token 값
VELOG_ACCESS_TOKEN=eyJ...

# TTS 음성 합성 (선택 — YouTube 음성 자동화 시)
TTS_PROVIDER=elevenlabs        # elevenlabs | clova
ELEVENLABS_API_KEY=...         # ElevenLabs 사용 시
```

### 1-3. 인증 확인

```bash
# Claude API 확인
python -c "import anthropic; print('OK')"

# Velog 토큰 확인
python Content/Blog/pipeline/publish_to_velog.py --preview retrofit_30min

# 전체 의존성 확인
python Content/Publishing/pipeline/translate_to_en.py --check
```

---

## 2. 콘텐츠 원천 구조

```
Book/                          ← 단일 원천 (42개 챕터 마크다운)
├── 00_서문.md
├── Part_I_기초/
│   ├── Chapter_01_...md
│   └── Chapter_02_...md
├── Part_II_지표시스템/ (8챕터)
├── Part_III_개발자가이드/ (3챕터)
├── Part_IV_QA관리자가이드/ (4챕터)
├── Part_V_프로덕션운영/ (4챕터)
├── Part_VI_실전이식가이드/ (5챕터)
└── Appendix/ (9개)

Content/
├── Blog/
│   ├── post_map.json          ← 블로그 포스트 기획 (22개 포스트 정의)
│   ├── pipeline/              ← 생성 스크립트
│   └── output/<post_id>/      ← 생성 결과
├── YouTube/
│   ├── episode_map.json       ← 에피소드 기획 (37개 에피소드 정의)
│   ├── pipeline/              ← 생성 스크립트
│   └── output/<episode_id>/   ← 생성 결과
└── Publishing/
    ├── pipeline/              ← EPUB·번역 스크립트
    └── output/                ← 플랫폼별 출판 파일
```

---

## 3. Velog 블로그

### Skill 사용법

```
/blog <post_id>               # 포스트 생성
/blog <post_id> --publish     # 생성 + Velog 즉시 발행
/blog <post_id> --publish --draft  # 생성 + 임시저장
/blog --list                  # 전체 포스트 현황
```

### 수동 실행 (Skill 없이)

```bash
# 포스트 생성
cd Content/Blog/pipeline
python run_all.py <post_id>

# Velog 발행
python publish_to_velog.py <post_id>
python publish_to_velog.py <post_id> --draft   # 임시저장
python publish_to_velog.py <post_id> --preview # 발행 전 확인
```

### 기획된 포스트 22개

```bash
/blog --list   # 전체 목록 및 생성 현황 확인
```

| 유형 | 포스트 수 | 내용 |
|------|----------|------|
| 입문·튜토리얼 | 6개 | intro, quickstart, retrofit_30min 등 |
| Gate A–G 심층 | 7개 | gate_a ~ gate_g |
| 실전 사례 | 5개 | failure_loop, cicd_gate 등 |
| 도구·통합 | 4개 | framework_integration, llm_judge 등 |

### 전체 발행 (배치)

```bash
cd Content/Blog/pipeline

# 전체 생성
python run_all.py --all

# 전체 Velog 발행 (생성된 포스트 순차 발행)
for post_id in $(python run_all.py --list | grep "✅" | awk '{print $2}'); do
    python publish_to_velog.py "$post_id"
    sleep 3
done
```

---

## 4. YouTube

### Skill 사용법

```
/youtube <episode_id>              # 나레이션 생성 (검토 대기)
/youtube <episode_id> --force      # 나레이션 검토 후 전체 파이프라인
/youtube <episode_id> --skip-audio # 음성 생략 (TTS 미설정 시)
/youtube --list                    # 전체 에피소드 현황
/youtube --season 1                # 시즌 1 전체 생성
```

### 워크플로 (2단계)

```
1단계: /youtube S1E1
       → narration.md 생성 → 검토·수정

2단계: /youtube S1E1 --force [--skip-audio]
       → slides.md + narration.srt + metadata.txt 생성
```

### 기획된 에피소드 37개

```
Season 1 (2편): 입문
Season 2 (8편): Harness Gate A–G
Season 3 (3편): 개발자 실전
Season 4 (4편): QA 관리자
Season 5 (4편): 프로덕션 운영
Season 6 (5편): 기존 프로젝트 이식
Special F (7편): 실패 케이스
Special R (4편): 보안·레드팀
```

### 시즌 단위 배치 생성

```bash
# 시즌 1 나레이션 전체 생성
cd Content/YouTube/pipeline
python chapter_to_narration.py S1E1
python chapter_to_narration.py S1E2

# 검토 후 나머지 파이프라인
python run_all.py S1E1 --skip-audio
python run_all.py S1E2 --skip-audio
```

### YouTube 업로드 체크리스트

`output/<episode_id>/metadata.txt` 에서 복사:
- 제목 (한국어 + 영문 키워드)
- 설명 (해시태그 포함)
- 태그 (10개)
- 썸네일 제작 → `slides.md` 첫 슬라이드 캡처

---

## 5. 부크크 (한국어 전자책)

### Skill 사용법

```
/publish bookk           # 부크크 EPUB + 메타데이터 생성
/publish bookk --check   # 의존성 확인
```

### 수동 실행

```bash
cd Content/Publishing/pipeline
python run_bookk.py          # EPUB + 메타데이터 전체 생성
python run_bookk.py --check  # pandoc 등 의존성 확인
```

### 생성 파일

```
Content/Publishing/output/bookk/
├── AI_에이전트_Harness_Engineering_실무_가이드_bookk.epub
└── bookk_metadata.md    ← 부크크 등록 정보 (제목·가격·분류·설명)
```

### 부크크 등록 절차

1. `bookk.co.kr` → 전자책 등록
2. EPUB 파일 업로드
3. `bookk_metadata.md` 의 정보 복붙
4. 표지 이미지 업로드 (1600×2400px, JPG)
5. 가격: 13,000원 (권장)
6. 심사 → 리디북스·교보·예스24 자동 유통 (2–4주)

---

## 6. Amazon KDP (영어 전자책)

### Skill 사용법

```
/publish kdp-en                 # 번역 + EPUB + 메타데이터 전체 파이프라인
/publish kdp-en --skip-translate  # 이미 번역된 경우 EPUB만
```

### 수동 실행 (단계별)

```bash
cd Content/Publishing/pipeline

# Step 1: 한국어 → 영어 번역 (36챕터, 수 시간 소요)
python translate_to_en.py --list       # 번역 현황 확인
python translate_to_en.py --chapter 01 # 챕터 1개 시범 번역
python translate_to_en.py --all        # 전체 번역 (중단 후 재시작 가능)

# Step 2: 영문 KDP 메타데이터 생성
python generate_kdp_en_metadata.py

# Step 3: 영문 EPUB 빌드
python build_epub_en.py

# 전체 한 번에
python run_kdp_en.py
python run_kdp_en.py --skip-translate  # 번역 완료 시
```

### 번역 진행 관리

```bash
# 현황 확인
python translate_to_en.py --list

# 특정 챕터만 재번역
python translate_to_en.py --chapter 01 --force

# 체크포인트: Content/Publishing/output_en/.translation_checkpoint.json
```

### KDP 등록 절차

1. `kdp.amazon.com` → Bookshelf → + Kindle eBook
2. `output_en/kdp/kdp_metadata_en.md` 의 정보 복붙
3. `output_en/kdp/description_en.html` → KDP 설명란 붙여넣기
4. `output_en/kdp/keywords_en.txt` → 키워드 7개 입력
5. 가격: $9.99 (70% 로열티 적용)

---

## 7. 콘텐츠 기획

### 원칙: Book → 모든 채널 파생

```
Book 챕터 1개
    ├── Velog 포스트 1개  (심화·실용 각색)
    ├── YouTube 에피소드 1개  (시각화·나레이션)
    └── 부크크/KDP 챕터 1개  (원문 그대로)
```

### 발행 순서 (권장)

```
1주차: 부크크·KDP 출판 (기반 확보)
       → /publish bookk && /publish kdp-en

2주차~: Velog 포스트 주 2회 발행
        → /blog <post_id> --publish

4주차~: YouTube 에피소드 주 1회 업로드
        → /youtube <episode_id> --force --skip-audio
```

### 콘텐츠 캘린더 (예시)

| 주차 | Velog | YouTube | 비고 |
|------|-------|---------|------|
| 1 | intro + quickstart | — | 책 출판 발표 |
| 2 | gate_a + gate_b | S1E1 | |
| 3 | gate_c + gate_d | S1E2 | |
| 4 | gate_e + gate_f | S2E1 | |
| … | … | … | |

### 크로스 프로모션

- **Velog 포스트 하단**: YouTube 에피소드 링크
- **YouTube 설명**: Velog 포스트 링크 + PyPI 링크
- **부크크/KDP**: GitHub README에 구매 링크
- **agent-evaluator PyPI**: `README.md` 하단에 책 링크

---

## 8. 전체 명령어 요약

```bash
# ── 블로그 (Velog) ──────────────────────────────────────
/blog --list                          # 포스트 현황
/blog <post_id>                       # 포스트 생성
/blog <post_id> --publish             # 생성 + 발행
/blog <post_id> --publish --draft     # 생성 + 임시저장

# ── YouTube ────────────────────────────────────────────
/youtube --list                       # 에피소드 현황
/youtube <episode_id>                 # 나레이션 생성 (검토 필요)
/youtube <episode_id> --force --skip-audio  # 전체 파이프라인

# ── 출판 (부크크 + KDP) ────────────────────────────────
/publish bookk                        # 한국어 EPUB 빌드
/publish kdp-en                       # 영어 번역 + EPUB 빌드
/publish kdp-en --skip-translate      # 번역 완료 시 EPUB만

# ── 번역 관리 ──────────────────────────────────────────
python Content/Publishing/pipeline/translate_to_en.py --list
python Content/Publishing/pipeline/translate_to_en.py --all
```

---

## 9. 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| `ANTHROPIC_API_KEY` 없음 | `.env` 미설정 | `.env`에 키 추가 |
| Velog 발행 401 오류 | 토큰 만료 | 브라우저에서 토큰 재발급 |
| pandoc 없음 | 미설치 | `brew install pandoc` |
| 번역 중단 후 재시작 | — | `translate_to_en.py --all` 재실행 (자동 이어서) |
| EPUB 한글 깨짐 | 폰트 미포함 | pandoc `--embed-resources` 옵션 확인 |
