# Agent Evaluator

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.5.0-green.svg)](https://github.com/yourusername/agent-evaluator)

**Production-ready evaluation framework for AI agents**

A comprehensive Python framework for evaluating, monitoring, and optimizing AI agent performance with support for multiple frameworks including LangChain, CrewAI, AutoGen, and LangGraph.

## Features

### Core Capabilities

- **Performance Monitoring**: Track task completion rates, accuracy, latency, and token usage
- **Quality Evaluation**: Detect hallucinations, evaluate response quality, and measure accuracy
- **Multi-Agent Support**: Monitor agent coordination, workflow execution, and tool selection
- **Security Metrics**: Track input sanitization, output leakage, privilege escalation, and tool chain attacks
- **Framework Integration**: Built-in support for LangChain, CrewAI, AutoGen, and LangGraph
- **Interactive Dashboard**: Visualize metrics and evaluation results with Streamlit

### Key Metrics

**Layer 1 - Foundation Metrics**
- Task Completion Rate (TCR)
- Accuracy Evaluation
- Hallucination Detection
- Response Quality Assessment
- Latency Tracking
- Token Economy Analysis

**Layer 2 - Advanced Metrics**
- Tool Call Analysis
- Retry & Correction Tracking
- Tool Selection Optimization
- Agent Coordination Monitoring
- Workflow Execution Analysis

**Layer 3 - Production Metrics**
- Security Monitoring
- Cost Optimization
- Transparency & Explainability
- Framework-specific Integration

## Installation

### Basic Installation

```bash
pip install agent-evaluator
```

### With Optional Dependencies

```bash
# Install with DeepEval support
pip install agent-evaluator[deepeval]

# Install with RAGAS support
pip install agent-evaluator[ragas]

# Install with LangChain support
pip install agent-evaluator[langchain]

# Install all optional dependencies
pip install agent-evaluator[all]
```

### From Source

```bash
git clone https://github.com/yourusername/agent-evaluator.git
cd agent-evaluator
pip install -e .
```

## Quick Start

### Basic Usage

```python
from agent_evaluator import PerformanceMonitor, create_taskresult

# Create a performance monitor
monitor = PerformanceMonitor()

# Create and record a task
task = create_taskresult(
    task_id="task_001",
    question="What is the capital of France?",
    response="Paris",
    ground_truth="Paris",
    execution_time=1.2
)

monitor.record_task(task)

# Save results with comprehensive report
monitor.save_to_file("results.json")
```

### Using Context Manager

```python
from agent_evaluator import evaluation_session, create_taskresult

with evaluation_session("results.json") as monitor:
    task = create_taskresult(
        task_id="task_001",
        question="What is AI?",
        response="Artificial Intelligence...",
        ground_truth="AI is...",
        execution_time=2.5
    )
    monitor.record_task(task)
# Results are automatically saved!
```

### LLM Integration

```python
from agent_evaluator import PerformanceMonitor, LLMHelper

monitor = PerformanceMonitor()
llm = LLMHelper(monitor)

# Evaluate with OpenAI
task = llm.evaluate_openai(
    task_id="qa_001",
    prompt="What is machine learning?",
    ground_truth="Machine learning is..."
)
# Automatically recorded in monitor!
```

## Framework Integration

### LangChain

```python
from agent_evaluator.integrations import LangChainIntegration

integration = LangChainIntegration(monitor)
# Automatically tracks LangChain agent execution
```

### CrewAI

```python
from agent_evaluator.integrations import CrewAIIntegration

integration = CrewAIIntegration(monitor)
# Monitors CrewAI crew execution
```

### LangGraph

```python
from agent_evaluator.integrations import LangGraphIntegration

integration = LangGraphIntegration(monitor)
# Tracks LangGraph workflow execution
```

## Dashboard

Launch the interactive dashboard to visualize evaluation results:

```bash
cd Evaluator_Examples/Dashboard
streamlit run dashboard_data_editor.py
```

The dashboard provides:
- Overview statistics
- Core metrics visualization
- Advanced metrics analysis
- Security monitoring
- Cost analysis
- Detailed task inspection

## Examples

The project includes comprehensive examples organized by difficulty level:

### Level 1: Foundation (5-10 minutes)
- `01_quickstart.py` - Basic workflow introduction
- `02_layer1_trackers.py` - Foundation metrics
- `03_taskresult_helpers.py` - Helper functions
- `04_thresholds_validation.py` - Quality thresholds
- `05_layer1_security_basic.py` - Basic security metrics

### Level 2: Advanced (15-30 minutes)
- `01_golden_dataset.py` - Dataset creation and evaluation
- `02_layer3_hybrid.py` - Hybrid evaluation with external libraries
- `03_rag_system.py` - RAG system evaluation
- `04_tool_selection.py` - Tool selection optimization
- `05_multi_agent.py` - Multi-agent coordination
- `06_workflow.py` - Complex workflow tracking

### Level 3: Production (30+ minutes)
- `01_framework_crewai.py` - CrewAI integration
- `02_cost_optimization.py` - Cost optimization strategies
- `03_framework_langchain.py` - LangChain integration
- `04_framework_langgraph.py` - LangGraph integration
- `05_transparency.py` - Explainability and transparency

Run examples:

```bash
cd Evaluator_Examples
python level_1_foundation/01_quickstart.py
```

## Project Structure

```
agent-evaluator/
├── agent_evaluator/
│   ├── core/                 # Core monitoring and evaluation
│   ├── datasets/             # Dataset generation utilities
│   ├── helpers/              # Helper functions
│   ├── integrations/         # Framework integrations
│   ├── reporting/            # Report generation
│   └── utils/                # Utility functions
├── Evaluator_Examples/
│   ├── level_1_foundation/   # Basic examples
│   ├── level_2_advanced/     # Advanced examples
│   ├── level_3_production/   # Production examples
│   └── Dashboard/            # Interactive dashboard
├── Docs/                     # Documentation
└── tests/                    # Unit tests
```

## Requirements

- Python >= 3.8
- numpy >= 1.20.0, < 2.0.0
- pandas >= 1.3.0
- python-dotenv >= 0.19.0

### Optional Dependencies

- deepeval >= 0.20.0 (for advanced evaluation)
- ragas >= 0.1.0 (for RAG evaluation)
- langchain >= 0.1.0 (for LangChain integration)

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/agent-evaluator.git
cd agent-evaluator

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=agent_evaluator --cov-report=html
```

### Code Quality

```bash
# Format code
black agent_evaluator/

# Check style
flake8 agent_evaluator/

# Type checking
mypy agent_evaluator/
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Sungwoo Kim**
- Email: sungwoo.kim@gmail.com

## Citation

If you use Agent Evaluator in your research or project, please cite:

```bibtex
@software{agent_evaluator,
  title = {Agent Evaluator: Production-ready evaluation framework for AI agents},
  author = {Kim, Sungwoo},
  year = {2024},
  version = {0.5.0},
  url = {https://github.com/yourusername/agent-evaluator}
}
```

## Acknowledgments

- Built with support for DeepEval, RAGAS, LangChain, CrewAI, AutoGen, and LangGraph
- Inspired by the need for comprehensive AI agent evaluation in production environments

## Support

- Documentation: [Docs/](Docs/)
- Issues: [GitHub Issues](https://github.com/yourusername/agent-evaluator/issues)
- Examples: [Evaluator_Examples/](Evaluator_Examples/)

---

Made with ❤️ for the AI Agent community
