# Deployment Runbook - SanskritiSetu

**Version**: 1.0
**Last Updated**: November 2025
**Maintainer**: DevOps Team

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Blue-Green Deployment Procedure](#blue-green-deployment-procedure)
4. [Database Migration Procedure](#database-migration-procedure)
5. [Rollback Procedure](#rollback-procedure)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Troubleshooting](#troubleshooting)

---

## Overview

This runbook covers the standard deployment procedures for the SanskritiSetu platform. All deployments use blue-green deployment strategy for zero-downtime updates.

### Architecture Summary

```
                    [Load Balancer]
                         |
            +------------+------------+
            |                         |
      [Blue Env]                [Green Env]
      (Active)                  (Standby)
            |                         |
      [Blue DB]                 [Green DB]
      (Primary)                 (Replica)
```

### Key Components

| Component | Blue Port | Green Port | Health Check |
|-----------|-----------|------------|--------------|
| Backend API | 8001 | 8002 | /health |
| Frontend | 8501 | 8502 | /health |
| Database | 5432 | 5433 | TCP |
| Redis | 6379 | 6380 | PING |

---

## Pre-Deployment Checklist

### [CRITICAL] Before Any Deployment

- [ ] **Backup Verified**: Confirm latest backup exists and is verified
  ```powershell
  python -c "from deployment.backup.backup_manager import *; m = DatabaseBackupManager(); print(m.get_recovery_metrics())"
  ```

- [ ] **Tests Passing**: All unit tests pass
  ```powershell
  python -m pytest tests/ -v --tb=short
  ```

- [ ] **Quality Gate Passed (CI/Linux)**: Verify latest GitHub Actions quality/security workflows are green
  ```powershell
  # Voor Windows lokaal: gebruik pre-commit + SOP guardrails
  pre-commit run --all-files
  python scripts/validate_sop_quality.py
  ```

- [ ] **Dependencies Audited**: No critical vulnerabilities
  ```powershell
  pip install safety; safety check
  ```

- [ ] **Change Log Updated**: All changes documented in CHANGELOG.md

- [ ] **Stakeholders Notified**: Ops team, QA team informed

### Environment Verification

```powershell
# Check current active environment
$env:ACTIVE_ENV  # Should be 'blue' or 'green'

# Verify standby environment is healthy
docker-compose -f deployment/blue_green/docker-compose.$STANDBY_ENV.yml ps

# Check database replication lag
python scripts/check_db_replication.py
```

---

## Blue-Green Deployment Procedure

### Step 1: Prepare Standby Environment

```powershell
# 1. Set environment variables
$ACTIVE_ENV = "blue"    # Current active
$STANDBY_ENV = "green"  # Target for deployment

# 2. Pull latest changes to standby
cd c:\Users\rsram\OneDrive\Documenten\GitHub\SanskritiSetu.org
git pull origin main

# 3. Build new containers
docker-compose -f deployment/blue_green/docker-compose.$STANDBY_ENV.yml build --no-cache

# 4. Start standby environment
docker-compose -f deployment/blue_green/docker-compose.$STANDBY_ENV.yml up -d
```

### Step 2: Run Database Migrations

```powershell
# 1. Check migration status
alembic current

# 2. Apply migrations to standby database
$env:DATABASE_URL = "postgresql://user:pass@localhost:5433/sanskriti_setu"
alembic upgrade head

# 3. Verify migration
alembic current  # Should show latest revision
```

### Step 3: Verify Standby Health

```powershell
# 1. Health check
python -c "
from deployment.blue_green.deploy import BlueGreenDeployer, DeploymentConfig
import asyncio

config = DeploymentConfig(
    blue_url='http://localhost:8001',
    green_url='http://localhost:8002',
    health_check_path='/health'
)
deployer = BlueGreenDeployer(config)
result = asyncio.run(deployer.verify_environment('$STANDBY_ENV'))
print(f'Health Check: {\"[OK]\" if result else \"[FAIL]\"}')
"

# 2. Smoke tests
python -m pytest tests/integration/smoke/ -v --tb=short
```

### Step 4: Switch Traffic

```powershell
# 1. Execute traffic switch
python -c "
from deployment.blue_green.deploy import BlueGreenDeployer, DeploymentConfig
import asyncio

config = DeploymentConfig()
deployer = BlueGreenDeployer(config)
success = asyncio.run(deployer.switch_traffic('$STANDBY_ENV'))
print(f'Traffic Switch: {\"[OK]\" if success else \"[FAIL]\"}')
"

# 2. Verify new active environment
curl http://localhost/health  # Should return from $STANDBY_ENV
```

### Step 5: Monitor

```powershell
# 1. Watch logs for 15 minutes
docker-compose -f deployment/blue_green/docker-compose.$STANDBY_ENV.yml logs -f --tail=100

# 2. Check error rates
# [Grafana Dashboard URL]: http://grafana.internal/d/deployments

# 3. Verify key metrics
# - Response time < 200ms
# - Error rate < 0.1%
# - CPU < 70%
# - Memory < 80%
```

---

## Database Migration Procedure

### Standard Migration

```powershell
# 1. Create backup before migration
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager, BackupType
import asyncio

manager = DatabaseBackupManager()
result = asyncio.run(manager.create_backup(BackupType.FULL))
print(f'Backup ID: {result.id}')
print(f'Status: {result.status}')
"

# 2. Apply migration
alembic upgrade head

# 3. Verify
alembic current
```

### Rollback Migration

```powershell
# 1. Check current revision
alembic current

# 2. Downgrade to previous
alembic downgrade -1

# 3. For specific revision
alembic downgrade <revision_id>
```

### Data-Only Migration

For large data migrations, use maintenance window:

```powershell
# 1. Enable maintenance mode
python scripts/enable_maintenance.py

# 2. Run data migration
python scripts/migrations/migrate_data_v2.py

# 3. Disable maintenance mode
python scripts/disable_maintenance.py
```

---

## Rollback Procedure

### Automatic Rollback (within deployment)

The blue-green deployer automatically rolls back if health checks fail:

```python
# Automatic rollback is triggered when:
# - Health check fails after traffic switch
# - Error rate exceeds threshold (1%)
# - Response time exceeds threshold (5s)
```

### Manual Rollback

```powershell
# 1. Switch traffic back to previous environment
python -c "
from deployment.blue_green.deploy import BlueGreenDeployer, DeploymentConfig
import asyncio

config = DeploymentConfig()
deployer = BlueGreenDeployer(config)
success = asyncio.run(deployer.rollback())
print(f'Rollback: {\"[OK]\" if success else \"[FAIL]\"}')
"

# 2. Verify rollback
curl http://localhost/health
curl http://localhost/api/v1/status
```

### Database Rollback

```powershell
# 1. Restore from backup
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager
import asyncio

manager = DatabaseBackupManager()

# Get latest successful backup
backups = manager.list_backups()
latest = backups[0]
print(f'Restoring from: {latest.id}')

success = asyncio.run(manager.restore_backup(latest.id))
print(f'Restore: {\"[OK]\" if success else \"[FAIL]\"}')
"

# 2. Verify database state
python scripts/verify_db_state.py
```

---

## Post-Deployment Verification

### Automated Checks

```powershell
# Run post-deployment verification suite
python scripts/post_deploy_checks.py

# Expected output:
# [OK] API Health Check
# [OK] Database Connectivity
# [OK] Redis Connectivity
# [OK] Authentication Flow
# [OK] Key Endpoints Responsive
# [OK] Background Jobs Running
```

### Manual Verification Checklist

- [ ] **Login Flow**: Test admin and user login
- [ ] **API Endpoints**: Verify critical endpoints respond
- [ ] **Background Jobs**: Check job queue processing
- [ ] **Notifications**: Verify email/webhook delivery
- [ ] **Performance**: Check response times in monitoring

### Monitoring Alerts

Verify these alerts are not firing:

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| High Error Rate | > 1% | /d/errors |
| Slow Response | > 500ms avg | /d/latency |
| High CPU | > 80% | /d/resources |
| Low Disk Space | < 20% | /d/disk |

---

## Troubleshooting

### Deployment Failed - Health Check

**Symptoms**: Health check returns non-200 status

**Investigation**:
```powershell
# Check container logs
docker-compose -f deployment/blue_green/docker-compose.$ENV.yml logs backend

# Check container status
docker-compose -f deployment/blue_green/docker-compose.$ENV.yml ps

# Check health endpoint directly
curl -v http://localhost:$PORT/health
```

**Resolution**:
1. If container crashed: Check logs for error, fix code, rebuild
2. If database issue: Verify connection string, check DB status
3. If dependency issue: Verify all services are running

### Deployment Failed - Database Migration

**Symptoms**: `alembic upgrade head` fails

**Investigation**:
```powershell
# Check migration history
alembic history

# Check current state
alembic current

# Check for pending migrations
alembic heads
```

**Resolution**:
1. If syntax error: Fix migration file, test locally first
2. If data conflict: Review migration, may need data cleanup
3. If lock timeout: Check for blocking queries, wait or kill

### High Error Rate After Deployment

**Symptoms**: Error rate > 1% in monitoring

**Investigation**:
```powershell
# Check recent errors
docker-compose -f deployment/blue_green/docker-compose.$ENV.yml logs --since 5m | grep -i error

# Check application logs
tail -f /var/log/sanskriti_setu/app.log | grep ERROR
```

**Resolution**:
1. If new bug: Rollback to previous version
2. If data issue: Investigate affected records
3. If external dependency: Check third-party service status

### Performance Degradation

**Symptoms**: Response times > 500ms

**Investigation**:
```powershell
# Check resource usage
docker stats

# Check database queries
python scripts/analyze_slow_queries.py

# Check cache hit rate
redis-cli INFO stats | grep hit
```

**Resolution**:
1. If CPU bound: Scale horizontally or optimize code
2. If DB bound: Add indexes, optimize queries
3. If memory bound: Increase container limits, check for leaks

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| On-Call Engineer | Rotating | PagerDuty |
| DevOps Lead | TBD | Slack: #devops |
| Database Admin | TBD | Slack: #dba |
| Security | TBD | security@sanskriti-setu.org |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Nov 2025 | Initial version |
