"""
tests/test_report_diagnosis_section.py
===========================================
정적 HTML 리포트(comprehensive_report.py)에 반영한 Gate RCA 진단 섹션
(`_build_diagnosis()`) 테스트 — 대시보드 "Improve" 탭에서만 보이던 내용을
`save_to_file()`/`agent-eval gate`/대시보드 Export HTML이 저장하는 정적
리포트에도 반영하는 기능.

``_build_diagnosis()``는 ``agent_evaluator.rca.diagnose()``를 그대로 감싸는
얇은 렌더링 레이어다 — 새 판정 로직은 없으므로, 여기서는 ① 두 진입점
(`generate_comprehensive_html_report`/`generate_html_from_result_file`) 모두
섹션을 포함하는지, ② baseline 없음/있음·MAST 후보·추천 이력·예외 상황에서
렌더링이 깨지지 않는지만 확인한다.
"""
from __future__ import annotations

import json

from agent_evaluator import PerformanceMonitor, create_taskresult
from agent_evaluator.rca.recommendation_tracking import record_recommendation_outcome
from agent_evaluator.reporting.comprehensive_report import (
    _build_diagnosis,
    generate_comprehensive_html_report,
)


def _harness_groups(**gates):
    return {"extra_metrics": {"harness_groups": gates}}


class TestBuildDiagnosisNoBaseline:
    def test_absolute_threshold_mode_label(self):
        current = _harness_groups(A={"score": 0.3, "status": "fail", "gate": "fail", "details": {}})
        html = _build_diagnosis(current)
        assert "Absolute-threshold detection" in html
        assert "Gate A" in html

    def test_healthy_report_shows_no_detection_message(self):
        current = _harness_groups(
            A={"score": 0.95, "status": "pass", "gate": "pass", "details": {}},
            C={"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
        )
        html = _build_diagnosis(current)
        assert "No regression or fail/warn Gate detected" in html

    def test_always_ends_with_hotl_disclaimer(self):
        html = _build_diagnosis(_harness_groups())
        assert "HOTL" in html
        assert "The final judgment is yours" in html


class TestBuildDiagnosisWithBaseline:
    def test_regression_mode_label(self):
        baseline = _harness_groups(
            A={"score": 0.9, "status": "pass", "gate": "pass", "details": {}},
        )
        current = _harness_groups(
            A={"score": 0.3, "status": "fail", "gate": "fail", "details": {}},
        )
        html = _build_diagnosis(current, baseline)
        assert "Regression-based detection" in html

    def test_gate_f_mast_candidates_rendered(self):
        baseline = _harness_groups(
            F={"score": 0.9, "status": "pass", "gate": "pass",
               "details": {"avg_conflict_resolution": 0.95}},
        )
        current = _harness_groups(
            F={"score": 0.3, "status": "fail", "gate": "fail",
               "details": {"avg_conflict_resolution": 0.2}},
        )
        html = _build_diagnosis(current, baseline)
        assert "MAST" in html
        assert "Cemri et al" in html
        assert "% of paper traces" in html


class TestBuildDiagnosisRecommendationHistory:
    def test_history_rendered_when_log_has_entries(self, tmp_path):
        log_path = tmp_path / "recommendation_outcomes.jsonl"
        record_recommendation_outcome(
            log_path, recommendation_id="r1", target_gate="A",
            before={"extra_metrics": {"harness_groups": {"A": {"score": 0.3}}}},
            after={"extra_metrics": {"harness_groups": {"A": {"score": 0.6}}}},
            note="added InstructionConfig",
        )
        html = _build_diagnosis(_harness_groups(), recommendation_log_path=log_path)
        assert "Improvement history" in html
        assert "added InstructionConfig" in html

    def test_no_history_section_when_log_missing(self, tmp_path):
        html = _build_diagnosis(
            _harness_groups(), recommendation_log_path=tmp_path / "does_not_exist.jsonl",
        )
        assert "Improvement history" not in html


class TestBuildDiagnosisErrorHandling:
    def test_malformed_current_dict_does_not_raise(self):
        # extra_metrics 없는 dict도 예외를 내지 않아야 한다(try/except로 감쌈).
        html = _build_diagnosis({})
        assert isinstance(html, str)


class TestEntryPointsIncludeDiagnosisSection:
    def test_generate_comprehensive_html_report_includes_diagnosis(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0, task_type="qa",
        ))
        html = generate_comprehensive_html_report(monitor)
        assert 'id="diagnosis"' in html
        assert "Gate RCA Diagnosis" in html

    def test_generate_html_from_result_file_includes_diagnosis(self, tmp_path):
        from agent_evaluator.serve.loader import load_results

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0, task_type="qa",
        ))
        monitor.save_to_file("result")

        # save_to_file() 자체가 generate_comprehensive_html_report()를 호출하므로
        # 이미 생성된 result.html에 섹션이 있는지 직접 확인 — 이게 실제 사용자가
        # 보는 파일이다.
        html_path = tmp_path / "result.html"
        assert html_path.exists()
        saved_html = html_path.read_text(encoding="utf-8")
        assert 'id="diagnosis"' in saved_html

        # generate_html_from_result_file() 경로(대시보드 Export HTML)도 별도로 확인.
        rs = load_results(tmp_path)
        rf = next(f for f in rs.files if f.path.stem == "result")
        from agent_evaluator.reporting.comprehensive_report import (
            generate_html_from_result_file,
        )
        rf_html = generate_html_from_result_file(rf)
        assert 'id="diagnosis"' in rf_html

    def test_save_to_file_json_unaffected(self, tmp_path):
        """새 섹션이 JSON 출력(schema)에는 영향을 주지 않아야 한다 — HTML 전용 추가."""
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="a", ground_truth="a",
            execution_time=1.0, task_type="qa",
        ))
        monitor.save_to_file("result2")
        with open(tmp_path / "result2.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "diagnosis" not in data
        assert "extra_metrics" in data


class TestSaveToFileBaselinePlumbing:
    """Phase 2 — save_to_file(baseline_path=...)/QuickEval.save(baseline_path=...)가 생성된 HTML의
    진단 모드를 회귀 기반으로 격상시키는지 확인한다."""

    def _write_baseline_json(self, path, *, gate_a_score: float) -> None:
        payload = _harness_groups(
            A={"score": gate_a_score, "status": "pass", "gate": "pass", "details": {}},
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_save_to_file_with_baseline_path_uses_regression_mode(self, tmp_path):
        baseline_path = tmp_path / "baseline.json"
        self._write_baseline_json(baseline_path, gate_a_score=0.9)

        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0, task_type="qa",
        ))
        monitor.save_to_file("current", baseline_path=str(baseline_path))

        html = (tmp_path / "current.html").read_text(encoding="utf-8")
        assert "Regression-based detection" in html

    def test_save_to_file_without_baseline_path_uses_absolute_mode(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0, task_type="qa",
        ))
        monitor.save_to_file("current_nobaseline")

        html = (tmp_path / "current_nobaseline.html").read_text(encoding="utf-8")
        assert "Absolute-threshold detection" in html
        assert "Regression-based detection" not in html

    def test_save_to_file_invalid_baseline_path_falls_back_without_raising(self, tmp_path):
        monitor = PerformanceMonitor(output_dir=str(tmp_path))
        monitor.record_task(create_taskresult(
            task_id="t1", question="q", response="정상 응답입니다",
            ground_truth="정상 응답입니다", execution_time=1.0, task_type="qa",
        ))
        # 존재하지 않는 baseline_path — 예외 없이 절대 임계값 모드로 폴백해야 한다.
        monitor.save_to_file(
            "current_badbaseline", baseline_path=str(tmp_path / "does_not_exist.json"),
        )

        html = (tmp_path / "current_badbaseline.html").read_text(encoding="utf-8")
        assert "Absolute-threshold detection" in html

    def test_quickeval_save_passes_baseline_path_through(self, tmp_path):
        from agent_evaluator import QuickEval

        baseline_path = tmp_path / "baseline.json"
        self._write_baseline_json(baseline_path, gate_a_score=0.9)

        qe = QuickEval(str(tmp_path))

        @qe.qa
        def agent(question, ground_truth=""):
            return "정상 응답입니다"

        agent("질문", ground_truth="정상 응답입니다")
        qe.save("qe_current", baseline_path=str(baseline_path))

        html = (tmp_path / "qe_current.html").read_text(encoding="utf-8")
        assert "Regression-based detection" in html
