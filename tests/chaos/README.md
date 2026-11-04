# Chaos Engineering Tests

Comprehensive chaos engineering test suite for SanskritiSetu orchestration system.

## Test Categories

### 1. Network Failure Simulation (`test_network_failures.py`)

Tests system resilience against network issues:

- **Network Partitioning**: Split-brain scenarios between services
- **Latency Injection**: High latency conditions
- **Packet Loss**: Random packet drops
- **Service Degradation**: Graceful fallbacks

```bash
# Run network failure tests
pytest tests/chaos/test_network_failures.py -v -m chaos
```

### 2. Node Outage Recovery (`test_node_outage.py`)

Tests recovery from node failures:

- **Single Node Failure**: Individual node recovery
- **Multiple Node Failures**: Cascading failure handling
- **Node Recovery**: Fast recovery and rebalancing
- **Graceful Shutdown**: Connection draining
- **Failure Detection**: Heartbeat and timeout detection

```bash
# Run node outage tests
pytest tests/chaos/test_node_outage.py -v -m chaos
```

### 3. Load Testing (`test_load_orchestration.py`)

Tests performance under high load:

- **Concurrent Requests**: 100-500 concurrent users
- **Sustained Load**: Long-running load tests
- **Ramp Up/Down**: Gradual load changes
- **Stress Testing**: Finding breaking points
- **Spike Recovery**: Recovery from traffic spikes

```bash
# Run load tests
pytest tests/performance/test_load_orchestration.py -v -m performance
```

## Running All Chaos Tests

```bash
# All chaos tests
pytest tests/chaos/ -v -m chaos

# All performance tests
pytest tests/performance/ -v -m performance

# Everything
pytest tests/chaos/ tests/performance/ -v
```

## Test Environment Setup

### Prerequisites

```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Verify services
./scripts/health_check.sh
```

### Configuration

Create `.env.chaos`:

```bash
CHAOS_TEST_TARGET=http://localhost:8000
CHAOS_MAX_CONCURRENT=500
CHAOS_TEST_DURATION=300
CHAOS_METRICS_ENABLED=true
```

## Interpreting Results

### Success Criteria

| Test Type | Success Rate | Max Response Time | Recovery Time |
|-----------|--------------|-------------------|---------------|
| Network Partition | > 95% | < 2s | < 30s |
| Node Failure | > 90% | < 5s | < 60s |
| Load Test (100 users) | > 99% | < 1s | N/A |
| Load Test (500 users) | > 95% | < 2s | N/A |

### Common Failures

1. **Timeout Errors**: Increase timeout thresholds or optimize queries
2. **Connection Pool Exhaustion**: Increase pool size
3. **Memory Leaks**: Check for resource cleanup
4. **Database Lock Contention**: Optimize transactions

## Integration with CI/CD

### GitHub Actions

```yaml
# .github/workflows/chaos-tests.yml
name: Chaos Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  chaos-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start test environment
        run: docker-compose -f docker-compose.test.yml up -d

      - name: Wait for services
        run: sleep 60

      - name: Run chaos tests
        run: pytest tests/chaos/ -v --tb=short

      - name: Run load tests
        run: pytest tests/performance/ -v --tb=short

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: chaos-test-results
          path: test-results/
```

## Runbook Integration

### During Incident

1. **Identify failure type** using symptoms
2. **Run relevant chaos test** to reproduce
3. **Apply recovery procedure** from runbook
4. **Verify fix** with targeted test

### Example

```bash
# Symptom: High error rate on routing
# Hypothesis: Redis cache failure

# Reproduce
pytest tests/chaos/test_network_failures.py::TestNetworkPartitioning::test_routing_during_redis_partition -v

# If reproduced, apply fix:
# 1. Restart Redis
# 2. Clear cache
# 3. Verify

# Verify fix
pytest tests/integration/test_orchestration_system.py::TestAgentRouterAgent -v
```

## Metrics Collection

### Prometheus Metrics

```python
# During tests, collect:
- request_duration_seconds
- request_success_total
- request_failure_total
- active_connections
- cache_hit_rate
- agent_health_score
```

### Grafana Dashboard

Import `grafana/dashboards/chaos-testing.json` to visualize:

- Request rate and latency
- Error rates by endpoint
- Resource utilization
- Recovery times

## Best Practices

1. **Run in isolated environment** - Never against production
2. **Start small** - Begin with low load, gradually increase
3. **Monitor continuously** - Watch metrics during tests
4. **Document findings** - Update runbooks with new failure modes
5. **Automate regularly** - Schedule weekly chaos tests

## Troubleshooting Tests

### Test Timeouts

```bash
# Increase timeout for slow tests
pytest tests/chaos/ -v --timeout=300
```

### Connection Refused

```bash
# Verify services are running
docker-compose ps

# Check port bindings
netstat -tlnp | grep 8000
```

### Resource Exhaustion

```bash
# Clean up Docker resources
docker system prune -a

# Increase Docker resources in settings
```

## Contributing

Add new chaos tests:

1. Create test file in `tests/chaos/`
2. Use `@pytest.mark.chaos` marker
3. Include runbook documentation
4. Add to this README
5. Update CI configuration

## References

- [Chaos Engineering Principles](https://principlesofchaos.org/)
- [Netflix Chaos Monkey](https://github.com/Netflix/chaosmonkey)
- [Gremlin Chaos Engineering](https://www.gremlin.com/chaos-engineering/)
