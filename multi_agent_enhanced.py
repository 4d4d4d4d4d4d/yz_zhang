#!/usr/bin/env python3
"""
Enhanced Multi-Agent System - Advanced framework with async support, persistence, and monitoring.

Enhancements over base version:
- Round 1: Async/await support for concurrent agent execution
- Round 2: Improved error handling with retry and circuit breaker
- Round 3: State persistence and checkpointing
- Round 4: Intelligent message routing with priority queues
- Round 5: Agent dependency management and DAG execution
- Round 6: Enhanced monitoring, metrics, and observability
- Round 7: Configuration management with hot reload
- Round 8: Agent pooling and load balancing
- Round 9: Event hooks and plugin system
- Round 10: Type safety, documentation, and code quality

Author: Multi-Agent System Framework
License: MIT
"""

from __future__ import annotations

import asyncio
import uuid
import time
import json
import logging
import pickle
import heapq
import functools
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, Generic,
    Awaitable, Union, Protocol, runtime_checkable, Type, NamedTuple
)
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
import threading
from concurrent.futures import ThreadPoolExecutor
import traceback
import copy
import hashlib

# Type variables
T = TypeVar('T')
AgentT = TypeVar('AgentT', bound='AsyncBaseAgent')


# =============================================================================
# Round 6: Enhanced Logging and Monitoring
# =============================================================================

class StructuredLogger:
    """Structured logging with context and metrics integration."""

    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self._logger = logging.getLogger(name)
        self._context = context or {}
        self._metrics_collector: Optional['MetricsCollector'] = None

    def bind(self, **kwargs) -> 'StructuredLogger':
        """Create a new logger with additional context."""
        new_context = {**self._context, **kwargs}
        new_logger = StructuredLogger(self._logger.name, new_context)
        new_logger._metrics_collector = self._metrics_collector
        return new_logger

    def set_metrics_collector(self, collector: 'MetricsCollector') -> None:
        self._metrics_collector = collector

    def _log(self, level: int, msg: str, **kwargs) -> None:
        extra = {**self._context, **kwargs}
        structured_msg = f"{msg} | {json.dumps(extra)}" if extra else msg
        self._logger.log(level, structured_msg)

    def debug(self, msg: str, **kwargs) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log(logging.ERROR, msg, **kwargs)
        if self._metrics_collector:
            self._metrics_collector.increment('errors_total')


class MetricsCollector:
    """Collects and aggregates metrics from agents and orchestrator."""

    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._start_time = time.time()

    def increment(self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._make_key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        if labels:
            label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            histogram_stats = {}
            for key, values in self._histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    histogram_stats[key] = {
                        'count': len(values),
                        'sum': sum(values),
                        'min': sorted_vals[0],
                        'max': sorted_vals[-1],
                        'avg': sum(values) / len(values),
                        'p50': sorted_vals[len(sorted_vals) // 2],
                        'p99': sorted_vals[int(len(sorted_vals) * 0.99)] if len(sorted_vals) > 1 else sorted_vals[0]
                    }

            return {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': histogram_stats,
                'uptime_seconds': time.time() - self._start_time
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global metrics collector
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics


# =============================================================================
# Enumerations and Constants (Enhanced)
# =============================================================================

class MessageType(Enum):
    """Types of messages exchanged between agents."""
    TASK = auto()
    RESULT = auto()
    CRITIQUE = auto()
    REFINEMENT = auto()
    QUERY = auto()
    RESPONSE = auto()
    STATUS = auto()
    TERMINATION = auto()
    ERROR = auto()          # New: Error notification
    HEARTBEAT = auto()      # New: Health check
    CHECKPOINT = auto()     # New: State checkpoint


class AgentState(Enum):
    """Possible states of an agent."""
    IDLE = auto()
    PROCESSING = auto()
    WAITING = auto()
    SUSPENDED = auto()      # New: Temporarily suspended
    ERROR = auto()          # New: In error state
    TERMINATED = auto()


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def __lt__(self, other: 'TaskPriority') -> bool:
        return self.value < other.value


class GoalStatus(Enum):
    """Status of goal achievement."""
    NOT_STARTED = auto()
    IN_PROGRESS = auto()
    PARTIALLY_ACHIEVED = auto()
    ACHIEVED = auto()
    FAILED = auto()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()     # Normal operation
    OPEN = auto()       # Failing, reject calls
    HALF_OPEN = auto()  # Testing recovery


# =============================================================================
# Round 2: Error Handling - Circuit Breaker and Retry
# =============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_successes = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_successes = 0
                else:
                    raise CircuitBreakerOpen("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_requests:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


async def retry_with_backoff(
    func: Callable[..., Awaitable[T]],
    config: RetryConfig = RetryConfig(),
    *args, **kwargs
) -> T:
    """Execute function with exponential backoff retry."""
    import random

    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt),
                    config.max_delay
                )
                if config.jitter:
                    delay *= (0.5 + random.random())

                await asyncio.sleep(delay)

    raise last_exception


# =============================================================================
# Round 9: Event Hooks and Plugin System
# =============================================================================

class EventType(Enum):
    """Types of events that can trigger hooks."""
    AGENT_STARTED = auto()
    AGENT_STOPPED = auto()
    MESSAGE_SENT = auto()
    MESSAGE_RECEIVED = auto()
    TASK_STARTED = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    ITERATION_STARTED = auto()
    ITERATION_COMPLETED = auto()
    GOAL_ACHIEVED = auto()
    ERROR_OCCURRED = auto()
    STATE_CHECKPOINTED = auto()


@dataclass
class Event:
    """Event data passed to hooks."""
    type: EventType
    source: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """Pub/sub event bus for hook system."""

    def __init__(self):
        self._handlers: Dict[EventType, List[Callable[[Event], Awaitable[None]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Awaitable[None]]
    ) -> None:
        """Subscribe to an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Awaitable[None]]
    ) -> None:
        """Unsubscribe from an event type."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logging.error(f"Event handler error: {e}")


@runtime_checkable
class Plugin(Protocol):
    """Protocol for plugins."""

    @property
    def name(self) -> str: ...

    async def initialize(self, orchestrator: 'AsyncMultiAgentOrchestrator') -> None: ...

    async def shutdown(self) -> None: ...


class PluginManager:
    """Manages plugins for the multi-agent system."""

    def __init__(self, orchestrator: 'AsyncMultiAgentOrchestrator'):
        self.orchestrator = orchestrator
        self._plugins: Dict[str, Plugin] = {}

    async def register(self, plugin: Plugin) -> None:
        """Register and initialize a plugin."""
        await plugin.initialize(self.orchestrator)
        self._plugins[plugin.name] = plugin

    async def unregister(self, name: str) -> None:
        """Unregister and shutdown a plugin."""
        if name in self._plugins:
            await self._plugins[name].shutdown()
            del self._plugins[name]

    async def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for plugin in self._plugins.values():
            await plugin.shutdown()
        self._plugins.clear()


# =============================================================================
# Round 7: Configuration Management
# =============================================================================

@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    enabled: bool = True
    max_queue_size: int = 1000
    processing_timeout: float = 60.0
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    custom_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    max_iterations: int = 10
    convergence_threshold: float = 0.9
    checkpoint_interval: int = 5
    checkpoint_path: Optional[str] = None
    enable_metrics: bool = True
    enable_persistence: bool = False
    agent_configs: Dict[str, AgentConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrchestratorConfig':
        agent_configs = {}
        for name, config in data.get('agent_configs', {}).items():
            if 'retry_config' in config:
                config['retry_config'] = RetryConfig(**config['retry_config'])
            agent_configs[name] = AgentConfig(**config)
        data['agent_configs'] = agent_configs
        return cls(**data)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> 'OrchestratorConfig':
        path = Path(path)
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['agent_configs'] = {
            name: asdict(config) for name, config in self.agent_configs.items()
        }
        return result


class ConfigWatcher:
    """Watches configuration file for changes and triggers reload."""

    def __init__(self, path: Path, callback: Callable[[OrchestratorConfig], Awaitable[None]]):
        self.path = path
        self.callback = callback
        self._last_mtime: Optional[float] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                mtime = self.path.stat().st_mtime
                if self._last_mtime is not None and mtime != self._last_mtime:
                    config = OrchestratorConfig.from_file(self.path)
                    await self.callback(config)
                self._last_mtime = mtime
            except Exception as e:
                logging.error(f"Config watch error: {e}")
            await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False


# =============================================================================
# Round 4: Priority Queue for Messages
# =============================================================================

@dataclass(order=True)
class PrioritizedMessage:
    """Message wrapper with priority for queue ordering."""
    priority: int
    timestamp: float = field(compare=True)
    message: 'Message' = field(compare=False)


class AsyncPriorityQueue:
    """Async-compatible priority queue."""

    def __init__(self, maxsize: int = 0):
        self._heap: List[PrioritizedMessage] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition(self._lock)
        self._maxsize = maxsize

    async def put(self, message: 'Message', priority: int = 0) -> None:
        async with self._lock:
            if self._maxsize > 0 and len(self._heap) >= self._maxsize:
                # Remove lowest priority item
                heapq.heappop(self._heap)
            item = PrioritizedMessage(-priority, time.time(), message)  # Negate for max-heap
            heapq.heappush(self._heap, item)
            self._not_empty.notify()

    async def get(self, timeout: Optional[float] = None) -> 'Message':
        async with self._not_empty:
            while not self._heap:
                try:
                    await asyncio.wait_for(self._not_empty.wait(), timeout)
                except asyncio.TimeoutError:
                    raise asyncio.QueueEmpty()
            return heapq.heappop(self._heap).message

    def qsize(self) -> int:
        return len(self._heap)

    def empty(self) -> bool:
        return len(self._heap) == 0


# =============================================================================
# Core Data Structures (Enhanced)
# =============================================================================

@dataclass
class Message:
    """Enhanced message with priority and tracing."""
    type: MessageType
    sender_id: str
    content: Any
    receiver_id: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type.name,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'priority': self.priority.name,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat(),
            'reply_to': self.reply_to,
            'trace_id': self.trace_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            id=data['id'],
            type=MessageType[data['type']],
            sender_id=data['sender_id'],
            receiver_id=data.get('receiver_id'),
            priority=TaskPriority[data.get('priority', 'MEDIUM')],
            content=data['content'],
            metadata=data.get('metadata', {}),
            timestamp=datetime.fromisoformat(data['timestamp']),
            reply_to=data.get('reply_to'),
            trace_id=data.get('trace_id', uuid.uuid4().hex[:16])
        )


@dataclass
class Task:
    """Enhanced task with dependencies and timeout."""
    description: str
    objective: str
    constraints: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    max_iterations: int = 5
    timeout: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    success_criteria: Dict[str, Any] = field(default_factory=dict)
    subtasks: List['Task'] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.now)

    def decompose(self, parts: List[Tuple[str, str]]) -> List['Task']:
        self.subtasks = [
            Task(description=desc, objective=obj, priority=self.priority)
            for desc, obj in parts
        ]
        return self.subtasks

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'description': self.description,
            'objective': self.objective,
            'constraints': self.constraints,
            'priority': self.priority.name,
            'max_iterations': self.max_iterations,
            'timeout': self.timeout,
            'dependencies': self.dependencies,
            'success_criteria': self.success_criteria,
            'created_at': self.created_at.isoformat()
        }


@dataclass
class ExecutionResult:
    """Enhanced execution result with timing and errors."""
    task_id: str
    output: Any
    confidence: float = 0.5
    reasoning: str = ""
    iteration: int = 1
    metrics: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'output': self.output,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'iteration': self.iteration,
            'metrics': self.metrics,
            'error': self.error,
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionResult':
        data = data.copy()
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class Critique:
    """Critique/feedback on execution result."""
    result_id: str
    score: float
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    should_refine: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GoalEvaluation:
    """Evaluation of goal achievement."""
    goal: str
    status: GoalStatus
    progress: float
    metrics: Dict[str, float] = field(default_factory=dict)
    gaps: List[str] = field(default_factory=list)
    recommendation: str = ""


# =============================================================================
# Round 3: State Persistence
# =============================================================================

@dataclass
class AgentCheckpoint:
    """Checkpoint of agent state."""
    agent_id: str
    agent_type: str
    state: AgentState
    metrics: Dict[str, Any]
    custom_state: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrchestratorCheckpoint:
    """Checkpoint of orchestrator state."""
    iteration_count: int
    metrics: Dict[str, Any]
    agent_checkpoints: List[AgentCheckpoint]
    pending_messages: List[Dict[str, Any]]
    timestamp: datetime = field(default_factory=datetime.now)


class StatePersistence:
    """Handles state persistence and recovery."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path("./checkpoints")
        self.path.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(self, checkpoint: OrchestratorCheckpoint) -> str:
        """Save checkpoint to disk."""
        checkpoint_id = f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filepath = self.path / f"{checkpoint_id}.pkl"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_checkpoint, filepath, checkpoint)

        return checkpoint_id

    def _write_checkpoint(self, filepath: Path, checkpoint: OrchestratorCheckpoint) -> None:
        with open(filepath, 'wb') as f:
            pickle.dump(checkpoint, f)

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[OrchestratorCheckpoint]:
        """Load checkpoint from disk."""
        filepath = self.path / f"{checkpoint_id}.pkl"
        if not filepath.exists():
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_checkpoint, filepath)

    def _read_checkpoint(self, filepath: Path) -> OrchestratorCheckpoint:
        with open(filepath, 'rb') as f:
            return pickle.load(f)

    async def list_checkpoints(self) -> List[str]:
        """List available checkpoints."""
        return [f.stem for f in self.path.glob("checkpoint_*.pkl")]

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        filepath = self.path / f"{checkpoint_id}.pkl"
        if filepath.exists():
            filepath.unlink()
            return True
        return False


# =============================================================================
# Round 1: Async Agent Base Class
# =============================================================================

class AsyncBaseAgent(ABC):
    """
    Async-capable base class for all agents.

    Enhancements:
    - Full async/await support
    - Circuit breaker integration
    - Enhanced metrics
    - Event publishing
    """

    def __init__(
        self,
        name: str,
        agent_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        config: Optional[AgentConfig] = None
    ):
        self.name = name
        self.id = agent_id or f"{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        self.capabilities = capabilities or []
        self.config = config or AgentConfig(name=name)
        self.state = AgentState.IDLE

        # Async message queue with priority
        self.message_queue = AsyncPriorityQueue(maxsize=self.config.max_queue_size)
        self.message_history: List[Message] = []

        # Logging
        self.logger = StructuredLogger(f"Agent.{self.name}")
        self.logger.set_metrics_collector(get_metrics())

        # State
        self._running = False
        self._lock = asyncio.Lock()
        self._circuit_breaker = CircuitBreaker()

        # Event bus reference (set by orchestrator)
        self._event_bus: Optional[EventBus] = None

        # Metrics
        self.metrics = {
            'messages_processed': 0,
            'tasks_completed': 0,
            'total_processing_time': 0.0,
            'errors': 0,
            'avg_processing_time': 0.0
        }

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Set event bus for publishing events."""
        self._event_bus = event_bus

    async def _publish_event(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """Publish event if event bus is configured."""
        if self._event_bus:
            event = Event(type=event_type, source=self.id, data=data)
            await self._event_bus.publish(event)

    async def receive_message(self, message: Message) -> None:
        """Receive and queue a message for processing."""
        await self.message_queue.put(message, message.priority.value)
        self.message_history.append(message)
        self.logger.debug("Received message", message_id=message.id, from_agent=message.sender_id)
        await self._publish_event(EventType.MESSAGE_RECEIVED, {'message_id': message.id})

    def send_message(
        self,
        msg_type: MessageType,
        content: Any,
        receiver_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Create and return a message to be sent."""
        message = Message(
            type=msg_type,
            sender_id=self.id,
            receiver_id=receiver_id,
            content=content,
            reply_to=reply_to,
            priority=priority,
            metadata=metadata or {}
        )
        self.message_history.append(message)
        return message

    @abstractmethod
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a received message and optionally return a response."""
        pass

    async def run_once(self, timeout: float = 0.1) -> Optional[Message]:
        """Process one message from the queue."""
        try:
            message = await asyncio.wait_for(
                self.message_queue.get(timeout=timeout),
                timeout=timeout
            )
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

        async with self._lock:
            self.state = AgentState.PROCESSING

        start_time = time.time()
        response = None

        try:
            # Use circuit breaker for processing
            response = await self._circuit_breaker.call(
                self._process_with_timeout,
                message
            )

            processing_time = time.time() - start_time
            self.metrics['messages_processed'] += 1
            self.metrics['total_processing_time'] += processing_time
            self.metrics['avg_processing_time'] = (
                self.metrics['total_processing_time'] / self.metrics['messages_processed']
            )

            get_metrics().histogram(
                'agent_processing_time_seconds',
                processing_time,
                {'agent': self.name}
            )

        except CircuitBreakerOpen:
            self.logger.warning("Circuit breaker open, message rejected")
            self.metrics['errors'] += 1
        except asyncio.TimeoutError:
            self.logger.error("Message processing timeout")
            self.metrics['errors'] += 1
        except Exception as e:
            self.metrics['errors'] += 1
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            await self._publish_event(EventType.ERROR_OCCURRED, {
                'error': str(e),
                'message_id': message.id
            })
        finally:
            async with self._lock:
                self.state = AgentState.IDLE

        return response

    async def _process_with_timeout(self, message: Message) -> Optional[Message]:
        """Process message with timeout."""
        return await asyncio.wait_for(
            self.process_message(message),
            timeout=self.config.processing_timeout
        )

    async def run(self, max_iterations: Optional[int] = None) -> None:
        """Run the agent's message processing loop."""
        self._running = True
        await self._publish_event(EventType.AGENT_STARTED, {'agent_id': self.id})
        iterations = 0

        while self._running:
            if max_iterations and iterations >= max_iterations:
                break

            await self.run_once()
            iterations += 1
            await asyncio.sleep(0.001)  # Yield to event loop

        await self._publish_event(EventType.AGENT_STOPPED, {'agent_id': self.id})

    async def stop(self) -> None:
        """Stop the agent's processing loop."""
        self._running = False
        async with self._lock:
            self.state = AgentState.TERMINATED

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state.name,
            'queue_size': self.message_queue.qsize(),
            'metrics': self.metrics.copy(),
            'circuit_breaker': self._circuit_breaker.state.name
        }

    def get_checkpoint_state(self) -> Dict[str, Any]:
        """Get state for checkpointing. Override in subclasses."""
        return {}

    def restore_from_checkpoint(self, state: Dict[str, Any]) -> None:
        """Restore state from checkpoint. Override in subclasses."""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name})"


# =============================================================================
# Round 5: Dependency Management
# =============================================================================

class DependencyGraph:
    """Manages task dependencies as a DAG."""

    def __init__(self):
        self._dependencies: Dict[str, Set[str]] = defaultdict(set)
        self._dependents: Dict[str, Set[str]] = defaultdict(set)
        self._completed: Set[str] = set()

    def add_task(self, task_id: str, dependencies: List[str]) -> None:
        """Add a task with its dependencies."""
        for dep in dependencies:
            self._dependencies[task_id].add(dep)
            self._dependents[dep].add(task_id)

    def mark_completed(self, task_id: str) -> List[str]:
        """Mark task as completed and return newly unblocked tasks."""
        self._completed.add(task_id)
        unblocked = []

        for dependent in self._dependents.get(task_id, []):
            if self.is_ready(dependent):
                unblocked.append(dependent)

        return unblocked

    def is_ready(self, task_id: str) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in self._completed for dep in self._dependencies.get(task_id, []))

    def get_ready_tasks(self, all_tasks: List[str]) -> List[str]:
        """Get all tasks that are ready to execute."""
        return [t for t in all_tasks if self.is_ready(t) and t not in self._completed]

    def has_cycle(self) -> bool:
        """Detect if there's a cycle in the dependency graph."""
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for dep in self._dependencies.get(node, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in self._dependencies:
            if node not in visited:
                if dfs(node):
                    return True

        return False


# =============================================================================
# Round 8: Agent Pool and Load Balancing
# =============================================================================

class LoadBalancingStrategy(Enum):
    """Load balancing strategies for agent pools."""
    ROUND_ROBIN = auto()
    LEAST_LOADED = auto()
    RANDOM = auto()
    WEIGHTED = auto()


class AgentPool(Generic[AgentT]):
    """Pool of agents with load balancing."""

    def __init__(
        self,
        agent_factory: Callable[[], AgentT],
        min_size: int = 1,
        max_size: int = 10,
        strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_LOADED
    ):
        self.agent_factory = agent_factory
        self.min_size = min_size
        self.max_size = max_size
        self.strategy = strategy

        self._agents: List[AgentT] = []
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

        # Initialize minimum agents
        for _ in range(min_size):
            self._agents.append(agent_factory())

    async def get_agent(self) -> AgentT:
        """Get an agent based on load balancing strategy."""
        async with self._lock:
            if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                agent = self._agents[self._round_robin_index % len(self._agents)]
                self._round_robin_index += 1
                return agent

            elif self.strategy == LoadBalancingStrategy.LEAST_LOADED:
                return min(self._agents, key=lambda a: a.message_queue.qsize())

            elif self.strategy == LoadBalancingStrategy.RANDOM:
                import random
                return random.choice(self._agents)

            else:
                return self._agents[0]

    async def scale_up(self) -> Optional[AgentT]:
        """Add a new agent to the pool."""
        async with self._lock:
            if len(self._agents) < self.max_size:
                agent = self.agent_factory()
                self._agents.append(agent)
                return agent
            return None

    async def scale_down(self) -> Optional[AgentT]:
        """Remove an agent from the pool."""
        async with self._lock:
            if len(self._agents) > self.min_size:
                # Remove least loaded agent
                agent = min(self._agents, key=lambda a: a.message_queue.qsize())
                self._agents.remove(agent)
                return agent
            return None

    @property
    def size(self) -> int:
        return len(self._agents)

    @property
    def agents(self) -> List[AgentT]:
        return list(self._agents)


# =============================================================================
# Specialized Async Agent Implementations
# =============================================================================

class AsyncCoordinatorAgent(AsyncBaseAgent):
    """Async coordinator agent with dependency management."""

    def __init__(self, name: str = "Coordinator"):
        super().__init__(name, capabilities=['task_decomposition', 'orchestration', 'aggregation'])
        self.active_tasks: Dict[str, Task] = {}
        self.task_assignments: Dict[str, str] = {}
        self.results: Dict[str, List[ExecutionResult]] = defaultdict(list)
        self.dependency_graph = DependencyGraph()
        self.decomposition_strategy: Optional[Callable[[Task], List[Tuple[str, str]]]] = None

    def set_decomposition_strategy(self, strategy: Callable[[Task], List[Tuple[str, str]]]) -> None:
        self.decomposition_strategy = strategy

    def decompose_task(self, task: Task) -> List[Task]:
        if self.decomposition_strategy:
            parts = self.decomposition_strategy(task)
        else:
            parts = [(task.description, task.objective)]
        return task.decompose(parts)

    async def process_message(self, message: Message) -> Optional[Message]:
        if message.type == MessageType.TASK:
            task = message.content

            if isinstance(task, dict) and 'parent_task' in task:
                return None

            if isinstance(task, dict):
                task_fields = {'description', 'objective', 'constraints', 'priority',
                              'max_iterations', 'success_criteria', 'subtasks', 'id',
                              'timeout', 'dependencies'}
                filtered_task = {k: v for k, v in task.items() if k in task_fields}
                if 'priority' in filtered_task and isinstance(filtered_task['priority'], str):
                    filtered_task['priority'] = TaskPriority[filtered_task['priority']]
                task = Task(**filtered_task)

            self.active_tasks[task.id] = task

            # Add to dependency graph
            self.dependency_graph.add_task(task.id, task.dependencies)

            subtasks = self.decompose_task(task)
            self.logger.info(f"Decomposed task {task.id} into {len(subtasks)} subtasks")

            await self._publish_event(EventType.TASK_STARTED, {'task_id': task.id})

            return self.send_message(
                MessageType.TASK,
                {'parent_task': task.id, 'subtasks': [st.to_dict() for st in subtasks]},
                priority=task.priority,
                metadata={'requires_distribution': True}
            )

        elif message.type == MessageType.RESULT:
            result = message.content
            if isinstance(result, dict):
                result = ExecutionResult.from_dict(result)

            self.results[result.task_id].append(result)

            # Mark completed in dependency graph
            unblocked = self.dependency_graph.mark_completed(result.task_id)
            if unblocked:
                self.logger.info(f"Tasks unblocked: {unblocked}")

            self.logger.info(
                f"Received result for task {result.task_id} "
                f"(iteration {result.iteration}, confidence: {result.confidence:.2f})"
            )

            return self.send_message(
                MessageType.RESULT,
                result.to_dict(),
                metadata={'requires_critique': True}
            )

        elif message.type == MessageType.STATUS:
            self.logger.debug(f"Status update: {message.content}")
            return None

        return None

    def aggregate_results(self, task_id: str) -> Optional[ExecutionResult]:
        if task_id not in self.results:
            return None
        results = self.results[task_id]
        if not results:
            return None
        return max(results, key=lambda r: r.confidence)

    def get_checkpoint_state(self) -> Dict[str, Any]:
        return {
            'active_tasks': {k: v.to_dict() for k, v in self.active_tasks.items()},
            'results': {k: [r.to_dict() for r in v] for k, v in self.results.items()}
        }


class AsyncExecutorAgent(AsyncBaseAgent):
    """Async executor agent with retry support."""

    def __init__(
        self,
        name: str = "Executor",
        execution_fn: Optional[Callable[[Task], Awaitable[Any]]] = None
    ):
        super().__init__(name, capabilities=['task_execution', 'refinement'])
        self.current_task: Optional[Task] = None
        self._execution_fn = execution_fn
        self.refinement_history: List[Tuple[ExecutionResult, Critique]] = []

    async def _default_execution(self, task: Task) -> Any:
        return f"Executed: {task.objective}"

    def set_execution_function(self, fn: Callable[[Task], Any]) -> None:
        self._execution_fn = fn

    async def execute_task(self, task: Task, iteration: int = 1) -> ExecutionResult:
        self.current_task = task
        start_time = time.time()

        try:
            if self._execution_fn:
                if asyncio.iscoroutinefunction(self._execution_fn):
                    output = await self._execution_fn(task)
                else:
                    output = self._execution_fn(task)
            else:
                output = await self._default_execution(task)

            execution_time = time.time() - start_time
            confidence = self._calculate_confidence(output, task)

            result = ExecutionResult(
                task_id=task.id,
                output=output,
                confidence=confidence,
                reasoning=f"Executed task: {task.description}",
                iteration=iteration,
                execution_time=execution_time,
                metrics={'output_length': len(str(output)) if output else 0}
            )

            self.metrics['tasks_completed'] += 1
            await self._publish_event(EventType.TASK_COMPLETED, {
                'task_id': task.id,
                'confidence': confidence
            })

            return result

        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            await self._publish_event(EventType.TASK_FAILED, {
                'task_id': task.id,
                'error': str(e)
            })

            return ExecutionResult(
                task_id=task.id,
                output=None,
                confidence=0.0,
                reasoning=f"Execution failed: {str(e)}",
                iteration=iteration,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _calculate_confidence(self, output: Any, task: Task) -> float:
        confidence = 0.5
        if output is not None:
            confidence += 0.2
        if output and isinstance(output, str) and len(output) > 10:
            confidence += 0.1
        if not task.constraints:
            confidence += 0.1
        return min(confidence, 1.0)

    def refine_result(self, result: ExecutionResult, critique: Critique) -> ExecutionResult:
        self.refinement_history.append((result, critique))

        refined_output = result.output
        if isinstance(refined_output, str) and critique.suggestions:
            refined_output = f"{refined_output}\n[Refined based on: {'; '.join(critique.suggestions)}]"

        new_confidence = min(result.confidence + 0.1, 1.0)

        return ExecutionResult(
            task_id=result.task_id,
            output=refined_output,
            confidence=new_confidence,
            reasoning=f"Refined from iteration {result.iteration}",
            iteration=result.iteration + 1,
            metrics={**result.metrics, 'refinement_applied': True}
        )

    async def process_message(self, message: Message) -> Optional[Message]:
        if message.type == MessageType.TASK:
            task_data = message.content

            if isinstance(task_data, dict) and 'parent_task' in task_data:
                subtasks = task_data.get('subtasks', [])
                if subtasks:
                    task_fields = {'description', 'objective', 'constraints', 'priority',
                                  'max_iterations', 'success_criteria', 'subtasks', 'id'}
                    filtered = {k: v for k, v in subtasks[0].items() if k in task_fields}
                    if 'priority' in filtered and isinstance(filtered['priority'], str):
                        filtered['priority'] = TaskPriority[filtered['priority']]
                    task = Task(**filtered)
                else:
                    return None
            elif isinstance(task_data, dict):
                task_fields = {'description', 'objective', 'constraints', 'priority',
                              'max_iterations', 'success_criteria', 'subtasks', 'id'}
                filtered_task = {k: v for k, v in task_data.items() if k in task_fields}
                if 'priority' in filtered_task and isinstance(filtered_task['priority'], str):
                    filtered_task['priority'] = TaskPriority[filtered_task['priority']]
                task = Task(**filtered_task)
            else:
                task = task_data

            result = await self.execute_task(task)

            return self.send_message(
                MessageType.RESULT,
                result.to_dict(),
                reply_to=message.id
            )

        elif message.type == MessageType.CRITIQUE:
            critique_data = message.content
            if isinstance(critique_data, dict):
                critique = Critique(**critique_data)
            else:
                critique = critique_data

            if self.refinement_history:
                last_result, _ = self.refinement_history[-1]
            else:
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


class AsyncCriticAgent(AsyncBaseAgent):
    """Async critic agent."""

    def __init__(
        self,
        name: str = "Critic",
        evaluation_fn: Optional[Callable[[ExecutionResult, Optional[Task]], Critique]] = None
    ):
        super().__init__(name, capabilities=['evaluation', 'feedback', 'quality_assessment'])
        self._evaluation_fn = evaluation_fn
        self.evaluation_history: List[Critique] = []
        self.quality_threshold = 0.8

    def _default_evaluation(self, result: ExecutionResult, task: Optional[Task] = None) -> Critique:
        score = result.confidence
        strengths = []
        weaknesses = []
        suggestions = []

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

    def set_evaluation_function(self, fn: Callable[[ExecutionResult, Optional[Task]], Critique]) -> None:
        self._evaluation_fn = fn

    def evaluate(self, result: ExecutionResult, task: Optional[Task] = None) -> Critique:
        if self._evaluation_fn:
            critique = self._evaluation_fn(result, task)
        else:
            critique = self._default_evaluation(result, task)

        self.evaluation_history.append(critique)
        self.logger.info(
            f"Evaluated result {result.task_id}: score={critique.score:.2f}, should_refine={critique.should_refine}"
        )
        return critique

    async def process_message(self, message: Message) -> Optional[Message]:
        if message.type == MessageType.RESULT:
            result_data = message.content
            if isinstance(result_data, dict):
                result = ExecutionResult.from_dict(result_data)
            else:
                result = result_data

            critique = self.evaluate(result)

            return self.send_message(
                MessageType.CRITIQUE,
                critique.to_dict(),
                reply_to=message.id
            )

        return None


class AsyncRefinementAgent(AsyncBaseAgent):
    """Async refinement agent."""

    def __init__(self, name: str = "Refiner"):
        super().__init__(name, capabilities=['refinement', 'improvement', 'iteration'])
        self.refinement_count: Dict[str, int] = defaultdict(int)
        self.max_refinements = 5
        self.improvement_strategies: List[Callable[[Any, Critique], Any]] = []

    def add_improvement_strategy(self, strategy: Callable[[Any, Critique], Any]) -> None:
        self.improvement_strategies.append(strategy)

    def refine(self, result: ExecutionResult, critique: Critique) -> ExecutionResult:
        task_id = result.task_id
        self.refinement_count[task_id] += 1

        if self.refinement_count[task_id] > self.max_refinements:
            self.logger.warning(f"Max refinements ({self.max_refinements}) reached for task {task_id}")
            return result

        refined_output = result.output

        for strategy in self.improvement_strategies:
            try:
                refined_output = strategy(refined_output, critique)
            except Exception as e:
                self.logger.error(f"Strategy failed: {e}")

        if not self.improvement_strategies and isinstance(refined_output, str):
            for suggestion in critique.suggestions:
                refined_output = f"{refined_output}\n- Addressed: {suggestion}"

        return ExecutionResult(
            task_id=task_id,
            output=refined_output,
            confidence=min(result.confidence + 0.15, 1.0),
            reasoning=f"Refinement #{self.refinement_count[task_id]}",
            iteration=result.iteration + 1,
            metrics={**result.metrics, 'refinement_iteration': self.refinement_count[task_id]}
        )

    async def process_message(self, message: Message) -> Optional[Message]:
        if message.type == MessageType.CRITIQUE:
            content = message.content
            if isinstance(content, dict) and 'result' in content and 'critique' in content:
                result = ExecutionResult.from_dict(content['result'])
                critique = Critique(**content['critique'])
            else:
                if isinstance(content, dict):
                    critique = Critique(**content)
                else:
                    critique = content
                result = ExecutionResult(task_id=critique.result_id, output="", iteration=0)

            if critique.should_refine:
                refined = self.refine(result, critique)
                return self.send_message(
                    MessageType.REFINEMENT,
                    refined.to_dict(),
                    reply_to=message.id
                )

        return None


class AsyncGoalEvaluatorAgent(AsyncBaseAgent):
    """Async goal evaluator agent."""

    def __init__(self, name: str = "GoalEvaluator"):
        super().__init__(name, capabilities=['goal_evaluation', 'progress_tracking', 'convergence_detection'])
        self.goal_history: Dict[str, List[GoalEvaluation]] = defaultdict(list)
        self.convergence_threshold = 0.95
        self.evaluation_criteria: Dict[str, Callable[[Any], float]] = {}

    def add_criterion(self, name: str, evaluator: Callable[[Any], float]) -> None:
        self.evaluation_criteria[name] = evaluator

    def evaluate_goal(self, goal: str, current_result: Any, task: Optional[Task] = None) -> GoalEvaluation:
        metrics = {}

        for name, evaluator in self.evaluation_criteria.items():
            try:
                metrics[name] = evaluator(current_result)
            except Exception as e:
                self.logger.error(f"Criterion {name} failed: {e}")
                metrics[name] = 0.0

        if metrics:
            progress = sum(metrics.values()) / len(metrics) * 100
        else:
            if current_result is None:
                progress = 0.0
            elif isinstance(current_result, ExecutionResult):
                progress = current_result.confidence * 100
            else:
                progress = 50.0

        if progress >= 95:
            status = GoalStatus.ACHIEVED
        elif progress >= 70:
            status = GoalStatus.PARTIALLY_ACHIEVED
        elif progress > 0:
            status = GoalStatus.IN_PROGRESS
        else:
            status = GoalStatus.NOT_STARTED

        gaps = []
        if progress < 100:
            if not current_result:
                gaps.append("No result produced yet")
            elif isinstance(current_result, ExecutionResult):
                if current_result.confidence < 0.8:
                    gaps.append("Confidence below threshold")
                if not current_result.reasoning:
                    gaps.append("Missing reasoning")

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
        history = self.goal_history.get(goal, [])

        if len(history) < 2:
            return False

        recent = history[-3:] if len(history) >= 3 else history
        progress_values = [e.progress for e in recent]

        if all(abs(p - progress_values[-1]) < 2.0 for p in progress_values):
            return progress_values[-1] >= self.convergence_threshold * 100

        return False

    async def process_message(self, message: Message) -> Optional[Message]:
        if message.type == MessageType.RESULT:
            content = message.content
            if isinstance(content, dict):
                goal = content.get('goal', 'default_goal')
                result = content.get('result')
                if isinstance(result, dict):
                    result = ExecutionResult.from_dict(result)
            else:
                goal = 'default_goal'
                result = content

            evaluation = self.evaluate_goal(goal, result)
            converged = self.check_convergence(goal)

            if evaluation.status == GoalStatus.ACHIEVED:
                await self._publish_event(EventType.GOAL_ACHIEVED, {'goal': goal})

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
# Enhanced Async Orchestrator
# =============================================================================

class AsyncMultiAgentOrchestrator:
    """
    Enhanced async orchestrator with all improvements.

    Features:
    - Async agent execution
    - State persistence
    - Event hooks
    - Load balancing
    - Comprehensive monitoring
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self.agents: Dict[str, AsyncBaseAgent] = {}
        self.agent_pools: Dict[str, AgentPool] = {}
        self.iteration_count = 0
        self.execution_log: List[Dict[str, Any]] = []

        # Logging and monitoring
        self.logger = StructuredLogger("Orchestrator")
        self.logger.set_metrics_collector(get_metrics())
        self.metrics_collector = get_metrics()

        # Event system
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager(self)

        # Persistence
        self.persistence = StatePersistence(
            Path(self.config.checkpoint_path) if self.config.checkpoint_path else None
        )

        # State
        self._running = False
        self._lock = asyncio.Lock()

    def register_agent(self, agent: AsyncBaseAgent) -> None:
        agent.set_event_bus(self.event_bus)
        self.agents[agent.id] = agent
        self.logger.info(f"Registered agent: {agent.name}", agent_id=agent.id)

    def unregister_agent(self, agent_id: str) -> Optional[AsyncBaseAgent]:
        agent = self.agents.pop(agent_id, None)
        if agent:
            self.logger.info(f"Unregistered agent: {agent.name}")
        return agent

    async def route_message(self, message: Message) -> None:
        self.metrics_collector.increment('messages_routed_total')

        self.execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'event': 'message_routed',
            'message_id': message.id,
            'type': message.type.name,
            'from': message.sender_id,
            'to': message.receiver_id or 'broadcast',
            'trace_id': message.trace_id
        })

        if message.receiver_id:
            if message.receiver_id in self.agents:
                await self.agents[message.receiver_id].receive_message(message)
        else:
            await self._route_by_type(message)

    async def _route_by_type(self, message: Message) -> None:
        routing_rules = {
            MessageType.TASK: ['task_decomposition', 'orchestration', 'task_execution'],
            MessageType.RESULT: ['evaluation', 'quality_assessment', 'goal_evaluation'],
            MessageType.CRITIQUE: ['refinement', 'improvement', 'task_execution'],
            MessageType.REFINEMENT: ['evaluation', 'goal_evaluation'],
            MessageType.STATUS: ['orchestration'],
        }

        target_capabilities = routing_rules.get(message.type, [])

        tasks = []
        for agent in self.agents.values():
            if any(cap in agent.capabilities for cap in target_capabilities):
                tasks.append(agent.receive_message(message))

        if tasks:
            await asyncio.gather(*tasks)

    def create_default_agents(self) -> None:
        coordinator = AsyncCoordinatorAgent()
        executor = AsyncExecutorAgent()
        critic = AsyncCriticAgent()
        refiner = AsyncRefinementAgent()
        goal_evaluator = AsyncGoalEvaluatorAgent()

        self.register_agent(coordinator)
        self.register_agent(executor)
        self.register_agent(critic)
        self.register_agent(refiner)
        self.register_agent(goal_evaluator)

    async def run_iteration(self) -> Dict[str, Any]:
        self.iteration_count += 1
        iteration_results = {
            'iteration': self.iteration_count,
            'messages_processed': 0,
            'agents_active': []
        }

        self.logger.info(f"=== Iteration {self.iteration_count} ===")

        await self.event_bus.publish(Event(
            type=EventType.ITERATION_STARTED,
            source="orchestrator",
            data={'iteration': self.iteration_count}
        ))

        tasks = []
        for agent_id, agent in self.agents.items():
            tasks.append(self._run_agent_once(agent, iteration_results))

        responses = await asyncio.gather(*tasks)

        # Route responses
        for response in responses:
            if response:
                await self.route_message(response)

        self.metrics_collector.increment('iterations_completed_total')

        await self.event_bus.publish(Event(
            type=EventType.ITERATION_COMPLETED,
            source="orchestrator",
            data={'iteration': self.iteration_count, 'results': iteration_results}
        ))

        # Checkpoint if needed
        if self.config.enable_persistence and self.iteration_count % self.config.checkpoint_interval == 0:
            await self.save_checkpoint()

        return iteration_results

    async def _run_agent_once(
        self,
        agent: AsyncBaseAgent,
        iteration_results: Dict[str, Any]
    ) -> Optional[Message]:
        response = await agent.run_once()
        if response:
            iteration_results['messages_processed'] += 1
            iteration_results['agents_active'].append(agent.id)
        return response

    async def execute_task(self, task: Task, goal: Optional[str] = None) -> Dict[str, Any]:
        goal = goal or task.objective
        self.logger.info(f"Starting task execution: {task.description}", goal=goal)

        initial_message = Message(
            type=MessageType.TASK,
            sender_id="orchestrator",
            content=task.to_dict(),
            priority=task.priority,
            metadata={'goal': goal}
        )
        await self.route_message(initial_message)

        converged = False
        final_result = None

        while self.iteration_count < self.config.max_iterations and not converged:
            await self.run_iteration()

            for agent in self.agents.values():
                if isinstance(agent, AsyncGoalEvaluatorAgent):
                    converged = agent.check_convergence(goal)
                    if converged:
                        self.metrics_collector.increment('goals_achieved_total')
                        self.logger.info("Goal converged!")
                        break

            await asyncio.sleep(0.01)

        for agent in self.agents.values():
            if isinstance(agent, AsyncCoordinatorAgent):
                final_result = agent.aggregate_results(task.id)
                break

        return {
            'task_id': task.id,
            'goal': goal,
            'iterations': self.iteration_count,
            'converged': converged,
            'final_result': final_result.to_dict() if final_result else None,
            'metrics': self.metrics_collector.get_metrics(),
            'execution_log': self.execution_log
        }

    async def save_checkpoint(self) -> str:
        agent_checkpoints = []
        for agent in self.agents.values():
            checkpoint = AgentCheckpoint(
                agent_id=agent.id,
                agent_type=agent.__class__.__name__,
                state=agent.state,
                metrics=agent.metrics.copy(),
                custom_state=agent.get_checkpoint_state()
            )
            agent_checkpoints.append(checkpoint)

        orchestrator_checkpoint = OrchestratorCheckpoint(
            iteration_count=self.iteration_count,
            metrics=self.metrics_collector.get_metrics(),
            agent_checkpoints=agent_checkpoints,
            pending_messages=[m.to_dict() for m in self.execution_log[-100:]]
        )

        checkpoint_id = await self.persistence.save_checkpoint(orchestrator_checkpoint)

        await self.event_bus.publish(Event(
            type=EventType.STATE_CHECKPOINTED,
            source="orchestrator",
            data={'checkpoint_id': checkpoint_id}
        ))

        self.logger.info(f"Checkpoint saved: {checkpoint_id}")
        return checkpoint_id

    def get_status(self) -> Dict[str, Any]:
        return {
            'iteration': self.iteration_count,
            'agents': {
                agent_id: agent.get_status()
                for agent_id, agent in self.agents.items()
            },
            'metrics': self.metrics_collector.get_metrics(),
            'config': self.config.to_dict()
        }

    def reset(self) -> None:
        self.iteration_count = 0
        self.execution_log.clear()
        for agent in self.agents.values():
            agent.message_queue = AsyncPriorityQueue(maxsize=agent.config.max_queue_size)
            agent.state = AgentState.IDLE
        self.metrics_collector.reset()


# =============================================================================
# High-Level API
# =============================================================================

class AsyncCollaborativeProblemSolver:
    """High-level async API for multi-agent problem solving."""

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.orchestrator = AsyncMultiAgentOrchestrator(config)
        self.orchestrator.create_default_agents()
        self.solutions: Dict[str, Any] = {}

    def configure_executor(self, execution_fn: Callable[[Task], Any]) -> None:
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, AsyncExecutorAgent):
                agent.set_execution_function(execution_fn)

    def configure_evaluator(
        self,
        evaluation_fn: Callable[[ExecutionResult, Optional[Task]], Critique]
    ) -> None:
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, AsyncCriticAgent):
                agent.set_evaluation_function(evaluation_fn)

    def add_goal_criterion(self, name: str, evaluator: Callable[[Any], float]) -> None:
        for agent in self.orchestrator.agents.values():
            if isinstance(agent, AsyncGoalEvaluatorAgent):
                agent.add_criterion(name, evaluator)

    def subscribe_event(
        self,
        event_type: EventType,
        handler: Callable[[Event], Awaitable[None]]
    ) -> None:
        self.orchestrator.event_bus.subscribe(event_type, handler)

    async def solve(
        self,
        problem: str,
        objective: str,
        constraints: Optional[List[str]] = None,
        max_iterations: int = 10,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        self.orchestrator.config.max_iterations = max_iterations

        task = Task(
            description=problem,
            objective=objective,
            constraints=constraints or [],
            max_iterations=max_iterations,
            timeout=timeout
        )

        if timeout:
            try:
                result = await asyncio.wait_for(
                    self.orchestrator.execute_task(task, goal=objective),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                result = {
                    'task_id': task.id,
                    'goal': objective,
                    'iterations': self.orchestrator.iteration_count,
                    'converged': False,
                    'final_result': None,
                    'error': 'Task timed out',
                    'metrics': self.orchestrator.metrics_collector.get_metrics()
                }
        else:
            result = await self.orchestrator.execute_task(task, goal=objective)

        self.solutions[task.id] = result
        return result

    def get_metrics(self) -> Dict[str, Any]:
        return self.orchestrator.metrics_collector.get_metrics()


# =============================================================================
# Demo
# =============================================================================

async def demo_async_system():
    """Demonstrate the enhanced async multi-agent system."""
    print("\n" + "="*60)
    print("Enhanced Multi-Agent System Demo (Async)")
    print("="*60 + "\n")

    # Create solver
    solver = AsyncCollaborativeProblemSolver()

    # Configure custom executor
    async def async_executor(task: Task) -> str:
        await asyncio.sleep(0.1)  # Simulate async work
        return f"Async solution for: {task.objective}"

    solver.configure_executor(async_executor)

    # Subscribe to events
    async def on_task_completed(event: Event):
        print(f"  [Event] Task completed: {event.data.get('task_id')}")

    solver.subscribe_event(EventType.TASK_COMPLETED, on_task_completed)

    # Solve
    result = await solver.solve(
        problem="Implement async multi-agent system",
        objective="Create efficient collaborative agents",
        constraints=["Must support async", "Must be scalable"],
        max_iterations=5
    )

    print(f"\nTask ID: {result['task_id']}")
    print(f"Goal: {result['goal']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Converged: {result['converged']}")
    print(f"\nMetrics: {json.dumps(solver.get_metrics(), indent=2, default=str)}")

    return result


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("    ENHANCED MULTI-AGENT SYSTEM FRAMEWORK")
    print("        10 Rounds of Optimization")
    print("="*60)

    asyncio.run(demo_async_system())

    print("\n" + "="*60)
    print("Demo complete!")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
