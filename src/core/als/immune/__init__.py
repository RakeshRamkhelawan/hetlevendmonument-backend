"""Immune System - Threat detection and automated response."""

from typing import Any

from .antibody_registry import AntibodyAction, AntibodyRegistry
from .immune_system import ImmuneSystem, ThreatEvent
from .threat_detector import ThreatDetector, ThreatSignature

__all__ = [
    "AntibodyRegistry",
    "AntibodyAction",
    "ThreatDetector",
    "ThreatSignature",
    "ThreatEvent",
    "ImmuneSystem",
]
