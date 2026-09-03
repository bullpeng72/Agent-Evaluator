"""
tests/test_compare_html_export.py
====================================
비교 결과(SPEC-025 REQ-2/5 group_by/pairwise)를 self-contained HTML 리포트로
내보내는 기능 — generate_comparison_html_report() + GET /api/export/html/compare.
"""
from __future__ import annotations

import pytest

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.reporting.comprehensive_report import generate_comparison_html_report

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# generate_comparison_html_report() — 순수 렌더링 단위 테스트
# ---------------------------------------------------------------------------

class TestGenerateComparisonHtmlReport:
    def _base_result(self, **overrides):
        result = {
            "file_count": 2,
            "files": [
                {"file_id": "f1", "name": "run_a", "found": True, "total_tasks": 10,
                 "tcr": 90.0, "accuracy": 85.0, "avg_latency": 1.2, "total_cost": 0.01},
                {"file_id": "f2", "name": "run_b", "found": True, "total_tasks": 10,
                 "tcr": 80.0, "accuracy": 75.0, "avg_latency": 1.5, "total_cost": 0.02},
            ],
            "delta": [{"vs": "f2", "tcr_delta": 10.0, "accuracy_delta": 10.0, "latency_delta": -0.3}],
        }
        result.update(overrides)
        return result

    def test_basic_metric_table_renders(self):
        html = generate_comparison_html_report(self._base_result())
        assert "run_a" in html
        assert "run_b" in html
        assert "90.0%" in html
        assert "<!DOCTYPE html>" in html

    def test_no_files_found_does_not_crash(self):
        html = generate_comparison_html_report({"file_count": 0, "files": [], "delta": []})
        assert "No files found" in html
        assert "</html>" in html

    def test_delta_section_rendered(self):
        html = generate_comparison_html_report(self._base_result())
        assert "vs f2" in html
        assert "+10.00%" in html

    def test_detailed_regression_improvement_rendered(self):
        result = self._base_result(detailed={
            "common_task_count": 5, "only_in_first": 1, "only_in_second": 2,
        }, regression_tasks=[
            {"task_id": "t1", "task_type": "qa", "accuracy_delta": -0.2, "latency_delta": 0.1},
        ], improvement_tasks=[
            {"task_id": "t2", "task_type": "qa", "accuracy_delta": 0.3, "latency_delta": -0.1},
        ])
        html = generate_comparison_html_report(result)
        assert "Regressions (1)" in html
        assert "Improvements (1)" in html
        assert "t1" in html and "t2" in html

    def test_pairwise_section_rendered(self):
        result = self._base_result(pairwise={
            "judged_count": 3, "wins_a": 2, "wins_b": 1, "ties": 0, "win_rate": 0.6667,
            "per_task": [{"task_id": "t1", "winner": "a", "reasoning": "more complete"}],
        })
        html = generate_comparison_html_report(result)
        assert "Pairwise LLM Judge" in html
        assert "66.7%" in html
        assert "more complete" in html

    def test_no_pairwise_key_omits_section(self):
        html = generate_comparison_html_report(self._base_result())
        assert "Pairwise LLM Judge" not in html

    def test_html_escapes_malicious_task_content(self):
        """task_id/reasoning 등 사용자 생성 텍스트에 HTML/script가 섞여도 이스케이프되어야 한다."""
        result = self._base_result(pairwise={
            "judged_count": 1, "wins_a": 1, "wins_b": 0, "ties": 0, "win_rate": 1.0,
            "per_task": [{"task_id": "<script>alert(1)</script>", "winner": "a", "reasoning": "<b>x</b>"}],
        })
        html = generate_comparison_html_report(result)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.parametrize("result", [
        # null-valued delta fields — a bare f"{None:+.2f}" would TypeError
        {"files": [{"found": True, "name": "a", "tcr": 80.0}],
         "delta": [{"vs": "b", "tcr_delta": None, "accuracy_delta": None, "latency_delta": None}]},
        # null-valued per-task delta in the detail section
        {"files": [{"found": True, "name": "a"}], "detailed": {"common_task_count": None},
         "regression_tasks": [{"task_id": "t1", "accuracy_delta": None, "latency_delta": None}]},
        # a metric value arriving as a string — f"{'x':.1f}" would ValueError
        {"files": [{"found": True, "name": "a", "tcr": "88.5", "total_tasks": "10",
                    "accuracy": None, "avg_latency": None, "total_cost": None}]},
        # containers that are not lists / not dicts
        {"files": "oops"},
        {"files": [{"found": True, "name": "a"}], "delta": {"x": 1}, "detailed": "nope",
         "regression_tasks": ["x", None, 5], "pairwise": "nope"},
        {"files": None, "delta": None, "detailed": None, "regression_tasks": None,
         "improvement_tasks": None, "pairwise": None},
    ])
    def test_malformed_compare_result_never_crashes(self, result):
        html = generate_comparison_html_report(result)
        assert html.lstrip().startswith("<")
        assert "</html>" in html


# ---------------------------------------------------------------------------
# GET /api/export/html/compare — TestClient 통합 테스트
# ---------------------------------------------------------------------------

def _write_run(results_dir, filename, *, prompt_version=None, tcr_tasks=3):
    monitor = PerformanceMonitor(output_dir=str(results_dir), prompt_version=prompt_version)
    for i in range(tcr_tasks):
        monitor.record_task(create_taskresult(
            task_id=f"{filename}_t{i}", question=f"q{i}", response=f"r{i}", execution_time=1.0,
        ))
    monitor.save_to_file(filename)


@pytest.fixture(scope="module")
def compare_results_dir(tmp_path_factory: pytest.TempPathFactory):
    d = tmp_path_factory.mktemp("compare_export_data")
    _write_run(d, "run_v1", prompt_version="v1-few-shot")
    _write_run(d, "run_v2", prompt_version="v2-cot")
    return d


@pytest.fixture(scope="module")
def compare_client(compare_results_dir) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=compare_results_dir, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


def _file_ids(compare_client: TestClient) -> dict:
    r = compare_client.get("/api/results")
    data = r.json()
    return {f["name"]: f["id"] for f in data["files"]}


@pytest.fixture(scope="module")
def pairwise_results_dir(tmp_path_factory: pytest.TempPathFactory):
    """run_v1/run_v2 픽스처와 달리, 두 파일이 동일한 task_id를 공유하도록 만든다 —
    compare_client 픽스처(_write_run)는 task_id에 파일명을 접두해 두 파일이 절대
    겹치지 않으므로, pairwise=True를 의미 있게(judged_count > 0) 검증하려면
    별도 픽스처가 필요하다."""
    d = tmp_path_factory.mktemp("pairwise_export_data")
    for filename, prompt_version in (("pw_v1", "v1-baseline"), ("pw_v2", "v2-detailed")):
        monitor = PerformanceMonitor(output_dir=str(d), prompt_version=prompt_version)
        for i in range(2):
            monitor.record_task(create_taskresult(
                task_id=f"shared_t{i}", question=f"q{i}", response=f"{filename}_r{i}",
                execution_time=1.0,
            ))
        monitor.save_to_file(filename)
    return d


@pytest.fixture(scope="module")
def pairwise_client(pairwise_results_dir) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=pairwise_results_dir, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


class TestExportHtmlCompareEndpoint:
    def test_compare_by_ids_returns_html(self, compare_client: TestClient):
        ids = _file_ids(compare_client)
        r = compare_client.get(f"/api/export/html/compare?ids={ids['run_v1']},{ids['run_v2']}")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        assert "run_v1" in r.text
        assert "run_v2" in r.text

    def test_compare_by_group_by_returns_html(self, compare_client: TestClient):
        r = compare_client.get("/api/export/html/compare?group_by=prompt_version")
        assert r.status_code == 200
        assert "run_v1" in r.text
        assert "run_v2" in r.text

    def test_route_not_shadowed_by_file_id_route(self, compare_client: TestClient):
        """'/html/compare'가 '/html/{file_id}'에 삼켜지지 않고 비교 리포트로 라우팅돼야 한다."""
        ids = _file_ids(compare_client)
        r = compare_client.get(f"/api/export/html/compare?ids={ids['run_v1']},{ids['run_v2']}")
        assert r.status_code == 200
        # file_id 라우트로 잘못 갔다면 file_id="compare"가 404를 냈을 것
        assert "Result Comparison Report" in r.text

    def test_missing_ids_and_group_by_returns_400_not_500(self, compare_client: TestClient):
        r = compare_client.get("/api/export/html/compare")
        assert r.status_code == 400

    def test_single_file_export_html_still_works(self, compare_client: TestClient):
        """기존 단일 파일 HTML export가 회귀 없이 그대로 동작하는지 확인."""
        ids = _file_ids(compare_client)
        r = compare_client.get(f"/api/export/html/{ids['run_v1']}")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]

    def test_pairwise_true_end_to_end_renders_win_rate(self, pairwise_client: TestClient):
        """export_html_compare()가 pairwise=True를 compare_results()에 실제로 전달하고,
        그 결과의 win_rate/per_task가 HTML에 그대로 렌더링되는지 엔드투엔드로 확인
        (judge_pairwise()만 모킹 — 나머지는 전부 실제 라우팅/집계 경로)."""
        from unittest.mock import patch

        from agent_evaluator import LLMJudge

        ids = _file_ids(pairwise_client)
        with patch.object(
            LLMJudge, "judge_pairwise",
            lambda self, *a, **kw: {"skipped": False, "winner": "b", "reasoning": "more detailed", "cost_usd": 0.0},
        ):
            r = pairwise_client.get(
                f"/api/export/html/compare?ids={ids['pw_v1']},{ids['pw_v2']}&pairwise=true",
            )
        assert r.status_code == 200
        assert "Pairwise LLM Judge" in r.text
        assert "more detailed" in r.text
        assert "2 common task(s) judged" in r.text
        # winner="b" 2건 모두 → win_rate(첫 파일 기준) = 0.0
        assert "0.0%" in r.text
