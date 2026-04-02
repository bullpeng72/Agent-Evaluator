"""
tests/test_serve_routers.py
===========================
Smoke tests for all 12 serve/routers using FastAPI TestClient.

Guards:
- pytest.importorskip("fastapi") — skips entire module if [serve] extras not installed
- pytest.importorskip("httpx")   — starlette TestClient depends on httpx

Each test asserts the response status code is NOT 500
(or the exact expected code for known 404/422 paths with no data).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def results_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Empty results directory — no JSON files."""
    return tmp_path_factory.mktemp("results")


@pytest.fixture(scope="module")
def results_dir_with_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Results directory with one minimal evaluation JSON."""
    d = tmp_path_factory.mktemp("results_data")
    payload = {
        "report": {
            "total_tasks": 2,
            "successful_tasks": 2,
            "task_completion_rate": 1.0,
            "accuracy_metrics": {},
            "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0},
            "token_metrics": {"total_tokens": 100, "total_cost": 0.001},
            "quality_metrics": {},
            "agentic_metrics": {},
            "security_metrics": {},
        },
        "tasks": [
            {
                "task_id": "t1",
                "task_type": "qa",
                "success": True,
                "completion_score": 1.0,
                "accuracy_score": 0.9,
                "execution_time": 1.0,
                "tokens_used": 50,
                "tool_calls": [],
                "attempts": 1,
                "errors": [],
                "timestamp": "2026-01-01T00:00:00",
            }
        ],
        "metadata": {"version": "0.7.0", "name": "test_eval"},
    }
    (d / "test_eval.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


@pytest.fixture(scope="module")
def client_empty(results_dir: Path) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=results_dir, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client(results_dir_with_data: Path) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=results_dir_with_data, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

class TestHTMLPages:
    def test_dashboard_root(self, client: TestClient):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_slides_page(self, client: TestClient):
        r = client.get("/slides")
        assert r.status_code not in (500,)

    def test_sdk_docs_page(self, client: TestClient):
        r = client.get("/sdk-docs")
        assert r.status_code not in (500,)


# ---------------------------------------------------------------------------
# data router  (/api/...)
# ---------------------------------------------------------------------------

class TestDataRouter:
    def test_health(self, client: TestClient):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_results_list_empty(self, client_empty: TestClient):
        r = client_empty.get("/api/results")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_results_list_with_data(self, client: TestClient):
        r = client.get("/api/results")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_results_detail_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/results/nonexistent_id")
        assert r.status_code == 404

    def test_results_detail_found(self, client: TestClient):
        # Get the first file_id from the list
        files = client.get("/api/results").json()
        if not files:
            pytest.skip("no result files loaded")
        file_id = files[0]["id"]
        r = client.get(f"/api/results/{file_id}")
        assert r.status_code == 200

    def test_summary(self, client: TestClient):
        r = client.get("/api/summary")
        assert r.status_code not in (500,)


# ---------------------------------------------------------------------------
# config router  (/api/thresholds, /api/config)
# ---------------------------------------------------------------------------

class TestConfigRouter:
    def test_get_thresholds(self, client: TestClient):
        r = client.get("/api/thresholds")
        assert r.status_code == 200

    def test_get_config(self, client: TestClient):
        r = client.get("/api/config")
        assert r.status_code == 200

    def test_post_thresholds(self, client: TestClient):
        payload = {"tcr": 80.0, "accuracy": 70.0}
        r = client.post("/api/thresholds", json=payload)
        assert r.status_code not in (500,)


# ---------------------------------------------------------------------------
# alerts router  (/api/alerts/...)
# ---------------------------------------------------------------------------

class TestAlertsRouter:
    def test_alerts_list(self, client: TestClient):
        r = client.get("/api/alerts")
        assert r.status_code == 200

    def test_alerts_today(self, client: TestClient):
        r = client.get("/api/alerts/today")
        assert r.status_code == 200

    def test_alerts_summary(self, client: TestClient):
        r = client.get("/api/alerts/summary")
        assert r.status_code == 200

    def test_alerts_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/alerts/file/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# anomaly router  (/api/anomalies/...)
# ---------------------------------------------------------------------------

class TestAnomalyRouter:
    def test_anomalies_list(self, client: TestClient):
        r = client.get("/api/anomalies")
        assert r.status_code == 200

    def test_anomaly_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/anomalies/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# conversation router  (/api/conversation/...)
# ---------------------------------------------------------------------------

class TestConversationRouter:
    def test_conversation_list(self, client: TestClient):
        r = client.get("/api/conversation")
        assert r.status_code == 200

    def test_conversation_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/conversation/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# cost router  (/api/cost/...)
# ---------------------------------------------------------------------------

class TestCostRouter:
    def test_cost_summary(self, client: TestClient):
        r = client.get("/api/cost/summary")
        assert r.status_code == 200

    def test_cost_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/cost/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# feedback router  (/api/feedback/...)
# ---------------------------------------------------------------------------

class TestFeedbackRouter:
    def test_feedback_list(self, client: TestClient):
        r = client.get("/api/feedback")
        assert r.status_code == 200

    def test_feedback_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/feedback/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# stream router  (/api/stream/...)
# ---------------------------------------------------------------------------

class TestStreamRouter:
    def test_stream_live_stats(self, client: TestClient):
        r = client.get("/api/stream/live-stats")
        assert r.status_code not in (500,)

    def test_stream_snapshot_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/stream/snapshot/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# export router  (/api/export/...)
# ---------------------------------------------------------------------------

class TestExportRouter:
    def _first_file_id(self, client: TestClient) -> str:
        files = client.get("/api/results").json()
        if not files:
            pytest.skip("no result files loaded")
        return files[0]["id"]

    def test_export_json_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/export/json/nonexistent")
        assert r.status_code == 404

    def test_export_json_found(self, client: TestClient):
        file_id = self._first_file_id(client)
        r = client.get(f"/api/export/json/{file_id}")
        assert r.status_code == 200

    def test_export_csv_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/export/csv/nonexistent")
        assert r.status_code == 404

    def test_export_csv_found(self, client: TestClient):
        file_id = self._first_file_id(client)
        r = client.get(f"/api/export/csv/{file_id}")
        assert r.status_code == 200

    def test_export_html_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/export/html/nonexistent")
        assert r.status_code == 404

    def test_export_html_found(self, client: TestClient):
        file_id = self._first_file_id(client)
        r = client.get(f"/api/export/html/{file_id}")
        assert r.status_code not in (500,)


# ---------------------------------------------------------------------------
# golden router  (/api/golden/...)
# ---------------------------------------------------------------------------

class TestGoldenRouter:
    def test_golden_list(self, client: TestClient):
        r = client.get("/api/golden")
        assert r.status_code == 200

    def test_golden_candidates(self, client: TestClient):
        r = client.get("/api/golden/candidates")
        assert r.status_code == 200

    def test_golden_versions(self, client: TestClient):
        r = client.get("/api/golden/versions")
        assert r.status_code == 200

    def test_golden_name_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/golden/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# transparency router  (/api/transparency/...)
# ---------------------------------------------------------------------------

class TestTransparencyRouter:
    def test_traces_list(self, client: TestClient):
        r = client.get("/api/transparency/traces")
        assert r.status_code == 200

    def test_audit_list(self, client: TestClient):
        r = client.get("/api/transparency/audit")
        assert r.status_code == 200

    def test_annotations_list(self, client: TestClient):
        r = client.get("/api/transparency/annotations")
        assert r.status_code == 200

    def test_traces_name_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/transparency/traces/nonexistent")
        assert r.status_code in (200, 404)

    def test_audit_name_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/transparency/audit/nonexistent")
        assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# webhook router  (/api/webhook/...)
# ---------------------------------------------------------------------------

class TestWebhookRouter:
    def test_webhook_test(self, client: TestClient):
        r = client.post("/api/webhook/test", json={"url": "http://localhost:9999/hook"})
        # May fail if target unreachable — 200 or 4xx acceptable, never 500
        assert r.status_code not in (500,)
