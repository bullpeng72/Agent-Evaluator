"""KDP 등록에 필요한 모든 메타데이터를 생성한다.

생성 항목:
  - 책 설명 (HTML 형식, Amazon KDP 최적화)
  - 7개 검색 키워드
  - 저자 소개
  - 출판 준비 체크리스트

Usage:
    python generate_kdp_metadata.py
    python generate_kdp_metadata.py --force
"""
import argparse
import re
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY, AUTHOR_BIO_KDP, AUTHOR_NAME,
    BISAC_PRIMARY, BISAC_SECONDARY, BOOK_DIR, BOOK_SUBTITLE,
    BOOK_TITLE, CLAUDE_MODEL, EBOOK_PRICE_USD, LANGUAGE,
    OUTPUT_DIR, PRINT_PRICE_USD, PUBLISHER,
)

# Amazon KDP 책 설명은 HTML 지원 (최대 4000자)
DESCRIPTION_PROMPT = """당신은 Amazon 도서 마케팅 전문가입니다.
다음 기술 서적의 Amazon KDP 책 설명을 작성하세요.

책 정보:
- 제목: {title}
- 부제목: {subtitle}
- 저자: {author}
- 언어: 한국어
- 대상 독자: Python 개발자, AI 엔지니어, 백엔드 개발자
- 핵심 가치: AI 에이전트를 프로덕션에 배포할 준비가 됐는지 코드로 판정

서문 내용 (참고):
{intro_content}

요구사항:
1. HTML 형식 (Amazon KDP 지원 태그: <h2>, <p>, <ul>, <li>, <b>, <br>)
2. 총 1500~2500자 (영문 기준)
3. 구조: 훅 문장 → 이 책이 해결하는 문제 → 핵심 내용 → 독자가 얻는 것 → CTA
4. 검색 키워드 자연스럽게 포함: AI 에이전트 평가, LLM 품질, Harness Engineering
5. 한국어로 작성 (Amazon.co.jp 등 한국어 독자 타겟)

HTML 설명 텍스트만 출력하세요."""

KEYWORDS_PROMPT = """Amazon KDP 검색 키워드 7개를 선정하세요.
각 키워드는 최대 7단어 이내.

책 주제: {title} — {subtitle}

독자 검색 행동 분석:
- 개발자가 AI 에이전트 평가를 검색할 때 쓰는 용어
- 한국어 키워드 우선 (Amazon.co.jp 한국어 섹션 타겟)
- 경쟁이 낮고 의도가 명확한 키워드

형식: 번호 없이 키워드 7개를 줄바꿈으로 구분해서만 출력."""



def load_intro() -> str:
    intro_path = BOOK_DIR / "00_서문.md"
    if intro_path.exists():
        return intro_path.read_text(encoding="utf-8")[:3000]
    return ""


def generate_description(client: anthropic.Anthropic, intro: str) -> str:
    prompt = DESCRIPTION_PROMPT.format(
        title=BOOK_TITLE, subtitle=BOOK_SUBTITLE,
        author=AUTHOR_NAME, intro_content=intro,
    )
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def generate_keywords(client: anthropic.Anthropic) -> list[str]:
    prompt = KEYWORDS_PROMPT.format(title=BOOK_TITLE, subtitle=BOOK_SUBTITLE)
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    keywords = [k.strip() for k in raw.split("\n") if k.strip()]
    return keywords[:7]


def generate_author_bio(_client: anthropic.Anthropic) -> str:
    return AUTHOR_BIO_KDP


CHECKLIST = """
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
   - Author: {author}
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
   - List Price: ${ebook_price} USD
   - KDP Select 등록 (선택 — 90일 독점, Kindle Unlimited 포함)
6. **Publish** → 검토 72시간 → Amazon 스토어 노출

### 가격 전략
| 형식 | 가격 | 로열티 | 정산 예상 |
|------|------|--------|---------|
| Kindle eBook | ${ebook_price} | 70% | ${ebook_royalty:.2f}/권 |
| Paperback (POD) | ${print_price} | 60%* | ${print_royalty:.2f}/권 |

*인쇄 비용 차감 후 실수령 기준 (200페이지 기준 약 $5 인쇄비)

### 한국어 책 판매 최적화
- Amazon.co.jp (일본 → 한국어 독자 접근 가능)
- Amazon.com → Korean Books 카테고리
- Goodreads 등록 (Author Program)
- 블로그/GitHub에 Amazon 링크 추가
""".format(
    author=AUTHOR_NAME,
    ebook_price=EBOOK_PRICE_USD,
    ebook_royalty=EBOOK_PRICE_USD * 0.70,
    print_price=PRINT_PRICE_USD,
    print_royalty=PRINT_PRICE_USD * 0.60 - 5.0,
)


def build_metadata_file(description: str, keywords: list[str], author_bio: str) -> str:
    lines = [
        f"# Amazon KDP 메타데이터 — {BOOK_TITLE}",
        "",
        "---",
        "",
        "## 기본 정보",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 제목 | {BOOK_TITLE} |",
        f"| 부제목 | {BOOK_SUBTITLE} |",
        f"| 저자 | {AUTHOR_NAME} |",
        f"| 언어 | {LANGUAGE} (Korean) |",
        f"| 출판사 | {PUBLISHER} |",
        f"| BISAC 1 | {BISAC_PRIMARY} |",
        f"| BISAC 2 | {BISAC_SECONDARY} |",
        f"| eBook 가격 | ${EBOOK_PRICE_USD} USD |",
        f"| Print 가격 | ${PRINT_PRICE_USD} USD |",
        "",
        "---",
        "",
        "## 책 설명 (HTML — KDP 복사·붙여넣기용)",
        "",
        "```html",
        description,
        "```",
        "",
        "---",
        "",
        "## 검색 키워드 (7개)",
        "",
        "KDP → Book Details → Keywords 7개 칸에 각각 입력:",
        "",
    ]
    for i, kw in enumerate(keywords, 1):
        lines.append(f"{i}. {kw}")

    lines += [
        "",
        "---",
        "",
        "## 저자 소개",
        "",
        author_bio,
        "",
        "---",
        "",
        CHECKLIST,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Amazon KDP 메타데이터 생성")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = OUTPUT_DIR / "kdp"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kdp_metadata.md"
    description_path = out_dir / "description.html"
    keywords_path = out_dir / "keywords.txt"

    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} 이미 존재. --force로 덮어쓰기.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    intro = load_intro()

    print("\n[KDP] 책 설명 생성 중...")
    description = generate_description(client, intro)

    print("[KDP] 검색 키워드 생성 중...")
    keywords = generate_keywords(client)

    print("[KDP] 저자 소개 생성 중...")
    author_bio = generate_author_bio(client)

    metadata = build_metadata_file(description, keywords, author_bio)
    out_path.write_text(metadata, encoding="utf-8")
    description_path.write_text(description, encoding="utf-8")
    keywords_path.write_text("\n".join(keywords), encoding="utf-8")

    print(f"\n완료:")
    print(f"  {out_path}       ← 전체 메타데이터 + 체크리스트")
    print(f"  {description_path} ← KDP HTML 설명 (복붙용)")
    print(f"  {keywords_path}     ← 키워드 7개")
    print(f"\n키워드 미리보기:")
    for i, kw in enumerate(keywords, 1):
        print(f"  {i}. {kw}")


if __name__ == "__main__":
    main()
