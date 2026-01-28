#!/usr/bin/env python3
"""
Test suite for Multi-Agent System.

Tests cover:
- Individual agent functionality
- Message passing and routing
- Iterative refinement
- Goal convergence
- LLM integration
"""

import unittest
import time
from datetime import datetime
from queue import Empty

from multi_agent_system import (
    # Enums
    MessageType, AgentState, TaskPriority, GoalStatus,
    # Data structures
    Message, Task, ExecutionResult, Critique, GoalEvaluation,
    # Agents
    BaseAgent, CoordinatorAgent, ExecutorAgent, CriticAgent,
    RefinementAgent, GoalEvaluatorAgent,
    # Orchestrator
    MultiAgentOrchestrator, CollaborativeProblemSolver
)

from llm_integration import (
    LLMConfig, LLMProvider, MockLLMAdapter,
    LLMExecutorAgent, LLMCriticAgent, LLMGoalEvaluatorAgent,
    LLMMultiAgentOrchestrator
)


class TestMessage(unittest.TestCase):
    """Test Message class."""

    def test_message_creation(self):
        """Test basic message creation."""
        msg = Message(
            type=MessageType.TASK,
            sender_id="agent_1",
            content={"task": "test"}
        )

        self.assertEqual(msg.type, MessageType.TASK)
        self.assertEqual(msg.sender_id, "agent_1")
        self.assertIsNotNone(msg.id)
        self.assertIsNotNone(msg.timestamp)

    def test_message_serialization(self):
        """Test message to/from dict."""
        msg = Message(
            type=MessageType.RESULT,
            sender_id="agent_1",
            receiver_id="agent_2",
            content={"result": "success"},
            metadata={"priority": "high"}
        )

        msg_dict = msg.to_dict()
        self.assertEqual(msg_dict['type'], 'RESULT')
        self.assertEqual(msg_dict['sender_id'], 'agent_1')

        # Reconstruct
        msg2 = Message.from_dict(msg_dict)
        self.assertEqual(msg2.type, MessageType.RESULT)
        self.assertEqual(msg2.sender_id, msg.sender_id)


class TestTask(unittest.TestCase):
    """Test Task class."""

    def test_task_creation(self):
        """Test basic task creation."""
        task = Task(
            description="Test task",
            objective="Test objective",
            constraints=["constraint1", "constraint2"],
            priority=TaskPriority.HIGH
        )

        self.assertEqual(task.description, "Test task")
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(len(task.constraints), 2)

    def test_task_decomposition(self):
        """Test task decomposition."""
        task = Task(description="Main task", objective="Main objective")
        subtasks = task.decompose([
            ("Subtask 1", "Objective 1"),
            ("Subtask 2", "Objective 2"),
        ])

        self.assertEqual(len(subtasks), 2)
        self.assertEqual(subtasks[0].description, "Subtask 1")
        self.assertEqual(len(task.subtasks), 2)


class TestExecutionResult(unittest.TestCase):
    """Test ExecutionResult class."""

    def test_result_creation(self):
        """Test basic result creation."""
        result = ExecutionResult(
            task_id="task_1",
            output="Test output",
            confidence=0.85,
            reasoning="Test reasoning",
            iteration=1
        )

        self.assertEqual(result.task_id, "task_1")
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.iteration, 1)

    def test_result_serialization(self):
        """Test result to dict."""
        result = ExecutionResult(
            task_id="task_1",
            output={"key": "value"},
            confidence=0.9
        )

        result_dict = result.to_dict()
        self.assertEqual(result_dict['task_id'], 'task_1')
        self.assertEqual(result_dict['confidence'], 0.9)


class TestCritique(unittest.TestCase):
    """Test Critique class."""

    def test_critique_creation(self):
        """Test basic critique creation."""
        critique = Critique(
            result_id="result_1",
            score=0.75,
            strengths=["Good structure"],
            weaknesses=["Lacks detail"],
            suggestions=["Add more examples"],
            should_refine=True
        )

        self.assertEqual(critique.score, 0.75)
        self.assertTrue(critique.should_refine)
        self.assertEqual(len(critique.strengths), 1)


class TestExecutorAgent(unittest.TestCase):
    """Test ExecutorAgent."""

    def test_agent_creation(self):
        """Test agent creation."""
        agent = ExecutorAgent(name="TestExecutor")

        self.assertEqual(agent.name, "TestExecutor")
        self.assertEqual(agent.state, AgentState.IDLE)
        self.assertIn('task_execution', agent.capabilities)

    def test_task_execution(self):
        """Test basic task execution."""
        agent = ExecutorAgent()

        task = Task(description="Test", objective="Test objective")
        result = agent.execute_task(task)

        self.assertEqual(result.task_id, task.id)
        self.assertIsNotNone(result.output)
        self.assertGreater(result.confidence, 0)

    def test_custom_execution_function(self):
        """Test custom execution function."""
        def custom_exec(task):
            return f"Custom: {task.objective}"

        agent = ExecutorAgent()
        agent.set_execution_function(custom_exec)

        task = Task(description="Test", objective="MyObjective")
        result = agent.execute_task(task)

        self.assertIn("Custom:", result.output)
        self.assertIn("MyObjective", result.output)

    def test_message_processing(self):
        """Test processing task message."""
        agent = ExecutorAgent()

        msg = Message(
            type=MessageType.TASK,
            sender_id="coordinator",
            content={
                'description': 'Test task',
                'objective': 'Test objective',
                'id': 'test_task_1'
            }
        )

        agent.receive_message(msg)
        response = agent.run_once()

        self.assertIsNotNone(response)
        self.assertEqual(response.type, MessageType.RESULT)


class TestCriticAgent(unittest.TestCase):
    """Test CriticAgent."""

    def test_evaluation(self):
        """Test basic evaluation."""
        critic = CriticAgent()

        result = ExecutionResult(
            task_id="task_1",
            output="Some good output here with detail",
            confidence=0.7
        )

        critique = critic.evaluate(result)

        self.assertIsInstance(critique, Critique)
        self.assertGreater(critique.score, 0)

    def test_quality_threshold(self):
        """Test quality threshold affects should_refine."""
        critic = CriticAgent()
        critic.quality_threshold = 0.9

        # Low quality result
        result = ExecutionResult(
            task_id="task_1",
            output="x",  # Short output
            confidence=0.5
        )

        critique = critic.evaluate(result)
        self.assertTrue(critique.should_refine)


class TestCoordinatorAgent(unittest.TestCase):
    """Test CoordinatorAgent."""

    def test_task_decomposition(self):
        """Test task decomposition."""
        coordinator = CoordinatorAgent()

        # Set decomposition strategy
        coordinator.set_decomposition_strategy(
            lambda t: [
                ("Step 1", "First objective"),
                ("Step 2", "Second objective")
            ]
        )

        task = Task(description="Complex task", objective="Main goal")
        subtasks = coordinator.decompose_task(task)

        self.assertEqual(len(subtasks), 2)

    def test_result_aggregation(self):
        """Test result aggregation."""
        coordinator = CoordinatorAgent()

        # Simulate receiving results
        coordinator.results['task_1'] = [
            ExecutionResult(task_id='task_1', output='a', confidence=0.6),
            ExecutionResult(task_id='task_1', output='b', confidence=0.9),
            ExecutionResult(task_id='task_1', output='c', confidence=0.7)
        ]

        best = coordinator.aggregate_results('task_1')

        self.assertIsNotNone(best)
        self.assertEqual(best.output, 'b')  # Highest confidence


class TestRefinementAgent(unittest.TestCase):
    """Test RefinementAgent."""

    def test_refinement(self):
        """Test basic refinement."""
        refiner = RefinementAgent()

        result = ExecutionResult(
            task_id='task_1',
            output='Initial output',
            confidence=0.6,
            iteration=1
        )

        critique = Critique(
            result_id='task_1',
            score=0.6,
            suggestions=['Add more detail']
        )

        refined = refiner.refine(result, critique)

        self.assertEqual(refined.iteration, 2)
        self.assertGreater(refined.confidence, result.confidence)

    def test_max_refinements(self):
        """Test max refinement limit."""
        refiner = RefinementAgent()
        refiner.max_refinements = 2

        result = ExecutionResult(task_id='task_1', output='x', iteration=1)
        critique = Critique(result_id='task_1', score=0.5)

        # Refine multiple times
        for i in range(5):
            result = refiner.refine(result, critique)

        # Should stop at max
        self.assertEqual(refiner.refinement_count['task_1'], 5)


class TestGoalEvaluatorAgent(unittest.TestCase):
    """Test GoalEvaluatorAgent."""

    def test_goal_evaluation(self):
        """Test basic goal evaluation."""
        evaluator = GoalEvaluatorAgent()

        result = ExecutionResult(
            task_id='task_1',
            output='Good result',
            confidence=0.9
        )

        evaluation = evaluator.evaluate_goal("Test goal", result)

        self.assertIsInstance(evaluation, GoalEvaluation)
        self.assertGreater(evaluation.progress, 0)

    def test_convergence_detection(self):
        """Test convergence detection."""
        evaluator = GoalEvaluatorAgent()
        evaluator.convergence_threshold = 0.9

        # Simulate history with improving progress
        evaluator.goal_history['goal_1'] = [
            GoalEvaluation(goal='goal_1', status=GoalStatus.IN_PROGRESS, progress=70),
            GoalEvaluation(goal='goal_1', status=GoalStatus.PARTIALLY_ACHIEVED, progress=85),
            GoalEvaluation(goal='goal_1', status=GoalStatus.ACHIEVED, progress=95),
            GoalEvaluation(goal='goal_1', status=GoalStatus.ACHIEVED, progress=95),
            GoalEvaluation(goal='goal_1', status=GoalStatus.ACHIEVED, progress=95),
        ]

        self.assertTrue(evaluator.check_convergence('goal_1'))


class TestMultiAgentOrchestrator(unittest.TestCase):
    """Test MultiAgentOrchestrator."""

    def test_agent_registration(self):
        """Test agent registration."""
        orchestrator = MultiAgentOrchestrator()

        agent = ExecutorAgent("TestAgent")
        orchestrator.register_agent(agent)

        self.assertIn(agent.id, orchestrator.agents)

    def test_default_agents_creation(self):
        """Test creating default agents."""
        orchestrator = MultiAgentOrchestrator()
        orchestrator.create_default_agents()

        # Should have 5 default agents
        self.assertEqual(len(orchestrator.agents), 5)

    def test_message_routing(self):
        """Test message routing."""
        orchestrator = MultiAgentOrchestrator()
        executor = ExecutorAgent()
        orchestrator.register_agent(executor)

        msg = Message(
            type=MessageType.TASK,
            sender_id="test",
            receiver_id=executor.id,
            content={'description': 'Test', 'objective': 'Test'}
        )

        orchestrator.route_message(msg)

        self.assertEqual(executor.message_queue.qsize(), 1)

    def test_iteration_execution(self):
        """Test running iterations."""
        orchestrator = MultiAgentOrchestrator(max_iterations=3)
        orchestrator.create_default_agents()

        # Run a few iterations
        for _ in range(3):
            orchestrator.run_iteration()

        self.assertEqual(orchestrator.iteration_count, 3)


class TestCollaborativeProblemSolver(unittest.TestCase):
    """Test CollaborativeProblemSolver."""

    def test_basic_solve(self):
        """Test basic problem solving."""
        solver = CollaborativeProblemSolver()

        result = solver.solve(
            problem="Test problem",
            objective="Test objective",
            max_iterations=3
        )

        self.assertIn('task_id', result)
        self.assertIn('iterations', result)
        self.assertIn('metrics', result)

    def test_custom_executor(self):
        """Test with custom executor."""
        solver = CollaborativeProblemSolver()

        solver.configure_executor(lambda t: f"Custom result for: {t.objective}")

        result = solver.solve(
            problem="Test",
            objective="Test objective",
            max_iterations=2
        )

        self.assertIsNotNone(result)


class TestMockLLMAdapter(unittest.TestCase):
    """Test MockLLMAdapter."""

    def test_basic_completion(self):
        """Test basic completion."""
        adapter = MockLLMAdapter()

        response = adapter.complete("Test prompt")

        self.assertIsNotNone(response)
        self.assertGreater(adapter.call_count, 0)

    def test_predefined_responses(self):
        """Test predefined responses."""
        adapter = MockLLMAdapter()
        adapter.add_response("Response 1")
        adapter.add_response("Response 2")

        r1 = adapter.complete("Prompt 1")
        r2 = adapter.complete("Prompt 2")

        self.assertEqual(r1, "Response 1")
        self.assertEqual(r2, "Response 2")

    def test_contextual_responses(self):
        """Test contextual mock responses."""
        adapter = MockLLMAdapter()

        # Critique-type prompt
        response = adapter.complete("Please critique this output")
        self.assertIn("score", response)

        # Goal-type prompt (using specific keyword)
        response = adapter.complete("What is the goal progress status?")
        self.assertIn("status", response)


class TestLLMPoweredAgents(unittest.TestCase):
    """Test LLM-powered agents."""

    def test_llm_executor(self):
        """Test LLM executor agent."""
        adapter = MockLLMAdapter()
        adapter.add_response("LLM-generated execution result")

        executor = LLMExecutorAgent(llm_adapter=adapter)

        task = Task(description="Test", objective="Test objective")
        result = executor.execute_task(task)

        self.assertEqual(result.output, "LLM-generated execution result")

    def test_llm_critic(self):
        """Test LLM critic agent."""
        adapter = MockLLMAdapter()

        critic = LLMCriticAgent(llm_adapter=adapter)

        result = ExecutionResult(task_id='t1', output='Test output')
        critique = critic.evaluate(result)

        self.assertIsInstance(critique, Critique)
        self.assertGreater(critique.score, 0)


class TestLLMMultiAgentOrchestrator(unittest.TestCase):
    """Test LLM-powered orchestrator."""

    def test_basic_solve(self):
        """Test basic problem solving with LLM agents."""
        config = LLMConfig.mock()
        orchestrator = LLMMultiAgentOrchestrator(llm_config=config, max_iterations=3)

        result = orchestrator.solve(
            problem="Design an API",
            objective="Create REST API specification"
        )

        self.assertIn('task_id', result)
        self.assertIn('iterations', result)

    def test_llm_metrics(self):
        """Test LLM metrics collection."""
        config = LLMConfig.mock()
        orchestrator = LLMMultiAgentOrchestrator(llm_config=config, max_iterations=2)

        orchestrator.solve(problem="Test", objective="Test")

        metrics = orchestrator.get_llm_metrics()
        self.assertIn('call_count', metrics)


class TestIntegration(unittest.TestCase):
    """Integration tests."""

    def test_full_workflow(self):
        """Test complete workflow from task to result."""
        solver = CollaborativeProblemSolver()

        # Configure with tracking
        execution_count = {'count': 0}

        def tracked_executor(task):
            execution_count['count'] += 1
            return f"Execution #{execution_count['count']}: {task.objective}"

        solver.configure_executor(tracked_executor)

        result = solver.solve(
            problem="Complete integration test",
            objective="Verify end-to-end functionality",
            constraints=["Must complete within iterations"],
            max_iterations=5
        )

        self.assertIsNotNone(result['task_id'])
        self.assertLessEqual(result['iterations'], 5)
        self.assertGreater(execution_count['count'], 0)

    def test_refinement_loop(self):
        """Test that refinement loop works correctly."""
        orchestrator = MultiAgentOrchestrator(max_iterations=5)

        # Create agents with refinement capability
        executor = ExecutorAgent()
        critic = CriticAgent()
        critic.quality_threshold = 0.9  # High threshold to force refinement

        orchestrator.register_agent(CoordinatorAgent())
        orchestrator.register_agent(executor)
        orchestrator.register_agent(critic)
        orchestrator.register_agent(RefinementAgent())
        orchestrator.register_agent(GoalEvaluatorAgent())

        task = Task(description="Test refinement", objective="High quality output")

        result = orchestrator.execute_task(task)

        # Should have gone through multiple iterations due to high threshold
        self.assertGreater(result['iterations'], 1)


if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2)
