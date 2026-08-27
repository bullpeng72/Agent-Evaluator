"""
tests/test_phase4_experiment_metadata.py
============================================
Phase 4(개선 엔진, 폐루프 학습) — rca.derive_experiment_metadata()의 회귀 테스트.

이 모듈은 실제 ``git`` 서브프로세스를 호출하므로(``git diff --stat``·``git log``),
모킹이 아니라 진짜 임시 git 저장소에 진짜 커밋을 만들어 검증한다 — Phase 3의
동시성 테스트가 진짜 스레드를 쓴 것과 같은 원칙이다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent_evaluator.rca import ExperimentMetadata, derive_experiment_metadata
from agent_evaluator.rca.experiment_metadata import _extract_commit_sha


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def real_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    (repo / "a.py").write_text("print('v1')\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "initial commit")

    (repo / "a.py").write_text("print('v2')\n")
    (repo / "b.py").write_text("print('new file')\n")
    _git(repo, "add", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "second commit")

    return repo


def _sha(repo: Path, ref: str = "HEAD") -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _report(commit: str) -> dict:
    return {"extra_metrics": {"lineage": {"git_commit": commit}}}


class TestExtractCommitSha:
    def test_prefers_git_commit_field(self):
        assert _extract_commit_sha({"git_commit": "abc123", "agent_version": "def456"}) == "abc123"

    def test_falls_back_to_agent_version_stripping_dirty_suffix(self):
        assert _extract_commit_sha({"agent_version": "abc123-dirty-9f8e"}) == "abc123"

    def test_falls_back_to_bare_agent_version(self):
        assert _extract_commit_sha({"agent_version": "abc123"}) == "abc123"

    def test_none_when_neither_field_present(self):
        assert _extract_commit_sha({}) is None

    def test_none_when_agent_version_is_not_a_string(self):
        assert _extract_commit_sha({"agent_version": None}) is None


class TestDeriveExperimentMetadata:
    def test_resolves_diff_between_two_real_commits(self, real_git_repo: Path):
        commits = subprocess.run(
            ["git", "-C", str(real_git_repo), "log", "--pretty=format:%H", "--reverse"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        first_sha, second_sha = commits[0], commits[1]

        result = derive_experiment_metadata(
            _report(first_sha), _report(second_sha), repo_path=real_git_repo,
        )

        assert isinstance(result, ExperimentMetadata)
        assert result.from_commit == first_sha[:8]
        assert result.to_commit == second_sha[:8]
        assert "a.py" in result.changed_files
        assert "b.py" in result.changed_files
        assert "changed" in result.diff_stat_summary
        assert len(result.commits_between) == 1
        assert result.commits_between[0].subject == "second commit"
        assert result.source == "git"

    def test_changed_files_not_truncated_for_deep_paths(self, real_git_repo: Path):
        """SPEC-041: --stat 출력을 파싱하면 tty가 아닌 서브프로세스에서 git이 폭을
        80으로 잡아 긴 경로를 '...abbrev/'로 잘라버린다. --name-only는 전체 경로를
        잘림 없이 준다."""
        deep = real_git_repo / (
            "src/very/deeply/nested/package/subpackage/module/component"
        )
        deep.mkdir(parents=True)
        long_file = deep / "a_rather_long_filename_that_pushes_past_eighty_columns.py"
        long_file.write_text("x = 1\n")
        _git(real_git_repo, "add", "-A")
        _git(real_git_repo, "commit", "-q", "-m", "add deep file")

        commits = subprocess.run(
            ["git", "-C", str(real_git_repo), "log", "--pretty=format:%H", "--reverse"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        result = derive_experiment_metadata(
            _report(commits[0]), _report(commits[-1]), repo_path=real_git_repo,
        )
        rel = "src/very/deeply/nested/package/subpackage/module/component/" \
              "a_rather_long_filename_that_pushes_past_eighty_columns.py"
        assert result is not None
        assert rel in result.changed_files
        assert all("..." not in f for f in result.changed_files)

    def test_none_when_commits_are_identical(self, real_git_repo: Path):
        sha = _sha(real_git_repo)
        result = derive_experiment_metadata(_report(sha), _report(sha), repo_path=real_git_repo)
        assert result is None

    def test_none_when_lineage_missing_in_either_report(self, real_git_repo: Path):
        sha = _sha(real_git_repo)
        assert derive_experiment_metadata({}, _report(sha), repo_path=real_git_repo) is None
        assert derive_experiment_metadata(_report(sha), {}, repo_path=real_git_repo) is None

    def test_none_when_extra_metrics_missing_entirely(self):
        assert derive_experiment_metadata({}, {}, repo_path=".") is None

    def test_none_when_commit_not_found_in_repo(self, real_git_repo: Path):
        sha = _sha(real_git_repo)
        result = derive_experiment_metadata(
            _report("0" * 40), _report(sha), repo_path=real_git_repo,
        )
        assert result is None

    def test_none_when_repo_path_is_not_a_git_repo(self, tmp_path: Path):
        not_a_repo = tmp_path / "plain_dir"
        not_a_repo.mkdir()
        result = derive_experiment_metadata(
            _report("a" * 40), _report("b" * 40), repo_path=not_a_repo,
        )
        assert result is None

    def test_falls_back_to_agent_version_when_git_commit_absent(self, real_git_repo: Path):
        commits = subprocess.run(
            ["git", "-C", str(real_git_repo), "log", "--pretty=format:%H", "--reverse"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        first_sha, second_sha = commits[0], commits[1]

        before = {"extra_metrics": {"lineage": {"agent_version": first_sha}}}
        after = {"extra_metrics": {"lineage": {"agent_version": f"{second_sha}-dirty-abcd"}}}
        result = derive_experiment_metadata(before, after, repo_path=real_git_repo)

        assert result is not None
        assert result.from_commit == first_sha[:8]
        assert result.to_commit == second_sha[:8]
