#!/usr/bin/env python3
"""
LLM Integration Module for Multi-Agent System.

Provides adapters for integrating Large Language Models as the "brain"
of agents, enabling intelligent task execution, evaluation, and refinement.

Supports:
- OpenAI API (GPT-4, GPT-3.5)
- Anthropic API (Claude)
- Local models via Ollama
- Mock LLM for testing

Architecture:
    Agent <-> LLMAdapter <-> External LLM API
                  |
                  v
            Response Parser
"""

from __future__ import annotations

import os
import json
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from enum import Enum, auto
import hashlib

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from multi_agent_system import (
    BaseAgent, Task, ExecutionResult, Critique, Message, MessageType,
    ExecutorAgent, CriticAgent, GoalEvaluatorAgent, GoalEvaluation, GoalStatus
)

logger = logging.getLogger(__name__)


# =============================================================================
# LLM Configuration
# =============================================================================

class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = auto()
    ANTHROPIC = auto()
    OLLAMA = auto()
    MOCK = auto()


@dataclass
class LLMConfig:
    """Configuration for LLM connection."""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: float = 60.0
    retry_count: int = 3
    retry_delay: float = 1.0

    @classmethod
    def openai(cls, model: str = "gpt-4", api_key: Optional[str] = None) -> 'LLMConfig':
        return cls(
            provider=LLMProvider.OPENAI,
            model=model,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1"
        )

    @classmethod
    def anthropic(cls, model: str = "claude-3-sonnet-20240229", api_key: Optional[str] = None) -> 'LLMConfig':
        return cls(
            provider=LLMProvider.ANTHROPIC,
            model=model,
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            base_url="https://api.anthropic.com/v1"
        )

    @classmethod
    def ollama(cls, model: str = "llama2", base_url: str = "http://localhost:11434") -> 'LLMConfig':
        return cls(
            provider=LLMProvider.OLLAMA,
            model=model,
            base_url=base_url
        )

    @classmethod
    def mock(cls) -> 'LLMConfig':
        return cls(
            provider=LLMProvider.MOCK,
            model="mock"
        )


# =============================================================================
# LLM Adapter Interface
# =============================================================================

class LLMAdapter(ABC):
    """Abstract base class for LLM adapters."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.call_count = 0
        self.total_tokens = 0
        self.cache: Dict[str, str] = {}

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion for the given prompt."""
        pass

    def complete_with_cache(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion with caching."""
        cache_key = hashlib.md5(
            f"{prompt}:{system_prompt}:{json.dumps(kwargs, sort_keys=True)}".encode()
        ).hexdigest()

        if cache_key in self.cache:
            logger.debug("Cache hit")
            return self.cache[cache_key]

        result = self.complete(prompt, system_prompt, **kwargs)
        self.cache[cache_key] = result
        return result

    def get_metrics(self) -> Dict[str, Any]:
        """Get usage metrics."""
        return {
            'call_count': self.call_count,
            'total_tokens': self.total_tokens,
            'cache_size': len(self.cache)
        }


# =============================================================================
# Concrete LLM Adapters
# =============================================================================

class MockLLMAdapter(LLMAdapter):
    """Mock LLM adapter for testing without API calls."""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config or LLMConfig.mock())
        self.responses: List[str] = []
        self.response_index = 0

    def add_response(self, response: str) -> None:
        """Add a predefined response."""
        self.responses.append(response)

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Return mock response."""
        self.call_count += 1

        if self.responses:
            response = self.responses[self.response_index % len(self.responses)]
            self.response_index += 1
            return response

        # Generate contextual mock response
        if "critique" in prompt.lower() or "evaluate" in prompt.lower():
            return json.dumps({
                "score": 0.75,
                "strengths": ["Well-structured approach", "Clear reasoning"],
                "weaknesses": ["Could be more detailed"],
                "suggestions": ["Add more examples", "Consider edge cases"],
                "should_refine": True
            })
        elif "refine" in prompt.lower() or "improve" in prompt.lower():
            return "Refined output with improvements based on feedback: Added more detail and examples."
        elif "goal" in prompt.lower() or "progress" in prompt.lower():
            return json.dumps({
                "status": "IN_PROGRESS",
                "progress": 70,
                "gaps": ["Need more testing"],
                "recommendation": "Continue refinement"
            })
        else:
            return f"Executed task based on: {prompt[:100]}..."


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI API."""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config or LLMConfig.openai())
        if not HAS_HTTPX:
            raise ImportError("httpx is required for OpenAI adapter. Install with: pip install httpx")

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Call OpenAI API."""
        self.call_count += 1

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
        }

        for attempt in range(self.config.retry_count):
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    response = client.post(
                        f"{self.config.base_url}/chat/completions",
                        headers=headers,
                        json=data
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Track tokens
                    if "usage" in result:
                        self.total_tokens += result["usage"].get("total_tokens", 0)

                    return result["choices"][0]["message"]["content"]

            except Exception as e:
                logger.warning(f"OpenAI API call failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.retry_count - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise

        return ""


class AnthropicAdapter(LLMAdapter):
    """Adapter for Anthropic Claude API."""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config or LLMConfig.anthropic())
        if not HAS_HTTPX:
            raise ImportError("httpx is required for Anthropic adapter. Install with: pip install httpx")

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Call Anthropic API."""
        self.call_count += 1

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": [{"role": "user", "content": prompt}]
        }

        if system_prompt:
            data["system"] = system_prompt

        for attempt in range(self.config.retry_count):
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    response = client.post(
                        f"{self.config.base_url}/messages",
                        headers=headers,
                        json=data
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Track tokens
                    if "usage" in result:
                        self.total_tokens += result["usage"].get("input_tokens", 0)
                        self.total_tokens += result["usage"].get("output_tokens", 0)

                    return result["content"][0]["text"]

            except Exception as e:
                logger.warning(f"Anthropic API call failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.retry_count - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise

        return ""


class OllamaAdapter(LLMAdapter):
    """Adapter for local Ollama models."""

    def __init__(self, config: Optional[LLMConfig] = None):
        super().__init__(config or LLMConfig.ollama())
        if not HAS_HTTPX:
            raise ImportError("httpx is required for Ollama adapter. Install with: pip install httpx")

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Call Ollama API."""
        self.call_count += 1

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"

        data = {
            "model": self.config.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature)
            }
        }

        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                response = client.post(
                    f"{self.config.base_url}/api/generate",
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")

        except Exception as e:
            logger.error(f"Ollama API call failed: {e}")
            raise


def create_adapter(config: LLMConfig) -> LLMAdapter:
    """Factory function to create appropriate adapter."""
    adapters = {
        LLMProvider.OPENAI: OpenAIAdapter,
        LLMProvider.ANTHROPIC: AnthropicAdapter,
        LLMProvider.OLLAMA: OllamaAdapter,
        LLMProvider.MOCK: MockLLMAdapter
    }

    adapter_class = adapters.get(config.provider)
    if not adapter_class:
        raise ValueError(f"Unsupported provider: {config.provider}")

    return adapter_class(config)


# =============================================================================
# LLM-Powered Agents
# =============================================================================

class LLMExecutorAgent(ExecutorAgent):
    """Executor agent powered by an LLM."""

    def __init__(
        self,
        name: str = "LLMExecutor",
        llm_adapter: Optional[LLMAdapter] = None
    ):
        super().__init__(name)
        self.llm = llm_adapter or MockLLMAdapter()
        self.system_prompt = """You are an expert task executor. Your job is to:
1. Understand the given task and its objectives
2. Execute the task step by step
3. Provide clear, structured output
4. Explain your reasoning

Be thorough but concise. Focus on achieving the objective."""

    def _default_execution(self, task: Task) -> Any:
        """Execute task using LLM."""
        prompt = f"""Task: {task.description}

Objective: {task.objective}

Constraints:
{chr(10).join(f'- {c}' for c in task.constraints) if task.constraints else 'None'}

Please execute this task and provide your output. Include your reasoning."""

        response = self.llm.complete(prompt, self.system_prompt)
        return response


class LLMCriticAgent(CriticAgent):
    """Critic agent powered by an LLM."""

    def __init__(
        self,
        name: str = "LLMCritic",
        llm_adapter: Optional[LLMAdapter] = None
    ):
        super().__init__(name)
        self.llm = llm_adapter or MockLLMAdapter()
        self.system_prompt = """You are an expert critic and evaluator. Your job is to:
1. Carefully analyze the given output
2. Identify strengths and weaknesses
3. Provide a quality score (0.0 to 1.0)
4. Give actionable improvement suggestions
5. Determine if refinement is needed

Be constructive but rigorous. Focus on helping improve the output.

IMPORTANT: Respond in valid JSON format with this structure:
{
  "score": 0.0-1.0,
  "strengths": ["list of strengths"],
  "weaknesses": ["list of weaknesses"],
  "suggestions": ["list of suggestions"],
  "should_refine": true/false
}"""

    def _default_evaluation(
        self,
        result: ExecutionResult,
        task: Optional[Task] = None
    ) -> Critique:
        """Evaluate using LLM."""
        prompt = f"""Please evaluate the following output:

Output to evaluate:
{result.output}

Original task (if available):
{task.description if task else 'Not provided'}

Objective:
{task.objective if task else 'Not provided'}

Current confidence: {result.confidence}
Iteration: {result.iteration}

Provide your critique in JSON format."""

        response = self.llm.complete(prompt, self.system_prompt)

        try:
            # Parse JSON response
            data = json.loads(response)
            return Critique(
                result_id=result.task_id,
                score=float(data.get("score", 0.5)),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                suggestions=data.get("suggestions", []),
                should_refine=data.get("should_refine", True)
            )
        except json.JSONDecodeError:
            # Fallback to heuristic parsing
            logger.warning("Failed to parse LLM response as JSON, using heuristics")
            return super()._default_evaluation(result, task)


class LLMGoalEvaluatorAgent(GoalEvaluatorAgent):
    """Goal evaluator agent powered by an LLM."""

    def __init__(
        self,
        name: str = "LLMGoalEvaluator",
        llm_adapter: Optional[LLMAdapter] = None
    ):
        super().__init__(name)
        self.llm = llm_adapter or MockLLMAdapter()
        self.system_prompt = """You are an expert at evaluating goal achievement. Your job is to:
1. Assess progress toward the stated goal
2. Identify what has been achieved
3. Identify gaps and what's missing
4. Provide progress percentage (0-100)
5. Recommend next steps

IMPORTANT: Respond in valid JSON format with this structure:
{
  "status": "NOT_STARTED|IN_PROGRESS|PARTIALLY_ACHIEVED|ACHIEVED|FAILED",
  "progress": 0-100,
  "achievements": ["what has been accomplished"],
  "gaps": ["what is missing"],
  "recommendation": "next steps"
}"""

    def evaluate_goal(
        self,
        goal: str,
        current_result: Any,
        task: Optional[Task] = None
    ) -> GoalEvaluation:
        """Evaluate goal using LLM."""
        prompt = f"""Please evaluate progress toward this goal:

Goal: {goal}

Current result:
{current_result}

Task details (if available):
{task.description if task else 'Not provided'}

Provide your evaluation in JSON format."""

        response = self.llm.complete(prompt, self.system_prompt)

        try:
            data = json.loads(response)
            status_map = {
                "NOT_STARTED": GoalStatus.NOT_STARTED,
                "IN_PROGRESS": GoalStatus.IN_PROGRESS,
                "PARTIALLY_ACHIEVED": GoalStatus.PARTIALLY_ACHIEVED,
                "ACHIEVED": GoalStatus.ACHIEVED,
                "FAILED": GoalStatus.FAILED
            }

            evaluation = GoalEvaluation(
                goal=goal,
                status=status_map.get(data.get("status", "IN_PROGRESS"), GoalStatus.IN_PROGRESS),
                progress=float(data.get("progress", 50)),
                metrics={"llm_evaluated": True},
                gaps=data.get("gaps", []),
                recommendation=data.get("recommendation", "Continue refinement")
            )

            self.goal_history[goal].append(evaluation)
            return evaluation

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response, using parent implementation")
            return super().evaluate_goal(goal, current_result, task)


# =============================================================================
# LLM-Powered Orchestrator
# =============================================================================

class LLMMultiAgentOrchestrator:
    """
    Multi-agent orchestrator with LLM-powered agents.

    Provides a high-level interface for creating and running
    LLM-powered multi-agent systems.
    """

    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        max_iterations: int = 10
    ):
        from multi_agent_system import MultiAgentOrchestrator, CoordinatorAgent, RefinementAgent

        self.llm_config = llm_config or LLMConfig.mock()
        self.llm_adapter = create_adapter(self.llm_config)
        self.orchestrator = MultiAgentOrchestrator(max_iterations=max_iterations)

        # Create LLM-powered agents
        self._setup_agents()

    def _setup_agents(self) -> None:
        """Setup LLM-powered agents."""
        from multi_agent_system import CoordinatorAgent, RefinementAgent

        # Coordinator (not LLM-powered, handles routing)
        coordinator = CoordinatorAgent()

        # LLM-powered executor
        executor = LLMExecutorAgent(llm_adapter=self.llm_adapter)

        # LLM-powered critic
        critic = LLMCriticAgent(llm_adapter=self.llm_adapter)

        # Standard refiner
        refiner = RefinementAgent()

        # LLM-powered goal evaluator
        goal_evaluator = LLMGoalEvaluatorAgent(llm_adapter=self.llm_adapter)

        # Register all agents
        self.orchestrator.register_agent(coordinator)
        self.orchestrator.register_agent(executor)
        self.orchestrator.register_agent(critic)
        self.orchestrator.register_agent(refiner)
        self.orchestrator.register_agent(goal_evaluator)

    def solve(
        self,
        problem: str,
        objective: str,
        constraints: Optional[List[str]] = None,
        max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """Solve a problem using LLM-powered agents."""
        if max_iterations:
            self.orchestrator.max_iterations = max_iterations

        task = Task(
            description=problem,
            objective=objective,
            constraints=constraints or []
        )

        return self.orchestrator.execute_task(task, goal=objective)

    def get_llm_metrics(self) -> Dict[str, Any]:
        """Get LLM usage metrics."""
        return self.llm_adapter.get_metrics()


# =============================================================================
# Prompt Templates
# =============================================================================

class PromptTemplates:
    """Collection of prompt templates for different agent roles."""

    TASK_DECOMPOSITION = """You are a task planning expert. Break down the following complex task into smaller, manageable subtasks.

Main Task: {task_description}
Objective: {objective}
Constraints: {constraints}

Provide a list of subtasks in JSON format:
[
  {{"description": "subtask 1 description", "objective": "subtask 1 objective"}},
  {{"description": "subtask 2 description", "objective": "subtask 2 objective"}}
]"""

    CODE_REVIEW = """You are an expert code reviewer. Review the following code for:
1. Correctness
2. Performance
3. Security
4. Best practices
5. Readability

Code to review:
```
{code}
```

Provide your review with specific line references and suggestions."""

    DOCUMENT_ANALYSIS = """Analyze the following document and extract key information.

Document:
{document}

Provide:
1. Summary
2. Key points
3. Action items
4. Questions/Clarifications needed"""

    REFINEMENT = """You are tasked with improving the following output based on feedback.

Original output:
{output}

Feedback received:
Strengths: {strengths}
Weaknesses: {weaknesses}
Suggestions: {suggestions}

Please provide an improved version that addresses the weaknesses and incorporates the suggestions while maintaining the strengths."""


# =============================================================================
# Demo
# =============================================================================

def demo_llm_agents():
    """Demonstrate LLM-powered multi-agent system."""
    print("\n" + "="*60)
    print("LLM-Powered Multi-Agent System Demo")
    print("="*60 + "\n")

    # Use mock adapter for demo (no API calls needed)
    config = LLMConfig.mock()
    orchestrator = LLMMultiAgentOrchestrator(llm_config=config, max_iterations=5)

    # Solve a problem
    result = orchestrator.solve(
        problem="Design a REST API for a user management system",
        objective="Create a comprehensive API specification with endpoints, request/response formats, and error handling",
        constraints=[
            "Must follow REST best practices",
            "Must include authentication",
            "Must handle common error cases"
        ]
    )

    print(f"Task completed in {result['iterations']} iterations")
    print(f"Converged: {result['converged']}")
    print(f"\nLLM Metrics: {orchestrator.get_llm_metrics()}")

    return result


if __name__ == '__main__':
    demo_llm_agents()
