"""TypedDict definitions for ethical reasoning engine.

These types replace TODO(TYPE) placeholders in engine.py with structured,
documented dict types. SymPy leaf nodes remain ``Any`` because the library
is optional and its internal types are not imported at runtime.
"""

from typing import Any, TypedDict


# ------------------------------------------------------------------
# Engine state types
# ------------------------------------------------------------------


class SymbolicEngine(TypedDict):
    """Symbolic logic engine state (initialised when SymPy is available).

    Keys:
        - ``variables``: maps concept name -> SymPy Symbol object.
        - ``operators``: maps operator name -> SymPy class (And, Or, Not, Implies).
    """

    variables: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    operators: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class InferencePattern(TypedDict):
    """A named logical inference pattern loaded at startup."""

    pattern: str
    confidence: float


class ContradictionPattern(TypedDict):
    """Pattern used by the contradiction detector."""

    pattern: list[str]
    severity: str


class ContradictionDetector(TypedDict):
    """Runtime contradiction-detection configuration."""

    patterns: list[ContradictionPattern]


class PerformanceMetrics(TypedDict):
    """Metrics stored with each reasoning result."""

    frameworks_used: int
    inferences_made: int
    contradictions_found: int
    recommendations_generated: int


class ReasoningRecord(TypedDict):
    """A single entry in ``self.reasoning_history``."""

    reasoning_id: str
    timestamp: str
    scenario: "EthicalScenario"
    results: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    performance_metrics: PerformanceMetrics


# ------------------------------------------------------------------
# Scenario / input types
# ------------------------------------------------------------------


class EthicalScenario(TypedDict, total=False):
    """Input scenario for ethical reasoning.

    All keys are optional because the engine defensively calls ``.get()``
    with defaults.
    """

    action: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    stakeholders: list[str]


# ------------------------------------------------------------------
# Logical representation types
# ------------------------------------------------------------------


class Proposition(TypedDict, total=False):
    """A logical proposition extracted from an action or context.

    Fields ``truth_value``, ``dependencies`` and ``source`` are optional
    because they are only present for certain proposition sources.
    """

    text: str
    logical_form: str
    certainty: float
    type: str
    truth_value: bool | None
    dependencies: list[str]
    source: str


class EthicalConcept(TypedDict):
    """An ethical concept (e.g. autonomy, privacy) detected in a scenario."""

    concept: str
    relevance_score: float
    matching_keywords: list[str]
    context_factors: bool


class LogicalStatementDict(TypedDict):
    """Serialised form of a :class:`LogicalStatement` dataclass.

    Used inside ``LogicalRepresentation`` so that the dict can be passed
    around without importing the dataclass at every call-site.
    """

    statement_id: str
    proposition: str
    logical_form: str
    truth_value: bool | None
    certainty: float
    dependencies: list[str]


class Relationship(TypedDict):
    """A directed logical relationship between two statements."""

    from_statement: str
    to_statement: str
    relationship_type: str
    strength: float
    reasoning: str


class LogicalRepresentation(TypedDict):
    """Formal logical representation of an ethical scenario."""

    action: str
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    propositions: list[Proposition]
    ethical_concepts: list[EthicalConcept]
    logical_statements: list[LogicalStatementDict]
    relationships: list[Relationship]
    complexity_score: float


# ------------------------------------------------------------------
# Framework analysis types
# ------------------------------------------------------------------


class FrameworkAnalysis(TypedDict, total=False):
    """Result of applying one ethical framework to a scenario.

    The ``ethical_assessment`` value is framework-specific (scores, virtues,
    outcomes, etc.) so it remains ``dict[str, Any]``.
    """

    framework: str
    analysis_timestamp: str
    applicable_rules: list[str]
    ethical_assessment: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    reasoning_steps: list[str]
    framework_specific_insights: list[str]
    primary_focus: str
    key_principles: list[str]


# ------------------------------------------------------------------
# Inference / reasoning types
# ------------------------------------------------------------------


class ValidInference(TypedDict):
    """A single inference that matched an inference rule."""

    rule: str
    conclusion: str
    confidence: float
    supporting_statements: list[str | None]


class InferenceResult(TypedDict):
    """Output of ``_perform_logical_inference``."""

    valid_inferences: list[ValidInference]
    logical_conclusions: list[str]
    inference_confidence: float
    reasoning_paths: list[str]


class Contradiction(TypedDict):
    """Detected logical or ethical contradiction."""

    type: str
    contradictory_conclusions: list[str]
    severity: str
    resolution_needed: bool


class ReasoningChainDict(TypedDict):
    """Serialised reasoning chain produced by ``_generate_reasoning_chains``."""

    framework: str
    chain_id: str
    reasoning_steps: list[str]
    conclusions: list[str]
    confidence: float


class Dilemma(TypedDict, total=False):
    """An ethical dilemma detected during analysis.

    ``conflicting_frameworks`` is present for ``type == "framework_conflict"``;
    ``conflicting_principles`` is present for ``type == "principle_conflict"``.
    """

    type: str
    description: str
    conflicting_frameworks: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    conflicting_principles: list[str]
    severity: float


# ------------------------------------------------------------------
# Outcome / utility types
# ------------------------------------------------------------------


class Outcome(TypedDict):
    """A predicted outcome for consequentialist analysis."""

    outcome: str
    probability: float
    utility: float


class UtilityAnalysis(TypedDict):
    """Aggregated utility metrics across predicted outcomes."""

    expected_utility: float
    best_case_utility: float
    worst_case_utility: float
    outcome_variance: float


class StakeholderImpact(TypedDict):
    """Impact of outcomes on a single stakeholder group."""

    impact_score: float
    affected_outcomes: list[str]


# ------------------------------------------------------------------
# Rule / pattern types
# ------------------------------------------------------------------


class InferenceRule(TypedDict):
    """A hard-coded inference rule used during logical inference."""

    rule: str
    pattern: list[str]
    conclusion: str
    confidence: float


# ------------------------------------------------------------------
# Care-ethics types
# ------------------------------------------------------------------


class CareRelationship(TypedDict):
    """A care relationship identified in care-ethics analysis."""

    stakeholder: str
    care_level: str
    vulnerability: str


# ------------------------------------------------------------------
# System / fallback types
# ------------------------------------------------------------------


class SystemStatus(TypedDict):
    """Runtime status returned by ``get_system_status``."""

    ethical_rules_loaded: int
    framework_coverage: int
    reasoning_history_size: int
    symbolic_engine_available: bool
    llm_client_available: bool
    sympy_available: bool
    inference_patterns: int
    system_initialized: bool


class FallbackResult(TypedDict):
    """Result returned by ``_fallback_ethical_reasoning``."""

    reasoning_id: str
    scenario: EthicalScenario
    fallback_assessment: str
    confidence: float
    recommendations: list[str]
    reasoning_timestamp: str
