"""EU AI Act risk level types -- shared layer, no governance deps."""

from __future__ import annotations

from enum import Enum


class AIActRiskLevel(str, Enum):
    """EU AI Act risk levels per Regulation (EU) 2024/1689."""

    UNACCEPTABLE = "unacceptable"
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH_RISK = "high_risk"
