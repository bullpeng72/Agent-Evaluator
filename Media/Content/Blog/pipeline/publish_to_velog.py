"""Velog 비공식 GraphQL API를 통해 블로그 포스트를 자동 발행한다.

인증: 브라우저 쿠키의 access_token (F12 → Application → Cookies → velog.io)
환경변수: VELOG_ACCESS_TOKEN

Usage:
    python publish_to_velog.py <post_id>               # 발행 (draft=False)
    python publish_to_velog.py <post_id> --draft       # 임시 저장
    python publish_to_velog.py <post_id> --preview     # 발행 없이 내용만 출력
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# .env 탐색: 스크립트 위치 기준으로 상위 디렉토리를 순서대로 확인
def _find_env() -> Path:
    for parent in [Path(__file__).parent, *Path(__file__).parents]:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return Path(".env")

load_dotenv(_find_env())

PIPELINE_DIR = Path(__file__).parent
OUTPUT_DIR = PIPELINE_DIR.parent / "output"

VELOG_GQL = "https://v3.velog.io/graphql"

# writePost mutation — Velog 내부 API
WRITE_POST_MUTATION = """
mutation WritePost($input: WritePostInput!) {
  writePost(input: $input) {
    id
    title
    slug
    url_slug
    is_private
    is_temp
    user {
      username
    }
  }
}
"""

UPDATE_POST_MUTATION = """
mutation UpdatePost($id: ID!, $input: UpdatePostInput!) {
  updatePost(id: $id, input: $input) {
    id
    title
    slug
    url_slug
  }
}
"""


def _load_post(post_id: str) -> tuple[str, dict]:
    """post_velog.md + seo.json 로드."""
    post_dir = OUTPUT_DIR / post_id
    md_path = post_dir / "post_velog.md"
    seo_path = post_dir / "seo.json"

    if not md_path.exists():
        print(f"[ERROR] 포스트 파일 없음: {md_path}")
        print(f"  먼저 '/blog {post_id}' 로 포스트를 생성하세요.")
        sys.exit(1)

    content = md_path.read_text(encoding="utf-8")
    seo = json.loads(seo_path.read_text(encoding="utf-8")) if seo_path.exists() else {}
    return content, seo


def _parse_post(content: str, seo: dict) -> dict:
    """마크다운에서 제목·태그·본문을 추출한다."""
    lines = content.splitlines()

    # 첫 줄 해시태그 추출 (#태그1 #태그2 ...)
    tags: list[str] = []
    body_start = 0
    if lines and lines[0].startswith("#") and not lines[0].startswith("# "):
        raw_tags = re.findall(r"#(\S+)", lines[0])
        tags = raw_tags[:5]  # Velog 최대 5개
        body_start = 1

    # 제목 추출 (# 제목)
    title = ""
    for i, line in enumerate(lines[body_start:], body_start):
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            body_start = i + 1
            break

    # 본문 (빈 줄 skip 후 시작)
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    body = "\n".join(lines[body_start:])

    slug = seo.get("slug_suggestion", re.sub(r"[^a-z0-9-]", "-", title.lower())[:50])
    short_description = seo.get("meta_description", "")

    return {
        "title": title,
        "body": body,
        "tags": tags,
        "slug": slug,
        "short_description": short_description,
        "series": None,
        "thumbnail": None,
    }


def _gql_request(token: str, query: str, variables: dict) -> dict:
    """Velog GraphQL 요청."""
    import urllib.request
    import urllib.error

    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        VELOG_GQL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"access_token={token}",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://velog.io",
            "Referer": "https://velog.io/write",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] HTTP {e.code}: {body[:300]}")
        sys.exit(1)


def publish(post_id: str, draft: bool = False, preview: bool = False) -> None:
    token = os.getenv("VELOG_ACCESS_TOKEN", "").strip()
    if not token and not preview:
        print("[ERROR] VELOG_ACCESS_TOKEN 환경변수가 없습니다.")
        print()
        print("  Chrome F12 → Console에 아래 실행:")
        print("  document.cookie.split(';').find(c=>c.trim().startsWith('access_token')).trim()")
        print()
        print("  나온 값에서 = 이후 부분을 복사해 .env에 추가:")
        print("  VELOG_ACCESS_TOKEN=eyJ...")
        sys.exit(1)

    content, seo = _load_post(post_id)
    post = _parse_post(content, seo)

    if preview:
        print(f"\n{'─'*55}")
        print(f"  제목: {post['title']}")
        print(f"  슬러그: {post['slug']}")
        print(f"  태그: {', '.join(post['tags'])}")
        print(f"  설명: {post['short_description'][:80]}...")
        print(f"  본문 길이: {len(post['body'])}자")
        print(f"{'─'*55}")
        print("\n[PREVIEW] 실제 발행하려면 --draft 또는 플래그 없이 실행하세요.")
        return

    mode = "임시저장" if draft else "발행"
    print(f"\n[Velog] {post['title'][:50]} — {mode} 중...")

    variables = {
        "input": {
            "title": post["title"],
            "body": post["body"],
            "tags": post["tags"],
            "is_markdown": True,
            "is_temp": draft,
            "is_private": False,
            "url_slug": post["slug"],
            "thumbnail": post["thumbnail"],
            "meta": {},
            "series_id": post["series"],
        }
    }

    result = _gql_request(token, WRITE_POST_MUTATION, variables)

    if "errors" in result:
        errs = result["errors"]
        print(f"[ERROR] GraphQL 오류: {errs}")
        # 토큰 만료 가능성
        if any("auth" in str(e).lower() or "unauthorized" in str(e).lower() for e in errs):
            print("\n  토큰이 만료됐을 수 있습니다. 브라우저에서 재로그인 후 토큰을 갱신하세요.")
        sys.exit(1)

    data = result.get("data", {}).get("writePost", {})
    username = data.get("user", {}).get("username", "bullpeng72")
    url_slug = data.get("url_slug", post["slug"])
    post_url = f"https://velog.io/@{username}/{url_slug}"

    print(f"\n  ✅ {'임시저장' if draft else '발행'} 완료!")
    print(f"  URL: {post_url}")
    print(f"  ID : {data.get('id', '—')}")


def main():
    parser = argparse.ArgumentParser(description="Velog 자동 발행")
    parser.add_argument("post_id", help="포스트 ID (예: retrofit_30min)")
    parser.add_argument("--draft", action="store_true", help="임시저장 (발행 안 함)")
    parser.add_argument("--preview", action="store_true", help="내용 확인만 (발행 안 함)")
    args = parser.parse_args()

    publish(args.post_id, draft=args.draft, preview=args.preview)


if __name__ == "__main__":
    main()
