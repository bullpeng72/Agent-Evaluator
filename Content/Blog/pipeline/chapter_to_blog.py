"""Step 1: 책 챕터 → Velog 블로그 포스트 Markdown.

Usage:
    python chapter_to_blog.py intro
    python chapter_to_blog.py gate_a
    python chapter_to_blog.py --list
"""
import argparse
import json
import sys
from pathlib import Path

from config import (
    BOOK_DIR, CLAUDE_MODEL,
    GITHUB_URL, OUTPUT_DIR, POST_MAP_PATH, PYPI_URL, SERIES_NAME,
)
from llm import call_claude

BLOG_SYSTEM_PROMPT = """당신은 기술 블로그 작가입니다.
AI 에이전트 평가 전문 서적의 챕터를 개발자 독자를 위한 블로그 포스트로 변환합니다.

규칙:
- 한국어, 구어체와 문어체 중간 수준 (너무 딱딱하지도, 너무 가볍지도 않게)
- 독자는 Python 개발자. LangChain/OpenAI 경험 있음.
- 제목: 검색 키워드를 자연스럽게 포함. 클릭하고 싶은 제목.
- TL;DR 박스: 핵심 3줄 요약 (블록인용 > 형식)
- 본문 구조: 문제 제기 → 개념 설명 → 코드 예제 → 결론
- 코드 블록: 실제 실행 가능한 코드. 언어 태그 명시.
- 각 H2 섹션 끝에 한 줄 요약 문장.
- 마지막에 CTA (call-to-action): GitHub 링크, PyPI 링크, 시리즈 연결.
- 목표 분량: {target_words}자.
- SEO: H2/H3 헤더에 핵심 키워드 자연스럽게 배치."""

BLOG_USER_PROMPT = """다음 책 챕터를 블로그 포스트로 변환하세요.

포스트 정보:
- 슬러그: {post_id}
- 제목: {title}
- 유형: {post_type}
- 태그: {tags}
- 핵심 훅: {hook}
- 목표 분량: {target_words}자
- 시리즈: {series_name} (순서: {series_order}편)

GitHub: {github_url}
PyPI: {pypi_url}

챕터 내용:
---
{chapter_content}
---

아래 구조로 블로그 포스트를 작성하세요:

1. 제목 (# 헤더, 주어진 제목 그대로)
2. TL;DR (> 블록인용으로 핵심 3줄)
3. 도입부 (왜 이게 중요한지, 문제 상황)
4. 본문 (H2/H3 구조, 코드 예제 포함)
5. 마무리 (핵심 요약)
6. 다음 편 예고 + CTA (GitHub/PyPI 링크)
"""

CTA_TEMPLATE = """
---

## 마치며

> **시리즈**: [{series_name}]({github_url}/blob/main/Book/README.md) — {series_order}편/{total_posts}편

**관련 리소스:**
- GitHub: {github_url}
- PyPI: `pip install agent-evaluator`
- 전체 문서: {pypi_url}

다음 편에서는 **{next_title}**을 다룹니다.
"""


def load_post(post_id: str) -> dict:
    data = json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))
    post = data["posts"].get(post_id)
    if not post:
        print(f"[ERROR] 포스트 '{post_id}' 없음.")
        available = list(data["posts"].keys())
        print(f"사용 가능: {', '.join(available)}")
        sys.exit(1)
    post["id"] = post_id
    post["series_name"] = data.get("series_name", SERIES_NAME)
    post["github_url"] = data.get("github_url", GITHUB_URL)
    post["pypi_url"] = data.get("pypi_url", PYPI_URL)
    post["total_posts"] = len(data["posts"])
    return post


def load_chapter(chapter_file: str) -> str:
    path = BOOK_DIR / chapter_file
    if not path.exists():
        print(f"[ERROR] 챕터 파일 없음: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def get_next_post_title(post_id: str) -> str:
    """다음 편 제목 반환."""
    data = json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))
    posts = data["posts"]
    current_order = posts[post_id].get("series_order", 0)
    for pid, p in posts.items():
        if p.get("series_order") == current_order + 1:
            return p.get("title", "")
    return "다음 시리즈"


def generate_blog_post(post: dict, chapter_content: str) -> str:
    system = BLOG_SYSTEM_PROMPT.format(target_words=post.get("target_words", 2000))
    user = BLOG_USER_PROMPT.format(
        post_id=post["id"],
        title=post["title"],
        post_type=post.get("type", ""),
        tags=", ".join(post.get("tags", [])),
        hook=post.get("hook", ""),
        target_words=post.get("target_words", 2000),
        series_name=post["series_name"],
        series_order=post.get("series_order", "?"),
        github_url=post["github_url"],
        pypi_url=post["pypi_url"],
        chapter_content=chapter_content[:14000],
    )

    print(f"  Claude 호출 중...")
    content = call_claude(system, user, CLAUDE_MODEL, max_tokens=5000)

    # CTA 블록 추가 (Claude가 포함 안 했을 경우 대비)
    if GITHUB_URL not in content:
        next_title = get_next_post_title(post["id"])
        content += CTA_TEMPLATE.format(
            series_name=post["series_name"],
            github_url=post["github_url"],
            pypi_url=post["pypi_url"],
            series_order=post.get("series_order", "?"),
            total_posts=post.get("total_posts", "?"),
            next_title=next_title,
        )

    return content


def add_velog_tags(content: str, tags: list[str]) -> str:
    """Velog용 태그 라인을 포스트 상단에 추가."""
    tag_line = " ".join(f"#{t.replace(' ', '')}" for t in tags)
    return f"{tag_line}\n\n{content}"


def save_post(post_id: str, content: str, platform: str) -> Path:
    out_dir = OUTPUT_DIR / post_id
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"post_{platform}.md"
    out_path = out_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path


def list_posts():
    data = json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))
    posts = sorted(data["posts"].items(), key=lambda x: x[1].get("series_order", 99))
    print(f"\n{'ID':25s} {'순서':5s} {'유형':8s} {'제목'}")
    print("─" * 80)
    for post_id, post in posts:
        status = "✅" if (OUTPUT_DIR / post_id / "post_velog.md").exists() else "·"
        print(f"{status} {post_id:23s} {post.get('series_order', '?'):5} {post.get('type', ''):8s} {post['title'][:45]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="챕터 → Velog 블로그 포스트 생성")
    parser.add_argument("post_id", nargs="?", help="포스트 ID (예: gate_a, intro)")
    parser.add_argument("--list", action="store_true", help="포스트 목록 출력")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    if args.list:
        list_posts()
        return

    if not args.post_id:
        parser.print_help()
        sys.exit(0)

    post_id = args.post_id

    # 이미 존재하는지 확인
    out_path_check = OUTPUT_DIR / post_id / "post_velog.md"
    if out_path_check.exists() and not args.force:
        print(f"[SKIP] {out_path_check} 이미 존재. --force로 덮어쓰기.")
        return

    print(f"\n[Step 1] 챕터 → Velog 포스트: {post_id}")
    post = load_post(post_id)
    print(f"  제목: {post['title']}")
    print(f"  챕터: {post['chapter_file']}")

    chapter_content = load_chapter(post["chapter_file"])
    print(f"  챕터 크기: {len(chapter_content):,}자")

    content = generate_blog_post(post, chapter_content)
    content = add_velog_tags(content, post.get("tags", []))
    read_time = len(content) // 500

    out_path = save_post(post_id, content, "velog")
    print(f"  완료: {out_path} (~{read_time}분 읽기)")


if __name__ == "__main__":
    main()
