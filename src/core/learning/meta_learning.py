#!/usr/bin/env python3
"""
M-MDP Meta-Learning Module - Phase 3 Day 15-17 Implementation
MAML (Model-Agnostic Meta-Learning) for rapid agent adaptation
"""

from __future__ import annotations

import copy
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import torch
    import torch.nn as nn
    import torch.optim as optim

# Optional ML dependencies - only import if available
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from src.core.memory.memory_manager import MemoryManager
from .memory_guided_learning import MemoryGuidedLearningManager

# ASCII-only logging compliance
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class MetaTask:
    """Meta-learning task definition for agent adaptation"""

    task_id: str
    task_type: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    support_data: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    query_data: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    agent_type: str
    performance_target: float = 0.8

    def __post_init__(self) -> None:
        """Validate meta-task configuration"""
        if not self.task_id:
            raise ValueError("Meta-task requires valid task_id")
        if not self.support_data:
            raise ValueError("Meta-task requires support data for adaptation")


@dataclass
class MAMLConfig:
    """MAML algorithm configuration parameters"""

    inner_lr: float = 0.01  # Inner loop learning rate
    outer_lr: float = 0.001  # Outer loop learning rate
    inner_steps: int = 5  # Number of inner loop gradient steps
    outer_steps: int = 100  # Number of outer loop iterations
    batch_size: int = 16  # Number of tasks per meta-batch
    support_size: int = 5  # Number of support examples per task
    query_size: int = 10  # Number of query examples per task
    adaptation_layers: list[str] | None = None  # Layers to adapt (None = all)

    def __post_init__(self) -> None:
        """Set default adaptation layers if not specified"""
        if self.adaptation_layers is None:
            self.adaptation_layers = ["all"]


class MAMLOptimizer:
    """Model-Agnostic Meta-Learning optimizer for rapid agent adaptation"""

    def __init__(self, base_model: nn.Module, config: MAMLConfig) -> None:
        """
        Initialize MAML optimizer with base model and configuration

        Args:
            base_model: Neural network model to meta-learn
            config: MAML configuration parameters
        """
        self.base_model = base_model
        self.config = config
        self.meta_optimizer = optim.Adam(base_model.parameters(), lr=config.outer_lr)
        self.adaptation_history: list[Any] = []  # TODO(TYPE): replace Any with concrete type

        logger.info(
            f"MAML Optimizer initialized with inner_lr={config.inner_lr}, outer_lr={config.outer_lr}"
        )

    def inner_loop(self, task: MetaTask, model: nn.Module) -> tuple[nn.Module, dict[str, float]]:
        """
        Perform inner loop adaptation for a specific task

        Args:
            task: Meta-task to adapt to
            model: Model to adapt

        Returns:
            Adapted model and adaptation metrics
        """
        # Clone model for task-specific adaptation
        adapted_model = copy.deepcopy(model)
        inner_optimizer = optim.SGD(adapted_model.parameters(), lr=self.config.inner_lr)

        adaptation_losses: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Perform inner loop gradient steps
        for step in range(self.config.inner_steps):
            inner_optimizer.zero_grad()

            # Compute loss on support data
            support_loss = self._compute_task_loss(task.support_data, adapted_model, task.task_type)
            support_loss.backward()
            inner_optimizer.step()

            adaptation_losses.append(support_loss.item())

        # Compute adaptation metrics
        metrics = {
            "adaptation_loss": np.mean(adaptation_losses),
            "adaptation_steps": self.config.inner_steps,
            "final_support_loss": adaptation_losses[-1] if adaptation_losses else 0.0,
        }

        return adapted_model, metrics

    def outer_loop(
        self, meta_batch: list[MetaTask]
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform outer loop meta-update across batch of tasks

        Args:
            meta_batch: Batch of meta-tasks for meta-learning

        Returns:
            Meta-learning metrics
        """
        self.meta_optimizer.zero_grad()

        total_meta_loss: torch.Tensor = torch.tensor(0.0)
        batch_metrics: defaultdict[str, list[float]] = defaultdict(list)

        for task in meta_batch:
            # Inner loop adaptation
            adapted_model, adaptation_metrics = self.inner_loop(task, self.base_model)

            # Compute meta-loss on query data
            query_loss = self._compute_task_loss(task.query_data, adapted_model, task.task_type)
            total_meta_loss = total_meta_loss + query_loss

            # Collect metrics
            batch_metrics["adaptation_loss"].append(adaptation_metrics["adaptation_loss"])
            batch_metrics["query_loss"].append(query_loss.item())

        # Meta-gradient update
        meta_loss = total_meta_loss / len(meta_batch)
        meta_loss.backward()  # type: ignore[no-untyped-call]  # torch.Tensor.backward is niet geannoteerd
        self.meta_optimizer.step()

        # Compile batch metrics
        metrics = {
            "meta_loss": meta_loss.item(),
            "avg_adaptation_loss": np.mean(batch_metrics["adaptation_loss"]),
            "avg_query_loss": np.mean(batch_metrics["query_loss"]),
            "batch_size": len(meta_batch),
        }

        return metrics

    def _compute_task_loss(
        self,
        data: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        model: nn.Module,
        task_type: str,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Compute loss for specific task type and data

        Args:
            data: Task-specific training data
            model: Model to evaluate
            task_type: Type of task (classification, regression, etc.)

        Returns:
            Computed loss tensor
        """
        if not data:
            return torch.tensor(0.0, requires_grad=True)

        # Convert data to tensors
        inputs = torch.stack([torch.tensor(item["input"], dtype=torch.float32) for item in data])
        targets = torch.stack([torch.tensor(item["target"], dtype=torch.float32) for item in data])

        # Forward pass
        outputs = model(inputs)

        # Compute task-specific loss
        loss_fn: "nn.Module"
        if task_type == "classification":
            loss_fn = nn.CrossEntropyLoss()
        elif task_type == "regression":
            loss_fn = nn.MSELoss()
        else:
            # Default to MSE for unknown task types
            loss_fn = nn.MSELoss()

        loss = loss_fn(outputs, targets)
        return loss

    def fast_adapt(
        self, task: MetaTask, num_steps: int | None = None
    ) -> tuple[nn.Module, dict[str, float]]:
        """
        Quickly adapt base model to new task

        Args:
            task: New task to adapt to
            num_steps: Number of adaptation steps (uses config default if None)

        Returns:
            Adapted model and performance metrics
        """
        steps = num_steps or self.config.inner_steps
        original_steps = self.config.inner_steps
        self.config.inner_steps = steps

        try:
            adapted_model, metrics = self.inner_loop(task, self.base_model)

            # Evaluate on query data
            query_loss = self._compute_task_loss(task.query_data, adapted_model, task.task_type)
            metrics["query_performance"] = query_loss.item()
            metrics["adaptation_success"] = query_loss.item() < task.performance_target

            return adapted_model, metrics

        finally:
            # Restore original configuration
            self.config.inner_steps = original_steps


class StrategyTransferLearning:
    """Strategy transfer learning for cross-agent knowledge sharing"""

    def __init__(
        self,
        memory_manager: MemoryGuidedLearningManager | MemoryManager | None = None,
    ) -> None:
        """
        Initialize strategy transfer learning system

        Args:
            memory_manager: Memory system for strategy storage and retrieval
        """
        self.memory_manager = memory_manager
        self.strategy_embeddings: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.transfer_history: list[Any] = []  # TODO(TYPE): replace Any with concrete type

        logger.info("Strategy Transfer Learning system initialized")

    def extract_strategy(
        self,
        agent_type: str,
        model: nn.Module,
        context: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Extract learned strategy from agent model

        Args:
            agent_type: Type of agent (CVA, orchestrator, specialist)
            model: Trained agent model
            context: Learning context (any type with required attributes)

        Returns:
            Extracted strategy representation
        """
        # Extract model parameters relevant to strategy
        strategy_params: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for name, param in model.named_parameters():
            if "policy" in name or "value" in name:
                strategy_params[name] = param.detach().clone()

        # Safely extract context attributes with defaults
        task_id = getattr(context, "task_id", "unknown_task")
        task_type = getattr(context, "task_type", "unknown")
        performance_metrics = getattr(context, "performance_metrics", {})
        timestamp = getattr(context, "timestamp", None)

        # Create strategy representation
        strategy = {
            "agent_type": agent_type,
            "strategy_id": f"strategy_{agent_type}_{task_id}",
            "parameters": strategy_params,
            "context": {
                "task_type": task_type,
                "performance_score": (
                    performance_metrics.get("reward", 0.0)
                    if isinstance(performance_metrics, dict)
                    else 0.0
                ),
                "episodes": (
                    performance_metrics.get("episodes", 0)
                    if isinstance(performance_metrics, dict)
                    else 0
                ),
                "success_rate": (
                    performance_metrics.get("success_rate", 0.0)
                    if isinstance(performance_metrics, dict)
                    else 0.0
                ),
            },
            "timestamp": timestamp,
        }

        # Store strategy in memory if method exists
        if self.memory_manager is not None:
            store_method = getattr(self.memory_manager, "store_learning_context", None)
            if store_method is not None and callable(store_method):
                store_method(context)

        logger.info(f"Strategy extracted from {agent_type} agent: {strategy['strategy_id']}")
        return strategy

    def transfer_strategy(
        self,
        source_strategy: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        target_model: nn.Module,
        target_agent_type: str,
    ) -> tuple[nn.Module, dict[str, float]]:
        """
        Transfer strategy from source to target agent

        Args:
            source_strategy: Strategy to transfer
            target_model: Target agent model
            target_agent_type: Type of target agent

        Returns:
            Modified target model and transfer metrics
        """
        transfer_metrics = {
            "source_agent": source_strategy["agent_type"],
            "target_agent": target_agent_type,
            "strategy_performance": source_strategy["context"]["performance_score"],
        }

        # Calculate compatibility between source and target
        compatibility_score = self._calculate_compatibility(
            source_strategy["agent_type"], target_agent_type
        )

        if compatibility_score < 0.5:
            logger.warning(
                f"Low compatibility ({compatibility_score:.2f}) between "
                f"{source_strategy['agent_type']} and {target_agent_type}"
            )

        # Transfer compatible parameters
        transferred_params = 0
        total_params = 0

        with torch.no_grad():
            for name, source_param in source_strategy["parameters"].items():
                if name in dict(target_model.named_parameters()):
                    target_param = dict(target_model.named_parameters())[name]

                    # Apply transfer with compatibility weighting
                    if target_param.shape == source_param.shape:
                        # Direct parameter transfer weighted by compatibility
                        target_param.copy_(
                            compatibility_score * source_param
                            + (1 - compatibility_score) * target_param
                        )
                        transferred_params += 1

                    total_params += 1

        transfer_metrics.update(
            {
                "compatibility_score": compatibility_score,
                "parameters_transferred": transferred_params,
                "total_parameters": total_params,
                "transfer_success_rate": transferred_params / max(total_params, 1),
            }
        )

        # Record transfer history
        self.transfer_history.append(
            {
                "timestamp": source_strategy.get("timestamp", None),
                "source": source_strategy["agent_type"],
                "target": target_agent_type,
                "metrics": transfer_metrics,
            }
        )

        logger.info(f"Strategy transfer completed: {transferred_params}/{total_params} parameters")
        return target_model, transfer_metrics

    def _calculate_compatibility(self, source_type: str, target_type: str) -> float:
        """
        Calculate compatibility score between agent types

        Args:
            source_type: Source agent type
            target_type: Target agent type

        Returns:
            Compatibility score (0.0 to 1.0)
        """
        # Define agent type similarities
        compatibility_matrix = {
            ("cva", "cva"): 1.0,
            ("cva", "orchestrator"): 0.7,
            ("cva", "specialist"): 0.5,
            ("orchestrator", "orchestrator"): 1.0,
            ("orchestrator", "cva"): 0.7,
            ("orchestrator", "specialist"): 0.6,
            ("specialist", "specialist"): 1.0,
            ("specialist", "orchestrator"): 0.6,
            ("specialist", "cva"): 0.5,
        }

        return compatibility_matrix.get((source_type.lower(), target_type.lower()), 0.3)


class FewShotLearningManager:
    """Few-shot learning capabilities for rapid agent adaptation"""

    def __init__(self, meta_optimizer: MAMLOptimizer) -> None:
        """
        Initialize few-shot learning manager

        Args:
            meta_optimizer: MAML optimizer for meta-learning
        """
        self.meta_optimizer = meta_optimizer
        self.few_shot_history: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self.prototype_networks: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info("Few-Shot Learning Manager initialized")

    def few_shot_adaptation(
        self,
        support_examples: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        query_examples: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        task_type: str,
        num_shots: int = 5,
    ) -> dict[str, float]:
        """
        Perform few-shot learning adaptation

        Args:
            support_examples: Few labeled examples for adaptation
            query_examples: Examples to evaluate adaptation
            task_type: Type of task for adaptation
            num_shots: Number of examples per class/category

        Returns:
            Few-shot learning performance metrics
        """
        # Create meta-task from few-shot data
        meta_task = MetaTask(
            task_id=f"few_shot_{task_type}_{len(support_examples)}",
            task_type=task_type,
            context={"few_shot": True, "num_shots": num_shots},
            support_data=support_examples,
            query_data=query_examples,
            agent_type="adaptive",
        )

        # Perform rapid adaptation
        adapted_model, metrics = self.meta_optimizer.fast_adapt(meta_task, num_steps=3)

        # Evaluate few-shot performance
        few_shot_metrics = {
            "num_shots": num_shots,
            "support_size": len(support_examples),
            "query_size": len(query_examples),
            "adaptation_loss": metrics["adaptation_loss"],
            "query_performance": metrics["query_performance"],
            "adaptation_success": metrics["adaptation_success"],
        }

        # Record few-shot learning attempt
        self.few_shot_history.append(
            {
                "task_type": task_type,
                "num_shots": num_shots,
                "metrics": few_shot_metrics,
                "timestamp": torch.tensor(0.0),  # Placeholder timestamp
            }
        )

        logger.info(
            f"Few-shot learning completed: {num_shots} shots, "
            f"performance: {few_shot_metrics['query_performance']:.3f}"
        )

        return few_shot_metrics

    def prototype_learning(
        self,
        examples: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        class_labels: list[str],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, torch.Tensor]:
        """
        Learn prototypes for few-shot classification

        Args:
            examples: Training examples
            class_labels: Class labels for examples

        Returns:
            Learned class prototypes
        """
        prototypes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Group examples by class
        class_examples = defaultdict(list)
        for example, label in zip(examples, class_labels):
            class_examples[label].append(example)

        # Compute prototype for each class
        for class_label, class_data in class_examples.items():
            # Convert to tensors and compute mean
            embeddings = [torch.tensor(item["input"], dtype=torch.float32) for item in class_data]
            if embeddings:
                prototype = torch.stack(embeddings).mean(dim=0)
                prototypes[class_label] = prototype

        # Store prototypes for reuse
        self.prototype_networks.update(prototypes)

        logger.info(f"Learned {len(prototypes)} class prototypes")
        return prototypes


class AdvancedOptimizationManager:
    """Advanced optimization algorithms for meta-learning enhancement"""

    def __init__(self) -> None:
        """Initialize advanced optimization manager"""
        self.optimization_history: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        self.adaptive_schedules: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info("Advanced Optimization Manager initialized")

    def adaptive_learning_rate(self, loss_history: list[float], current_lr: float) -> float:
        """
        Compute adaptive learning rate based on loss history

        Args:
            loss_history: Recent loss values
            current_lr: Current learning rate

        Returns:
            Adjusted learning rate
        """
        if len(loss_history) < 3:
            return current_lr

        # Analyze loss trend
        recent_losses = loss_history[-3:]
        loss_trend = np.polyfit(range(len(recent_losses)), recent_losses, 1)[0]

        # Adjust learning rate based on trend
        if loss_trend < -0.01:  # Decreasing loss
            new_lr = min(current_lr * 1.05, 0.01)  # Slight increase
        elif loss_trend > 0.01:  # Increasing loss
            new_lr = max(current_lr * 0.95, 0.0001)  # Decrease
        else:
            new_lr = current_lr  # Stable

        return new_lr

    def gradient_clipping(self, model: nn.Module, max_norm: float = 1.0) -> float:
        """
        Apply gradient clipping to prevent exploding gradients

        Args:
            model: Model to clip gradients
            max_norm: Maximum gradient norm

        Returns:
            Gradient norm before clipping
        """
        total_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
        return float(total_norm.item())

    def cosine_annealing_schedule(
        self,
        current_step: int,
        total_steps: int,
        initial_lr: float,
        min_lr: float = 0.0001,
    ) -> float:
        """
        Compute cosine annealing learning rate schedule

        Args:
            current_step: Current training step
            total_steps: Total training steps
            initial_lr: Initial learning rate
            min_lr: Minimum learning rate

        Returns:
            Scheduled learning rate
        """
        cosine_factor = 0.5 * (1 + np.cos(np.pi * current_step / total_steps))
        lr = min_lr + (initial_lr - min_lr) * cosine_factor
        return float(lr)


class MetaLearningManager:
    """Main manager for meta-learning capabilities integration"""

    def __init__(
        self,
        base_models: dict[str, nn.Module],
        memory_manager: MemoryManager,
        config: MAMLConfig | None = None,
    ) -> None:
        """
        Initialize meta-learning management system

        Args:
            base_models: Base models for different agent types
            memory_manager: Memory management system
            config: MAML configuration (uses default if None)
        """
        self.base_models = base_models
        self.memory_manager = memory_manager
        self.config = config or MAMLConfig()

        # Initialize components
        self.maml_optimizers = {}
        for agent_type, model in base_models.items():
            self.maml_optimizers[agent_type] = MAMLOptimizer(model, self.config)

        self.strategy_transfer = StrategyTransferLearning(memory_manager)

        # Get first optimizer for few-shot manager, with fallback
        first_optimizer: MAMLOptimizer | None = None
        if self.maml_optimizers:
            first_optimizer = next(iter(self.maml_optimizers.values()))

        if first_optimizer is None:
            raise ValueError("At least one base model is required for meta-learning")

        self.few_shot_manager = FewShotLearningManager(first_optimizer)
        self.optimization_manager = AdvancedOptimizationManager()

        self.meta_learning_stats = {
            "total_adaptations": 0,
            "successful_transfers": 0,
            "few_shot_attempts": 0,
            "average_adaptation_time": 0.0,
        }

        logger.info(f"Meta-Learning Manager initialized with {len(base_models)} agent types")

    def meta_train_step(self, meta_batch: list[MetaTask]) -> dict[str, float]:
        """
        Perform single meta-training step across all agent types

        Args:
            meta_batch: Batch of meta-tasks for training

        Returns:
            Comprehensive meta-learning metrics
        """
        all_metrics: dict[str, float] = {}
        # Group tasks by agent type
        agent_tasks = defaultdict(list)
        for task in meta_batch:
            agent_tasks[task.agent_type].append(task)

        # Meta-train each agent type
        for agent_type, tasks in agent_tasks.items():
            if agent_type in self.maml_optimizers:
                metrics = self.maml_optimizers[agent_type].outer_loop(tasks)
                all_metrics[f"{agent_type}_meta_loss"] = metrics["meta_loss"]
                all_metrics[f"{agent_type}_adaptation_loss"] = metrics["avg_adaptation_loss"]

        # Update statistics
        self.meta_learning_stats["total_adaptations"] += len(meta_batch)

        return all_metrics

    def rapid_agent_adaptation(
        self, agent_type: str, task: MetaTask
    ) -> tuple[nn.Module, dict[str, float]]:
        """
        Rapidly adapt specific agent to new task

        Args:
            agent_type: Type of agent to adapt
            task: Task to adapt to

        Returns:
            Adapted agent model and performance metrics
        """
        if agent_type not in self.maml_optimizers:
            raise ValueError(f"Unknown agent type: {agent_type}")

        adapted_model, metrics = self.maml_optimizers[agent_type].fast_adapt(task)

        # Update statistics
        if metrics.get("adaptation_success", False):
            self.meta_learning_stats["successful_transfers"] += 1

        return adapted_model, metrics

    def cross_agent_transfer(
        self,
        source_agent: str,
        target_agent: str,
        context: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """
        Transfer strategy from source to target agent

        Args:
            source_agent: Source agent type
            target_agent: Target agent type
            context: Learning context

        Returns:
            Transfer performance metrics
        """
        if source_agent not in self.base_models or target_agent not in self.base_models:
            raise ValueError("Invalid agent types for transfer")

        # Extract strategy from source
        source_model = self.base_models[source_agent]
        strategy = self.strategy_transfer.extract_strategy(source_agent, source_model, context)

        # Transfer to target
        target_model = self.base_models[target_agent]
        _, transfer_metrics = self.strategy_transfer.transfer_strategy(
            strategy, target_model, target_agent
        )

        return transfer_metrics

    def get_meta_learning_status(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get comprehensive meta-learning system status

        Returns:
            Meta-learning system status and statistics
        """
        return {
            "agent_types": list(self.base_models.keys()),
            "maml_config": {
                "inner_lr": self.config.inner_lr,
                "outer_lr": self.config.outer_lr,
                "inner_steps": self.config.inner_steps,
                "batch_size": self.config.batch_size,
            },
            "statistics": self.meta_learning_stats,
            "components": {
                "maml_optimizers": len(self.maml_optimizers),
                "strategy_transfer": "operational",
                "few_shot_learning": "operational",
                "advanced_optimization": "operational",
            },
        }


# Export main classes for integration
__all__ = [
    "MetaTask",
    "MAMLConfig",
    "MAMLOptimizer",
    "StrategyTransferLearning",
    "FewShotLearningManager",
    "AdvancedOptimizationManager",
    "MetaLearningManager",
]

# ASCII-only compliance check
logger.info("M-MDP Meta-Learning Module initialized successfully - Phase 3 Day 15-17")
