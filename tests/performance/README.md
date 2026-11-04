# Performance Tests for SanskritiSetu

This directory contains performance and load tests for the SanskritiSetu platform.

## Overview

| Test File | Description | Duration |
|-----------|-------------|----------|
| `test_company_layer_performance.py` | Company layer microbenchmarks | ~10s |
| `test_load_orchestration.py` | Load tests for orchestration endpoints | ~5min |
| `test_p5_performance_resilience.py` | Workflow engine and resilience tests | ~10min |

## Prerequisites

1. **Redis** - Must be running on `localhost:6379` (default)
   ```bash
   # Using Docker
   docker-compose up -d redis

   # Or local Redis
   redis-server
   ```

2. **Environment Variables** - Set in `.env.test`:
   ```bash
   RUN_PERFORMANCE=1
   RUN_COMPANY_PERFORMANCE=1
   REDIS_URL=redis://localhost:6379/0
   ```

## Running Tests

### Option 1: Using the Helper Scripts

**PowerShell (Windows):**
```powershell
# Run all performance tests
.\scripts\run_performance_tests.ps1

# Run specific test pattern
.\scripts\run_performance_tests.ps1 -TestPattern "test_company_layer"

# Validate setup without running tests
.\scripts\run_performance_tests.ps1 -DryRun
```

**Batch (Windows):**
```cmd
# Run all performance tests
scripts\run_performance_tests.bat

# Run specific test
scripts\run_performance_tests.bat test_company_layer_performance
```

**Python (Cross-platform):**
```bash
# Start workers first (for tests requiring Dramatiq)
python scripts/start_performance_workers.py

# In another terminal, run tests with environment variables
export RUN_PERFORMANCE=1
export RUN_COMPANY_PERFORMANCE=1
pytest tests/performance/ -v --tb=short -m performance
```

### Option 2: Manual Execution

```bash
# Set environment variables
export RUN_PERFORMANCE=1
export RUN_COMPANY_PERFORMANCE=1

# Run all performance tests
pytest tests/performance/ -v --tb=short -m performance

# Run specific test file
pytest tests/performance/test_company_layer_performance.py -v --tb=short

# Run with verbose output
pytest tests/performance/test_load_orchestration.py -v --tb=short -s
```

## Test Categories

### Company Layer Performance (`test_company_layer_performance.py`)

Microbenchmarks for core company layer operations:
- Pack scoring (< 100ms)
- Goal alignment (< 10ms)
- Org chart operations (100 departments)
- Goal tree operations (500 goals)
- Heartbeat throughput (1000 agents)

### Load Orchestration (`test_load_orchestration.py`)

Load tests for orchestration system:
- Health endpoint load (50 concurrent users)
- Route endpoint load (100 concurrent users)
- Concurrent workflow submissions
- Sustained load (5 minutes)
- Stress tests to find breaking points

### Performance & Resilience (`test_p5_performance_resilience.py`)

Advanced performance and resilience tests:
- Workflow engine parallel load (100 workflows across 10 tenants)
- Circuit breaker behavior under load
- Database connection pool stress test

## Worker Configuration

For tests requiring Dramatiq workers:

```bash
# Start workers
python scripts/start_performance_workers.py

# Or with custom settings
python scripts/start_performance_workers.py --processes 4 --threads 8

# Validate configuration
python scripts/start_performance_workers.py --dry-run
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RUN_PERFORMANCE` | Enable all performance tests | `0` |
| `RUN_COMPANY_PERFORMANCE` | Enable company layer tests | `0` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `WORKFLOW_TIMEOUT_SECONDS` | Worker timeout | `3600` |
| `WORKER_LOG_LEVEL` | Worker logging level | `INFO` |

## Performance Targets

| Metric | Target | Critical |
|--------|--------|----------|
| Health Check | < 100ms | < 500ms |
| Route Request | < 500ms | < 2000ms |
| Workflow Create | < 2000ms | < 10000ms |
| Max RPS | 1000 | 500 |
| Error Rate | < 1% | < 5% |

## CI/CD Integration

Performance tests are NOT run on every commit. They run:
- On schedule (nightly/weekly)
- Pre-release validation
- On-demand via workflow dispatch

To skip performance tests in local runs:
```bash
# Don't set RUN_PERFORMANCE or set to 0
pytest tests/ -v --ignore=tests/performance
```

## Troubleshooting

### Redis Connection Failed
```bash
# Check Redis is running
docker ps | grep redis

# Test connection
python -c "import redis; r=redis.from_url('redis://localhost:6379/0'); r.ping(); print('OK')"
```

### Tests Skipped
Make sure environment variables are set:
```bash
export RUN_PERFORMANCE=1
export RUN_COMPANY_PERFORMANCE=1
```

### Workers Not Processing Tasks
1. Check worker logs
2. Verify Redis URL matches between workers and tests
3. Ensure workers started with: `python scripts/start_performance_workers.py`
