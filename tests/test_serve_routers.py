"""
tests/test_serve_routers.py
===========================
Smoke tests for all 13 serve/routers using FastAPI TestClient.

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

    def test_dashboard2_page(self, client: TestClient):
        """/dashboard는 dashboard2.html.j2(유일한 대시보드 템플릿)를 렌더링한다.
        Phase 8에서 Improve 탭을 추가하며 이 라우트 직접 렌더링 테스트를 신설."""
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "s-improve" in r.text
        assert "loadImproveDiagnosis" in r.text


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
        # B12: 응답이 페이지네이션 dict 형태로 변경됨
        assert isinstance(data, dict)
        assert "files" in data
        assert isinstance(data["files"], list)
        assert "total" in data

    def test_results_list_with_data(self, client: TestClient):
        r = client.get("/api/results")
        assert r.status_code == 200
        data = r.json()
        # B12: 페이지네이션 dict 형태
        assert isinstance(data, dict)
        assert "files" in data
        assert len(data["files"]) >= 1

    def test_results_detail_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/results/nonexistent_id")
        assert r.status_code == 404

    def test_results_detail_found(self, client: TestClient):
        # Get the first file_id from the list (B12: files is nested under 'files' key)
        resp = client.get("/api/results").json()
        files = resp.get("files", resp) if isinstance(resp, dict) else resp
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


@pytest.fixture(scope="module")
def client_with_anomaly(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    from agent_evaluator.serve.server import create_app

    d = tmp_path_factory.mktemp("results_anomaly")
    payload = {
        "report": {"total_tasks": 1, "successful_tasks": 1, "task_completion_rate": 1.0,
                   "latency_metrics": {"mean": 1.0, "p50": 1.0, "p95": 1.5, "p99": 2.0}},
        "tasks": [{"task_id": "t1", "task_type": "qa", "success": True,
                   "completion_score": 1.0, "accuracy_score": 0.9, "execution_time": 1.0,
                   "tokens_used": 50, "tool_calls": [], "attempts": 1, "errors": [],
                   "timestamp": "2026-01-01T00:00:00"}],
        "anomaly_data": {"anomalies": [{
            "event_id": "latency_trend-abc12345", "type": "latency_trend",
            "metric": "latency_trend", "severity": "critical",
            "detail": "p95 up 40%", "value": 0.12, "threshold": 0.05,
            "detected_at": "2026-01-01T00:00:00", "algorithm": "linear_regression",
        }]},
        "metadata": {"version": "0.7.0", "name": "anom_eval"},
    }
    (d / "anom_eval.json").write_text(json.dumps(payload), encoding="utf-8")
    app = create_app(results_dir=d, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


class TestAnomalyExplainEndpoint:
    """SPEC-041: explain 엔드포인트가 살아났는지 — 예전엔 저장된 AnomalyEvent에
    event_id/metric 키가 없어 항상 404 아니면 metric='unknown'이었다."""

    @staticmethod
    def _file_id(c: TestClient) -> str:
        return c.get("/api/results").json()["files"][0]["id"]

    def test_explain_resolves_event_and_returns_real_suggestion(self, client_with_anomaly):
        c = client_with_anomaly
        fid = self._file_id(c)
        r = c.get(f"/api/results/{fid}/anomaly/explain/latency_trend-abc12345")
        assert r.status_code == 200
        body = r.json()
        assert body["metric"] == "latency_trend"
        assert body["suggested_action"] != "Analyze this metric in detail."
        assert "trending up" in body["suggested_action"]

    def test_unknown_event_id_is_404(self, client_with_anomaly):
        c = client_with_anomaly
        fid = self._file_id(c)
        r = c.get(f"/api/results/{fid}/anomaly/explain/no-such-event")
        assert r.status_code == 404


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
        resp = client.get("/api/results").json()
        # B12: 응답이 페이지네이션 dict 형태로 변경됨
        files = resp.get("files", resp) if isinstance(resp, dict) else resp
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


# ---------------------------------------------------------------------------
# diagnose router  (/api/diagnose/...) — Phase 8 "Improve" 탭 백엔드
# ---------------------------------------------------------------------------

class TestDiagnoseRouter:
    def test_diagnosis_found(self, client: TestClient):
        r = client.get("/api/results")
        file_id = r.json()["files"][0]["id"] if r.json().get("files") else None
        if file_id is None:
            pytest.skip("no result file id available from /api/results")
        r = client.get(f"/api/diagnose/{file_id}")
        assert r.status_code == 200
        body = r.json()
        assert "detection_mode" in body
        assert "findings" in body

    def test_diagnosis_file_not_found(self, client_empty: TestClient):
        r = client_empty.get("/api/diagnose/nonexistent")
        assert r.status_code == 404

    def test_recommendations_empty_when_no_log_file(self, client: TestClient):
        r = client.get("/api/diagnose/")
        assert r.status_code == 200
        body = r.json()
        assert body["outcomes"] == []
        assert body["summary"]["total"] == 0

    def test_recommendation_outcomes_ok_with_str_results_dir(self, tmp_path):
        """SPEC-041: 프로그래매틱 호출자가 create_app(results_dir=<str>)로 만들어도
        recommendation_outcomes 엔드포인트가 `str / str` 로 500 나지 않는다."""
        from agent_evaluator.serve.server import create_app

        app = create_app(results_dir=str(tmp_path), watch=False, offline=False)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/api/diagnose/")
        assert r.status_code == 200
        assert r.json()["summary"]["total"] == 0
