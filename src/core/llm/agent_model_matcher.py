#!/usr/bin/env python3
"""
Agent-Model Matcher - Intelligent LLM Model Selection System
Determines optimal Google Gemini model based on agent type and task characteristics
M-MDP Compliant Implementation
"""

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels"""

    SIMPLE = "simple"  # Basic calculations, simple responses
    MODERATE = "moderate"  # Standard analysis, content generation
    COMPLEX = "complex"  # Deep analysis, complex reasoning
    EXPERT = "expert"  # Multi-step reasoning, strategic planning


class AgentCategory(Enum):
    """Agent category classifications"""

    ANALYTICAL = "analytical"  # Financial, Business, Data agents
    CREATIVE = "creative"  # Content, Marketing, Design agents
    TECHNICAL = "technical"  # Code, Security, Infrastructure agents
    STRATEGIC = "strategic"  # CVA, Risk, Planning agents
    SPECIALIZED = "specialized"  # Legal, HR, Domain-specific agents
    SUPPORT = "support"  # Customer support, help desk agents


@dataclass
class ModelCapabilities:
    """Model capability profile"""

    reasoning_strength: float  # 0.0-1.0 - logical reasoning ability
    speed_score: float  # 0.0-1.0 - response speed
    cost_efficiency: float  # 0.0-1.0 - cost per token efficiency
    context_window: int  # Maximum tokens in context
    multimodal: bool  # Supports images/audio
    specialized_features: list[str]  # ['tts', 'image_gen', 'code', etc.]


@dataclass
class AgentProfile:
    """Agent capability and requirement profile"""

    agent_type: str
    category: AgentCategory
    typical_complexity: TaskComplexity
    reasoning_required: float  # 0.0-1.0
    speed_priority: float  # 0.0-1.0
    cost_sensitivity: float  # 0.0-1.0
    context_needs: int  # Typical context window requirement
    special_requirements: list[str]  # Special features needed


@dataclass
class TaskCharacteristics:
    """Individual task characteristics"""

    complexity: TaskComplexity
    estimated_tokens: int
    requires_reasoning: bool
    speed_critical: bool
    cost_sensitive: bool
    special_features: list[str] | None = None


class AgentModelMatcher:
    """
    Intelligent matching system between agents and optimal Google Gemini models
    M-MDP Compliant: Sync matching logic, async model discovery
    """

    def __init__(self) -> None:
        # Model capability database (populated from Google AI API discovery)
        self.model_capabilities: dict[str, ModelCapabilities] = {}

        # Agent profile database
        self.agent_profiles: dict[str, AgentProfile] = {}

        # Performance history for learning
        self.performance_history: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type

        # Caching for frequently requested combinations
        self.match_cache: dict[str, str] = {}
        self.cache_ttl = 3600  # 1 hour
        self.cache_timestamps: dict[str, float] = {}

        # Defer expensive initialization in test mode; real use triggers _ensure_initialized()
        if not (os.environ.get("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ):
            self._initialize_default_profiles()
            self._initialize_model_capabilities()

    def _ensure_initialized(self) -> None:
        """Deferred init: no-op after first call; called by all public read methods."""
        if not self.agent_profiles:
            self._initialize_default_profiles()
        if not self.model_capabilities:
            self._initialize_model_capabilities()

    def _initialize_default_profiles(self) -> None:
        """Initialize default agent profiles - SYNC M-MDP"""

        # Financial Agent Profile
        self.agent_profiles["financial_agent"] = AgentProfile(
            agent_type="financial_agent",
            category=AgentCategory.ANALYTICAL,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.9,  # High reasoning for calculations
            speed_priority=0.6,  # Moderate speed needs
            cost_sensitivity=0.7,  # Cost conscious
            context_needs=2000,  # Moderate context
            special_requirements=["mathematical_reasoning", "data_analysis"],
        )

        # Business Analyst Agent Profile
        self.agent_profiles["business_analyst"] = AgentProfile(
            agent_type="business_analyst",
            category=AgentCategory.ANALYTICAL,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.8,  # High reasoning for insights
            speed_priority=0.5,  # Quality over speed
            cost_sensitivity=0.6,  # Balanced cost consideration
            context_needs=4000,  # Large context for data analysis
            special_requirements=["data_visualization", "strategic_thinking"],
        )

        # Content Marketer Profile
        self.agent_profiles["content_marketer"] = AgentProfile(
            agent_type="content_marketer",
            category=AgentCategory.CREATIVE,
            typical_complexity=TaskComplexity.MODERATE,
            reasoning_required=0.6,  # Creative + some strategy
            speed_priority=0.8,  # Fast content generation
            cost_sensitivity=0.9,  # Very cost sensitive (high volume)
            context_needs=1500,  # Moderate context
            special_requirements=["creative_writing", "marketing_knowledge"],
        )

        # CVA Agent Profile (Strategic)
        self.agent_profiles["cva_agent"] = AgentProfile(
            agent_type="cva_agent",
            category=AgentCategory.STRATEGIC,
            typical_complexity=TaskComplexity.EXPERT,
            reasoning_required=1.0,  # Maximum reasoning for strategy
            speed_priority=0.4,  # Quality over speed
            cost_sensitivity=0.3,  # Cost less important for strategy
            context_needs=8000,  # Large context for complex decisions
            special_requirements=["strategic_planning", "multi_agent_coordination"],
        )

        # Technical/Code Agent Profile
        self.agent_profiles["code_agent"] = AgentProfile(
            agent_type="code_agent",
            category=AgentCategory.TECHNICAL,
            typical_complexity=TaskComplexity.COMPLEX,
            reasoning_required=0.8,  # Logic and debugging
            speed_priority=0.7,  # Developer productivity
            cost_sensitivity=0.8,  # Cost conscious
            context_needs=6000,  # Large codebase context
            special_requirements=["code_generation", "debugging", "architecture"],
        )

        logger.info(f"Initialized {len(self.agent_profiles)} default agent profiles")

    def _initialize_model_capabilities(self) -> None:
        """Initialize Google Gemini model capabilities - SYNC M-MDP"""

        # Gemini 2.5 Pro - Top tier reasoning
        self.model_capabilities["gemini-2.5-pro"] = ModelCapabilities(
            reasoning_strength=1.0,
            speed_score=0.6,
            cost_efficiency=0.3,
            context_window=1000000,
            multimodal=True,
            specialized_features=["advanced_reasoning", "thinking_mode", "multimodal"],
        )

        # Gemini 2.5 Flash - Balanced performance
        self.model_capabilities["gemini-2.5-flash"] = ModelCapabilities(
            reasoning_strength=0.8,
            speed_score=0.9,
            cost_efficiency=0.8,
            context_window=1000000,
            multimodal=True,
            specialized_features=["balanced_performance", "multimodal"],
        )

        # Gemini 2.5 Flash Lite - High speed, cost efficient
        self.model_capabilities["gemini-2.5-flash-lite"] = ModelCapabilities(
            reasoning_strength=0.6,
            speed_score=1.0,
            cost_efficiency=1.0,
            context_window=1000000,
            multimodal=False,
            specialized_features=["high_throughput", "cost_optimized"],
        )

        # Gemini 2.0 Flash - Latest multimodal
        self.model_capabilities["gemini-2.0-flash"] = ModelCapabilities(
            reasoning_strength=0.7,
            speed_score=0.8,
            cost_efficiency=0.7,
            context_window=1000000,
            multimodal=True,
            specialized_features=["latest_features", "native_tool_use", "multimodal"],
        )

        # Gemini TTS models
        self.model_capabilities["gemini-2.5-flash-preview-tts"] = ModelCapabilities(
            reasoning_strength=0.5,
            speed_score=0.7,
            cost_efficiency=0.6,
            context_window=100000,
            multimodal=True,
            specialized_features=["text_to_speech", "audio_generation"],
        )

        logger.info(f"Initialized {len(self.model_capabilities)} model capability profiles")

    def select_optimal_model(
        self,
        agent_type: str,
        task_characteristics: TaskCharacteristics | None = None,
    ) -> str:
        """
        Select optimal model for agent and task - SYNC M-MDP
        Returns model name string
        """
        self._ensure_initialized()
        # Check cache first
        cache_key = self._generate_cache_key(agent_type, task_characteristics)
        cached_model = self._get_cached_match(cache_key)
        if cached_model:
            logger.debug(f"Cache hit for {agent_type}: {cached_model}")
            return cached_model

        # Get agent profile
        agent_profile = self.agent_profiles.get(agent_type)
        if not agent_profile:
            logger.warning(f"Unknown agent type {agent_type}, using default profile")
            agent_profile = self._create_default_profile(agent_type)

        # Calculate match scores for each available model
        model_scores: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for model_name, capabilities in self.model_capabilities.items():
            score = self._calculate_match_score(agent_profile, capabilities, task_characteristics)
            model_scores[model_name] = score

        # Select best match
        if not model_scores:
            best_model = "gemini-2.5-flash"  # Safe fallback
            logger.warning(f"No models available, using fallback: {best_model}")
        else:
            best_model = max(model_scores.items(), key=lambda x: x[1])[0]
            logger.info(
                f"Selected {best_model} for {agent_type} (score: {model_scores[best_model]:.3f})"
            )

        # Cache result
        self._cache_match(cache_key, best_model)

        return best_model

    def _calculate_match_score(
        self,
        agent_profile: AgentProfile,
        model_capabilities: ModelCapabilities,
        task_chars: TaskCharacteristics | None = None,
    ) -> float:
        """
        Calculate compatibility score between agent and model - SYNC M-MDP
        Returns score 0.0-1.0
        """
        score = 0.0
        weights = {
            "reasoning": 0.3,
            "speed": 0.2,
            "cost": 0.25,
            "context": 0.15,
            "special": 0.1,
        }

        # Reasoning match
        reasoning_match = (
            min(
                model_capabilities.reasoning_strength / max(agent_profile.reasoning_required, 0.1),
                2.0,
            )
            / 2.0
        )
        score += weights["reasoning"] * reasoning_match

        # Speed match
        if agent_profile.speed_priority > 0.7:
            # High speed priority - prefer fast models
            speed_match = model_capabilities.speed_score
        else:
            # Speed less important - don't penalize slower models much
            speed_match = min(model_capabilities.speed_score * 1.5, 1.0)
        score += weights["speed"] * speed_match

        # Cost efficiency match
        cost_match = model_capabilities.cost_efficiency * agent_profile.cost_sensitivity
        score += weights["cost"] * cost_match

        # Context window adequacy
        if model_capabilities.context_window >= agent_profile.context_needs:
            context_match = 1.0
        else:
            context_match = model_capabilities.context_window / agent_profile.context_needs
        score += weights["context"] * context_match

        # Special requirements match
        special_match = self._calculate_special_requirements_match(
            agent_profile.special_requirements, model_capabilities.specialized_features
        )
        score += weights["special"] * special_match

        # Task-specific adjustments
        if task_chars:
            score = self._apply_task_adjustments(score, task_chars, model_capabilities)

        return min(score, 1.0)  # Cap at 1.0

    def _calculate_special_requirements_match(
        self, agent_requirements: list[str], model_features: list[str]
    ) -> float:
        """Calculate special requirements match score"""
        if not agent_requirements:
            return 1.0

        matches: float = 0.0
        for requirement in agent_requirements:
            # Check for direct matches or semantic matches
            if requirement in model_features:
                matches += 1
            elif self._is_semantic_match(requirement, model_features):
                matches += 0.5

        return matches / len(agent_requirements)

    def _is_semantic_match(self, requirement: str, features: list[str]) -> bool:
        """Check for semantic matches between requirements and features"""
        semantic_mappings = {
            "mathematical_reasoning": ["advanced_reasoning", "thinking_mode"],
            "data_analysis": ["advanced_reasoning", "balanced_performance"],
            "creative_writing": ["balanced_performance", "latest_features"],
            "strategic_planning": ["advanced_reasoning", "thinking_mode"],
            "code_generation": ["advanced_reasoning", "native_tool_use"],
            "audio_generation": ["text_to_speech", "multimodal"],
        }

        mapped_features = semantic_mappings.get(requirement, [])
        return any(feature in features for feature in mapped_features)

    def _apply_task_adjustments(
        self,
        base_score: float,
        task_chars: TaskCharacteristics,
        model_caps: ModelCapabilities,
    ) -> float:
        """Apply task-specific score adjustments"""
        adjusted_score = base_score

        # Complexity adjustments
        if task_chars.complexity == TaskComplexity.EXPERT:
            if model_caps.reasoning_strength < 0.8:
                adjusted_score *= 0.7  # Penalize weak reasoning for expert tasks
        elif task_chars.complexity == TaskComplexity.SIMPLE:
            if model_caps.cost_efficiency > 0.8:
                adjusted_score *= 1.2  # Boost cost-efficient models for simple tasks

        # Speed critical adjustments
        if task_chars.speed_critical and model_caps.speed_score < 0.7:
            adjusted_score *= 0.6

        # Cost sensitive adjustments
        if task_chars.cost_sensitive and model_caps.cost_efficiency < 0.6:
            adjusted_score *= 0.8

        return adjusted_score

    def _create_default_profile(self, agent_type: str) -> AgentProfile:
        """Create default profile for unknown agent types"""
        return AgentProfile(
            agent_type=agent_type,
            category=AgentCategory.SPECIALIZED,
            typical_complexity=TaskComplexity.MODERATE,
            reasoning_required=0.7,
            speed_priority=0.6,
            cost_sensitivity=0.7,
            context_needs=2000,
            special_requirements=[],
        )

    def _generate_cache_key(self, agent_type: str, task_chars: TaskCharacteristics | None) -> str:
        """Generate cache key for agent-task combination"""
        if task_chars:
            key_data = f"{agent_type}_{task_chars.complexity.value}_{task_chars.speed_critical}_{task_chars.cost_sensitive}"
        else:
            key_data = f"{agent_type}_default"

        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def _get_cached_match(self, cache_key: str) -> str | None:
        """Get cached model match if still valid"""
        if cache_key in self.match_cache:
            timestamp = self.cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self.cache_ttl:
                return self.match_cache[cache_key]
            else:
                # Expired cache entry
                del self.match_cache[cache_key]
                del self.cache_timestamps[cache_key]
        return None

    def _cache_match(self, cache_key: str, model: str) -> None:
        """Cache model match result"""
        self.match_cache[cache_key] = model
        self.cache_timestamps[cache_key] = time.time()

    async def update_model_capabilities(self, discovered_models: dict[str, dict[str, Any]]) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Update model capabilities from dynamic discovery - ASYNC M-MDP
        """
        self._ensure_initialized()
        try:
            for model_name, model_info in discovered_models.items():
                if model_name not in self.model_capabilities:
                    # Create capability profile for new model
                    capabilities = self._infer_capabilities_from_model_info(model_name, model_info)
                    self.model_capabilities[model_name] = capabilities
                    logger.info(f"Added new model capabilities: {model_name}")

            # Clear cache when capabilities change
            self.match_cache.clear()
            self.cache_timestamps.clear()

        except Exception as e:
            logger.error(
                "Failed to update model capabilities: %s: %s", type(e).__name__, e, exc_info=True
            )

    def _infer_capabilities_from_model_info(
        self, model_name: str, model_info: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> ModelCapabilities:
        """Infer capabilities from model information"""
        # Capability inference logic based on model name and info
        reasoning_strength = 0.7  # default
        speed_score = 0.7  # default
        cost_efficiency = 0.7  # default

        # Model name-based inference
        if "pro" in model_name.lower():
            reasoning_strength = 0.9
            speed_score = 0.6
            cost_efficiency = 0.4
        elif "flash" in model_name.lower():
            reasoning_strength = 0.7
            speed_score = 0.9
            cost_efficiency = 0.8
        elif "lite" in model_name.lower():
            reasoning_strength = 0.6
            speed_score = 1.0
            cost_efficiency = 1.0

        specialized_features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "tts" in model_name.lower():
            specialized_features.append("text_to_speech")
        if "2.5" in model_name:
            specialized_features.append("thinking_mode")
        if "2.0" in model_name:
            specialized_features.append("native_tool_use")

        return ModelCapabilities(
            reasoning_strength=reasoning_strength,
            speed_score=speed_score,
            cost_efficiency=cost_efficiency,
            context_window=model_info.get("context_window", 100000),
            multimodal=model_info.get("multimodal", True),
            specialized_features=specialized_features,
        )

    def get_agent_profile(self, agent_type: str) -> AgentProfile | None:
        """Get agent profile for external inspection"""
        self._ensure_initialized()
        return self.agent_profiles.get(agent_type)

    def register_agent_profile(self, profile: AgentProfile) -> None:
        """Register new agent profile"""
        self._ensure_initialized()
        self.agent_profiles[profile.agent_type] = profile
        logger.info(f"Registered new agent profile: {profile.agent_type}")

    def get_model_recommendation_explanation(
        self,
        agent_type: str,
        selected_model: str,
        task_chars: TaskCharacteristics | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get explanation for why specific model was recommended
        """
        self._ensure_initialized()
        agent_profile = self.agent_profiles.get(agent_type)
        model_caps = self.model_capabilities.get(selected_model)

        if not agent_profile or not model_caps:
            return {"error": "Profile or model capabilities not found"}

        explanation: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "agent_type": agent_type,
            "selected_model": selected_model,
            "reasoning": [],
            "scores": {},
        }

        # Calculate individual component scores
        reasoning_match = (
            min(
                model_caps.reasoning_strength / max(agent_profile.reasoning_required, 0.1),
                2.0,
            )
            / 2.0
        )
        speed_match = (
            model_caps.speed_score
            if agent_profile.speed_priority > 0.7
            else min(model_caps.speed_score * 1.5, 1.0)
        )
        cost_match = model_caps.cost_efficiency * agent_profile.cost_sensitivity

        explanation["scores"] = {
            "reasoning_match": round(reasoning_match, 3),
            "speed_match": round(speed_match, 3),
            "cost_match": round(cost_match, 3),
        }

        # Generate reasoning explanations
        if reasoning_match > 0.8:
            explanation["reasoning"].append(
                f"Model reasoning strength ({model_caps.reasoning_strength}) matches agent requirements ({agent_profile.reasoning_required})"
            )

        if speed_match > 0.8:
            explanation["reasoning"].append(
                f"Model speed ({model_caps.speed_score}) aligns with agent priority ({agent_profile.speed_priority})"
            )

        if cost_match > 0.7:
            explanation["reasoning"].append(
                f"Model cost efficiency ({model_caps.cost_efficiency}) suitable for agent sensitivity ({agent_profile.cost_sensitivity})"
            )

        return explanation


# Global instance for import
agent_model_matcher = AgentModelMatcher()
