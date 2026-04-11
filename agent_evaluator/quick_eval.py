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
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, overload

logger = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])

__all__ = ["QuickEval"]


class _QuickEvalDecorator:
    """QuickEval 속성 접근 시 반환되는 데코레이터 헬퍼.

    괄호 없이 ``@eval.qa`` 로도, 파라미터와 함께 ``@eval.qa(score_fn=...)`` 로도 동작한다.
    """

    def __init__(self, eval_decorator: Any, task_type: str) -> None:
        self._eval = eval_decorator
        self._task_type = task_type

    @overload
    def __call__(self, func: _F) -> _F: ...
    @overload
    def __call__(self, func: None = None, **kwargs: Any) -> Callable[[_F], _F]: ...
    def __call__(self, func_or_kwargs: Any = None, **kwargs: Any) -> Any:
        """괄호 없이 함수에 직접 적용하거나 kwargs와 함께 호출한다.

        Usage::

            @eval.qa                       # 괄호 없이
            def f(q, ground_truth=""): ...

            @eval.qa(score_fn=my_fn)       # kwargs와 함께
            def f(q, ground_truth=""): ...
        """
        if callable(func_or_kwargs):
            # @eval.qa (괄호 없음) — 함수에 직접 적용
            return self._eval(task_type=self._task_type)(func_or_kwargs)
        elif func_or_kwargs is None:
            # @eval.qa() 또는 @eval.qa(score_fn=...) — 데코레이터 반환
            return self._eval(task_type=self._task_type, **kwargs)
        else:
            raise TypeError(
                f"_QuickEvalDecorator.__call__: callable 또는 키워드 인자를 기대합니다, "
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
                        f"QuickEval: PerformanceMonitor에 알 수 없는 파라미터가 전달됩니다 "
                        f"(무시됨): {sorted(_invalid)}",
                        UserWarning,
                        stacklevel=2,
                    )
                    for _k in _invalid:
                        monitor_kwargs.pop(_k)
            except Exception as _e:
                logger.debug("QuickEval.__init__: monitor_kwargs 검사 실패 (무시): %s", _e)

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
            flush_filename=flush_filename,
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
                logger.debug("for_regression_eval: baseline 로드 실패 (무시): %s", _e)
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
                print("성능 회귀 감지!", report["regressions"])
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
        model: str = "gpt-4o-mini",
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
        kwargs.setdefault("judge_model", model)
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
                f"알 수 없는 preset '{preset_name}'. "
                f"사용 가능한 preset: {valid}\n"
                f"예: QuickEval.from_preset('rag', 'results/')"
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
    # 단축 데코레이터 속성 — @eval.qa, @eval.tool_use 등
    # ------------------------------------------------------------------

    @property
    def qa(self) -> _QuickEvalDecorator:
        """``task_type="qa"`` 데코레이터. 괄호 없이 사용 가능.

        Usage::

            @eval.qa
            def agent(question, ground_truth=""): ...

            @eval.qa(score_fn=my_fn)
            def agent(question, ground_truth=""): ...
        """
        return _QuickEvalDecorator(self._eval, "qa")

    @property
    def tool_use(self) -> _QuickEvalDecorator:
        """``task_type="tool_use"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "tool_use")

    @property
    def rag(self) -> _QuickEvalDecorator:
        """``task_type="information_retrieval"`` + ``context_arg="context"`` 데코레이터.

        Usage::

            @eval.rag
            def rag_agent(question, context="", ground_truth=""): ...
        """
        class _RagDecorator(_QuickEvalDecorator):
            def __call__(self_inner, func_or_kwargs=None, **kwargs):
                kwargs.setdefault("context_arg", "context")
                return super().__call__(func_or_kwargs, **kwargs)
        return _RagDecorator(self._eval, "information_retrieval")

    @property
    def code(self) -> _QuickEvalDecorator:
        """``task_type="code_generation"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "code_generation")

    @property
    def reasoning(self) -> _QuickEvalDecorator:
        """``task_type="reasoning"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "reasoning")

    @property
    def planning(self) -> _QuickEvalDecorator:
        """``task_type="planning"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "planning")

    @property
    def data_analysis(self) -> _QuickEvalDecorator:
        """``task_type="data_analysis"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "data_analysis")

    @property
    def creative(self) -> _QuickEvalDecorator:
        """``task_type="creative"`` 데코레이터."""
        return _QuickEvalDecorator(self._eval, "creative")

    @property
    def chat(self) -> Any:
        """멀티턴 대화 평가 데코레이터 (``conversation_eval``).

        Usage::

            @eval.chat
            def chatbot(question, session_id="default"): ...

            @eval.chat(max_turns=10)
            def chatbot(question, session_id="default"): ...
        """
        eval_dec = self._eval

        class _ChatDecorator:
            def __call__(self_inner, func_or_kwargs=None, **kwargs):
                if callable(func_or_kwargs):
                    return eval_dec.conversation()(func_or_kwargs)
                elif func_or_kwargs is None:
                    return eval_dec.conversation(**kwargs)
                else:
                    raise TypeError("callable 또는 kwargs를 기대합니다")

        return _ChatDecorator()

    @property
    def batch(self) -> Any:
        """배치 처리 평가 데코레이터 (``batch_eval``).

        Usage::

            @eval.batch
            def batch_agent(questions, ground_truths=None): ...
        """
        eval_dec = self._eval

        class _BatchDecorator:
            def __call__(self_inner, func_or_kwargs=None, **kwargs):
                if callable(func_or_kwargs):
                    return eval_dec.batch()(func_or_kwargs)
                elif func_or_kwargs is None:
                    return eval_dec.batch(**kwargs)
                else:
                    raise TypeError("callable 또는 kwargs를 기대합니다")

        return _BatchDecorator()

    # ------------------------------------------------------------------
    # 직접 호출 — @eval(task_type="qa") 형태
    # ------------------------------------------------------------------

    def __call__(self, task_type: Any = "qa", **kwargs: Any) -> Callable:
        """``@eval(task_type=...)`` 형태로 데코레이터를 직접 생성한다.

        Usage::

            @eval(task_type="qa", score_fn=my_fn)
            def agent(question, ground_truth=""): ...
        """
        return self._eval(task_type=task_type, **kwargs)

    def with_retry(self, task_type: Any = "qa", **kwargs: Any) -> Callable:
        """재시도 내장 데코레이터 (``agent_eval_with_retry``).

        Usage::

            @eval.with_retry(task_type="qa", max_retries=3, delay=1.0, backoff=2.0, jitter=True)
            def fragile_agent(question, ground_truth=""): ...
        """
        return self._eval.with_retry(task_type=task_type, **kwargs)

    @property
    def multi_agent(self) -> _QuickEvalDecorator:
        """멀티 에이전트 협업 평가 데코레이터 ``task_type="coordination"`` (A8).

        Usage::

            @eval.multi_agent
            def crew_task(question, ground_truth=""): ...
        """
        return _QuickEvalDecorator(self._eval, "coordination")

    @property
    def security(self) -> _QuickEvalDecorator:
        """보안 평가 데코레이터 ``task_type="tool_use"`` + ``framework="native"`` (A8).

        보안 지표(InputSanitization, OutputLeakage 등)가 활성화된 경우에 유용하다.

        Usage::

            eval = QuickEval.for_security("results/")

            @eval.security
            def secure_agent(question, ground_truth=""): ...
        """
        return _QuickEvalDecorator(self._eval, "tool_use")

    @property
    def streaming(self) -> _QuickEvalDecorator:
        """generator / async generator 함수 전용 데코레이터.

        ``agent_eval`` 이 generator 함수를 자동 감지하므로 ``@eval.qa`` 와 동일하게
        동작하지만, 스트리밍 의도를 명시적으로 표현한다.

        Usage::

            @eval.streaming
            def agent(question, ground_truth=""):
                for chunk in llm.stream(question):  # sync generator
                    yield chunk

            @eval.streaming
            async def async_agent(question, ground_truth=""):
                async for chunk in llm.astream(question):  # async generator
                    yield chunk
        """
        return _QuickEvalDecorator(self._eval, "qa")

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
        **thresholds: float,
    ) -> Union[bool, Dict[str, Any]]:
        """CI/CD 품질 게이팅 — 임계값 미달 시 ``SystemExit`` 발생.

        Args:
            tcr: Task Completion Rate 최소값 (0–100).
            accuracy: Accuracy 최소값 (0–100).
            config_file: JSON 파일 경로.  ``{"tcr": 85, "accuracy": 70, "latency_p95": 5.0}``
                형태의 임계값을 읽는다.  직접 지정한 파라미터가 파일 값보다 우선한다.
            dry_run: ``True`` 이면 ``sys.exit()`` 를 호출하지 않고 결과를 dict 로 반환한다.
                ``{"passed": bool, "results": {metric: {"current": float, "threshold": float,
                "passed": bool}}}`` 형식.
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
                logger.warning("gate config_file 로드 실패 (무시): %s", _e)

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
                failures.append(f"TCR {actual_tcr:.1f}% < 요구 {tcr}%")

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
                failures.append(f"Accuracy {actual_acc:.1f}% < 요구 {accuracy}%")

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
                failures.append(f"P95 지연 {p95:.2f}s > 허용 {req}s")

        # A7: quality / hallucination 임계값 지원
        if "quality" in thresholds:
            # H2: quality 트래커가 비활성화된 경우 경고
            _quality_enabled = getattr(self._monitor, "_enable_quality", True)
            if not _quality_enabled:
                import warnings as _w
                _w.warn(
                    "QuickEval.gate(quality=...): quality 트래킹이 비활성화되어 있어 "
                    "실제 값은 0.0입니다. PerformanceMonitor 설정을 확인하세요.",
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
                failures.append(f"Quality {actual_q:.1f} < 요구 {req_q}")

        if "hallucination" in thresholds:
            # H2: hallucination 트래커가 비활성화된 경우 경고
            _hall_enabled = getattr(self._monitor, "_enable_hallucination_detection", False)
            if not _hall_enabled:
                import warnings as _w
                _w.warn(
                    "QuickEval.gate(hallucination=...): hallucination 탐지가 비활성화되어 있어 "
                    "실제 값은 0.0입니다. QuickEval.for_rag() 또는 "
                    "enable_hallucination_detection=True 를 사용하세요.",
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
                failures.append(f"Hallucination rate {actual_h:.1f}% > 허용 {req_h}%")

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
                    f"평균 토큰 수 {_avg_tokens:.1f} > 허용 {token_efficiency_min}"
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
                logger.debug("gate: tool_f1 조회 실패, 0.0 사용: %s", _e)
                _f1 = 0.0
            _tool_pass = _f1 >= tool_f1_min
            dry_run_results["tool_f1"] = {
                "current": round(_f1, 4),
                "threshold": tool_f1_min,
                "passed": _tool_pass,
            }
            if not _tool_pass:
                failures.append(f"Tool F1 {_f1:.4f} < 요구 {tool_f1_min}")

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
                logger.debug("gate: coordination_success_rate 조회 실패, 0.0 사용: %s", _e)
                _csr = 0.0
            _coord_pass = _csr >= coordination_success_rate_min
            dry_run_results["coordination_success_rate"] = {
                "current": round(_csr, 4),
                "threshold": coordination_success_rate_min,
                "passed": _coord_pass,
            }
            if not _coord_pass:
                failures.append(
                    f"Coordination success rate {_csr:.4f} < 요구 {coordination_success_rate_min}"
                )

        if dry_run:
            return {
                "passed": len(failures) == 0,
                "results": dry_run_results,
            }

        if failures:
            msg = "QuickEval 품질 게이팅 실패:\n" + "\n".join(f"  - {f}" for f in failures)
            logger.error(msg)
            print(msg)
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

    def compare(self, other: "QuickEval") -> Dict[str, Any]:
        """두 QuickEval 인스턴스의 주요 지표를 비교한다 (D1).

        Args:
            other: 비교 대상 :class:`QuickEval` 인스턴스.

        Returns:
            ``{"self": {...}, "other": {...}, "delta": {...}}`` 구조.
            ``delta`` 는 ``self - other`` 기준이며 양수가 self 가 더 좋음을 의미한다.

        Example::

            baseline = QuickEval("results/baseline/")
            # ... baseline 평가 실행 ...

            candidate = QuickEval("results/candidate/")
            # ... candidate 평가 실행 ...

            diff = baseline.compare(candidate)
            print(f"TCR 변화: {diff['delta']['tcr']:+.1f}%")
        """
        def _summary(qe: "QuickEval") -> Dict[str, Any]:
            return qe.summary()

        s = _summary(self)
        o = _summary(other)
        delta: Dict[str, Any] = {}
        for key in ("tcr", "accuracy", "avg_latency", "total_tokens", "total_tasks"):
            sv = s.get(key, 0.0)
            ov = o.get(key, 0.0)
            try:
                delta[key] = round(float(sv) - float(ov), 4)
            except (TypeError, ValueError):
                delta[key] = None

        return {"self": s, "other": o, "delta": delta}

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
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_file}")

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
            raise RuntimeError("기록된 태스크가 없습니다. 평가를 먼저 실행하세요.")
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
                logger.debug("replay: TaskResult 로드 실패 (무시): %s", _e)
        logger.info("replay: %d개 태스크 로드 완료 (%s)", len(tasks_data), results_file)
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
                                    logger.debug("watch: 파일 처리 실패 (무시): %s", _e)
                        _seen.update(_current)
                        # H4: _seen 집합 크기 상한 — 메모리 누수 방지
                        if len(_seen) > max_watched_files:
                            _trim = len(_seen) - max_watched_files
                            _seen -= set(list(_seen)[:_trim])
                    except Exception as _e:
                        logger.debug("watch: 폴링 실패 (무시): %s", _e)
                    _t.sleep(5)

            def stop(self_h) -> None:
                self_h._stopped = True

        return _WatchHandle()

    def __repr__(self) -> str:
        total = self._monitor.task_count  # D7: task_count property 사용
        return f"QuickEval(output_dir={self._monitor.output_dir!r}, tasks={total})"
