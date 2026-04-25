"""Step 2: 블로그 포스트 → SEO 메타데이터.

생성 항목: 메타 description, 검색 키워드, Open Graph 정보, 내부 링크 추천

Usage:
    python generate_seo.py gate_a
    python generate_seo.py --all    # 모든 기존 포스트에 대해 실행
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import CLAUDE_MODEL, OUTPUT_DIR, POST_MAP_PATH
from llm import call_claude

SEO_PROMPT = """다음 블로그 포스트의 SEO 메타데이터를 JSON으로 생성하세요.

포스트 제목: {title}
태그: {tags}
포스트 내용 (일부):
{content_preview}

아래 JSON 형식으로 정확히 출력하세요. 다른 텍스트 없이 JSON만:
{{
  "meta_description": "검색결과에 표시될 설명 (155자 이내, 핵심 키워드 포함)",
  "focus_keyword": "주요 검색 키워드 1개",
  "secondary_keywords": ["보조 키워드1", "보조 키워드2", "보조 키워드3"],
  "og_title": "소셜 공유용 제목 (60자 이내)",
  "og_description": "소셜 공유용 설명 (200자 이내)",
  "slug_suggestion": "url-slug-in-english",
  "reading_time_minutes": 5,
  "content_type": "tutorial | 개념 | 사례연구 | 심층분석",
  "target_audience": "독자 설명 (1문장)",
  "internal_link_topics": ["관련 포스트 주제1", "관련 포스트 주제2"]
}}"""


def load_post_meta(post_id: str) -> dict:
    data = json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))
    post = data["posts"].get(post_id, {})
    post["id"] = post_id
    return post


def generate_seo(post_id: str, post_meta: dict, content: str) -> dict:
    prompt = SEO_PROMPT.format(
        title=post_meta.get("title", ""),
        tags=", ".join(post_meta.get("tags", [])),
        content_preview=content[:2000],
    )

    raw = call_claude("", prompt, CLAUDE_MODEL, max_tokens=800).strip()
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        return {"error": "JSON 파싱 실패", "raw": raw}

    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return {"error": "JSON 디코딩 오류", "raw": raw}


def format_seo_report(post_id: str, seo: dict) -> str:
    if "error" in seo:
        return f"# SEO 메타데이터 오류\n\n{seo.get('raw', '')}"

    lines = [
        f"# SEO 메타데이터 — {post_id}",
        "",
        f"## 메타 Description",
        f"{seo.get('meta_description', '')}",
        "",
        f"## 주요 키워드",
        f"- Focus: **{seo.get('focus_keyword', '')}**",
        f"- Secondary: {', '.join(seo.get('secondary_keywords', []))}",
        "",
        f"## Open Graph",
        f"- OG Title: {seo.get('og_title', '')}",
        f"- OG Description: {seo.get('og_description', '')}",
        "",
        f"## 기타",
        f"- URL Slug: `{seo.get('slug_suggestion', '')}`",
        f"- 예상 읽기 시간: {seo.get('reading_time_minutes', '?')}분",
        f"- 콘텐츠 유형: {seo.get('content_type', '')}",
        f"- 대상 독자: {seo.get('target_audience', '')}",
        "",
        f"## 내부 링크 추천 주제",
    ]
    for topic in seo.get("internal_link_topics", []):
        lines.append(f"- {topic}")

    return "\n".join(lines)


def process_post(post_id: str, force: bool = False) -> bool:
    post_dir = OUTPUT_DIR / post_id
    content_path = post_dir / "post_velog.md"
    seo_json_path = post_dir / "seo.json"
    seo_txt_path = post_dir / "seo.txt"

    if seo_json_path.exists() and not force:
        print(f"  [SKIP] {post_id} — seo.json 이미 존재.")
        return True

    if not content_path.exists():
        print(f"  [SKIP] {post_id} — post_velog.md 없음. chapter_to_blog.py 먼저 실행.")
        return False

    print(f"  {post_id}: SEO 메타데이터 생성 중...")
    post_meta = load_post_meta(post_id)
    content = content_path.read_text(encoding="utf-8")
    seo = generate_seo(post_id, post_meta, content)

    seo_json_path.write_text(json.dumps(seo, ensure_ascii=False, indent=2), encoding="utf-8")
    seo_txt_path.write_text(format_seo_report(post_id, seo), encoding="utf-8")

    print(f"  완료: {seo_txt_path.name} | Focus: {seo.get('focus_keyword', '?')}")
    return True


def main():
    parser = argparse.ArgumentParser(description="블로그 포스트 SEO 메타데이터 생성")
    parser.add_argument("post_id", nargs="?", help="포스트 ID")
    parser.add_argument("--all", action="store_true", help="모든 기존 포스트에 적용")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.all:
        data = json.loads(POST_MAP_PATH.read_text(encoding="utf-8"))
        post_ids = list(data["posts"].keys())
        print(f"\n[Step 2] SEO 메타데이터 생성 — {len(post_ids)}개 포스트")
        for post_id in post_ids:
            process_post(post_id, args.force)
        return

    if not args.post_id:
        parser.print_help()
        sys.exit(0)

    print(f"\n[Step 2] SEO 메타데이터 생성: {args.post_id}")
    process_post(args.post_id, args.force)


if __name__ == "__main__":
    main()
