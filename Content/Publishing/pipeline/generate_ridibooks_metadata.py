"""리디북스 등록에 필요한 메타데이터를 생성한다.

리디북스는 Amazon KDP와 달리 HTML 설명 미지원 — 순수 텍스트(마크다운 일부) 사용.
카테고리: IT/컴퓨터 > 프로그래밍 > 개발 방법론 (카테고리 ID: 550)

생성 항목:
  - 책 소개 (텍스트, 1000~2000자, 리디북스 등록 최적화)
  - 작가 소개
  - 출판사 리뷰 / 편집자 코멘트
  - 등록 체크리스트

Usage:
    python generate_ridibooks_metadata.py
    python generate_ridibooks_metadata.py --force
"""
import argparse
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY, AUTHOR_BIO_RIDI, AUTHOR_NAME, BOOK_DIR,
    BOOK_SUBTITLE, BOOK_TITLE, CLAUDE_MODEL, OUTPUT_DIR,
    RIDI_CATEGORY_ID, RIDI_EBOOK_PRICE_KRW, RIDI_EBOOK_PRICE_SALE_KRW,
)

DESCRIPTION_PROMPT = """당신은 한국 전자책 플랫폼 리디북스에 능통한 편집자입니다.
리디북스 IT 기술서 섹션에 최적화된 책 소개를 작성하세요.

책 정보:
- 제목: {title}
- 부제목: {subtitle}
- 저자: {author}
- 카테고리: IT/컴퓨터 > 프로그래밍 > 개발 방법론
- 대상 독자: Python 개발자, AI 엔지니어, DevOps 엔지니어

서문 내용 (참고):
{intro_content}

요구사항:
1. 순수 텍스트 (HTML 태그 금지, 줄바꿈과 단락 구분만 사용)
2. 총 1000~2000자 (한국어 기준)
3. 구조: [이 책에 대하여] 단락 → [이 책의 핵심 내용] 단락 → [이런 분께 권합니다] 단락
4. 리디북스 IT 독자 맞춤: 실무 적용 가능성, 코드 예제 풍부함 강조
5. 검색 최적화 키워드 자연스럽게 포함: AI 에이전트, LLM, 품질 평가, CI/CD, Python
6. 구어체 아닌 서술체로 작성

텍스트만 출력하세요."""


PUBLISHER_REVIEW_PROMPT = """리디북스 '출판사 리뷰' 섹션용 짧은 편집자 코멘트를 작성하세요.
이 책은 자가 출판이므로 저자 본인의 시각으로 작성.

책: {title} — {subtitle}

요구사항:
- 2~3문장, 150~250자
- "이 책은..." 으로 시작
- 독자가 얻을 가장 실용적인 가치 한 가지 강조
- 한국어로 작성"""


CHECKLIST = """
## 리디북스 등록 체크리스트

### 사전 준비
- [ ] 리디북스 출판사 계정 생성 (ridibooks.com/publish → 출판사 등록)
- [ ] 사업자등록 또는 개인 출판사 등록 (개인도 가능)
- [ ] EPUB 파일 (build_epub.py --target ridi 로 생성)
- [ ] 표지 이미지 (1400×2000px 이상, JPG/PNG, 200KB 이상)

### 등록 순서
1. **출판사 등록**: ridibooks.com/publish → "출판사 신청"
   - 개인 출판사: 사업자등록 없이 신청 가능 (심사 2~5 영업일)
2. **도서 등록**: 출판사 관리자 → 도서 등록 → 새 도서
3. **기본 정보 입력**
   - 도서명: {title}
   - 저자: {author}
   - 출판사: Self-Published
   - 카테고리: IT/컴퓨터 > 프로그래밍 (카테고리 ID: {category_id})
   - 언어: 한국어
   - 발행일: 2026년 (예정)
4. **소개 텍스트 입력**
   - 책 소개: (아래 생성된 텍스트 붙여넣기)
   - 작가 소개: (아래 생성된 텍스트 붙여넣기)
   - 출판사 리뷰: (아래 생성된 텍스트 붙여넣기)
5. **파일 업로드**
   - EPUB 파일 업로드 (리디북스 뷰어 미리보기로 확인)
   - 표지 이미지 업로드
6. **가격 설정**
   - 정가: {price_krw:,}원
   - 판매가: {sale_krw:,}원 (정가의 90%)
   - 리디 로열티: 판매가의 50% → 권당 {royalty:,}원
7. **심사 신청** → 심사 3~7 영업일 → 리디북스 스토어 노출

### 가격 전략
| 항목 | 금액 |
|------|------|
| 정가 | {price_krw:,}원 |
| 판매가 | {sale_krw:,}원 |
| 로열티 (50%) | {royalty:,}원/권 |
| 손익분기 (월) | 판매 50권 이상 (월 {break_even:,}원) |

### 리디북스 최적화 팁
- 도서 소개 첫 문단이 검색 결과에 노출됨 → 핵심 가치를 첫 50자에 담기
- 태그 최대 10개 활용: AI 에이전트, LLM, Python, 품질평가, CI/CD, 개발자, 백엔드, MLOps
- 리디 셀렉트(구독) 등록 고려 (추가 수익원, 별도 계약)
""".format(
    title=BOOK_TITLE,
    author=AUTHOR_NAME,
    category_id=RIDI_CATEGORY_ID,
    price_krw=RIDI_EBOOK_PRICE_KRW,
    sale_krw=RIDI_EBOOK_PRICE_SALE_KRW,
    royalty=int(RIDI_EBOOK_PRICE_SALE_KRW * 0.5),
    break_even=int(RIDI_EBOOK_PRICE_SALE_KRW * 0.5 * 50),
)


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
        model=CLAUDE_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def generate_author_bio(_client: anthropic.Anthropic) -> str:
    return AUTHOR_BIO_RIDI


def generate_publisher_review(client: anthropic.Anthropic) -> str:
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=300,
        messages=[{"role": "user", "content": PUBLISHER_REVIEW_PROMPT.format(
            title=BOOK_TITLE, subtitle=BOOK_SUBTITLE,
        )}],
    )
    return msg.content[0].text.strip()


def build_metadata_file(description: str, author_bio: str, publisher_review: str) -> str:
    lines = [
        f"# 리디북스 메타데이터 — {BOOK_TITLE}",
        "",
        "---",
        "",
        "## 기본 정보",
        "",
        "| 항목 | 값 |",
        "|------|-----|",
        f"| 도서명 | {BOOK_TITLE} |",
        f"| 부제목 | {BOOK_SUBTITLE} |",
        f"| 저자 | {AUTHOR_NAME} |",
        f"| 카테고리 ID | {RIDI_CATEGORY_ID} (IT/컴퓨터 > 프로그래밍) |",
        f"| 정가 | {RIDI_EBOOK_PRICE_KRW:,}원 |",
        f"| 판매가 | {RIDI_EBOOK_PRICE_SALE_KRW:,}원 |",
        f"| 로열티 | {int(RIDI_EBOOK_PRICE_SALE_KRW * 0.5):,}원/권 (50%) |",
        "",
        "---",
        "",
        "## 책 소개 (리디북스 등록용 텍스트)",
        "",
        description,
        "",
        "---",
        "",
        "## 작가 소개",
        "",
        author_bio,
        "",
        "---",
        "",
        "## 출판사 리뷰",
        "",
        publisher_review,
        "",
        "---",
        "",
        CHECKLIST,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="리디북스 메타데이터 생성")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = OUTPUT_DIR / "ridibooks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ridi_metadata.md"
    desc_path = out_dir / "description.txt"

    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} 이미 존재. --force로 덮어쓰기.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    intro = load_intro()

    print("\n[리디북스] 책 소개 생성 중...")
    description = generate_description(client, intro)

    print("[리디북스] 작가 소개 생성 중...")
    author_bio = generate_author_bio(client)

    print("[리디북스] 출판사 리뷰 생성 중...")
    publisher_review = generate_publisher_review(client)

    metadata = build_metadata_file(description, author_bio, publisher_review)
    out_path.write_text(metadata, encoding="utf-8")
    desc_path.write_text(description, encoding="utf-8")

    print(f"\n완료:")
    print(f"  {out_path}   ← 전체 메타데이터 + 체크리스트")
    print(f"  {desc_path}  ← 책 소개 텍스트 (복붙용)")
    print(f"\n책 소개 미리보기 (처음 100자):")
    print(f"  {description[:100]}...")


if __name__ == "__main__":
    main()
