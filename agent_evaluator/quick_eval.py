"""
agent_evaluator.quick_eval
==========================
QuickEval — 원스톱 평가 Facade.

PerformanceMonitor 생성, 데코레이터 적용, 결과 저장을 단 몇 줄로 해결한다.

Quick Start::

    from agent_evaluator import QuickEval

    # 1줄로 시작
    eval = QuickEval("results/")

    @eval.qa
    def my_agent(question: str, ground_truth: str = "") -> str:
        return llm.predict(question)

    # 실행
    my_agent("한국의 수도는?", ground_truth="서울")

    # 저장
    eval.save()

    # CI/CD 게이팅
    eval.gate(tcr=85, accuracy=70)
"""
from __future__ import annotations

import functools
import logging
import re
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = ["QuickEval", "HarnessEvaluationGate", "CompareResult"]

# ---------------------------------------------------------------------------
# ANSI helpers (터미널 색상 — 미지원 환경에서는 공백 문자열)
# ---------------------------------------------------------------------------
def _ansi_support() -> bool:
    import sys, os
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and os.name != "nt"

_USE_COLOR = _ansi_support()
_G  = "\033[32m" if _USE_COLOR else ""   # green
_Y  = "\033[33m" if _USE_COLOR else ""   # yellow
_RD = "\033[31m" if _USE_COLOR else ""   # red
_B  = "\033[1m"  if _USE_COLOR else ""   # bold
_R  = "\033[0m"  if _USE_COLOR else ""   # reset
_D  = "\033[2m"  if _USE_COLOR else ""   # dim
_C  = "\033[36m" if _USE_COLOR else ""   # cyan

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))

def _pad_right(s: str, w: int) -> str:
    return s + " " * max(0, w - _vlen(s))

def _pad_left(s: str, w: int) -> str:
    return " " * max(0, w - _vlen(s)) + s


# ---------------------------------------------------------------------------
# CompareResult
# ---------------------------------------------------------------------------

class CompareResult:
    """QuickEval.compare() 반환값.

    ``print(result)`` 시 컬러 비교 테이블을 출력하고,
    ``result["delta"]["tcr"]`` 처럼 기존 dict 접근도 그대로 지원한다.

    Attributes:
        self_name:  첫 번째 eval의 레이블 (기본 "eval_a").
        other_name: 두 번째 eval의 레이블 (기본 "eval_b").
        winner:     "self" | "other" | "tie" — 더 높은 TCR 기준.

    Example::

        result = eval_a.compare(eval_b)
        print(result)                       # 테이블 출력
        result["delta"]["tcr"]              # -32.5
        result.winner                       # 'other'
        result.to_dict()                    # 기존 raw dict
    """

    # (key, 표시명, 단위, 방향)  방향: "high"=높을수록 좋음, "low"=낮을수록 좋음
    _ROWS = [
        ("tcr",              "TCR",            "%",   "high"),
        ("accuracy",         "Accuracy",       "%",   "high"),
        ("quality_avg",      "Quality Avg",    "%",   "high"),
        ("hallucination_rate","Hallucination", "%",   "low"),
        ("p95_latency",      "P95 Latency",    "s",   "low"),
        ("avg_latency",      "Avg Latency",    "s",   "low"),
        ("total_cost_usd",   "Cost",           "USD", "low"),
        ("total_tokens",     "Total Tokens",   "",    "low"),
        ("total_tasks",      "Total Tasks",    "",    ""),
    ]

    def __init__(
        self,
        self_summary: Dict[str, Any],
        other_summary: Dict[str, Any],
        delta: Dict[str, Any],
        self_name: str = "eval_a",
        other_name: str = "eval_b",
    ) -> None:
        self._self   = self_summary
        self._other  = other_summary
        self._delta  = delta
        self.self_name  = self_name
        self.other_name = other_name

    # ------------------------------------------------------------------
    # dict 호환
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        mapping = {"self": self._self, "other": self._other, "delta": self._delta}
        if key not in mapping:
            raise KeyError(key)
        return mapping[key]

    def __contains__(self, key: object) -> bool:
        return key in ("self", "other", "delta")

    def __iter__(self) -> Iterator[str]:
        return iter(("self", "other", "delta"))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """기존 raw dict 구조로 반환한다."""
        return {"self": self._self, "other": self._other, "delta": self._delta}

    # ------------------------------------------------------------------
    # winner 판정
    # ------------------------------------------------------------------

    @property
    def winner(self) -> str:
        """TCR 기준 우세한 쪽. "self" | "other" | "tie"."""
        st = self._self.get("tcr", 0.0) or 0.0
        ot = self._other.get("tcr", 0.0) or 0.0
        if st > ot:
            return "self"
        if ot > st:
            return "other"
        return "tie"

    def _winner_label(self) -> str:
        w = self.winner
        if w == "self":
            return self.self_name
        if w == "other":
            return self.other_name
        return "tie"

    # ------------------------------------------------------------------
    # 포맷 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt(val: Any, unit: str) -> str:
        if val is None:
            return "N/A"
        try:
            v = float(val)
        except (TypeError, ValueError):
            return str(val)
        if unit == "%":
            return f"{v:.1f}%"
        if unit == "s":
            return f"{v:.3f}s"
        if unit == "USD":
            return f"${v:.4f}"
        if unit == "":
            return f"{int(v):,}"
        return f"{v:.2f}"

    @staticmethod
    def _fmt_delta(val: Any, unit: str, direction: str) -> str:
        if val is None:
            return "N/A"
        try:
            v = float(val)
        except (TypeError, ValueError):
            return str(val)

        sign = "+" if v > 0 else ""
        if unit == "%":
            raw = f"{sign}{v:.1f}pp"
        elif unit == "s":
            raw = f"{sign}{v:.3f}s"
        elif unit == "USD":
            raw = f"{sign}${v:.4f}"
        else:
            raw = f"{sign}{int(v):,}" if unit == "" else f"{sign}{v:.2f}"

        if direction == "":
            return f"{_D}{raw}{_R}"

        good = (direction == "high" and v > 0) or (direction == "low" and v < 0)
        bad  = (direction == "high" and v < 0) or (direction == "low" and v > 0)
        arrow = " ▲" if v > 0 else (" ▼" if v < 0 else "")
        if good:
            return f"{_G}{raw}{arrow}{_R}"
        if bad:
            return f"{_RD}{raw}{arrow}{_R}"
        return f"{_D}{raw}{_R}"

    # ------------------------------------------------------------------
    # 테이블 렌더링
    # ------------------------------------------------------------------

    def _build_table(self) -> str:
        meta_s = self._self.get("_meta", {})
        meta_o = self._other.get("_meta", {})

        COL_METRIC = 18
        COL_VAL    = 14
        COL_DELTA  = 14
        SEP  = "═" * (COL_METRIC + COL_VAL * 2 + COL_DELTA + 8)
        SEP2 = "─" * (COL_METRIC + COL_VAL * 2 + COL_DELTA + 8)

        lines: List[str] = []
        lines.append(f"  {_B}{SEP}{_R}")
        lines.append(f"  {_B}QuickEval Comparison{_R}")
        lines.append(f"  {SEP}")
        lines.append("")

        # 헤더
        h_metric = _pad_right(f"{_B}Metric{_R}", COL_METRIC)
        h_self   = _pad_right(f"{_B}{self.self_name}{_R}", COL_VAL)
        h_other  = _pad_right(f"{_B}{self.other_name}{_R}", COL_VAL)
        h_delta  = f"{_B}Delta (a−b){_R}"
        lines.append(f"  {h_metric}  {h_self}  {h_other}  {h_delta}")
        lines.append(f"  {SEP2}")

        active_rows = 0
        for key, label, unit, direction in self._ROWS:
            sv = self._self.get(key)
            ov = self._other.get(key)

            # computed 여부 확인
            meta_key = f"{key}_computed"
            s_computed = meta_s.get(meta_key, True)
            o_computed = meta_o.get(meta_key, True)

            # 양쪽 모두 0이고 computed=False이면 스킵
            sv_f = float(sv) if sv is not None else 0.0
            ov_f = float(ov) if ov is not None else 0.0
            if sv_f == 0.0 and ov_f == 0.0 and not s_computed and not o_computed:
                continue

            active_rows += 1
            dv = self._delta.get(key)

            s_fmt = self._fmt(sv, unit)
            o_fmt = self._fmt(ov, unit)
            d_fmt = self._fmt_delta(dv, unit, direction)

            # 승자 강조
            if direction in ("high", "low") and sv is not None and ov is not None:
                if direction == "high":
                    s_better = sv_f > ov_f
                else:
                    s_better = sv_f < ov_f
                o_better = not s_better and sv_f != ov_f

                if s_better:
                    s_fmt = f"{_G}{s_fmt} ✓{_R}"
                elif o_better:
                    o_fmt = f"{_G}{o_fmt} ✓{_R}"

            col_metric = _pad_right(label, COL_METRIC)
            col_s      = _pad_right(s_fmt, COL_VAL)
            col_o      = _pad_right(o_fmt, COL_VAL)
            lines.append(f"  {col_metric}  {col_s}  {col_o}  {d_fmt}")

        lines.append(f"  {SEP}")

        # 승자 배너
        w = self.winner
        winner_label = self._winner_label()
        tcr_s = self._self.get("tcr", 0.0) or 0.0
        tcr_o = self._other.get("tcr", 0.0) or 0.0
        acc_s = self._self.get("accuracy", 0.0) or 0.0
        acc_o = self._other.get("accuracy", 0.0) or 0.0
        dtcr  = self._delta.get("tcr", 0.0) or 0.0
        dacc  = self._delta.get("accuracy", 0.0) or 0.0

        if w == "tie":
            lines.append(f"  {_Y}{_B}🤝  Tie  (TCR equal){_R}")
        else:
            tcr_diff  = abs(dtcr)
            acc_diff  = abs(dacc)
            detail_parts = []
            if tcr_diff  > 0: detail_parts.append(f"TCR {tcr_diff:+.1f}pp")
            if acc_diff  > 0: detail_parts.append(f"Accuracy {acc_diff:+.1f}pp")
            detail = ", ".join(detail_parts) if detail_parts else ""
            lines.append(
                f"  {_G}{_B}🏆  {winner_label} wins"
                + (f"  ({detail})" if detail else "")
                + f"{_R}"
            )

        lines.append(f"  {SEP}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return self._build_table()

    def __repr__(self) -> str:
        return (
            f"CompareResult(winner={self.winner!r}, "
            f"self_tcr={self._self.get('tcr')}, "
            f"other_tcr={self._other.get('tcr')})"
        )


class _QuickEvalBatchShortcut:
    """QuickEval.batch 속성 반환 객체 — @eval.batch / @eval.batch() 모두 지원."""

    def __init__(self, eval_decorator: Any) -> None:
        self._eval = eval_decorator

    def __call__(self, func_or_kwargs: Any = None, **kwargs: Any) -> Any:
        if callable(func_or_kwargs):
            return self._eval.batch()(func_or_kwargs)
        elif func_or_kwargs is None:
            return self._eval.batch(**kwargs)
        else:
            raise TypeError(
                f"_QuickEvalBatchShortcut: expected a callable or keyword arguments, "
                f"got {type(func_or_kwargs).__name__!r}"
            )


class _QuickEvalChatShortcut:
    """QuickEval.chat 속성 반환 객체 — @eval.chat / @eval.chat() 모두 지원."""

    def __init__(self, eval_decorator: Any) -> None:
        self._eval = eval_decorator

    def __call__(self, func_or_kwargs: Any = None, **kwargs: Any) -> Any:
        if callable(func_or_kwargs):
            return self._eval.conversation()(func_or_kwargs)
        elif func_or_kwargs is None:
            return self._eval.conversation(**kwargs)
        else:
            raise TypeError(
                f"_QuickEvalChatShortcut: expected a callable or keyword arguments, "
                f"got {type(func_or_kwargs).__name__!r}"
            )


class QuickEval:
    """원스톱 평가 Facade — PerformanceMonitor + EvalDecorator 를 단순화한 인터페이스.

    Args:
        output_dir: 결과 저장 디렉토리 (기본: ``"results/"``).
        auto_save: True 이면 ``auto_save_interval`` 건마다 자동 저장.
        auto_save_interval: auto_save 주기 (기본: 10).
        auto_save_filename: auto_save 파일명 (기본: ``"quickeval_auto"``).
        alert_rules: 모든 데코레이터에 적용할 :class:`SimpleTaskAlertRule` 리스트.
        flush_every: N 번 호출마다 ``save_to_file()`` 자동 실행 (0 = 비활성).
        flush_filename: flush 저장 파일명 (기본: ``"quickeval_flush"``).
        instructions: :class:`InstructionConfig` — 응답 형식·키워드 준수 추적.
        goal_alignment: :class:`GoalAlignmentConfig` — 목표-도구 정렬 추적.
        plan_tracking: :class:`PlanConfig` — 계획 일관성 추적.
        loop_detection: :class:`LoopDetectionConfig` — 도구 호출 루프 감지.
        scope: :class:`ScopeConfig` — 도구 사용 범위 경계 설정.
        sla: :class:`SLAConfig` — SLA 준수 추적.
        threat_severity: :class:`ThreatSeverityConfig` — 보안 위협 심각도 설정.
        compliance: :class:`ComplianceConfig` — PII·컴플라이언스 위반 추적.
        fault_tolerance: :class:`FaultToleranceConfig` — 장애 내성 추적.
        reproducibility: :class:`ReproducibilityConfig` — 재현성 추적.
        observability: :class:`ObservabilityConfig` — 트레이스 완성도 설정.
        explainability: :class:`ExplainabilityConfig` — 응답 설명 가능성 설정.
        consensus: :class:`ConsensusConfig` — 멀티에이전트 합의 품질 설정.
        **monitor_kwargs: :class:`PerformanceMonitor` 에 전달할 추가 파라미터.

    Examples::

        # 기본 사용
        eval = QuickEval("results/")

        @eval.qa
        def agent(question, ground_truth=""): ...

        @eval.tool_use
        def tool_agent(question, ground_truth=""): ...

        @eval.rag
        def rag_agent(question, context="", ground_truth=""): ...

        eval.save()
        eval.gate(tcr=85)

        # Harness Config 통합
        from agent_evaluator import InstructionConfig, SLAConfig
        eval = QuickEval(
            "results/",
            instructions=InstructionConfig(required_keywords=["result"]),
            sla=SLAConfig(p95_ms=3000),
        )

        @eval.qa
        def my_agent(question, ground_truth=""): ...

        eval.harness_gate(min_group_score=0.7)

        # RAG 특화 (hallucination 자동 활성화)
        eval = QuickEval.for_rag("results/")

        # 보안 특화
        eval = QuickEval.for_security("results/")

        # 자동 저장
        eval = QuickEval("results/", auto_save=True, auto_save_interval=5)
    """

    def __init__(
        self,
        output_dir: str = "results/",
        *,
        auto_save: bool = False,
        auto_save_interval: int = 10,
        auto_save_filename: str = "quickeval_auto",
        alert_rules: Optional[List[Any]] = None,
        flush_every: int = 0,
        flush_filename: str = "quickeval_flush",
        # Harness Config 그룹별 파라미터
        instructions: Optional[Any] = None,         # InstructionConfig
        goal_alignment: Optional[Any] = None,        # GoalAlignmentConfig
        plan_tracking: Optional[Any] = None,         # PlanConfig
        loop_detection: Optional[Any] = None,        # LoopDetectionConfig
        scope: Optional[Any] = None,                 # ScopeConfig
        sla: Optional[Any] = None,                   # SLAConfig
        threat_severity: Optional[Any] = None,       # ThreatSeverityConfig
        compliance: Optional[Any] = None,            # ComplianceConfig
        fault_tolerance: Optional[Any] = None,       # FaultToleranceConfig
        reproducibility: Optional[Any] = None,       # ReproducibilityConfig
        observability: Optional[Any] = None,         # ObservabilityConfig
        explainability: Optional[Any] = None,        # ExplainabilityConfig
        consensus: Optional[Any] = None,             # ConsensusConfig
        **monitor_kwargs: Any,
    ) -> None:
        import inspect as _inspect
        import warnings as _warnings
        from agent_evaluator.core.trackers.monitor import PerformanceMonitor
        from agent_evaluator.decorators import EvalDecorator

        # H1: monitor_kwargs 유효성 검사 — 잘못된 파라미터를 조기에 경고
        if monitor_kwargs:
            try:
                _valid_pm_params = (
                    set(_inspect.signature(PerformanceMonitor.__init__).parameters.keys())
                    - {"self"}
                )
                _invalid = set(monitor_kwargs) - _valid_pm_params
                if _invalid:
                    _warnings.warn(
                        f"QuickEval: Unknown parameters passed to PerformanceMonitor "
                        f"(ignored): {sorted(_invalid)}",
                        UserWarning,
                        stacklevel=2,
                    )
                    for _k in _invalid:
                        monitor_kwargs.pop(_k)
            except Exception as _e:
                logger.debug("QuickEval.__init__: monitor_kwargs validation failed (ignored): %s", _e)

        # Harness defaults — None이 아닌 파라미터만 저장
        self._harness_defaults: Dict[str, Any] = {
            k: v for k, v in {
                "instructions": instructions,
                "goal_alignment": goal_alignment,
                "plan_tracking": plan_tracking,
                "loop_detection": loop_detection,
                "scope": scope,
                "sla": sla,
                "threat_severity": threat_severity,
                "compliance": compliance,
                "fault_tolerance": fault_tolerance,
                "reproducibility": reproducibility,
                "observability": observability,
                "explainability": explainability,
                "consensus": consensus,
            }.items() if v is not None
        }

        self._monitor = PerformanceMonitor(
            output_dir=output_dir,
            auto_save=auto_save,
            auto_save_interval=auto_save_interval,
            auto_save_filename=auto_save_filename,
            **monitor_kwargs,
        )
        self._eval = EvalDecorator(
            self._monitor,
            alert_rules=alert_rules or [],
            flush_every=flush_every,
        )

    @classmethod
    def for_rag(cls, output_dir: str = "results/", **kwargs: Any) -> "QuickEval":
        """RAG 파이프라인 평가에 최적화된 QuickEval 인스턴스.

        hallucination_detection 이 기본 활성화된다.

        Example::

            eval = QuickEval.for_rag("results/")

            @eval.rag
            def rag_agent(question, context="", ground_truth=""): ...
        """
        kwargs.setdefault("enable_hallucination_detection", True)
        return cls(output_dir, **kwargs)

    @classmethod
    def for_security(cls, output_dir: str = "results/", **kwargs: Any) -> "QuickEval":
        """보안 에이전트 평가에 최적화된 QuickEval 인스턴스.

        모든 보안 트래커(InputSanitization, OutputLeakage, ToolAuth 등)가 기본 활성화된다.

        Example::

            eval = QuickEval.for_security("results/")

            @eval.tool_use
            def secure_agent(question, ground_truth=""): ...
        """
        kwargs.setdefault("enable_security_metrics", True)
        return cls(output_dir, **kwargs)

    @classmethod
    def for_regression_eval(
        cls,
        output_dir: str = "results/",
        baseline_file: Optional[str] = None,
        regression_threshold: float = 0.05,
        **kwargs: Any,
    ) -> "QuickEval":
        """회귀 평가에 최적화된 QuickEval 인스턴스 (D2 / Y).

        자동 저장 + LLM Judge 를 활성화해 점수 회귀를 바로 감지할 수 있도록 한다.
        ``baseline_file`` 을 지정하면 이전 결과와 비교해 성능 저하를 탐지할 수 있다.

        Args:
            output_dir: 결과 저장 디렉토리.
            baseline_file: baseline JSON 파일 경로 (``save()`` 로 생성한 파일).
            regression_threshold: 기준 대비 하락 비율 임계값 (기본 5%).
            **kwargs: 추가 설정.

        Example::

            eval = QuickEval.for_regression_eval(
                "results/regression/",
                baseline_file="results/baseline.json",
                regression_threshold=0.05,
            )

            @eval.qa
            def agent(question, ground_truth=""): ...

            eval.gate(tcr=90, accuracy=80)
            report = eval.check_regression()
        """
        import json as _json
        import os as _os

        kwargs.setdefault("auto_save", True)
        kwargs.setdefault("auto_save_interval", 5)
        kwargs.setdefault("enable_llm_judge", True)       # D2: LLM Judge로 품질 회귀 즉시 감지
        kwargs.setdefault("enable_hallucination_detection", True)  # D2: hallucination 회귀도 감지
        kwargs.setdefault("enable_quality_evaluation", True)       # D2: 품질 평가 활성화
        instance = cls(output_dir, **kwargs)
        instance._baseline_file = baseline_file
        instance._regression_threshold = regression_threshold

        # baseline 로드
        if baseline_file and _os.path.exists(baseline_file):
            try:
                with open(baseline_file, "r", encoding="utf-8") as _f:
                    instance._baseline_summary = _json.load(_f)
            except Exception as _e:
                logger.debug("for_regression_eval: baseline load failed (ignored): %s", _e)
                instance._baseline_summary = None
        else:
            instance._baseline_summary = None

        return instance

    def check_regression(self) -> Dict[str, Any]:
        """현재 지표와 baseline을 비교해 성능 저하 여부를 반환합니다 (Y).

        ``for_regression_eval(baseline_file=...)`` 로 생성한 인스턴스에서 사용한다.

        Returns:
            ``has_baseline``, ``regression_threshold_pct``, ``regressions``, ``any_regression``
            을 포함하는 dict.

        Example::

            eval = QuickEval.for_regression_eval(
                "results/", baseline_file="results/baseline.json"
            )
            # ... 평가 실행 후 ...
            report = eval.check_regression()
            if report["any_regression"]:
                print("Performance regression detected!", report["regressions"])
        """
        if not hasattr(self, "_baseline_summary") or self._baseline_summary is None:
            return {"has_baseline": False}

        current = self.summary()
        threshold = getattr(self, "_regression_threshold", 0.05)
        regressions: Dict[str, Any] = {}

        for key in ("tcr", "accuracy", "quality_avg"):
            baseline_val = self._baseline_summary.get(key)
            current_val = current.get(key)
            if baseline_val is not None and current_val is not None:
                try:
                    _b = float(baseline_val)
                    _c = float(current_val)
                    change = (_c - _b) / max(abs(_b), 1e-9)
                    if change < -threshold:
                        regressions[key] = {
                            "baseline": _b,
                            "current": _c,
                            "change_pct": round(change * 100, 2),
                            "regressed": True,
                        }
                except (TypeError, ValueError):
                    pass

        return {
            "has_baseline": True,
            "baseline_file": getattr(self, "_baseline_file", None),
            "regression_threshold_pct": threshold * 100,
            "regressions": regressions,
            "any_regression": bool(regressions),
        }

    @classmethod
    def for_llm_judge(
        cls,
        output_dir: str = "results/",
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> "QuickEval":
        """LLM Judge 자동 채점에 최적화된 QuickEval 인스턴스.

        ``[llm]`` extras 필요: ``pip install "agent-evaluator[llm]"``.

        Example::

            eval = QuickEval.for_llm_judge("results/", model="claude-sonnet-4-6")

            @eval.qa
            def agent(question, ground_truth=""): ...
        """
        kwargs.setdefault("enable_llm_judge", True)
        if model is not None:
            kwargs.setdefault("judge_model", model)
        return cls(output_dir, **kwargs)

    @classmethod
    def for_harness(
        cls,
        output_dir: str = "results/",
        *,
        sla_p95: Optional[float] = None,
        reproducibility_runs: int = 3,
        enable_security: bool = True,
        **kwargs: Any,
    ) -> "QuickEval":
        """Harness 관점의 완전 평가에 최적화된 QuickEval 인스턴스.

        Goal Achievement · Behavioral Integrity · Reliability · Performance Contract ·
        Security Boundary · Multi-Agent · Observability 7개 그룹을 모두 측정한다.

        Args:
            output_dir: 결과 저장 디렉토리.
            sla_p95: P95 레이턴시 SLA(초). 설정 시 초과 태스크에 경고 기록.
            reproducibility_runs: 재현성 측정용 재실행 횟수 (기본: 3).
            enable_security: 보안 메트릭 활성화 여부 (기본: True).

        Example::

            eval = QuickEval.for_harness("results/", sla_p95=5.0)

            @eval.qa
            def agent(question, ground_truth=""): ...
        """
        if enable_security:
            kwargs.setdefault("enable_security_metrics", True)
        if sla_p95 is not None:
            kwargs.setdefault("sla_p95", sla_p95)
        kwargs.setdefault("_harness_reproducibility_runs", reproducibility_runs)
        return cls(output_dir, **kwargs)

    @classmethod
    def for_production(
        cls,
        output_dir: str = "results/",
        *,
        sla_p95: float = 5.0,
        reproducibility_runs: int = 3,
        judge_model: Optional[str] = None,
        **kwargs: Any,
    ) -> "QuickEval":
        """프로덕션 배포 전 종합 평가에 최적화된 QuickEval 인스턴스.

        SLA · 재현성 · 보안 · LLM Judge 모두 활성화한다.

        Args:
            output_dir: 결과 저장 디렉토리.
            sla_p95: P95 레이턴시 SLA(초, 기본: 5.0).
            reproducibility_runs: 재현성 측정용 재실행 횟수 (기본: 3).
            judge_model: LLM Judge 모델명. None이면 API 키 기반 자동 결정.

        Example::

            eval = QuickEval.for_production("results/", sla_p95=3.0)

            @eval.qa
            def agent(question, ground_truth=""): ...

            eval.gate(tcr=90, accuracy=80)  # CI/CD 게이팅
        """
        kwargs.setdefault("enable_security_metrics", True)
        kwargs.setdefault("enable_llm_judge", True)
        if judge_model is not None:
            kwargs.setdefault("judge_model", judge_model)
        kwargs.setdefault("sla_p95", sla_p95)
        kwargs.setdefault("_harness_reproducibility_runs", reproducibility_runs)
        return cls(output_dir, **kwargs)

    # ------------------------------------------------------------------
    # 프리셋 팩토리 — list_presets() / from_preset()
    # ------------------------------------------------------------------

    @classmethod
    def list_presets(cls) -> List[str]:
        """사용 가능한 QuickEval 팩토리 프리셋 목록을 반환합니다.

        Returns:
            사용 가능한 프리셋 이름 리스트.

        Example::

            >>> QuickEval.list_presets()
            ['default', 'rag', 'security', 'llm_judge', 'regression_eval']
        """
        return ["default", "rag", "security", "llm_judge", "regression_eval"]

    @classmethod
    def from_preset(
        cls,
        preset_name: str,
        output_dir: str = "results/",
        **kwargs: Any,
    ) -> "QuickEval":
        """프리셋 이름으로 QuickEval 인스턴스를 생성합니다.

        Args:
            preset_name: ``'default'``, ``'rag'``, ``'security'``, ``'llm_judge'``,
                ``'regression_eval'`` 중 하나.
            output_dir: 결과 저장 디렉토리.
            **kwargs: 추가 설정 (팩토리 메서드에 전달).

        Returns:
            설정이 적용된 QuickEval 인스턴스.

        Raises:
            ValueError: 알 수 없는 ``preset_name`` 인 경우.

        Example::

            eval = QuickEval.from_preset("rag", "results/")
            eval = QuickEval.from_preset("security", "results/", model="claude-sonnet-4-6")
        """
        _preset_map: Dict[str, Any] = {
            "default": cls,
            "rag": cls.for_rag,
            "security": cls.for_security,
            "llm_judge": cls.for_llm_judge,
            "regression_eval": cls.for_regression_eval,
        }
        factory = _preset_map.get(preset_name)
        if factory is None:
            valid = list(_preset_map.keys())
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Available presets: {valid}\n"
                f"e.g.: QuickEval.from_preset('rag', 'results/')"
            )
        if factory is cls:
            return cls(output_dir, **kwargs)
        return factory(output_dir, **kwargs)

    # ------------------------------------------------------------------
    # monitor / eval 접근
    # ------------------------------------------------------------------

    @property
    def monitor(self) -> Any:
        """내부 :class:`PerformanceMonitor` 인스턴스."""
        return self._monitor

    @property
    def eval(self) -> Any:
        """내부 :class:`EvalDecorator` 인스턴스."""
        return self._eval

    # ------------------------------------------------------------------
    # __getattr__ 위임 — 단축 속성을 EvalDecorator로 위임
    # ------------------------------------------------------------------

    # EvalDecorator에 위임할 속성 목록.
    # EvalDecorator가 _ShortcutCallable 프로퍼티로 제공하는 task_type 단축키 + 유틸리티 메서드.
    # NOTE: batch / chat 은 EvalDecorator에 no-paren property가 없으므로 아래에 직접 정의.
    _DELEGATED_ATTRS: frozenset = frozenset({
        # task_type 단축 속성 (_ShortcutCallable 반환)
        "qa", "tool_use", "rag", "code", "reasoning",
        "planning", "data_analysis", "creative",
        "multi_agent", "secure", "streaming",
        # EvalDecorator 유틸리티 메서드
        "context", "update_defaults", "inspect", "get_config",
    })

    def __getattr__(self, name: str) -> Any:
        """미등록 속성을 내부 EvalDecorator로 위임한다.

        ``qa``, ``rag`` 등의 단축 속성과 ``update_defaults`` 같은 유틸리티를
        QuickEval에서 그대로 사용할 수 있도록 EvalDecorator에 전달한다.

        Raises:
            AttributeError: ``_DELEGATED_ATTRS`` 에 없는 이름이거나 EvalDecorator에도
                없는 경우.
        """
        # __init__ 완료 전 (_eval 미존재) 또는 내부 속성 접근 시 무한 재귀 방지
        if name.startswith("_"):
            raise AttributeError(f"'QuickEval' object has no attribute {name!r}")
        try:
            eval_dec = object.__getattribute__(self, "_eval")
        except AttributeError:
            raise AttributeError(f"'QuickEval' object has no attribute {name!r}")
        if name in self._DELEGATED_ATTRS:
            return getattr(eval_dec, name)
        raise AttributeError(f"'QuickEval' object has no attribute {name!r}")

    # ------------------------------------------------------------------
    # 단축 데코레이터 속성 — batch / chat (no-paren 지원)
    # NOTE: EvalDecorator.batch / .conversation 은 메서드(callable)이므로
    #       @eval.batch (괄호 없음) 패턴을 지원하려면 별도 프로퍼티 필요.
    # ------------------------------------------------------------------

    @property
    def batch(self) -> _QuickEvalBatchShortcut:
        """배치 처리 평가 데코레이터 (``batch_eval``).

        Usage::

            @eval.batch
            def batch_agent(questions, ground_truths=None): ...

            @eval.batch(task_type="tool_use")
            def batch_agent(questions, ground_truths=None): ...
        """
        return _QuickEvalBatchShortcut(self._eval)

    @property
    def chat(self) -> _QuickEvalChatShortcut:
        """멀티턴 대화 평가 데코레이터 (``conversation_eval``).

        Usage::

            @eval.chat
            def chatbot(question, session_id="default"): ...

            @eval.chat(max_turns=10)
            def chatbot(question, session_id="default"): ...
        """
        return _QuickEvalChatShortcut(self._eval)

    @property
    def security(self) -> Any:
        """보안 평가 단축 데코레이터 (``EvalDecorator.secure`` 별칭).

        ``security_mode=True`` 로 자동 설정된다.
        ``QuickEval.for_security()`` 로 생성한 인스턴스와 함께 사용하면 보안 지표가
        활성화된다.

        Usage::

            eval = QuickEval.for_security("results/")

            @eval.security
            def secure_agent(question, ground_truth=""): ...
        """
        # EvalDecorator에서는 'secure'라는 이름으로 등록되어 있음
        # QuickEval은 하위 호환성을 위해 'security' 별칭으로 노출
        return self._eval.secure

    # ------------------------------------------------------------------
    # 직접 호출 — @eval(task_type="qa") 형태
    # ------------------------------------------------------------------

    def __call__(self, task_type: Any = "qa", **kwargs: Any) -> Callable:
        """``@eval(task_type=...)`` 형태로 데코레이터를 직접 생성한다.

        Harness defaults (``instructions``, ``sla`` 등)가 설정된 경우 자동으로 병합된다.
        kwargs로 직접 전달한 파라미터가 harness defaults보다 우선한다.

        Usage::

            @eval(task_type="qa", score_fn=my_fn)
            def agent(question, ground_truth=""): ...
        """
        # harness defaults와 kwargs 병합 (kwargs가 우선)
        # __new__ 후 __init__ 미호출 시 방어 처리
        harness_defaults: Dict[str, Any] = getattr(self, "_harness_defaults", {})
        merged: Dict[str, Any] = {**harness_defaults, **kwargs}
        return self._eval(task_type=task_type, **merged)

    def with_retry(self, task_type: Any = "qa", **kwargs: Any) -> Callable:
        """재시도 내장 데코레이터 (``agent_eval_with_retry``).

        Usage::

            @eval.with_retry(task_type="qa", max_retries=3, delay=1.0, backoff=2.0, jitter=True)
            def fragile_agent(question, ground_truth=""): ...
        """
        return self._eval.with_retry(task_type=task_type, **kwargs)

    # ------------------------------------------------------------------
    # 결과 저장 / 보고
    # ------------------------------------------------------------------

    def save(self, filename: str = "quickeval") -> str:
        """평가 결과를 JSON + HTML 로 저장.

        Args:
            filename: 저장할 파일명 (확장자 없이). 기본 ``"quickeval"``.

        Returns:
            저장된 JSON 파일 경로.

        Example::

            eval.save()                  # quickeval.json, quickeval.html
            eval.save("my_results")      # my_results.json, my_results.html
        """
        return self._monitor.save_to_file(filename)

    def report(self) -> Any:
        """EvaluationReport 객체를 반환.

        Example::

            report = eval.report()
            print(f"TCR: {report.task_completion_rate:.1f}%")
        """
        return self._monitor.generate_report()

    def gate(
        self,
        tcr: Optional[float] = None,
        accuracy: Optional[float] = None,
        config_file: Optional[str] = None,
        dry_run: bool = False,
        # C: 고급 지표 임계값
        token_efficiency_min: Optional[float] = None,
        tool_f1_min: Optional[float] = None,
        coordination_success_rate_min: Optional[float] = None,
        # Harness Gate A~G 점수 기반 판정
        gate_min: Optional[float] = None,
        gate_thresholds: Optional[Dict[str, float]] = None,
        required_gates: Optional[List[str]] = None,
        fail_on_gate_warn: bool = False,
        **thresholds: float,
    ) -> Union[bool, Dict[str, Any]]:
        """CI/CD 품질 게이팅 — 임계값 미달 시 ``SystemExit`` 발생.

        Args:
            tcr: Task Completion Rate 최소값 (0–100).
            accuracy: Accuracy 최소값 (0–100).
            config_file: JSON 파일 경로.  ``{"tcr": 85, "accuracy": 70, "latency_p95": 5.0}``
                형태의 임계값을 읽는다.  직접 지정한 파라미터가 파일 값보다 우선한다.
            dry_run: ``True`` 이면 ``sys.exit()`` 를 호출하지 않고 결과를 dict 로 반환한다.
                ``{"passed": bool, "results": {...}, "gate_results": {...}}`` 형식.
            gate_min: 모든 Harness Gate(A~G)에 적용할 최소 점수 (0.0–1.0).
                ``gate_thresholds`` 에 없는 Gate의 기본 임계값으로도 사용된다.
            gate_thresholds: Gate별 개별 최소 점수 dict.
                예: ``{"A": 0.8, "D": 0.9, "E": 0.95}``.
                지정된 Gate만 검사하며 ``gate_min`` 보다 우선 적용된다.
            required_gates: 검사 대상 Gate 목록. 미지정 시 데이터가 있는 Gate 전체.
                예: ``["A", "D", "E"]``.
            fail_on_gate_warn: ``True`` 이면 Gate 상태가 ``"warn"`` 이어도 실패로 처리.
            **thresholds: 추가 임계값 (``latency_p95=5.0`` 등).

        Returns:
            ``dry_run=False`` (기본): 모든 임계값을 충족하면 ``True``.
            ``dry_run=True``: 검사 결과 dict.

        Raises:
            SystemExit: 임계값 미달 시 (``dry_run=False`` 일 때만).

        Example::

            eval.gate(tcr=85, accuracy=70)
            eval.gate(config_file=".thresholds.json")               # 파일에서 임계값 로드
            eval.gate(config_file=".thresholds.json", tcr=90)       # 파일 tcr을 90으로 override
            result = eval.gate(tcr=85, accuracy=70, dry_run=True)   # 종료 없이 결과 확인
            eval.gate(gate_min=0.7, gate_thresholds={"D": 0.9})     # Gate D는 0.9, 나머지는 0.7
            eval.gate(gate_thresholds={"A": 0.8}, required_gates=["A", "D"])  # A·D만 검사
        """
        import json
        import os
        import sys

        # config_file에서 임계값 로드 (직접 지정한 파라미터 값이 우선)
        if config_file is not None:
            try:
                with open(config_file, encoding="utf-8") as _f:
                    _cfg: Dict[str, Any] = json.load(_f)
                if tcr is None and "tcr" in _cfg:
                    tcr = float(_cfg["tcr"])
                if accuracy is None and "accuracy" in _cfg:
                    accuracy = float(_cfg["accuracy"])
                for _k, _v in _cfg.items():
                    if _k not in ("tcr", "accuracy") and _k not in thresholds:
                        thresholds[_k] = float(_v)
            except Exception as _e:
                logger.warning("gate config_file load failed (ignored): %s", _e)

        report = self._monitor.generate_report()
        failures: List[str] = []
        # dry_run 모드 전용: 각 지표별 상세 결과 수집
        dry_run_results: Dict[str, Any] = {}

        if tcr is not None:
            actual_tcr = float(
                (report.accuracy_metrics or {}).get("tcr", {}).get("tcr", 0.0)
            )
            _passed_tcr = actual_tcr >= tcr
            dry_run_results["tcr"] = {
                "current": actual_tcr,
                "threshold": tcr,
                "passed": _passed_tcr,
            }
            if not _passed_tcr:
                failures.append(f"TCR {actual_tcr:.1f}% < required {tcr}%")

        if accuracy is not None:
            actual_acc = float(
                (report.accuracy_metrics or {})
                .get("accuracy_scores", {})
                .get("overall_accuracy", 0.0)
            )
            _passed_acc = actual_acc >= accuracy
            dry_run_results["accuracy"] = {
                "current": actual_acc,
                "threshold": accuracy,
                "passed": _passed_acc,
            }
            if not _passed_acc:
                failures.append(f"Accuracy {actual_acc:.1f}% < required {accuracy}%")

        if "latency_p95" in thresholds:
            p95 = float(
                (report.efficiency_metrics or {}).get("latency", {}).get("p95", 0.0)
            )
            req = thresholds["latency_p95"]
            _passed_lat = p95 <= req
            dry_run_results["latency_p95"] = {
                "current": p95,
                "threshold": req,
                "passed": _passed_lat,
            }
            if not _passed_lat:
                failures.append(f"P95 latency {p95:.2f}s > allowed {req}s")

        # A7: quality / hallucination 임계값 지원
        if "quality" in thresholds:
            # H2: quality 트래커가 비활성화된 경우 경고
            _quality_enabled = getattr(self._monitor, "_enable_quality", True)
            if not _quality_enabled:
                import warnings as _w
                _w.warn(
                    "QuickEval.gate(quality=...): quality tracking is disabled, "
                    "actual value is 0.0. Check your PerformanceMonitor configuration.",
                    UserWarning,
                    stacklevel=2,
                )
            _s = self.summary()
            actual_q = _s.get("quality_avg", 0.0)
            req_q = thresholds["quality"]
            _passed_q = actual_q >= req_q
            dry_run_results["quality"] = {
                "current": actual_q,
                "threshold": req_q,
                "passed": _passed_q,
            }
            if not _passed_q:
                failures.append(f"Quality {actual_q:.1f} < required {req_q}")

        if "hallucination" in thresholds:
            # H2: hallucination 트래커가 비활성화된 경우 경고
            _hall_enabled = getattr(self._monitor, "_enable_hallucination_detection", False)
            if not _hall_enabled:
                import warnings as _w
                _w.warn(
                    "QuickEval.gate(hallucination=...): hallucination detection is disabled, "
                    "actual value is 0.0. Use QuickEval.for_rag() or "
                    "enable_hallucination_detection=True.",
                    UserWarning,
                    stacklevel=2,
                )
            _s = self.summary()
            actual_h = _s.get("hallucination_rate", 0.0)
            req_h = thresholds["hallucination"]
            _passed_h = actual_h <= req_h
            dry_run_results["hallucination"] = {
                "current": actual_h,
                "threshold": req_h,
                "passed": _passed_h,
            }
            if not _passed_h:
                failures.append(f"Hallucination rate {actual_h:.1f}% > allowed {req_h}%")

        # C: token_efficiency — 태스크당 평균 토큰 수 (상한, 낮을수록 좋음)
        if token_efficiency_min is not None:
            tasks = list(self._monitor.tasks)
            _tokens_total = 0
            for _t in tasks:
                _tu = _t.tokens_used
                if isinstance(_tu, int):
                    _tokens_total += _tu
                elif isinstance(_tu, dict):
                    _tokens_total += _tu.get("total", _tu.get("input", 0) + _tu.get("output", 0))
            _avg_tokens = _tokens_total / max(1, len(tasks))
            _token_pass = _avg_tokens <= token_efficiency_min
            dry_run_results["token_efficiency"] = {
                "current": round(_avg_tokens, 1),
                "threshold": token_efficiency_min,
                "passed": _token_pass,
            }
            if not _token_pass:
                failures.append(
                    f"Avg tokens {_avg_tokens:.1f} > allowed {token_efficiency_min}"
                )

        # C: tool_f1 — 도구 선택 F1 최소값
        if tool_f1_min is not None:
            try:
                _tool_sel = getattr(self._monitor, "_tool_selection_tracker", None)
                if _tool_sel is not None and hasattr(_tool_sel, "get_summary"):
                    _f1 = float(
                        (_tool_sel.get_summary() or {}).get("overall_f1", 0.0) or 0.0
                    )
                else:
                    _f1 = float(
                        (report.efficiency_metrics or {})
                        .get("tool_selection", {})
                        .get("overall_f1", 0.0)
                        or 0.0
                    )
            except Exception as _e:
                logger.debug("gate: tool_f1 lookup failed, using 0.0: %s", _e)
                _f1 = 0.0
            _tool_pass = _f1 >= tool_f1_min
            dry_run_results["tool_f1"] = {
                "current": round(_f1, 4),
                "threshold": tool_f1_min,
                "passed": _tool_pass,
            }
            if not _tool_pass:
                failures.append(f"Tool F1 {_f1:.4f} < required {tool_f1_min}")

        # C: coordination_success_rate — 에이전트 협력 성공률
        if coordination_success_rate_min is not None:
            try:
                _coord = getattr(self._monitor, "_coordination_tracker", None)
                if _coord is not None and hasattr(_coord, "get_summary"):
                    _csr = float(
                        (_coord.get_summary() or {}).get("success_rate", 0.0) or 0.0
                    )
                else:
                    _csr = float(
                        (report.efficiency_metrics or {})
                        .get("coordination", {})
                        .get("success_rate", 0.0)
                        or 0.0
                    )
            except Exception as _e:
                logger.debug("gate: coordination_success_rate lookup failed, using 0.0: %s", _e)
                _csr = 0.0
            _coord_pass = _csr >= coordination_success_rate_min
            dry_run_results["coordination_success_rate"] = {
                "current": round(_csr, 4),
                "threshold": coordination_success_rate_min,
                "passed": _coord_pass,
            }
            if not _coord_pass:
                failures.append(
                    f"Coordination success rate {_csr:.4f} < required {coordination_success_rate_min}"
                )

        # Harness Gate A~G 점수 기반 판정
        gate_run_results: Dict[str, Any] = {}
        if gate_min is not None or gate_thresholds:
            d = report.to_dict() if hasattr(report, "to_dict") else {}
            harness = (d.get("extra_metrics") or {}).get("harness_groups", {})
            _gate_thresholds = gate_thresholds or {}
            _required = set(g.upper() for g in required_gates) if required_gates else None
            for gate_id in "ABCDEFG":
                if _required is not None and gate_id not in _required:
                    continue
                gate_data = harness.get(gate_id)
                if not isinstance(gate_data, dict):
                    continue
                score = gate_data.get("score")
                if score is None:
                    continue
                threshold = _gate_thresholds.get(gate_id, gate_min)
                if threshold is None:
                    continue
                score_f = float(score)
                status = gate_data.get("status", "")
                _gate_passed = score_f >= threshold
                if fail_on_gate_warn and status == "warn":
                    _gate_passed = False
                gate_run_results[gate_id] = {
                    "score": round(score_f, 4),
                    "threshold": threshold,
                    "status": status,
                    "passed": _gate_passed,
                }
                if not _gate_passed:
                    failures.append(
                        f"Gate {gate_id} score {score_f:.3f} < required {threshold:.3f}"
                        + (f" (status={status})" if fail_on_gate_warn and status == "warn" else "")
                    )

        if dry_run:
            result: Dict[str, Any] = {
                "passed": len(failures) == 0,
                "results": dry_run_results,
            }
            if gate_run_results:
                result["gate_results"] = gate_run_results
            return result

        if failures:
            msg = "QuickEval quality gate failed:\n" + "\n".join(f"  - {f}" for f in failures)
            print(msg, file=sys.stderr)
            sys.exit(1)

        return True

    def generate_gate_config(self, filepath: str = "gate_config.json") -> dict:
        """현재 지표를 기반으로 gate() 임계값 설정 파일을 생성한다 (E3).

        기존 평가 결과에서 현실적인 임계값을 자동으로 제안하며, JSON 파일로 저장한다.
        생성된 파일은 ``gate(config_file="gate_config.json")`` 으로 바로 사용 가능하다.

        Args:
            filepath: 저장할 JSON 파일 경로 (기본: "gate_config.json").

        Returns:
            생성된 임계값 dict. ``{"tcr": float, "accuracy": float, ...}`` 형식.

        Example::

            qe = QuickEval("results/")
            # ... 평가 실행 ...
            qe.generate_gate_config("my_thresholds.json")
            # 다음 번 CI에서:
            qe.gate(config_file="my_thresholds.json")
        """
        import json as _json
        import os as _os

        summary = self.summary()
        # 현재 지표에서 약간 여유있는 임계값 제안 (현재값의 95%)
        _tcr = summary.get("tcr", 0.0)
        _acc = summary.get("accuracy", 0.0)
        config = {
            "tcr": round(max(0.0, _tcr * 0.95), 1),
            "accuracy": round(max(0.0, _acc * 0.95), 1),
            "quality": None,      # quality 트래킹 활성화 시 수동으로 설정
            "hallucination": None,  # hallucination 트래킹 활성화 시 수동으로 설정
        }
        _dir = _os.path.dirname(_os.path.abspath(filepath))
        _os.makedirs(_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as _f:
            _json.dump(config, _f, indent=2, ensure_ascii=False)
        return config

    def summary(self) -> Dict[str, Any]:
        """주요 지표 요약 딕셔너리를 반환 (A6: 확장).

        Returns:
            tcr, accuracy, total_tasks, avg_latency, p95_latency,
            total_cost_usd, quality_avg, hallucination_rate, total_tokens

        Example::

            s = eval.summary()
            print(f"TCR: {s['tcr']:.1f}%, P95: {s['p95_latency']:.2f}s")
        """
        report = self._monitor.generate_report()
        acc_m = report.accuracy_metrics or {}
        eff_m = report.efficiency_metrics or {}
        # quality_avg (0–100 scale)
        quality_avg = 0.0
        try:
            quality_avg = float(
                acc_m.get("quality", {}).get("avg_score", 0.0) or
                acc_m.get("response_quality", {}).get("avg_score", 0.0)
            ) * 20  # 0–5 → 0–100
        except (TypeError, ValueError):
            pass
        # hallucination rate
        hallucination_rate = 0.0
        try:
            h = acc_m.get("hallucination", {})
            tot = int(h.get("total_evaluated", 0) or 0)
            flagged = int(h.get("total_flagged", 0) or 0)
            if tot > 0:
                hallucination_rate = round(flagged / tot * 100, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        # total cost
        total_cost_usd = 0.0
        try:
            total_cost_usd = float(eff_m.get("tokens", {}).get("total_cost_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        # V: 각 필드의 computed 여부 (트래커 활성화 상태 반영)
        _hall_enabled = getattr(self._monitor, "_enable_hallucination_detection", False)
        _quality_enabled = getattr(self._monitor, "_enable_quality", True)
        # cost는 TokenEconomyTracker가 항상 활성
        # latency는 LatencyTracker가 항상 활성
        _meta: Dict[str, Any] = {
            "tcr_computed": report.total_tasks > 0,
            "accuracy_computed": report.total_tasks > 0,
            "quality_avg_computed": bool(_quality_enabled) and quality_avg > 0.0,
            "hallucination_rate_computed": bool(_hall_enabled),
            "p95_latency_computed": report.total_tasks > 0,
            "total_cost_usd_computed": total_cost_usd > 0.0,
        }

        return {
            "tcr": float(acc_m.get("tcr", {}).get("tcr", 0.0)),
            "accuracy": float(acc_m.get("accuracy_scores", {}).get("overall_accuracy", 0.0)),
            "total_tasks": report.total_tasks,
            "avg_latency": float(eff_m.get("latency", {}).get("mean", 0.0)),
            "p95_latency": float(eff_m.get("latency", {}).get("p95", 0.0)),
            "total_cost_usd": total_cost_usd,
            "quality_avg": quality_avg,
            "hallucination_rate": hallucination_rate,
            "total_tokens": int(eff_m.get("tokens", {}).get("total_tokens", 0)),
            "_meta": _meta,  # V: 계산 가능 여부 메타데이터
        }

    def compare(
        self,
        other: "QuickEval",
        self_name: str = "eval_a",
        other_name: str = "eval_b",
    ) -> "CompareResult":
        """두 QuickEval 인스턴스의 주요 지표를 비교한다 (D1).

        Args:
            other:      비교 대상 :class:`QuickEval` 인스턴스.
            self_name:  이 인스턴스의 표시 레이블 (기본 "eval_a").
            other_name: other 인스턴스의 표시 레이블 (기본 "eval_b").

        Returns:
            :class:`CompareResult` — ``print()`` 시 비교 테이블을 출력한다.
            기존 dict 접근(``result["delta"]["tcr"]``)도 그대로 동작한다.

        Example::

            result = eval_a.compare(eval_b, self_name="v1", other_name="v2")
            print(result)                    # 컬러 비교 테이블
            result["delta"]["tcr"]           # -32.5
            result.winner                    # 'other'
            result.to_dict()                 # 기존 raw dict
        """
        s = self.summary()
        o = other.summary()
        delta: Dict[str, Any] = {}
        for key in ("tcr", "accuracy", "avg_latency", "total_tokens", "total_tasks",
                    "quality_avg", "hallucination_rate", "p95_latency", "total_cost_usd"):
            sv = s.get(key, 0.0)
            ov = o.get(key, 0.0)
            try:
                delta[key] = round(float(sv) - float(ov), 4)
            except (TypeError, ValueError):
                delta[key] = None

        return CompareResult(s, o, delta, self_name=self_name, other_name=other_name)

    # -----------------------------------------------------------------------
    # E1-E6: v0.7.9 신규 QuickEval 메서드
    # -----------------------------------------------------------------------

    @classmethod
    def from_config(cls, config_file: str) -> "QuickEval":
        """YAML 또는 JSON 설정 파일에서 QuickEval 인스턴스를 생성한다 (E1).

        설정 파일 형식::

            output_dir: results/
            enable_hallucination: true
            enable_security: false
            model: claude-sonnet-4-6
            auto_save: true
            auto_save_interval: 20

        Args:
            config_file: YAML 또는 JSON 파일 경로.

        Returns:
            설정값으로 초기화된 QuickEval 인스턴스.
        """
        import json as _json
        import os as _os

        config: Dict[str, Any] = {}
        if not _os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        if config_file.endswith((".yaml", ".yml")):
            try:
                import yaml as _yaml  # type: ignore
                with open(config_file, "r", encoding="utf-8") as _f:
                    config = _yaml.safe_load(_f) or {}
            except ImportError:
                # YAML 없으면 JSON fallback 시도
                with open(config_file, "r", encoding="utf-8") as _f:
                    config = _json.load(_f)
        else:
            with open(config_file, "r", encoding="utf-8") as _f:
                config = _json.load(_f)

        return cls(
            output_dir=config.get("output_dir", "results/"),
            # PerformanceMonitor kwargs — passed via **monitor_kwargs
            enable_hallucination_detection=config.get("enable_hallucination", False),
            enable_security_metrics=config.get("enable_security", False),
            auto_save=config.get("auto_save", False),
            auto_save_interval=int(config.get("auto_save_interval", 10)),
        )

    def export_to_dataframe(
        self,
        include_fields: Optional[List[str]] = None,
    ) -> Any:
        """모든 태스크를 pandas DataFrame으로 내보낸다 (E2).

        ``self.monitor.export_to_dataframe()`` 의 편의 래퍼.

        Args:
            include_fields: task.extra에서 추가로 포함할 키 목록.

        Returns:
            pandas DataFrame.

        Raises:
            RuntimeError: 기록된 태스크가 없는 경우.
        """
        if self._monitor.task_count == 0:
            raise RuntimeError("No tasks recorded. Run an evaluation first.")
        return self._monitor.export_to_dataframe(include_fields=include_fields)

    def replay(self, results_file: str) -> "QuickEval":
        """저장된 결과 파일에서 TaskResult를 재로드한다 (E3).

        이전 평가 결과를 현재 모니터에 다시 기록해 지표를 재계산하거나
        결과를 병합할 때 유용하다.

        Args:
            results_file: save_to_file()로 생성된 JSON 파일 경로.

        Returns:
            ``self`` — 메서드 체이닝 지원.
        """
        import json as _json
        with open(results_file, "r", encoding="utf-8") as _f:
            data = _json.load(_f)
        tasks_data = data.get("task_results", data.get("tasks", []))
        from .core.trackers.base import TaskResult
        for td in tasks_data:
            try:
                tr = TaskResult.from_dict(td)
                self._monitor.record_task(tr)
            except Exception as _e:
                logger.debug("replay: TaskResult load failed (ignored): %s", _e)
        logger.info("replay: %d tasks loaded (%s)", len(tasks_data), results_file)
        return self

    def ab_test(self, other: "QuickEval") -> Dict[str, Any]:
        """두 QuickEval 인스턴스의 정확도 분포를 통계적으로 비교한다 (E4).

        t-검정으로 두 에이전트의 성능 차이가 통계적으로 유의미한지 검증한다.

        Args:
            other: 비교할 다른 QuickEval 인스턴스.

        Returns:
            ``{"self_mean", "other_mean", "delta", "better",
               "t_statistic", "p_value", "significant", "sample_sizes"}``
        """
        self_scores = [getattr(t, "accuracy_score", 0.0) or 0.0 for t in self._monitor.tasks]
        other_scores = [getattr(t, "accuracy_score", 0.0) or 0.0 for t in other._monitor.tasks]
        self_mean = sum(self_scores) / len(self_scores) if self_scores else 0.0
        other_mean = sum(other_scores) / len(other_scores) if other_scores else 0.0
        delta = round(self_mean - other_mean, 6)
        better = "self" if delta > 0 else ("other" if delta < 0 else "equal")

        t_stat: Optional[float] = None
        p_val: Optional[float] = None
        significant: Optional[bool] = None
        try:
            from scipy import stats as _stats  # type: ignore
            if len(self_scores) >= 2 and len(other_scores) >= 2:
                _result = _stats.ttest_ind(self_scores, other_scores)
                t_stat = float(_result.statistic)
                p_val = float(_result.pvalue)
                significant = p_val < 0.05
        except ImportError:
            pass  # scipy 없으면 t-검정 생략

        return {
            "self_mean": round(self_mean, 6),
            "other_mean": round(other_mean, 6),
            "delta": delta,
            "better": better,
            "t_statistic": t_stat,
            "p_value": p_val,
            "significant": significant,
            "sample_sizes": {"self": len(self_scores), "other": len(other_scores)},
        }

    def cached(
        self,
        ttl: int = 3600,
        cache_key_fn: Optional[Callable] = None,
    ) -> Callable:
        """응답 캐싱 데코레이터를 반환한다 (E5).

        캐시 히트 시 함수를 호출하지 않고 저장된 응답을 반환한다.
        에이전트 비용을 줄이기 위한 선택적 최적화.

        Args:
            ttl: 캐시 유효 시간(초, 기본 3600).
            cache_key_fn: 커스텀 캐시 키 생성 함수 ``(*args, **kwargs) -> str``.
                ``None`` 이면 ``str(args)+str(kwargs)`` 해시 사용.

        Returns:
            데코레이터 함수.

        Example::

            @eval.cached(ttl=600)
            @eval.qa
            def agent(question: str, ground_truth: str = "") -> str:
                return llm.predict(question)
        """
        import time as _t_mod
        if not hasattr(self, "_response_cache"):
            self._response_cache: Dict[str, Any] = {}

        def _make_key(*args, **kwargs) -> str:
            if cache_key_fn is not None:
                try:
                    return str(cache_key_fn(*args, **kwargs))
                except Exception:
                    pass
            return str(hash(str(args) + str(sorted(kwargs.items()))))

        def decorator(func: Callable) -> Callable:
            import asyncio as _asyncio
            import inspect as _inspect

            if _inspect.iscoroutinefunction(func):
                # H3: async 함수 지원
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    _key = _make_key(*args, **kwargs)
                    _now = _t_mod.time()
                    _cached = self._response_cache.get(_key)
                    if _cached is not None:
                        _val, _expiry = _cached
                        if _now < _expiry:
                            return _val
                    _result = await func(*args, **kwargs)
                    self._response_cache[_key] = (_result, _now + ttl)
                    return _result
                return async_wrapper  # type: ignore[return-value]
            else:
                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    _key = _make_key(*args, **kwargs)
                    _now = _t_mod.time()
                    _cached = self._response_cache.get(_key)
                    if _cached is not None:
                        _val, _expiry = _cached
                        if _now < _expiry:
                            return _val
                    _result = func(*args, **kwargs)
                    self._response_cache[_key] = (_result, _now + ttl)
                    return _result
                return wrapper
        return decorator

    def watch(
        self,
        directory: Optional[str] = None,
        callback: Optional[Callable] = None,
        max_watched_files: int = 10_000,
    ) -> Any:
        """디렉토리의 새 JSON 결과 파일을 감시해 자동으로 replay한다 (E6).

        ``watchdog`` 라이브러리가 있으면 이벤트 기반으로, 없으면 5초 폴링으로 작동한다.

        Args:
            directory: 감시할 디렉토리 (기본: output_dir).
            callback: 새 파일 감지 시 호출되는 콜백 ``(file_path: str) -> None``.
            max_watched_files: ``_seen`` 집합 최대 크기 (기본 10,000).
                초과 시 오래된 항목을 제거해 메모리 누수를 방지한다 (H4).

        Returns:
            ``.stop()`` 메서드를 가진 감시 핸들 객체.
        """
        import os as _os
        import threading as _th

        _dir = directory or self._monitor.output_dir or "results"
        _seen = set(_os.listdir(_dir)) if _os.path.isdir(_dir) else set()

        class _WatchHandle:
            def __init__(self_h) -> None:
                self_h._stopped = False
                self_h._thread = _th.Thread(target=self_h._run, daemon=True)
                self_h._thread.start()

            def _run(self_h) -> None:
                import time as _t
                nonlocal _seen
                while not self_h._stopped:
                    try:
                        _current = set(_os.listdir(_dir)) if _os.path.isdir(_dir) else set()
                        _new = _current - _seen
                        for _fname in _new:
                            if _fname.endswith(".json"):
                                _fpath = _os.path.join(_dir, _fname)
                                try:
                                    self.replay(_fpath)
                                    if callback:
                                        callback(_fpath)
                                except Exception as _e:
                                    logger.debug("watch: file processing failed (ignored): %s", _e)
                        _seen.update(_current)
                        # H4: _seen 집합 크기 상한 — 메모리 누수 방지
                        if len(_seen) > max_watched_files:
                            _trim = len(_seen) - max_watched_files
                            _seen -= set(list(_seen)[:_trim])
                    except Exception as _e:
                        logger.debug("watch: polling failed (ignored): %s", _e)
                    _t.sleep(5)

            def stop(self_h) -> None:
                self_h._stopped = True

        return _WatchHandle()

    # ------------------------------------------------------------------
    # Harness 게이팅 / 요약
    # ------------------------------------------------------------------

    def harness_gate(
        self,
        min_group_score: float = 0.7,
        required_groups: Optional[List[str]] = None,
        fail_on_warn: bool = False,
    ) -> Dict[str, Any]:
        """Harness 그룹 점수 기반 CI/CD 게이팅.

        Args:
            min_group_score: 각 그룹의 최소 허용 점수 (기본 0.7).
            required_groups: 검사할 그룹 목록 (기본: 점수가 있는 모든 그룹).
                예: ``["A", "D", "E"]`` — Goal·Performance·Security만 검사.
            fail_on_warn: ``True`` 이면 ``warn`` 상태도 실패로 처리.

        Returns:
            ``{"passed": bool, "groups": {...}, "failed_groups": [...]}``

        Raises:
            SystemExit(1): 게이팅 실패 시.

        Example::

            eval = QuickEval(
                "results/",
                instructions=InstructionConfig(required_keywords=["result"]),
                sla=SLAConfig(p95_ms=3000),
            )

            @eval.qa
            def my_agent(question, ground_truth=""): ...

            my_agent("test", ground_truth="answer")
            eval.harness_gate(min_group_score=0.7, required_groups=["A", "D"])
        """
        import sys

        report = self._monitor.generate_report()
        harness_groups = (report.extra_metrics or {}).get("harness_groups", {})

        if not harness_groups:
            print("[harness_gate] No harness data available — skipping gate")
            return {"passed": True, "groups": {}, "failed_groups": []}

        results: Dict[str, Any] = {}
        failed: List[str] = []

        groups_to_check = required_groups or [
            k for k in harness_groups
            if k != "overall" and isinstance(harness_groups[k], dict)
        ]

        for group_name in groups_to_check:
            group_data = harness_groups.get(group_name, {})
            if not isinstance(group_data, dict):
                continue
            score = group_data.get("score")
            status = group_data.get("status", "n/a")
            if score is None:
                results[group_name] = {"score": None, "status": "n/a", "passed": True}
                continue
            passed = float(score) >= min_group_score
            if fail_on_warn and status == "warn":
                passed = False
            results[group_name] = {
                "score": round(float(score), 3),
                "status": status,
                "passed": passed,
            }
            if not passed:
                failed.append(group_name)

        overall_passed = len(failed) == 0

        print(f"\n{'=' * 50}")
        print(f"Harness Gate: {'PASSED' if overall_passed else 'FAILED'}")
        for g, r in results.items():
            icon = "[PASS]" if r["passed"] else "[FAIL]"
            score_str = f"{r['score']:.3f}" if r["score"] is not None else "n/a"
            print(f"  {icon} Group {g}: {score_str} ({r['status']})")
        if failed:
            print(f"\nFailed groups: {failed}")
        print(f"{'=' * 50}\n")

        if not overall_passed:
            sys.exit(1)

        return {"passed": overall_passed, "groups": results, "failed_groups": failed}

    def harness_summary(self) -> Dict[str, Any]:
        """Harness 그룹별 요약 리포트를 반환합니다.

        Returns:
            ``{"overall": float | None, "groups": {A: {score, status, details}, ...}}``

        Example::

            s = eval.harness_summary()
            print(f"Overall: {s['overall']}")
            for group, data in s['groups'].items():
                print(f"  Group {group}: {data['score']}")
        """
        report = self._monitor.generate_report()
        harness_groups = (report.extra_metrics or {}).get("harness_groups", {})

        if not harness_groups:
            return {"overall": None, "groups": {}}

        group_summary: Dict[str, Any] = {}
        for k, v in harness_groups.items():
            if k == "overall":
                continue
            if isinstance(v, dict):
                group_summary[k] = {
                    "score": v.get("score"),
                    "status": v.get("status", "n/a"),
                    "details": v.get("details", {}),
                }

        overall = harness_groups.get("overall", {})
        overall_score = overall.get("score") if isinstance(overall, dict) else None

        return {"overall": overall_score, "groups": group_summary}

    def __repr__(self) -> str:
        total = self._monitor.task_count  # D7: task_count property 사용
        return f"QuickEval(output_dir={self._monitor.output_dir!r}, tasks={total})"


# ---------------------------------------------------------------------------
# HarnessEvaluationGate — Group A-G 종합 배포 판정 도구
# ---------------------------------------------------------------------------

class HarnessEvaluationGate:
    """Group A-G Harness Config 기반 종합 배포 판정 도구.

    ``PerformanceMonitor.generate_report()``가 반환한 ``EvaluationReport``에서
    harness_groups 데이터를 읽어 Group A-G 전체를 한 번에 평가한다.
    ``agent-eval gate`` CLI의 Python API 버전이며, CI/CD 파이프라인에서
    자동 배포 차단에 사용한다.

    Args:
        report: ``PerformanceMonitor.generate_report()`` 반환값.
        min_group_score: 각 그룹 최소 허용 점수 (기본 0.7 = 70%).
        required_groups: 검사할 그룹 목록. ``None``이면 점수가 있는 모든 그룹.
            예: ``["A", "D", "E"]`` — Goal·Performance·Security만 검사.
        fail_on_warn: ``True``이면 ``warn`` 상태도 실패로 처리.

    Example::

        from agent_evaluator import PerformanceMonitor, HarnessEvaluationGate
        from agent_evaluator import InstructionConfig, SLAConfig
        from agent_evaluator.decorators import agent_eval

        monitor = PerformanceMonitor(output_dir="results/")

        @agent_eval(monitor, task_type="qa",
            instructions=InstructionConfig(required_keywords=["서울"], fail_on_violation=True),
            sla=SLAConfig(p95_ms=3000, fail_on_violation=True),
        )
        def my_agent(question, ground_truth=""): ...

        my_agent("한국의 수도는?", ground_truth="서울")

        report = monitor.generate_report()
        gate = HarnessEvaluationGate(report)
        result = gate.evaluate()
        # → {"passed": True, "groups": {"A": {...}, "D": {...}}, "violations": [], "summary": {...}}

        # CI/CD — 실패 시 sys.exit(1)
        gate.enforce()

        # 특정 그룹만 검사
        HarnessEvaluationGate(report, required_groups=["A", "E"]).enforce()
    """

    def __init__(
        self,
        report: Any,
        *,
        min_group_score: float = 0.7,
        required_groups: Optional[List[str]] = None,
        fail_on_warn: bool = False,
    ) -> None:
        self._report = report
        self._min_group_score = min_group_score
        self._required_groups = required_groups
        self._fail_on_warn = fail_on_warn
        self._result: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self) -> Dict[str, Any]:
        """Group A-G 전체를 평가하고 결과 dict를 반환한다.

        Returns:
            ``{
                "passed": bool,
                "groups": {
                    "A": {"score": float|None, "status": str, "passed": bool},
                    ...
                },
                "violations": [{"group": str, "score": float, "status": str}],
                "summary": {
                    "total_groups": int,
                    "passed_groups": int,
                    "overall_score": float|None,
                }
            }``

        Example::

            result = gate.evaluate()
            if not result["passed"]:
                for v in result["violations"]:
                    print(f"Group {v['group']} failed: {v['score']:.3f}")
        """
        harness_groups = (getattr(self._report, "extra_metrics", None) or {}).get(
            "harness_groups", {}
        )

        if not harness_groups:
            self._result = {
                "passed": True,
                "groups": {},
                "violations": [],
                "summary": {"total_groups": 0, "passed_groups": 0, "overall_score": None},
            }
            return self._result

        groups_to_check: List[str] = self._required_groups or [
            k for k in harness_groups
            if k != "overall" and isinstance(harness_groups[k], dict)
        ]

        results: Dict[str, Any] = {}
        violations: List[Dict[str, Any]] = []

        for group_name in groups_to_check:
            group_data = harness_groups.get(group_name, {})
            if not isinstance(group_data, dict):
                continue
            score = group_data.get("score")
            status = group_data.get("status", "n/a")

            if score is None:
                results[group_name] = {"score": None, "status": "n/a", "passed": True}
                continue

            passed = float(score) >= self._min_group_score
            if self._fail_on_warn and status == "warn":
                passed = False

            results[group_name] = {
                "score": round(float(score), 3),
                "status": status,
                "passed": passed,
            }

            if not passed:
                violations.append({
                    "group": group_name,
                    "score": round(float(score), 3),
                    "status": status,
                })

        overall = harness_groups.get("overall", {})
        overall_score = overall.get("score") if isinstance(overall, dict) else None
        passed_count = sum(1 for r in results.values() if r.get("passed", True))

        self._result = {
            "passed": len(violations) == 0,
            "groups": results,
            "violations": violations,
            "summary": {
                "total_groups": len(results),
                "passed_groups": passed_count,
                "overall_score": round(float(overall_score), 3) if overall_score is not None else None,
            },
        }
        return self._result

    def enforce(self, exit_on_fail: bool = True) -> "HarnessEvaluationGate":
        """``evaluate()``를 실행하고 실패 시 ``sys.exit(1)``을 호출한다.

        Args:
            exit_on_fail: ``False``로 설정하면 ``sys.exit`` 없이 결과만 반환.

        Returns:
            ``self`` — 메서드 체이닝용.

        Raises:
            SystemExit(1): 게이팅 실패 시 (``exit_on_fail=True`` 기본값일 때).

        Example::

            HarnessEvaluationGate(report).enforce()          # CI/CD — 실패 시 종료
            result = gate.enforce(exit_on_fail=False).result  # dry-run
        """
        import sys

        result = self.evaluate()
        self._print_result(result)
        if not result["passed"] and exit_on_fail:
            sys.exit(1)
        return self

    @classmethod
    def from_file(
        cls,
        result_file: str,
        *,
        min_group_score: float = 0.7,
        required_groups: Optional[List[str]] = None,
        fail_on_warn: bool = False,
    ) -> "HarnessEvaluationGate":
        """JSON 결과 파일에서 Gate를 직접 생성한다.

        Args:
            result_file: ``monitor.save_to_file()``이 생성한 JSON 경로.

        Returns:
            ``HarnessEvaluationGate`` 인스턴스.

        Example::

            gate = HarnessEvaluationGate.from_file("results/eval.json")
            gate.enforce()
        """
        import json

        with open(result_file, encoding="utf-8") as _f:
            data: Dict[str, Any] = json.load(_f)

        class _ReportProxy:
            """JSON 데이터를 EvaluationReport처럼 노출하는 최소 프록시."""
            def __init__(self, extra: Dict[str, Any]) -> None:
                self.extra_metrics = extra

        # JSON 최상위에 extra_metrics 또는 harness_groups 키가 있을 수 있음
        extra = data.get("extra_metrics") or {}
        if "harness_groups" not in extra and "harness_groups" in data:
            extra = {"harness_groups": data["harness_groups"]}

        return cls(
            _ReportProxy(extra),
            min_group_score=min_group_score,
            required_groups=required_groups,
            fail_on_warn=fail_on_warn,
        )

    # ------------------------------------------------------------------
    # Property
    # ------------------------------------------------------------------

    @property
    def result(self) -> Optional[Dict[str, Any]]:
        """마지막 ``evaluate()`` 또는 ``enforce()`` 결과. 호출 전에는 ``None``."""
        return self._result

    @property
    def passed(self) -> Optional[bool]:
        """``evaluate()`` 호출 후 통과 여부. 호출 전에는 ``None``."""
        return self._result["passed"] if self._result is not None else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _print_result(self, result: Dict[str, Any]) -> None:
        ok = result["passed"]
        summary = result["summary"]
        print(f"\n{'=' * 52}")
        print(f"  Harness Evaluation Gate: {'PASSED ✅' if ok else 'FAILED ❌'}")
        print(f"{'─' * 52}")
        for g in sorted(result["groups"]):
            r = result["groups"][g]
            icon = "✅" if r["passed"] else "❌"
            score_str = f"{r['score']:.3f}" if r["score"] is not None else "n/a"
            print(f"  {icon} Group {g}: {score_str}  ({r['status']})")
        print(f"{'─' * 52}")
        print(
            f"  Passed: {summary['passed_groups']}/{summary['total_groups']} groups"
            + (f"  |  Overall: {summary['overall_score']:.3f}" if summary["overall_score"] is not None else "")
        )
        if result["violations"]:
            print(f"\n  ⚠ Violations:")
            for v in result["violations"]:
                print(f"    Group {v['group']}: score={v['score']:.3f}  status={v['status']}")
        print(f"{'=' * 52}\n")

    def __repr__(self) -> str:
        status = "evaluated" if self._result else "pending"
        return (
            f"HarnessEvaluationGate("
            f"min_score={self._min_group_score}, "
            f"groups={self._required_groups!r}, "
            f"status={status!r})"
        )
