"""
agent-eval trend — 순차 평가 결과 파일의 추세 분석.

여러 평가 실행 결과 JSON을 시간순으로 읽어 TCR·정확도·지연시간·환각률의
슬로프를 계산하고 지속적 하락 추세(회귀)를 감지한다.

종료 코드:
    0 — 회귀 없음 (또는 --fail-on-regression 미지정)
    1 — 회귀 감지 (--fail-on-regression 지정 시)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.cli.gate import _load_metrics


# ---------------------------------------------------------------------------
# ANSI 색상
# ---------------------------------------------------------------------------

_COLOR = _supports_color()

G  = "\033[32m" if _COLOR else ""
Y  = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B  = "\033[1m"  if _COLOR else ""
R  = "\033[0m"  if _COLOR else ""
D  = "\033[2m"  if _COLOR else ""
C  = "\033[36m" if _COLOR else ""

_SEP = "━" * 52


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class RunPoint:
    """단일 평가 실행에서 추출한 지표 스냅샷."""

    path: str
    tcr: Optional[float]
    accuracy: Optional[float]
    p95_latency: Optional[float]
    hallucination: Optional[float]
    total_cost: Optional[float] = None


@dataclass
class MetricTrend:
    """단일 지표의 추세 분석 결과."""

    metric: str                     # 지표 키
    label: str                      # 표시 이름
    slope: float                    # run당 변화율
    direction: str                  # "improving" | "degrading" | "stable"
    first_val: Optional[float]      # 윈도우 첫 값
    last_val: Optional[float]       # 윈도우 마지막 값
    data_points: int                # 유효 데이터 포인트 수

    @property
    def any_regression(self) -> bool:
        return self.direction == "degrading"


@dataclass
class RunTrendReport:
    """전체 추세 분석 보고서."""

    results_dir: str
    window: int                          # 분석에 사용된 파일 수
    pattern: str
    runs: List[RunPoint] = field(default_factory=list)
    tcr_trend: Optional[MetricTrend] = None
    accuracy_trend: Optional[MetricTrend] = None
    latency_trend: Optional[MetricTrend] = None
    hallucination_trend: Optional[MetricTrend] = None
    cost_trend: Optional[MetricTrend] = None

    @property
    def any_regression(self) -> bool:
        return any(
            t.any_regression
            for t in [
                self.tcr_trend,
                self.accuracy_trend,
                self.latency_trend,
                self.hallucination_trend,
                self.cost_trend,
            ]
            if t is not None
        )

    def to_dict(self) -> Dict:
        def _trend_dict(t: Optional[MetricTrend]) -> Optional[Dict]:
            if t is None:
                return None
            return {
                "metric": t.metric,
                "label": t.label,
                "slope": t.slope,
                "direction": t.direction,
                "first_val": t.first_val,
                "last_val": t.last_val,
                "data_points": t.data_points,
            }

        return {
            "results_dir": self.results_dir,
            "window": self.window,
            "pattern": self.pattern,
            "any_regression": self.any_regression,
            "runs": [
                {
                    "path": r.path,
                    "tcr": r.tcr,
                    "accuracy": r.accuracy,
                    "p95_latency": r.p95_latency,
                    "hallucination": r.hallucination,
                    "total_cost": r.total_cost,
                }
                for r in self.runs
            ],
            "trends": {
                "tcr": _trend_dict(self.tcr_trend),
                "accuracy": _trend_dict(self.accuracy_trend),
                "p95_latency": _trend_dict(self.latency_trend),
                "hallucination": _trend_dict(self.hallucination_trend),
                "total_cost": _trend_dict(self.cost_trend),
            },
        }


# ---------------------------------------------------------------------------
# 핵심 분석기
# ---------------------------------------------------------------------------

class RunTrendAnalyzer:
    """순차 평가 결과 JSON 파일에서 지표 추세를 분석한다.

    Args:
        results_dir: 결과 JSON 파일이 저장된 디렉토리.
        pattern: 파일 글로브 패턴 (기본: ``*.json``).
        window: 최근 N개 파일만 분석 (기본: 10).
        slope_threshold: 이 값 미만의 절댓값 slope는 "stable"로 판정 (기본: 0.3).
            단위는 지표 단위/run (TCR·정확도·환각률은 %, 지연시간은 초).

    Example:
        analyzer = RunTrendAnalyzer("results/", window=10)
        report = analyzer.analyze()
        if report.any_regression:
            sys.exit(1)
    """

    def __init__(
        self,
        results_dir: str,
        pattern: str = "*.json",
        window: int = 10,
        slope_threshold: float = 0.3,
    ) -> None:
        self.results_dir = Path(results_dir)
        self.pattern = pattern
        self.window = window
        self.slope_threshold = slope_threshold

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def analyze(self) -> RunTrendReport:
        """결과 디렉토리를 읽어 추세 보고서를 반환한다.

        Returns:
            RunTrendReport — 지표별 MetricTrend 포함.

        Raises:
            FileNotFoundError: results_dir 가 존재하지 않을 때.
        """
        if not self.results_dir.is_dir():
            raise FileNotFoundError(
                f"Results directory not found: {self.results_dir}"
            )

        files = sorted(self.results_dir.glob(self.pattern))[-self.window :]
        runs: List[RunPoint] = []
        for f in files:
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue
            m = _load_metrics(data)
            runs.append(
                RunPoint(
                    path=str(f),
                    tcr=m.get("tcr"),
                    accuracy=m.get("accuracy"),
                    p95_latency=m.get("p95_latency"),
                    hallucination=m.get("hallucination"),
                    total_cost=m.get("total_cost"),
                )
            )

        return RunTrendReport(
            results_dir=str(self.results_dir),
            window=len(runs),
            pattern=self.pattern,
            runs=runs,
            tcr_trend=self._trend(
                "tcr", "TCR", [r.tcr for r in runs], higher_is_better=True
            ),
            accuracy_trend=self._trend(
                "accuracy", "Accuracy", [r.accuracy for r in runs], higher_is_better=True
            ),
            latency_trend=self._trend(
                "p95_latency",
                "P95 Latency",
                [r.p95_latency for r in runs],
                higher_is_better=False,
            ),
            hallucination_trend=self._trend(
                "hallucination",
                "Hallucination Rate",
                [r.hallucination for r in runs],
                higher_is_better=False,
            ),
            cost_trend=self._trend(
                "total_cost",
                "Total Cost",
                [r.total_cost for r in runs],
                higher_is_better=False,
            ),
        )

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _trend(
        self,
        metric: str,
        label: str,
        values: List[Optional[float]],
        higher_is_better: bool,
    ) -> Optional[MetricTrend]:
        """값 목록에서 MetricTrend 를 계산한다.

        유효 데이터 포인트가 3개 미만이면 None 반환.
        """
        pts: List[Tuple[int, float]] = [
            (i, v) for i, v in enumerate(values) if v is not None
        ]
        if len(pts) < 3:
            return None

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        slope = _slope(xs, ys)

        thr = self.slope_threshold
        if abs(slope) < thr:
            direction = "stable"
        elif (slope > 0) == higher_is_better:
            direction = "improving"
        else:
            direction = "degrading"

        return MetricTrend(
            metric=metric,
            label=label,
            slope=slope,
            direction=direction,
            first_val=ys[0],
            last_val=ys[-1],
            data_points=len(pts),
        )


# ---------------------------------------------------------------------------
# 선형 회귀 (slope 계산)
# ---------------------------------------------------------------------------

def _slope(xs: List[float], ys: List[float]) -> float:
    """단순 선형 회귀 기울기(a)를 반환한다 (y = ax + b)."""
    n = len(xs)
    if n < 2:
        return 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    return num / den if den != 0.0 else 0.0


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

def _direction_icon(direction: str) -> str:
    return {"improving": f"{G}↑{R}", "degrading": f"{RD}↓{R}", "stable": f"{D}→{R}"}.get(
        direction, "?"
    )


def _direction_label(direction: str) -> str:
    return {
        "improving": f"{G}improving{R}",
        "degrading": f"{RD}degrading{R}",
        "stable": f"{D}stable{R}",
    }.get(direction, direction)


def _fmt(val: Optional[float], unit: str) -> str:
    if val is None:
        return f"{D}N/A{R}"
    if unit == "%":
        return f"{val:.1f}%"
    if unit == "s":
        return f"{val:.3f}s"
    if unit == "$":
        return f"${val:.4f}"
    return f"{val:.2f}"


_METRIC_UNIT = {
    "tcr": "%",
    "accuracy": "%",
    "p95_latency": "s",
    "hallucination": "%",
    "total_cost": "$",
}


def _print_report(report: RunTrendReport, slope_threshold: float) -> None:
    """추세 보고서를 터미널에 출력한다."""
    print()
    print(f"  {_SEP}")
    print(f"  {B}Agent Evaluator — Run Trend Analysis{R}")
    print(f"  Directory: {D}{report.results_dir}{R}")
    print(f"  Files analyzed: {report.window}  Pattern: {D}{report.pattern}{R}  slope threshold: {D}±{slope_threshold}{R}")
    print(f"  {_SEP}")

    # 파일 목록
    if report.runs:
        print()
        print(f"  {B}Analyzed run files{R}")
        for i, run in enumerate(report.runs, 1):
            fname = Path(run.path).name
            parts = []
            if run.tcr is not None:
                parts.append(f"TCR={run.tcr:.1f}%")
            if run.accuracy is not None:
                parts.append(f"acc={run.accuracy:.1f}%")
            if run.p95_latency is not None:
                parts.append(f"p95={run.p95_latency:.3f}s")
            if run.total_cost is not None:
                parts.append(f"cost=${run.total_cost:.4f}")
            summary = "  ".join(parts) if parts else f"{D}no metrics{R}"
            print(f"  {D}{i:>2}.{R} {fname:<52} {D}{summary}{R}")
        print()

    # 추세 테이블
    trends = [
        (report.tcr_trend, "tcr"),
        (report.accuracy_trend, "accuracy"),
        (report.latency_trend, "p95_latency"),
        (report.hallucination_trend, "hallucination"),
        (report.cost_trend, "total_cost"),
    ]
    active = [(t, k) for t, k in trends if t is not None]

    print(f"  {_SEP}")
    if not active:
        print(f"\n  {D}Not enough valid data points (minimum 3 per metric required).{R}\n")
        print(f"  {_SEP}\n")
        return

    print()
    hdr = f"  {'Metric':<18}  {'First':>9}  {'Last':>10}  {'slope/run':>10}  {'Trend':<14}  Points"
    print(hdr)
    print(f"  {'─' * 18}  {'─' * 9}  {'─' * 10}  {'─' * 10}  {'─' * 14}  ─────")

    for trend, mkey in active:
        unit = _METRIC_UNIT.get(mkey, "")
        icon = _direction_icon(trend.direction)
        dlabel = _direction_label(trend.direction)
        slope_str = f"{trend.slope:+.3f}{unit}/run"
        print(
            f"  {trend.label:<18}  {_fmt(trend.first_val, unit):>9}  "
            f"{_fmt(trend.last_val, unit):>10}  {slope_str:>10}  "
            f"{icon} {dlabel:<12}  {trend.data_points}"
        )

    print()
    print(f"  {_SEP}")

    # 요약
    regressions = [t for t, _ in active if t.any_regression]
    print()
    if not regressions:
        print(f"  {G}{B}✅ No regressions — all metrics are stable or improving.{R}")
    else:
        print(f"  {RD}{B}⚠  Regressions detected ({len(regressions)} metric(s)){R}")
        for t in regressions:
            unit = _METRIC_UNIT.get(t.metric, "")
            print(
                f"  {RD}  ↓  {t.label}{R}"
                f"  {_fmt(t.first_val, unit)} → {_fmt(t.last_val, unit)}"
                f"  (slope {t.slope:+.3f}{unit}/run)"
            )
        print()
        print(f"  {D}→ Use --fail-on-regression to fail the CI step on regression.{R}")

    print(f"  {_SEP}")
    print()


# ---------------------------------------------------------------------------
# cmd_trend (CLI 핸들러)
# ---------------------------------------------------------------------------

def cmd_trend(args: argparse.Namespace) -> int:
    """trend 서브커맨드 핸들러.

    Args:
        args: argparse.Namespace — CLI 인수.

    Returns:
        종료 코드 (0=회귀 없음, 1=회귀 감지 또는 오류).

    Example:
        import argparse
        ns = argparse.Namespace(
            results_dir="results/",
            pattern="*.json",
            window=10,
            slope_threshold=0.3,
            fail_on_regression=False,
            output_json=None,
        )
        exit_code = cmd_trend(ns)
    """
    analyzer = RunTrendAnalyzer(
        results_dir=args.results_dir,
        pattern=args.pattern,
        window=args.window,
        slope_threshold=args.slope_threshold,
    )

    try:
        report = analyzer.analyze()
    except FileNotFoundError as exc:
        print(f"{RD}❌ {exc}{R}", file=sys.stderr)
        return 1

    if getattr(args, "output_json", None):
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"{D}JSON saved: {args.output_json}{R}")

    _print_report(report, args.slope_threshold)

    if args.fail_on_regression and report.any_regression:
        return 1

    return 0


# ---------------------------------------------------------------------------
# argparse 서브파서 빌더 (main.py에서 호출)
# ---------------------------------------------------------------------------

def build_trend_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """trend 서브커맨드를 argparse 서브파서에 등록한다."""
    from agent_evaluator.cli._utils import _supports_color  # noqa: F401 — color guard

    p = sub.add_parser(
        "trend",
        help="Analyze metric trends across sequential evaluation runs (TCR/accuracy regression detection)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Read JSON result files in a directory in chronological order and\n"
            "analyze trends in TCR, accuracy, P95 latency, and hallucination rate.\n"
            "\n"
            "Computes a linear slope per metric to detect sustained decline;\n"
            "use --fail-on-regression to abort a CI/CD pipeline on regression.\n"
            "\n"
            "Exit codes:\n"
            "  0 — no regression\n"
            "  1 — regression detected (when --fail-on-regression is set)\n"
        ),
        epilog=(
            "Examples:\n"
            "  agent-eval trend results/\n"
            "  agent-eval trend results/ --window 5\n"
            "  agent-eval trend results/ --fail-on-regression\n"
            "  agent-eval trend results/ --pattern '*quality*.json' --window 20\n"
            "  agent-eval trend results/ --slope-threshold 0.5 --output-json trend.json\n"
        ),
    )
    p.add_argument(
        "results_dir",
        help="Directory containing evaluation result JSON files",
    )
    p.add_argument(
        "--window", "-w",
        type=int,
        default=10,
        metavar="N",
        help="Number of most recent files to analyze (default: 10)",
    )
    p.add_argument(
        "--pattern",
        default="*.json",
        metavar="GLOB",
        help="Filename glob pattern (default: '*.json')",
    )
    p.add_argument(
        "--slope-threshold",
        type=float,
        default=0.3,
        dest="slope_threshold",
        metavar="FLOAT",
        help=(
            "Slopes below this absolute value are classified as 'stable' (default: 0.3).\n"
            "Unit: %%/run (TCR·accuracy·hallucination), s/run (latency)"
        ),
    )
    p.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        dest="fail_on_regression",
        help="Return exit code 1 on regression (CI/CD failure)",
    )
    p.add_argument(
        "--output-json",
        default=None,
        dest="output_json",
        metavar="PATH",
        help="Save analysis results to a JSON file",
    )
