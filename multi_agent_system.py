#!/usr/bin/env python3
"""
Multi-Agent System - A framework for collaborative AI agents with iterative refinement.

This system implements:
- Multiple specialized agents with distinct roles
- Inter-agent communication via message passing
- Iterative refinement cycles for goal convergence
- Goal achievement evaluation with quantitative metrics

Architecture:
    Coordinator Agent <-> Executor Agents <-> Critic Agent <-> Refinement Agent
                    \                                        /
                     ------> Goal Evaluator <----------------

Author: Multi-Agent System Framework
License: MIT
"""

from __future__ import annotations

import uuid
import time
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, Generic
)
from collections import defaultdict
from datetime import datetime
import threading
from queue import Queue, Empty
import hashlib


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Enumerations and Constants
# =============================================================================

class MessageType(Enum):
    """Types of messages exchanged between agents."""
    TASK = auto()           # New task assignment
    RESULT = auto()         # Task execution result
    CRITIQUE = auto()       # Feedback/criticism on result
    REFINEMENT = auto()     # Refined version after critique
    QUERY = auto()          # Information request
    RESPONSE = auto()       # Response to query
    STATUS = auto()         # Status update
    TERMINATION = auto()    # Signal to terminate


class AgentState(Enum):
    """Possible states of an agent."""
    IDLE = auto()
    PROCESSING = auto()
    WAITING = auto()
    TERMINATED = auto()


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class GoalStatus(Enum):
    """Status of goal achievement."""
    NOT_STARTED = auto()
    IN_PROGRESS = auto()
    PARTIALLY_ACHIEVED = auto()
    ACHIEVED = auto()
    FAILED = auto()


# =============================================================================
# Core Data Structures
# =============================================================================

@dataclass
class Message:
    """
    Message exchanged between agents.

    Attributes:
        id: Unique message identifier
        type: Type of message (task, result, critique, etc.)
        sender_id: ID of the sending agent
        receiver_id: ID of the receiving agent (None for broadcast)
        content: Message payload
        metadata: Additional message metadata
        timestamp: When the message was created
        reply_to: ID of message this is responding to
    """
    type: MessageType
    sender_id: str
    content: Any
    receiver_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        """Serialize message to dictionary."""
        return {
            'id': self.id,
            'type': self.type.name,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
            'reply_to': self.reply_to
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Deserialize message from dictionary."""
        return cls(
            id=data['id'],
            type=MessageType[data['type']],
            sender_id=data['sender_id'],
            receiver_id=data.get('receiver_id'),
            content=data['content'],
            metadata=data.get('metadata', {}),
            timestamp=datetime.fromisoformat(data['timestamp']),
            reply_to=data.get('reply_to')
        )


@dataclass
class Task:
    """
    A task to be executed by agents.

    Attributes:
        id: Unique task identifier
        description: Human-readable task description
        objective: The goal to achieve
        constraints: Constraints that must be satisfied
        priority: Task priority level
        max_iterations: Maximum refinement iterations allowed
        success_criteria: Criteria for determining success
        subtasks: List of decomposed subtasks
    """
    description: str
    objective: str
    constraints: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    max_iterations: int = 5
    success_criteria: Dict[str, Any] = field(default_factory=dict)
    subtasks: List['Task'] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def decompose(self, parts: List[Tuple[str, str]]) -> List['Task']:
        """Decompose task into subtasks."""
        self.subtasks = [
            Task(description=desc, objective=obj, priority=self.priority)
            for desc, obj in parts
        ]
        return self.subtasks


@dataclass
class ExecutionResult:
    """
    Result of task execution.

    Attributes:
        task_id: ID of the executed task
        output: The actual output/result
        confidence: Agent's confidence in the result (0-1)
        reasoning: Explanation of how result was achieved
        iteration: Which iteration this result is from
        metrics: Quantitative metrics about the execution
    """
    task_id: str
    output: Any
    confidence: float = 0.5
    reasoning: str = ""
    iteration: int = 1
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'output': self.output,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'iteration': self.iteration,
            'metrics': self.metrics
        }


@dataclass
class Critique:
    """
    Critique/feedback on an execution result.

    Attributes:
        result_id: ID of the result being critiqued
        score: Overall quality score (0-1)
        strengths: List of positive aspects
        weaknesses: List of areas for improvement
        suggestions: Specific improvement suggestions
        should_refine: Whether refinement is recommended
    """
    result_id: str
    score: float
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    should_refine: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'result_id': self.result_id,
            'score': self.score,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'suggestions': self.suggestions,
            'should_refine': self.should_refine
        }


@dataclass
class GoalEvaluation:
    """
    Evaluation of goal achievement.

    Attributes:
        goal: The original goal being evaluated
        status: Current status of goal achievement
        progress: Progress percentage (0-100)
        metrics: Detailed evaluation metrics
        gaps: What's missing to achieve the goal
        recommendation: Next steps recommendation
    """
    goal: str
    status: GoalStatus
    progress: float  # 0-100
    metrics: Dict[str, float] = field(default_factory=dict)
    gaps: List[str] = field(default_factory=list)
    recommendation: str = ""


# =============================================================================
# Agent Base Class
# =============================================================================

class BaseAgent(ABC):
    """
    Abstract base class for all agents in the system.

    Provides:
    - Message handling infrastructure
    - State management
    - Logging and monitoring
    - Hook points for derived classes
    """

    def __init__(
        self,
        name: str,
        agent_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None
    ):
        self.name = name
        self.id = agent_id or f"{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        self.capabilities = capabilities or []
        self.state = AgentState.IDLE
        self.message_queue: Queue[Message] = Queue()
        self.message_history: List[Message] = []
        self.logger = logging.getLogger(f"Agent.{self.name}")
        self._running = False
        self._lock = threading.Lock()

        # Performance metrics
        self.metrics = {
            'messages_processed': 0,
            'tasks_completed': 0,
            'total_processing_time': 0.0,
            'errors': 0
        }

    def receive_message(self, message: Message) -> None:
        """Receive and queue a message for processing."""
        self.message_queue.put(message)
        self.message_history.append(message)
        self.logger.debug(f"Received message {message.id} from {message.sender_id}")

    def send_message(
        self,
        msg_type: MessageType,
        content: Any,
        receiver_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Create and return a message to be sent."""
        message = Message(
            type=msg_type,
            sender_id=self.id,
            receiver_id=receiver_id,
            content=content,
            reply_to=reply_to,
            metadata=metadata or {}
        )
        self.message_history.append(message)
        return message

    @abstractmethod
    def process_message(self, message: Message) -> Optional[Message]:
        """Process a received message and optionally return a response."""
        pass

    def run_once(self) -> Optional[Message]:
        """Process one message from the queue."""
        try:
            message = self.message_queue.get(timeout=0.1)
            with self._lock:
                self.state = AgentState.PROCESSING

            start_time = time.time()
            response = self.process_message(message)
            processing_time = time.time() - start_time

            self.metrics['messages_processed'] += 1
            self.metrics['total_processing_time'] += processing_time

            with self._lock:
                self.state = AgentState.IDLE

            return response
        except Empty:
            return None
        except Exception as e:
            self.metrics['errors'] += 1
            self.logger.error(f"Error processing message: {e}")
            with self._lock:
                self.state = AgentState.IDLE
            raise

    def run(self, max_iterations: Optional[int] = None) -> None:
        """Run the agent's message processing loop."""
        self._running = True
        iterations = 0

        while self._running:
            if max_iterations and iterations >= max_iterations:
                break

            self.run_once()
            iterations += 1

    def stop(self) -> None:
        """Stop the agent's processing loop."""
        self._running = False
        with self._lock:
            self.state = AgentState.TERMINATED

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state.name,
            'queue_size': self.message_queue.qsize(),
            'metrics': self.metrics.copy()
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


# =============================================================================
# Specialized Agent Implementations
# =============================================================================

class CoordinatorAgent(BaseAgent):
    """
    Coordinator Agent: Decomposes tasks and orchestrates other agents.

    Responsibilities:
    - Task decomposition and planning
    - Work distribution to executor agents
    - Progress monitoring
    - Final result aggregation
    """

    def __init__(self, name: str = "Coordinator"):
        super().__init__(name, capabilities=['task_decomposition', 'orchestration', 'aggregation'])
        self.active_tasks: Dict[str, Task] = {}
        self.task_assignments: Dict[str, str] = {}  # task_id -> agent_id
        self.results: Dict[str, List[ExecutionResult]] = defaultdict(list)
        self.decomposition_strategy: Optional[Callable[[Task], List[Tuple[str, str]]]] = None

    def set_decomposition_strategy(
        self,
        strategy: Callable[[Task], List[Tuple[str, str]]]
    ) -> None:
        """Set custom task decomposition strategy."""
        self.decomposition_strategy = strategy

    def decompose_task(self, task: Task) -> List[Task]:
        """Decompose a complex task into subtasks."""
        if self.decomposition_strategy:
            parts = self.decomposition_strategy(task)
        else:
            # Default: single task, no decomposition
            parts = [(task.description, task.objective)]

        return task.decompose(parts)

    def process_message(self, message: Message) -> Optional[Message]:
        """Process incoming messages and coordinate responses."""

        if message.type == MessageType.TASK:
            # New task received - decompose and distribute
            task = message.content

            # Handle already decomposed tasks (with parent_task key)
            if isinstance(task, dict) and 'parent_task' in task:
                # Already processed subtasks message, skip to prevent loop
                return None

            if isinstance(task, dict):
                # Filter out any non-Task fields before constructing
                task_fields = {'description', 'objective', 'constraints', 'priority',
                              'max_iterations', 'success_criteria', 'subtasks', 'id'}
                filtered_task = {k: v for k, v in task.items() if k in task_fields}
                task = Task(**filtered_task)

            self.active_tasks[task.id] = task
            subtasks = self.decompose_task(task)

            self.logger.info(f"Decomposed task {task.id} into {len(subtasks)} subtasks")

            # Return message with subtasks for distribution
            return self.send_message(
                MessageType.TASK,
                {'parent_task': task.id, 'subtasks': [st.__dict__ for st in subtasks]},
                metadata={'requires_distribution': True}
            )

        elif message.type == MessageType.RESULT:
            # Result received from executor
            result = message.content
            if isinstance(result, dict):
                result = ExecutionResult(**result)

            self.results[result.task_id].append(result)
            self.logger.info(
                f"Received result for task {result.task_id} "
                f"(iteration {result.iteration}, confidence: {result.confidence:.2f})"
            )

            # Forward to critic for evaluation
            return self.send_message(
                MessageType.RESULT,
                result.to_dict(),
                metadata={'requires_critique': True}
            )

        elif message.type == MessageType.STATUS:
            # Status update from subordinate agent
            self.logger.debug(f"Status update: {message.content}")
            return None

        return None

    def aggregate_results(self, task_id: str) -> Optional[ExecutionResult]:
        """Aggregate all results for a task into final output."""
        if task_id not in self.results:
            return None

        results = self.results[task_id]
        if not results:
            return None

        # Take the highest confidence result
        best_result = max(results, key=lambda r: r.confidence)
        return best_result


class ExecutorAgent(BaseAgent):
    """
    Executor Agent: Performs actual task execution.

    Responsibilities:
    - Execute assigned tasks
    - Report results with confidence scores
    - Apply refinements based on feedback
    """

    def __init__(
        self,
        name: str = "Executor",
        execution_fn: Optional[Callable[[Task], Any]] = None
    ):
        super().__init__(name, capabilities=['task_execution', 'refinement'])
        self.current_task: Optional[Task] = None
        self.execution_fn = execution_fn or self._default_execution
        self.refinement_history: List[Tuple[ExecutionResult, Critique]] = []

    def _default_execution(self, task: Task) -> Any:
        """Default execution function (override for real implementation)."""
        return f"Executed: {task.objective}"

    def set_execution_function(self, fn: Callable[[Task], Any]) -> None:
        """Set custom execution function."""
        self.execution_fn = fn

    def execute_task(self, task: Task, iteration: int = 1) -> ExecutionResult:
        """Execute a task and return result."""
        self.current_task = task

        try:
            output = self.execution_fn(task)
            confidence = self._calculate_confidence(output, task)

            result = ExecutionResult(
                task_id=task.id,
                output=output,
                confidence=confidence,
                reasoning=f"Executed task: {task.description}",
                iteration=iteration,
                metrics={
                    'execution_time': time.time(),
                    'output_length': len(str(output)) if output else 0
                }
            )

            self.metrics['tasks_completed'] += 1
            return result

        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            return ExecutionResult(
                task_id=task.id,
                output=None,
                confidence=0.0,
                reasoning=f"Execution failed: {str(e)}",
                iteration=iteration
            )

    def _calculate_confidence(self, output: Any, task: Task) -> float:
        """Calculate confidence score for the output."""
        # Base confidence
        confidence = 0.5

        # Adjust based on output presence
        if output is not None:
            confidence += 0.2

        # Adjust based on output quality heuristics
        if output and isinstance(output, str) and len(output) > 10:
            confidence += 0.1

        # Adjust based on task constraints satisfaction (simplified)
        if not task.constraints:
            confidence += 0.1

        return min(confidence, 1.0)

    def refine_result(
        self,
        result: ExecutionResult,
        critique: Critique
    ) -> ExecutionResult:
        """Refine a result based on critique feedback."""
        self.refinement_history.append((result, critique))

        # Apply suggestions (simplified - real implementation would be smarter)
        refined_output = result.output
        if isinstance(refined_output, str) and critique.suggestions:
            refined_output = f"{refined_output}\n[Refined based on: {'; '.join(critique.suggestions)}]"

        # Increase confidence slightly if we addressed feedback
        new_confidence = min(result.confidence + 0.1, 1.0)

        return ExecutionResult(
            task_id=result.task_id,
            output=refined_output,
            confidence=new_confidence,
            reasoning=f"Refined from iteration {result.iteration}: Applied {len(critique.suggestions)} suggestions",
            iteration=result.iteration + 1,
            metrics={**result.metrics, 'refinement_applied': True}
        )

    def process_message(self, message: Message) -> Optional[Message]:
        """Process incoming messages."""

        if message.type == MessageType.TASK:
            # Execute the task
            task_data = message.content

            # Handle already decomposed tasks (with parent_task key) - skip subtask routing messages
            if isinstance(task_data, dict) and 'parent_task' in task_data:
                # This is a subtask distribution message, process subtasks
                subtasks = task_data.get('subtasks', [])
                if subtasks:
                    # Execute the first subtask (simplified)
                    task_fields = {'description', 'objective', 'constraints', 'priority',
                                  'max_iterations', 'success_criteria', 'subtasks', 'id'}
                    filtered = {k: v for k, v in subtasks[0].items() if k in task_fields}
                    task = Task(**filtered)
                else:
                    return None
            elif isinstance(task_data, dict):
                # Filter out any non-Task fields before constructing
                task_fields = {'description', 'objective', 'constraints', 'priority',
                              'max_iterations', 'success_criteria', 'subtasks', 'id'}
                filtered_task = {k: v for k, v in task_data.items() if k in task_fields}
                task = Task(**filtered_task)
            else:
                task = task_data

            result = self.execute_task(task)

            return self.send_message(
                MessageType.RESULT,
                result.to_dict(),
                reply_to=message.id
            )

        elif message.type == MessageType.CRITIQUE:
            # Refine based on critique
            critique_data = message.content
            if isinstance(critique_data, dict):
                critique = Critique(**critique_data)
            else:
                critique = critique_data

            # Find the original result
            if self.refinement_history:
                last_result, _ = self.refinement_history[-1]
            else:
                # Create a placeholder result
                last_result = ExecutionResult(
                    task_id=critique.result_id,
                    output="",
                    iteration=0
                )

            if critique.should_refine:
                refined = self.refine_result(last_result, critique)
                return self.send_message(
                    MessageType.REFINEMENT,
                    refined.to_dict(),
                    reply_to=message.id
                )

        return None


class CriticAgent(BaseAgent):
    """
    Critic Agent: Evaluates results and provides constructive feedback.

    Responsibilities:
    - Quality assessment of results
    - Identifying strengths and weaknesses
    - Providing actionable improvement suggestions
    - Determining if refinement is needed
    """

    def __init__(
        self,
        name: str = "Critic",
        evaluation_fn: Optional[Callable[[ExecutionResult, Task], Critique]] = None
    ):
        super().__init__(name, capabilities=['evaluation', 'feedback', 'quality_assessment'])
        self.evaluation_fn = evaluation_fn or self._default_evaluation
        self.evaluation_history: List[Critique] = []
        self.quality_threshold = 0.8  # Score above this = acceptable

    def _default_evaluation(
        self,
        result: ExecutionResult,
        task: Optional[Task] = None
    ) -> Critique:
        """Default evaluation function."""
        score = result.confidence

        strengths = []
        weaknesses = []
        suggestions = []

        # Analyze the result
        if result.output:
            strengths.append("Produced non-empty output")

            if isinstance(result.output, str):
                if len(result.output) > 50:
                    strengths.append("Detailed output provided")
                else:
                    weaknesses.append("Output could be more detailed")
                    suggestions.append("Expand the output with more context")
        else:
            weaknesses.append("No output produced")
            suggestions.append("Ensure task execution produces output")
            score *= 0.5

        if result.confidence < 0.5:
            weaknesses.append("Low confidence in result")
            suggestions.append("Review execution approach")

        if result.reasoning:
            strengths.append("Reasoning provided")
        else:
            weaknesses.append("No reasoning provided")
            suggestions.append("Add explanation of how result was achieved")

        should_refine = score < self.quality_threshold

        return Critique(
            result_id=result.task_id,
            score=score,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            should_refine=should_refine
        )

    def set_evaluation_function(
        self,
        fn: Callable[[ExecutionResult, Optional[Task]], Critique]
    ) -> None:
        """Set custom evaluation function."""
        self.evaluation_fn = fn

    def evaluate(
        self,
        result: ExecutionResult,
        task: Optional[Task] = None
    ) -> Critique:
        """Evaluate a result and produce a critique."""
        critique = self.evaluation_fn(result, task)
        self.evaluation_history.append(critique)

        self.logger.info(
            f"Evaluated result {result.task_id}: "
            f"score={critique.score:.2f}, "
            f"should_refine={critique.should_refine}"
        )

        return critique

    def process_message(self, message: Message) -> Optional[Message]:
        """Process incoming messages."""

        if message.type == MessageType.RESULT:
            # Evaluate the result
            result_data = message.content
            if isinstance(result_data, dict):
                result = ExecutionResult(**result_data)
            else:
                result = result_data

            critique = self.evaluate(result)

            return self.send_message(
                MessageType.CRITIQUE,
                critique.to_dict(),
                reply_to=message.id
            )

        return None


class RefinementAgent(BaseAgent):
    """
    Refinement Agent: Specializes in improving results based on feedback.

    Responsibilities:
    - Analyzing critique feedback
    - Applying targeted improvements
    - Tracking refinement progress
    - Preventing infinite refinement loops
    """

    def __init__(self, name: str = "Refiner"):
        super().__init__(name, capabilities=['refinement', 'improvement', 'iteration'])
        self.refinement_count: Dict[str, int] = defaultdict(int)
        self.max_refinements = 5
        self.improvement_strategies: List[Callable[[Any, Critique], Any]] = []

    def add_improvement_strategy(
        self,
        strategy: Callable[[Any, Critique], Any]
    ) -> None:
        """Add an improvement strategy."""
        self.improvement_strategies.append(strategy)

    def refine(
        self,
        result: ExecutionResult,
        critique: Critique
    ) -> ExecutionResult:
        """Refine a result based on critique."""
        task_id = result.task_id
        self.refinement_count[task_id] += 1

        if self.refinement_count[task_id] > self.max_refinements:
            self.logger.warning(
                f"Max refinements ({self.max_refinements}) reached for task {task_id}"
            )
            return result

        refined_output = result.output

        # Apply improvement strategies
        for strategy in self.improvement_strategies:
            try:
                refined_output = strategy(refined_output, critique)
            except Exception as e:
                self.logger.error(f"Strategy failed: {e}")

        # Default refinement if no strategies
        if not self.improvement_strategies and isinstance(refined_output, str):
            for suggestion in critique.suggestions:
                refined_output = f"{refined_output}\n- Addressed: {suggestion}"

        return ExecutionResult(
            task_id=task_id,
            output=refined_output,
            confidence=min(result.confidence + 0.15, 1.0),
            reasoning=f"Refinement #{self.refinement_count[task_id]}",
            iteration=result.iteration + 1,
            metrics={
                **result.metrics,
                'refinement_iteration': self.refinement_count[task_id]
            }
        )

    def process_message(self, message: Message) -> Optional[Message]:
        """Process incoming messages."""

        if message.type == MessageType.CRITIQUE:
            # Get critique and associated result
            content = message.content
            if isinstance(content, dict) and 'result' in content and 'critique' in content:
                result = ExecutionResult(**content['result'])
                critique = Critique(**content['critique'])
            else:
                # Assume content is just critique, create placeholder result
                if isinstance(content, dict):
                    critique = Critique(**content)
                else:
                    critique = content
                result = ExecutionResult(
                    task_id=critique.result_id,
                    output="",
                    iteration=0
                )

            if critique.should_refine:
                refined = self.refine(result, critique)
                return self.send_message(
                    MessageType.REFINEMENT,
                    refined.to_dict(),
                    reply_to=message.id
                )

        return None


class GoalEvaluatorAgent(BaseAgent):
    """
    Goal Evaluator Agent: Assesses overall goal achievement.

    Responsibilities:
    - Tracking progress toward goals
    - Quantitative goal evaluation
    - Determining convergence
    - Recommending next steps
    """

    def __init__(self, name: str = "GoalEvaluator"):
        super().__init__(name, capabilities=['goal_evaluation', 'progress_tracking', 'convergence_detection'])
        self.goal_history: Dict[str, List[GoalEvaluation]] = defaultdict(list)
        self.convergence_threshold = 0.95
        self.evaluation_criteria: Dict[str, Callable[[Any], float]] = {}

    def add_criterion(self, name: str, evaluator: Callable[[Any], float]) -> None:
        """Add an evaluation criterion."""
        self.evaluation_criteria[name] = evaluator

    def evaluate_goal(
        self,
        goal: str,
        current_result: Any,
        task: Optional[Task] = None
    ) -> GoalEvaluation:
        """Evaluate progress toward a goal."""
        metrics = {}

        # Apply evaluation criteria
        for name, evaluator in self.evaluation_criteria.items():
            try:
                metrics[name] = evaluator(current_result)
            except Exception as e:
                self.logger.error(f"Criterion {name} failed: {e}")
                metrics[name] = 0.0

        # Calculate overall progress
        if metrics:
            progress = sum(metrics.values()) / len(metrics) * 100
        else:
            # Default heuristic
            if current_result is None:
                progress = 0.0
            elif isinstance(current_result, ExecutionResult):
                progress = current_result.confidence * 100
            else:
                progress = 50.0

        # Determine status
        if progress >= 95:
            status = GoalStatus.ACHIEVED
        elif progress >= 70:
            status = GoalStatus.PARTIALLY_ACHIEVED
        elif progress > 0:
            status = GoalStatus.IN_PROGRESS
        else:
            status = GoalStatus.NOT_STARTED

        # Identify gaps
        gaps = []
        if progress < 100:
            if not current_result:
                gaps.append("No result produced yet")
            elif isinstance(current_result, ExecutionResult):
                if current_result.confidence < 0.8:
                    gaps.append("Confidence below threshold")
                if not current_result.reasoning:
                    gaps.append("Missing reasoning")

        # Generate recommendation
        if status == GoalStatus.ACHIEVED:
            recommendation = "Goal achieved. Ready for finalization."
        elif status == GoalStatus.PARTIALLY_ACHIEVED:
            recommendation = f"Continue refinement. Focus on: {', '.join(gaps[:2])}"
        else:
            recommendation = "Requires more iterations to achieve goal."

        evaluation = GoalEvaluation(
            goal=goal,
            status=status,
            progress=progress,
            metrics=metrics,
            gaps=gaps,
            recommendation=recommendation
        )

        self.goal_history[goal].append(evaluation)
        return evaluation

    def check_convergence(self, goal: str) -> bool:
        """Check if goal has converged."""
        history = self.goal_history.get(goal, [])

        if len(history) < 2:
            return False

        # Check if progress has plateaued
        recent = history[-3:] if len(history) >= 3 else history
        progress_values = [e.progress for e in recent]

        # Converged if all recent values are close
        if all(abs(p - progress_values[-1]) < 2.0 for p in progress_values):
            return progress_values[-1] >= self.convergence_threshold * 100

        return False

    def process_message(self, message: Message) -> Optional[Message]:
        """Process incoming messages."""

        if message.type == MessageType.RESULT:
            content = message.content
            if isinstance(content, dict):
                goal = content.get('goal', 'default_goal')
                result = content.get('result')
                if isinstance(result, dict):
                    result = ExecutionResult(**result)
            else:
                goal = 'default_goal'
                result = content

            evaluation = self.evaluate_goal(goal, result)
            converged = self.check_convergence(goal)

            return self.send_message(
                MessageType.STATUS,
                {
                    'goal': goal,
                    'evaluation': {
                        'status': evaluation.status.name,
                        'progress': evaluation.progress,
                        'metrics': evaluation.metrics,
                        'gaps': evaluation.gaps,
                        'recommendation': evaluation.recommendation
                    },
                    'converged': converged
                },
                reply_to=message.id
            )

        return None


# =============================================================================
# Multi-Agent Orchestrator
# =============================================================================

class MultiAgentOrchestrator:
    """
    Orchestrates multiple agents to achieve complex goals through iterative collaboration.

    Features:
    - Agent registration and lifecycle management
    - Message routing between agents
    - Iterative refinement cycles
    - Goal-oriented termination
    - Comprehensive logging and monitoring
    """

    def __init__(
        self,
        max_iterations: int = 10,
        convergence_threshold: float = 0.9
    ):
        self.agents: Dict[str, BaseAgent] = {}
        self.message_bus: Queue[Message] = Queue()
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.iteration_count = 0
        self.execution_log: List[Dict[str, Any]] = []
        self.logger = logging.getLogger("Orchestrator")
        self._running = False

        # Metrics
        self.metrics = {
            'total_messages': 0,
            'iterations_completed': 0,
            'goals_achieved': 0,
            'refinement_cycles': 0
        }

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the orchestrator."""
        self.agents[agent.id] = agent
        self.logger.info(f"Registered agent: {agent.name} ({agent.id})")

    def unregister_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Unregister an agent from the orchestrator."""
        agent = self.agents.pop(agent_id, None)
        if agent:
            self.logger.info(f"Unregistered agent: {agent.name}")
        return agent

    def route_message(self, message: Message) -> None:
        """Route a message to appropriate agent(s)."""
        self.metrics['total_messages'] += 1

        self.execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'event': 'message_routed',
            'message_id': message.id,
            'type': message.type.name,
            'from': message.sender_id,
            'to': message.receiver_id or 'broadcast'
        })

        if message.receiver_id:
            # Direct message
            if message.receiver_id in self.agents:
                self.agents[message.receiver_id].receive_message(message)
        else:
            # Broadcast or route based on message type
            self._route_by_type(message)

    def _route_by_type(self, message: Message) -> None:
        """Route message based on type to appropriate agents."""
        # Define routing rules
        routing_rules = {
            MessageType.TASK: ['task_decomposition', 'orchestration', 'task_execution'],
            MessageType.RESULT: ['evaluation', 'quality_assessment', 'goal_evaluation'],
            MessageType.CRITIQUE: ['refinement', 'improvement', 'task_execution'],
            MessageType.REFINEMENT: ['evaluation', 'goal_evaluation'],
            MessageType.STATUS: ['orchestration'],
        }

        target_capabilities = routing_rules.get(message.type, [])

        for agent in self.agents.values():
            if any(cap in agent.capabilities for cap in target_capabilities):
                agent.receive_message(message)

    def create_default_agents(self) -> None:
        """Create and register default agent set."""
        coordinator = CoordinatorAgent()
        executor = ExecutorAgent()
        critic = CriticAgent()
        refiner = RefinementAgent()
        goal_evaluator = GoalEvaluatorAgent()

        self.register_agent(coordinator)
        self.register_agent(executor)
        self.register_agent(critic)
        self.register_agent(refiner)
        self.register_agent(goal_evaluator)

    def run_iteration(self) -> Dict[str, Any]:
        """Run one iteration of the multi-agent loop."""
        self.iteration_count += 1
        iteration_results = {
            'iteration': self.iteration_count,
            'messages_processed': 0,
            'agents_active': []
        }

        self.logger.info(f"=== Iteration {self.iteration_count} ===")

        # Process messages for each agent
        for agent_id, agent in self.agents.items():
            response = agent.run_once()

            if response:
                iteration_results['messages_processed'] += 1
                iteration_results['agents_active'].append(agent_id)
                self.route_message(response)

        self.metrics['iterations_completed'] += 1
        return iteration_results

    def execute_task(
        self,
        task: Task,
        goal: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a task through the multi-agent system.

        Returns execution summary including final result and metrics.
        """
        goal = goal or task.objective
        self.logger.info(f"Starting task execution: {task.description}")
        self.logger.info(f"Goal: {goal}")

        # Initial task message
        initial_message = Message(
            type=MessageType.TASK,
            sender_id="orchestrator",
            content=task.__dict__,
            metadata={'goal': goal}
        )
        self.route_message(initial_message)

        # Iterative execution loop
        converged = False
        final_result = None

        while self.iteration_count < self.max_iterations and not converged:
            iteration_result = self.run_iteration()

            # Check for convergence
            for agent in self.agents.values():
                if isinstance(agent, GoalEvaluatorAgent):
                    converged = agent.check_convergence(goal)
                    if converged:
                        self.metrics['goals_achieved'] += 1
                        self.logger.info("Goal converged!")
                        break

            # Small delay to prevent tight loop
            time.sleep(0.01)

        # Aggregate final result
        for agent in self.agents.values():
            if isinstance(agent, CoordinatorAgent):
                final_result = agent.aggregate_results(task.id)
                break

        return {
            'task_id': task.id,
            'goal': goal,
            'iterations': self.iteration_count,
            'converged': converged,
            'final_result': final_result.to_dict() if final_result else None,
            'metrics': self.metrics.copy(),
            'execution_log': self.execution_log
        }

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            'iteration': self.iteration_count,
            'agents': {
                agent_id: agent.get_status()
                for agent_id, agent in self.agents.items()
            },
            'metrics': self.metrics.copy(),
            'message_bus_size': self.message_bus.qsize()
        }

    def reset(self) -> None:
        """Reset orchestrator state."""
        self.iteration_count = 0
        self.execution_log.clear()
        for agent in self.agents.values():
            agent.message_queue = Queue()
            agent.state = AgentState.IDLE


# =============================================================================
# High-Level API: Collaborative Problem Solving
# =============================================================================

class CollaborativeProblemSolver:
    """
    High-level API for solving problems through multi-agent collaboration.

    Provides a simple interface for:
    - Problem definition
    - Agent configuration
    - Iterative solution refinement
    - Result extraction
    """

    def __init__(self):
        self.orchestrator = MultiAgentOrchestrator()
        self.orchestrator.create_default_agents()
        self.solutions: Dict[str, Any] = {}

    def configure_executor(self, execution_fn: Callable[[Task], Any]) -> None:
        """Configure the execution function for the executor agent."""
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, ExecutorAgent):
                agent.set_execution_function(execution_fn)

    def configure_evaluator(
        self,
        evaluation_fn: Callable[[ExecutionResult, Optional[Task]], Critique]
    ) -> None:
        """Configure the evaluation function for the critic agent."""
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, CriticAgent):
                agent.set_evaluation_function(evaluation_fn)

    def add_goal_criterion(
        self,
        name: str,
        evaluator: Callable[[Any], float]
    ) -> None:
        """Add a goal evaluation criterion."""
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, GoalEvaluatorAgent):
                agent.add_criterion(name, evaluator)

    def solve(
        self,
        problem: str,
        objective: str,
        constraints: Optional[List[str]] = None,
        max_iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Solve a problem through iterative multi-agent collaboration.

        Args:
            problem: Description of the problem
            objective: The goal to achieve
            constraints: Constraints that must be satisfied
            max_iterations: Maximum refinement iterations

        Returns:
            Solution dictionary with result and metadata
        """
        self.orchestrator.max_iterations = max_iterations

        task = Task(
            description=problem,
            objective=objective,
            constraints=constraints or [],
            max_iterations=max_iterations
        )

        result = self.orchestrator.execute_task(task, goal=objective)
        self.solutions[task.id] = result

        return result

    def get_solution_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Get the history of solutions for a task."""
        if task_id in self.solutions:
            return self.solutions[task_id].get('execution_log', [])
        return []

    def get_agent_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics from all agents."""
        return {
            agent_id: agent.get_status()
            for agent_id, agent in self.orchestrator.agents.items()
        }


# =============================================================================
# Demonstration and Examples
# =============================================================================

def demo_basic_usage():
    """Demonstrate basic usage of the multi-agent system."""
    print("\n" + "="*60)
    print("Multi-Agent System Demo: Basic Usage")
    print("="*60 + "\n")

    # Create the collaborative problem solver
    solver = CollaborativeProblemSolver()

    # Configure a custom execution function
    def simple_executor(task: Task) -> str:
        """Simple executor that generates a response."""
        return f"Solution for '{task.objective}': Implementing step-by-step approach"

    solver.configure_executor(simple_executor)

    # Solve a problem
    result = solver.solve(
        problem="Optimize the file organization algorithm",
        objective="Create an efficient file sorting strategy",
        constraints=["Must handle duplicates", "Must preserve original filenames"],
        max_iterations=5
    )

    print(f"Task ID: {result['task_id']}")
    print(f"Goal: {result['goal']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Converged: {result['converged']}")
    print(f"Final Result: {result['final_result']}")
    print(f"\nMetrics: {json.dumps(result['metrics'], indent=2)}")

    return result


def demo_custom_agents():
    """Demonstrate custom agent configuration."""
    print("\n" + "="*60)
    print("Multi-Agent System Demo: Custom Agents")
    print("="*60 + "\n")

    # Create orchestrator
    orchestrator = MultiAgentOrchestrator(max_iterations=3)

    # Create custom executor with domain-specific logic
    def code_review_executor(task: Task) -> Dict[str, Any]:
        return {
            'code_quality': 0.85,
            'issues_found': ['Missing docstring', 'Unused import'],
            'suggestions': ['Add type hints', 'Use f-strings']
        }

    executor = ExecutorAgent("CodeReviewer", execution_fn=code_review_executor)

    # Create custom critic with strict evaluation
    def strict_evaluator(result: ExecutionResult, task: Optional[Task]) -> Critique:
        output = result.output
        score = 0.0

        if isinstance(output, dict):
            score = output.get('code_quality', 0)

        return Critique(
            result_id=result.task_id,
            score=score,
            strengths=['Comprehensive review'] if score > 0.7 else [],
            weaknesses=['Quality below standard'] if score < 0.8 else [],
            suggestions=['Improve code quality'] if score < 0.9 else [],
            should_refine=score < 0.9
        )

    critic = CriticAgent("StrictReviewer", evaluation_fn=strict_evaluator)

    # Register agents
    orchestrator.register_agent(CoordinatorAgent())
    orchestrator.register_agent(executor)
    orchestrator.register_agent(critic)
    orchestrator.register_agent(GoalEvaluatorAgent())

    # Execute task
    task = Task(
        description="Review the authentication module",
        objective="Ensure code quality meets standards"
    )

    result = orchestrator.execute_task(task)

    print(f"Execution completed in {result['iterations']} iterations")
    print(f"Status: {orchestrator.get_status()}")

    return result


def demo_iterative_refinement():
    """Demonstrate iterative refinement process."""
    print("\n" + "="*60)
    print("Multi-Agent System Demo: Iterative Refinement")
    print("="*60 + "\n")

    # Track refinement iterations
    refinement_log = []

    # Create executor that improves over iterations
    iteration_state = {'count': 0}

    def improving_executor(task: Task) -> str:
        iteration_state['count'] += 1
        quality = min(0.6 + (iteration_state['count'] * 0.15), 1.0)

        result = f"Iteration {iteration_state['count']}: Quality = {quality:.2f}"
        refinement_log.append({
            'iteration': iteration_state['count'],
            'quality': quality
        })

        return result

    solver = CollaborativeProblemSolver()
    solver.configure_executor(improving_executor)

    # Add custom goal criterion
    solver.add_goal_criterion(
        'quality_metric',
        lambda r: 0.9 if r and 'Quality = 1.00' in str(r) else 0.5
    )

    result = solver.solve(
        problem="Generate high-quality documentation",
        objective="Create comprehensive API documentation",
        max_iterations=8
    )

    print("Refinement Progress:")
    for entry in refinement_log:
        bar = '█' * int(entry['quality'] * 20)
        print(f"  Iteration {entry['iteration']}: [{bar:<20}] {entry['quality']:.2f}")

    print(f"\nFinal iterations: {result['iterations']}")

    return result


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point demonstrating the multi-agent system."""
    print("\n" + "="*60)
    print("       MULTI-AGENT SYSTEM FRAMEWORK")
    print("   Collaborative AI for Iterative Problem Solving")
    print("="*60)

    # Run demonstrations
    demo_basic_usage()
    demo_custom_agents()
    demo_iterative_refinement()

    print("\n" + "="*60)
    print("Demonstrations complete!")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
