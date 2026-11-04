"""Enums for supervisor and task management."""

from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Status values for task execution."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_FAILURE = "partial_failure"
    ESCALATED = "escalated"


class AgentStatus(str, Enum):
    """Status values for agents."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    OFFLINE = "offline"


class RoutingLayer(str, Enum):
    """GunaRouter routing layers."""

    LAYER_1_KEYWORD = "layer1_keyword"
    LAYER_2_PATTERN = "layer2_pattern"
    LAYER_3_SEMANTIC = "layer3_semantic"
    LAYER_4_META = "layer4_meta"


class SupervisorID(str, Enum):
    """Supervisor identifiers."""

    FINANCE = "finance.treasury.supervisor"
    HR = "hr.culture.supervisor"
    IT = "it.security.supervisor"
    LEGAL = "legal.compliance.supervisor"
    OPERATIONS = "operations.supply.supervisor"
    PRODUCT = "product.innovation.supervisor"
    SALES = "sales.marketing.supervisor"
    DATA = "data.ai.supervisor"
    CX = "customer.experience.supervisor"
    STRATEGY = "strategy.business.supervisor"
    CVA = "cva.meta.supervisor"
