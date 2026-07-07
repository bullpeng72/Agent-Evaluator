"""
tests/test_spec027_git_agent_version_tagging.py
==================================================
SPEC-027 REQ-1/2/3: agent_version="auto" sentinel — 이미 캐싱된 self._git_commit(SPEC-007)의
앞 8자를 자동으로 agent_version 태그로 사용하고(REQ-1), 커밋되지 않은 tracked 파일 변경이
있으면(dirty 상태) 그 diff를 해시해 접미사로 붙이며(REQ-2), 최종 해석된 값을 읽기 전용
프로퍼티로 노출한다(REQ-3).
"""
import subprocess as _real_subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent_evaluator import PerformanceMonitor


def _fake_run(clean_diff: bool = True):
    """rev-parse HEAD와 diff HEAD를 명령어로 구분해 서로 다른 결과를 반환하는 side_effect.

    clean_diff=True면 작업 트리가 클린(diff 출력 없음), False면 diff 출력이 있는(dirty) 상태.
    """
    def _run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout="abc123def456\n")
        if "diff" in cmd:
            stdout = "" if clean_diff else "diff --git a/f.py b/f.py\n+changed line\n"
            return MagicMock(returncode=0, stdout=stdout)
        raise AssertionError(f"unexpected git subprocess call: {cmd}")
    return _run


class TestAutoAgentVersionCleanState:
    def test_auto_resolves_to_commit_prefix(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version == "abc123de"  # 앞 8자, dirty 접미사 없음
        assert m._git_commit == "abc123def456"  # git_commit 자체는 여전히 전체 SHA

    def test_auto_reflected_in_lineage(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="auto")
        lineage = m.generate_report().extra_metrics["lineage"]
        assert lineage["agent_version"] == "abc123de"


class TestAutoAgentVersionDirtyState:
    def test_dirty_diff_appends_hash_suffix(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=False)):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version.startswith("abc123de-dirty-")
        assert len(m._agent_version) == len("abc123de-dirty-") + 6  # sha256 앞 6자

    def test_same_dirty_diff_produces_same_tag(self):
        """같은 커밋 + 완전히 동일한 미커밋 변경 → 재현 가능한 동일 태그."""
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=False)):
            m1 = PerformanceMonitor(agent_version="auto")
            m2 = PerformanceMonitor(agent_version="auto")
        assert m1._agent_version == m2._agent_version

    def test_different_dirty_diff_produces_different_tag(self):
        """핵심 케이스 — 같은 커밋에서 서로 다른 미커밋 변경은 서로 다른 태그를 낸다."""
        def _run_variant_a(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n")
            return MagicMock(returncode=0, stdout="diff --git a/f.py b/f.py\n+version A\n")

        def _run_variant_b(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n")
            return MagicMock(
                returncode=0, stdout="diff --git a/f.py b/f.py\n+version B (different)\n",
            )

        with patch("subprocess.run", side_effect=_run_variant_a):
            m_a = PerformanceMonitor(agent_version="auto")
        with patch("subprocess.run", side_effect=_run_variant_b):
            m_b = PerformanceMonitor(agent_version="auto")

        assert m_a._agent_version != m_b._agent_version
        # 둘 다 같은 커밋에서 갈라져 나왔으므로 커밋 prefix는 동일해야 한다
        assert m_a._agent_version.split("-dirty-")[0] == m_b._agent_version.split("-dirty-")[0]

    def test_git_diff_failure_falls_back_to_commit_only_tag(self):
        """git diff 서브프로세스 실패(타임아웃 등) — 커밋-only 태그로 안전 폴백."""
        def _run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="abc123def456\n")
            raise _real_subprocess.TimeoutExpired(cmd="git diff", timeout=2)

        with patch("subprocess.run", side_effect=_run):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version == "abc123de"  # dirty 접미사 없이 안전하게 폴백


class TestAutoAgentVersionGracefulDegradation:
    def test_auto_with_git_not_found_returns_none(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version is None

    def test_auto_with_nonzero_returncode_returns_none(self):
        """비-git 디렉토리 등 — git rev-parse HEAD가 실패 코드를 반환하는 경우.

        git_commit 자체가 없으므로 dirty-diff 분기(REQ-2)로 진입조차 하지 않는다
        (monitor.py의 ``if self._git_commit is None:`` 가드가 앞서 처리).
        """
        with patch("subprocess.run", return_value=MagicMock(returncode=128, stdout="")):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version is None

    def test_auto_with_timeout_returns_none(self):
        _timeout = _real_subprocess.TimeoutExpired(cmd="git", timeout=2)
        with patch("subprocess.run", side_effect=_timeout):
            m = PerformanceMonitor(agent_version="auto")
        assert m._agent_version is None


class TestAutoAgentVersionRegressionSafety:
    """"auto"가 아닌 기존 사용법은 100% 그대로 — 회귀 없음."""

    def test_literal_string_unaffected(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="v2-cot")
        assert m._agent_version == "v2-cot"

    def test_none_default_unaffected(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor()
        assert m._agent_version is None

    def test_empty_string_not_treated_as_auto(self):
        """빈 문자열은 "auto"가 아니므로 그대로 유지된다 — sentinel 매칭은 정확히 "auto"만."""
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="")
        assert m._agent_version == ""


class TestAgentVersionReadOnlyProperty:
    """SPEC-027 REQ-3: 최종 해석된 agent_version을 읽기 전용 프로퍼티로 노출."""

    def test_property_returns_literal_string(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="v2-cot")
        assert m.agent_version == "v2-cot"

    def test_property_returns_none_by_default(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor()
        assert m.agent_version is None

    def test_property_reflects_auto_resolution_clean(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="auto")
        assert m.agent_version == m._agent_version == "abc123de"

    def test_property_reflects_auto_resolution_dirty(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=False)):
            m = PerformanceMonitor(agent_version="auto")
        assert m.agent_version == m._agent_version
        assert m.agent_version.startswith("abc123de-dirty-")

    def test_property_has_no_setter(self):
        with patch("subprocess.run", side_effect=_fake_run(clean_diff=True)):
            m = PerformanceMonitor(agent_version="v2-cot")
        with pytest.raises(AttributeError):
            m.agent_version = "v3-something"
