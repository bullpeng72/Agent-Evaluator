"""
tests/test_phase8_diagnose_router.py
=======================================
Phase 8(개선 엔진, 대시보드 "Improve" 탭 백엔드) — agent_evaluator/serve/routers/diagnose.py
의 회귀 테스트. 실제 harness_groups 회귀 데이터·추천 이력 로그를 갖춘 전용 fixture로
diagnose()/recommendation-tracking 연동이 대시보드 경로에서도 CLI와 동일하게 동작하는지
확인한다(tests/test_serve_routers.py의 스모크 테스트와 별개 — 여기는 실제 응답 내용을 검증).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent_evaluator.rca.recommendation_tracking import record_recommendation_outcome  # noqa: E402
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
    d = tmp_path_factory.mktemp("results_diag")
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


class TestDiagnosisWithoutBaseline:
    def test_absolute_threshold_detects_failing_gate(self, client: TestClient):
        current_id = _file_id(client, "current")
        r = client.get(f"/api/diagnose/{current_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["detection_mode"] == "absolute_threshold"
        assert "A" in body["detected_gates"]
        assert body["file_id"] == current_id
        assert body["baseline_id"] is None


class TestDiagnosisWithBaseline:
    def test_regression_detected_and_finding_populated(self, client: TestClient):
        current_id = _file_id(client, "current")
        baseline_id = _file_id(client, "baseline")
        r = client.get(f"/api/diagnose/{current_id}", params={"baseline_id": baseline_id})
        assert r.status_code == 200
        body = r.json()
        assert body["detection_mode"] == "regression_vs_baseline"
        assert body["detected_gates"] == ["A"]
        finding = body["findings"][0]
        assert finding["gate"] == "A"
        assert finding["current_score"] == 0.4
        assert finding["baseline_score"] == 0.9
        assert any(d["field"] == "avg_plan_coherence" for d in finding["top_detail_deltas"])

    def test_baseline_not_found_returns_404(self, client: TestClient):
        current_id = _file_id(client, "current")
        r = client.get(f"/api/diagnose/{current_id}", params={"baseline_id": "nonexistent"})
        assert r.status_code == 404

    def test_show_diff_false_by_default_omits_experiment_metadata(self, client: TestClient):
        current_id = _file_id(client, "current")
        baseline_id = _file_id(client, "baseline")
        r = client.get(f"/api/diagnose/{current_id}", params={"baseline_id": baseline_id})
        assert r.json()["experiment_metadata"] is None

    def test_show_diff_true_does_not_error_without_git_lineage(self, client: TestClient):
        current_id = _file_id(client, "current")
        baseline_id = _file_id(client, "baseline")
        r = client.get(
            f"/api/diagnose/{current_id}",
            params={"baseline_id": baseline_id, "show_diff": "true"},
        )
        assert r.status_code == 200
        # 이 fixture 데이터엔 lineage.git_commit이 없으므로 조용히 None이어야 한다.
        assert r.json()["experiment_metadata"] is None


class TestRecommendationOutcomesEndpoint:
    def test_empty_when_no_log_file_written_yet(self, client: TestClient):
        r = client.get("/api/diagnose/")
        assert r.status_code == 200
        assert r.json() == {
            "outcomes": [],
            "summary": {"total": 0, "confirmed": 0, "refuted": 0, "inconclusive": 0, "by_gate": {}},
        }

    def test_reads_recorded_outcomes(self, results_dir_with_regression: Path):
        # 별도 앱 인스턴스 — 모듈 스코프 client 픽스처가 이미 로드된 뒤에 로그 파일을
        # 새로 만들어도 반영되도록 새로 create_app()한다(파일 스캔은 요청 시점 로딩이라
        # 별 문제는 없지만, 다른 테스트의 "빈 로그" 기대와 격리하기 위해 별도 인스턴스 사용).
        log_path = results_dir_with_regression / "recommendation_outcomes.jsonl"
        before = _result_payload(gate_a_score=0.4)
        after = _result_payload(gate_a_score=0.85)
        record_recommendation_outcome(
            log_path, recommendation_id="mast-fm-3.2", target_gate="A",
            before=before, after=after,
        )
        app = create_app(results_dir=results_dir_with_regression, watch=False, offline=False)
        fresh_client = TestClient(app, raise_server_exceptions=False)

        r = fresh_client.get("/api/diagnose/")
        assert r.status_code == 200
        body = r.json()
        assert len(body["outcomes"]) == 1
        assert body["outcomes"][0]["recommendation_id"] == "mast-fm-3.2"
        assert body["summary"]["confirmed"] == 1

    def test_filters_by_gate_query_param(self, results_dir_with_regression: Path):
        app = create_app(results_dir=results_dir_with_regression, watch=False, offline=False)
        fresh_client = TestClient(app, raise_server_exceptions=False)
        r = fresh_client.get("/api/diagnose/", params={"gate": "F"})
        assert r.status_code == 200
        assert r.json()["outcomes"] == []  # 위에서 기록한 건 target_gate="A"뿐
