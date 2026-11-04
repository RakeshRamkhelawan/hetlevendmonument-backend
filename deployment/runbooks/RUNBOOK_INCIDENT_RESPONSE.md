# Incident Response Runbook - SanskritiSetu

**Version**: 1.0
**Last Updated**: November 2025
**Maintainer**: DevOps Team

---

## Table of Contents

1. [Incident Severity Levels](#incident-severity-levels)
2. [Incident Response Process](#incident-response-process)
3. [Common Incidents](#common-incidents)
4. [Escalation Matrix](#escalation-matrix)
5. [Communication Templates](#communication-templates)
6. [Post-Incident Process](#post-incident-process)

---

## Incident Severity Levels

### SEV-1: Critical

**Definition**: Complete service outage or security breach affecting all users

**Examples**:
- Platform completely down
- Data breach detected
- Database corruption
- Authentication system failure

**Response Time**: 15 minutes
**Resolution Target**: 1 hour
**Notification**: All stakeholders immediately

### SEV-2: Major

**Definition**: Significant degradation affecting majority of users

**Examples**:
- Core API endpoints failing
- Slow response times (> 10s)
- Payment processing failure
- Partial data loss

**Response Time**: 30 minutes
**Resolution Target**: 4 hours
**Notification**: Engineering + Product + Support

### SEV-3: Minor

**Definition**: Limited impact affecting subset of users

**Examples**:
- Non-critical feature broken
- Intermittent errors (< 5% of requests)
- Minor UI issues
- Single tenant affected

**Response Time**: 2 hours
**Resolution Target**: 24 hours
**Notification**: Engineering team

### SEV-4: Low

**Definition**: Minimal impact, cosmetic issues

**Examples**:
- Documentation errors
- Minor visual bugs
- Non-blocking warnings

**Response Time**: Next business day
**Resolution Target**: 1 week
**Notification**: Logged in issue tracker

---

## Incident Response Process

### Phase 1: Detection (0-5 minutes)

```
[ALERT] --> [Acknowledge] --> [Assess Severity] --> [Declare Incident]
```

**Actions**:

1. **Acknowledge Alert**
   ```powershell
   # Acknowledge in PagerDuty/monitoring system
   # Record start time
   echo "[INCIDENT] Start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
   ```

2. **Initial Assessment**
   ```powershell
   # Quick health check
   curl http://api.sanskriti-setu.org/health

   # Check error rates
   # [Grafana]: http://grafana.internal/d/overview
   ```

3. **Declare Severity**
   - SEV-1/2: Create incident channel in Slack
   - SEV-3/4: Log in issue tracker

### Phase 2: Response (5-30 minutes)

```
[Assemble Team] --> [Investigate] --> [Identify Cause] --> [Implement Fix]
```

**Actions**:

1. **Assemble Response Team**
   - Incident Commander (IC)
   - Technical Lead
   - Communications Lead (SEV-1/2)

2. **Investigation Commands**
   ```powershell
   # Check service status
   docker-compose ps

   # Check recent deployments
   git log --oneline -10

   # Check logs
   docker-compose logs --tail=100 backend

   # Check database
   python scripts/db_health_check.py

   # Check external services
   python scripts/check_external_deps.py
   ```

3. **Document Findings**
   - Timeline of events
   - Affected systems
   - User impact
   - Root cause hypothesis

### Phase 3: Mitigation (30-60 minutes)

```
[Implement Fix] --> [Verify Fix] --> [Monitor] --> [Confirm Resolution]
```

**Mitigation Options (in order of preference)**:

1. **Feature Flag Toggle**
   ```powershell
   # Disable problematic feature
   python scripts/toggle_feature.py --disable <feature_name>
   ```

2. **Rollback Deployment**
   ```powershell
   # Rollback to previous version
   python -c "
   from deployment.blue_green.deploy import BlueGreenDeployer
   import asyncio
   deployer = BlueGreenDeployer()
   asyncio.run(deployer.rollback())
   "
   ```

3. **Database Restore**
   ```powershell
   # Restore from backup
   python -c "
   from deployment.backup.backup_manager import DatabaseBackupManager
   import asyncio
   manager = DatabaseBackupManager()
   asyncio.run(manager.restore_backup('<backup_id>'))
   "
   ```

4. **Scaling**
   ```powershell
   # Scale up services
   docker-compose up -d --scale backend=5
   ```

### Phase 4: Resolution

```
[Verify System Normal] --> [Update Stakeholders] --> [Close Incident]
```

**Actions**:

1. **Verify Resolution**
   ```powershell
   # Run smoke tests
   python -m pytest tests/integration/smoke/ -v

   # Monitor for 30 minutes
   # Watch dashboards for anomalies
   ```

2. **Close Incident**
   - Update status page
   - Send resolution notification
   - Schedule post-mortem (SEV-1/2)

---

## Common Incidents

### INC-001: API Unresponsive

**Symptoms**:
- Health check fails
- HTTP 502/503 errors
- Timeouts

**Diagnosis**:
```powershell
# 1. Check container status
docker-compose ps

# 2. Check container logs
docker-compose logs --tail=50 backend

# 3. Check resource usage
docker stats

# 4. Check database connection
python -c "
from sqlalchemy import create_engine
engine = create_engine('$DATABASE_URL')
engine.connect()
print('[OK] Database connected')
"
```

**Resolution**:
```powershell
# Option A: Restart backend
docker-compose restart backend

# Option B: Rollback if recent deployment
python -c "
from deployment.blue_green.deploy import BlueGreenDeployer
import asyncio
asyncio.run(BlueGreenDeployer().rollback())
"

# Option C: Scale horizontally
docker-compose up -d --scale backend=3
```

---

### INC-002: Database Connectivity Issues

**Symptoms**:
- Connection timeout errors
- "too many connections" errors
- Slow query execution

**Diagnosis**:
```powershell
# 1. Check database status
pg_isready -h localhost -p 5432

# 2. Check connection count
psql -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# 3. Check for blocking queries
psql -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
ORDER BY duration DESC;
"

# 4. Check replication status (if applicable)
psql -c "SELECT * FROM pg_stat_replication;"
```

**Resolution**:
```powershell
# Option A: Kill idle connections
psql -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND query_start < now() - interval '30 minutes';
"

# Option B: Kill blocking queries
psql -c "SELECT pg_terminate_backend(<pid>);"

# Option C: Restart connection pooler (PgBouncer)
systemctl restart pgbouncer

# Option D: Failover to replica (if primary is down)
pg_ctl promote -D /var/lib/postgresql/data
```

---

### INC-003: High Memory Usage

**Symptoms**:
- OOM kills in container logs
- Slow response times
- Swap usage increasing

**Diagnosis**:
```powershell
# 1. Check memory usage
docker stats --no-stream

# 2. Check for memory leaks
docker exec backend python -c "
import tracemalloc
tracemalloc.start()
# ... run some operations
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
"

# 3. Check garbage collection
docker exec backend python -c "
import gc
gc.collect()
print(f'Collected: {gc.get_stats()}')
"
```

**Resolution**:
```powershell
# Option A: Restart containers
docker-compose restart backend

# Option B: Increase memory limit
# Edit docker-compose.yml: mem_limit: 2g

# Option C: Scale horizontally to distribute load
docker-compose up -d --scale backend=3
```

---

### INC-004: Authentication Failures

**Symptoms**:
- Users cannot log in
- JWT validation errors
- Session timeouts

**Diagnosis**:
```powershell
# 1. Check auth service logs
docker-compose logs --tail=50 backend | grep -i auth

# 2. Verify JWT secret is set
docker exec backend printenv JWT_SECRET_KEY

# 3. Check token validation
curl -X POST http://localhost:8000/api/v1/auth/verify \
  -H "Authorization: Bearer <token>"

# 4. Check Redis (session store)
redis-cli PING
redis-cli KEYS "session:*"
```

**Resolution**:
```powershell
# Option A: Restart auth components
docker-compose restart backend redis

# Option B: Clear expired sessions
redis-cli KEYS "session:*" | xargs redis-cli DEL

# Option C: Rotate JWT secret (will log out all users)
# 1. Generate new secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 2. Update environment variable
# 3. Restart services
```

---

### INC-005: Data Corruption Detected

**Symptoms**:
- Invalid data in responses
- Foreign key violations
- Inconsistent counts

**Diagnosis**:
```powershell
# 1. Identify affected tables
psql -c "
SELECT relname, n_dead_tup, n_live_tup
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000;
"

# 2. Check for constraint violations
psql -c "
SELECT conrelid::regclass AS table_name, conname, condeferrable
FROM pg_constraint
WHERE NOT pg_catalog.pg_constraint.convalidated;
"

# 3. Verify data integrity
python scripts/verify_data_integrity.py
```

**Resolution**:
```powershell
# Option A: Point-in-time recovery
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager
import asyncio
from datetime import datetime, timedelta

manager = DatabaseBackupManager()
# Recover to 1 hour before corruption
target_time = datetime.now() - timedelta(hours=1)
asyncio.run(manager.restore_backup('<backup_id>', point_in_time=target_time))
"

# Option B: Manual data fix (if isolated)
psql -c "BEGIN; UPDATE ... ; COMMIT;"

# Option C: Full restore from backup
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager
import asyncio
manager = DatabaseBackupManager()
backups = manager.list_backups()
asyncio.run(manager.restore_backup(backups[0].id))
"
```

---

## Escalation Matrix

| Level | Trigger | Who to Contact | Method |
|-------|---------|----------------|--------|
| L1 | Any alert | On-Call Engineer | PagerDuty |
| L2 | SEV-1/2 or 30min unresolved | Tech Lead | Slack + Phone |
| L3 | 1 hour unresolved | Engineering Manager | Phone |
| L4 | Data breach | Security Team + Legal | Phone + Email |
| L5 | Multi-hour outage | Executive Team | Phone |

---

## Communication Templates

### Initial Incident Notification (Internal)

```
[INCIDENT] SEV-{1/2/3} - {Brief Description}

Status: Investigating
Impact: {User impact description}
Start Time: {HH:MM UTC}
Incident Commander: {Name}

Current Actions:
- {Action 1}
- {Action 2}

Next Update: {Time}

#incident-{id}
```

### Status Page Update (External)

```
Investigating - {Service} Issues

We are currently investigating reports of {issue description}.
Some users may experience {impact}.

We will provide an update in 30 minutes.

Posted: {Time}
```

### Resolution Notification

```
Resolved - {Service} Issues

The issue affecting {service} has been resolved.

Duration: {X hours Y minutes}
Root Cause: {Brief description}
Resolution: {What was done}

We apologize for any inconvenience.

Posted: {Time}
```

---

## Post-Incident Process

### Post-Mortem Template

**Incident**: {ID} - {Title}
**Date**: {Date}
**Duration**: {Duration}
**Severity**: SEV-{X}
**Author**: {Name}

#### Summary
{1-2 sentence description}

#### Timeline
| Time | Event |
|------|-------|
| HH:MM | First alert |
| HH:MM | Incident declared |
| HH:MM | Root cause identified |
| HH:MM | Fix deployed |
| HH:MM | Monitoring confirmed resolution |

#### Root Cause
{Detailed explanation}

#### Impact
- Users affected: {count}
- Requests failed: {count}
- Revenue impact: {if applicable}

#### What Went Well
- {Item 1}
- {Item 2}

#### What Went Wrong
- {Item 1}
- {Item 2}

#### Action Items
| Priority | Action | Owner | Due Date |
|----------|--------|-------|----------|
| P1 | {Action} | {Name} | {Date} |
| P2 | {Action} | {Name} | {Date} |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Nov 2025 | Initial version |
