# Multi-Agent System & File Organizer

A comprehensive Python toolkit containing:
1. **Multi-Agent System**: A framework for collaborative AI agents with iterative refinement
2. **File Organizer**: A utility to organize files by various criteria

---

## Multi-Agent System

A sophisticated framework for building collaborative AI agent systems that achieve complex goals through iterative refinement and inter-agent communication.

### Architecture

```
                    ┌─────────────────┐
                    │   Orchestrator  │
                    │  (Coordination) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────────┐    ┌──────────────┐
│  Executor   │───▶│     Critic      │───▶│   Refiner    │
│   Agent     │    │     Agent       │    │    Agent     │
└─────────────┘    └─────────────────┘    └──────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Goal Evaluator  │
                    │    Agent        │
                    └─────────────────┘
```

### Key Features

- **Multiple Agent Roles**: Coordinator, Executor, Critic, Refiner, Goal Evaluator
- **Message-Based Communication**: Typed messages with routing and history
- **Iterative Refinement**: Automatic improvement cycles based on critique
- **Goal Convergence**: Quantitative goal evaluation and convergence detection
- **LLM Integration**: Support for OpenAI, Anthropic, Ollama, and mock providers
- **Extensible Architecture**: Easy to add custom agents and strategies

### Quick Start

```python
from multi_agent_system import CollaborativeProblemSolver

# Create solver with default agents
solver = CollaborativeProblemSolver()

# Solve a problem
result = solver.solve(
    problem="Design a user authentication system",
    objective="Create secure, scalable auth architecture",
    constraints=["Must support OAuth2", "Must handle 1M users"],
    max_iterations=10
)

print(f"Completed in {result['iterations']} iterations")
print(f"Converged: {result['converged']}")
print(f"Result: {result['final_result']}")
```

### Agent Types

#### 1. Coordinator Agent
Orchestrates task decomposition and work distribution.

```python
from multi_agent_system import CoordinatorAgent

coordinator = CoordinatorAgent()
coordinator.set_decomposition_strategy(
    lambda task: [
        ("Step 1: Research", "Gather requirements"),
        ("Step 2: Design", "Create architecture"),
        ("Step 3: Implement", "Build solution")
    ]
)
```

#### 2. Executor Agent
Performs actual task execution.

```python
from multi_agent_system import ExecutorAgent

executor = ExecutorAgent()
executor.set_execution_function(
    lambda task: f"Implemented: {task.objective}"
)
```

#### 3. Critic Agent
Evaluates results and provides feedback.

```python
from multi_agent_system import CriticAgent

critic = CriticAgent()
critic.quality_threshold = 0.85  # Refinement threshold
```

#### 4. Refinement Agent
Improves results based on critique.

```python
from multi_agent_system import RefinementAgent

refiner = RefinementAgent()
refiner.max_refinements = 5  # Prevent infinite loops
```

#### 5. Goal Evaluator Agent
Tracks progress toward goals.

```python
from multi_agent_system import GoalEvaluatorAgent

evaluator = GoalEvaluatorAgent()
evaluator.add_criterion('completeness', lambda r: 0.9 if r else 0.0)
```

### LLM Integration

```python
from llm_integration import LLMConfig, LLMMultiAgentOrchestrator

# Configure LLM provider
config = LLMConfig.openai(model="gpt-4")
# Or: config = LLMConfig.anthropic(model="claude-3-sonnet-20240229")
# Or: config = LLMConfig.ollama(model="llama2")

# Create LLM-powered orchestrator
orchestrator = LLMMultiAgentOrchestrator(
    llm_config=config,
    max_iterations=10
)

# Solve with LLM-powered agents
result = orchestrator.solve(
    problem="Design a REST API",
    objective="Create comprehensive API specification"
)
```

### Custom Agent Example

```python
from multi_agent_system import BaseAgent, Message, MessageType

class SecurityAuditorAgent(BaseAgent):
    """Custom agent for security auditing."""

    def __init__(self):
        super().__init__(
            name="SecurityAuditor",
            capabilities=['security_audit', 'vulnerability_scan']
        )

    def process_message(self, message: Message):
        if message.type == MessageType.RESULT:
            # Audit the result for security issues
            issues = self._scan_for_vulnerabilities(message.content)

            return self.send_message(
                MessageType.CRITIQUE,
                {
                    'security_issues': issues,
                    'severity': self._calculate_severity(issues)
                },
                reply_to=message.id
            )
        return None

    def _scan_for_vulnerabilities(self, content):
        # Implement security scanning logic
        return []

    def _calculate_severity(self, issues):
        return 'low' if not issues else 'high'
```

### Message Types

| Type | Description |
|------|-------------|
| `TASK` | New task assignment |
| `RESULT` | Task execution result |
| `CRITIQUE` | Feedback on result |
| `REFINEMENT` | Improved version |
| `QUERY` | Information request |
| `RESPONSE` | Query response |
| `STATUS` | Status update |
| `TERMINATION` | Stop signal |

### Iteration Flow

```
1. Task arrives → Coordinator decomposes
2. Executor executes subtasks
3. Critic evaluates results
4. If score < threshold:
   └── Refiner improves result
   └── Go to step 3
5. Goal Evaluator checks convergence
6. If not converged and iterations < max:
   └── Go to step 2
7. Return final result
```

### Running Tests

```bash
# Run all tests
python -m pytest test_multi_agent.py -v

# Run with coverage
python -m pytest test_multi_agent.py --cov=multi_agent_system --cov-report=html
```

### Demo

```bash
# Run the demonstration
python multi_agent_system.py

# Run LLM integration demo
python llm_integration.py
```

---

## File Organizer

A simple yet powerful Python utility to organize files in directories by various criteria.

### Features

- **Organize by Extension**: Categorizes files into folders (Images, Documents, Code, etc.)
- **Organize by Date**: Groups files by modification date (YYYY/Month folders)
- **Organize by Size**: Sorts files into Small/Medium/Large categories
- **Dry-run Mode**: Preview changes before applying them
- **Custom Categories**: Define your own file type categories via JSON config

### Usage

```bash
# Organize by file extension
python file_organizer.py /path/to/directory --by-extension

# Organize by modification date
python file_organizer.py /path/to/directory --by-date

# Organize by file size
python file_organizer.py /path/to/directory --by-size

# Preview changes first
python file_organizer.py /path/to/directory --by-extension --dry-run

# Use custom categories
python file_organizer.py /path/to/directory --by-extension --config my_categories.json
```

### Default Categories

- **Images**: jpg, jpeg, png, gif, bmp, svg, webp, ico
- **Documents**: pdf, doc, docx, txt, odt, rtf, tex, md
- **Spreadsheets**: xls, xlsx, csv, ods
- **Presentations**: ppt, pptx, odp
- **Videos**: mp4, avi, mkv, mov, flv, wmv, webm
- **Audio**: mp3, wav, flac, aac, ogg, wma, m4a
- **Archives**: zip, rar, 7z, tar, gz, bz2, xz
- **Code**: py, js, java, cpp, c, h, hpp, cs, go, rs, rb
- **Web**: html, css, scss, sass, xml, json, yaml, yml
- **Executables**: exe, dll, so, dylib, app, deb, rpm
- **Fonts**: ttf, otf, woff, woff2, eot

---

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd yz_zhang

# Install dependencies (optional, for LLM integration)
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Requirements

- Python 3.8+
- Core: Standard library only
- LLM Integration: `httpx>=0.24.0`

## Project Structure

```
yz_zhang/
├── multi_agent_system.py    # Core multi-agent framework
├── llm_integration.py       # LLM adapter and integration
├── test_multi_agent.py      # Test suite
├── file_organizer.py        # File organization utility
├── example_config.json      # Example configuration
├── requirements.txt         # Dependencies
└── README.md               # This file
```

## License

MIT License - Feel free to use and modify as needed.

## Critical Review: Design Decisions

### Strengths
1. **Modular Architecture**: Clean separation of concerns with specialized agents
2. **Type Safety**: Extensive use of dataclasses and type hints
3. **Extensibility**: Easy to add custom agents and strategies
4. **Observable**: Comprehensive logging and metrics collection
5. **Testable**: Mock adapters enable testing without external dependencies

### Potential Improvements
1. **Async Support**: Could benefit from async/await for concurrent agent execution
2. **Persistence**: Add state serialization for long-running tasks
3. **Distributed Execution**: Support for running agents across multiple processes
4. **Advanced Routing**: More sophisticated message routing algorithms
5. **Backpressure**: Queue size limits and flow control

### Trade-offs
- Chose simplicity over maximum performance (synchronous execution)
- Prioritized readability over code brevity
- Used composition over inheritance where possible
