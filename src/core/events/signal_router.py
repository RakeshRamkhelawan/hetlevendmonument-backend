"""SignalRouter -- maps departments to default signal topics."""
from __future__ import annotations
from types import MappingProxyType
from typing import Final

_DEPARTMENT_TOPICS_RAW: dict[str, tuple[str, ...]] = {
    "hr": ("user.created", "user.updated", "email.received", "ticket.assigned", "ticket.resolved"),
    "finance": ("invoice.received", "invoice.paid", "payment.processed", "budget.threshold"),
    "it": ("alert.critical", "alert.warning", "deployment.failed", "deployment.succeeded", "incident.reported"),
    "operations": ("task.created", "task.completed", "shipment.delayed", "inventory.low"),
    "sales": ("lead.created", "lead.converted", "deal.won", "deal.lost"),
    "marketing": ("campaign.launched", "campaign.completed", "engagement.spike"),
}

DEPARTMENT_TOPICS: Final[MappingProxyType[str, tuple[str, ...]]] = MappingProxyType(_DEPARTMENT_TOPICS_RAW)

def resolve_topics(department: str | None, custom_topics: list[str] | None = None) -> list[str]:
    base = list(DEPARTMENT_TOPICS.get(department or "", ()))
    extra = custom_topics or []
    seen: set[str] = set()
    result: list[str] = []
    for t in base + extra:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result

def resolve_channel(topic: str, tenant_id: int) -> str:
    return f"organism:{tenant_id}:{topic}"
