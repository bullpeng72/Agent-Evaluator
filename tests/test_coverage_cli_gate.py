"""
tests/test_coverage_cli_gate.py
================================
cli/gate.py 미커버 영역 집중 테스트 (23% → 80%+ 목표).

커버 대상:
  - _load_metrics: TCR 스케일 변환, success_rate fallback, accuracy/hallucination/p95/llm_judge
  - _default_baseline_path / _load_baseline / _save_baseline
  - _check_gates: active/inactive, min/max, current None
  - _check_regression: min/max direction, tolerance, 분모 0
  - _fmt_value / _fmt_threshold / _fmt_delta
  - _print_table: 출력 분기 (no active / all pass / regression only / fail)
  - _write_junit_xml: pass/fail testcase, regression testcase
  - cmd_gate: 파일 없음, JSON 파싱 실패, 정상 0, 정상 1, 회귀 2,
              --save-baseline 단독, --baseline 명시, --junit-xml 출력
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# 헬퍼: gate 모듈 임포트
# ---------------------------------------------------------------------------
from agent_evaluator.cli.gate import (
    _check_gates,
    _check_regression,
    _default_baseline_path,
    _fmt_delta,
    _fmt_threshold,
    _fmt_value,
    _load_baseline,
    _load_metrics,
    _print_table,
    _save_baseline,
    _write_junit_xml,
    cmd_gate,
)


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

def _make_args(**kwargs) -> argparse.Namespace:
    """cmd_gate 에 필요한 기본 Namespace 생성."""
    defaults = dict(
        result_file="dummy.json",
        tcr=None,
        accuracy=None,
        p95_latency=None,
        hallucination=None,
        llm_judge=None,
        fail_on_regression=None,
        baseline=None,
        save_baseline=False,
        junit_xml=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_result_data(
    tcr: Optional[float] = 0.9,
    accuracy: Optional[float] = 0.85,
    p95: Optional[float] = 1.5,
    hallucination: Optional[float] = 0.1,
    llm_judge_overall: Optional[float] = None,
) -> Dict[str, Any]:
    """표준 평가 결과 JSON dict 생성."""
    data: Dict[str, Any] = {
        "accuracy_metrics": {
            "tcr": {"tcr": tcr},
            "accuracy_scores": {"overall_accuracy": accuracy},
            "hallucination": {"overall_rate": hallucination},
        },
        "efficiency_metrics": {
            "latency": {"p95": p95},
        },
        "tasks": [],
    }
    if llm_judge_overall is not None:
        data["tasks"] = [
            {"llm_judge": {"scores": {"overall": llm_judge_overall}}}
        ]
    return data


@pytest.fixture
def tmp_result_file(tmp_path):
    """임시 결과 JSON 파일 경로 팩토리."""
    def _factory(data: Dict[str, Any], filename: str = "result.json") -> Path:
        p = tmp_path / filename
        p.write_text(json.dumps(data), encoding="utf-8")
        return p
    return _factory


# ===========================================================================
# 1. _load_metrics
# ===========================================================================

class TestLoadMetrics:
    def test_tcr_0_to_1_scale_converted(self):
        data = _make_result_data(tcr=0.9)
        m = _load_metrics(data)
        assert m["tcr"] == pytest.approx(90.0)

    def test_tcr_already_percentage(self):
        data = _make_result_data(tcr=85.0)
        m = _load_metrics(data)
        assert m["tcr"] == pytest.approx(85.0)

    def test_tcr_fallback_success_rate(self):
        data: Dict[str, Any] = {
            "accuracy_metrics": {"tcr": {"success_rate": 0.75}},
            "efficiency_metrics": {},
            "tasks": [],
        }
        m = _load_metrics(data)
        assert m["tcr"] == pytest.approx(75.0)

    def test_tcr_none_when_missing(self):
        data: Dict[str, Any] = {"accuracy_metrics": {}, "efficiency_metrics": {}, "tasks": []}
        m = _load_metrics(data)
        assert m["tcr"] is None

    def test_accuracy_extracted(self):
        data = _make_result_data(accuracy=0.82)
        m = _load_metrics(data)
        assert m["accuracy"] == pytest.approx(82.0)

    def test_accuracy_already_pct(self):
        data = _make_result_data(accuracy=82.0)
        m = _load_metrics(data)
        assert m["accuracy"] == pytest.approx(82.0)

    def test_hallucination_extracted(self):
        data = _make_result_data(hallucination=0.05)
        m = _load_metrics(data)
        assert m["hallucination"] == pytest.approx(5.0)

    def test_p95_latency_extracted(self):
        data = _make_result_data(p95=2.3)
        m = _load_metrics(data)
        assert m["p95_latency"] == pytest.approx(2.3)

    def test_p95_none_when_missing(self):
        data: Dict[str, Any] = {
            "accuracy_metrics": {},
            "efficiency_metrics": {"latency": {}},
            "tasks": [],
        }
        m = _load_metrics(data)
        assert m["p95_latency"] is None

    def test_llm_judge_overall_averaged(self):
        data: Dict[str, Any] = {
            "accuracy_metrics": {},
            "efficiency_metrics": {},
            "tasks": [
                {"llm_judge": {"scores": {"overall": 4.0}}},
                {"llm_judge": {"scores": {"overall": 3.0}}},
            ],
        }
        m = _load_metrics(data)
        assert m["llm_judge_overall"] == pytest.approx(3.5)

    def test_llm_judge_none_when_no_tasks(self):
        data = _make_result_data()
        m = _load_metrics(data)
        assert m["llm_judge_overall"] is None

    def test_llm_judge_skips_non_dict_task(self):
        data: Dict[str, Any] = {
            "accuracy_metrics": {},
            "efficiency_metrics": {},
            "tasks": ["not_a_dict", {"llm_judge": {"scores": {"overall": 5.0}}}],
        }
        m = _load_metrics(data)
        assert m["llm_judge_overall"] == pytest.approx(5.0)

    def test_invalid_tcr_value_skipped(self):
        data: Dict[str, Any] = {
            "accuracy_metrics": {"tcr": {"tcr": "invalid"}},
            "efficiency_metrics": {},
            "tasks": [],
        }
        m = _load_metrics(data)
        assert m["tcr"] is None

    def test_empty_data_all_none(self):
        m = _load_metrics({})
        assert all(v is None for v in m.values())


# ===========================================================================
# 2. _default_baseline_path
# ===========================================================================

class TestDefaultBaselinePath:
    def test_same_directory_as_result(self, tmp_path):
        result = tmp_path / "subdir" / "result.json"
        bp = _default_baseline_path(result)
        assert bp == tmp_path / "subdir" / "baseline.json"

    def test_filename_is_baseline_json(self, tmp_path):
        result = tmp_path / "result.json"
        assert _default_baseline_path(result).name == "baseline.json"


# ===========================================================================
# 3. _load_baseline / _save_baseline
# ===========================================================================

class TestBaselineIO:
    def test_load_baseline_missing_returns_none(self, tmp_path):
        bp = tmp_path / "no_file.json"
        assert _load_baseline(bp) is None

    def test_load_baseline_invalid_json_returns_none(self, tmp_path):
        bp = tmp_path / "bad.json"
        bp.write_text("not-json", encoding="utf-8")
        assert _load_baseline(bp) is None

    def test_load_baseline_valid(self, tmp_path):
        bp = tmp_path / "baseline.json"
        payload = {"tcr": 90.0, "accuracy": 80.0}
        bp.write_text(json.dumps(payload), encoding="utf-8")
        result = _load_baseline(bp)
        assert result is not None
        assert result["tcr"] == 90.0

    def test_save_baseline_creates_file(self, tmp_path):
        bp = tmp_path / "new_dir" / "baseline.json"
        metrics = {"tcr": 85.0, "accuracy": 70.0, "p95_latency": None,
                   "hallucination": None, "llm_judge_overall": None}
        _save_baseline(bp, metrics)
        assert bp.is_file()
        loaded = json.loads(bp.read_text(encoding="utf-8"))
        assert loaded["tcr"] == 85.0
        assert "saved_at" in loaded

    def test_save_and_load_roundtrip(self, tmp_path):
        bp = tmp_path / "baseline.json"
        metrics = {"tcr": 92.0, "accuracy": 80.0, "p95_latency": 1.2,
                   "hallucination": 5.0, "llm_judge_overall": 4.0}
        _save_baseline(bp, metrics)
        loaded = _load_baseline(bp)
        assert loaded is not None
        assert loaded["tcr"] == 92.0
        assert loaded["p95_latency"] == 1.2


# ===========================================================================
# 4. _check_gates
# ===========================================================================

class TestCheckGates:
    def _args(self, tcr=None, accuracy=None, p95_latency=None, hallucination=None, llm_judge=None):
        return argparse.Namespace(
            tcr=tcr, accuracy=accuracy, p95_latency=p95_latency,
            hallucination=hallucination, llm_judge=llm_judge,
        )

    def _metrics(self):
        return {"tcr": 90.0, "accuracy": 80.0, "p95_latency": 1.5,
                "hallucination": 5.0, "llm_judge_overall": 4.0}

    def test_no_thresholds_all_inactive(self):
        results = _check_gates(self._metrics(), self._args())
        assert all(not g["active"] for g in results)
        assert all(g["passed"] for g in results)

    def test_min_direction_pass(self):
        results = _check_gates(self._metrics(), self._args(tcr=85.0))
        tcr_gate = next(g for g in results if g["name"] == "tcr")
        assert tcr_gate["active"] is True
        assert tcr_gate["passed"] is True  # 90.0 >= 85.0

    def test_min_direction_fail(self):
        results = _check_gates(self._metrics(), self._args(tcr=95.0))
        tcr_gate = next(g for g in results if g["name"] == "tcr")
        assert tcr_gate["passed"] is False  # 90.0 < 95.0

    def test_max_direction_pass(self):
        results = _check_gates(self._metrics(), self._args(p95_latency=2.0))
        lat_gate = next(g for g in results if g["name"] == "p95_latency")
        assert lat_gate["passed"] is True  # 1.5 <= 2.0

    def test_max_direction_fail(self):
        results = _check_gates(self._metrics(), self._args(p95_latency=1.0))
        lat_gate = next(g for g in results if g["name"] == "p95_latency")
        assert lat_gate["passed"] is False  # 1.5 > 1.0

    def test_current_none_fails_when_threshold_set(self):
        metrics = {"tcr": None, "accuracy": None, "p95_latency": None,
                   "hallucination": None, "llm_judge_overall": None}
        results = _check_gates(metrics, self._args(tcr=80.0))
        tcr_gate = next(g for g in results if g["name"] == "tcr")
        assert tcr_gate["active"] is True
        assert tcr_gate["passed"] is False
        assert tcr_gate["current"] is None

    def test_hallucination_max_gate(self):
        results = _check_gates(self._metrics(), self._args(hallucination=10.0))
        h_gate = next(g for g in results if g["name"] == "hallucination")
        assert h_gate["passed"] is True  # 5.0 <= 10.0

    def test_llm_judge_min_gate(self):
        results = _check_gates(self._metrics(), self._args(llm_judge=3.5))
        j_gate = next(g for g in results if g["name"] == "llm_judge_overall")
        assert j_gate["passed"] is True  # 4.0 >= 3.5


# ===========================================================================
# 5. _check_regression
# ===========================================================================

class TestCheckRegression:
    def _metrics(self):
        return {"tcr": 85.0, "accuracy": 75.0, "p95_latency": 1.5,
                "hallucination": 8.0, "llm_judge_overall": 3.5}

    def _baseline(self):
        return {"tcr": 90.0, "accuracy": 80.0, "p95_latency": 1.0,
                "hallucination": 5.0, "llm_judge_overall": 4.0}

    def test_min_direction_regression_detected(self):
        # tcr 85 < 90 * (1 - 0.0) → 회귀
        regressions = _check_regression(self._metrics(), self._baseline(), 0.0)
        names = [r["name"] for r in regressions]
        assert "tcr" in names

    def test_within_tolerance_not_regression(self):
        # tcr 85 / baseline 90 = ~5.5% 하락, tolerance 10% → 통과
        regressions = _check_regression(self._metrics(), self._baseline(), 10.0)
        names = [r["name"] for r in regressions]
        assert "tcr" not in names

    def test_max_direction_regression_detected(self):
        # p95_latency 1.5 > 1.0 * 1.0 (tolerance 0%) → 회귀
        regressions = _check_regression(self._metrics(), self._baseline(), 0.0)
        names = [r["name"] for r in regressions]
        assert "p95_latency" in names

    def test_none_current_skipped(self):
        metrics = {"tcr": None, "accuracy": None, "p95_latency": None,
                   "hallucination": None, "llm_judge_overall": None}
        regressions = _check_regression(metrics, self._baseline(), 0.0)
        assert regressions == []

    def test_baseline_zero_skipped(self):
        baseline = {"tcr": 0.0, "accuracy": 80.0, "p95_latency": 1.0,
                    "hallucination": 5.0, "llm_judge_overall": 4.0}
        regressions = _check_regression(self._metrics(), baseline, 0.0)
        names = [r["name"] for r in regressions]
        assert "tcr" not in names  # 분모 0 guard

    def test_baseline_non_numeric_skipped(self):
        baseline = {"tcr": "not_a_number", "accuracy": 80.0,
                    "p95_latency": 1.0, "hallucination": 5.0, "llm_judge_overall": 4.0}
        regressions = _check_regression(self._metrics(), baseline, 0.0)
        names = [r["name"] for r in regressions]
        assert "tcr" not in names

    def test_pct_change_in_result(self):
        # tcr 85 vs baseline 90 → pct_change 음수 (하락)
        regressions = _check_regression(self._metrics(), self._baseline(), 0.0)
        tcr_reg = next((r for r in regressions if r["name"] == "tcr"), None)
        assert tcr_reg is not None
        assert tcr_reg["pct_change"] < 0


# ===========================================================================
# 6. 포맷 함수
# ===========================================================================

class TestFmtFunctions:
    def test_fmt_value_none(self):
        result = _fmt_value(None, "%")
        assert "N/A" in result

    def test_fmt_value_percent(self):
        result = _fmt_value(85.123, "%")
        assert "85.1%" in result

    def test_fmt_value_seconds(self):
        result = _fmt_value(1.567, "s")
        assert "1.57s" in result

    def test_fmt_value_per5(self):
        result = _fmt_value(4.5, "/5")
        assert "4.50/5" in result

    def test_fmt_threshold_none(self):
        result = _fmt_threshold(None, "min", "%")
        assert "—" in result

    def test_fmt_threshold_min(self):
        result = _fmt_threshold(80.0, "min", "%")
        assert "≥" in result
        assert "80%" in result

    def test_fmt_threshold_max_seconds(self):
        result = _fmt_threshold(2.0, "max", "s")
        assert "≤" in result
        assert "2.0s" in result

    def test_fmt_threshold_per5(self):
        result = _fmt_threshold(3.5, "min", "/5")
        assert "≥" in result
        assert "3.5/5" in result

    def test_fmt_delta_min_positive(self):
        # current 90 - threshold 80 = +10
        result = _fmt_delta(90.0, 80.0, "min", "%")
        assert "+10.0%" in result

    def test_fmt_delta_min_negative(self):
        result = _fmt_delta(70.0, 80.0, "min", "%")
        assert "-10.0%" in result

    def test_fmt_delta_max_positive(self):
        # threshold 2.0 - current 1.5 = +0.5 (좋음: 임계값 내)
        result = _fmt_delta(1.5, 2.0, "max", "s")
        assert "+" in result


# ===========================================================================
# 7. _print_table
# ===========================================================================

class TestPrintTable:
    def _make_gate_result(self, active, passed, current=90.0, threshold=80.0,
                          direction="min", unit="%"):
        return {
            "name": "tcr",
            "label": "TCR",
            "current": current,
            "threshold": threshold if active else None,
            "direction": direction,
            "unit": unit,
            "active": active,
            "passed": passed,
        }

    def test_print_no_active_gates(self, capsys):
        gate_results = [self._make_gate_result(active=False, passed=True)]
        _print_table(gate_results, "result.json")
        out = capsys.readouterr().out
        assert "임계값 기준이 지정되지 않았습니다" in out

    def test_print_all_pass(self, capsys):
        gate_results = [self._make_gate_result(active=True, passed=True)]
        _print_table(gate_results, "result.json")
        out = capsys.readouterr().out
        assert "모든 기준 통과" in out

    def test_print_fail(self, capsys):
        gate_results = [self._make_gate_result(active=True, passed=False, current=70.0)]
        _print_table(gate_results, "result.json")
        out = capsys.readouterr().out
        assert "품질 기준 미달" in out

    def test_print_regression_warning(self, capsys):
        gate_results = [self._make_gate_result(active=True, passed=True)]
        regressions = [{
            "name": "tcr",
            "label": "TCR",
            "current": 85.0,
            "baseline_val": 90.0,
            "pct_change": -5.56,
            "unit": "%",
        }]
        _print_table(gate_results, "result.json", regressions)
        out = capsys.readouterr().out
        assert "회귀" in out

    def test_print_skip_when_current_none(self, capsys):
        gate_results = [self._make_gate_result(active=True, passed=False, current=None)]
        _print_table(gate_results, "result.json")
        out = capsys.readouterr().out
        # SKIP 메시지 포함 또는 품질 기준 미달
        assert "SKIP" in out or "품질 기준 미달" in out

    def test_regression_only_warning_message(self, capsys):
        gate_results = [self._make_gate_result(active=True, passed=True)]
        regressions = [{
            "name": "tcr", "label": "TCR", "current": 85.0,
            "baseline_val": 90.0, "pct_change": -5.0, "unit": "%",
        }]
        _print_table(gate_results, "result.json", regressions)
        out = capsys.readouterr().out
        assert "임계값은 통과했으나 회귀 감지" in out


# ===========================================================================
# 8. _write_junit_xml
# ===========================================================================

class TestWriteJunitXml:
    def _gate(self, passed=True, current=90.0, threshold=80.0):
        return {
            "name": "tcr", "label": "TCR",
            "current": current, "threshold": threshold,
            "direction": "min", "unit": "%",
            "active": True, "passed": passed,
        }

    def test_creates_xml_file(self, tmp_path):
        out = tmp_path / "results.xml"
        _write_junit_xml([self._gate(passed=True)], None, out)
        assert out.is_file()

    def test_xml_has_testsuites(self, tmp_path):
        out = tmp_path / "results.xml"
        _write_junit_xml([self._gate(passed=True)], None, out)
        content = out.read_text(encoding="utf-8")
        assert "testsuites" in content
        assert "testsuite" in content

    def test_xml_has_failure_for_fail_gate(self, tmp_path):
        out = tmp_path / "results.xml"
        _write_junit_xml([self._gate(passed=False, current=70.0)], None, out)
        content = out.read_text(encoding="utf-8")
        assert "<failure" in content

    def test_xml_no_failure_for_pass_gate(self, tmp_path):
        out = tmp_path / "results.xml"
        _write_junit_xml([self._gate(passed=True)], None, out)
        content = out.read_text(encoding="utf-8")
        assert "<failure" not in content

    def test_xml_regression_testcase(self, tmp_path):
        out = tmp_path / "results.xml"
        regressions = [{
            "name": "tcr", "label": "TCR",
            "current": 85.0, "baseline_val": 90.0, "pct_change": -5.56, "unit": "%",
        }]
        _write_junit_xml([], regressions, out)
        content = out.read_text(encoding="utf-8")
        assert "regression" in content

    def test_xml_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "new" / "dir" / "results.xml"
        _write_junit_xml([self._gate()], None, out)
        assert out.is_file()

    def test_xml_test_count_in_testsuite_attr(self, tmp_path):
        out = tmp_path / "results.xml"
        gates = [self._gate(passed=True), self._gate(passed=False, current=70.0)]
        _write_junit_xml(gates, None, out)
        content = out.read_text(encoding="utf-8")
        assert 'tests="2"' in content
        assert 'failures="1"' in content


# ===========================================================================
# 9. cmd_gate — end-to-end
# ===========================================================================

class TestCmdGate:
    def test_file_not_found_returns_1(self, tmp_path):
        args = _make_args(result_file=str(tmp_path / "nonexistent.json"))
        rc = cmd_gate(args)
        assert rc == 1

    def test_invalid_json_returns_1(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        args = _make_args(result_file=str(f))
        rc = cmd_gate(args)
        assert rc == 1

    def test_no_thresholds_returns_0(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data()), encoding="utf-8")
        args = _make_args(result_file=str(f))
        rc = cmd_gate(args)
        assert rc == 0

    def test_all_thresholds_pass_returns_0(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.9, accuracy=0.85)), encoding="utf-8")
        args = _make_args(result_file=str(f), tcr=85.0, accuracy=80.0)
        rc = cmd_gate(args)
        assert rc == 0

    def test_threshold_fail_returns_1(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.7)), encoding="utf-8")
        args = _make_args(result_file=str(f), tcr=90.0)
        rc = cmd_gate(args)
        assert rc == 1

    def test_save_baseline_only_returns_0(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data()), encoding="utf-8")
        args = _make_args(result_file=str(f), save_baseline=True)
        rc = cmd_gate(args)
        assert rc == 0
        # baseline.json 생성됐는지 확인
        baseline = tmp_path / "baseline.json"
        assert baseline.is_file()

    def test_save_baseline_then_gate_continues(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.7)), encoding="utf-8")
        args = _make_args(result_file=str(f), save_baseline=True, tcr=90.0)
        rc = cmd_gate(args)
        assert rc == 1  # 저장 후 게이팅 계속 — 실패

    def test_fail_on_regression_no_baseline_returns_0(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.85)), encoding="utf-8")
        args = _make_args(result_file=str(f), fail_on_regression=5.0)
        rc = cmd_gate(args)
        # baseline 없으면 회귀 검사 건너뜀 → 게이팅 기준 없으므로 0
        assert rc == 0

    def test_fail_on_regression_with_baseline_regression_detected(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.7)), encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"tcr": 90.0, "saved_at": "2025-01-01"}),
                            encoding="utf-8")
        args = _make_args(result_file=str(f), fail_on_regression=0.0)
        rc = cmd_gate(args)
        assert rc == 2

    def test_explicit_baseline_path_used(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data(tcr=0.7)), encoding="utf-8")
        custom_bl = tmp_path / "custom_baseline.json"
        custom_bl.write_text(json.dumps({"tcr": 90.0, "saved_at": "2025-01-01"}),
                             encoding="utf-8")
        args = _make_args(
            result_file=str(f),
            baseline=str(custom_bl),
            fail_on_regression=0.0,
        )
        rc = cmd_gate(args)
        assert rc == 2  # 회귀 감지

    def test_junit_xml_created(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps(_make_result_data()), encoding="utf-8")
        xml_path = tmp_path / "junit.xml"
        args = _make_args(result_file=str(f), junit_xml=str(xml_path))
        cmd_gate(args)
        assert xml_path.is_file()
        content = xml_path.read_text(encoding="utf-8")
        assert "testsuites" in content

    def test_llm_judge_threshold_pass(self, tmp_path):
        data = _make_result_data(llm_judge_overall=4.0)
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), llm_judge=3.5)
        rc = cmd_gate(args)
        assert rc == 0

    def test_llm_judge_threshold_fail(self, tmp_path):
        data = _make_result_data(llm_judge_overall=2.0)
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), llm_judge=3.5)
        rc = cmd_gate(args)
        assert rc == 1

    def test_hallucination_threshold_fail(self, tmp_path):
        data = _make_result_data(hallucination=0.3)  # 30%
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), hallucination=20.0)
        rc = cmd_gate(args)
        assert rc == 1  # 30 > 20

    def test_regression_with_all_metrics_no_regression(self, tmp_path):
        data = _make_result_data(tcr=0.95, accuracy=0.9, p95=1.0, hallucination=0.02)
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        baseline_data = {"tcr": 90.0, "accuracy": 85.0, "p95_latency": 1.5,
                         "hallucination": 10.0, "llm_judge_overall": None,
                         "saved_at": "2025-01-01"}
        bl = tmp_path / "baseline.json"
        bl.write_text(json.dumps(baseline_data), encoding="utf-8")
        args = _make_args(result_file=str(f), fail_on_regression=5.0)
        rc = cmd_gate(args)
        assert rc == 0  # 모두 개선됨 → 회귀 없음

    def test_p95_threshold_pass(self, tmp_path):
        data = _make_result_data(p95=1.2)
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), p95_latency=2.0)
        rc = cmd_gate(args)
        assert rc == 0

    def test_p95_threshold_fail(self, tmp_path):
        data = _make_result_data(p95=3.0)
        f = tmp_path / "result.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        args = _make_args(result_file=str(f), p95_latency=2.0)
        rc = cmd_gate(args)
        assert rc == 1
