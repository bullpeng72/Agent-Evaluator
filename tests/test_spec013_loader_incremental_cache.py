"""
tests/test_spec013_loader_incremental_cache.py
==================================================
SPEC-013: 대시보드 로더 증분 캐싱 (watch 모드 요청당 전량 재파싱 제거) 검증.

REQ-1: ResultFile.mtime 필드 기록.
REQ-2: load_results(results_dir, previous=...) 증분 캐싱.
REQ-3/4: routers/data.py::list_results() / server.py::reload_results()가
         previous=기존 result_set을 전달하도록 배선.
REQ-5: previous 생략 시 기존 동작과 100% 동일(하위호환).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

import pytest

from agent_evaluator.serve import loader as loader_module
from agent_evaluator.serve.loader import load_results, parse_file


def _write_result_file(dir_path: Path, name: str, tcr: float = 90.0) -> Path:
    p = dir_path / f"{name}.json"
    p.write_text(
        json.dumps({
            "timestamp": "2026-07-02T00:00:00",
            "total_tasks": 1,
            "tasks": [{"task_id": name}],
            "accuracy_metrics": {"tcr": {"tcr": tcr}},
        }),
        encoding="utf-8",
    )
    return p


@pytest.fixture
def results_dir(tmp_path):
    for i in range(5):
        _write_result_file(tmp_path, f"r{i}")
    return tmp_path


class TestResultFileMtime:
    def test_parse_file_records_mtime(self, tmp_path):
        p = _write_result_file(tmp_path, "a")
        rf = parse_file(p)
        assert rf.mtime == pytest.approx(p.stat().st_mtime)

    def test_default_mtime_is_zero(self):
        """ResultFile을 mtime 없이(키워드 생략) 생성해도 기본값 0.0으로 안전하게 초기화된다."""
        from agent_evaluator.serve.loader import ResultFile
        import inspect
        sig = inspect.signature(ResultFile)
        assert sig.parameters["mtime"].default == 0.0


class TestLoadResultsIncrementalCache:
    def test_previous_omitted_behaves_like_before(self, results_dir):
        """REQ-5: previous 생략 시 기존 동작과 100% 동일 — 모든 파일이 파싱된다."""
        rs = load_results(results_dir)
        assert len(rs.files) == 5

    def test_no_changes_skips_all_reparsing(self, results_dir):
        """Acceptance: 변경이 전혀 없으면 두 번째 호출에서 parse_file()이 0회 호출되어야 한다."""
        rs1 = load_results(results_dir)
        with mock.patch.object(loader_module, "parse_file", wraps=parse_file) as spy:
            rs2 = load_results(results_dir, previous=rs1)
            assert spy.call_count == 0
        assert len(rs2.files) == 5

    def test_one_modified_file_triggers_single_reparse(self, results_dir):
        """Acceptance: 100개 중 1개만 수정하면 parse_file()이 정확히 1회만 호출되어야 한다."""
        rs1 = load_results(results_dir)
        # mtime 해상도(일부 파일시스템 1초 단위) 이슈를 피하기 위해 명시적으로 미래 시각 지정
        target = results_dir / "r2.json"
        _write_result_file(results_dir, "r2", tcr=50.0)
        _future = time.time() + 5
        import os
        os.utime(target, (_future, _future))

        with mock.patch.object(loader_module, "parse_file", wraps=parse_file) as spy:
            rs2 = load_results(results_dir, previous=rs1)
            assert spy.call_count == 1
            assert spy.call_args[0][0] == target
        # 변경된 파일의 내용이 실제로 갱신됐는지 확인
        updated = next(f for f in rs2.files if f.path == target)
        assert updated.tcr == 50.0

    def test_new_file_added_only_new_file_parsed(self, results_dir):
        """Acceptance: 새 파일 1개 추가 시 해당 파일만 파싱되고 나머지는 캐시 재사용."""
        rs1 = load_results(results_dir)
        _write_result_file(results_dir, "r_new")

        with mock.patch.object(loader_module, "parse_file", wraps=parse_file) as spy:
            rs2 = load_results(results_dir, previous=rs1)
            assert spy.call_count == 1
        assert len(rs2.files) == 6

    def test_deleted_file_excluded_from_results(self, results_dir):
        """Acceptance: 파일 삭제 시 결과에서 제외된다."""
        rs1 = load_results(results_dir)
        (results_dir / "r3.json").unlink()

        rs2 = load_results(results_dir, previous=rs1)
        assert len(rs2.files) == 4
        assert not any(f.path.name == "r3.json" for f in rs2.files)

    def test_cached_result_file_object_identity_reused(self, results_dir):
        """변경되지 않은 파일은 새 ResultFile을 만들지 않고 캐시된 객체를 그대로 재사용해야 한다."""
        rs1 = load_results(results_dir)
        rs2 = load_results(results_dir, previous=rs1)
        cached_by_path = {f.path: f for f in rs1.files}
        for f in rs2.files:
            assert f is cached_by_path[f.path]


class TestServerAndRouterIntegration:
    def test_reload_results_passes_previous(self, results_dir):
        """server.py::reload_results()가 previous=기존 result_set을 전달하는지 확인."""
        from types import SimpleNamespace
        from agent_evaluator.serve import server as server_module

        original_result_set = load_results(results_dir)
        app = SimpleNamespace(state=SimpleNamespace(
            results_dir=results_dir, result_set=original_result_set,
        ))
        with mock.patch.object(
            server_module, "load_results", wraps=load_results
        ) as spy:
            server_module.reload_results(app)
            spy.assert_called_once()
            _, kwargs = spy.call_args
            assert kwargs.get("previous") is original_result_set

    def test_list_results_endpoint_skips_reparse_when_unchanged(self, results_dir):
        """Acceptance: watch 모드에서 연속 2회 요청 사이에 변경이 없으면 두 번째 요청에서
        parse_file이 호출되지 않아야 한다."""
        from agent_evaluator.serve.server import create_app
        from fastapi.testclient import TestClient

        app = create_app(results_dir=results_dir, watch=True)
        with TestClient(app) as client:
            r1 = client.get("/api/results")
            assert r1.status_code == 200
            with mock.patch.object(loader_module, "parse_file", wraps=parse_file) as spy:
                r2 = client.get("/api/results")
                assert r2.status_code == 200
                assert spy.call_count == 0
