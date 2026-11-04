from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class EthicalFramework(Enum):
    """Different ethical reasoning frameworks"""

    DEONTOLOGICAL = "deontological"  # Duty-based ethics (Kant)
    CONSEQUENTIALIST = "consequentialist"  # Outcome-based ethics (Mill)
    VIRTUE_ETHICS = "virtue_ethics"  # Character-based ethics (Aristotle)
    CARE_ETHICS = "care_ethics"  # Relationship-based ethics (Gilligan)
    PRAGMATIC = "pragmatic"  # Practical ethics (Dewey)


class LogicalOperator(Enum):
    """Logical operators for ethical reasoning"""

    AND = "and"
    OR = "or"
    NOT = "not"
    IMPLIES = "implies"
    IFF = "if_and_only_i"
    EXISTS = "exists"
    FORALL = "for_all"


@dataclass
class EthicalRule:
    """Represents an ethical rule with logical structure"""

    rule_id: str
    framework: EthicalFramework
    condition: str  # Logical condition
    conclusion: str  # Ethical conclusion
    priority: int  # Rule priority (1-10)
    confidence: float  # Rule confidence (0-1)
    source: str  # Source of the rule
    examples: list[str]  # Example applications


@dataclass
class LogicalStatement:
    """Represents a logical statement in ethical reasoning"""

    statement_id: str
    proposition: str
    logical_form: str
    truth_value: bool | None
    certainty: float
    dependencies: list[str]


@dataclass
class ReasoningChain:
    """Represents a chain of ethical reasoning"""

    chain_id: str
    premises: list[LogicalStatement]
    inference_steps: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    conclusions: list[LogicalStatement]
    framework_used: EthicalFramework
    confidence_score: float
    potential_contradictions: list[str]


@dataclass
class EthicalDilemma:
    """Represents an ethical dilemma with multiple conflicting principles"""

    dilemma_id: str
    description: str
    conflicting_principles: list[str]
    stakeholders: list[str]
    possible_outcomes: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    resolution_strategies: list[str]
