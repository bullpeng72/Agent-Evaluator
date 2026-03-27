#!/usr/bin/env python3
"""
CrewAI Integration - Full 3-Layer Metrics Support
==================================================

CrewAI 1.x Crew 객체를 래핑하여 평가 지표를 자동으로 추적합니다.

주요 기능:
- Layer 1: Native Metrics — TCR, Accuracy, Latency, Token Economy, ResponseQuality
  - crew.usage_metrics 를 통한 실제 토큰 수 추출 (crewai 1.x)
- Layer 2: Agentic AI Metrics — Tool Selection, Agent Coordination, Workflow Execution
  - task_callback 주입으로 태스크별 실시간 타이밍 수집 (crewai 1.x)
  - step_callback 주입으로 도구 호출 실시간 추적 (crewai 1.x)
  - result.tasks_output 를 통한 태스크별 실제 에이전트/결과 추적 (fallback)
- Security (opt-in): enable_security=True 로 InputSanitization / OutputLeakage / ToolAuthorization 활성화
- kickoff_async() 지원 (async 실행)

사용 방법:
    from agent_evaluator.integrations import CrewAIEvaluator

    crew = Crew(agents=[...], tasks=[...])
    evaluator = CrewAIEvaluator(crew, monitor, enable_layer2=True)

    result = evaluator.kickoff(
        inputs={'topic': 'AI trends'},
        ground_truth='Expected answer...',
        expected_tools=['search', 'analysis']
    )

요구 사항:
    pip install "agent-evaluator[crewai]"
    crewai >= 1.0.0
"""

import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType

try:
    from ..helpers.taskresult_helpers import (
        create_taskresult_from_execution,
        calculate_accuracy_score,
    )
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    create_taskresult_from_execution = None
    calculate_accuracy_score = None  # type: ignore[assignment]

try:
    from crewai import Crew
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


def _ensure_security_trackers(
    monitor: PerformanceMonitor,
    privilege_registry: Optional[Dict[str, str]] = None,
) -> None:
    """
    monitor에 보안 트래커가 없으면 자동으로 초기화합니다.
    Layer 1 (InputSanitization, OutputLeakage, ToolAuthorization) +
    Layer 2 (PrivilegeEscalation, ToolChainAttack) 모두 포함.

    Args:
        privilege_registry: tool_name → privilege_level 매핑 dict.
            제공 시 _infer_privilege_level() 휴리스틱보다 우선 적용됩니다.
    """
    from ..core.agent_evaluator import (
        InputSanitizationTracker, OutputLeakageDetector, ToolAuthorizationTracker,
        PrivilegeEscalationDetector, ToolChainAttackDetector,
    )
    if getattr(monitor, "input_sanitizer", None) is None:
        monitor.input_sanitizer = InputSanitizationTracker()
    if getattr(monitor, "output_leakage_detector", None) is None:
        monitor.output_leakage_detector = OutputLeakageDetector()
    if getattr(monitor, "tool_authorizer", None) is None:
        _allowed = getattr(monitor, "_authorized_tools", None) or None
        monitor.tool_authorizer = ToolAuthorizationTracker(
            allowed_tools=_allowed if _allowed else None
        )
    if getattr(monitor, "privilege_escalation_detector", None) is None:
        monitor.privilege_escalation_detector = PrivilegeEscalationDetector()
    if getattr(monitor, "tool_chain_attack_detector", None) is None:
        monitor.tool_chain_attack_detector = ToolChainAttackDetector()
    # 보안 트래커가 초기화된 이상 generate_report() / _generate_alerts() 가 포함하도록 플래그 동기화
    monitor.enable_security_metrics = True
    if privilege_registry and not getattr(monitor, "privilege_registry", None):
        monitor.privilege_registry = privilege_registry
    elif not getattr(monitor, "privilege_registry", None):
        monitor.privilege_registry = {}
    # authorized_tools 미설정 경고 — DQ-011: __auth_warned__ 마크로 중복 경고 방지
    if (not getattr(monitor, "_authorized_tools", None)
            and not getattr(monitor, "__auth_warned__", False)):
        monitor.__auth_warned__ = True  # type: ignore[attr-defined]
        import warnings as _w
        _w.warn(
            "ToolAuthorizationTracker: authorized_tools not set — all tool calls will pass authorization. "
            "Pass authorized_tools=['tool_a', 'tool_b'] to the evaluator for meaningful security metrics.",
            UserWarning,
            stacklevel=3,
        )
    # M6: privilege_registry 미설정 경고 — FA2 fix: __configured__ 마크로 중복 경고 방지
    if not privilege_registry and not getattr(monitor, "privilege_registry", {}).get("__configured__"):
        monitor.privilege_registry["__configured__"] = True
        import warnings as _w
        _w.warn(
            "PrivilegeEscalationDetector: privilege_registry not configured — using keyword heuristic only. "
            "Generic tool names (e.g., 'call_api', 'query_data') may be misclassified as 'read'. "
            "Pass privilege_registry={'tool_name': 'admin|write|read'} for accurate escalation detection.",
            UserWarning,
            stacklevel=3,
        )


def _resolve_privilege_level(tool_name: str, monitor: Optional[Any] = None) -> str:
    """
    도구 권한 수준 결정:
    1순위: monitor.privilege_registry[tool_name] (실제 설정)
    2순위: infer_privilege_level() 휴리스틱 (키워드 기반, framework_integrations 공유)
    """
    from .framework_integrations import infer_privilege_level
    registry: Dict[str, str] = getattr(monitor, "privilege_registry", {}) or {}
    if tool_name in registry:
        return registry[tool_name]
    return infer_privilege_level(tool_name)


class CrewAIEvaluator:
    """
    CrewAI 1.x Crew 평가 클래스 (Layer 1/2 지원)

    crewai 1.x 에서 변경된 주요 API:
    - kickoff() 결과가 CrewOutput 객체 (result.raw 로 텍스트 추출)
    - crew.usage_metrics 로 실제 토큰 수 접근
    - result.tasks_output 로 태스크별 에이전트 이름·결과 접근
    - task_callback / step_callback 으로 실시간 타이밍·도구 추적
    """

    def __init__(
        self,
        crew: Any,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_security: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True,
        privilege_registry: Optional[Dict[str, str]] = None,
        authorized_tools: Optional[List[str]] = None,
    ):
        """
        CrewAIEvaluator 초기화

        Args:
            crew: CrewAI Crew 객체
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_security: 보안 지표 활성화 (opt-in, 성능 영향)
            task_type: TaskResult 타입
            verbose: 상세 출력
        """
        if not CREWAI_AVAILABLE:
            raise ImportError(
                "CrewAI is not installed. "
                "Install with: pip install 'agent-evaluator[crewai]'"
            )
        self.crew = crew
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_security = enable_security
        self.task_type = task_type
        self.verbose = verbose
        self.authorized_tools: List[str] = list(authorized_tools or [])
        if self.authorized_tools:
            self.monitor._authorized_tools = self.authorized_tools

        self.execution_history: List[Dict[str, Any]] = []
        self._tasks_with_ground_truth: int = 0  # ground_truth 제공 횟수 추적 (Accuracy N/A 판단용)
        self._current_task_id: Optional[str] = None
        self._workflow_steps: List[tuple] = []    # (name, success, duration)
        self._agent_interactions: List[tuple] = []  # (from_agent, to_agent, success)
        self._tool_usage: List[tuple] = []           # (tool_name, success, duration, parameters, execution_result)
        self._last_task_checkpoint: float = 0.0
        self._last_agent: Optional[str] = None
        self._last_task_success: bool = True
        self._last_step_time: float = 0.0

        if enable_security:
            _ensure_security_trackers(self.monitor, privilege_registry=privilege_registry)
        elif privilege_registry:
            self.monitor.privilege_registry = privilege_registry

        if self.verbose:
            print(f"✅ CrewAIEvaluator 초기화 완료 "
                  f"(Layer2: {enable_layer2}, Security: {enable_security})")

    # ── 실시간 콜백 (crewai 1.x task_callback / step_callback) ──────────

    def _setup_callbacks(self):
        """kickoff() 전 실시간 콜백을 crew 객체에 주입합니다."""
        try:
            try:
                self.crew.task_callback = self._on_task_complete
                self.crew.step_callback = self._on_step
            except Exception:
                object.__setattr__(self.crew, "task_callback", self._on_task_complete)
                object.__setattr__(self.crew, "step_callback", self._on_step)
        except Exception:
            pass  # 콜백 주입 실패 시 post-execution 방식으로 fallback

    def _on_task_complete(self, task_output: Any):
        """
        crewai 1.x task_callback: 태스크 완료 시 호출됩니다.
        태스크 간 체크포인트 시간 차를 이용해 근사 실행 시간을 계산합니다.
        """
        now = time.time()
        elapsed = now - self._last_task_checkpoint if self._last_task_checkpoint else 0.0
        self._last_task_checkpoint = now

        desc = getattr(task_output, "description", None) or f"task_{len(self._workflow_steps)}"
        agent_name = getattr(task_output, "agent", None) or ""
        # agent_name 없으면 crew.agents 순서 매핑 시도, 최후 fallback으로 인덱스 기반 이름
        if not agent_name:
            _step_idx = len(self._workflow_steps)
            _agents = getattr(self.crew, "agents", []) or []
            if _step_idx < len(_agents):
                agent_name = (
                    getattr(_agents[_step_idx], "name", None)
                    or getattr(_agents[_step_idx], "role", None)
                    or f"crew_agent_{_step_idx + 1}"
                )
            else:
                agent_name = f"crew_agent_{_step_idx + 1}"
        raw_out = getattr(task_output, "raw", "") or ""
        # DQ-019/DQ-028: 공백 전용 응답은 실패로 처리. str 타입 보장으로 미래 버전 대응
        task_success = isinstance(raw_out, str) and bool(raw_out.strip())

        self._workflow_steps.append((str(desc), task_success, elapsed, agent_name))

        if self._last_agent and self._last_agent != agent_name:
            # from-agent의 success(이전 태스크 완료 여부)로 전환 성공 판단
            self._agent_interactions.append((self._last_agent, agent_name, self._last_task_success))
        self._last_agent = agent_name
        self._last_task_success = task_success

    def _on_step(self, step: Any):
        """
        crewai 1.x step_callback: 에이전트 스텝(도구 호출 포함) 시 호출됩니다.
        tool_name 과 parameters 를 함께 수집합니다.
        """
        tool_name = None
        params: Dict[str, Any] = {}
        if isinstance(step, dict):
            tool_name = step.get("tool") or step.get("tool_name")
            raw_params = step.get("parameters") or step.get("inputs") or step.get("tool_input")
        else:
            tool_name = getattr(step, "tool", None) or getattr(step, "tool_name", None)
            raw_params = (
                getattr(step, "parameters", None)
                or getattr(step, "inputs", None)
                or getattr(step, "tool_input", None)
            )
        if isinstance(raw_params, dict):
            params = raw_params
        elif isinstance(raw_params, str) and raw_params.strip():
            try:
                import json as _json
                _parsed = _json.loads(raw_params)
                if isinstance(_parsed, dict):
                    params = _parsed
            except Exception:
                params = {"input": raw_params}

        if tool_name:
            # 도구 실패 감지: step 객체의 error/is_error/exception 필드 확인
            if isinstance(step, dict):
                tool_error = step.get("error") or step.get("exception") or step.get("is_error")
            else:
                tool_error = (
                    getattr(step, "error", None)
                    or getattr(step, "exception", None)
                    or getattr(step, "is_error", None)
                )
            tool_success = not bool(tool_error)
            # 도구 실행 결과 추출 (OutputLeakage + ToolCallAnalyzer 활용)
            exec_result = ""
            if isinstance(step, dict):
                _raw_result = step.get("result") or step.get("output") or step.get("result_text") or ""
            else:
                _raw_result = (
                    getattr(step, "result", None)
                    or getattr(step, "output", None)
                    or getattr(step, "result_text", None)
                    or ""
                )
            if _raw_result:
                # DQ-010: 500 → 2000자 — 긴 도구 출력의 민감 데이터 탐지 범위 확대
                exec_result = str(_raw_result)[:2000]
            # 실제 도구 실행 시간 측정 (이전 스텝 이후 경과 시간)
            now = time.time()
            step_dur = now - self._last_step_time if self._last_step_time else 0.0
            self._last_step_time = now
            self._tool_usage.append((str(tool_name), tool_success, step_dur, params, exec_result))

    # ── 실행 ─────────────────────────────────────────────────────────────

    def kickoff(
        self,
        inputs: Dict[str, Any],
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> Any:
        """
        Crew를 동기 실행하고 평가 지표를 수집합니다.

        Args:
            inputs: crew.kickoff(inputs=...) 에 전달할 입력
            ground_truth: 정답 텍스트 (Accuracy 계산용)
            expected_tools: 기대 도구 목록 (Layer 2 Tool Selection)
            expected_agents: 기대 에이전트 목록 (Layer 2 Coordination)
            expected_elements: ResponseQuality completeness 평가용 기대 요소 목록
                               (None 이면 crew.tasks.expected_output 에서 자동 추출)
            task_id: 작업 ID (없으면 자동 생성)

        Returns:
            CrewOutput 객체 (crewai 1.x)
        """
        if task_id is None:
            # UI-022: 4개 어댑터 공통 ms 타임스탬프 포맷
            task_id = f"crew_{int(time.time() * 1000)}"
        self._current_task_id = task_id
        self._reset_tracking()
        # DQ-002: 빈 문자열 ground_truth는 유의미한 accuracy 측정 불가
        if ground_truth is not None and ground_truth.strip():
            self._tasks_with_ground_truth += 1

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 CrewAI 실행 시작 (Task ID: {task_id})")
            print(f"{'='*70}")

        # 실시간 콜백 주입
        if self.enable_layer2:
            self._setup_callbacks()

        start_time = time.time()
        self._last_task_checkpoint = start_time
        success = True
        errors: List[str] = []
        crew_output = None

        try:
            crew_output = self.crew.kickoff(inputs=inputs)
            if self.verbose:
                print(f"\n✅ Crew 실행 완료")
        except Exception as e:
            success = False
            errors.append(str(e))
            if self.verbose:
                print(f"\n❌ Crew 실행 실패: {e}")

        execution_time = time.time() - start_time

        # task_callback 이 주입되지 않았거나 내용이 비어 있으면 fallback (execution_time 이후)
        if self.enable_layer2 and not self._workflow_steps:
            self._extract_layer2_from_output(crew_output, expected_agents,
                                             execution_time=execution_time)

        # crewai 1.x: CrewOutput.raw 로 텍스트 추출
        response_text = self._extract_response(crew_output)

        # crewai 1.x: crew.usage_metrics 로 실제 토큰 수 추출 (없으면 길이 기반 추정)
        _query_text = self._extract_query_from_inputs(inputs)
        tokens = self._extract_tokens(question=_query_text, response=response_text)

        # 중간 태스크 출력 → RAG 컨텍스트 수집
        retrieved_contexts = self._extract_retrieval_contexts(crew_output)

        self._record_layer1(
            task_id=task_id,
            question=_query_text,
            response=response_text,
            ground_truth=ground_truth,
            execution_time=execution_time,
            success=success,
            errors=errors,
            tokens=tokens,
            retrieved_contexts=retrieved_contexts,
            override_expected_elements=expected_elements,
            inputs=inputs,
        )

        if self.enable_layer2:
            self._record_layer2(task_id, expected_tools, expected_agents,
                                success=success, execution_time=execution_time)

        if self.enable_security:
            self._record_security(task_id, _query_text, response_text, retrieved_contexts)

        # FA3: 표준 실행 히스토리 스키마 (UI-023: input/output 키 통일)
        self.execution_history.append({
            "task_id": task_id,
            "timestamp": datetime.now(),
            "success": success,
            "execution_time": execution_time,
            "framework": "crewai",
            "input": inputs,
            "output": response_text,
        })

        if self.verbose:
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}s)")

        return crew_output

    async def kickoff_async(
        self,
        inputs: Dict[str, Any],
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> Any:
        """
        Crew를 비동기 실행하고 평가 지표를 수집합니다.

        사용 방법:
            result = await evaluator.kickoff_async(inputs={...})
        """
        if task_id is None:
            # UI-022: 4개 어댑터 공통 ms 타임스탬프 포맷
            task_id = f"crew_{int(time.time() * 1000)}"
        self._current_task_id = task_id
        self._reset_tracking()
        # DQ-002: 빈 문자열 ground_truth는 유의미한 accuracy 측정 불가
        if ground_truth is not None and ground_truth.strip():
            self._tasks_with_ground_truth += 1

        if self.enable_layer2:
            self._setup_callbacks()

        start_time = time.time()
        self._last_task_checkpoint = start_time
        success = True
        errors: List[str] = []
        crew_output = None

        try:
            crew_output = await self.crew.kickoff_async(inputs=inputs)
        except Exception as e:
            success = False
            errors.append(str(e))

        execution_time = time.time() - start_time

        if self.enable_layer2 and not self._workflow_steps:
            self._extract_layer2_from_output(crew_output, expected_agents,
                                             execution_time=execution_time)
        response_text = self._extract_response(crew_output)
        _query_text = self._extract_query_from_inputs(inputs)
        tokens = self._extract_tokens(question=_query_text, response=response_text)
        retrieved_contexts = self._extract_retrieval_contexts(crew_output)

        self._record_layer1(
            task_id=task_id,
            question=_query_text,
            response=response_text,
            ground_truth=ground_truth,
            execution_time=execution_time,
            success=success,
            errors=errors,
            tokens=tokens,
            retrieved_contexts=retrieved_contexts,
            override_expected_elements=expected_elements,
            inputs=inputs,
        )
        if self.enable_layer2:
            self._record_layer2(task_id, expected_tools, expected_agents,
                                success=success, execution_time=execution_time)
        if self.enable_security:
            self._record_security(task_id, _query_text, response_text, retrieved_contexts)

        # FA3: 표준 실행 히스토리 스키마 (UI-023: input/output 키 통일)
        self.execution_history.append({
            "task_id": task_id,
            "timestamp": datetime.now(),
            "success": success,
            "execution_time": execution_time,
            "framework": "crewai",
            "input": inputs,
            "output": response_text,
        })
        return crew_output

    def run(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """kickoff()의 framework-agnostic 별칭 (EvaluatorProtocol 통일 인터페이스).

        다른 프레임워크(LangChain·LangGraph·AutoGen)의 ``run()`` 과 동일한 방식으로
        호출할 수 있도록 ``kickoff()`` 를 위임합니다.

        Args:
            user_input: crew.kickoff(inputs=...) 에 전달할 입력 (dict 또는 문자열)
            ground_truth: 정답 텍스트 (Accuracy 계산용)
            expected_tools: 기대 도구 목록
            expected_agents: 기대 에이전트 목록 (CrewAI 전용)
            expected_elements: ResponseQuality 기대 요소
            **kwargs: kickoff() 에 전달될 추가 파라미터
        """
        from .framework_integrations import to_crew_inputs
        return self.kickoff(
            inputs=to_crew_inputs(user_input),
            ground_truth=ground_truth,
            expected_tools=expected_tools,
            expected_agents=expected_agents,
            expected_elements=expected_elements,
            **kwargs,
        )

    def run_sync(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """run()의 동기 래퍼 별칭 — EvaluatorProtocol.run_sync() 인터페이스 충족.

        ``user_input`` 은 dict 또는 문자열 모두 허용합니다.
        문자열인 경우 ``to_crew_inputs()`` 로 inputs dict로 변환 후 전달합니다.
        CrewAI는 항상 동기이므로 run() 을 그대로 위임합니다.
        """
        return self.run(
            user_input,
            ground_truth=ground_truth,
            expected_tools=expected_tools,
            expected_elements=expected_elements,
            expected_agents=expected_agents,
            **kwargs,
        )

    # ── 추출 헬퍼 ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_query_from_inputs(inputs: Any) -> str:
        """
        kickoff() 입력에서 실제 사용자 쿼리 텍스트를 추출합니다.

        우선순위:
        1. dict: "query", "question", "topic", "task", "input", "prompt" 키 순서로 탐색
        2. dict: 첫 번째 str 값 (길이가 가장 긴 것 우선)
        3. str: 그대로 반환
        4. 기타: str() 변환 (last resort, InputSanitization에 dict repr 대신 의미있는 값 전달)
        """
        if isinstance(inputs, str):
            return inputs
        if isinstance(inputs, dict):
            for key in ("query", "question", "topic", "task", "input", "prompt", "message", "text"):
                if key in inputs and isinstance(inputs[key], str):
                    return inputs[key]
            # fallback: 가장 긴 str 값
            str_vals = [(k, v) for k, v in inputs.items() if isinstance(v, str) and v.strip()]
            if str_vals:
                return max(str_vals, key=lambda kv: len(kv[1]))[1]
        return str(inputs)

    def _extract_response(self, crew_output: Any) -> str:
        """CrewOutput(crewai 1.x) 또는 문자열에서 응답 텍스트 추출"""
        if crew_output is None:
            return ""
        # crewai 1.x: CrewOutput.raw
        raw = getattr(crew_output, "raw", None)
        if raw is not None:
            return str(raw)
        return str(crew_output)

    def _extract_tokens(self, question: str = "", response: str = "") -> Dict[str, int]:
        """
        crewai 1.x: crew.usage_metrics 에서 실제 토큰 수 추출.

        usage_metrics 는 kickoff() 이후 crew 객체에 설정됩니다.
        UsageMetrics(prompt_tokens, completion_tokens, total_tokens, ...)
        Fallback: usage_metrics 없으면 입력/출력 텍스트 길이 기반 추정.
        """
        tokens: Dict[str, int] = {"input": 0, "output": 0}
        usage = getattr(self.crew, "usage_metrics", None)
        if usage is not None:
            # DQ-043: `or` 연산자는 정수 0을 falsy로 처리 → 첫 필드가 0이면 다음 필드로 넘어가는 버그
            # is not None 체크로 변경: 0은 유효한 토큰 수이므로 None이 아닌 한 사용
            def _first_not_none(*attrs: str) -> Optional[int]:
                for attr in attrs:
                    _v = getattr(usage, attr, None)
                    if _v is not None:
                        return int(_v)
                return None

            _pt = _first_not_none("prompt_tokens", "total_prompt_tokens", "input_tokens")
            _ct = _first_not_none("completion_tokens", "total_completion_tokens", "output_tokens")
            if _pt is not None:
                tokens["input"] = max(0, _pt - getattr(self, "_prev_input_tokens", 0))
            if _ct is not None:
                tokens["output"] = max(0, _ct - getattr(self, "_prev_output_tokens", 0))
        # Fallback: usage_metrics 없거나 실제 0일 때만 텍스트 길이 기반 추정
        # (API가 명시적으로 0을 반환한 경우와 미수집을 구분하기 위해 == 0 명시 비교)
        if tokens["input"] == 0 and tokens["output"] == 0:
            tokens["input"] = max(1, len(question) // 4) if question else 0
            tokens["output"] = max(1, len(response) // 4) if response else 0
        return tokens

    def _extract_model_name(self) -> str:
        """crew.agents[0].llm 에서 모델명 추출 (TokenEconomy 비용 계산용)"""
        for agent in getattr(self.crew, "agents", []):
            llm = getattr(agent, "llm", None)
            if llm is None:
                continue
            name = (
                getattr(llm, "model_name", "")
                or getattr(llm, "model", "")
                or getattr(llm, "deployment_name", "")
            )
            if name:
                return str(name)
        return ""

    def _extract_layer2_from_output(
        self,
        crew_output: Any,
        expected_agents: Optional[List[str]],
        execution_time: float = 0.0,
    ):
        """
        crewai 1.x: result.tasks_output 에서 태스크별 에이전트·결과를 추출해
        workflow_steps 와 agent_interactions 를 자동으로 구성합니다.
        (task_callback 주입 실패 시 fallback)
        execution_time: crew 전체 실행 시간 — 태스크 수로 균등 분배
        """
        tasks_output = getattr(crew_output, "tasks_output", []) or []

        # 전체 실행 시간을 태스크 수로 균등 분배 (실측 불가 시 최선)
        # M3: task_callback 미작동 시 균등 분배 → duration_estimated=True 마킹
        _n_tasks = max(len(tasks_output), 1)
        _avg_dur = execution_time / _n_tasks if execution_time > 0 else 0.0
        _duration_estimated = _n_tasks > 1  # 복수 태스크에 균등 분배 = 추정값
        # DQ-015: 균등 분배 fallback 사용 시 UserWarning — 실제 태스크 타이밍 아님을 명시
        if _duration_estimated:
            import warnings as _w
            _w.warn(
                f"CrewAI: task_callback 데이터 없음 — 전체 실행 시간을 {_n_tasks}개 태스크에 균등 분배. "
                "task_callback 주입이 정상 작동하면 실측 타이밍이 사용됩니다. "
                "(duration_estimated=True 마킹됨)",
                UserWarning,
                stacklevel=4,
            )

        prev_agent: Optional[str] = None
        prev_success: bool = True
        for i, task_out in enumerate(tasks_output):
            # agent 이름: task_out.agent 우선, 없으면 crew.agents에서 순서 매핑 시도, 최후 fallback
            agent_name = getattr(task_out, "agent", None)
            if not agent_name:
                _agents = getattr(self.crew, "agents", []) or []
                agent_name = getattr(_agents[i], "role", None) if i < len(_agents) else None
                agent_name = agent_name or f"crew_agent_{i + 1}"
            description = getattr(task_out, "description", None) or f"task_{i}"
            raw_out = getattr(task_out, "raw", "") or ""
            # DQ-019/DQ-028: 공백 전용 응답은 실패로 처리. str 타입 보장으로 미래 버전 대응
            task_success = isinstance(raw_out, str) and bool(raw_out.strip())

            # 5번째 원소: duration_estimated 플래그 (task_callback 미작동 시 True)
            self._workflow_steps.append((description, task_success, _avg_dur, agent_name, _duration_estimated))

            if prev_agent and prev_agent != agent_name:
                # 3-tuple 으로 생성 — _on_task_complete 와 동일한 형식
                self._agent_interactions.append((prev_agent, agent_name, prev_success))
            prev_agent = agent_name
            prev_success = task_success

        # crew.agents 에서 도구 목록 추출 (step_callback 없을 때 fallback)
        if not self._tool_usage:
            import re as _re
            # 1순위: tasks_output.raw 에서 ReAct 포맷("Action: X / Action Input: Y") 파싱
            _parsed_any = False
            for task_out in tasks_output:
                raw_str = str(getattr(task_out, "raw", "") or "")
                task_success = bool(raw_str)
                # Action: 단일 라인, Action Input: Observation:/Action: 전까지 multi-line 허용
                actions = _re.findall(r'Action:\s*([^\n]+)', raw_str)
                inputs = _re.findall(
                    r'Action Input:\s*(.*?)(?=\nObservation:|\nAction:|\nThought:|\nFinal Answer:|$)',
                    raw_str, _re.DOTALL
                )
                for j, action in enumerate(actions):
                    tool_name = action.strip()
                    raw_input = inputs[j].strip() if j < len(inputs) else ""
                    params: Dict[str, Any] = {}
                    try:
                        import json as _json
                        parsed = _json.loads(raw_input)
                        if isinstance(parsed, dict):
                            params = parsed
                        else:
                            params = {"input": raw_input} if raw_input else {}
                    except Exception:
                        params = {"input": raw_input} if raw_input else {}
                    self._tool_usage.append((tool_name, task_success, 0.0, params, ""))
                    _parsed_any = True

            # 2순위: crew.agents 도구 목록 (도구 이름만, 실행 정보 없음)
            if not _parsed_any:
                for agent in getattr(self.crew, "agents", []):
                    for tool in getattr(agent, "tools", []):
                        tool_name = getattr(tool, "name", str(tool))
                        self._tool_usage.append((tool_name, True, 0.0, {}, ""))

    def _extract_expected_elements(self, inputs: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        crew.tasks 의 expected_output 필드에서 ResponseQuality expected_elements 추출.

        CrewAI Task.expected_output 은 해당 태스크의 이상적 출력을 기술하므로,
        ResponseQualityEvaluator 의 completeness 차원 평가에 활용할 수 있습니다.
        마지막 태스크(최종 출력)의 expected_output 을 우선하고, 없으면 전체 태스크를 수집합니다.
        task 정보가 없으면 kickoff inputs 텍스트에서 휴리스틱으로 추출합니다.
        """
        import re
        elements: List[str] = []
        seen: set = set()

        def _add(elem: str) -> bool:
            e = elem.strip().rstrip(".,;!? ")
            if e and 2 < len(e) < 120 and e.lower() not in seen:
                seen.add(e.lower())
                elements.append(e)
                return True
            return False

        tasks = getattr(self.crew, "tasks", []) or []

        # 마지막 태스크(최종 출력 태스크)의 expected_output 우선
        for task in reversed(tasks):
            expected_out = str(getattr(task, "expected_output", "") or "")
            if expected_out and len(expected_out) > 10:
                # 문장/구문 단위로 분리해 개별 expected_element로 추가 (LangChain/AutoGen과 동일)
                _phrases = re.split(r"[.;,\n]|(?<=[가-힣])\s+(?=[가-힣A-Za-z])", expected_out)
                _added = 0
                for _phrase in _phrases:
                    _p = _phrase.strip()
                    if _p and len(_p) > 5 and _added < 5:
                        _add(_p)
                        _added += 1
                if not _added:
                    _add(expected_out[:300])
                break

        # 마지막 태스크에 없으면 전체 태스크 description 활용
        if not elements:
            for task in tasks:
                desc = str(getattr(task, "description", "") or "")
                if desc and len(desc) > 10:
                    _add(desc[:200])

        # 태스크 정보 없으면 inputs 텍스트에서 휴리스틱 추출
        if not elements and inputs:
            combined = " ".join(str(v) for v in inputs.values() if v)
            en_patterns = [
                r'(?:include|mention|describe|explain|provide|list|cover|address|discuss|analyze|evaluate|review|assess)\s+([^,\.\n]{3,100})',
            ]
            ko_patterns = [
                r'(?:포함|언급|설명|제공|나열|기술|작성|다루|분석|검토|평가|살펴|알아|논의)(?:해|하|하여|하고|할|하는|되어야|되어|줘|주세요)\s*([^,\.\n]{2,80})',
                r'([^,\.\n]{2,40})(?:의|에\s*대한|에\s*관한)\s+(?:장단점|중요성|의의|상세|이유|효과|문제점|영향)',
            ]
            for pat in en_patterns + ko_patterns:
                for m in re.finditer(pat, combined, re.IGNORECASE):
                    _add(m.group(1))
                    if len(elements) >= 5:
                        return elements
            # Fallback: 콤마/세미콜론 분리
            if not elements and len(combined) < 300:
                parts = [p.strip() for p in re.split(r'[,;]', combined) if p.strip()]
                if 1 < len(parts) <= 6:
                    for p in parts:
                        _add(p)
                        if len(elements) >= 5:
                            break

        return elements[:5]  # 최대 5개

    # ── 검색 컨텍스트 추출 ───────────────────────────────────────────────

    def _extract_retrieval_contexts(self, crew_output: Any) -> List[str]:
        """
        CrewAI 중간 태스크 출력을 RAG 컨텍스트로 활용합니다.

        CrewAI 파이프라인에서 중간 태스크(리서치·검색 등)의 결과물은
        최종 태스크의 입력 컨텍스트 역할을 합니다.
        태스크가 2개 이상인 경우 중간 태스크 출력을 HallucinationDetector 컨텍스트로 수집합니다.
        """
        contexts: List[str] = []
        tasks_output = getattr(crew_output, "tasks_output", []) or []

        _RAG_TASK_KEYWORDS = frozenset({
            "search", "retrieve", "retriev", "query", "find", "fetch",
            "research", "gather", "collect", "look up", "reference",
            "based on", "according to", "from the", "context",
            "문서", "검색", "조회", "참고", "자료", "기반",
        })

        if len(tasks_output) < 2:
            # 단일 태스크: task description에서 RAG 패턴 감지 시 컨텍스트로 활용
            tasks = getattr(self.crew, "tasks", []) or []
            for task in tasks:
                desc = str(getattr(task, "description", "") or "").lower()
                if any(kw in desc for kw in _RAG_TASK_KEYWORDS):
                    # context_vars 또는 expected_output을 컨텍스트 프록시로 사용
                    ctx_vars = getattr(task, "context", None)
                    if ctx_vars:
                        for ctx_task in (ctx_vars if isinstance(ctx_vars, list) else [ctx_vars]):
                            # ctx_task는 실행된 Task 객체: .raw(실행 결과) 우선,
                            # 미실행이면 .expected_output을 proxy로 사용
                            ctx_raw = (
                                str(getattr(ctx_task, "raw", "") or "")
                                or str(getattr(ctx_task, "expected_output", "") or "")
                            )
                            if ctx_raw and len(ctx_raw) >= 20:
                                contexts.append(ctx_raw)
            return contexts

        _RETRIEVAL_KEYWORDS = frozenset({
            "search", "retrieve", "retriev", "query", "find",
            "look", "fetch", "research", "gather", "collect",
        })

        # 중간 태스크(마지막 제외) 출력 수집 — 검색 키워드 우선, 없으면 첫 중간 태스크
        intermediate = tasks_output[:-1]
        found_retrieval = False
        for task_out in intermediate:
            raw = str(getattr(task_out, "raw", "") or "")
            if not raw or len(raw) < 20:
                continue
            desc = str(getattr(task_out, "description", "") or "").lower()
            if any(kw in desc for kw in _RETRIEVAL_KEYWORDS):
                contexts.append(raw)
                found_retrieval = True

        # 검색 키워드 없으면 충분히 긴 중간 태스크만 수집 (노이즈 방지: 50자 미만 제외)
        if not found_retrieval:
            for task_out in intermediate:
                raw = str(getattr(task_out, "raw", "") or "")
                if raw and len(raw) >= 50:
                    contexts.append(raw)

        return contexts

    # ── 메트릭 기록 ──────────────────────────────────────────────────────

    def _record_layer1(
        self,
        task_id: str,
        question: str,
        response: str,
        ground_truth: Optional[str],
        execution_time: float,
        success: bool,
        errors: List[str],
        tokens: Dict[str, int],
        retrieved_contexts: Optional[List[str]] = None,
        override_expected_elements: Optional[List[str]] = None,
        inputs: Optional[Dict[str, Any]] = None,
    ):
        execution_time = max(0.001, execution_time)  # D3-1: zero-latency guard
        if self.verbose:
            print(f"\n📈 Layer 1: Native Metrics 기록 중...")

        # step_callback 수집 도구 호출 — 두 경로 모두 TaskResult에 설정해
        # record_task()가 tool_analyzer를 한 번만 실행하도록 한다
        # FA6: duration_estimated 플래그 — duration=0.0이면 측정 불가 추정값 (AutoGen과 동일 규약)
        _fallback_tool_calls = [
            {
                "tool_name": t[0],
                "success": t[1],
                "duration": t[2],
                "parameters": t[3] if len(t) > 3 and isinstance(t[3], dict) else {},
                "privilege_level": _resolve_privilege_level(t[0], self.monitor),
                "execution_result": t[4] if len(t) > 4 else "",
                **({"duration_estimated": True} if t[2] == 0.0 else {}),
            }
            for t in self._tool_usage
        ] if self._tool_usage else []

        if create_taskresult_from_execution and _HELPERS_AVAILABLE:
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type=self.task_type,
                question=question,
                response=response,
                ground_truth=ground_truth,
                execution_time=execution_time,
                has_error=not success,
                error_message=errors[0] if errors else None,
            )
            # 실제 측정 토큰으로 덮어쓰기
            if tokens["input"] or tokens["output"]:
                task.tokens_used = tokens
            # helper는 tool_calls=[]로 초기화 → step_callback 데이터 소급 설정
            if _fallback_tool_calls:
                task.tool_calls = _fallback_tool_calls
        else:
            # DQ-051: 공백 전용 ground_truth 필터 — DQ-017/018 패턴과 일치
            _acc = (
                calculate_accuracy_score(response, ground_truth)
                if calculate_accuracy_score and response and ground_truth
                and ground_truth.strip()
                else 0.0
            )
            task = TaskResult(
                task_id=task_id,
                task_type=self.task_type,
                success=success,
                completion_score=1.0 if success and response else 0.0,
                accuracy_score=_acc,
                execution_time=execution_time,
                tokens_used=tokens,
                tool_calls=_fallback_tool_calls,
                attempts=1,
                errors=errors,
                timestamp=datetime.now(),
            )

        # DQ-168: record_task() 전에 model 설정 → tokens_used.get("model") 경로 활성화
        _effective_model = (self._extract_model_name() or "unknown_model").lower()  # DQ-183
        task.tokens_used["model"] = _effective_model
        self.monitor.record_task(task)
        # 소급 설정 (defense-in-depth)
        if self.monitor.token_tracker.usage_log:
            self.monitor.token_tracker.usage_log[-1]["model"] = _effective_model


        # ResponseQualityEvaluator — 명시 전달 우선, 없으면 crew.tasks.expected_output 자동 추출
        if question and response:
            try:
                expected_elements = (
                    override_expected_elements
                    if override_expected_elements is not None
                    else self._extract_expected_elements(inputs=inputs)
                )
                self.monitor.quality_evaluator.evaluate_response(
                    task_id=task_id,
                    response=response,
                    request=question,
                    expected_elements=expected_elements,
                    ground_truth=ground_truth,
                )
                if self.verbose:
                    n_elem = len(expected_elements)
                    print(f"   ✅ ResponseQuality 평가 완료 (expected_elements: {n_elem})")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # HallucinationDetector — 중간 태스크 출력에서 수집한 RAG 컨텍스트
        if retrieved_contexts and response:
            try:
                # DQ-047: 대용량 RAG 결과 → 무제한 join 방지 (HallucinationDetector OOM 위험)
                # DQ-141: 공백 전용 컨텍스트 배제
                combined_context = "\n".join(c for c in retrieved_contexts if c.strip())[:50_000]
                if not combined_context.strip():
                    raise ValueError("retrieved_contexts are all whitespace")
                self.monitor.hallucination_detector.detect_hallucination(
                    task_id=task_id,
                    response=response,
                    context=combined_context,
                    ground_truth=ground_truth,
                )
                if self.verbose:
                    print(f"   ✅ HallucinationDetector: {len(retrieved_contexts)} 컨텍스트 분석")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        if self.verbose:
            print(f"   ✅ TCR: {(task.completion_score or 0.0) * 100:.1f}%  "
                  f"Latency: {execution_time:.2f}s  Tokens: {tokens}")
            if tokens.get("input", 0) > 0 or tokens.get("output", 0) > 0:
                print(f"   ℹ️ TokenEconomy: usage_metrics delta 계산 — "
                      f"in={tokens.get('input', 0)} out={tokens.get('output', 0)}")

    def _record_layer2(
        self,
        task_id: str,
        expected_tools: Optional[List[str]],
        expected_agents: Optional[List[str]],
        success: bool = True,
        execution_time: float = 0.0,
    ):
        if self.verbose:
            print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

        # Tool Selection Accuracy — expected_tools 가 명시적으로 제공된 경우에만 기록
        # expected_tools 없이 호출하면 100% 만점이 기록되어 지표가 오염됨
        actual_tools = [t for t, *_ in self._tool_usage]
        if expected_tools:
            self.monitor.tool_selection_tracker.evaluate_selection(
                task_id=task_id,
                expected_tools=expected_tools or [],
                actual_tools=actual_tools,
            )
            if self.verbose:
                print(f"   ✅ Tool Selection: expected={len(expected_tools or [])} "
                      f"actual={len(actual_tools)}")

        # Agent Coordination — task_success 기반 실제 성공 여부 반영
        for interaction in self._agent_interactions:
            from_agent, to_agent = interaction[0], interaction[1]
            interaction_success = interaction[2] if len(interaction) > 2 else True
            # DQ-108: track_agent_interaction()에서 저장한 interaction_type 사용
            # 자동 감지(3-tuple)는 "delegation", 수동 기록(4-tuple)은 사용자 지정값 사용
            i_type = interaction[3] if len(interaction) > 3 else "delegation"
            self.monitor.agent_coordination_tracker.track_interaction(
                task_id=task_id,
                from_agent=from_agent,
                to_agent=to_agent,
                interaction_type=i_type,
                success=interaction_success,
                context={
                    "framework": "crewai",
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                },
            )
        if self.verbose and self._agent_interactions:
            print(f"   ✅ Agent Coordination: {len(self._agent_interactions)} interactions")

        # Agent Selection Accuracy — expected_agents vs actually observed agents
        if expected_agents and self._agent_interactions:
            actual_agents = list(dict.fromkeys(
                agent
                for interaction in self._agent_interactions
                for agent in (interaction[0], interaction[1])
                if agent and not agent.startswith("crew_agent_")
            ))
            if not actual_agents:
                # fallback: crew_agent_ 이름도 포함
                actual_agents = list(dict.fromkeys(
                    agent
                    for interaction in self._agent_interactions
                    for agent in (interaction[0], interaction[1])
                    if agent
                ))
            try:
                self.monitor.tool_selection_tracker.evaluate_selection(
                    task_id=f"{task_id}_agent_sel",
                    expected_tools=expected_agents,
                    actual_tools=actual_agents,
                )
                if self.verbose:
                    print(f"   ✅ Agent Selection: expected={len(expected_agents)} "
                          f"actual={len(actual_agents)}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # Workflow Execution (task_callback 실시간 타이밍 또는 fallback)
        # step_name 키워드로 step_type 동적 분기: tool_call / llm_generation / task_completion
        _WORKFLOW_TOOL_KWS = frozenset({
            "search", "retrieve", "retriev", "query", "find", "fetch",
            "lookup", "browse", "scrape", "read", "load",
            "extract", "collect", "get", "obtain", "pull", "ingest",
        })
        _WORKFLOW_LLM_KWS = frozenset({
            "generate", "write", "analyze", "summarize", "create",
            "compose", "evaluate", "reason", "draft", "review",
            "plan", "coordinate", "manage", "process", "research",
            "compile", "format", "finalize", "output",
        })
        for _step in self._workflow_steps:
            step_name, step_success, duration = _step[0], _step[1], _step[2]
            _step_agent = _step[3] if len(_step) > 3 else ""
            _step_estimated = _step[4] if len(_step) > 4 else False  # M3: 균등 분배 추정값 플래그
            _name_lower = step_name.lower()
            if any(kw in _name_lower for kw in _WORKFLOW_TOOL_KWS):
                step_type = "tool_call"
            elif any(kw in _name_lower for kw in _WORKFLOW_LLM_KWS):
                step_type = "llm_generation"
            else:
                step_type = "task_completion"
            _meta: Dict[str, Any] = {}
            if _step_agent:
                _meta["agent"] = _step_agent
            if _step_estimated:
                _meta["duration_estimated"] = True  # M3: task_callback 미작동 시 균등 분배
            self.monitor.workflow_tracker.track_step(
                task_id=task_id,
                step_name=step_name,
                step_type=step_type,
                success=step_success,
                execution_time=duration,
                framework="crewai",
                metadata=_meta,
            )
        if self.verbose and self._workflow_steps:
            print(f"   ✅ Workflow Execution: {len(self._workflow_steps)} tasks tracked")


        # RetryCorrectionTracker — 항상 기록 (성공만 해도 first_attempt_success_rate 계산에 필요)
        if self._workflow_steps:
            # retry 감지: 동일 태스크명이 두 번 이상 등장하거나, 실패한 태스크가 있으면 retry 기록
            # 순차 파이프라인(모두 다른 이름, 모두 성공)은 단일 시도로 기록
            _task_names = [s[0] for s in self._workflow_steps]
            _has_duplicate = len(_task_names) != len(set(_task_names))
            _failed_steps = [s for s in self._workflow_steps if not s[1]]
            if _has_duplicate or _failed_steps:
                # 실제 retry 또는 실패 있음: 각 step을 attempt로 기록
                attempts_log = [
                    {
                        "success": _step[1],
                        "retry_reason": (
                            f"task_failed: {_step[0]}" + (f" (agent: {_step[3]})" if len(_step) > 3 and _step[3] else "")
                            if not _step[1] else ""
                        ),
                        "duration": _step[2],
                    }
                    for _step in self._workflow_steps
                ]
            else:
                # 모두 다른 이름의 순차 태스크가 성공 → 단일 시도로 기록
                attempts_log = [{"success": True, "retry_reason": "", "duration": execution_time}]
        else:
            # task_callback 미작동 + tasks_output fallback도 없는 경우 → 전체를 단일 시도로 기록
            attempts_log = [{"success": success, "retry_reason": "", "duration": execution_time}]
        try:
            self.monitor.retry_tracker.track_attempts(
                task_id=task_id,
                attempts_log=attempts_log,
                task_type=self.task_type,
            )
            failed_count = sum(1 for a in attempts_log if not a["success"])
            if self.verbose:
                if self._workflow_steps:
                    if failed_count:
                        print(f"   ✅ RetryCorrection: {failed_count} failed task(s) tracked")
                    else:
                        print(f"   ✅ RetryCorrection: {len(self._workflow_steps)} steps (no failures)")
                else:
                    print(f"   ✅ RetryCorrection: single attempt (no callback data), success={success}")
        except Exception as _e:
            if self.verbose:
                print(f"   ⚠️ {_e}")

    def _record_security(
        self,
        task_id: str,
        input_text: str,
        output_text: str,
        retrieved_contexts: Optional[List[str]] = None,
    ):
        if self.verbose:
            print(f"\n🔒 Security Metrics 기록 중...")

        sanitizer = getattr(self.monitor, "input_sanitizer", None)
        leakage_det = getattr(self.monitor, "output_leakage_detector", None)
        authorizer = getattr(self.monitor, "tool_authorizer", None)

        # D8-3: enable_security=True 인데 트래커 미초기화 시 경고
        if self.enable_security and sanitizer is None:
            import warnings as _w
            _w.warn(
                "CrewAI: enable_security=True 이지만 보안 트래커가 초기화되지 않았습니다. "
                "_ensure_security_trackers()가 호출되지 않은 것 같습니다.",
                UserWarning,
                stacklevel=3,
            )

        if sanitizer:
            try:
                # DQ-007: 4000자 초과 입력 truncation — evaluate_input 정규식 성능 보호
                _safe_input = input_text[:4000] if input_text else input_text
                result = sanitizer.evaluate_input(
                    task_id=task_id,
                    input_text=_safe_input,
                )
                if self.verbose:
                    print(f"   ✅ InputSanitization: risk={result.get('risk_level', 'low')}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        if leakage_det:
            # 최종 응답 + 중간 태스크 출력 + step_callback 도구 결과 통합 검사 (중복 제거)
            _seen_outputs: set = set()
            _extra_outputs: List[str] = []
            for c in (retrieved_contexts or []):
                if c and c not in _seen_outputs:
                    _extra_outputs.append(c)
                    _seen_outputs.add(c)
            for t in self._tool_usage:
                if len(t) > 4 and t[4] and t[4] not in _seen_outputs:
                    _extra_outputs.append(t[4])
                    _seen_outputs.add(t[4])
            _full_output = output_text
            if _extra_outputs:
                _full_output = output_text + "\n" + "\n".join(_extra_outputs)
            if _full_output:
                try:
                    result = leakage_det.detect_leakage(
                        task_id=task_id,
                        output_text=_full_output,
                    )
                    leaked = result.get("leakage_count", 0) > 0
                    if self.verbose:
                        extra = f" (+{len(_extra_outputs)} task outputs)" if _extra_outputs else ""
                        print(f"   ✅ OutputLeakage: detected={leaked}{extra}")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

        if authorizer:
            for entry in self._tool_usage:
                t_name, t_ok = entry[0], entry[1]
                t_params = entry[3] if len(entry) > 3 else {}
                try:
                    authorizer.track_tool_call(
                        task_id=task_id,
                        tool_name=t_name,
                        parameters=t_params if isinstance(t_params, dict) else {},
                    )
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

        # PrivilegeEscalationDetector
        priv_det = getattr(self.monitor, "privilege_escalation_detector", None)
        if priv_det and self._tool_usage:
            tool_calls_dicts = [
                {
                    "tool_name": entry[0],
                    "success": entry[1],
                    "duration": entry[2],
                    "parameters": entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {},
                    "privilege_level": _resolve_privilege_level(entry[0], self.monitor),
                }
                for entry in self._tool_usage
            ]
            try:
                priv_det.analyze_privilege_chain(task_id=task_id, tool_calls=tool_calls_dicts)
                if self.verbose:
                    print(f"   ✅ PrivilegeEscalation: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # ToolChainAttackDetector
        chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
        if chain_det and self._tool_usage:
            tool_names = [entry[0] for entry in self._tool_usage]
            try:
                chain_det.analyze_tool_chain(task_id=task_id, tool_sequence=tool_names)
                if self.verbose:
                    print(f"   ✅ ToolChainAttack: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

    def _reset_tracking(self):
        self._workflow_steps = []
        self._agent_interactions = []
        self._tool_usage = []
        self._last_task_checkpoint = 0.0
        self._last_agent = None
        self._last_task_success = True
        self._last_step_time = 0.0
        # 누적 토큰 스냅샷 — kickoff() 시작 전 값을 저장해 delta 계산
        _um = getattr(self.crew, "usage_metrics", None)
        def _first_not_none_val(*attrs: str) -> int:
            for a in attrs:
                v = getattr(_um, a, None)
                if v is not None:
                    return int(v)
            return 0
        if _um is not None:
            self._prev_input_tokens = _first_not_none_val("prompt_tokens", "total_prompt_tokens", "input_tokens")
            self._prev_output_tokens = _first_not_none_val("completion_tokens", "total_completion_tokens", "output_tokens")
        else:
            self._prev_input_tokens = 0
            self._prev_output_tokens = 0

    # ── 수동 추적 API ─────────────────────────────────────────────────────

    def track_workflow_step(
        self, step_name: str, success: bool = True,
        duration: float = 0.0, agent_name: str = "",
    ):
        """워크플로우 단계를 수동으로 추적합니다."""
        self._workflow_steps.append((step_name, success, duration, agent_name))

    def track_agent_interaction(
        self,
        from_agent: str,
        to_agent: str,
        interaction_type: str = "delegation",
        success: bool = True,
    ):
        """에이전트 간 상호작용을 수동으로 추적합니다.

        Args:
            from_agent: 상호작용을 시작하는 에이전트 이름
            to_agent: 상호작용을 받는 에이전트 이름
            interaction_type: 상호작용 유형 — "delegation" / "communication" / "collaboration"
                              (기본값 "delegation")
            success: 상호작용 성공 여부 (기본값 True)
        """
        # DQ-108: interaction_type을 4-tuple 4번째 원소에 저장
        # _record_layer2() 에서 interaction[3]으로 읽어 tracker에 전달됨
        self._agent_interactions.append((from_agent, to_agent, success, interaction_type))

    def track_tool_usage(
        self,
        tool_name: str,
        success: bool = True,
        duration: float = 0.0,
        parameters: Optional[Dict[str, Any]] = None,
        execution_result: str = "",
    ):
        """도구 사용을 수동으로 추적합니다."""
        self._tool_usage.append((tool_name, success, duration, parameters or {}, execution_result))

    # ── 보고서 ────────────────────────────────────────────────────────────

    def generate_report(self, output_path: Optional[str] = None) -> Any:
        """평가 보고서 생성"""
        if self.verbose:
            print(f"\n{'='*70}\n📊 평가 보고서 생성\n{'='*70}")

        report = self.monitor.generate_report()

        if self.verbose:
            print(f"\n🔹 Layer 1: Native Metrics")
            tcr = report.accuracy_metrics.get("tcr", {})
            acc = report.accuracy_metrics.get("accuracy_scores", {})
            lat = report.efficiency_metrics.get("latency", {})
            tok = report.efficiency_metrics.get("tokens", {})
            _acc_str = (
                f"{acc.get('overall_accuracy', 0):.1f}%"
                if self._tasks_with_ground_truth > 0
                else "N/A (no ground truth provided)"
            )
            print(f"   TCR: {tcr.get('tcr', 0):.1f}%")
            print(f"   Accuracy: {_acc_str}")
            print(f"   Avg Latency: {lat.get('avg', 0):.2f}s")
            print(f"   Total Tokens: {tok.get('total_tokens', 0)}")
            # DQ-197/198
            _q = self.monitor.quality_evaluator.get_quality_metrics()
            if _q:
                print(f"   Response Quality: {_q.get('avg_total_score', 0):.2f}/5.0"
                      f"  (grade: {_q.get('avg_grade', 'N/A')})")
            _h = self.monitor.hallucination_detector.get_hallucination_rate()
            if _h and "overall_rate" in _h:
                print(f"   Hallucination Rate: {_h.get('overall_rate', 0):.1f}%")

            if self.enable_layer2:
                print(f"\n🔹 Layer 2: Agentic AI Metrics")
                tool = self.monitor.tool_selection_tracker.get_accuracy_stats()
                coord = self.monitor.agent_coordination_tracker.calculate_coordination_score()
                wf = self.monitor.workflow_tracker.calculate_execution_success_rate()
                tool_eff = self.monitor.tool_analyzer.get_efficiency_stats()
                _tool_acc_str = (
                    f"{tool.get('accuracy', 0):.1f}%"
                    if tool
                    else "N/A (no expected_tools provided)"
                )
                retry = self.monitor.retry_tracker.get_retry_metrics()
                print(f"   Tool Selection Accuracy: {_tool_acc_str}")
                print(f"   Workflow Execution Score: {wf.get('success_rate', 0):.1f}%")
                if coord:
                    print(f"   Agent Coordination Rate: {coord.get('score', 0):.1f}%")
                if tool_eff:
                    print(f"   Tool Call Success Rate: {tool_eff.get('success_rate', 0):.1f}%")
                if retry:
                    print(f"   Retry Rate: {retry.get('retry_rate', 0):.1f}%  "
                          f"First-attempt Success: {retry.get('first_attempt_success_rate', 0):.1f}%")

            if self.enable_security:
                print(f"\n🔹 Security Metrics")
                sanitizer = getattr(self.monitor, "input_sanitizer", None)
                leakage_det = getattr(self.monitor, "output_leakage_detector", None)
                authorizer = getattr(self.monitor, "tool_authorizer", None)
                priv_det = getattr(self.monitor, "privilege_escalation_detector", None)
                chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
                if sanitizer:
                    sec = sanitizer.get_security_stats()
                    print(f"   Input Threat Rate: {sec.get('threat_rate', 0):.1f}%")
                if leakage_det:
                    leak = leakage_det.get_leakage_stats()
                    print(f"   Output Leakage Rate: {leak.get('leakage_rate', 0):.1f}%")
                if authorizer:
                    auth = authorizer.get_compliance_stats()
                    print(f"   Tool Compliance Rate: {auth.get('compliance_rate', 100):.1f}%")
                if priv_det:
                    priv = priv_det.get_escalation_stats()
                    print(f"   Privilege Escalation Rate: {priv.get('escalation_rate', 0):.1f}%")
                if chain_det:
                    chain = chain_det.get_attack_stats()
                    print(f"   Tool Chain Attack Rate: {chain.get('attack_rate', 0):.1f}%")

        if output_path:
            self.monitor.save_to_file(output_path)
            if self.verbose:
                print(f"\n💾 보고서 저장: {output_path}")

        return report

    def reset(self) -> None:
        """실행 이력과 내부 상태를 초기화합니다. 같은 인스턴스로 새 평가 세션을 시작할 때 사용하세요."""
        self.execution_history = []
        self._tasks_with_ground_truth = 0
        self._reset_tracking()

    def get_statistics(self) -> Dict[str, Any]:
        """현재까지 통계 반환"""
        return {
            "total_executions": len(self.execution_history),
            "successful_executions": sum(1 for h in self.execution_history if h["success"]),
            "average_duration": (
                sum(h.get("execution_time", 0.0) for h in self.execution_history) / len(self.execution_history)
                if self.execution_history else 0.0
            ),
            "layer2_enabled": self.enable_layer2,
            "security_enabled": self.enable_security,
        }


def create_evaluated_crew(
    crew: Any,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> CrewAIEvaluator:
    """CrewAI Crew를 평가 래퍼로 감싸는 편의 함수"""
    return CrewAIEvaluator(
        crew=crew,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )


def create_evaluated_crewai_agent(
    crew: Any,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> CrewAIEvaluator:
    """CrewAI Crew를 평가 래퍼로 감싸는 편의 함수.

    create_evaluated_crew() 의 네이밍 통일 별칭.
    다른 프레임워크 팩토리 함수와 동일한 패턴:
        create_evaluated_crewai_agent(crew, monitor=monitor, ...)
    """
    return create_evaluated_crew(
        crew=crew,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )
