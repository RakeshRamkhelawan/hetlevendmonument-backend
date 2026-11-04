"""Prometheus metrics for CVA (Conversational Virtual Assistant).

Ref: CVA Audit Phase 5 - Observability
"""

from prometheus_client import Counter, Histogram

# Counter for total CVA chat requests
# Labels: tenant_id, status (success/error)
cva_chat_requests_total = Counter(
    "cva_chat_requests_total",
    "Total CVA chat requests",
    ["tenant_id", "status"],
)

# Histogram for CVA chat response duration
# Labels: tenant_id
# Buckets: 0.1s, 0.5s, 1s, 2s, 5s, 10s, 30s
cva_chat_duration_seconds = Histogram(
    "cva_chat_duration_seconds",
    "CVA chat response time in seconds",
    ["tenant_id"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
