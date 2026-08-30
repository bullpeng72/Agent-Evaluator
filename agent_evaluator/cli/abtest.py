"""
agent-eval abtest — 결과 JSON 파일 2개 이상을 통계적으로 비교하는 CLI.

``QuickEval.ab_test()``/``ab_test_nway()``/``ab_test_sequential()``를 감싸는 얇은
터미널 출력 레이어다 — 새 통계 로직은 없다. 두 파일을 주면 Welch's t-test(또는
``--sequential`` 지정 시 mSPRT always-valid inference), 세 파일 이상을 주면
Benjamini-Hochberg FDR 보정을 적용한 N-way pairwise 비교로 자동 전환된다.

이 명령은 CI 게이트가 아니다(``agent-eval gate``와 다르다) — 유의성·효과크기·
표본 충분성 경고를 출력할 뿐 pass/fail을 판정하지 않는다. "통계적으로 유의하다"와
"배포해도 된다"는 다른 판단이며, 후자는 여전히 사람의 몫이다.

종료 코드:
    0 — 비교 정상 완료(유의하지 않아도, guardrail이 실패해도 0)
    1 — 결과 파일을 읽을 수 없거나 파일 수가 부족함(최소 2개)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent_evaluator.cli._utils import _supports_color
from agent_evaluator.quick_eval import QuickEval

_COLOR = _supports_color()
G = "\033[32m" if _COLOR else ""
Y = "\033[33m" if _COLOR else ""
RD = "\033[31m" if _COLOR else ""
B = "\033[1m" if _COLOR else ""
R = "\033[0m" if _COLOR else ""
D = "\033[2m" if _COLOR else ""


def _load_quickeval(path: str) -> QuickEval | None:
    """결과 JSON 파일을 읽어 QuickEval 인스턴스로 감싼다.

    ``ab_test()``/``ab_test_nway()``/``ab_test_sequential()``는 모두
    ``QuickEval._monitor.tasks``(``TaskResult`` 객체 리스트)를 읽으므로,
    ``PerformanceMonitor.load_from_file()``이 이미 하는 재구성 작업을 그대로
    재사용한다 — 새 파싱 로직을 만들지 않는다.
    """
    from agent_evaluator.core.trackers.monitor import PerformanceMonitor

    if not Path(path).is_file():
        return None
    try:
        monitor = PerformanceMonitor.load_from_file(path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None
    qe = QuickEval(output_dir=None)
    qe._monitor = monitor
    return qe


def _variant_names(paths: list[str]) -> list[str]:
    """파일 경로에서 표시용 변형 이름을 만든다 — basename이 겹치면 전체 경로로 대체."""
    stems = [Path(p).stem for p in paths]
    if len(set(stems)) == len(stems):
        return stems
    return paths


def _parse_guardrail(spec: str) -> dict[str, Any]:
    """``METRIC:DIRECTION:MAX_REGRESSION`` 형식을 guardrail dict로 변환."""
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid --guardrail format: {spec!r} "
            "(format: METRIC:higher_is_better|lower_is_better:MAX_REGRESSION)"
        )
    metric, direction, max_regression = parts
    if direction not in ("higher_is_better", "lower_is_better"):
        raise ValueError(
            f"--guardrail direction must be 'higher_is_better' or 'lower_is_better': "
            f"{direction!r} (metric={metric!r})"
        )
    return {"metric": metric, "direction": direction, "max_regression": float(max_regression)}


def _print_mde(result: dict[str, Any]) -> None:
    """Minimum detectable effect at 80% power for this sample size (P10).

    Only meaningful for a proportion-like metric (both means in [0, 1]) — for
    latency/token metrics we skip it. Turns "not significant" into an actionable
    statement: is the difference genuinely small, or is the sample just too small
    to tell?
    """
    try:
        from agent_evaluator.utils.confidence import mde_two_proportions
    except Exception:
        return
    m_a = result.get("self_mean")
    m_b = result.get("other_mean")
    n_a = (result.get("sample_sizes") or {}).get("self", 0)
    n_b = (result.get("sample_sizes") or {}).get("other", 0)
    if not all(isinstance(x, (int, float)) for x in (m_a, m_b)):
        return
    if not (0.0 <= m_a <= 1.0 and 0.0 <= m_b <= 1.0):
        return  # not a proportion-like metric — MDE for proportions doesn't apply
    p_pooled = (m_a * n_a + m_b * n_b) / max(n_a + n_b, 1)
    mde = mde_two_proportions(n_a, n_b, p_pooled)
    if mde is None:
        return
    observed = abs(result.get("delta") or 0.0)
    print(
        f"  {D}min detectable effect @ 80% power (α=0.05): "
        f"±{mde:.4f} — observed |delta| {observed:.4f}{R}"
    )
    if not result.get("significant") and observed < mde:
        print(
            f"  {Y}⚠ the observed difference is smaller than this sample can reliably "
            f"detect — underpowered, not evidence the versions are equivalent. "
            f"Collect more tasks or run --sequential.{R}"
        )


def _print_two_way(result: dict[str, Any], name_a: str, name_b: str) -> None:
    metric = result["metric"]
    print(f"{D}Metric: {metric}{R}")
    print(f"  {name_a}: mean={result['self_mean']:.6f}  n={result['sample_sizes']['self']}")
    print(f"  {name_b}: mean={result['other_mean']:.6f}  n={result['sample_sizes']['other']}")

    delta = result["delta"]
    _delta_color = G if delta > 0 else (RD if delta < 0 else D)
    better = {"self": name_a, "other": name_b, "equal": "equal"}[result["better"]]
    print(f"\n  delta: {_delta_color}{delta:+.6f}{R}  ({better} ahead)")

    if result["t_statistic"] is not None:
        print(f"  t-statistic: {result['t_statistic']:.4f}   p-value: {result['p_value']:.4f}")
        if result["effect_size_cohens_d"] is not None:
            print(f"  effect size (Cohen's d): {result['effect_size_cohens_d']:.4f}")
        _sig_color = G if result["significant"] else D
        _sig_text = "significant (p < 0.05)" if result["significant"] else "not significant"
        print(f"  {_sig_color}Statistically {_sig_text}{R}")
    else:
        print(f"  {Y}⚠ scipy not installed — skipping t-test/effect size (pip install scipy){R}")

    _print_mde(result)

    if result["sample_size_warning"]:
        print(f"  {Y}⚠ {result['sample_size_warning']}{R}")

    guardrails = result.get("guardrail_results") or []
    if guardrails:
        print(f"\n  {D}Guardrail Metrics:{R}")
        for g in guardrails:
            _status = f"{G}PASS{R}" if g["passed"] else f"{RD}FAIL{R}"
            print(
                f"    {g['metric']} ({g['direction']}, max_regression={g['max_regression']}): "
                f"{name_a}={g['self_mean']} {name_b}={g['other_mean']} → {_status}"
            )
        _overall = f"{G}PASS{R}" if result["guardrails_passed"] else f"{RD}FAIL{R}"
        print(f"  {D}Guardrails overall: {_overall}")


def _print_sequential(result: dict[str, Any], name_a: str, name_b: str) -> None:
    metric = result["metric"]
    print(f"{D}Metric: {metric}  (mSPRT always-valid inference, tau={result['tau']}){R}")
    print(f"  {name_a}: mean={result['self_mean']:.6f}  n={result['sample_sizes']['self']}")
    print(f"  {name_b}: mean={result['other_mean']:.6f}  n={result['sample_sizes']['other']}")
    print(f"\n  delta: {result['delta']:+.6f}")

    if result["warning"]:
        print(f"  {Y}⚠ {result['warning']}{R}")
        return

    print(
        f"  always-valid p-value: {result['always_valid_p_value']:.6f}  (alpha={result['alpha']})"
    )
    _sig_color = G if result["significant"] else D
    _sig_text = "significant" if result["significant"] else "not significant"
    print(f"  {_sig_color}Statistically {_sig_text}{R}")
    print(
        f"  {D}This verdict is always-valid, so no matter how many times you've checked "
        f"so far (peeking), the false-positive rate stays within alpha.{R}"
    )


def _print_nway(result: dict[str, Any]) -> None:
    metric = result["metric"]
    print(
        f"{D}Metric: {metric}  (N-way, Benjamini-Hochberg FDR correction, "
        f"alpha={result['fdr_alpha']}){R}"
    )
    print(f"\n  {D}Per-variant means:{R}")
    for name, stats in result["variant_stats"].items():
        print(f"    {name}: mean={stats['mean']:.6f}  n={stats['n']}")

    for w in result["sample_size_warnings"]:
        print(f"  {Y}⚠ {w}{R}")

    print(f"\n  {D}Pairwise comparisons:{R}")
    for p in result["pairwise"]:
        _sig_raw = "significant" if p["significant"] else "n.s."
        _sig_fdr = "significant" if p["significant_fdr"] else "n.s."
        _color = G if p["significant_fdr"] else D
        _p = f"{p['p_value']:.4f}" if p["p_value"] is not None else "n/a"
        _p_fdr = (
            f"{p['p_value_fdr_adjusted']:.4f}" if p["p_value_fdr_adjusted"] is not None else "n/a"
        )
        print(
            f"    {_color}{p['a']} vs {p['b']}: delta={p['delta']:+.6f}  "
            f"p={_p}({_sig_raw})  p_fdr={_p_fdr}({_sig_fdr}){R}"
        )


def cmd_abtest(args: argparse.Namespace) -> int:
    result_files: list[str] = args.result_files
    if len(result_files) < 2:
        print(
            f"{RD}❌ At least 2 result files are required (got: {len(result_files)}){R}",
            file=sys.stderr,
        )
        return 1

    loaded: list[QuickEval] = []
    for path in result_files:
        qe = _load_quickeval(path)
        if qe is None:
            print(f"{RD}❌ Could not read result file: {path}{R}", file=sys.stderr)
            return 1
        loaded.append(qe)

    names = _variant_names(result_files)

    guardrails: list[dict[str, Any]] | None = None
    if args.guardrail:
        try:
            guardrails = [_parse_guardrail(spec) for spec in args.guardrail]
        except ValueError as e:
            print(f"{RD}❌ {e}{R}", file=sys.stderr)
            return 1

    if len(loaded) > 2:
        if args.sequential:
            print(
                f"{RD}❌ --sequential can only be used with exactly 2 result files{R}",
                file=sys.stderr,
            )
            return 1
        if guardrails:
            print(
                f"{RD}❌ --guardrail can only be used with exactly 2 result files{R}",
                file=sys.stderr,
            )
            return 1
        result = QuickEval.ab_test_nway(
            dict(zip(names, loaded)),
            metric=args.metric,
            fdr_alpha=args.fdr_alpha,
            min_recommended_samples=args.min_samples,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        print(f"{B}N-way A/B Test{R} — comparing {len(loaded)} versions")
        _print_nway(result)
        print(f"\n{D}Significance is statistical evidence only — the deploy decision is yours.{R}")
        return 0

    name_a, name_b = names
    qe_a, qe_b = loaded

    if args.sequential:
        if args.tau is None:
            print(
                f"{RD}❌ --sequential requires --tau (no implicit default){R}",
                file=sys.stderr,
            )
            return 1
        result = qe_a.ab_test_sequential(qe_b, metric=args.metric, tau=args.tau, alpha=args.alpha)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        print(f"{B}A/B Test (Sequential/mSPRT){R} — {name_a} vs {name_b}")
        _print_sequential(result, name_a, name_b)
        print(f"\n{D}Significance is statistical evidence only — the deploy decision is yours.{R}")
        return 0

    result = qe_a.ab_test(
        qe_b,
        metric=args.metric,
        guardrails=guardrails,
        min_recommended_samples=args.min_samples,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"{B}A/B Test{R} — {name_a} vs {name_b}")
    _print_two_way(result, name_a, name_b)
    print(f"\n{D}Significance is statistical evidence only — the deploy decision is yours.{R}")
    return 0


def build_abtest_subparser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """abtest 서브커맨드를 argparse 서브파서에 등록한다."""
    p = sub.add_parser(
        "abtest",
        help="Statistical A/B comparison of 2+ evaluation result JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Compare 2 or more evaluation result JSON files on a metric — significance,\n"
            "effect size, and sample-size warnings. Not a CI gate: reports statistical\n"
            "evidence only, never a pass/fail verdict.\n"
            "\n"
            "2 files -> Welch's t-test (QuickEval.ab_test()). Add --sequential for\n"
            "mSPRT always-valid inference (safe to check results as they come in).\n"
            "3+ files -> N-way pairwise comparison with Benjamini-Hochberg FDR\n"
            "correction (QuickEval.ab_test_nway())."
        ),
        epilog=(
            f"{B}Examples:{R}\n"
            f"  {G}agent-eval abtest results/v1.json results/v2.json{R}\n"
            f"  {G}agent-eval abtest results/v1.json results/v2.json --metric execution_time{R}\n"
            f"  {G}agent-eval abtest results/v1.json results/v2.json "
            f"--guardrail latency_ms:lower_is_better:0.5{R}\n"
            f"  {G}agent-eval abtest results/v1.json results/v2.json --sequential --tau 0.05{R}\n"
            f"  {G}agent-eval abtest results/v1.json results/v2.json results/v3.json{R}\n"
            f"  {G}agent-eval abtest results/*.json --json{R}\n"
        ),
    )
    p.add_argument(
        "result_files",
        nargs="+",
        metavar="RESULT_FILE",
        help="2 or more evaluation result JSON file paths",
    )
    p.add_argument(
        "--metric",
        default="accuracy_score",
        help="TaskResult attribute or task.extra key to compare (default: accuracy_score)",
    )
    p.add_argument(
        "--guardrail",
        action="append",
        metavar="METRIC:DIRECTION:MAX_REGRESSION",
        dest="guardrail",
        help=(
            "Guardrail Metric (OEC) — repeatable. DIRECTION is 'higher_is_better' or "
            "'lower_is_better' (required, no implicit default). Only valid with exactly "
            "2 result files, not with --sequential."
        ),
    )
    p.add_argument(
        "--sequential",
        action="store_true",
        help="Use mSPRT always-valid inference instead of a fixed-sample t-test. Requires --tau.",
    )
    p.add_argument(
        "--tau",
        type=float,
        default=None,
        help="Mixture prior scale for --sequential (no implicit default — "
        "see 'agent-eval abtest --help').",
    )
    p.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level for --sequential (default: 0.05)",
    )
    p.add_argument(
        "--fdr-alpha",
        type=float,
        default=0.05,
        dest="fdr_alpha",
        help="Significance level after FDR correction, for 3+ files (default: 0.05)",
    )
    p.add_argument(
        "--min-samples",
        type=int,
        default=30,
        dest="min_samples",
        help="Sample count below which a sample-size warning is shown (default: 30)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the raw comparison result as JSON instead of the formatted report",
    )
