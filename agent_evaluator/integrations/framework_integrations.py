"""
Framework Integration Utility Functions
========================================
Provides utility functions for checking framework availability and installation instructions.

v0.5.0: Deprecated legacy classes have been removed.
All evaluation classes have been moved to dedicated integration modules:
- crewai_integration.py: CrewAIEvaluator
- langchain_integration.py: LangChainEvaluator, AdvancedLangChainCallback
- langgraph_integration.py: LangGraphEvaluator
- autogen_integration.py: AutoGenEvaluator
"""

from typing import Any, Dict, List, Optional, Union


# ==============================================================================
# Input Type Adapters — framework-agnostic 변환 헬퍼
# ==============================================================================

def to_graph_state(
    user_input: Any,
    messages_key: str = "messages",
) -> Dict[str, Any]:
    """문자열 또는 dict 입력을 LangGraph 그래프 상태 dict로 변환합니다.

    Args:
        user_input: 문자열 질문 또는 이미 구성된 상태 dict
        messages_key: 메시지 리스트를 담을 상태 키 (기본값: "messages")

    Returns:
        LangGraph ``run()`` 에 전달 가능한 상태 dict

    Examples:
        >>> to_graph_state("AI는 무엇인가?")
        {"messages": [HumanMessage(content="AI는 무엇인가?")]}

        >>> to_graph_state({"messages": [...], "context": "..."})  # 그대로 반환
        {"messages": [...], "context": "..."}
    """
    if isinstance(user_input, dict):
        # messages 키가 있으면 list/tuple 여부 검증
        if messages_key in user_input and not isinstance(user_input[messages_key], (list, tuple)):
            raise TypeError(
                f"to_graph_state: '{messages_key}' must be a list/tuple, "
                f"got {type(user_input[messages_key]).__name__}. "
                "Pass a plain string to have it wrapped automatically."
            )
        return user_input
    content = str(user_input)
    try:
        from langchain_core.messages import HumanMessage
        return {messages_key: [HumanMessage(content=content)]}
    except ImportError:
        return {messages_key: [{"role": "user", "content": content}]}


def to_crew_inputs(
    user_input: Any,
    input_key: str = "input",
) -> Dict[str, Any]:
    """문자열 또는 dict 입력을 CrewAI ``kickoff(inputs=...)`` 형식으로 변환합니다.

    Args:
        user_input: 문자열 질문 또는 이미 구성된 inputs dict
        input_key: 문자열 입력을 담을 dict 키 (기본값: "input")

    Returns:
        CrewAI ``kickoff(inputs=...)`` 에 전달 가능한 dict

    Examples:
        >>> to_crew_inputs("AI 트렌드를 분석해줘")
        {"input": "AI 트렌드를 분석해줘"}

        >>> to_crew_inputs({"topic": "AI", "style": "formal"})  # 그대로 반환
        {"topic": "AI", "style": "formal"}
    """
    if isinstance(user_input, dict):
        return user_input
    return {input_key: str(user_input)}


def to_task_string(user_input: Any) -> str:
    """다양한 입력 타입에서 태스크 문자열을 추출합니다.

    LangChain/AutoGen 처럼 단순 문자열 입력을 기대하는 프레임워크에
    LangGraph/CrewAI 용 dict 입력이 전달된 경우에도 올바른 문자열을 추출합니다.

    Args:
        user_input: 문자열, dict (messages/input/query 키), 또는 임의 타입

    Returns:
        태스크 문자열

    Examples:
        >>> to_task_string("What is AI?")
        "What is AI?"

        >>> to_task_string({"input": "AI란?", "style": "formal"})
        "AI란?"

        >>> to_task_string({"messages": [HumanMessage(content="Hello")]})
        "Hello"
    """
    if isinstance(user_input, str):
        return user_input
    if isinstance(user_input, dict):
        for key in ("input", "query", "question", "task", "message", "content"):
            if key in user_input and user_input[key]:
                return str(user_input[key])
        msgs = user_input.get("messages") or []
        if msgs:
            last = msgs[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))
            return str(getattr(last, "content", last))
    return str(user_input)


# ==============================================================================
# Utility Functions
# ==============================================================================

def check_framework_availability(framework: str = None) -> Dict[str, bool]:
    """
    Check availability of AI frameworks

    Args:
        framework: Specific framework to check (langchain, langgraph, crewai, autogen)
                  If None, checks all frameworks

    Returns:
        Dictionary with framework availability status

    Example:
        >>> from agent_evaluator.integrations import check_framework_availability
        >>> status = check_framework_availability()
        >>> print(status)
        {'langchain': True, 'langgraph': False, 'crewai': True, 'autogen': False}

        >>> # Check specific framework
        >>> if check_framework_availability('langchain')['langchain']:
        ...     print("LangChain is available!")
    """
    frameworks = {
        'langchain': False,
        'langgraph': False,
        'crewai': False,
        'autogen': False
    }

    # Check LangChain
    try:
        import langchain
        frameworks['langchain'] = True
    except ImportError:
        pass

    # Check LangGraph
    try:
        import langgraph
        frameworks['langgraph'] = True
    except ImportError:
        pass

    # Check CrewAI
    try:
        import crewai
        frameworks['crewai'] = True
    except ImportError:
        pass

    # Check AutoGen — autogen-agentchat (0.4+) 우선, 레거시 pyautogen fallback
    try:
        import autogen_agentchat  # noqa: F401
        frameworks['autogen'] = True
    except ImportError:
        try:
            import autogen  # noqa: F401 — legacy pyautogen
            frameworks['autogen'] = True
        except ImportError:
            pass

    if framework:
        return {framework: frameworks.get(framework, False)}

    return frameworks


def get_installation_instructions(framework: str) -> str:
    """
    Get installation instructions for a specific framework

    Args:
        framework: Framework name (langchain, langgraph, crewai, autogen)

    Returns:
        Installation instructions as a string

    Example:
        >>> from agent_evaluator.integrations import get_installation_instructions
        >>> print(get_installation_instructions('langchain'))
        Install LangChain with:
            pip install langchain langchain-core langchain-community

        Documentation: https://python.langchain.com/docs/get_started/installation
    """
    instructions = {
        'langchain': """Install LangChain with:
    pip install langchain langchain-core langchain-community

Documentation: https://python.langchain.com/docs/get_started/installation

For Agent Evaluator integration:
    from agent_evaluator.integrations import LangChainEvaluator, AdvancedLangChainCallback

    evaluator = LangChainEvaluator(agent, enable_layer2=True)
    result = evaluator.run(query="...", ground_truth="...")""",

        'langgraph': """Install LangGraph with:
    pip install langgraph

Documentation: https://python.langchain.com/docs/langgraph

For Agent Evaluator integration:
    from agent_evaluator.integrations import LangGraphEvaluator

    evaluator = LangGraphEvaluator(graph, enable_layer2=True)
    result = evaluator.run(inputs={...}, ground_truth="...")""",

        'crewai': """Install CrewAI with:
    pip install crewai crewai-tools

Documentation: https://docs.crewai.com/

For Agent Evaluator integration:
    from agent_evaluator.integrations import CrewAIEvaluator

    evaluator = CrewAIEvaluator(crew, enable_layer2=True)
    result = evaluator.kickoff(inputs={...}, ground_truth="...")""",

        'autogen': """Install AutoGen with:
    pip install autogen-agentchat autogen-core autogen-ext

Documentation: https://microsoft.github.io/autogen/

For Agent Evaluator integration:
    from agent_evaluator.integrations import AutoGenEvaluator

    evaluator = AutoGenEvaluator(agent, enable_layer2=True)
    result = evaluator.run_sync("질문", ground_truth="...")

Note: autogen-agentchat >= 0.4.0 (async-first API) 필요.
      레거시 pyautogen (0.2.x/0.3.x) 은 동기 API라 run_sync() 없이도 사용 가능하나
      ToolCallRequestEvent 기반 도구 추적은 0.4+ 에서만 동작합니다."""
    }

    return instructions.get(framework.lower(), f"Unknown framework: {framework}")


def print_framework_status():
    """
    Print a formatted status report of all frameworks

    Example:
        >>> from agent_evaluator.integrations import print_framework_status
        >>> print_framework_status()

        Framework Availability Status:
        ===============================
        ✅ LangChain: Available
        ❌ LangGraph: Not installed
        ✅ CrewAI: Available
        ❌ AutoGen: Not installed

        To install missing frameworks, use get_installation_instructions()
    """
    status = check_framework_availability()

    print("\nFramework Availability Status:")
    print("=" * 40)

    framework_names = {
        'langchain': 'LangChain',
        'langgraph': 'LangGraph',
        'crewai': 'CrewAI',
        'autogen': 'AutoGen'
    }

    for fw, available in status.items():
        icon = "✅" if available else "❌"
        status_text = "Available" if available else "Not installed"
        print(f"{icon} {framework_names[fw]}: {status_text}")

    print("\nTo install missing frameworks, use:")
    print("  from agent_evaluator.integrations import get_installation_instructions")
    print("  print(get_installation_instructions('framework_name'))")


# ==============================================================================
# EvaluatorProtocol — framework-agnostic type interface
# ==============================================================================

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # Python 3.7 fallback
    from typing_extensions import Protocol, runtime_checkable  # type: ignore[assignment]


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """4개 프레임워크 평가기가 공통으로 구현하는 인터페이스.

    실행 메서드(run/kickoff)는 프레임워크마다 입력 타입이 다르므로
    ``run_sync`` 로 통일한 동기 실행 진입점을 제공합니다.

    Usage::

        from agent_evaluator import EvaluatorProtocol

        def evaluate(evaluator: EvaluatorProtocol, user_input, **kw):
            result = evaluator.run_sync(user_input, **kw)
            report = evaluator.generate_report()
            stats  = evaluator.monitor.tool_analyzer.get_efficiency_stats()
            return report, stats

        # 4개 프레임워크 모두 동일하게 동작
        evaluate(lc_evaluator,  "What is AI?",            ground_truth="...")
        evaluate(lg_evaluator,  {"messages": [...]},       ground_truth="...")
        evaluate(crew_evaluator,{"topic": "AI"},           ground_truth="...")
        evaluate(ag_evaluator,  "What is AI?",             ground_truth="...")
    """

    @property
    def monitor(self) -> Any:
        """공유 PerformanceMonitor 인스턴스"""
        ...

    def run_sync(
        self,
        user_input: Any,
        ground_truth: Optional[str] = None,
        expected_tools: Optional[List[str]] = None,
        expected_elements: Optional[List[str]] = None,
        expected_agents: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """동기 실행 진입점 (프레임워크 무관 통일 인터페이스).

        ``user_input`` 은 프레임워크에 따라 자동 변환됩니다:
        - LangChain/AutoGen: 문자열로 처리 (``to_task_string()`` 적용)
        - LangGraph: dict 그래프 상태로 처리 (``to_graph_state()`` 적용)
        - CrewAI: inputs dict로 처리 (``to_crew_inputs()`` 적용)

        ``expected_agents`` 는 CrewAI 에서만 활성화됩니다.
        다른 프레임워크에서는 무시됩니다.

        **예외 처리 동작 (프레임워크별 차이):**
        - LangChain: 실행 중 예외가 ``run_sync()`` 호출자까지 전파됩니다.
          단, 예외 발생 전까지 수집된 메트릭(토큰, 도구 등)은 monitor에 보존됩니다.
        - LangGraph / CrewAI / AutoGen: 예외를 내부에서 억제하고,
          ``success=False`` 로 TaskResult를 기록한 뒤 빈 결과를 반환합니다.
          예외 정보는 ``monitor`` 의 태스크 기록에서 확인할 수 있습니다.
        """
        ...

    def generate_report(self, output_path: Optional[str] = None) -> Any:
        """평가 리포트 생성 (모든 프레임워크 동일 시그니처)"""
        ...


# ==============================================================================
# Shared Security Tracker Initializer — 4개 framework adapter 공통 로직
# ==============================================================================

def ensure_security_trackers(
    monitor: Any,
    privilege_registry: Optional[Dict[str, Any]] = None,
) -> None:
    """monitor에 보안 트래커가 없으면 자동 초기화합니다.

    4개 framework integration(LangChain/LangGraph/CrewAI/AutoGen) 공통 로직.
    각 파일의 중복 구현을 제거하고 이 단일 함수를 사용합니다.

    Args:
        monitor: PerformanceMonitor 인스턴스
        privilege_registry: tool_name → privilege_level 매핑 dict.
            제공 시 키워드 휴리스틱보다 우선 적용됩니다.
    """
    import warnings as _w
    from agent_evaluator.core.trackers.security import (
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
    monitor.enable_security_metrics = True
    if privilege_registry and not getattr(monitor, "privilege_registry", None):
        monitor.privilege_registry = privilege_registry
    elif not getattr(monitor, "privilege_registry", None):
        monitor.privilege_registry = {}
    if (not getattr(monitor, "_authorized_tools", None)
            and not getattr(monitor, "__auth_warned__", False)):
        monitor.__auth_warned__ = True
        _w.warn(
            "ToolAuthorizationTracker: authorized_tools not set — "
            "all tool calls will pass authorization. "
            "Pass authorized_tools=['tool_a', 'tool_b'] to the evaluator "
            "for meaningful security metrics.",
            UserWarning,
            stacklevel=3,
        )
    if not privilege_registry and not getattr(monitor, "privilege_registry", {}).get("__configured__"):
        monitor.privilege_registry["__configured__"] = True
        _w.warn(
            "PrivilegeEscalationDetector: privilege_registry not configured — "
            "using keyword heuristic only. "
            "Pass privilege_registry={'tool_name': 'admin|write|read'} for accurate detection.",
            UserWarning,
            stacklevel=3,
        )


def extract_tools_from_framework_object(obj: Any) -> List[str]:
    """프레임워크 객체에서 등록된 도구 이름 목록을 자동 추출합니다.

    4개 framework 공통 헬퍼. 각 wrapper의 __init__에서 authorized_tools 미제공 시
    호출해 ToolAuthorizationTracker whitelist를 자동 구성합니다.

    지원 경로:
    - LangChain AgentExecutor: .tools 리스트
    - LangChain LCEL Runnable: .runnable.tools / .bound.tools
    - LangGraph compiled graph: .nodes 내 바인딩 도구
    - CrewAI Crew: .agents[i].tools
    - AutoGen AssistantAgent: ._tools / .registered_tools / ._tool_definitions
    - AutoGen Team: ._participants[i] 재귀 탐색

    Args:
        obj: 프레임워크 에이전트/팀/그래프 객체

    Returns:
        도구 이름 문자열 리스트 (중복 제거, 빈 이름 제외)
    """
    tool_names: List[str] = []
    seen: set = set()

    def _add(name: str) -> None:
        n = (name or "").strip()
        if n and n not in seen:
            seen.add(n)
            tool_names.append(n)

    def _extract_from_tool(tool: Any) -> None:
        name = (
            getattr(tool, "name", None)
            or getattr(tool, "tool_name", None)
            or (tool if isinstance(tool, str) else None)
        )
        if name:
            _add(str(name))

    def _extract_tools_list(tools_list: Any) -> None:
        if not tools_list:
            return
        for t in tools_list:
            _extract_from_tool(t)

    # ── LangChain AgentExecutor / LCEL ────────────────────────────────
    _extract_tools_list(getattr(obj, "tools", None))
    _extract_tools_list(getattr(getattr(obj, "runnable", None), "tools", None))
    _extract_tools_list(getattr(getattr(obj, "bound", None), "tools", None))

    # ── LangGraph CompiledGraph: node 내 bound tools ──────────────────
    nodes = getattr(obj, "nodes", None)
    if isinstance(nodes, dict):
        for node_val in nodes.values():
            _extract_tools_list(getattr(node_val, "tools", None))
            bound = getattr(node_val, "bound", None)
            if bound:
                _extract_tools_list(getattr(bound, "tools", None))

    # ── CrewAI Crew: agents[i].tools ─────────────────────────────────
    for agent in getattr(obj, "agents", []) or []:
        _extract_tools_list(getattr(agent, "tools", None))

    # ── AutoGen single agent ──────────────────────────────────────────
    for attr in ("_tools", "registered_tools", "_tool_definitions", "tools"):
        _extract_tools_list(getattr(obj, attr, None))

    # ── AutoGen team: _participants 재귀 ─────────────────────────────
    for participant in getattr(obj, "_participants", []) or []:
        for attr in ("_tools", "registered_tools", "tools"):
            _extract_tools_list(getattr(participant, attr, None))

    return tool_names


# ==============================================================================
# Security helpers — shared across all framework adapters
# ==============================================================================

def infer_privilege_level(tool_name: str) -> str:
    """도구 이름 기반 권한 수준 추론 (PrivilegeEscalationDetector용 공유 헬퍼).

    DQ-124: CrewAI에만 있던 로직을 공유 유틸리티로 분리 —
    LangChain / LangGraph / AutoGen 어댑터에서도 동일 휴리스틱 사용.

    Returns:
        "admin" | "write" | "read"
    """
    _tn = (tool_name or "").lower()
    if any(k in _tn for k in (
        "delete", "drop", "remove", "exec", "system", "admin", "root",
        "sudo", "kill", "purge", "destroy", "truncate", "revoke", "chmod", "export",
    )):
        return "admin"
    if any(k in _tn for k in (
        "write", "update", "create", "modify", "insert", "post", "put",
        "patch", "upload", "save", "backup", "sync", "push", "migrate",
    )):
        return "write"
    return "read"


# ==============================================================================
# Module exports
# ==============================================================================

__all__ = [
    # Protocol
    'EvaluatorProtocol',
    # Input adapters
    'to_graph_state',
    'to_crew_inputs',
    'to_task_string',
    # Utilities
    'check_framework_availability',
    'get_installation_instructions',
    'print_framework_status',
    # Security helpers
    'infer_privilege_level',
    'ensure_security_trackers',
    'extract_tools_from_framework_object',
]
