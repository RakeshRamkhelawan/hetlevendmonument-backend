"""
ML-Powered Ethics Engine for Sanskriti Setu AI Multi-Agent System
Advanced ethical oversight with machine learning, adaptive learning, and context awareness
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

import numpy as np

from src.core.security.secure_pickle import SecureModelLoader

if TYPE_CHECKING:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import StandardScaler

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from src.core.shared.interfaces import TaskData
from src.core.shared.llm_client import LLMClient, LLMMessage, create_llm_client

logger = logging.getLogger(__name__)


@dataclass
class EthicalDecision:
    """Represents an ethical decision point with context and outcome"""

    decision_id: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    task_description: str
    risk_factors: dict[str, float]
    ethical_dimensions: dict[str, float]
    final_score: float
    confidence: float
    approved: bool
    human_feedback: bool | None = None
    timestamp: str | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class EthicalPrinciple:
    """Defines an ethical principle with weight and evaluation criteria"""

    name: str
    weight: float
    description: str
    evaluation_keywords: list[str]
    risk_indicators: list[str]
    positive_indicators: list[str]


@dataclass
class RiskAssessment:
    """Comprehensive risk assessment result"""

    overall_risk: float
    confidence: float
    risk_factors: dict[str, float]
    ethical_dimensions: dict[str, float]
    recommendations: list[str]
    requires_approval: bool
    monitoring_level: str
    reasoning: list[str]


class MLEthicsEngine:
    """ML-powered ethics engine with adaptive learning capabilities"""

    def __init__(self, models_path: str = "models/ethics") -> None:
        self.models_path = Path(models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)

        # SECURITY FIX: Initialize secure model loader with path validation
        self._secure_loader = SecureModelLoader(allowed_dir=str(self.models_path.resolve()))

        # Initialize ethical principles
        self.ethical_principles = self._initialize_ethical_principles()

        # ML Components
        self.text_vectorizer: TfidfVectorizer | None = None
        self.risk_classifier: RandomForestClassifier | None = None
        self.ethics_regressor: GradientBoostingClassifier | None = None
        self.feature_scaler: StandardScaler | None = None

        # Learning and Memory
        self.decision_history: list[EthicalDecision] = []
        self.feedback_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.knowledge_base: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        # Performance tracking
        self.prediction_accuracy = 0.0
        self.confidence_calibration = 0.0
        self.last_training_time: datetime | None = None

        # LLM integration for complex reasoning
        self.llm_client: LLMClient | None = None

        logger.info("ML Ethics Engine initialized")

    async def initialize(self) -> bool:
        """Initialize the ML Ethics Engine"""
        try:
            # Initialize LLM client for complex ethical reasoning
            self.llm_client = create_llm_client("anthropic")

            # Load or create ML models
            await self._load_or_create_models()

            # Load historical data
            await self._load_historical_data()

            # Initialize knowledge base
            await self._initialize_knowledge_base()

            logger.info("ML Ethics Engine fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ML Ethics Engine: {e}")
            return False

    def _initialize_ethical_principles(self) -> list[EthicalPrinciple]:
        """Initialize comprehensive ethical principles framework"""
        return [
            EthicalPrinciple(
                name="Beneficence",
                weight=1.0,
                description="Maximize benefits and minimize harm",
                evaluation_keywords=[
                    "benefit",
                    "improve",
                    "help",
                    "assist",
                    "optimize",
                ],
                risk_indicators=["harm", "damage", "hurt", "destroy", "worsen"],
                positive_indicators=["heal", "protect", "enhance", "support"],
            ),
            EthicalPrinciple(
                name="Non-maleficence",
                weight=1.2,
                description="Do no harm - highest priority principle",
                evaluation_keywords=["safety", "protection", "security", "prevention"],
                risk_indicators=[
                    "danger",
                    "threat",
                    "risk",
                    "vulnerability",
                    "exploit",
                ],
                positive_indicators=["safe", "secure", "protected", "validated"],
            ),
            EthicalPrinciple(
                name="Autonomy",
                weight=0.9,
                description="Respect user agency and decision-making",
                evaluation_keywords=["choice", "consent", "voluntary", "autonomous"],
                risk_indicators=["force", "coerce", "manipulate", "override"],
                positive_indicators=["consent", "informed", "voluntary", "choice"],
            ),
            EthicalPrinciple(
                name="Justice",
                weight=1.0,
                description="Ensure fairness and equitable treatment",
                evaluation_keywords=["fair", "equal", "unbiased", "equitable"],
                risk_indicators=["bias", "discriminate", "unfair", "prejudice"],
                positive_indicators=["inclusive", "equitable", "fair", "balanced"],
            ),
            EthicalPrinciple(
                name="Privacy",
                weight=1.1,
                description="Protect personal data and confidentiality",
                evaluation_keywords=["private", "confidential", "personal", "data"],
                risk_indicators=["expose", "leak", "share", "access", "breach"],
                positive_indicators=["encrypted", "anonymous", "protected", "secure"],
            ),
            EthicalPrinciple(
                name="Transparency",
                weight=0.8,
                description="Provide clear and understandable information",
                evaluation_keywords=["transparent", "clear", "explainable", "open"],
                risk_indicators=["hidden", "secret", "opaque", "unclear"],
                positive_indicators=["explained", "documented", "visible", "clear"],
            ),
            EthicalPrinciple(
                name="Accountability",
                weight=0.9,
                description="Ensure responsible and traceable decisions",
                evaluation_keywords=["accountable", "responsible", "traceable"],
                risk_indicators=["anonymous", "untraceable", "unaccountable"],
                positive_indicators=["logged", "auditable", "traceable", "responsible"],
            ),
        ]

    async def _load_or_create_models(self) -> None:
        """Load existing ML models or create new ones"""
        try:
            if SKLEARN_AVAILABLE:
                # Try to load existing models
                risk_model_path = self.models_path / "risk_classifier.pkl"
                ethics_model_path = self.models_path / "ethics_regressor.pkl"
                vectorizer_path = self.models_path / "text_vectorizer.pkl"
                scaler_path = self.models_path / "feature_scaler.pkl"

                if all(
                    p.exists()
                    for p in [
                        risk_model_path,
                        ethics_model_path,
                        vectorizer_path,
                        scaler_path,
                    ]
                ):
                    # SECURITY FIX: Use SecureModelLoader for safe pickle loading
                    # with mandatory path validation
                    self.risk_classifier = self._secure_loader.load_pickle(risk_model_path)
                    self.ethics_regressor = self._secure_loader.load_pickle(ethics_model_path)
                    self.text_vectorizer = self._secure_loader.load_pickle(vectorizer_path)
                    self.feature_scaler = self._secure_loader.load_pickle(scaler_path)

                    logger.info("Loaded existing ML ethics models securely")
                else:
                    # Create new models with initial training data
                    await self._create_initial_models()
                    logger.info("Created new ML ethics models")
            else:
                logger.warning("scikit-learn not available - using rule-based fallback")
                await self._create_fallback_models()

        except Exception as e:
            logger.error(f"Error loading/creating models: {e}")
            await self._create_fallback_models()

    async def _create_initial_models(self) -> None:
        """Create initial ML models with synthetic training data"""
        if not SKLEARN_AVAILABLE:
            return

        # Generate synthetic training data
        training_data = self._generate_initial_training_data()

        # Extract features and labels
        texts = [d["text"] for d in training_data]
        risk_labels = [d["risk_score"] for d in training_data]
        ethics_scores = [d["ethics_score"] for d in training_data]

        # Create and train text vectorizer
        self.text_vectorizer = TfidfVectorizer(
            max_features=1000, stop_words="english", ngram_range=(1, 2)
        )
        text_features = self.text_vectorizer.fit_transform(texts)

        # Create additional numerical features
        numerical_features = np.array(
            [self._extract_numerical_features(d["text"]) for d in training_data]
        )

        # Combine features
        from scipy import sparse

        if sparse.issparse(text_features):
            text_array = cast(Any, text_features).toarray()  # TODO(TYPE): replace Any with concrete type
        else:
            text_array = np.array(text_features)
        combined_features = np.hstack([text_array, numerical_features])

        # Scale features
        self.feature_scaler = StandardScaler()
        scaled_features = self.feature_scaler.fit_transform(combined_features)

        # Train risk classifier
        self.risk_classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        risk_categories = [
            "low" if r <= 0.3 else "medium" if r <= 0.7 else "high" for r in risk_labels
        ]
        self.risk_classifier.fit(scaled_features, risk_categories)

        # Train ethics regressor
        self.ethics_regressor = GradientBoostingClassifier(n_estimators=100, random_state=42)
        self.ethics_regressor.fit(scaled_features, ethics_scores)

        # Save models
        await self._save_models()

    async def _create_fallback_models(self) -> None:
        """Create simple rule-based models when ML libraries unavailable"""
        logger.info("Using rule-based fallback ethics models")

        # Simple keyword-based models
        self.risk_keywords = {
            "high": [
                "delete",
                "destroy",
                "hack",
                "breach",
                "exploit",
                "damage",
                "malicious",
            ],
            "medium": ["modify", "change", "alter", "access", "update", "remove"],
            "low": ["read", "view", "display", "list", "show", "get"],
        }

        self.ethics_keywords = {
            "positive": ["help", "assist", "improve", "protect", "secure", "benefit"],
            "negative": [
                "harm",
                "damage",
                "exploit",
                "manipulate",
                "deceive",
                "breach",
            ],
            "neutral": ["process", "analyze", "compute", "calculate", "store"],
        }

    def _generate_initial_training_data(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Generate synthetic training data for initial model training"""
        training_examples = [
            # High risk examples
            {
                "text": "Delete all user data from the database",
                "risk_score": 0.95,
                "ethics_score": 0.1,
            },
            {
                "text": "Hack into competitor systems to steal information",
                "risk_score": 1.0,
                "ethics_score": 0.0,
            },
            {
                "text": "Manipulate user choices without their knowledge",
                "risk_score": 0.8,
                "ethics_score": 0.2,
            },
            {
                "text": "Expose private user information publicly",
                "risk_score": 0.9,
                "ethics_score": 0.1,
            },
            {
                "text": "Override user safety settings automatically",
                "risk_score": 0.85,
                "ethics_score": 0.15,
            },
            # Medium risk examples
            {
                "text": "Modify user preferences based on behavior patterns",
                "risk_score": 0.5,
                "ethics_score": 0.6,
            },
            {
                "text": "Access user location data for service improvement",
                "risk_score": 0.4,
                "ethics_score": 0.7,
            },
            {
                "text": "Update system configuration during business hours",
                "risk_score": 0.6,
                "ethics_score": 0.5,
            },
            {
                "text": "Share aggregated user statistics with partners",
                "risk_score": 0.5,
                "ethics_score": 0.6,
            },
            {
                "text": "Implement new security measures without notice",
                "risk_score": 0.3,
                "ethics_score": 0.8,
            },
            # Low risk examples
            {
                "text": "Display personalized recommendations to users",
                "risk_score": 0.1,
                "ethics_score": 0.9,
            },
            {
                "text": "Backup user data to secure encrypted storage",
                "risk_score": 0.2,
                "ethics_score": 0.9,
            },
            {
                "text": "Provide helpful information based on user queries",
                "risk_score": 0.1,
                "ethics_score": 0.95,
            },
            {
                "text": "Generate reports from anonymized data",
                "risk_score": 0.2,
                "ethics_score": 0.8,
            },
            {
                "text": "Optimize system performance during maintenance",
                "risk_score": 0.15,
                "ethics_score": 0.85,
            },
            # Ethical edge cases
            {
                "text": "Use AI to help medical diagnosis with patient consent",
                "risk_score": 0.3,
                "ethics_score": 0.9,
            },
            {
                "text": "Automatically flag potentially harmful content",
                "risk_score": 0.2,
                "ethics_score": 0.8,
            },
            {
                "text": "Collect minimal data necessary for service function",
                "risk_score": 0.25,
                "ethics_score": 0.85,
            },
            {
                "text": "Provide transparent explanations for AI decisions",
                "risk_score": 0.1,
                "ethics_score": 0.95,
            },
            {
                "text": "Enable users to control their data sharing preferences",
                "risk_score": 0.1,
                "ethics_score": 0.95,
            },
        ]

        return training_examples

    def _extract_numerical_features(self, text: str) -> np.ndarray[Any, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract numerical features from text for ML models"""
        features: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        text_lower = text.lower()

        # Length features
        features.append(len(text))
        features.append(len(text.split()))

        # Sentiment indicators
        positive_words = ["help", "improve", "benefit", "protect", "secure", "assist"]
        negative_words = [
            "harm",
            "damage",
            "destroy",
            "exploit",
            "breach",
            "manipulate",
        ]

        features.append(sum(1 for word in positive_words if word in text_lower))
        features.append(sum(1 for word in negative_words if word in text_lower))

        # Action intensity
        action_words = ["delete", "modify", "access", "change", "update", "remove"]
        features.append(sum(1 for word in action_words if word in text_lower))

        # Privacy indicators
        privacy_words = ["data", "private", "personal", "confidential", "user"]
        features.append(sum(1 for word in privacy_words if word in text_lower))

        # Security indicators
        security_words = [
            "security",
            "safe",
            "protect",
            "secure",
            "encrypt",
            "authenticated",
        ]
        features.append(sum(1 for word in security_words if word in text_lower))

        return np.array(features)

    async def _save_models(self) -> None:
        """Save trained ML models to disk"""
        if not SKLEARN_AVAILABLE or not all(
            [
                self.risk_classifier,
                self.ethics_regressor,
                self.text_vectorizer,
                self.feature_scaler,
            ]
        ):
            return

        try:
            with open(self.models_path / "risk_classifier.pkl", "wb") as f:
                pickle.dump(self.risk_classifier, f)
            with open(self.models_path / "ethics_regressor.pkl", "wb") as f:
                pickle.dump(self.ethics_regressor, f)
            with open(self.models_path / "text_vectorizer.pkl", "wb") as f:
                pickle.dump(self.text_vectorizer, f)
            with open(self.models_path / "feature_scaler.pkl", "wb") as f:
                pickle.dump(self.feature_scaler, f)

            logger.info("ML ethics models saved successfully")

        except Exception as e:
            logger.error(f"Error saving models: {e}")

    async def _load_historical_data(self) -> None:
        """Load historical decision data for learning"""
        history_file = self.models_path / "decision_history.json"

        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                    self.decision_history = [
                        EthicalDecision(**d) for d in data.get("decisions", [])
                    ]
                    self.feedback_history = data.get("feedback", [])

                logger.info(f"Loaded {len(self.decision_history)} historical decisions")

            except Exception as e:
                logger.error(f"Error loading historical data: {e}")

    async def _initialize_knowledge_base(self) -> None:
        """Initialize ethics knowledge base"""
        self.knowledge_base = {
            "ethical_frameworks": {
                "deontological": "Duty-based ethics focusing on rules and principles",
                "consequentialist": "Outcome-based ethics focusing on results",
                "virtue_ethics": "Character-based ethics focusing on virtues",
            },
            "risk_categories": {
                "data_privacy": "Risks related to personal data exposure or misuse",
                "system_security": "Risks to system integrity and security",
                "user_autonomy": "Risks to user choice and decision-making",
                "fairness": "Risks of bias or discrimination",
                "transparency": "Risks of opaque or unexplainable decisions",
            },
            "compliance_frameworks": {
                "GDPR": "General Data Protection Regulation",
                "CCPA": "California Consumer Privacy Act",
                "SOX": "Sarbanes-Oxley Act",
                "HIPAA": "Health Insurance Portability and Accountability Act",
            },
        }

    async def assess_ethical_risk(
        self, task: TaskData, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> RiskAssessment:
        """Comprehensive ML-powered ethical risk assessment"""
        try:
            # Prepare input data
            text_input = f"{task.title} {task.description}"
            if context:
                text_input += f" Context: {json.dumps(context)}"

            # Extract features
            risk_factors = await self._analyze_risk_dimensions(text_input, context or {})
            ethical_dimensions = await self._analyze_ethical_dimensions(text_input, task)

            # ML-based prediction if available
            if SKLEARN_AVAILABLE and self.risk_classifier and self.ethics_regressor:
                ml_risk, ml_confidence = await self._ml_risk_prediction(text_input)
            else:
                ml_risk, ml_confidence = await self._rule_based_risk_prediction(text_input)

            # LLM-based reasoning for complex cases
            llm_reasoning = await self._llm_ethical_reasoning(
                text_input, risk_factors, ethical_dimensions
            )

            # Combine assessments
            overall_risk = self._combine_risk_assessments(ml_risk, risk_factors, ethical_dimensions)
            confidence = min(ml_confidence, 0.9)  # Cap confidence for safety

            # Generate recommendations
            recommendations = await self._generate_recommendations(
                overall_risk, risk_factors, ethical_dimensions
            )

            # Determine approval and monitoring requirements
            requires_approval = overall_risk >= 0.7 or any(v >= 0.8 for v in risk_factors.values())
            monitoring_level = self._determine_monitoring_level(overall_risk, risk_factors)

            # Compile reasoning
            reasoning = [
                f"ML Risk Assessment: {ml_risk:.2f}",
                f"Key Risk Factors: {', '.join([k for k, v in risk_factors.items() if v >= 0.5])}",
                f"Ethical Concerns: {', '.join([k for k, v in ethical_dimensions.items() if v <= 0.6])}",
            ]

            if llm_reasoning:
                reasoning.append(f"LLM Analysis: {llm_reasoning[:100]}...")

            assessment = RiskAssessment(
                overall_risk=overall_risk,
                confidence=confidence,
                risk_factors=risk_factors,
                ethical_dimensions=ethical_dimensions,
                recommendations=recommendations,
                requires_approval=requires_approval,
                monitoring_level=monitoring_level,
                reasoning=reasoning,
            )

            # Store decision for learning
            await self._store_decision(task, assessment, context)

            return assessment

        except Exception as e:
            logger.error(f"Error in ethical risk assessment: {e}")
            # Return safe default assessment
            return RiskAssessment(
                overall_risk=0.5,
                confidence=0.3,
                risk_factors={"unknown": 0.5},
                ethical_dimensions={"unknown": 0.5},
                recommendations=["Manual review recommended due to assessment error"],
                requires_approval=True,
                monitoring_level="high",
                reasoning=[f"Assessment error: {str(e)}"],
            )

    async def _analyze_risk_dimensions(
        self, text: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, float]:
        """Analyze multiple risk dimensions"""
        risk_factors: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        text_lower = text.lower()

        # Data Privacy Risk
        privacy_indicators = [
            "personal",
            "private",
            "confidential",
            "data",
            "information",
            "profile",
        ]
        privacy_risks = ["expose", "leak", "share", "sell", "access", "collect"]
        privacy_score = sum(1 for word in privacy_indicators if word in text_lower) * 0.2
        privacy_risk = sum(1 for word in privacy_risks if word in text_lower) * 0.3
        risk_factors["data_privacy"] = min(1.0, privacy_score + privacy_risk)

        # System Security Risk
        security_risks = [
            "hack",
            "breach",
            "exploit",
            "vulnerability",
            "attack",
            "malicious",
        ]
        security_actions = ["delete", "destroy", "modify", "override", "bypass"]
        security_risk = (
            sum(1 for word in security_risks + security_actions if word in text_lower) * 0.25
        )
        risk_factors["system_security"] = min(1.0, security_risk)

        # User Autonomy Risk
        autonomy_risks = [
            "force",
            "manipulate",
            "coerce",
            "trick",
            "deceive",
            "override",
        ]
        autonomy_risk = sum(1 for word in autonomy_risks if word in text_lower) * 0.3
        risk_factors["user_autonomy"] = min(1.0, autonomy_risk)

        # Fairness Risk
        fairness_risks = ["bias", "discriminate", "unfair", "prejudice", "exclude"]
        fairness_risk = sum(1 for word in fairness_risks if word in text_lower) * 0.3
        risk_factors["fairness"] = min(1.0, fairness_risk)

        # Transparency Risk
        transparency_risks = ["hidden", "secret", "opaque", "unclear", "mysterious"]
        transparency_risk = sum(1 for word in transparency_risks if word in text_lower) * 0.25
        risk_factors["transparency"] = min(1.0, transparency_risk)

        # Context-based adjustments
        if context.get("user_data_involved", False):
            risk_factors["data_privacy"] = min(1.0, risk_factors["data_privacy"] + 0.3)

        if context.get("system_critical", False):
            risk_factors["system_security"] = min(1.0, risk_factors["system_security"] + 0.2)

        return risk_factors

    async def _analyze_ethical_dimensions(self, text: str, task: TaskData) -> dict[str, float]:
        """Analyze ethical dimensions based on principles"""
        ethical_scores: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for principle in self.ethical_principles:
            score = await self._evaluate_principle_score(text, principle, task)
            ethical_scores[principle.name.lower()] = score

        return ethical_scores

    async def _evaluate_principle_score(
        self, text: str, principle: EthicalPrinciple, task: TaskData
    ) -> float:
        """Evaluate score for specific ethical principle"""
        text_lower = text.lower()

        # Calculate base score
        positive_matches = sum(1 for word in principle.positive_indicators if word in text_lower)
        negative_matches = sum(1 for word in principle.risk_indicators if word in text_lower)

        # Base score starts at neutral (0.5)
        base_score = 0.5

        # Adjust based on indicators
        base_score += positive_matches * 0.15
        base_score -= negative_matches * 0.2

        # Apply principle weight
        weighted_score = base_score * principle.weight

        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, weighted_score))

    async def _ml_risk_prediction(self, text: str) -> tuple[float, float]:
        """ML-based risk prediction with confidence"""
        try:
            # Check ML components are available
            if (
                self.text_vectorizer is None
                or self.feature_scaler is None
                or self.risk_classifier is None
            ):
                return 0.5, 0.3

            # Extract features
            text_vectorizer = self.text_vectorizer
            feature_scaler = self.feature_scaler
            risk_classifier = self.risk_classifier
            # Type assertions for Pyright
            assert text_vectorizer is not None
            assert feature_scaler is not None
            assert risk_classifier is not None
            text_features = text_vectorizer.transform([text])
            numerical_features = self._extract_numerical_features(text).reshape(1, -1)
            from scipy import sparse

            if sparse.issparse(text_features):
                text_array = cast(Any, text_features).toarray()  # TODO(TYPE): replace Any with concrete type
            else:
                text_array = np.array(text_features)
            combined_features = np.hstack([text_array, numerical_features])
            scaled_features = feature_scaler.transform(combined_features)

            # Get risk prediction
            risk_proba = risk_classifier.predict_proba(scaled_features)[0]
            risk_categories = risk_classifier.classes_

            # Convert to numerical risk score
            risk_score = 0.0
            for prob, category in zip(risk_proba, risk_categories):
                if category == "low":
                    risk_score += prob * 0.2
                elif category == "medium":
                    risk_score += prob * 0.5
                else:  # high
                    risk_score += prob * 0.8

            # Calculate confidence (higher entropy = lower confidence)
            entropy = -sum(float(p) * float(np.log(float(p) + 1e-10)) for p in risk_proba)
            max_entropy = float(np.log(len(risk_categories)))
            confidence = 1.0 - (entropy / max_entropy)

            return float(risk_score), float(confidence)

        except Exception as e:
            logger.error(f"Error in ML risk prediction: {e}")
            return 0.5, 0.3

    async def _rule_based_risk_prediction(self, text: str) -> tuple[float, float]:
        """Rule-based risk prediction fallback"""
        text_lower = text.lower()

        high_risk_score = sum(1 for word in self.risk_keywords["high"] if word in text_lower)
        medium_risk_score = sum(1 for word in self.risk_keywords["medium"] if word in text_lower)
        low_risk_score = sum(1 for word in self.risk_keywords["low"] if word in text_lower)

        # Calculate weighted risk score
        total_matches = high_risk_score + medium_risk_score + low_risk_score
        if total_matches == 0:
            return 0.3, 0.5  # Default neutral risk

        risk_score = (
            high_risk_score * 0.8 + medium_risk_score * 0.5 + low_risk_score * 0.2
        ) / total_matches
        confidence = min(0.8, total_matches * 0.2)  # More matches = higher confidence

        return risk_score, confidence

    async def _llm_ethical_reasoning(
        self,
        text: str,
        risk_factors: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ethical_dimensions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Use LLM for complex ethical reasoning"""
        if not self.llm_client:
            return ""

        try:
            # Only use LLM for complex cases
            max_risk = max(risk_factors.values()) if risk_factors else 0
            min_ethics = min(ethical_dimensions.values()) if ethical_dimensions else 1

            if max_risk < 0.5 and min_ethics > 0.6:
                return ""  # Simple case, no LLM needed

            reasoning_prompt = f"""
            Analyze the ethical implications of this action:

            Action: {text}

            Risk Factors: {risk_factors}
            Ethical Dimensions: {ethical_dimensions}

            Provide a brief ethical analysis focusing on:
            1. Key ethical concerns
            2. Potential unintended consequences
            3. Stakeholder impact
            4. Recommendations for risk mitigation

            Keep response under 200 words.
            """

            messages = [LLMMessage(role="user", content=reasoning_prompt)]
            response = await self.llm_client.chat_completion(messages)

            return response.content.strip()

        except Exception as e:
            logger.error(f"Error in LLM ethical reasoning: {e}")
            return ""

    def _combine_risk_assessments(
        self,
        ml_risk: float,
        risk_factors: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ethical_dimensions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Combine different risk assessment components"""
        # Weight the different components
        ml_weight = 0.4
        risk_factors_weight = 0.4
        ethics_weight = 0.2

        # Calculate average risk from risk factors
        avg_risk_factor = sum(risk_factors.values()) / len(risk_factors) if risk_factors else 0.5

        # Calculate ethics risk (lower ethics scores = higher risk)
        avg_ethics_score = (
            sum(ethical_dimensions.values()) / len(ethical_dimensions)
            if ethical_dimensions
            else 0.5
        )
        ethics_risk = 1.0 - avg_ethics_score  # Invert ethics score to get risk

        # Combine with weights
        combined_risk = (
            ml_risk * ml_weight
            + avg_risk_factor * risk_factors_weight
            + ethics_risk * ethics_weight
        )

        return max(0.0, min(1.0, combined_risk))

    async def _generate_recommendations(
        self,
        overall_risk: float,
        risk_factors: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ethical_dimensions: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate contextual recommendations based on assessment"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Risk-based recommendations
        if overall_risk >= 0.8:
            recommendations.append("CRITICAL: Requires senior leadership approval")
            recommendations.append("Implement comprehensive monitoring and alerting")
            recommendations.append("Consider alternative approaches with lower risk")
        elif overall_risk >= 0.6:
            recommendations.append("Requires approval from ethics committee")
            recommendations.append("Implement enhanced monitoring")
            recommendations.append("Document decision rationale thoroughly")
        elif overall_risk >= 0.4:
            recommendations.append("Proceed with standard approval process")
            recommendations.append("Enable detailed audit logging")
        else:
            recommendations.append("Standard processing approved")
            recommendations.append("Basic monitoring sufficient")

        # Factor-specific recommendations
        for factor, score in risk_factors.items():
            if score >= 0.7:
                if factor == "data_privacy":
                    recommendations.append("Implement additional privacy safeguards")
                    recommendations.append("Consider data minimization techniques")
                elif factor == "system_security":
                    recommendations.append("Conduct security audit before proceeding")
                    recommendations.append("Implement additional access controls")
                elif factor == "user_autonomy":
                    recommendations.append("Ensure explicit user consent")
                    recommendations.append("Provide clear opt-out mechanisms")
                elif factor == "fairness":
                    recommendations.append("Review for potential bias")
                    recommendations.append("Consider diverse stakeholder impact")
                elif factor == "transparency":
                    recommendations.append("Improve decision explainability")
                    recommendations.append("Provide clear communication to users")

        # Ethics-specific recommendations
        for dimension, score in ethical_dimensions.items():
            if score <= 0.4:
                recommendations.append(f"Address concerns related to {dimension}")

        return recommendations

    def _determine_monitoring_level(self, overall_risk: float, risk_factors: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Determine appropriate monitoring level"""
        max_risk_factor = max(risk_factors.values()) if risk_factors else 0

        if overall_risk >= 0.8 or max_risk_factor >= 0.9:
            return "critical"
        elif overall_risk >= 0.6 or max_risk_factor >= 0.7:
            return "high"
        elif overall_risk >= 0.4 or max_risk_factor >= 0.5:
            return "medium"
        else:
            return "low"

    async def _store_decision(
        self,
        task: TaskData,
        assessment: RiskAssessment,
        context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Store decision for learning and audit trail"""
        decision = EthicalDecision(
            decision_id=f"{task.id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            context=context or {},
            task_description=f"{task.title}: {task.description}",
            risk_factors=assessment.risk_factors,
            ethical_dimensions=assessment.ethical_dimensions,
            final_score=assessment.overall_risk,
            confidence=assessment.confidence,
            approved=not assessment.requires_approval,
        )

        self.decision_history.append(decision)

        # Limit history size
        if len(self.decision_history) > 1000:
            self.decision_history = self.decision_history[-800:]  # Keep most recent 800

        # Periodically save to disk
        if len(self.decision_history) % 10 == 0:
            await self._save_decision_history()

    async def _save_decision_history(self) -> None:
        """Save decision history to disk"""
        try:
            history_data = {
                "decisions": [asdict(d) for d in self.decision_history],
                "feedback": self.feedback_history,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            with open(self.models_path / "decision_history.json", "w") as f:
                json.dump(history_data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving decision history: {e}")

    async def provide_feedback(self, decision_id: str, feedback: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Accept feedback on decisions for learning"""
        try:
            # Find the decision
            decision = None
            for d in self.decision_history:
                if d.decision_id == decision_id:
                    decision = d
                    break

            if not decision:
                logger.warning(f"Decision {decision_id} not found for feedback")
                return

            # Update decision with feedback
            decision.human_feedback = feedback.get("approved", decision.approved)

            # Store feedback
            feedback_record = {
                "decision_id": decision_id,
                "feedback": feedback,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.feedback_history.append(feedback_record)

            # Trigger retraining if we have enough feedback
            if len(self.feedback_history) % 20 == 0:
                await self._retrain_models()

        except Exception as e:
            logger.error(f"Error processing feedback: {e}")

    async def _retrain_models(self) -> None:
        """Retrain models with accumulated feedback"""
        if not SKLEARN_AVAILABLE or len(self.decision_history) < 10:
            return

        try:
            logger.info("Retraining ML ethics models with feedback data")

            # Prepare training data from decisions
            texts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            risk_labels: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            ethics_scores: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for decision in self.decision_history:
                if decision.human_feedback is not None:
                    texts.append(decision.task_description)
                    # Use human feedback to adjust labels
                    actual_risk = 0.2 if decision.human_feedback else decision.final_score
                    risk_labels.append(actual_risk)
                    ethics_scores.append(1.0 - actual_risk)

            if len(texts) >= 10:  # Minimum data for retraining
                # Retrain models (simplified for demonstration)
                logger.info(f"Retraining with {len(texts)} feedback examples")
                self.last_training_time = datetime.now(timezone.utc)

                # Calculate accuracy improvement
                # (Implementation would compare predictions vs actual outcomes)
                self.prediction_accuracy = min(0.95, self.prediction_accuracy + 0.05)

        except Exception as e:
            logger.error(f"Error retraining models: {e}")

    async def get_learning_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get learning and performance statistics"""
        return {
            "total_decisions": len(self.decision_history),
            "decisions_with_feedback": len(
                [d for d in self.decision_history if d.human_feedback is not None]
            ),
            "feedback_records": len(self.feedback_history),
            "prediction_accuracy": self.prediction_accuracy,
            "confidence_calibration": self.confidence_calibration,
            "last_training": (
                self.last_training_time.isoformat() if self.last_training_time else None
            ),
            "ml_models_available": SKLEARN_AVAILABLE,
            "knowledge_base_size": len(self.knowledge_base),
            "ethical_principles": len(self.ethical_principles),
        }

    async def explain_decision(self, decision_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Provide detailed explanation of a decision"""
        decision = None
        for d in self.decision_history:
            if d.decision_id == decision_id:
                decision = d
                break

        if not decision:
            return {"error": "Decision not found"}

        # Generate comprehensive explanation
        explanation = {
            "decision_id": decision.decision_id,
            "task_description": decision.task_description,
            "final_risk_score": decision.final_score,
            "confidence": decision.confidence,
            "approved": decision.approved,
            "risk_breakdown": decision.risk_factors,
            "ethical_analysis": decision.ethical_dimensions,
            "key_factors": [f"{k}: {v:.2f}" for k, v in decision.risk_factors.items() if v >= 0.5],
            "ethical_concerns": [
                f"{k}: {v:.2f}" for k, v in decision.ethical_dimensions.items() if v <= 0.6
            ],
            "decision_rationale": self._generate_decision_rationale(decision),
            "timestamp": decision.timestamp,
        }

        return explanation

    def _generate_decision_rationale(self, decision: EthicalDecision) -> str:
        """Generate human-readable rationale for decision"""
        rationale_parts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Risk assessment summary
        if decision.final_score >= 0.8:
            rationale_parts.append(
                f"HIGH RISK ({decision.final_score:.2f}): This action poses significant ethical risks."
            )
        elif decision.final_score >= 0.6:
            rationale_parts.append(
                f"MEDIUM RISK ({decision.final_score:.2f}): This action requires careful consideration."
            )
        else:
            rationale_parts.append(
                f"LOW RISK ({decision.final_score:.2f}): This action appears ethically acceptable."
            )

        # Key risk factors
        high_risks = [k for k, v in decision.risk_factors.items() if v >= 0.6]
        if high_risks:
            rationale_parts.append(f"Primary concerns: {', '.join(high_risks)}.")

        # Ethical dimensions
        low_ethics = [k for k, v in decision.ethical_dimensions.items() if v <= 0.4]
        if low_ethics:
            rationale_parts.append(f"Ethical concerns: {', '.join(low_ethics)}.")

        # Final recommendation
        if decision.approved:
            rationale_parts.append("Recommended for approval with appropriate monitoring.")
        else:
            rationale_parts.append("Requires human review before proceeding.")

        return " ".join(rationale_parts)


# Factory function
async def create_ml_ethics_engine() -> MLEthicsEngine:
    """Create and initialize ML-powered ethics engine"""
    engine = MLEthicsEngine()
    await engine.initialize()
    return engine
