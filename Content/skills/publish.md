# /publish — 출판 파이프라인 (KDP · 리디북스 · 부크크)

책 메타데이터를 생성하고 EPUB/PDF를 빌드한다.

## 사용법

```
/publish [--platform kdp|ridi|bookk|all] [--meta-only] [--epub-only] [--cover <파일>] [--check]
```

**플랫폼 기본값**: all (세 플랫폼 동시)

## 실행 절차

인자: $ARGUMENTS

### 1단계: 의존성 점검

항상 실행한다:
```bash
cd Content/Publishing/pipeline && python run_all.py --check 2>&1
```

`--check` 단독 인자인 경우 여기서 종료한다.

의존성 문제가 있으면 해결 방법을 안내하고 진행 여부를 확인한다:
- `pandoc` 미설치: `brew install pandoc` 또는 `apt install pandoc`
- `weasyprint` 미설치: `pip install weasyprint`
- `ANTHROPIC_API_KEY` 미설정: `.env` 파일에 키 추가

### 2단계: 파이프라인 실행

`$ARGUMENTS`에 따라 실행한다:

```bash
cd Content/Publishing/pipeline && python run_all.py $ARGUMENTS 2>&1
```

인자가 없으면(`/publish` 단독) `--meta-only`로 먼저 실행해 내용을 검토하도록 안내한다:
```bash
cd Content/Publishing/pipeline && python run_all.py --meta-only 2>&1
```

### 3단계: 결과 요약

생성된 파일 목록과 크기를 플랫폼별로 출력한다:
```bash
ls -lh Content/Publishing/output/kdp/ 2>/dev/null
ls -lh Content/Publishing/output/ridibooks/ 2>/dev/null
ls -lh Content/Publishing/output/bookk/ 2>/dev/null
```

각 플랫폼의 메타데이터 파일을 출력한다:
```bash
cat Content/Publishing/output/kdp/kdp_metadata.md 2>/dev/null | head -80
cat Content/Publishing/output/ridibooks/ridi_metadata.md 2>/dev/null | head -60
cat Content/Publishing/output/bookk/bookk_metadata.md 2>/dev/null | head -60
```

등록 절차 안내를 출력한다:

**Amazon KDP** (kdp.amazon.com):
1. Bookshelf → 새 제목 추가 → Kindle eBook
2. `description.html` 내용을 책 설명란에 붙여넣기
3. `keywords.txt`에서 7개 키워드 입력
4. `book_kdp.epub` 업로드

**리디북스** (ridibooks.com/publish):
1. 도서 등록 → 전자책
2. `description.txt` 내용을 책 소개란에 입력
3. `book_ridi.epub` 업로드

**부크크** (bookk.co.kr):
1. 책 만들기 → 전자책 또는 종이책
2. `description.txt` 내용 입력
3. `book_bookk.pdf` 업로드 (종이책) 또는 `epub` (전자책)
