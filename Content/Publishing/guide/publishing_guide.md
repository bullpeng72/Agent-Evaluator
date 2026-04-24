# 출판·배포 가이드 — 블로그 & Amazon KDP

**기준 저서**: AI 에이전트 Harness Engineering 실무 가이드 (v0.8.5)  
**작성일**: 2026-04-24

---

## 1. 전체 배포 채널 구조

```
책 (Book/)
  │
  ├─── 유튜브 (YouTube/pipeline/)   ← AI 나레이션 + 슬라이드/코드 화면
  ├─── 블로그 (Blog/pipeline/)      ← 개발자 포스트 (Velog, Tistory, Medium)
  └─── Amazon KDP (Publishing/)     ← Kindle eBook + Paperback (POD)
```

채널별 역할:

| 채널 | 목적 | 독자 유입 |
|------|------|---------|
| 블로그 | 검색 엔진 유입, 기술 커뮤니티 | 구글 검색, Velog 피드 |
| 유튜브 | 알고리즘 유입, 개념 설명 | YouTube 검색·추천 |
| Amazon KDP | 수익화, 신뢰도 | Amazon 검색, 블로그/유튜브 CTA |

---

## 2. 블로그 포스팅 전략

### 2-1. 플랫폼 선택

| 플랫폼 | 장점 | 단점 | 권장 용도 |
|--------|------|------|---------|
| **Velog** | 한국 개발자 커뮤니티, Markdown 네이티브, 무료 | 구글 SEO 약함 | 기술 포스트 주력 |
| **Tistory** | 구글 SEO 강함, 카카오 계정 | 에디터 불편 | SEO 타겟 포스트 |
| **Medium** | 영어권 독자, 글로벌 | 유료 멤버십 필요 | 영문 요약본 |
| **GitHub Pages** | 완전한 통제권, 무료 | 직접 SEO 관리 | 기술 레퍼런스 |

**권장**: Velog(주) + Tistory(SEO 보조) 이중 운영

### 2-2. 포스팅 캘린더 (16개 포스트)

| 주차 | 포스트 ID | 제목 요약 | 유형 |
|------|---------|---------|------|
| 1주 | `intro` | AI 에이전트 평가 입문 | 개념 |
| 2주 | `quickstart` | QuickEval 5분 시작 | 튜토리얼 |
| 3주 | `harness_basics` | Harness 3요소 해설 | 개념 |
| 4주 | `gate_a` | Gate A 목표달성 | 심층분석 |
| 5주 | `gate_b` | Gate B 행동무결성 | 심층분석 |
| 6주 | `gate_c` | Gate C 신뢰성 | 심층분석 |
| 7주 | `gate_d` | Gate D 성능계약 | 심층분석 |
| 8주 | `gate_e` | Gate E 보안 | 심층분석 |
| 9주 | `gate_f` | Gate F 멀티 에이전트 | 심층분석 |
| 10주 | `gate_g` | Gate G 관측성 | 심층분석 |
| 11주 | `decorator` | 데코레이터 완전정복 | 튜토리얼 |
| 12주 | `frameworks` | 21개 프레임워크 통합 | 튜토리얼 |
| 13주 | `cicd` | AI CI/CD 게이팅 | 튜토리얼 |
| 14주 | `retrofit_30min` | 30분 이식 가이드 | 튜토리얼 |
| 15주 | `failure_loop` | 무한루프 실패 사례 | 사례연구 |
| 16주 | `failure_hallucination` | RAG 환각 실패 사례 | 사례연구 |

### 2-3. Claude Code 자동화 범위

```bash
# 설치
cd Blog && pip install -r ../YouTube/requirements.txt

# 단일 포스트 생성
python pipeline/run_all.py gate_a

# 전체 포스트 생성 (SEO 포함)
python pipeline/run_all.py --all

# 튜토리얼 유형만 생성
python pipeline/run_all.py --type 튜토리얼

# 목록 확인
python pipeline/run_all.py --list
```

**생성 파일 구조:**
```
Blog/output/gate_a/
  ├── post_velog.md    ← Velog 포스트 (태그 포함)
  ├── post_tistory.md  ← Tistory 포스트
  ├── seo.json         ← SEO 메타데이터 (JSON)
  └── seo.txt          ← SEO 보고서 (사람이 읽는 형식)
```

### 2-4. Velog 포스팅 방법 (수동)

1. velog.io → 새 포스트 작성
2. `Blog/output/{post_id}/post_velog.md` 내용 복사·붙여넣기
3. 태그 확인 (파일 첫 줄 `#태그` 형식)
4. 썸네일 이미지 업로드 (선택)
5. 발행

### 2-5. SEO 최적화 팁

- 포스트 URL: Velog 자동 생성 (슬러그는 `seo.json`의 `slug_suggestion` 참고)
- 메타 설명: `seo.json`의 `meta_description` 사용
- 내부 링크: 이전·다음 포스트 연결 (시리즈 독자 이탈 방지)
- 이미지 alt 텍스트: 핵심 키워드 포함

---

## 3. Amazon KDP 출판 가이드

### 3-1. KDP 개요

| 항목 | 내용 |
|------|------|
| 플랫폼 | kdp.amazon.com |
| 형식 | Kindle eBook (EPUB) + Paperback (PDF, POD) |
| ISBN | 불필요 (KDP 자동 ASIN 부여) |
| 로열티 | eBook 70% / Paperback 60% (인쇄비 차감) |
| 출판 검토 | 등록 후 72시간 내 Amazon 스토어 노출 |
| 수정 | 언제든 파일·가격 업데이트 가능 |

### 3-2. Claude Code 자동화 범위

```bash
# 의존성 확인
cd Publishing && python pipeline/run_kdp.py --check

# 메타데이터 + EPUB 전체 빌드
python pipeline/run_kdp.py

# 메타데이터만 생성
python pipeline/run_kdp.py --meta-only

# EPUB만 빌드 (표지 포함)
python pipeline/run_kdp.py --epub-only --cover cover.jpg
```

**생성 파일:**
```
Publishing/output/kdp/
  ├── kdp_metadata.md      ← 전체 메타데이터 + 체크리스트
  ├── description.html     ← KDP 복붙용 HTML 설명
  ├── keywords.txt         ← 검색 키워드 7개
  └── *.epub               ← EPUB 파일 (pandoc 빌드)
```

### 3-3. KDP 등록 순서 (수동)

**사전 준비:**
- [ ] `python pipeline/run_kdp.py` 실행 → 위 파일 생성
- [ ] 표지 이미지 제작 (2560×1600px, JPG, 300 DPI)
- [ ] `python pipeline/build_epub.py --cover cover.jpg` (표지 포함 재빌드)
- [ ] Kindle Previewer로 EPUB 확인

**KDP 등록:**
1. kdp.amazon.com 로그인 (Amazon 계정)
2. **세금 정보** 입력 (최초 1회, W-8BEN 양식)
3. **Bookshelf → + Kindle eBook**
4. **Book Details 탭**:
   - Language: Korean
   - Title / Subtitle: `kdp_metadata.md` 참조
   - Author: Sungwoo Kim
   - Description: `description.html` 내용 붙여넣기
   - Keywords: `keywords.txt` 7개 각 칸에 입력
   - Categories: 2개 선택
5. **Content 탭**: EPUB 업로드, 표지 JPG 업로드
6. **Rights & Pricing 탭**: 가격 설정, KDP Select 여부
7. **Publish Your Kindle eBook** 클릭

### 3-4. 가격 전략

| 형식 | 권장 가격 | 로열티 | 예상 정산 |
|------|---------|--------|---------|
| Kindle eBook | $9.99 | 70% | $6.99/권 |
| Paperback | $29.99 | 60%* | ~$13/권 |

*200페이지 기준 인쇄비 약 $5 차감

**KDP Select (선택):**
- 90일 독점 (Amazon에서만 판매)
- 혜택: Kindle Unlimited 포함, Free Days 프로모션
- 권장: 초기 90일 Select 가입 → 이후 해제하여 다른 플랫폼 확장

### 3-5. 표지 디자인 가이드

KDP 표지 요구사항:
- 크기: 2560×1600px (가로:세로 = 1.6:1)
- 형식: JPG (300 DPI)
- 파일 크기: 50MB 이하
- 권장 도구: Canva Pro (KDP 템플릿 있음), Adobe Express

표지 필수 요소:
- 제목 (한국어 + 영문 부제목)
- 저자명
- "Python / AI Agent / Harness Engineering" 키워드 시각화
- 배경: 기술 테마 (코드, 회로, 그래프 등)

### 3-6. 한국어 책 Amazon 판매 팁

- **판매 지역**: All territories 설정 (Amazon.com + Amazon.co.jp 동시 노출)
- **Amazon.co.jp**: 일본 거주 한국어 독자 + 한국에서 직구 구매자 접근 가능
- **카테고리**: `Computers & Technology > Artificial Intelligence` 선택
- **Goodreads**: Author Program 등록 → 리뷰 유도
- **블로그/유튜브 CTA**: 모든 콘텐츠 끝에 Amazon 링크 추가

---

## 4. 채널별 상호 연결 전략

```
블로그 포스트
  └── 말미 CTA: "전체 내용은 책에서 → Amazon 링크"
              "실습 코드: GitHub 링크"
              "영상 설명: YouTube 링크"

유튜브 영상
  └── 설명란: "관련 포스트 → 블로그 링크"
             "책 구매 → Amazon 링크"
             "코드 → GitHub 링크"

Amazon KDP
  └── 책 본문: "예제 코드 → GitHub"
              "최신 업데이트 → 블로그/유튜브"
```

### 론칭 순서 (권장)

| 시기 | 활동 |
|------|------|
| D-4주 | 블로그 1~3편 발행 (SEO 색인 시작) |
| D-2주 | GitHub README Amazon 링크 추가 |
| D-1주 | KDP 등록 완료 (검토 72시간 여유) |
| D-Day | Amazon 출판 공지 (블로그 + 유튜브 동시) |
| D+1주 | 유튜브 S1E1 + S6E3 발행 |
| 매주 | 블로그 1편 + 유튜브 1편 교차 발행 |

---

## 5. 수익 예측 (보수적 추정)

| 채널 | 12개월 목표 | 수익원 |
|------|-----------|------|
| Amazon Kindle | 200권 | $1,398 |
| Amazon Paperback | 50권 | $650 |
| YouTube | 구독자 1,000명 | AdSense $200~ |
| 블로그 | 월 5,000 PV | 애드센스 $50~ |
| **합계** | — | **~$2,300/년** |

> 수익보다 **기술 브랜딩과 커뮤니티 신뢰도** 구축이 1차 목표.
> GitHub Star 증가 → PyPI 다운로드 증가 → 컨설팅/강의 기회로 연결.
