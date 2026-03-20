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

from typing import Dict


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

    # Check AutoGen
    try:
        import autogen
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
    pip install pyautogen

Documentation: https://microsoft.github.io/autogen/

For Agent Evaluator integration:
    from agent_evaluator.integrations import AutoGenEvaluator

    evaluator = AutoGenEvaluator(agent, enable_layer2=True)
    result = evaluator.run(message="...", ground_truth="...")"""
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
# Module exports
# ==============================================================================

__all__ = [
    'check_framework_availability',
    'get_installation_instructions',
    'print_framework_status',
]
