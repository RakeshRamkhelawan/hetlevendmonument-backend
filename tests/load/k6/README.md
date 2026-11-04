# k6 Load Tests - Phase 3 Hardening

Sprint 5, Slice 3: Performance validation for Phase 3 Intelligent Agents

## Prerequisites

1. Install k6: https://k6.io/docs/get-started/installation/
   ```bash
   # Windows (Chocolatey)
   choco install k6

   # macOS
   brew install k6

   # Linux
   sudo gpg -k
   sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
   echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
   sudo apt-get update
   sudo apt-get install k6
   ```

2. Ensure backend is running (preferably staging environment)

3. Create test users in database (see [Test Data Setup](#test-data-setup))

## Test Scripts

### baseline.js
**Purpose**: Validate NFRs under normal load
**Target**: 50 concurrent users, 5-minute steady state
**Success**: p95 < 5s, error rate < 5%

```bash
k6 run tests/load/k6/baseline.js
```

**With custom environment:**
```bash
k6 run tests/load/k6/baseline.js \
  -e BASE_URL=https://staging.sanskritisetu.org \
  -e TEST_EMAIL=loadtest@test.com \
  -e TEST_PASSWORD=YourPassword123!
```

### stress.js
**Purpose**: Find breaking point, test stability under pressure
**Target**: Ramp to 200 users, spike to 300
**Success**: Error rate < 10%, no crashes, graceful degradation

```bash
k6 run tests/load/k6/stress.js
```

### noisy_neighbour.js
**Purpose**: Verify tenant isolation under load
**Target**: Tenant A (100 VUs heavy) vs Tenant B (10 VUs normal)
**Success**: Tenant B latency increase < 50%, zero data leakage

```bash
k6 run tests/load/k6/noisy_neighbour.js \
  -e TENANT_A_EMAIL=tenant_a@test.com \
  -e TENANT_A_PASSWORD=TenantA123! \
  -e TENANT_B_EMAIL=tenant_b@test.com \
  -e TENANT_B_PASSWORD=TenantB123!
```

## Test Data Setup

Before running tests, create test users in the database:

```sql
-- Tenant A (noisy neighbour)
INSERT INTO tenants (id, name, slug) VALUES (100, 'Tenant A', 'tenant_a');
INSERT INTO users (email, hashed_password, tenant_id, is_active)
VALUES ('tenant_a@test.com', '<bcrypt_hash>', 100, true);

-- Tenant B (normal user)
INSERT INTO tenants (id, name, slug) VALUES (200, 'Tenant B', 'tenant_b');
INSERT INTO users (email, hashed_password, tenant_id, is_active)
VALUES ('tenant_b@test.com', '<bcrypt_hash>', 200, true);

-- Create test procedures
INSERT INTO focus_builder_flows (tenant_id, name, flow_data, is_active)
VALUES
  (100, 'Simple Invoice Approval', '{"nodes": [], "edges": []}', true),
  (100, 'Complex Multi-Dept Procedure', '{"nodes": [], "edges": []}', true);
```

Or use the seed script:
```bash
python scripts/seed_load_test_data.py
```

## Interpreting Results

### Key Metrics

| Metric | Threshold | Description |
|--------|-----------|-------------|
| `http_req_duration` | p95 < 5s | Request latency (incl. waiting, receiving) |
| `http_req_failed` | < 5% | Failed requests (4xx/5xx errors) |
| `procedure_latency` | p50 < 2s, p95 < 5s | End-to-end procedure execution time |
| `tenant_b_latency` | p95 < 3s | Tenant B latency (noisy neighbour test) |
| `cross_tenant_leaks` | 0 | Data leakage across tenants (CRITICAL) |

### Success Criteria

✅ **PASS** if:
- All thresholds are met
- No crashes or 500 errors during ramp-down
- Tenant B latency increase < 50% in noisy neighbour test

❌ **FAIL** if:
- Any threshold exceeded
- Cross-tenant data leak detected (`rate > 0`)
- System becomes unresponsive (timeouts > 50%)

### Example Output

```
✓ http_req_duration..............: avg=1.2s  min=234ms med=987ms max=4.8s  p(95)=3.2s
✓ http_req_failed................: 2.34% ✓ 1234 ✗ 52789
✓ procedure_latency..............: p(50)=1.5s p(95)=4.2s
✓ tenant_b_errors................: 1.2%
✓ cross_tenant_leaks.............: 0.00% ✓ 0 ✗ 5432
```

## Advanced Options

### Cloud Execution (k6 Cloud)
```bash
k6 cloud tests/load/k6/baseline.js
```

### Custom VU Distribution
```bash
k6 run tests/load/k6/stress.js \
  --vus 100 \
  --duration 10m
```

### JSON Output for CI
```bash
k6 run tests/load/k6/baseline.js \
  --out json=baseline_results.json
```

### HTML Report (xk6-reporter)
```bash
# Install xk6-reporter first
# https://github.com/benc-uk/k6-reporter

k6 run tests/load/k6/baseline.js \
  --out json=report.json

# Convert to HTML
docker run --rm -v $(pwd):/app \
  ghcr.io/benc-uk/k6-reporter:latest \
  /app/report.json /app/report.html
```

## CI/CD Integration

Add to GitHub Actions (`.github/workflows/load-tests.yml`):

```yaml
name: Load Tests (Nightly)

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update
          sudo apt-get install k6

      - name: Run Baseline Test
        run: |
          k6 run tests/load/k6/baseline.js \
            -e BASE_URL=${{ secrets.STAGING_URL }} \
            -e TEST_EMAIL=${{ secrets.LOAD_TEST_EMAIL }} \
            -e TEST_PASSWORD=${{ secrets.LOAD_TEST_PASSWORD }} \
            --out json=baseline.json

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: load-test-results
          path: baseline.json
```

## Troubleshooting

### "Connection refused"
- Ensure backend is running: `curl http://localhost:8100/health`
- Check BASE_URL env var

### "Authentication failed"
- Verify test user exists in database
- Check email/password env vars

### High error rates (> 10%)
- Check backend logs for errors
- Verify database connection
- Check Redis/RabbitMQ services

### Timeouts in stress test
- Expected under high load
- If timeouts > 50%, system may need scaling
- Check resource limits (CPU, memory, database connections)

## References

- k6 Documentation: https://k6.io/docs/
- NFR Requirements: `docs/PHASE_3_INTELLIGENT_AGENTS.md` §2.5
- Observability Dashboard: `http://localhost:3000/grafana` (if running)
