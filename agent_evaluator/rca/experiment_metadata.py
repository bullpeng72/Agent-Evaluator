"""
agent_evaluator.rca.experiment_metadata
==========================================
Phase 4(개선 엔진, 폐루프 학습) — RCA가 "무엇이 나빠졌는지"(metric-space)까지는
자동으로 찾아내지만, "그게 실제로 어떤 코드 변경 때문인지"(commit-space)는
Chapter 31 §31.0의 워크드 예제에서도 여전히 사람이 git을 뒤져 찾아냈다. 이 모듈이
그 마지막 고리를 잇는다.

§31.5는 ``trace_incident_ownership.py``(PR 작성자·승인자 역추적)를 "참조 패턴이지
SDK가 검증한 기능이 아니다"라고 명시했다 — 하지만 그 경계는 그 스크립트가
**GitHub CLI(``gh``)에 의존하고 팀마다 다른 merge 전략(squash vs merge commit)을
가정**하기 때문이었다. "RCA 결과를 실제 코드 변경과 연결한다"는 방향 자체를
반대한 게 아니다. 이 모듈은 그 문제를 피한다 — ``gh``도 GitHub API도 안 쓰고
순수 ``git`` 명령(``git diff --stat``·``git log``)만 사용한다. git이 설치된 어떤
저장소에서도 동작하고, 팀의 merge 전략에 대한 가정이 없다(단순히 두 커밋 사이의
diff를 본다).

새 사용자 입력 절차를 만들지 않는다 — ``agent_version="auto"``가 이미
``git rev-parse HEAD``로 커밋을 캐싱해 ``extra_metrics.lineage.git_commit``에
저장해둔다(원칙④: 이미 있는 걸 다시 만들지 않는다). 이 모듈은 두 리포트의
이 필드를 읽어 사후에(post-hoc) diff를 조회할 뿐이다.
"""
from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import Any


@dataclasses.dataclass(frozen=True)
class CommitInfo:
    sha: str
    author: str
    date: str
    subject: str


@dataclasses.dataclass(frozen=True)
class ExperimentMetadata:
    """두 리포트(baseline/current)의 git commit 사이에 실제로 무엇이 바뀌었는지."""
    from_commit: str
    to_commit: str
    changed_files: list[str]
    diff_stat_summary: str          # git diff --stat의 마지막 요약 줄(예: "3 files changed, ...")
    commits_between: list[CommitInfo]
    source: str = "git"              # 향후 다른 소스(팀 자체 PR 시스템 등) 확장 여지를 남기는 표식


def _extract_commit_sha(lineage: dict[str, Any]) -> str | None:
    """lineage에서 커밋 SHA를 뽑는다. ``git_commit``이 정본이고(항상 순수 커밋 SHA),
    없으면 ``agent_version``에서 ``-dirty-<hash>`` 접미사를 벗겨 폴백한다(§20.4.1
    "auto" 태깅 규약과 동일한 파싱)."""
    commit = lineage.get("git_commit")
    if commit:
        return str(commit)
    agent_version = lineage.get("agent_version")
    if agent_version and isinstance(agent_version, str):
        return agent_version.split("-dirty-")[0] or None
    return None


def _run_git(repo_path: str | Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def derive_experiment_metadata(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    repo_path: str | Path = ".",
) -> ExperimentMetadata | None:
    """before/after 리포트의 ``lineage.git_commit``에서 실제 diff를 git으로 직접
    조회한다 — ``gh`` CLI·GitHub API 의존 없음.

    Args:
        before: 비교 기준(baseline) 평가 결과 JSON(로드된 dict).
        after: 비교 대상(current) 평가 결과 JSON.
        repo_path: 커밋을 조회할 git 저장소 경로(기본값: 현재 디렉토리).

    Returns:
        두 커밋 모두 확인되고 저장소에서 조회 가능하면 ``ExperimentMetadata``,
        아니면(커밋 정보 없음·저장소 아님·커밋을 못 찾음 등) ``None`` — 조용히
        실패한다(diff를 못 구해도 RCA의 나머지 결과는 그대로 유효해야 하므로).
    """
    before_lineage = (before.get("extra_metrics") or {}).get("lineage") or {}
    after_lineage = (after.get("extra_metrics") or {}).get("lineage") or {}
    from_commit = _extract_commit_sha(before_lineage)
    to_commit = _extract_commit_sha(after_lineage)
    if not from_commit or not to_commit or from_commit == to_commit:
        return None

    diff_stat = _run_git(repo_path, ["diff", "--stat", f"{from_commit}..{to_commit}"])
    if diff_stat is None:
        return None  # 저장소가 아니거나 커밋을 못 찾음 — 조용히 포기

    lines = [ln for ln in diff_stat.splitlines() if ln.strip()]
    changed_files = [ln.split("|")[0].strip() for ln in lines[:-1]] if len(lines) > 1 else []
    summary = lines[-1].strip() if lines else "(no changes)"

    log_output = _run_git(
        repo_path,
        [
            "log", "--pretty=format:%H\x1f%an\x1f%ad\x1f%s", "--date=short",
            f"{from_commit}..{to_commit}",
        ],
    ) or ""
    commits_between = []
    for line in log_output.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits_between.append(
                CommitInfo(sha=parts[0][:8], author=parts[1], date=parts[2], subject=parts[3])
            )

    return ExperimentMetadata(
        from_commit=from_commit[:8],
        to_commit=to_commit[:8],
        changed_files=changed_files,
        diff_stat_summary=summary,
        commits_between=commits_between,
    )
