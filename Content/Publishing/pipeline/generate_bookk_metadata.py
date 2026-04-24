"""부크크 등록에 필요한 메타데이터를 생성한다.

부크크(bookk.co.kr):
  - 종이책 POD: 교보문고 · 예스24 · 알라딘 자동 유통
  - 전자책: 부크크 자체 플랫폼 판매
  - 카테고리: IT/컴퓨터 > 프로그래밍/개발

생성 항목:
  - 책 소개 (부크크 등록 최적화, 1000~2000자)
  - 저자 소개
  - 출판 체크리스트 (종이책 + 전자책)

Usage:
    python generate_bookk_metadata.py
    python generate_bookk_metadata.py --force
"""
import argparse
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY, AUTHOR_BIO_BOOKK, AUTHOR_NAME, BOOK_DIR,
    BOOK_SUBTITLE, BOOK_TITLE, BOOKK_EBOOK_PRICE_KRW,
    BOOKK_PAPER_SIZE, BOOKK_PRINT_PRICE_KRW, CLAUDE_MODEL, OUTPUT_DIR,
)

DESCRIPTION_PROMPT = """당신은 한국 자가출판 플랫폼 부크크(bookk.co.kr)에 최적화된 편집자입니다.
부크크 IT 기술서 섹션에 맞는 책 소개를 작성하세요.

책 정보:
- 제목: {title}
- 부제목: {subtitle}
- 저자: {author}
- 카테고리: IT/컴퓨터 > 프로그래밍/개발
- 판매 채널: 부크크, 교보문고, 예스24, 알라딘

서문 내용 (참고):
{intro_content}

요구사항:
1. 순수 텍스트 (HTML 금지, 줄바꿈과 빈줄로 단락 구분)
2. 총 1000~2000자 (한국어 기준)
3. 구조:
   [책 소개] — 핵심 가치 2~3문장
   [이 책의 구성] — 6개 Part 간단 소개
   [이런 분께 추천합니다] — 3~4개 독자 프로파일
   [저자 소개] — 1~2문장
4. 교보문고·예스24에도 그대로 노출되므로 검색 최적화 키워드 포함:
   AI 에이전트, LLM, 품질 평가, Harness Engineering, Python, CI/CD
5. 전문 서술체로 작성 (구어체 X)

텍스트만 출력하세요."""



# 부크크 종이책 예상 인쇄비 (100페이지당 약 1,000원)
# 350p 기준 약 3,500원 인쇄비
BOOKK_PRINT_COST_KRW = 3_500
BOOKK_PRINT_ROYALTY = int((BOOKK_PRINT_PRICE_KRW - BOOKK_PRINT_COST_KRW) * 0.35)
BOOKK_EBOOK_ROYALTY = int(BOOKK_EBOOK_PRICE_KRW * 0.40)

CHECKLIST = """
## 부크크 등록 체크리스트

### 사전 준비
- [ ] 부크크 계정 생성 (bookk.co.kr → 회원가입)
- [ ] 종이책용 PDF (build_pdf_bookk.py로 생성, {paper_size} 판형)
- [ ] 전자책용 EPUB (build_epub.py --target kdp 또는 별도 EPUB)
- [ ] 표지 이미지 (종이책: 1968×2953px / 전자책: 1400×2000px 이상)

### 종이책 등록 순서 (bookk.co.kr)
1. 로그인 → "책 만들기" → "종이책"
2. **기본 정보**
   - 책 제목: {title}
   - 저자: {author}
   - 카테고리: IT/컴퓨터 > 프로그래밍/개발
   - 판형: {paper_size} ({paper_size_mm})
   - 제본: 무선제본 (권장)
3. **내지 파일 업로드**: PDF 업로드 → 미리보기 확인
4. **표지 디자인**: 부크크 표지 편집기 또는 직접 업로드
5. **책 소개 입력**: (아래 생성된 텍스트 붙여넣기)
6. **저자 소개 입력**: (아래 생성된 텍스트 붙여넣기)
7. **가격 설정**
   - 정가: {print_price:,}원
   - 인쇄비 차감 후 로열티: 약 {print_royalty:,}원/권 (35%)
8. **유통 채널 선택**:  ✅ 교보문고  ✅ 예스24  ✅ 알라딘  ✅ 부크크 자체몰
9. **출판 신청** → 부크크 심사 5~10 영업일 → 채널별 2~4주 내 노출

### 전자책 등록 순서
1. "책 만들기" → "전자책"
2. EPUB 파일 업로드 → 부크크 뷰어 미리보기 확인
3. 가격: {ebook_price:,}원 (로열티 약 {ebook_royalty:,}원/권, 40%)
4. 출판 신청 → 부크크 자체 플랫폼 판매 시작

### 가격 전략

| 형식 | 정가 | 인쇄비 | 로열티 | 비고 |
|------|------|--------|--------|------|
| 종이책 | {print_price:,}원 | ~{print_cost:,}원 | ~{print_royalty:,}원 | 교보·예스24·알라딘 유통 |
| 전자책 | {ebook_price:,}원 | — | ~{ebook_royalty:,}원 | 부크크 자체 플랫폼 |

### 유통 채널별 정산 일정
| 채널 | 정산 주기 |
|------|---------|
| 부크크 자체몰 | 매월 말 정산 |
| 교보문고 | 판매월 익익월 말 |
| 예스24 | 판매월 익익월 말 |
| 알라딘 | 판매월 익월 |

### 부크크 최적화 팁
- ISBN 발급: 부크크에서 무료 신청 가능 (교보·예스24 등록 필수 조건)
- 교보문고 MD 추천 신청: 등록 후 교보 담당 MD에게 개별 이메일 추천 가능
- 알라딘 새 책 알림: 등록 1주 내 알라딘 새 책 섹션 노출됨
""".format(
    title=BOOK_TITLE,
    author=AUTHOR_NAME,
    paper_size=BOOKK_PAPER_SIZE.upper(),
    paper_size_mm="148×210mm" if BOOKK_PAPER_SIZE == "a5" else
                  "182×257mm" if BOOKK_PAPER_SIZE == "b5" else "210×297mm",
    print_price=BOOKK_PRINT_PRICE_KRW,
    print_cost=BOOKK_PRINT_COST_KRW,
    print_royalty=BOOKK_PRINT_ROYALTY,
    ebook_price=BOOKK_EBOOK_PRICE_KRW,
    ebook_royalty=BOOKK_EBOOK_ROYALTY,
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
    return AUTHOR_BIO_BOOKK


def build_metadata_file(description: str, author_bio: str) -> str:
    lines = [
        f"# 부크크 메타데이터 — {BOOK_TITLE}",
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
        f"| 카테고리 | IT/컴퓨터 > 프로그래밍/개발 |",
        f"| 판형 (종이책) | {BOOKK_PAPER_SIZE.upper()} |",
        f"| 종이책 정가 | {BOOKK_PRINT_PRICE_KRW:,}원 |",
        f"| 전자책 정가 | {BOOKK_EBOOK_PRICE_KRW:,}원 |",
        f"| 종이책 로열티 | ~{BOOKK_PRINT_ROYALTY:,}원/권 |",
        f"| 전자책 로열티 | ~{BOOKK_EBOOK_ROYALTY:,}원/권 |",
        f"| 유통 채널 | 부크크 + 교보문고 + 예스24 + 알라딘 |",
        "",
        "---",
        "",
        "## 책 소개 (부크크·교보·예스24·알라딘 등록용)",
        "",
        description,
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
    parser = argparse.ArgumentParser(description="부크크 메타데이터 생성")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = OUTPUT_DIR / "bookk"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bookk_metadata.md"
    desc_path = out_dir / "description.txt"

    if out_path.exists() and not args.force:
        print(f"[SKIP] {out_path} 이미 존재. --force로 덮어쓰기.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    intro = load_intro()

    print("\n[부크크] 책 소개 생성 중...")
    description = generate_description(client, intro)

    print("[부크크] 저자 소개 생성 중...")
    author_bio = generate_author_bio(client)

    metadata = build_metadata_file(description, author_bio)
    out_path.write_text(metadata, encoding="utf-8")
    desc_path.write_text(description, encoding="utf-8")

    print(f"\n완료:")
    print(f"  {out_path}   ← 전체 메타데이터 + 체크리스트")
    print(f"  {desc_path}  ← 책 소개 텍스트 (복붙용)")
    print(f"\n책 소개 미리보기 (처음 100자):")
    print(f"  {description[:100]}...")


if __name__ == "__main__":
    main()
