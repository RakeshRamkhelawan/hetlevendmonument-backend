"""
Ultimate Learning Loop - SanskritiSetu.

Keep package exports lazy so importing a specific learning submodule does not
eagerly import every optional component in the learning stack.
"""

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "ExperienceReplay": (
        "src.core.learning.experience_replay",
        "PrioritizedExperienceReplay",
    ),
    "ReplayBuffer": ("src.core.learning.experience_replay", "ExperienceBuffer"),
    "ExperimentTracker": (
        "src.core.learning.experiment_tracker",
        "ExperimentTracker",
    ),
    "FeedbackService": ("src.core.learning.feedback_service", "FeedbackService"),
    "LearningEngine": ("src.core.learning.learning_engine", "LearningEngine"),
    "LearningRepository": (
        "src.core.learning.learning_repository",
        "LearningRepository",
    ),
    "MemoryGuidedLearning": (
        "src.core.learning.memory_guided_learning",
        "MemoryGuidedLearning",
    ),
    "MetaLearning": ("src.core.learning.meta_learning", "MetaLearning"),
    "MLflowIntegration": (
        "src.core.learning.mlflow_integration",
        "MLflowIntegration",
    ),
    "ModelRegistry": ("src.core.learning.model_registry", "ModelRegistry"),
    "LearningModel": ("src.core.learning.models", "LearningModel"),
    "PersistenceModels": (
        "src.core.learning.persistence_models",
        "PersistenceModels",
    ),
    "PPOTrainer": ("src.core.learning.ppo_trainer", "PPOTrainer"),
    "PredictiveAnalyticsEngine": (
        "src.core.learning.predictive_analytics_engine",
        "PredictiveAnalyticsEngine",
    ),
    "PredictiveEvolution": (
        "src.core.learning.predictive_evolution",
        "PredictiveEvolution",
    ),
    "ProductionIntegration": (
        "src.core.learning.production_integration",
        "ProductionIntegration",
    ),
    "RewardCalculator": (
        "src.core.learning.reward_calculator",
        "RewardCalculator",
    ),
    "RewardSystems": ("src.core.learning.reward_systems", "RewardSystems"),
    "SafetyValidation": (
        "src.core.learning.safety_validation",
        "SafetyValidation",
    ),
    "StateBuilder": ("src.core.learning.state_builder", "StateBuilder"),
    "TrainingPipeline": (
        "src.core.learning.training_pipeline",
        "TrainingPipeline",
    ),
}

__all__ = list(_EXPORTS.keys())  # pyright: ignore[reportUnsupportedDunderAll]
__version__ = "4.0.0"


def __getattr__(name: str) -> Any:
    """Resolve learning exports lazily to avoid import-time cascade failures."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
