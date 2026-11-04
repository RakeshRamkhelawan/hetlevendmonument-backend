---
name: Performance Monitoring
description: Autonomous system observability and anomaly detection using Prometheus metrics.
---

# Performance Monitoring Skill

This skill allows the CVA to monitor the health, performance, and resource usage of the SanskritiSetu platform.
It leverages **Prometheus** for real-time metrics and relies on the Agent's analytical capabilities to interpret them.

## Capabilities

1.  **System Health Check**: Check CPU, Memory, and basic up/down status of services.
2.  **Latency Analysis**: Monitor API response times and throughput.
3.  **Anomaly Detection**: Compare current metrics against historical averages (if available) or thresholds.
4.  **Optimization Advice**: Suggest scaling or optimizations based on load.

## Tools

### `get_system_metrics`
Retrieves key performance indicators (KPIs) from Prometheus.

**Parameters:**
- `window` (string, default "1h"): Time window for the analysis (e.g., "5m", "1h", "24h").

**Returns:**
JSON object containing:
- `cpu_usage_percent`: Average CPU usage of backend containers.
- `memory_usage_bytes`: Memory consumption.
- `request_rate_ops`: Requests per second.
- `error_rate_percent`: 5xx errors percentage.
- `p95_latency_seconds`: 95th percentile request latency.

### `query_prometheus` (Advanced)
Execute custom PromQL queries for specific investigations.

**Parameters:**
- `query` (string): Valid PromQL query.

## Best Practices

- **Contextualize**: When a user asks "How is the system?", start with `get_system_metrics("5m")` for real-time status.
- **Drill Down**: If `error_rate_percent` > 1%, use `query_prometheus` to find which endpoint is failing.
- **Autonomy**: If you detect high latency (>500ms), suggest specific actions (e.g., "Check RabbitMQ queue depth", "Redis cache hit rate might be low").

## Dependencies
- Requires `prometheus` container to be running (`make up-obs`).
- Requires `backend` service to be exposing `/metrics`.
