#!/usr/bin/env python3
"""
AutoGen Integration - Full 3-Layer Metrics Support
===================================================

autogen-agentchat 0.7.x (async-first API) 기반 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics — TCR, Accuracy, Latency, Token Economy, ResponseQuality
- Layer 2: Agentic AI Metrics — Tool Selection, Agent Coordination, Workflow Execution
  - ToolCallRequestEvent/ToolCallExecutionEvent 타임스탬프 추적으로 도구 실행 시간 측정
  - is_error=True → RetryCorrectionTracker 자동 연결
- Security (opt-in): enable_security=True 로 InputSanitization / OutputLeakage / ToolAuthorization 활성화
- 단일 에이전트(on_messages) 및 팀(RoundRobinGroupChat 등) 모두 지원
- 동기 편의 메서드(run_sync) 제공

사용 방법 — 단일 에이전트:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")
    agent = AssistantAgent("assistant", model_client=model_client)

    evaluator = AutoGenEvaluator(agent, monitor, enable_layer2=True)

    # async 실행
    result = await evaluator.run("질문", ground_truth="정답")

    # 또는 sync 실행 (이벤트 루프 없는 환경)
    result = evaluator.run_sync("질문")

사용 방법 — 팀 (멀티 에이전트):
    from autogen_agentchat.teams import RoundRobinGroupChat

    team = RoundRobinGroupChat([agent1, agent2], max_turns=4)
    evaluator = AutoGenEvaluator(team, monitor, enable_layer2=True)
    result = await evaluator.run("질문")

요구 사항:
    pip install "agent-evaluator[autogen]"
    pyautogen >= 0.3.0  →  autogen-agentchat >= 0.4.0
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType

try:
    from ..helpers.taskresult_helpers import (
        create_taskresult_from_execution,
        estimate_tokens,
        calculate_accuracy_score,
    )
    _HELPERS_AVAILABLE = True
except ImportError:
    _HELPERS_AVAILABLE = False
    create_taskresult_from_execution = None
    estimate_tokens = None
    calculate_accuracy_score = None  # type: ignore[assignment]

# autogen-agentchat 0.7.x imports
try:
    from autogen_agentchat.messages import (
        TextMessage,
        ToolCallRequestEvent,
        ToolCallExecutionEvent,
    )
    from autogen_core import CancellationToken
    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False
    TextMessage = None
    ToolCallRequestEvent = None
    ToolCallExecutionEvent = None
    CancellationToken = None


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
    2순위: _infer_privilege_level() 휴리스틱 (키워드 기반)
    """
    registry: Dict[str, str] = getattr(monitor, "privilege_registry", {}) or {}
    if tool_name in registry:
        return registry[tool_name]
    return _infer_privilege_level(tool_name)


def _infer_privilege_level(tool_name: str) -> str:
    """도구 이름 기반 권한 수준 추론 (PrivilegeEscalationDetector용 fallback)"""
    _tn = (tool_name or "").lower()
    if any(k in _tn for k in ("delete", "drop", "remove", "exec", "system", "admin", "root", "sudo", "kill", "purge", "destroy", "truncate", "revoke", "chmod", "export")):
        return "admin"
    if any(k in _tn for k in ("write", "update", "create", "modify", "insert", "post", "put", "patch", "upload", "save", "backup", "sync", "push", "migrate")):
        return "write"
    return "read"


class AutoGenEvaluator:
    """
    autogen-agentchat 0.7.x 에이전트/팀 평가 클래스 (async-first, Layer 1/2 지원)

    단일 AssistantAgent 또는 팀(GroupChat)을 모두 지원합니다.
    - 단일 에이전트: on_messages() 호출
    - 팀: team.run() 호출
    """

    def __init__(
        self,
        agent_or_team: Any,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_security: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True,
        privilege_registry: Optional[Dict[str, str]] = None,
        authorized_tools: Optional[List[str]] = None,
    ):
        """
        AutoGenEvaluator 초기화

        Args:
            agent_or_team: AssistantAgent 또는 GroupChat 팀 객체
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_security: 보안 지표 활성화 (opt-in, 성능 영향)
            task_type: TaskResult 타입
            verbose: 상세 출력
        """
        if not AUTOGEN_AVAILABLE:
            raise ImportError(
                "autogen-agentchat is not installed. "
                "Install with: pip install 'agent-evaluator[autogen]'"
            )

        self.agent_or_team = agent_or_team
        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_security = enable_security
        self.task_type = task_type
        self.verbose = verbose
        self.authorized_tools: List[str] = list(authorized_tools or [])
        if self.authorized_tools:
            self.monitor._authorized_tools = self.authorized_tools

        # 단일 에이전트 vs 팀 판별
        # 팀 클래스는 run() 메서드를 가지며 에이전트 목록(agents)이 있음
        # 팀 판별: on_messages가 없으면 팀(GroupChat/RoundRobin 등), 있으면 단일 에이전트
        # _participants 체크는 API 변경에 취약하므로 on_messages 부재를 1차 기준으로 사용
        self._is_team = (
            hasattr(agent_or_team, "run")
            and not hasattr(agent_or_team, "on_messages")
        )

        self.execution_history: List[Dict[str, Any]] = []
        self._tasks_with_ground_truth: int = 0  # ground_truth 제공 횟수 추적 (Accuracy N/A 판단용)

        if enable_security:
            _ensure_security_trackers(self.monitor, privilege_registry=privilege_registry)
        elif privilege_registry:
            self.monitor.privilege_registry = privilege_registry

        if self.verbose:
            mode = "team" if self._is_team else "single agent"
            print(f"✅ AutoGenEvaluator 초기화 완료 "
                  f"({mode}, Layer2: {enable_layer2}, Security: {enable_security})")

    # ── 실행 (async) ─────────────────────────────────────────────────────

    async def run(
        self,
        task: str,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # FA7: EvaluatorProtocol 통일 인터페이스
        task_id: Optional[str] = None,
        cancellation_token: Optional[Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        에이전트/팀을 실행하고 평가 메트릭을 수집합니다.

        Args:
            task: 질문 또는 지시문
            ground_truth: 정답 텍스트 (Accuracy 계산용)
            expected_tools: 기대 도구 목록 (Layer 2 Tool Selection)
            expected_elements: ResponseQuality completeness 평가용 기대 요소 목록
            expected_agents: 기대 에이전트 목록 (AgentCoordinationTracker 검증용)
            cancellation_token: CancellationToken (선택)

        Returns:
            {"response": str, "messages": list, "task_id": str}
        """
        task_id = task_id or f"autogen_{int(time.time() * 1000)}"
        start_time = time.time()
        errors: List[str] = []
        messages: List[Any] = []

        # 누적 토큰 스냅샷 — run() 시작 전 값을 저장해 delta 계산
        _prev_tokens = self._snapshot_model_usage()

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 AutoGen 실행 시작 (Task ID: {task_id})")
            print(f"{'='*70}")

        try:
            if self._is_team:
                messages = await self._run_team(task, cancellation_token)
            else:
                messages = await self._run_single(task, cancellation_token)

            if self.verbose:
                print(f"\n✅ AutoGen 실행 완료")
        except Exception as e:
            errors.append(str(e))
            if self.verbose:
                print(f"\n❌ AutoGen 실행 실패: {e}")

        execution_time = time.time() - start_time
        success = len(errors) == 0

        # 메시지에서 메트릭 추출
        response_text = self._extract_response(messages)
        tokens = self._extract_tokens(messages, task, response_text, prev_tokens=_prev_tokens)
        tool_calls = self._extract_tool_calls(messages, execution_time=execution_time)
        retrieved_contexts = self._extract_retrieved_contexts(messages, tool_calls)

        # expected_elements: 명시 전달 우선, 없으면 task에서 자동 추출
        _expected = expected_elements if expected_elements is not None else self._extract_expected_elements(task)

        self._record_layer1(
            task_id=task_id,
            question=task,
            response=response_text,
            ground_truth=ground_truth,
            execution_time=execution_time,
            success=success,
            errors=errors,
            tokens=tokens,
            tool_calls=tool_calls,
            retrieved_contexts=retrieved_contexts,
            expected_elements=_expected,
        )

        if self.enable_layer2:
            self._record_layer2(
                task_id=task_id,
                messages=messages,
                tool_calls=tool_calls,
                expected_tools=expected_tools,
                execution_time=execution_time,
                errors=errors,
                expected_agents=expected_agents,  # I-C-002: 에이전트 선택 정확도 평가
            )

        if self.enable_security:
            self._record_security(task_id, task, response_text, tool_calls, messages)

        # DQ-002: 빈 문자열 ground_truth는 유의미한 accuracy 측정 불가
        if ground_truth is not None and ground_truth.strip():
            self._tasks_with_ground_truth += 1
        # FA3: 표준 실행 히스토리 스키마 (UI-023: input/output 키 통일)
        self.execution_history.append({
            "task_id": task_id,
            "timestamp": datetime.now(),
            "success": success,
            "execution_time": execution_time,
            "framework": "autogen",
            "input": task,
            "output": response_text,
        })

        if self.verbose:
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}s)")

        return {
            "response": response_text,
            "messages": messages,
            "task_id": task_id,
        }

    async def _run_single(self, task: str, cancellation_token: Optional[Any]) -> List[Any]:
        """단일 AssistantAgent 실행 (on_messages 사용)"""
        ct = cancellation_token or CancellationToken()
        response = await self.agent_or_team.on_messages(
            [TextMessage(content=task, source="user")],
            cancellation_token=ct,
        )
        # Response.inner_messages: 중간 메시지 (tool calls 등)
        # Response.chat_message: 최종 응답
        inner = getattr(response, "inner_messages", []) or []
        final = getattr(response, "chat_message", None)
        return inner + ([final] if final else [])

    async def _run_team(self, task: str, cancellation_token: Optional[Any]) -> List[Any]:
        """팀(GroupChat 등) 실행 (run 사용)"""
        ct = cancellation_token or CancellationToken()
        result = await self.agent_or_team.run(
            task=task,
            cancellation_token=ct,
        )
        # TaskResult.messages 에 전체 대화 기록
        return getattr(result, "messages", []) or []

    # ── 동기 래퍼 ─────────────────────────────────────────────────────────

    def run_sync(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # Protocol 통일 (AutoGen에서는 미사용)
        **kwargs,
    ) -> Any:
        """동기 실행 편의 메서드 — EvaluatorProtocol.run_sync() 인터페이스 충족.

        ``user_input`` 은 문자열 또는 dict 모두 허용합니다.
        dict인 경우 ``to_task_string()`` 으로 문자열 추출 후 전달합니다.

        ``expected_agents`` 는 CrewAI 전용 파라미터입니다. AutoGen에서는 무시됩니다.
        에이전트 조율 추적은 실행 중 메시지 소스 전환으로 자동 감지됩니다.

        이미 실행 중인 이벤트 루프가 없는 환경(스크립트, Jupyter 셀 외부)에서 사용합니다.
        Jupyter 등 이미 루프가 있는 환경에서는 ``await evaluator.run()`` 을 직접 사용하세요.

        예외 처리: 실행 중 예외가 발생해도 수집된 메트릭은 monitor에 기록되며,
        예외는 억제되고 오류 정보가 담긴 dict를 반환합니다.
        """
        from .framework_integrations import to_task_string
        task = to_task_string(user_input)
        cancellation_token = kwargs.pop("cancellation_token", None)
        coro = self.run(
            task, ground_truth, expected_tools, expected_elements,
            expected_agents=expected_agents,
            cancellation_token=cancellation_token,
            **kwargs,
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Jupyter 등 이미 이벤트 루프가 있는 경우
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ── 추출 헬퍼 ────────────────────────────────────────────────────────

    def _extract_response(self, messages: List[Any]) -> str:
        """메시지 목록에서 최종 에이전트 응답 텍스트 추출"""
        if not messages:
            return ""
        # 마지막 TextMessage 를 응답으로 사용
        for msg in reversed(messages):
            if TextMessage and isinstance(msg, TextMessage):
                return str(msg.content)
            # dict 형태 메시지 fallback
            if isinstance(msg, dict):
                return str(msg.get("content", ""))
        return str(getattr(messages[-1], "content", ""))

    def _extract_model_name(self) -> str:
        """model_client 설정에서 모델명 추출 (TokenEconomy 비용 계산용)"""
        model_client = (
            getattr(self.agent_or_team, "model_client", None)
            or getattr(self.agent_or_team, "_model_client", None)
        )
        if model_client:
            for attr in ("model", "model_id", "_model", "model_name"):
                val = getattr(model_client, attr, None)
                if val and isinstance(val, str):
                    return val
            # 팀(GroupChat)인 경우 첫 번째 에이전트의 model_client 확인
            participants = getattr(self.agent_or_team, "_participants", None) or []
            for participant in participants:
                mc = getattr(participant, "model_client", None)
                if mc:
                    for attr in ("model", "model_id", "_model", "model_name"):
                        val = getattr(mc, attr, None)
                        if val and isinstance(val, str):
                            return val
        return ""

    def _snapshot_model_usage(self) -> Dict[str, int]:
        """현재 model_client 누적 토큰 수를 스냅샷으로 반환 (delta 계산용)"""
        model_client = (
            getattr(self.agent_or_team, "model_client", None)
            or getattr(self.agent_or_team, "_model_client", None)
        )
        if model_client:
            for method_name in ("total_usage", "actual_usage"):
                fn = getattr(model_client, method_name, None)
                if callable(fn):
                    try:
                        usage = fn()
                        return {
                            "input": getattr(usage, "prompt_tokens", 0) or 0,
                            "output": getattr(usage, "completion_tokens", 0) or 0,
                        }
                    except Exception:
                        pass
        return {"input": 0, "output": 0}

    def _extract_tokens(
        self, messages: List[Any], input_text: str, output_text: str,
        prev_tokens: Optional[Dict[str, int]] = None,
    ) -> Dict[str, int]:
        """
        토큰 추출 전략:
        1. 모델 클라이언트의 total_usage() - prev_tokens delta (누적값 보정)
        2. 없으면 텍스트 길이 기반 추정 (tiktoken 또는 휴리스틱)
        """
        # 전략 1: model_client.total_usage() — delta 계산으로 누적 오차 제거
        current = self._snapshot_model_usage()
        if current["input"] or current["output"]:
            prev = prev_tokens or {"input": 0, "output": 0}
            delta_in  = max(0, current["input"]  - prev.get("input",  0))
            delta_out = max(0, current["output"] - prev.get("output", 0))
            if delta_in or delta_out:
                return {"input": delta_in, "output": delta_out}

        # 전략 2: 텍스트 기반 추정 (한국어 인식 — 한글 비율 30%+ 시 char÷2 적용)
        def _korean_aware_est(text: str) -> int:
            if not text:
                return 1
            if estimate_tokens:
                return estimate_tokens(text)
            korean_ratio = sum(1 for c in text if "\uac00" <= c <= "\ud7a3") / max(len(text), 1)
            divisor = 2 if korean_ratio > 0.3 else 4
            return max(1, len(text) // divisor)

        return {
            "input": _korean_aware_est(input_text),
            "output": _korean_aware_est(output_text),
        }

    # 검색/조회 도구 키워드
    _RETRIEVAL_TOOL_KEYWORDS: frozenset = frozenset({
        "retrieve", "retriev", "search", "query", "rag",
        "fetch", "lookup", "document", "vector", "get_doc",
    })

    def _extract_expected_elements(self, task: str) -> List[str]:
        """
        task 문자열에서 기대 출력 요소를 휴리스틱으로 추출합니다.

        패턴 1: "include/mention/describe/explain X" 영문 키워드
        패턴 2: "포함/언급/설명/제공 X" 한국어 키워드
        Fallback: task가 짧고 콤마/세미콜론으로 구분된 경우 항목 분리

        Returns:
            최대 5개의 기대 요소 문자열 목록 (없으면 빈 리스트)
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

        en_patterns = [
            r'(?:include|mention|describe|explain|provide|list|cover|address|discuss|analyze|evaluate|review|assess|check)\s+([^,\.\n]{3,100})',
            r'(?:the\s+)?(?:importance|significance|details|aspects|reasons|benefits|drawbacks|pros|cons)\s+of\s+([^,\.\n]{3,80})',
        ]
        for pattern in en_patterns:
            for m in re.finditer(pattern, task, re.IGNORECASE):
                _add(m.group(1))
                if len(elements) >= 5:
                    return elements

        ko_patterns = [
            r'(?:포함|언급|설명|제공|나열|기술|작성|다루|분석|검토|평가|살펴|알아|논의|기재)(?:해|하|하여|하고|할|하는|되어야|되어|줘|주세요|바랍니다)\s*([^,\.\n]{2,80})',
            r'([^,\.\n]{2,40})(?:의|에\s*대한|에\s*관한)\s+(?:장단점|중요성|의의|상세|이유|효과|문제점|영향)',
            r'다음(?:과|을|의)\s+(?:같은|같이)?\s*([^,\.\n]{2,60})',
        ]
        for pattern in ko_patterns:
            for m in re.finditer(pattern, task, re.IGNORECASE):
                _add(m.group(1))
                if len(elements) >= 5:
                    return elements

        # Fallback: 콤마 구분 짧은 task (ex: "A, B, C를 분석해줘")
        if not elements and len(task) <= 300:
            parts = [p.strip() for p in re.split(r'[,;]', task) if p.strip()]
            if 1 < len(parts) <= 6:
                for p in parts:
                    _add(p)
                    if len(elements) >= 5:
                        break

        return elements[:5]

    def _extract_retrieved_contexts(
        self, messages: List[Any], tool_calls: List[Dict[str, Any]]
    ) -> List[str]:
        """
        ToolCallExecutionEvent 결과에서 RAG 컨텍스트를 추출합니다.
        검색/조회 도구의 실행 결과를 HallucinationDetector 컨텍스트로 활용합니다.
        """
        if not ToolCallExecutionEvent:
            return []

        # 검색 도구 call_id 수집 (키워드 기반)
        retrieval_ids: set = set()
        for tc in tool_calls:
            tool_name = tc.get("tool_name", "").lower()
            if any(kw in tool_name for kw in self._RETRIEVAL_TOOL_KEYWORDS):
                cid = tc.get("call_id")
                if cid:
                    retrieval_ids.add(cid)

        contexts: List[str] = []
        for msg in messages:
            if not isinstance(msg, ToolCallExecutionEvent):
                continue
            for result in getattr(msg, "content", []):
                if getattr(result, "is_error", False):
                    continue
                call_id = getattr(result, "call_id", None)
                content = str(getattr(result, "content", "") or "")
                if not content or len(content) <= 20:
                    continue
                # 키워드 매칭된 도구 결과 우선 수집
                if call_id in retrieval_ids:
                    contexts.append(content)

        # H2: 도구명 키워드 미매칭 시 → 결과 내용 기반 2차 탐지
        # "document", "source", "reference" 등 검색 컨텍스트 특징 키워드가 결과에 있으면 포함
        _CONTEXT_CONTENT_KWS = frozenset({
            "document", "source", "reference", "context", "article", "passage",
            "excerpt", "retrieved", "paragraph", "content", "result", "record",
            "문서", "출처", "참고", "내용", "검색결과", "단락", "문단",
        })

        def _looks_like_retrieval(text: str) -> bool:
            tl = text.lower()
            return any(kw in tl for kw in _CONTEXT_CONTENT_KWS)

        if not contexts and tool_calls:
            for msg in messages:
                if not isinstance(msg, ToolCallExecutionEvent):
                    continue
                for result in getattr(msg, "content", []):
                    if getattr(result, "is_error", False):
                        continue
                    content = str(getattr(result, "content", "") or "")
                    # 길이 기준 100자로 상향 (짧은 오류/상태 메시지 배제) + 내용 키워드 우선
                    if content and len(content) > 100 and _looks_like_retrieval(content):
                        contexts.append(content)
            # 내용 키워드도 미매칭 → 길이만으로 최후 fallback (50자 이상)
            if not contexts:
                for msg in messages:
                    if not isinstance(msg, ToolCallExecutionEvent):
                        continue
                    for result in getattr(msg, "content", []):
                        if getattr(result, "is_error", False):
                            continue
                        content = str(getattr(result, "content", "") or "")
                        if content and len(content) > 50:
                            contexts.append(content)

        return contexts

    def _extract_tool_calls(
        self, messages: List[Any], execution_time: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        ToolCallRequestEvent / ToolCallExecutionEvent 에서 도구 호출 추출.
        두 이벤트 간 타임스탬프를 활용해 도구 실행 시간을 측정합니다.
        _created_at 없을 때: 메시지 시퀀스 인덱스 기반 상대 타이밍 사용.
        """
        tool_calls: List[Dict[str, Any]] = []
        # call_id → (index, request_time) 매핑
        pending: Dict[str, tuple] = {}

        # _created_at 존재 여부 확인 — 없으면 시퀀스 인덱스(float)로 대체
        _has_real_ts = any(getattr(m, "_created_at", None) is not None for m in messages)

        for i, msg in enumerate(messages):
            if _has_real_ts:
                msg_time = getattr(msg, "_created_at", None) or 0.0
            else:
                # DQ-013: 인덱스 기반 fake 타이밍(float(i))은 의미 없는 값(1.0, 2.0 초)을 생성함
                # 0.0으로 유지 → 라인 691-705 의 균등 분배 fallback이 올바르게 처리
                msg_time = 0.0

            # ToolCallRequestEvent: 도구 호출 요청
            if ToolCallRequestEvent and isinstance(msg, ToolCallRequestEvent):
                for call in getattr(msg, "content", []):
                    call_id = getattr(call, "id", None) or str(len(tool_calls))
                    tool_name = getattr(call, "name", "unknown_tool")
                    idx = len(tool_calls)
                    tool_calls.append({
                        "tool_name": tool_name,
                        "call_id": call_id,
                        # DQ-045: arguments=None인 경우 {} 로 정규화 — track_tool_call(parameters=None) 방지
                        "parameters": getattr(call, "arguments", None) or {},
                        "success": True,
                        "duration": 0.0,
                        "privilege_level": _resolve_privilege_level(tool_name, self.monitor),
                    })
                    pending[call_id] = (idx, msg_time)

            # ToolCallExecutionEvent: 실행 결과 (성공/실패 + 타이밍 업데이트)
            elif ToolCallExecutionEvent and isinstance(msg, ToolCallExecutionEvent):
                for result in getattr(msg, "content", []):
                    call_id = getattr(result, "call_id", None)
                    is_error = getattr(result, "is_error", False)

                    result_content = getattr(result, "content", None)
                    # DQ-029: result_content 가 FunctionExecutionResult 리스트이면
                    # str(list) → repr 문자열이 아닌 실제 content 텍스트 추출
                    if isinstance(result_content, str):
                        exec_result = result_content[:2000]
                    elif isinstance(result_content, list):
                        # AutoGen FunctionExecutionResult 리스트 → 각 항목 .content 추출
                        _parts = []
                        for _r in result_content:
                            _c = getattr(_r, "content", None)
                            if isinstance(_c, str) and _c:
                                _parts.append(_c)
                        exec_result = ("\n".join(_parts))[:2000]
                    elif result_content is not None:
                        exec_result = str(result_content)[:2000]
                    else:
                        exec_result = ""

                    if call_id and call_id in pending:
                        idx, req_time = pending.pop(call_id)
                        elapsed = msg_time - req_time if msg_time > req_time else 0.0
                        tool_calls[idx]["success"] = not is_error
                        tool_calls[idx]["duration"] = elapsed
                        # H1: 실제 타임스탬프 없으면 추정값 마킹
                        if not _has_real_ts:
                            tool_calls[idx]["duration_estimated"] = True
                        if exec_result:
                            tool_calls[idx]["execution_result"] = exec_result
                    elif call_id is None:
                        # call_id 없는 이벤트만 FIFO fallback 허용
                        # call_id가 있지만 pending에 없으면 stale/중복 이벤트 → 스킵
                        for tc in tool_calls:
                            if not tc.get("_exec_matched", False):
                                tc["success"] = not is_error
                                tc["_exec_matched"] = True
                                if exec_result:
                                    tc["execution_result"] = exec_result
                                break

        # 임시 매핑 플래그 제거
        for tc in tool_calls:
            tc.pop("_exec_matched", None)

        # _created_at 없어 duration=0.0인 경우: execution_time을 도구 수로 균등 분배 (추정값)
        if not _has_real_ts and tool_calls and execution_time > 0:
            zero_dur = [tc for tc in tool_calls if tc["duration"] == 0.0]
            if zero_dur:
                import warnings
                time_per_call = execution_time / len(zero_dur)
                warnings.warn(
                    f"AutoGen: tool _created_at timestamps unavailable — "
                    f"distributing {execution_time:.2f}s equally across {len(tool_calls)} tool calls "
                    f"({time_per_call:.3f}s each). Actual per-tool durations may differ.",
                    UserWarning,
                    stacklevel=4,
                )
                for tc in zero_dur:
                    tc["duration"] = time_per_call
                    tc["duration_estimated"] = True  # 추정값 마킹

        return tool_calls

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
        tool_calls: List[Dict[str, Any]],
        retrieved_contexts: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
    ):
        execution_time = max(0.001, execution_time)  # D3-1: zero-latency guard
        if self.verbose:
            print(f"\n📈 Layer 1: Native Metrics 기록 중...")

        if create_taskresult_from_execution and _HELPERS_AVAILABLE:
            task = create_taskresult_from_execution(
                task_id=task_id,
                task_type=self.task_type,
                question=question,
                response=response,
                # None → "" 명시적 변환: `or ""` 사용 시 ground_truth="" 도 동일하게 처리되어
                # 하위 `if ground_truth and response:` 검사에서 의도치 않게 스킵될 수 있음
                ground_truth=ground_truth if ground_truth is not None else "",
                execution_time=execution_time,
                has_error=not success,
                error_message=errors[0] if errors else None,
            )
            if tokens.get("input", 0) > 0 or tokens.get("output", 0) > 0:
                task.tokens_used = tokens
            if tool_calls:
                task.tool_calls = tool_calls
        else:
            # DQ-138: 공백 전용 ground_truth(" ") 는 truthy지만 의미 없음 — strip() 추가
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
                completion_score=1.0 if (success and bool(response)) else 0.0,
                accuracy_score=_acc,
                execution_time=execution_time,
                tokens_used=tokens,
                tool_calls=tool_calls,
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


        # ResponseQualityEvaluator
        if question and response:
            try:
                # expected_elements 미제공 시 question에서 자동 추출 (LangChain/LangGraph/CrewAI와 동일)
                _expected = expected_elements if expected_elements else (
                    self._extract_expected_elements(question) if question else []
                )
                self.monitor.quality_evaluator.evaluate_response(
                    task_id=task_id,
                    response=response,
                    request=question,
                    expected_elements=_expected,
                    ground_truth=ground_truth,
                )
                if self.verbose:
                    suffix = f" (expected_elements: {len(_expected)})" if _expected else ""
                    print(f"   ✅ ResponseQuality 평가 완료{suffix}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # HallucinationDetector — 도구 실행 결과에서 수집한 RAG 컨텍스트
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
            # M5: AutoGen model_client.total_usage()는 에이전트 수명 누적값이므로 태스크별 분해 불가
            if tokens.get("input", 0) > 0 or tokens.get("output", 0) > 0:
                print(f"   ℹ️ TokenEconomy: model_client 누적값 사용 — "
                      f"태스크별 토큰 분해 불가 (per-task breakdown unavailable)")

    def _record_layer2(
        self,
        task_id: str,
        messages: List[Any],
        tool_calls: List[Dict[str, Any]],
        expected_tools: Optional[List[str]],
        execution_time: float = 0.0,
        errors: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
    ):
        if self.verbose:
            print(f"\n🤖 Layer 2: Agentic AI Metrics 기록 중...")

        # Tool Selection Accuracy — expected_tools 가 명시적으로 제공된 경우에만 기록
        # expected_tools 없이 호출하면 100% 만점이 기록되어 지표가 오염됨
        actual_tools = [tc["tool_name"] for tc in tool_calls]
        if expected_tools:
            try:
                self.monitor.tool_selection_tracker.evaluate_selection(
                    task_id=task_id,
                    expected_tools=expected_tools or [],
                    actual_tools=actual_tools,
                )
                if self.verbose:
                    if expected_tools:
                        print(f"   ✅ Tool Selection: expected={len(expected_tools)} "
                              f"actual={len(actual_tools)}")
                    else:
                        print(f"   ✅ Tool Selection: actual={len(actual_tools)} (no expected)")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # I-C-002: Agent Selection Accuracy — expected_agents vs 실제 발화 에이전트 소스
        # LangGraph·CrewAI와 동일 패턴: tool_selection_tracker.evaluate_selection()
        # AutoGen에서 "에이전트" = 메시지 source 속성 (user/human 계열 제외)
        if expected_agents:
            _NON_AG = frozenset({"user", "human", "human_input", "user_proxy", "human_proxy"})
            actual_agents = list(dict.fromkeys(
                src for msg in messages
                if (src := getattr(msg, "source", None))
                and src.lower() not in _NON_AG
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
                    print(f"   ⚠️ Agent Selection: {_e}")

        # Agent Coordination + Workflow Execution — 단일 메시지 패스
        # Pre-pass: ToolCallExecutionEvent 실패 에이전트 수집 (AgentCoord success 판단용)
        failed_sources: set = set()
        for msg in messages:
            if ToolCallExecutionEvent and isinstance(msg, ToolCallExecutionEvent):
                if any(getattr(r, "is_error", False) for r in getattr(msg, "content", [])):
                    src = getattr(msg, "source", None)
                    if src:
                        failed_sources.add(src)

        # M2: "user", "human" 등 사람 발화 소스는 에이전트 협업 추적에서 제외
        # 에이전트-에이전트 전환만 의미 있는 coordination 신호임
        _NON_AGENT_SOURCES = frozenset({"user", "human", "human_input", "user_proxy", "human_proxy"})

        prev_source: Optional[str] = None
        for i, msg in enumerate(messages):
            # source 속성이 없는 비표준 메시지는 None 처리 — 합성 에이전트명 생성 방지
            source = getattr(msg, "source", None)

            # AgentCoord — 에이전트-에이전트 전환만 기록 (user/human 소스 제외)
            # team 모드: agent_name A → agent_name B 전환
            # single 모드: agent↔user 전환은 workflow에서 추적, agent↔agent 전환만 여기서
            _from_is_agent = prev_source and prev_source.lower() not in _NON_AGENT_SOURCES
            _to_is_agent = source and source.lower() not in _NON_AGENT_SOURCES
            if source and prev_source and source != prev_source and _from_is_agent and _to_is_agent:
                interaction_success = source not in failed_sources
                try:
                    self.monitor.agent_coordination_tracker.track_interaction(
                        task_id=task_id,
                        from_agent=prev_source,
                        to_agent=source,
                        interaction_type="delegation",
                        success=interaction_success,
                        context={
                            "framework": "autogen",
                            "mode": "team" if self._is_team else "single",
                        },
                    )
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")
            if source:
                prev_source = source

            # Workflow Execution — 메시지 턴별 스텝 추적 (step_type 세분화)
            if ToolCallRequestEvent and isinstance(msg, ToolCallRequestEvent):
                step_type = "tool_call"
            elif ToolCallExecutionEvent and isinstance(msg, ToolCallExecutionEvent):
                step_type = "tool_call"  # 요청+실행 모두 tool_call
            else:
                step_type = "llm_generation"  # TextMessage 등

            # 실행 시간: 인접 메시지 _created_at 타임스탬프 차이
            msg_time = getattr(msg, "_created_at", None)
            prev_time = getattr(messages[i - 1], "_created_at", None) if i > 0 else None
            step_duration = (
                float(msg_time - prev_time)
                if (msg_time is not None and prev_time is not None and msg_time > prev_time)
                else 0.0
            )

            # 성공 여부: ToolCallExecutionEvent 는 is_error, 나머지는 기본 True
            step_success = True
            if ToolCallExecutionEvent and isinstance(msg, ToolCallExecutionEvent):
                step_success = not any(
                    getattr(r, "is_error", False)
                    for r in getattr(msg, "content", [])
                )

            # step_name: source 기반 재사용 가능한 이름 (집계 가능하도록 turn 번호 제외)
            _step_name = f"{source}_{step_type}" if source else step_type
            self.monitor.workflow_tracker.track_step(
                task_id=task_id,
                step_name=_step_name,
                step_type=step_type,
                success=step_success,
                execution_time=step_duration,
                framework="autogen",
                metadata={"agent": source, "turn": i + 1} if source else {"turn": i + 1},
            )

        if self.verbose:
            _mode = "team" if self._is_team else "single"
            print(f"   ✅ Agent Coordination ({_mode}): {len(messages)} messages processed")
            print(f"   ✅ Workflow Execution: {len(messages)} turns tracked")


        # RetryCorrectionTracker — 동일 tool 실패 후 재호출만 retry로 인정
        # 개별 tool 실패를 각각 attempt로 기록하면 retry 아닌 일반 실패도 과다 계산됨
        # 접근: 동일 tool_name이 실패 후 다시 호출된 경우 → retry; 나머지 → 단일 시도
        if tool_calls:
            _tool_first_failed: Dict[str, bool] = {}  # tool_name → first call failed?
            _has_retry = False
            for tc in tool_calls:
                tname = tc["tool_name"]
                _first = _tool_first_failed.get(tname)
                if _first is None:
                    _tool_first_failed[tname] = not tc.get("success", True)
                elif _first:
                    _has_retry = True  # 실패 후 동일 tool 재호출 감지

            if _has_retry:
                # retry 있음: tool 호출 단위로 attempt 기록
                attempts_log = []
                _tool_seen: Dict[str, bool] = {}
                for tc in tool_calls:
                    tname = tc["tool_name"]
                    if tname not in _tool_seen:
                        _tool_seen[tname] = tc.get("success", True)
                        attempts_log.append({
                            "success": tc.get("success", True),
                            "retry_reason": f"tool_error:{tname}" if not tc.get("success", True) else "",
                            "duration": tc.get("duration", 0.0),
                        })
                    else:
                        # 재호출 시도
                        attempts_log.append({
                            "success": tc.get("success", True),
                            "retry_reason": "",
                            "duration": tc.get("duration", 0.0),
                        })
            else:
                # retry 없음: 전체를 단일 시도로 기록
                overall_success = all(tc.get("success", True) for tc in tool_calls) and not (errors or [])
                attempts_log = [{"success": overall_success, "retry_reason": "", "duration": execution_time}]
        else:
            # 도구 호출 없음 — 단일 성공/실패 시도로 기록
            _has_tool_error = any(
                ToolCallExecutionEvent
                and isinstance(m, ToolCallExecutionEvent)
                and any(getattr(r, "is_error", False) for r in getattr(m, "content", []))
                for m in messages
            ) if messages else False
            _success = not _has_tool_error and len(errors) == 0
            attempts_log = [{"success": _success, "retry_reason": "", "duration": execution_time}]
        # H3: LLM 레벨 재시도 탐지 — 도구 retry 외에 동일 에이전트 연속 TextMessage를 proxy로 활용
        # autogen-agentchat 0.7.x 내부 LLM retry는 messages 스트림에 직접 노출되지 않으므로
        # 동일 소스 에이전트의 연속 TextMessage(도구 이벤트 없이) = 잠재적 재생성 시도로 간주
        _llm_retry_count = 0
        _prev_llm_source: Optional[str] = None
        _NON_AGENT = frozenset({"user", "human", "human_input", "user_proxy"})
        for _msg in messages:
            _is_tool_ev = (
                (ToolCallRequestEvent and isinstance(_msg, ToolCallRequestEvent))
                or (ToolCallExecutionEvent and isinstance(_msg, ToolCallExecutionEvent))
            )
            if _is_tool_ev:
                _prev_llm_source = None  # 도구 이벤트 사이에서 LLM 소스 리셋
                continue
            _src = getattr(_msg, "source", None)
            if _src and _src.lower() not in _NON_AGENT:
                if _src == _prev_llm_source:
                    _llm_retry_count += 1  # 동일 에이전트 연속 TextMessage = 잠재적 재생성
                else:
                    _prev_llm_source = _src

        if _llm_retry_count > 0 and not _has_retry:
            # 도구 retry는 없지만 LLM 재생성 신호 존재 → attempts_log 보완
            _llm_attempts = [
                {"success": False, "retry_reason": "llm_generation_retry", "duration": 0.0}
                for _ in range(_llm_retry_count)
            ]
            _llm_attempts.append({"success": not bool(errors), "retry_reason": "", "duration": execution_time})
            attempts_log = _llm_attempts

        failed_tools = [tc for tc in tool_calls if not tc.get("success", True)]
        try:
            self.monitor.retry_tracker.track_attempts(
                task_id=task_id,
                attempts_log=attempts_log,
            )
            if self.verbose:
                if failed_tools:
                    print(f"   ✅ RetryCorrection: {len(failed_tools)} failed tool calls tracked")
                elif _llm_retry_count > 0:
                    print(f"   ✅ RetryCorrection: {_llm_retry_count} potential LLM regeneration(s) detected")
                else:
                    print(f"   ✅ RetryCorrection: first attempt success")
        except Exception as _e:
            if self.verbose:
                print(f"   ⚠️ {_e}")

    def _record_security(
        self,
        task_id: str,
        input_text: str,
        output_text: str,
        tool_calls: List[Dict[str, Any]],
        messages: Optional[List[Any]] = None,
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
                "AutoGen: enable_security=True 이지만 보안 트래커가 초기화되지 않았습니다. "
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

        # OutputLeakage: LLM 응답 + 도구 실행 결과 모두 검사
        # 이미 파싱된 tool_calls["execution_result"] 우선 사용 → messages 재순회 불필요
        if leakage_det:
            _tool_outputs: List[str] = []
            # 1순위: _extract_tool_calls에서 저장한 execution_result 활용
            for tc in tool_calls:
                _res = str(tc.get("execution_result", "") or "")
                if _res:
                    _tool_outputs.append(_res)
            # 2순위 fallback: tool_calls 비어있으면 messages에서 직접 추출
            if not _tool_outputs and messages:
                for msg in messages:
                    if ToolCallExecutionEvent and isinstance(msg, ToolCallExecutionEvent):
                        for r in getattr(msg, "content", []):
                            _content = str(getattr(r, "content", "") or "")
                            if _content:
                                _tool_outputs.append(_content)
            _full_output = output_text
            if _tool_outputs:
                _full_output = output_text + "\n" + "\n".join(_tool_outputs)
            if _full_output:
                try:
                    result = leakage_det.detect_leakage(
                        task_id=task_id,
                        output_text=_full_output,
                    )
                    leaked = result.get("leakage_count", 0) > 0
                    if self.verbose:
                        extra = f" (+{len(_tool_outputs)} tool outputs)" if _tool_outputs else ""
                        print(f"   ✅ OutputLeakage: detected={leaked}{extra}")
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

        if authorizer:
            for tc in tool_calls:
                try:
                    authorizer.track_tool_call(
                        task_id=task_id,
                        tool_name=tc["tool_name"],
                        parameters=tc.get("parameters"),
                    )
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")
            if self.verbose and tool_calls:
                print(f"   ✅ ToolAuthorization: {len(tool_calls)} calls checked")

        # PrivilegeEscalationDetector
        priv_det = getattr(self.monitor, "privilege_escalation_detector", None)
        if priv_det and tool_calls:
            try:
                # DQ-124: privilege_level 없는 tool_calls에 휴리스틱으로 보강
                from .framework_integrations import infer_privilege_level as _infer_priv
                _enriched_calls = [
                    {**tc, "privilege_level": tc.get("privilege_level") or _infer_priv(tc.get("tool_name", ""))}
                    for tc in tool_calls
                ]
                priv_det.analyze_privilege_chain(task_id=task_id, tool_calls=_enriched_calls)
                if self.verbose:
                    print(f"   ✅ PrivilegeEscalation: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # ToolChainAttackDetector
        chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
        if chain_det and tool_calls:
            tool_names = [tc["tool_name"] for tc in tool_calls]
            try:
                chain_det.analyze_tool_chain(task_id=task_id, tool_sequence=tool_names)
                if self.verbose:
                    print(f"   ✅ ToolChainAttack: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

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
                retry = self.monitor.retry_tracker.get_retry_metrics()
                tool_eff = self.monitor.tool_analyzer.get_efficiency_stats()
                _tool_acc_str = (
                    f"{tool.get('accuracy', 0):.1f}%"
                    if tool
                    else "N/A (no expected_tools provided)"
                )
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
        """실행 이력과 내부 카운터를 초기화합니다. 같은 인스턴스로 새 평가 세션을 시작할 때 사용하세요."""
        self.execution_history = []
        self._tasks_with_ground_truth = 0

    def track_workflow_step(
        self,
        step_name: str,
        success: bool = True,
        duration: float = 0.0,
        agent_name: str = "",
    ) -> None:
        """워크플로우 단계를 수동으로 추적합니다. on_messages 이벤트 외부에서 커스텀 스텝을 기록할 때 사용하세요."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step_name,
            step_type="task_completion",
            success=success,
            execution_time=duration,
            framework="autogen",
            metadata={"agent": agent_name} if agent_name else {},
        )

    def track_agent_interaction(
        self,
        from_agent: str,
        to_agent: str,
        interaction_type: str = "delegation",
        success: bool = True,
    ) -> None:
        """에이전트 간 상호작용을 수동으로 추적합니다."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.agent_coordination_tracker.track_interaction(
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            interaction_type=interaction_type,
            success=success,
        )

    def track_tool_usage(
        self,
        tool_name: str,
        success: bool = True,
        duration: float = 0.0,
        parameters: Optional[Dict[str, Any]] = None,
        execution_result: str = "",
    ) -> None:
        """도구 사용을 수동으로 추적합니다."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.tool_analyzer.analyze_execution(
            task_id=task_id,
            tool_calls=[{
                "tool_name": tool_name,
                "success": success,
                "duration": duration,
                "parameters": parameters or {},
                "execution_result": execution_result,
            }],
        )

    def get_statistics(self) -> Dict[str, Any]:
        """통계 반환"""
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


def create_evaluated_autogen_agent(
    agent_or_team: Any,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> AutoGenEvaluator:
    """AutoGen 에이전트/팀을 평가 래퍼로 감싸는 편의 함수"""
    return AutoGenEvaluator(
        agent_or_team=agent_or_team,
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )
