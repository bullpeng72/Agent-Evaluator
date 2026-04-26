# /publish — 출판 파이프라인 (부크크 · KDP 영문)

EPUB/PDF를 빌드하고 메타데이터를 생성한다.

- **부크크** (한국어) → 리디북스·교보·예스24 자동 유통
- **Amazon KDP** (영문) → 영어 번역 + EPUB

## 사용법

```
/publish                          # 부크크 + KDP 영문 전체
/publish --platform bookk         # 부크크만
/publish --platform kdp-en        # 영문 KDP만
/publish --meta-only              # 메타데이터만 생성
/publish --epub-only              # EPUB/PDF만 빌드
/publish --cover cover.jpg        # 표지 이미지 포함
/publish --check                  # 의존성 확인
```

## 실행 절차

인자: $ARGUMENTS

### 1단계: 의존성 점검

항상 실행한다:
```bash
cd Content/Publishing/pipeline && python run_all.py --check 2>&1
```

`--check` 단독 인자인 경우 여기서 종료한다.

의존성 문제가 있으면 해결 방법을 안내한다:
- `pandoc` 미설치: `brew install pandoc` 또는 `apt install pandoc`
- `ANTHROPIC_API_KEY` 미설정: `.env` 파일에 키 추가

### 2단계: 파이프라인 실행

```bash
cd Content/Publishing/pipeline && python run_all.py $ARGUMENTS 2>&1
```

인자가 없으면(`/publish` 단독) 전체 파이프라인을 실행한다.

### 3단계: 결과 요약

생성된 파일 목록과 크기를 출력한다:
```bash
ls -lh Content/Publishing/output/bookk/ 2>/dev/null
ls -lh Content/Publishing/output_en/kdp/ 2>/dev/null
```

메타데이터 파일 앞부분을 출력한다:
```bash
cat Content/Publishing/output/bookk/bookk_metadata.md 2>/dev/null | head -60
cat Content/Publishing/output_en/kdp/kdp_metadata_en.md 2>/dev/null | head -60
```

등록 절차 안내를 출력한다:

**부크크** (bookk.co.kr):
1. 책 만들기 → 전자책
2. `bookk_metadata.md`의 정보 복붙
3. EPUB/PDF 업로드
4. 심사 후 리디북스·교보·예스24 자동 유통 (2–4주)

**Amazon KDP 영문** (kdp.amazon.com):
1. Bookshelf → + Kindle eBook
2. `kdp_metadata_en.md`의 정보 복붙
3. `description_en.html` → 책 설명란 붙여넣기
4. `keywords_en.txt` → 키워드 7개 입력
5. EPUB 업로드 → 가격 $9.99
