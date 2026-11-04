"""
Co-Pilot proactive monitors.

Background scanners that detect platform conditions and propose signals to
the Agent Council. The Council decides whether the signal reaches the user.

Phase 1 monitors (sprint 5):

    Platform monitoring (no user data):
        AgentHealthMonitor      - failing agents (>50% failure rate)
        WorkflowLatencyMonitor  - workflows slower than 3x baseline
        QueueDepthMonitor       - Dramatiq queue >1000 jobs
        TokenSpikeMonitor       - LLM token usage anomaly

    Compliance signals (user action context):
        PIIExportSignal         - about to export PII
        SensitiveWorkflowSignal - workflow touches sensitive data
        RBACAnomalyMonitor      - clusters of permission-denied events
        ConsentExpiryMonitor    - upcoming consent renewals

Each monitor implements ProactiveMonitor (proactive.monitor.ProactiveMonitor)
and is registered with ProactiveScheduler in app_lifespan.py.

References:
    - docs/copilot-architecture.md sec 8
"""

from __future__ import annotations

from src.core.copilot.proactive.monitor import ProactiveMonitor
# from src.core.copilot.proactive.scheduler import ProactiveScheduler  # Disabled: requires apscheduler
from src.core.copilot.proactive.types import Signal

__all__: list[str] = [
    "ProactiveMonitor",
    # "ProactiveScheduler",
    "Signal",
]
