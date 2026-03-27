#!/usr/bin/env python3
"""
LangGraph Integration - Full 3-Layer Metrics Support
=====================================================

LangGraph 1.1.x 워크플로우에 대한 완전한 평가 기능을 제공합니다.

주요 기능:
- Layer 1: Native Metrics — TCR, Accuracy, Latency, Token Economy, ResponseQuality
- Layer 2: Agentic AI Metrics — Workflow Execution 노드별 자동 추적
  - from_compiled 모드: stream() 사용으로 노드별 실측 타이밍 수집
  - AIMessage.tool_calls 파싱 → ToolSelectionTracker 자동 연결
- Security (opt-in): enable_security=True 로 InputSanitization / OutputLeakage 활성화
- 기존 컴파일된 그래프(CompiledGraph) 직접 래핑 지원
- AIMessage.usage_metadata 를 통한 정확한 토큰 추적

사용 방법 A — 직접 그래프 빌드:
    evaluator = LangGraphEvaluator(monitor, enable_layer2=True)
    evaluator.add_node("retrieve", retrieve_fn)
    evaluator.add_node("generate", generate_fn)
    evaluator.add_edge("retrieve", "generate")
    evaluator.set_entry_point("retrieve")
    result = evaluator.run({"messages": [HumanMessage(content="질문")]})

사용 방법 B — 기존 컴파일 그래프 래핑:
    app = your_graph.compile()
    evaluator = LangGraphEvaluator.from_compiled(app, monitor)
    result = evaluator.run({"messages": [...]})

요구 사항:
    pip install "agent-evaluator[langchain]"
    langgraph >= 1.0.0, langchain-core >= 1.0.0
"""

import time
from typing import Any, Callable, Dict, List, Optional, TypedDict
from datetime import datetime

from ..core.agent_evaluator import PerformanceMonitor, TaskResult, TaskType
from .framework_integrations import (
    ensure_security_trackers as _ensure_security_trackers,
    extract_tools_from_framework_object as _extract_tools_from_graph,
    infer_privilege_level as _infer_privilege_level,
)

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
    from langgraph.graph import StateGraph, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    START = "__start__"
    END = "__end__"


# 검색/조회 노드 감지용 키워드 — 노드 이름에 포함되면 RAG 컨텍스트로 수집
# "query"·"rag" 제거: 일반 쿼리 노드("query_decomposer" 등)와 오분류 가능성 높음
_RETRIEVAL_NODE_KEYWORDS = frozenset({
    "retrieve", "retriev", "search",
    "fetch", "lookup", "document", "vector",
})

# 생성 노드 키워드 — 명시적 생성 노드는 RAG 노드에서 제외
_GENERATION_NODE_KEYWORDS = frozenset({
    "generate", "write", "compose", "summarize", "create", "respond",
})


def _auto_extract_elements(text: str) -> List[str]:
    """
    입력 텍스트에서 ResponseQuality expected_elements를 다단계 휴리스틱으로 추출합니다.
    영문/한국어 동사 패턴, 목적어 패턴, 콤마 분리 fallback 을 차례로 적용합니다.
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
    for pat in en_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            _add(m.group(1))
            if len(elements) >= 5:
                return elements

    ko_patterns = [
        r'(?:포함|언급|설명|제공|나열|기술|작성|다루|분석|검토|평가|살펴|알아|논의|기재)(?:해|하|하여|하고|할|하는|되어야|되어|줘|주세요|바랍니다)\s*([^,\.\n]{2,80})',
        r'([^,\.\n]{2,40})(?:의|에\s*대한|에\s*관한)\s+(?:장단점|중요성|의의|상세|이유|효과|문제점|영향)',
        r'다음(?:과|을|의)\s+(?:같은|같이)?\s*([^,\.\n]{2,60})',
    ]
    for pat in ko_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            _add(m.group(1))
            if len(elements) >= 5:
                return elements

    if not elements and len(text) < 300:
        parts = re.split(r'[,;]', text)
        if 1 < len(parts) <= 6:
            for p in parts:
                _add(p)
                if len(elements) >= 5:
                    break

    return elements[:5]


def _estimate_tokens_cjk(text: str) -> int:
    """
    텍스트 길이 기반 토큰 추정 (한국어/중국어/일본어 인식).
    CJK 문자 비율이 30% 이상이면 char÷2, 그 이하면 char÷4 (영문 기준).
    tiktoken이 있으면 tiktoken 사용.
    """
    if not text:
        return 1
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return max(1, len(enc.encode(text)))
    except Exception:
        pass
    import re
    cjk_count = len(re.findall(r"[\u1100-\u11ff\u3040-\u30ff\u3130-\u318f\uac00-\ud7a3\u4e00-\u9fff]", text))
    ratio = cjk_count / max(len(text), 1)
    divisor = 2 if ratio > 0.3 else 4
    return max(1, len(text) // divisor)


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


class AgentState(TypedDict):
    """기본 LangGraph 상태 스키마"""
    messages: list


class LangGraphEvaluator:
    """
    LangGraph 1.x 워크플로우 평가 클래스 (Layer 1/2 지원)

    두 가지 사용 방식:
    1. 직접 노드/엣지를 추가해 그래프를 빌드 (add_node / add_edge)
    2. 기존 컴파일된 그래프를 래핑 (from_compiled 클래스 메서드)
    """

    def __init__(
        self,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_security: bool = False,
        task_type: str = TaskType.QA.value,
        state_schema: type = AgentState,
        verbose: bool = True,
        privilege_registry: Optional[Dict[str, str]] = None,
        authorized_tools: Optional[List[str]] = None,
    ):
        """
        LangGraphEvaluator 초기화 (직접 빌드 모드)

        Args:
            monitor: PerformanceMonitor (없으면 새로 생성)
            enable_layer2: Layer 2 메트릭 활성화
            enable_security: 보안 지표 활성화 (opt-in, 성능 영향)
            task_type: TaskResult 타입
            state_schema: StateGraph 상태 스키마 TypedDict
            verbose: 상세 출력
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is not installed. "
                "Install with: pip install 'agent-evaluator[langchain]'"
            )

        self.monitor = monitor if monitor is not None else PerformanceMonitor()
        self.enable_layer2 = enable_layer2
        self.enable_security = enable_security
        self.task_type = task_type
        self.verbose = verbose
        # authorized_tools 자동 추출: 미제공 시 graph에서 바인딩된 도구 탐색
        if not authorized_tools:
            authorized_tools = _extract_tools_from_graph(
                self._workflow if self._workflow is not None else {}
            )
            if authorized_tools and verbose:
                print(f"   ℹ️  authorized_tools 자동 추출: {authorized_tools}")
        self.authorized_tools: List[str] = list(authorized_tools or [])
        self._compiled_graph = None  # from_compiled 모드에서 사용

        self._workflow = StateGraph(state_schema)
        self._custom_nodes: Dict[str, Callable] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self._tasks_with_ground_truth: int = 0  # ground_truth 제공 횟수 추적 (Accuracy N/A 판단용)
        self._current_task_id: Optional[str] = None
        self._current_ground_truth: Optional[str] = None
        self._step_tracking: List[Dict[str, Any]] = []  # 노드별 실행 기록
        self._retrieved_contexts: List[str] = []        # RAG 컨텍스트 (검색 노드 출력)
        self._current_model_name: str = ""              # AIMessage.response_metadata에서 추출
        self._global_ai_tool_map: Dict[str, Any] = {}  # 그래프 전역 tool_name→args 매핑
        self._node_type_hints: Dict[str, str] = {}  # 명시적 노드 타입 힌트 맵

        if self.authorized_tools:
            self.monitor._authorized_tools = self.authorized_tools

        if enable_security:
            _ensure_security_trackers(self.monitor, privilege_registry=privilege_registry)
        elif privilege_registry:
            self.monitor.privilege_registry = privilege_registry

        if self.verbose:
            print(f"✅ LangGraphEvaluator 초기화 완료 "
                  f"(Layer2: {enable_layer2}, Security: {enable_security})")

    @classmethod
    def from_compiled(
        cls,
        compiled_graph,
        monitor: Optional[PerformanceMonitor] = None,
        enable_layer2: bool = True,
        enable_security: bool = False,
        task_type: str = TaskType.QA.value,
        verbose: bool = True,
        privilege_registry: Optional[Dict[str, str]] = None,
        authorized_tools: Optional[List[str]] = None,
        node_type_hints=None,  # ← 추가: {"node_name": "retrieval"|"generation"|"tool"|"auto"}
    ) -> "LangGraphEvaluator":
        """
        기존 컴파일된 LangGraph를 래핑합니다.
        run() 시 stream() 모드로 실행해 노드별 실측 타이밍을 수집합니다.

        Args:
            compiled_graph: CompiledStateGraph (StateGraph.compile() 결과)
            monitor: PerformanceMonitor
            ...

        Returns:
            LangGraphEvaluator 인스턴스 (run() 으로 실행)
        """
        evaluator = cls.__new__(cls)
        evaluator.monitor = monitor if monitor is not None else PerformanceMonitor()
        evaluator.enable_layer2 = enable_layer2
        evaluator.enable_security = enable_security
        evaluator.task_type = task_type
        evaluator.verbose = verbose
        evaluator._node_type_hints = dict(node_type_hints or {})  # 노드 타입 힌트 맵
        evaluator._compiled_graph = compiled_graph
        evaluator._workflow = None
        evaluator._custom_nodes = {}
        evaluator.execution_history = []
        evaluator._current_task_id = None
        evaluator._current_ground_truth = None
        evaluator._step_tracking = []
        evaluator._retrieved_contexts = []
        evaluator._current_model_name = ""
        evaluator._global_ai_tool_map = {}
        evaluator._tasks_with_ground_truth = 0

        # authorized_tools 자동 추출
        if not authorized_tools:
            authorized_tools = _extract_tools_from_graph(compiled_graph)
            if authorized_tools and verbose:
                print(f"   ℹ️  authorized_tools 자동 추출: {authorized_tools}")
        evaluator.authorized_tools = list(authorized_tools or [])

        if evaluator.authorized_tools:
            evaluator.monitor._authorized_tools = evaluator.authorized_tools

        if enable_security:
            _ensure_security_trackers(evaluator.monitor, privilege_registry=privilege_registry)
        elif privilege_registry:
            evaluator.monitor.privilege_registry = privilege_registry

        if verbose:
            print(f"✅ LangGraphEvaluator (from_compiled) 초기화 완료")
        return evaluator

    def set_compiled_graph(self, compiled_graph: Any) -> None:
        """컴파일된 그래프를 from_compiled 모드로 설정합니다.

        create_evaluated_langgraph_agent() 팩토리 함수가 내부적으로 사용.
        직접 호출 시 기존 _compiled_graph 를 교체합니다.
        """
        self._compiled_graph = compiled_graph
        self._workflow = None

    # ── 그래프 빌드 API (직접 빌드 모드) ─────────────────────────────────

    def add_node(self, name: str, func: Callable,
                 node_type: str = "auto"):
        """
        노드를 추가합니다. enable_layer2=True 이면 자동으로 추적 래퍼를 씌웁니다.

        Args:
            name: 노드 이름
            func: 노드 함수 (state → state)
            node_type: 노드 타입 힌트. "retrieval"|"generation"|"tool"|"auto" (기본값).
                       "auto" 이면 노드명 키워드로 자동 감지합니다.
                       "retrieval" 이면 RAG 컨텍스트 수집 대상으로 강제 지정합니다.
        """
        if self._workflow is None:
            raise RuntimeError("from_compiled 모드에서는 add_node를 사용할 수 없습니다.")
        self._custom_nodes[name] = func
        node_fn = self._wrap_node(name, func) if self.enable_layer2 else func
        self._workflow.add_node(name, node_fn)
        # 명시적 타입 힌트 저장 — _wrap_node 및 _run_with_stream 에서 참조
        if not hasattr(self, "_node_type_hints"):
            self._node_type_hints = {}
        if node_type != "auto":
            self._node_type_hints[name] = node_type

    def add_edge(self, from_node: str, to_node: str):
        """고정 엣지 추가"""
        if self._workflow is None:
            raise RuntimeError("from_compiled 모드에서는 add_edge를 사용할 수 없습니다.")
        self._workflow.add_edge(from_node, to_node)

    def add_conditional_edges(self, from_node: str, condition_fn: Callable, mapping: Dict[str, str]):
        """조건부 엣지 추가"""
        if self._workflow is None:
            raise RuntimeError("from_compiled 모드에서는 이 메서드를 사용할 수 없습니다.")
        self._workflow.add_conditional_edges(from_node, condition_fn, mapping)

    def set_entry_point(self, node_name: str):
        """그래프 진입점 설정"""
        if self._workflow is None:
            raise RuntimeError("from_compiled 모드에서는 이 메서드를 사용할 수 없습니다.")
        self._workflow.set_entry_point(node_name)

    # ── 노드 추적 래퍼 ────────────────────────────────────────────────────

    def _wrap_node(self, node_name: str, func: Callable) -> Callable:
        """노드 함수를 래핑해 Workflow Execution 지표를 자동으로 수집합니다."""

        def wrapped(state: Any) -> Any:
            start = time.time()
            success = True
            error: Optional[str] = None

            try:
                result = func(state)
            except Exception as e:
                success = False
                error = str(e)
                result = state

            elapsed = time.time() - start

            # WorkflowExecutionTracker 기록 — LLM vs. tool_call vs. 일반 노드 구분
            if self._current_task_id:
                # ToolMessage 우선 확인 → tool_call; AIMessage → llm_generation; 그 외 → node
                has_ai_msg = False
                has_tool_msg = False
                if isinstance(result, dict) and "messages" in result:
                    try:
                        from langchain_core.messages import (
                            AIMessage as _AI, ToolMessage as _TM,
                        )
                        _msgs = result["messages"]
                        has_tool_msg = any(isinstance(m, _TM) for m in _msgs)
                        has_ai_msg = any(isinstance(m, _AI) for m in _msgs)
                    except ImportError:
                        pass
                if has_tool_msg:
                    step_type = "tool_call"
                elif has_ai_msg:
                    step_type = "llm_generation"
                else:
                    step_type = "node"
                self.monitor.workflow_tracker.track_step(
                    task_id=self._current_task_id,
                    step_name=node_name,
                    step_type=step_type,
                    success=success,
                    execution_time=elapsed,
                    framework="langgraph",
                    metadata={"error": error} if error else {},
                )

            self._step_tracking.append({
                "node": node_name,
                "success": success,
                "execution_time": elapsed,
                "error": error,
                "tokens": {"input": 0, "output": 0},  # 명시적 초기화 — _extract_from_messages에서 누적
            })

            # messages 에서 ToolMessage / AIMessage 토큰/도구 추출
            if isinstance(result, dict) and "messages" in result:
                self._extract_from_messages(result["messages"], elapsed)

            # 검색 노드: ToolMessage 내용과 Document 객체를 RAG 컨텍스트로 수집
            # 생성 노드 키워드가 있으면 RAG 노드로 오분류 방지
            _hints = getattr(self, "_node_type_hints", {})
            _explicit_type = _hints.get(node_name, "auto")
            if _explicit_type == "retrieval":
                _is_retrieval = True
            elif _explicit_type in ("generation", "tool"):
                _is_retrieval = False
            else:
                _is_retrieval = (
                    any(kw in node_name.lower() for kw in _RETRIEVAL_NODE_KEYWORDS)
                    and not any(kw in node_name.lower() for kw in _GENERATION_NODE_KEYWORDS)
                )
            if _is_retrieval:
                if isinstance(result, dict):
                    for msg in result.get("messages", []):
                        content = getattr(msg, "content", "")
                        # DQ-001: 20자 미만 단편 필터 — 노이즈·단어 하나 제거
                        if (content and isinstance(content, str) and len(content) >= 20
                                and content not in self._retrieved_contexts):
                            self._retrieved_contexts.append(content)
                    # Document 객체 직접 반환 패턴 (documents/docs/context/retrieved/passages 키)
                    # DQ-016: "content"/"text"/"payload" 추가 — 커스텀 Document 스키마 지원
                    for key in ("documents", "docs", "context", "retrieved", "passages"):
                        for doc in result.get(key, []) or []:
                            # DQ-016: page_content → content → text → payload 순으로 fallback
                            if isinstance(doc, dict):
                                page_content = (
                                    doc.get("page_content")
                                    or doc.get("content")
                                    or doc.get("text")
                                    or doc.get("payload")
                                )
                            else:
                                page_content = (
                                    getattr(doc, "page_content", None)
                                    or getattr(doc, "content", None)
                                    or getattr(doc, "text", None)
                                )
                            # DQ-001: 20자 미만 단편 필터
                            if (page_content and len(str(page_content)) >= 20
                                    and str(page_content) not in self._retrieved_contexts):
                                self._retrieved_contexts.append(str(page_content))

            return result

        return wrapped

    def _extract_from_messages(self, messages: list, node_elapsed: float):
        """AIMessage.usage_metadata / tool_calls 와 ToolMessage 에서 토큰·도구 정보 추출"""
        if not self._step_tracking:
            # step_tracking 없이 호출되는 경우 방어 — 현재 경로에서는 발생하지 않지만
            # 향후 코드 변경 시 IndexError 방지
            return
        try:
            from langchain_core.messages import AIMessage, ToolMessage
        except ImportError:
            return

        for msg in messages:
            if isinstance(msg, AIMessage):
                meta = getattr(msg, "usage_metadata", None) or {}
                # None 기본값 사용 — 키 부재(None)와 API 명시 0 구분
                input_t = meta.get("input_tokens")
                output_t = meta.get("output_tokens")
                # Fallback: usage_metadata 에 키가 아예 없으면 길이 기반 추정 (한국어 인식)
                if input_t is None and output_t is None:
                    _content_str = str(getattr(msg, "content", ""))
                    input_t = _estimate_tokens_cjk(_content_str)
                    output_t = 0
                elif input_t is None:
                    input_t = 0
                # Partial fallback: input 키는 있고 output 키가 아예 없는 경우만 추정
                # (API가 명시적으로 output=0 반환 시 추정으로 덮어쓰지 않음)
                # DQ-004: input_t=0 일 때 falsy → 추정 건너뜀 버그 방지. is not None 사용
                if input_t is not None and output_t is None:
                    _content_str = str(getattr(msg, "content", ""))
                    if _content_str:
                        output_t = _estimate_tokens_cjk(_content_str)
                input_t = input_t or 0
                output_t = output_t or 0
                # 누적 토큰 — 동일 노드에서 AIMessage 여러 개일 때도 모두 합산
                # setdefault 대신 명시적 누적으로 두 번째 이후 AIMessage 토큰 손실 방지
                node_tokens = self._step_tracking[-1].setdefault("tokens", {"input": 0, "output": 0})
                node_tokens["input"] += input_t
                node_tokens["output"] += output_t
                # model_name 추출 (response_metadata 우선, 없으면 id 필드)
                if not self._current_model_name:
                    resp_meta = getattr(msg, "response_metadata", None) or {}
                    self._current_model_name = (
                        resp_meta.get("model_name", "")
                        or resp_meta.get("model", "")
                        or resp_meta.get("model_id", "")
                    )
                # AIMessage.tool_calls → ToolSelectionTracker 연결용 + parameters 수집
                tool_calls_raw = getattr(msg, "tool_calls", None) or []
                for tc in tool_calls_raw:
                    if isinstance(tc, dict):
                        tool_name = tc.get("name") or ""
                        args = tc.get("args") or tc.get("arguments") or {}
                    else:
                        tool_name = getattr(tc, "name", None) or ""
                        args = getattr(tc, "args", None) or getattr(tc, "arguments", {}) or {}
                    if not tool_name:
                        continue  # 이름 없는 tool_call은 ToolMessage 매핑 불가 → 건너뜀
                    self._step_tracking[-1].setdefault("ai_tool_calls", []).append(tool_name)
                    # tool_name → args 매핑: ToolMessage 처리 시 parameters로 활용
                    self._step_tracking[-1].setdefault("ai_tool_map", {})[tool_name] = args
                    # 그래프 전역 맵에도 누적 — ToolMessage가 다른 노드에서 올 때 fallback
                    self._global_ai_tool_map[tool_name] = args

            elif isinstance(msg, ToolMessage):
                # 에러 감지: dict 중첩 시 false-positive 방지 (최상위 키만 확인)
                content = msg.content
                if isinstance(content, dict):
                    is_error = bool(content.get("error") or content.get("is_error"))
                else:
                    is_error = "error" in str(content).lower()
                tool_name_str = getattr(msg, "name", None) or "unknown_tool"
                # AIMessage.tool_calls args → parameters 역매핑
                # 스텝 수준 맵 우선 → 글로벌 맵 fallback (다른 노드에서 선언된 tool_calls 처리)
                ai_map = self._step_tracking[-1].get("ai_tool_map", {})
                parameters = ai_map.get(tool_name_str) or self._global_ai_tool_map.get(tool_name_str) or {}
                # DQ-162: AIMessage args가 문자열로 파싱되는 경우 dict로 감싸기 (json.dumps 일관성)
                if not isinstance(parameters, dict):
                    parameters = {"_raw": str(parameters)}
                # 복수형 "tool_calls" 리스트로 수집 — 한 노드에서 여러 도구 호출 지원
                _exec_result = ""
                if content is not None:
                    _raw = content if isinstance(content, str) else str(content)
                    _exec_result = _raw[:2000]  # OutputLeakage + ToolCallAnalyzer용 — LangChain과 통일
                self._step_tracking[-1].setdefault("tool_calls", []).append({
                    "tool_name": tool_name_str,
                    "success": not is_error,
                    "duration": node_elapsed,
                    "parameters": parameters,
                    "privilege_level": _resolve_privilege_level(tool_name_str, self.monitor),
                    "execution_result": _exec_result,
                })

    # ── from_compiled 모드: stream() 기반 실행 ───────────────────────────

    def _run_with_stream(
        self,
        graph,
        initial_state: Dict[str, Any],
        **invoke_kwargs,
    ) -> Dict[str, Any]:
        """
        stream() 모드로 그래프를 실행해 노드별 실측 타이밍을 수집합니다.
        각 스트림 청크(노드 출력)의 처리 시간을 WorkflowTracker에 기록합니다.
        """
        result: Dict[str, Any] = {}
        node_start = time.time()
        prev_node: Optional[str] = None  # 노드 전환 추적용

        try:
            for chunk in graph.stream(initial_state, **invoke_kwargs):
                chunk_time = time.time()
                elapsed = chunk_time - node_start
                node_start = chunk_time

                # chunk = {node_name: state_update}
                for node_name, node_output in chunk.items():
                    if node_name in (START, END, "__start__", "__end__"):
                        continue

                    step_info: Dict[str, Any] = {
                        "node": node_name,
                        "success": True,
                        "execution_time": elapsed,
                        "error": None,
                        "tokens": {"input": 0, "output": 0},  # 명시적 초기화 — _wrap_node와 동일
                    }

                    # 노드 출력에서 메시지 추출
                    if isinstance(node_output, dict):
                        result.update(node_output)
                        msgs = node_output.get("messages", [])
                        if msgs:
                            self._step_tracking.append(step_info)
                            self._extract_from_messages(msgs, elapsed)
                        else:
                            self._step_tracking.append(step_info)
                    else:
                        self._step_tracking.append(step_info)

                    if self.enable_layer2 and self._current_task_id:
                        # step_type 세분화: AIMessage → llm_generation, ToolMessage → tool_call, 그 외 → node
                        stream_step_type = "node"
                        if isinstance(node_output, dict):
                            _msgs = node_output.get("messages", [])
                            if _msgs:
                                try:
                                    from langchain_core.messages import (
                                        AIMessage as _AI, ToolMessage as _TM,
                                    )
                                    if any(isinstance(m, _TM) for m in _msgs):
                                        stream_step_type = "tool_call"
                                    elif any(isinstance(m, _AI) for m in _msgs):
                                        stream_step_type = "llm_generation"
                                except ImportError:
                                    pass
                        self.monitor.workflow_tracker.track_step(
                            task_id=self._current_task_id,
                            step_name=node_name,
                            step_type=stream_step_type,
                            success=True,
                            execution_time=elapsed,
                            framework="langgraph",
                        )

                    # 검색 노드: 메시지 내용과 Document 객체를 RAG 컨텍스트로 수집
                    if any(kw in node_name.lower() for kw in _RETRIEVAL_NODE_KEYWORDS):
                        if isinstance(node_output, dict):
                            for msg in node_output.get("messages", []):
                                content = getattr(msg, "content", "")
                                if (content and isinstance(content, str) and len(content) > 0
                                        and content not in self._retrieved_contexts):
                                    self._retrieved_contexts.append(content)
                            # Document 객체 직접 반환 패턴
                            for key in ("documents", "docs", "context", "retrieved"):
                                for doc in node_output.get(key, []) or []:
                                    page_content = (
                                        getattr(doc, "page_content", None)
                                        or (doc.get("page_content") if isinstance(doc, dict) else None)
                                    )
                                    if (page_content and len(str(page_content)) > 0
                                            and str(page_content) not in self._retrieved_contexts):
                                        self._retrieved_contexts.append(str(page_content))

                    # 노드 전환 기록 (AgentCoordinationTracker용)
                    # step_info 에 prev_node 저장 → run() 에서 집계
                    if prev_node and prev_node != node_name:
                        step_info["prev_node"] = prev_node
                    prev_node = node_name

        except Exception:
            # stream() 실패 시 invoke() 로 fallback
            # 부분 수집된 step_tracking 초기화 (불완전 데이터 방지)
            self._step_tracking = []
            if self.verbose:
                print(f"⚠️  LangGraph stream() 실패 → invoke() fallback "
                      f"(Layer 2 지표 미수집, 실행 결과는 정상)")
            result = graph.invoke(initial_state, **invoke_kwargs)

        return result

    # ── 실행 ─────────────────────────────────────────────────────────────

    def run(
        self,
        initial_state: Dict[str, Any],
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # FA7: EvaluatorProtocol 통일 인터페이스
        task_id: Optional[str] = None,
        **invoke_kwargs,
    ) -> Dict[str, Any]:
        """
        워크플로우를 실행하고 평가 지표를 수집합니다.

        Args:
            initial_state: 초기 그래프 상태 dict
            ground_truth: 정답 텍스트 (Accuracy 계산용)
            expected_tools: 기대 도구 목록 (Layer 2 ToolSelection, from_compiled 모드)
            expected_elements: ResponseQuality completeness 평가용 기대 요소 목록
            expected_agents: 기대 노드/에이전트 목록 (AgentCoordinationTracker 검증용)
            **invoke_kwargs: graph.invoke()/stream() 에 전달할 추가 인자

        Returns:
            최종 그래프 상태 dict
        """
        self._current_task_id = task_id or f"langgraph_{int(time.time() * 1000)}"
        self._current_ground_truth = ground_truth
        # DQ-002: 빈 문자열 ground_truth는 유의미한 accuracy 측정 불가
        if ground_truth is not None and ground_truth.strip():
            self._tasks_with_ground_truth += 1
        self._step_tracking = []
        self._retrieved_contexts = []
        self._current_model_name = ""
        self._global_ai_tool_map = {}

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"🚀 LangGraph 실행 시작 (Task ID: {self._current_task_id})")
            print(f"{'='*70}")

        start_time = time.time()
        success = True
        errors: List[str] = []
        result: Dict[str, Any] = {}

        try:
            graph = self._compiled_graph or self._workflow.compile()

            if self._compiled_graph and self.enable_layer2:
                # from_compiled 모드: stream() 으로 노드별 실측 타이밍
                result = self._run_with_stream(graph, initial_state, **invoke_kwargs)
            else:
                # 직접 빌드 모드: wrapped 노드가 이미 추적 처리
                result = graph.invoke(initial_state, **invoke_kwargs)

            if self.verbose:
                print(f"\n✅ LangGraph 실행 완료")
        except Exception as e:
            success = False
            errors.append(str(e))
            result = initial_state
            if self.verbose:
                print(f"\n❌ LangGraph 실행 실패: {e}")

        execution_time = time.time() - start_time

        # 토큰 합산 + 노드 전환 수집 (step_tracking → 중복 없이)
        tokens: Dict[str, int] = {"input": 0, "output": 0}
        tool_calls: List[Dict[str, Any]] = []
        ai_tool_names: List[str] = []
        node_transitions: List[tuple] = []
        for step in self._step_tracking:
            t = step.get("tokens", {})
            tokens["input"] += t.get("input", 0)
            tokens["output"] += t.get("output", 0)
            # 복수형 "tool_calls" 리스트 수집 (여러 ToolMessage 지원)
            tool_calls.extend(step.get("tool_calls", []))
            if step.get("error"):
                errors.append(f"[{step['node']}] {step['error']}")
            ai_tool_names.extend(step.get("ai_tool_calls", []))
            # 노드 전환 수집 (from_compiled stream 모드)
            if prev_n := step.get("prev_node"):
                node_transitions.append((prev_n, step["node"]))

        # 직접 빌드 모드 fallback: _wrap_node step_tracking 순서 기반으로 노드 전환 보완
        # (from_compiled stream 모드에서는 step_info["prev_node"] 로 이미 수집됨)
        _PSEUDO_NODES = {START, END, "__start__", "__end__"}
        if not node_transitions and len(self._step_tracking) > 1:
            for i in range(1, len(self._step_tracking)):
                p = self._step_tracking[i - 1]["node"]
                c = self._step_tracking[i]["node"]
                if p != c and p not in _PSEUDO_NODES and c not in _PSEUDO_NODES:
                    node_transitions.append((p, c))

        response_text = self._extract_response(result)
        self._record_layer1(
            execution_time=execution_time,
            success=success and not errors,
            errors=errors,
            tokens=tokens,
            tool_calls=tool_calls,
            response_text=response_text,
            initial_state=initial_state,
            retrieved_contexts=self._retrieved_contexts,
            expected_elements=expected_elements or [],
        )

        if self.enable_layer2:
            self._record_layer2_extra(
                expected_tools=expected_tools,
                ai_tool_names=ai_tool_names,
                tool_calls=tool_calls,
                node_transitions=node_transitions,
                execution_time=execution_time,
                expected_agents=expected_agents,  # I-C-002: 노드 기반 에이전트 선택 정확도 평가
            )

        if self.enable_security:
            self._record_security(initial_state, response_text, tool_calls)

        # FA3: 표준 실행 히스토리 스키마 (UI-023: input/output 키 통일)
        self.execution_history.append({
            "task_id": self._current_task_id,
            "timestamp": datetime.now(),
            "success": success,
            "execution_time": execution_time,
            "framework": "langgraph",
            "input": initial_state,
            "output": result,
        })

        if self.verbose:
            print(f"\n📊 평가 완료 (소요 시간: {execution_time:.2f}s)")

        return result

    def _extract_response(self, state: Dict[str, Any]) -> str:
        """그래프 최종 상태에서 응답 텍스트 추출"""
        messages = state.get("messages", [])
        if not messages:
            return str(state.get("output", state.get("result", "")))
        try:
            from langchain_core.messages import AIMessage
            ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
            if ai_msgs:
                return str(ai_msgs[-1].content)
        except ImportError:
            pass
        last = messages[-1]
        if isinstance(last, dict):
            return str(last.get("content", last))
        return str(getattr(last, "content", last))

    def _record_layer1(
        self,
        execution_time: float,
        success: bool,
        errors: List[str],
        tokens: Dict[str, int],
        tool_calls: List[Dict[str, Any]],
        response_text: str,
        initial_state: Dict[str, Any],
        retrieved_contexts: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
    ):
        execution_time = max(0.001, execution_time)  # D3-1: zero-latency guard
        if self.verbose:
            print(f"\n📈 Layer 1: Native Metrics 기록 중...")

        msgs = initial_state.get("messages", [])
        if msgs:
            first = msgs[0]
            question = str(getattr(first, "content", first))
        else:
            # messages 키 없는 비표준 state: input/query/prompt 키 순서로 fallback
            _q = None
            for _k in ("input", "query", "question", "prompt", "task", "content"):
                if _k in initial_state and initial_state[_k]:
                    _q = str(initial_state[_k])
                    break
            question = _q if _q else str(initial_state)

        if create_taskresult_from_execution and _HELPERS_AVAILABLE:
            task = create_taskresult_from_execution(
                task_id=self._current_task_id,
                task_type=self.task_type,
                question=question,
                response=response_text,
                # None → "" 명시적 변환: `or ""` 사용 시 "" 도 동일하게 처리되어
                # 하위 accuracy_evaluator 검사에서 의도치 않게 스킵될 수 있음
                ground_truth=self._current_ground_truth if self._current_ground_truth is not None else "",
                execution_time=execution_time,
                has_error=not success,
                error_message=errors[0] if errors else None,
            )
            # I-C-001: tool_calls 실측 데이터 덮어씀 → monitor.record_task()가
            # tool_analyzer.analyze_execution()을 호출하도록 보장
            task.tool_calls = tool_calls
            # Override with actual measured tokens (estimated tokens from helper may be inaccurate)
            if tokens.get("input", 0) > 0 or tokens.get("output", 0) > 0:
                task.tokens_used = tokens
        else:
            # DQ-018: 공백 전용 ground_truth 는 truthy지만 의미 없는 계산 → strip() 추가
            _acc = (
                calculate_accuracy_score(response_text, self._current_ground_truth)
                if calculate_accuracy_score and response_text and self._current_ground_truth
                and self._current_ground_truth.strip()
                else 0.0
            )
            task = TaskResult(
                task_id=self._current_task_id,
                task_type=self.task_type,
                success=success,
                completion_score=1.0 if (success and bool(response_text)) else 0.0,
                accuracy_score=_acc,
                execution_time=execution_time,
                tokens_used=tokens,
                tool_calls=tool_calls,
                attempts=1,
                errors=errors,
                timestamp=datetime.now(),
            )

        # DQ-168: record_task() 전에 model 설정 → tokens_used.get("model") 경로 활성화
        _effective_model = (self._current_model_name or "unknown_model").lower()  # DQ-183
        task.tokens_used["model"] = _effective_model
        self.monitor.record_task(task)
        # 소급 설정 (defense-in-depth)
        if self.monitor.token_tracker.usage_log:
            self.monitor.token_tracker.usage_log[-1]["model"] = _effective_model


        # ResponseQualityEvaluator
        if question and response_text:
            try:
                _expected = expected_elements or []
                # expected_elements 자동 추출 (명시 전달 없을 때)
                if not _expected:
                    _expected = _auto_extract_elements(question)
                self.monitor.quality_evaluator.evaluate_response(
                    task_id=self._current_task_id,
                    response=response_text,
                    request=question,
                    expected_elements=_expected,
                    ground_truth=self._current_ground_truth,
                )
                if self.verbose and _expected:
                    print(f"   ✅ ResponseQuality: expected_elements={len(_expected)}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # HallucinationDetector — 검색 노드에서 수집한 RAG 컨텍스트
        if retrieved_contexts and response_text:
            try:
                # DQ-047: 대용량 RAG 결과 → 무제한 join 방지 (HallucinationDetector OOM 위험)
                # DQ-141: 공백 전용 컨텍스트 배제
                combined_context = "\n".join(c for c in retrieved_contexts if c.strip())[:50_000]
                if not combined_context.strip():
                    raise ValueError("retrieved_contexts are all whitespace")
                self.monitor.hallucination_detector.detect_hallucination(
                    task_id=self._current_task_id,
                    response=response_text,
                    context=combined_context,
                    ground_truth=self._current_ground_truth,
                )
                if self.verbose:
                    print(f"   ✅ HallucinationDetector: {len(retrieved_contexts)} 컨텍스트 분석")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        if self.verbose:
            print(f"   ✅ TCR: {(task.completion_score or 0.0) * 100:.1f}%  "
                  f"Latency: {execution_time:.2f}s  Tokens: {tokens}")

    def _record_layer2_extra(
        self,
        expected_tools: Optional[List[str]],
        ai_tool_names: List[str],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        node_transitions: Optional[List[tuple]] = None,
        execution_time: float = 0.0,
        expected_agents: Optional[List[str]] = None,
    ):
        """AIMessage.tool_calls 기반 ToolSelectionTracker + ToolCallAnalyzer + AgentCoordination"""
        # ToolSelectionTracker — expected_tools 가 명시적으로 제공된 경우에만 기록
        # expected_tools 없이 호출하면 100% 만점이 기록되어 지표가 오염됨
        #
        # DQ-022: tool_calls(실제 실행)와 ai_tool_names(AIMessage 예측)는 다른 소스
        # tool_calls 가 있으면 반드시 우선 사용. fallback 시 verbose 경고로 명시
        _tool_calls_executed = [tc["tool_name"] for tc in (tool_calls or [])]
        if _tool_calls_executed:
            actual_executed = _tool_calls_executed
            _selection_source = "executed"
        else:
            # fallback: AIMessage.tool_calls 예측값 (실제 실행 여부 불확실)
            actual_executed = ai_tool_names
            _selection_source = "predicted"
            if ai_tool_names and self.verbose:
                print(f"   ℹ️  Tool Selection: using AIMessage predicted tools (no ToolMessage execution data)")
        if expected_tools:
            try:
                self.monitor.tool_selection_tracker.evaluate_selection(
                    task_id=self._current_task_id,
                    expected_tools=expected_tools or [],
                    actual_tools=actual_executed,
                )
                if self.verbose:
                    if expected_tools:
                        print(f"   ✅ Tool Selection ({_selection_source}): "
                              f"expected={len(expected_tools)} actual={len(actual_executed)}")
                    else:
                        print(f"   ✅ Tool Selection: actual={len(actual_executed)} (no expected)")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")


        # I-C-002: Agent Selection Accuracy — expected_agents vs 실제 방문 노드
        # CrewAI와 동일 패턴: tool_selection_tracker.evaluate_selection()으로 에이전트 선택 정확도 평가
        # LangGraph에서 "에이전트" = 방문한 노드 (START/END/__start__/__end__ 제외)
        if expected_agents:
            _PSEUDO = {"__start__", "__end__", "start", "end"}
            actual_nodes = list(dict.fromkeys(
                s["node"] for s in self._step_tracking
                if s.get("node") and s["node"] not in _PSEUDO
            ))
            try:
                self.monitor.tool_selection_tracker.evaluate_selection(
                    task_id=f"{self._current_task_id}_agent_sel",
                    expected_tools=expected_agents,
                    actual_tools=actual_nodes,
                )
                if self.verbose:
                    print(f"   ✅ Agent Selection: expected={len(expected_agents)} "
                          f"actual={len(actual_nodes)}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ Agent Selection: {_e}")

        # AgentCoordinationTracker — 노드 전환 시퀀스 기반
        # to_node 실제 성공 여부를 step_tracking에서 조회
        node_success_map = {
            s["node"]: s.get("success", True) and not s.get("error")
            for s in self._step_tracking
        }
        transitions = node_transitions or []
        for from_node, to_node in transitions:
            interaction_success = node_success_map.get(to_node, True)
            try:
                self.monitor.agent_coordination_tracker.track_interaction(
                    task_id=self._current_task_id,
                    from_agent=from_node,
                    to_agent=to_node,
                    interaction_type="delegation",
                    success=interaction_success,
                    context={
                        "framework": "langgraph",
                        "from_node": from_node,
                        "to_node": to_node,
                    },
                )
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")
        if self.verbose and transitions:
            print(f"   ✅ Agent Coordination: {len(transitions)} node transitions")

        # RetryCorrectionTracker — 실패 후 동일 노드 재방문만 retry로 인정
        # 순차 파이프라인에서 노드가 여러 번 등장해도, 첫 방문이 성공이면 retry 아님.
        # 조건: 노드 N의 i번째 방문이 error/failure → (i+1)번째 방문이 존재 → retry
        if self._step_tracking:
            # 노드별 첫 실패 여부 기록 후, 동일 노드 재등장 시 retry로 판정
            _node_first_failed: Dict[str, bool] = {}  # node → first visit had error?
            _retried_nodes: set = set()
            for s in self._step_tracking:
                n = s["node"]
                _first_failed = _node_first_failed.get(n)
                if _first_failed is None:
                    # 첫 방문: 실패 여부 기록
                    _node_first_failed[n] = bool(s.get("error") or not s.get("success", True))
                elif _first_failed:
                    # 두 번째 이상 방문 + 첫 방문이 실패였음 → 실제 retry
                    _retried_nodes.add(n)

            if _retried_nodes:
                # 재시도 있음: 같은 노드의 연속 등장을 attempts_log로 변환
                attempts_log = []
                _seen_first: Dict[str, bool] = {}
                for s in self._step_tracking:
                    n = s["node"]
                    if n in _retried_nodes:
                        if n not in _seen_first:
                            _seen_first[n] = True
                            _err = s.get("error") or s.get("error_message") or ""
                            # DQ-036: 80자 truncation → 200자로 확대 (에러 컨텍스트 보존)
                            _reason = (
                                f"node_{n}: {str(_err)[:200]}" if _err
                                else f"node_{n}_retry"
                            )
                            attempts_log.append({
                                "success": False,
                                "retry_reason": _reason,
                                "duration": s.get("execution_time", 0.0),
                            })
                        else:
                            attempts_log.append({
                                "success": s.get("success", True) and not s.get("error"),
                                "retry_reason": "",
                                "duration": s.get("execution_time", 0.0),
                            })
            else:
                # 재시도 없음: 전체 그래프를 단일 시도로 기록 (측정된 execution_time 사용)
                overall_success = all(
                    s.get("success", True) and not s.get("error")
                    for s in self._step_tracking
                )
                attempts_log = [{"success": overall_success, "retry_reason": "", "duration": execution_time}]

            try:
                self.monitor.retry_tracker.track_attempts(
                    task_id=self._current_task_id,
                    attempts_log=attempts_log,
                    task_type=self.task_type,
                )
                if self.verbose:
                    if _retried_nodes:
                        print(f"   ✅ RetryCorrection: {len(_retried_nodes)} retried node(s) detected")
                    else:
                        print(f"   ✅ RetryCorrection: no retries (single attempt)")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

    def _record_security(
        self,
        initial_state: Dict[str, Any],
        response_text: str,
        tool_calls: List[Dict[str, Any]],
    ):
        if self.verbose:
            print(f"\n🔒 Security Metrics 기록 중...")

        # D8-1: 멀티턴 입력 전체 스캔 — 첫 메시지만 보던 기존 방식 개선
        # HumanMessage 또는 문자열 메시지 모두 수집해 injection 검사
        _msgs = initial_state.get("messages", [])
        if _msgs:
            from langchain_core.messages import HumanMessage as _HM
            _user_texts = []
            for _m in _msgs:
                # HumanMessage 또는 role=="user" dict 우선 수집
                _content = None
                if isinstance(_m, _HM):
                    _content = str(getattr(_m, "content", ""))
                elif isinstance(_m, dict) and _m.get("role") in ("user", "human"):
                    _content = str(_m.get("content", ""))
                elif not hasattr(_m, "type") and not isinstance(_m, dict):
                    # 문자열 등 비구조적 항목도 수집
                    _content = str(getattr(_m, "content", _m))
                if _content:
                    _user_texts.append(_content)
            # HumanMessage 없으면 첫 메시지로 fallback
            if not _user_texts and _msgs:
                _user_texts = [str(getattr(_msgs[0], "content", _msgs[0]))]
            # M7: 각 메시지를 최대 500자로 제한해 수집 (총 4000자까지)
            # → 단순 truncation보다 더 많은 메시지 커버 가능 (경계 injection 패턴 탐지 향상)
            _chunks: List[str] = []
            _total_chars = 0
            for _t in _user_texts:
                _c = _t[:500]
                if _total_chars + len(_c) > 4000:
                    break
                _chunks.append(_c)
                _total_chars += len(_c)
            _raw_input = " | ".join(_chunks)
        else:
            _raw_input = str(initial_state)
        if len(_raw_input) > 4000:
            import warnings as _w
            _w.warn(
                f"LangGraph InputSanitization: input truncated from {len(_raw_input)} to 4000 chars. "
                "Injection patterns beyond position 4000 will not be detected.",
                UserWarning,
                stacklevel=4,
            )
        input_text = _raw_input[:4000]
        sanitizer = getattr(self.monitor, "input_sanitizer", None)
        leakage_det = getattr(self.monitor, "output_leakage_detector", None)
        authorizer = getattr(self.monitor, "tool_authorizer", None)

        # D8-3: enable_security=True 인데 트래커 미초기화 시 경고
        if self.enable_security and sanitizer is None:
            import warnings as _w2
            _w2.warn(
                "LangGraph: enable_security=True 이지만 보안 트래커가 초기화되지 않았습니다. "
                "_ensure_security_trackers()가 호출되지 않은 것 같습니다.",
                UserWarning,
                stacklevel=3,
            )

        if sanitizer:
            try:
                result = sanitizer.evaluate_input(
                    task_id=self._current_task_id,
                    input_text=input_text,
                )
                if self.verbose:
                    print(f"   ✅ InputSanitization: risk={result.get('risk_level', 'low')}")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        if leakage_det:
            # 최종 응답 + ToolMessage 실행 결과 통합 스캔
            _tool_outputs: List[str] = []
            for step in self._step_tracking:
                for tc in step.get("tool_calls", []):
                    _res = str(tc.get("execution_result", "") or "")
                    if _res:
                        _tool_outputs.append(_res)
            _full_output = response_text
            if _tool_outputs:
                _full_output = response_text + "\n" + "\n".join(_tool_outputs)
            if _full_output:
                try:
                    result = leakage_det.detect_leakage(
                        task_id=self._current_task_id,
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
                        task_id=self._current_task_id,
                        tool_name=tc.get("tool_name", "unknown"),
                        parameters=tc.get("parameters"),
                    )
                except Exception as _e:
                    if self.verbose:
                        print(f"   ⚠️ {_e}")

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
                priv_det.analyze_privilege_chain(
                    task_id=self._current_task_id,
                    tool_calls=_enriched_calls,
                )
                if self.verbose:
                    print(f"   ✅ PrivilegeEscalation: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

        # ToolChainAttackDetector
        chain_det = getattr(self.monitor, "tool_chain_attack_detector", None)
        if chain_det and tool_calls:
            tool_names = [tc.get("tool_name", "unknown") for tc in tool_calls]
            try:
                chain_det.analyze_tool_chain(
                    task_id=self._current_task_id,
                    tool_sequence=tool_names,
                )
                if self.verbose:
                    print(f"   ✅ ToolChainAttack: analyzed")
            except Exception as _e:
                if self.verbose:
                    print(f"   ⚠️ {_e}")

    def run_sync(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,  # Protocol 통일 (LangGraph에서는 미사용)
        **kwargs,
    ) -> Any:
        """run()의 동기 별칭 — EvaluatorProtocol.run_sync() 인터페이스 충족.

        ``user_input`` 은 dict 또는 문자열 모두 허용합니다.
        문자열인 경우 ``to_graph_state()`` 로 그래프 상태 dict로 변환 후 전달합니다.
        """
        from .framework_integrations import to_graph_state
        return self.run(
            to_graph_state(user_input),
            ground_truth=ground_truth,
            expected_tools=expected_tools,
            expected_elements=expected_elements,
            expected_agents=expected_agents,
            **kwargs,
        )

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
                wf = self.monitor.workflow_tracker.calculate_execution_success_rate()
                tool = self.monitor.tool_selection_tracker.get_accuracy_stats()
                tool_eff = self.monitor.tool_analyzer.get_efficiency_stats()
                coord = self.monitor.agent_coordination_tracker.calculate_coordination_score()
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
        self._step_tracking = []
        self._retrieved_contexts = []
        self._global_ai_tool_map = {}
        self._current_task_id = None
        self._current_ground_truth = None

    def track_workflow_step(
        self,
        step_name: str,
        success: bool = True,
        duration: float = 0.0,
        agent_name: str = "",
    ) -> None:
        """워크플로우 단계를 수동으로 추적합니다. 스트림 외부에서 커스텀 노드 스텝을 기록할 때 사용하세요."""
        task_id = self.execution_history[-1]["task_id"] if self.execution_history else "manual"
        self.monitor.workflow_tracker.track_step(
            task_id=task_id,
            step_name=step_name,
            step_type="task_completion",
            success=success,
            execution_time=duration,
            framework="langgraph",
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


def create_evaluated_langgraph(
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> LangGraphEvaluator:
    """LangGraph 평가 워크플로우를 생성하는 편의 함수 (직접 빌드 모드)"""
    return LangGraphEvaluator(
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )


def create_evaluated_langgraph_agent(
    compiled_graph: Any,
    monitor: Optional[PerformanceMonitor] = None,
    enable_layer2: bool = True,
    enable_security: bool = False,
    **kwargs,
) -> LangGraphEvaluator:
    """기존 컴파일된 LangGraph 그래프를 평가 래퍼로 감싸는 편의 함수 (from_compiled 모드).

    다른 프레임워크 팩토리 함수와 동일한 시그니처 패턴:
        create_evaluated_langgraph_agent(compiled_graph, monitor=monitor, ...)

    Args:
        compiled_graph: 컴파일된 LangGraph (CompiledGraph 또는 StateGraph.compile() 결과)
        monitor: 공유 PerformanceMonitor 인스턴스 (None이면 자동 생성)
        enable_layer2: Layer 2 에이전틱 지표 활성화 (기본값 True)
        enable_security: 보안 지표 활성화 (기본값 False)
    """
    evaluator = LangGraphEvaluator(
        monitor=monitor,
        enable_layer2=enable_layer2,
        enable_security=enable_security,
        **kwargs,
    )
    evaluator.set_compiled_graph(compiled_graph)
    return evaluator
