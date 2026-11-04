"""Threat Detector - Pattern-based threat detection."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.als.infrastructure.signal_bus import Signal


@dataclass
class ThreatSignature:
    """Pattern for detecting threats."""

    pattern: str
    threat_type: str
    severity: str
    description: str


class ThreatDetector:
    """Detects threats in signals using pattern matching."""

    # Built-in threat signatures
    DEFAULT_SIGNATURES = [
        ThreatSignature(
            pattern=r"(drop|delete|truncate)\s+table",
            threat_type="sql_injection",
            severity="critical",
            description="SQL injection attempt",
        ),
        ThreatSignature(
            pattern=r"eval\s*\(|exec\s*\(",
            threat_type="code_injection",
            severity="critical",
            description="Code injection attempt",
        ),
        ThreatSignature(
            pattern=r"<script.*?>.*?</script>",
            threat_type="xss",
            severity="high",
            description="Cross-site scripting attempt",
        ),
        ThreatSignature(
            pattern=r"(\b(?:\d{1,3}\.){3}\d{1,3}\b).*?(\b(?:\d{1,3}\.){3}\d{1,3}\b)",
            threat_type="suspicious_ip",
            severity="medium",
            description="Suspicious IP pattern",
        ),
    ]

    def __init__(self) -> None:
        self.signatures = self.DEFAULT_SIGNATURES.copy()

    def add_signature(self, signature: ThreatSignature) -> None:
        """Add custom threat signature."""
        self.signatures.append(signature)

    def analyze(self, signal: Signal) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze signal for threats.

        Returns threat info if detected, None otherwise.
        """
        payload_str = json.dumps(signal.payload)

        for sig in self.signatures:
            if re.search(sig.pattern, payload_str, re.IGNORECASE):
                return {
                    "threat_type": sig.threat_type,
                    "severity": sig.severity,
                    "description": sig.description,
                    "matched_pattern": sig.pattern,
                    "source_agent": signal.source_agent_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        return None

    def calculate_signature(self, signal: Signal) -> str:
        """Calculate unique signature for signal."""
        payload_str = json.dumps(signal.payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:32]
