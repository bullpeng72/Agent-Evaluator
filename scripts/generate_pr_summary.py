#!/usr/bin/env python3
"""
scripts/generate_pr_summary.py
==================================
SPEC-034: Ch29 §29.4 PR 설명 템플릿의 "Gate 점수"/"위반 이력" 항목을 결과 JSON과
search_violations()에서 직접 읽어 채운다 — 손으로 옮겨 적다 생기는 오탈자·누락을 없앤다.

Gate 점수는 extra_metrics.harness_groups.{A,D,G}.score(대문자 단일 글자 키)에서,
세션 목표는 extra_metrics.lineage.iteration_note에서 읽는다. search_violations()는
task_id 필터가 아니라 키워드 검색(FTS5 MATCH)이므로, 세 번째 인자로 이 세션이
다룬 도구 이름이나 핵심 키워드를 넘겨야 한다 — "이 세션의 위반 전체"를 정확히
가져오는 API는 없다.

실행::

    python scripts/generate_pr_summary.py <result.json> <sessions.db> <violation_query> > pr_body.md
"""
from __future__ import annotations

import json
import sys

from agent_evaluator.storage.sqlite_backend import search_violations

_GATE_LABELS = [("A", "목표달성"), ("D", "성능"), ("G", "관측성")]


def generate_pr_summary(result_json_path: str, db_path: str, violation_query: str) -> str:
    with open(result_json_path, encoding="utf-8") as f:
        report = json.load(f)

    lineage = report.get("extra_metrics", {}).get("lineage", {})
    harness = report.get("extra_metrics", {}).get("harness_groups", {})

    lines = ["## 세션 목표", lineage.get("iteration_note") or "(iteration_note 미기록)", ""]
    lines += ["## Gate 점수", "| Gate | 점수 | 상태 |", "|---|---|---|"]
    for gate_key, label in _GATE_LABELS:
        g = harness.get(gate_key) or {}
        score = g.get("score")
        score_display = score if score is not None else "n/a"
        lines.append(f"| {gate_key} ({label}) | {score_display} | {g.get('status', 'n/a')} |")
    lines.append("")

    lines.append("## 위반 이력")
    results = search_violations(db_path, violation_query, include_blocked=True)  # SPEC-030
    if results:
        for r in results:
            prefix = "[차단됨]" if r.get("blocked") else "[관찰됨]"
            lines.append(f"- {prefix} {r['summary']}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 버전 태그")
    lines.append(f"`agent_version`: {lineage.get('agent_version') or 'n/a'}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "usage: python scripts/generate_pr_summary.py "
            "<result.json> <sessions.db> <violation_query>",
            file=sys.stderr,
        )
        sys.exit(2)
    print(generate_pr_summary(sys.argv[1], sys.argv[2], sys.argv[3]))
