"""
RunTrendAnalyzer 및 agent-eval trend CLI 테스트.

이슈 #1 (feat(gate): RunTrendAnalyzer) 구현 검증.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from agent_evaluator.cli.trend import (
    MetricTrend,
    RunPoint,
    RunTrendAnalyzer,
    RunTrendReport,
    _slope,
    cmd_trend,
)


# ---------------------------------------------------------------------------
# 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_result_json(
    tcr: float = 90.0,
    accuracy: float = 85.0,
    p95_latency: float = 1.0,
    hallucination: float = 5.0,
) -> dict:
    """_load_metrics()가 파싱할 수 있는 최소 result JSON."""
    return {
        "accuracy_metrics": {
            "tcr": {"tcr": tcr / 100.0},
            "accuracy_scores": {"overall_accuracy": accuracy / 100.0},
            "hallucination": {"overall_rate": hallucination / 100.0},
        },
        "efficiency_metrics": {
            "latency": {"p95": p95_latency},
        },
    }


def _write_results(tmp_dir: Path, runs: list) -> None:
    """runs 목록을 순서대로 파일에 기록한다 (파일명 정렬 보장)."""
    for i, data in enumerate(runs):
        fname = tmp_dir / f"result_{i:03d}.json"
        fname.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# _slope 단위 테스트
# ---------------------------------------------------------------------------

class TestSlope:
    def test_positive_slope(self):
        xs = [0, 1, 2, 3, 4]
        ys = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _slope(xs, ys) == pytest.approx(1.0, abs=1e-9)

    def test_negative_slope(self):
        xs = [0, 1, 2, 3, 4]
        ys = [5.0, 4.0, 3.0, 2.0, 1.0]
        assert _slope(xs, ys) == pytest.approx(-1.0, abs=1e-9)

    def test_flat(self):
        xs = [0, 1, 2]
        ys = [3.0, 3.0, 3.0]
        assert _slope(xs, ys) == pytest.approx(0.0, abs=1e-9)

    def test_single_point_returns_zero(self):
        assert _slope([0], [5.0]) == 0.0

    def test_zero_denominator_returns_zero(self):
        # 모든 x가 같으면 분모 0 → 0 반환
        assert _slope([1, 1, 1], [1.0, 2.0, 3.0]) == 0.0


# ---------------------------------------------------------------------------
# RunTrendAnalyzer 단위 테스트
# ---------------------------------------------------------------------------

class TestRunTrendAnalyzer:
    def test_analyze_detects_tcr_regression(self, tmp_path):
        """TCR이 지속적으로 하락하는 경우 degrading 으로 감지."""
        runs = [
            _make_result_json(tcr=94.0),
            _make_result_json(tcr=91.0),
            _make_result_json(tcr=88.0),
            _make_result_json(tcr=85.0),
            _make_result_json(tcr=82.0),
        ]
        _write_results(tmp_path, runs)

        analyzer = RunTrendAnalyzer(str(tmp_path), slope_threshold=0.3)
        report = analyzer.analyze()

        assert report.tcr_trend is not None
        assert report.tcr_trend.direction == "degrading"
        assert report.tcr_trend.any_regression is True
        assert report.any_regression is True

    def test_analyze_detects_tcr_improving(self, tmp_path):
        """TCR이 지속적으로 개선되는 경우 improving 으로 감지."""
        runs = [
            _make_result_json(tcr=80.0),
            _make_result_json(tcr=83.0),
            _make_result_json(tcr=86.0),
            _make_result_json(tcr=89.0),
            _make_result_json(tcr=92.0),
        ]
        _write_results(tmp_path, runs)

        analyzer = RunTrendAnalyzer(str(tmp_path), slope_threshold=0.3)
        report = analyzer.analyze()

        assert report.tcr_trend is not None
        assert report.tcr_trend.direction == "improving"
        assert report.tcr_trend.any_regression is False
        assert report.any_regression is False

    def test_analyze_stable_within_threshold(self, tmp_path):
        """slope가 임계값 미만이면 stable 로 판정."""
        runs = [
            _make_result_json(tcr=90.1),
            _make_result_json(tcr=89.9),
            _make_result_json(tcr=90.0),
            _make_result_json(tcr=90.1),
            _make_result_json(tcr=89.8),
        ]
        _write_results(tmp_path, runs)

        analyzer = RunTrendAnalyzer(str(tmp_path), slope_threshold=0.3)
        report = analyzer.analyze()

        assert report.tcr_trend is not None
        assert report.tcr_trend.direction == "stable"

    def test_analyze_latency_regression(self, tmp_path):
        """P95 지연시간이 지속 상승하면 degrading (높을수록 나쁨)."""
        runs = [
            _make_result_json(p95_latency=1.0),
            _make_result_json(p95_latency=1.5),
            _make_result_json(p95_latency=2.0),
            _make_result_json(p95_latency=2.5),
            _make_result_json(p95_latency=3.0),
        ]
        _write_results(tmp_path, runs)

        analyzer = RunTrendAnalyzer(str(tmp_path), slope_threshold=0.05)
        report = analyzer.analyze()

        assert report.latency_trend is not None
        assert report.latency_trend.direction == "degrading"

    def test_window_limits_files(self, tmp_path):
        """window 파라미터가 최근 N개만 분석한다."""
        for i in range(8):
            fname = tmp_path / f"result_{i:03d}.json"
            fname.write_text(json.dumps(_make_result_json(tcr=float(90 + i))), encoding="utf-8")

        analyzer = RunTrendAnalyzer(str(tmp_path), window=5)
        report = analyzer.analyze()

        assert report.window == 5
        assert len(report.runs) == 5

    def test_insufficient_data_returns_none_trend(self, tmp_path):
        """파일이 2개 이하면 trend 가 None (3개 미만 포인트 불충분)."""
        _write_results(tmp_path, [
            _make_result_json(tcr=90.0),
            _make_result_json(tcr=88.0),
        ])

        analyzer = RunTrendAnalyzer(str(tmp_path))
        report = analyzer.analyze()

        assert report.tcr_trend is None
        assert report.any_regression is False

    def test_missing_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            RunTrendAnalyzer("/nonexistent/path/xyz").analyze()

    def test_pattern_filters_files(self, tmp_path):
        """pattern 파라미터로 특정 파일만 분석."""
        for i in range(3):
            (tmp_path / f"quality_{i:03d}.json").write_text(
                json.dumps(_make_result_json(tcr=90.0)), encoding="utf-8"
            )
        (tmp_path / "baseline.json").write_text(
            json.dumps(_make_result_json(tcr=50.0)), encoding="utf-8"
        )

        analyzer = RunTrendAnalyzer(str(tmp_path), pattern="quality_*.json")
        report = analyzer.analyze()

        assert report.window == 3
        assert all("quality_" in r.path for r in report.runs)

    def test_skips_invalid_json(self, tmp_path):
        """손상된 JSON 파일은 건너뛴다."""
        (tmp_path / "result_000.json").write_text("{invalid json", encoding="utf-8")
        for i in range(1, 4):
            (tmp_path / f"result_{i:03d}.json").write_text(
                json.dumps(_make_result_json(tcr=90.0)), encoding="utf-8"
            )

        analyzer = RunTrendAnalyzer(str(tmp_path))
        report = analyzer.analyze()

        assert report.window == 3  # 손상 파일 1개 제외


# ---------------------------------------------------------------------------
# RunTrendReport 단위 테스트
# ---------------------------------------------------------------------------

class TestRunTrendReport:
    def test_any_regression_aggregates_trends(self):
        stable = MetricTrend("tcr", "TCR", 0.0, "stable", 90.0, 90.0, 5)
        degrading = MetricTrend("accuracy", "정확도", -1.0, "degrading", 85.0, 80.0, 5)

        report = RunTrendReport(
            results_dir="results/",
            window=5,
            pattern="*.json",
            tcr_trend=stable,
            accuracy_trend=degrading,
        )
        assert report.any_regression is True

    def test_no_regression_all_stable(self):
        report = RunTrendReport(
            results_dir="results/",
            window=5,
            pattern="*.json",
            tcr_trend=MetricTrend("tcr", "TCR", 0.1, "stable", 90.0, 90.5, 5),
        )
        assert report.any_regression is False

    def test_to_dict_structure(self, tmp_path):
        runs = [_make_result_json(tcr=float(90 - i)) for i in range(5)]
        _write_results(tmp_path, runs)

        report = RunTrendAnalyzer(str(tmp_path)).analyze()
        d = report.to_dict()

        assert "any_regression" in d
        assert "trends" in d
        assert "runs" in d
        assert "tcr" in d["trends"]
        assert len(d["runs"]) == 5


# ---------------------------------------------------------------------------
# cmd_trend CLI 핸들러 테스트
# ---------------------------------------------------------------------------

class TestCmdTrend:
    def _ns(self, results_dir, **kwargs) -> argparse.Namespace:
        defaults = {
            "pattern": "*.json",
            "window": 10,
            "slope_threshold": 0.3,
            "fail_on_regression": False,
            "output_json": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(results_dir=str(results_dir), **defaults)

    def test_returns_0_no_regression(self, tmp_path):
        runs = [_make_result_json(tcr=90.0) for _ in range(5)]
        _write_results(tmp_path, runs)

        code = cmd_trend(self._ns(tmp_path))
        assert code == 0

    def test_returns_0_without_fail_flag_even_on_regression(self, tmp_path):
        """--fail-on-regression 미지정 시 회귀가 있어도 0 반환."""
        runs = [_make_result_json(tcr=float(90 - i * 3)) for i in range(5)]
        _write_results(tmp_path, runs)

        code = cmd_trend(self._ns(tmp_path, fail_on_regression=False))
        assert code == 0

    def test_returns_1_with_fail_flag_on_regression(self, tmp_path):
        runs = [_make_result_json(tcr=float(90 - i * 3)) for i in range(5)]
        _write_results(tmp_path, runs)

        code = cmd_trend(self._ns(tmp_path, fail_on_regression=True))
        assert code == 1

    def test_returns_1_on_missing_directory(self, tmp_path):
        code = cmd_trend(self._ns(tmp_path / "nonexistent"))
        assert code == 1

    def test_output_json_written(self, tmp_path):
        runs = [_make_result_json(tcr=90.0) for _ in range(5)]
        _write_results(tmp_path, runs)
        out = tmp_path / "trend_out.json"

        cmd_trend(self._ns(tmp_path, output_json=str(out)))

        assert out.exists()
        data = json.loads(out.read_text())
        assert "any_regression" in data
        assert "trends" in data

    def test_window_option_respected(self, tmp_path):
        for i in range(8):
            (tmp_path / f"r_{i:03d}.json").write_text(
                json.dumps(_make_result_json(tcr=90.0)), encoding="utf-8"
            )
        out = tmp_path / "out.json"

        cmd_trend(self._ns(tmp_path, window=4, output_json=str(out)))

        data = json.loads(out.read_text())
        assert data["window"] == 4

    def test_slope_threshold_affects_direction(self, tmp_path):
        """slope_threshold를 높이면 작은 하락을 stable 로 처리."""
        runs = [_make_result_json(tcr=float(90 - i * 0.1)) for i in range(5)]
        _write_results(tmp_path, runs)
        out = tmp_path / "out.json"

        # 낮은 threshold: degrading
        cmd_trend(self._ns(tmp_path, slope_threshold=0.01, output_json=str(out)))
        data_low = json.loads(out.read_text())

        # 높은 threshold: stable
        cmd_trend(self._ns(tmp_path, slope_threshold=1.0, output_json=str(out)))
        data_high = json.loads(out.read_text())

        tcr_low = data_low["trends"]["tcr"]
        tcr_high = data_high["trends"]["tcr"]
        assert tcr_low is not None and tcr_low["direction"] == "degrading"
        assert tcr_high is not None and tcr_high["direction"] == "stable"
