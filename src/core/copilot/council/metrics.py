"""Prometheus metrics voor Agent Council.

Cardinality-discipline:
- `tenant_id` als label OK op counters (low-frequency increments).
- `tenant_id` NIET op histograms (1000+ tenants x N buckets = explosie).
- `user_id` NOOIT als label.

SECURITY NOTE (H-7): `tenant_id` labels kunnen tenant-enummeratie blootstellen
via het `/metrics` endpoint. Het `/metrics` endpoint MOET:
1. Network-restricted zijn (niet publiek bereikbaar).
2. Alleen toegankelijk zijn voor interne Prometheus scrapers.
3. Documenteerd in AGENTS.md als **intern-only**.

Namespace: `copilot_council_*` per ADR-014.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Total council deliberations per tenant + verdict
# Cardinality: tenants x 5 verdicts. Aanvaardbaar tot ~10k tenants
# (50k series). Bij groter tenant-bestand: overweeg `tenant_tier`
# (free/paid/enterprise) i.p.v. raw tenant_id, of recording rules in
# Prometheus die per-tenant aggregeren naar bucket.
COUNCIL_TURNS_TOTAL = Counter(
    "copilot_council_turns_total",
    "Total Agent Council deliberations completed.",
    labelnames=("tenant_id", "verdict"),
)

# Deliberation latency per Officer (incl. "council_total" voor de hele cyclus)
# Histogram buckets afgestemd op P95 < 500ms SLA (ADR-027)
COUNCIL_DELIBERATION_SECONDS = Histogram(
    "copilot_council_deliberation_seconds",
    "Per-officer deliberation latency in seconds.",
    labelnames=("officer",),
    buckets=(0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
)

# Per-Officer verdict counts (welke Officer veroorzaakt welke uitkomst?)
# Cardinality: 7 officers x 5 verdicts = 35; geen probleem
COUNCIL_VERDICT_TOTAL = Counter(
    "copilot_council_verdict_total",
    "Per-officer verdict counts.",
    labelnames=("officer", "verdict"),
)

# HITL pending -- gauge: kan op- en aflopen
HITL_PENDING = Gauge(
    "copilot_hitl_pending",
    "Pending HITL requests per tenant.",
    labelnames=("tenant_id",),
)

# Audit writes -- success/failed is mission-critical (AI Act compliance)
AUDIT_WRITES_TOTAL = Counter(
    "copilot_audit_writes_total",
    "Audit log write attempts.",
    labelnames=("status",),  # success | failed
)

# Hash chain breaks -- MOET altijd 0 zijn; verhoging = audit-incident.
# `tenant_id` label gerechtvaardigd: zeldzaam event (compliance incident),
# cardinality blijft minimaal (alleen tenants met daadwerkelijke break).
# Incident-response heeft tenant-context nodig.
HASH_CHAIN_BREAKS_TOTAL = Counter(
    "copilot_hash_chain_breaks_total",
    "Detected hash chain breaks (alerts on increase).",
    labelnames=("tenant_id",),
)

# Notification dispatcher metrics
NOTIFICATIONS_DISPATCHED_TOTAL = Counter(
    "copilot_notifications_dispatched_total",
    "Notifications successfully dispatched.",
    labelnames=("tenant_id", "severity"),
)

NOTIFICATIONS_DEFERRED_TOTAL = Counter(
    "copilot_notifications_deferred_total",
    "Notifications deferred to digest or rejected by budget.",
    labelnames=("tenant_id", "reason"),
)

# Cache metrics (koppeling sprint 3 dag 2)
COUNCIL_CACHE_HIT_TOTAL = Counter(
    "copilot_council_cache_hit_total",
    "Officer verdict cache hits.",
    labelnames=("officer",),
)

COUNCIL_CACHE_MISS_TOTAL = Counter(
    "copilot_council_cache_miss_total",
    "Officer verdict cache misses.",
    labelnames=("officer",),
)

__all__ = [
    "COUNCIL_TURNS_TOTAL",
    "COUNCIL_DELIBERATION_SECONDS",
    "COUNCIL_VERDICT_TOTAL",
    "HITL_PENDING",
    "AUDIT_WRITES_TOTAL",
    "HASH_CHAIN_BREAKS_TOTAL",
    "NOTIFICATIONS_DISPATCHED_TOTAL",
    "NOTIFICATIONS_DEFERRED_TOTAL",
    "COUNCIL_CACHE_HIT_TOTAL",
    "COUNCIL_CACHE_MISS_TOTAL",
]
