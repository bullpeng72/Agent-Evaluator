"""
tests/test_export_html_baseline_route.py
===========================================
Phase 2(개선 엔진의 정적 HTML 리포트 반영) — GET /api/export/html/{file_id}?baseline_id=
의 회귀 테스트. `tests/test_phase8_diagnose_router.py`(같은 baseline_id 쌍 패턴)와
`tests/test_report_diagnosis_section.py`(_build_diagnosis() 자체 단위 테스트)의
중간 지점 — 대시보드 "Export HTML" 버튼이 실제로 baseline_id를 받아
회귀 기반 진단을 포함한 HTML을 반환하는지 라우터 레벨에서 확인한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent_evaluator.serve.server import create_app  # noqa: E402


def _result_payload(*, gate_a_score: float, task_id: str = "t1") -> dict:
    return {
        "report": {
            "total_tasks": 1, "successful_tasks": 1, "task_completion_rate": 1.0,
            "accuracy_metrics": {},
            "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
            "token_metrics": {"total_tokens": 10, "total_cost": 0.001},
            "quality_metrics": {}, "agentic_metrics": {}, "security_metrics": {},
        },
        "tasks": [{
            "task_id": task_id, "task_type": "qa", "success": True,
            "completion_score": 1.0, "accuracy_score": 0.9, "execution_time": 1.0,
            "tokens_used": 10, "tool_calls": [], "attempts": 1, "errors": [],
            "timestamp": "2026-01-01T00:00:00",
        }],
        "extra_metrics": {
            "harness_groups": {
                "A": {
                    "score": gate_a_score, "status": "pass" if gate_a_score >= 0.7 else "fail",
                    "gate": "pass" if gate_a_score >= 0.7 else "fail",
                    "details": {"avg_plan_coherence": gate_a_score, "tcr_pct": 90.0},
                },
            },
        },
        "metadata": {"version": "0.9.13", "name": "test_eval"},
    }


@pytest.fixture(scope="module")
def results_dir_with_regression(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("results_export_baseline")
    (d / "baseline.json").write_text(
        json.dumps(_result_payload(gate_a_score=0.9, task_id="b1")), encoding="utf-8",
    )
    (d / "current.json").write_text(
        json.dumps(_result_payload(gate_a_score=0.4, task_id="c1")), encoding="utf-8",
    )
    return d


@pytest.fixture(scope="module")
def client(results_dir_with_regression: Path) -> TestClient:
    app = create_app(results_dir=results_dir_with_regression, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


def _file_id(client: TestClient, name: str) -> str:
    r = client.get("/api/results")
    for f in r.json()["files"]:
        if f["name"] == name or name in f["name"]:
            file_id: str = f["id"]
            return file_id
    raise AssertionError(f"file '{name}' not found in /api/results: {r.json()}")


class TestExportHtmlWithoutBaseline:
    def test_absolute_threshold_mode_and_backward_compatible(self, client: TestClient):
        current_id = _file_id(client, "current")
        r = client.get(f"/api/export/html/{current_id}")
        assert r.status_code == 200
        assert "Absolute-threshold detection" in r.text
        assert "Regression-based detection" not in r.text


class TestExportHtmlWithBaseline:
    def test_regression_mode_activated(self, client: TestClient):
        current_id = _file_id(client, "current")
        baseline_id = _file_id(client, "baseline")
        r = client.get(f"/api/export/html/{current_id}", params={"baseline_id": baseline_id})
        assert r.status_code == 200
        assert "Regression-based detection" in r.text

    def test_nonexistent_baseline_id_returns_404(self, client: TestClient):
        current_id = _file_id(client, "current")
        r = client.get(
            f"/api/export/html/{current_id}", params={"baseline_id": "nonexistent"},
        )
        assert r.status_code == 404
