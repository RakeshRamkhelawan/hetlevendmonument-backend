# Operations Guide - SanskritiSetu

**Version**: 1.0
**Last Updated**: November 2025
**Maintainer**: DevOps Team

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Backup Management](#backup-management)
3. [Monitoring and Alerting](#monitoring-and-alerting)
4. [Log Management](#log-management)
5. [Performance Tuning](#performance-tuning)
6. [Security Operations](#security-operations)
7. [Maintenance Windows](#maintenance-windows)

---

## Daily Operations

### Morning Checklist (09:00)

- [ ] Review overnight alerts in PagerDuty/monitoring
- [ ] Check system health dashboard
- [ ] Verify backup completion from previous night
- [ ] Review error rates from last 24 hours
- [ ] Check disk space on all servers
- [ ] Review any pending deployments

```powershell
# Quick health check script
python scripts/morning_health_check.py

# Expected output:
# [OK] API Health: Healthy
# [OK] Database: Connected (lag: 0ms)
# [OK] Redis: Connected
# [OK] Backup: Completed at 02:00 UTC
# [OK] Disk Space: 65% used
# [OK] Error Rate: 0.02%
```

### Weekly Tasks (Monday)

- [ ] Review weekly metrics report
- [ ] Analyze slow query logs
- [ ] Check certificate expiration dates
- [ ] Review and rotate credentials if needed
- [ ] Update dependency versions (patch only)
- [ ] Clean up old logs and temp files

```powershell
# Weekly maintenance script
python scripts/weekly_maintenance.py

# Actions performed:
# - Vacuum database tables
# - Rotate logs
# - Clean temp directories
# - Update metrics baselines
```

### Monthly Tasks (First Monday)

- [ ] Full security audit
- [ ] Dependency audit (minor/major updates)
- [ ] Capacity planning review
- [ ] Backup restoration test
- [ ] DR failover test (quarterly)
- [ ] Update runbooks if needed

---

## Backup Management

### Backup Schedule

| Type | Frequency | Retention | Time (UTC) |
|------|-----------|-----------|------------|
| Full | Daily | 30 days | 02:00 |
| Incremental | Hourly | 7 days | :00 |
| Weekly | Sunday | 12 weeks | 03:00 |
| Monthly | 1st of month | 12 months | 04:00 |

### Manual Backup Operations

```powershell
# Create manual backup
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager, BackupType
import asyncio

manager = DatabaseBackupManager()

# Full backup
result = asyncio.run(manager.create_backup(
    backup_type=BackupType.FULL,
    description='Manual backup before maintenance'
))
print(f'Backup ID: {result.id}')
print(f'Status: {result.status}')
print(f'Size: {result.compressed_size_bytes / 1024 / 1024:.2f} MB')
"
```

### List Backups

```powershell
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager, BackupType, BackupStatus
from datetime import datetime, timedelta, timezone

manager = DatabaseBackupManager()

# List recent backups
backups = manager.list_backups()
print('Recent Backups:')
print('-' * 80)
for b in backups[:10]:
    print(f'{b.id} | {b.backup_type.value:12} | {b.status.value:10} | {b.started_at}')
"
```

### Verify Backup

```powershell
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager
import asyncio

manager = DatabaseBackupManager()
backup_id = '<backup_id>'

result = asyncio.run(manager.verify_backup(backup_id))
print(f'Verification: {\"[OK]\" if result else \"[FAIL]\"}')")
"
```

### Restore Backup

```powershell
# DANGER: This will overwrite the database!

python -c "
from deployment.backup.backup_manager import DatabaseBackupManager
import asyncio

manager = DatabaseBackupManager()
backup_id = '<backup_id>'

# Optional: Restore to different database
# target_database = 'sanskriti_setu_restored'

result = asyncio.run(manager.restore_backup(backup_id))
print(f'Restore: {\"[OK]\" if result else \"[FAIL]\"}')")
"
```

### Recovery Metrics

```powershell
python -c "
from deployment.backup.backup_manager import DatabaseBackupManager

manager = DatabaseBackupManager()
metrics = manager.get_recovery_metrics()

print('Recovery Metrics:')
print(f'  RPO (hours): {metrics[\"rpo_hours\"]}')
print(f'  RTO (minutes): {metrics[\"rto_minutes\"]}')
print(f'  Last Full Backup: {metrics[\"last_full_backup\"]}')
print(f'  Total Backups: {metrics[\"total_backups\"]}')
print(f'  Verified Backups: {metrics[\"verified_backups\"]}')
"
```

---

## Monitoring and Alerting

### Key Metrics

| Metric | Warning | Critical | Dashboard |
|--------|---------|----------|-----------|
| API Response Time | > 200ms | > 500ms | /d/api |
| Error Rate | > 0.5% | > 1% | /d/errors |
| CPU Usage | > 70% | > 90% | /d/resources |
| Memory Usage | > 80% | > 95% | /d/resources |
| Disk Usage | > 70% | > 90% | /d/disk |
| DB Connections | > 80 | > 100 | /d/database |
| Queue Depth | > 1000 | > 5000 | /d/queues |

### Alert Configuration

Alerts are configured in Prometheus/Alertmanager:

```yaml
# Example alert rule
groups:
  - name: sanskriti_setu
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"
```

### Silencing Alerts

During maintenance windows:

```powershell
# Create silence in Alertmanager
curl -X POST http://alertmanager:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": ".*", "isRegex": true}],
    "startsAt": "2025-11-26T10:00:00Z",
    "endsAt": "2025-11-26T12:00:00Z",
    "createdBy": "ops-team",
    "comment": "Scheduled maintenance"
  }'
```

---

## Log Management

### Log Locations

| Service | Location | Rotation |
|---------|----------|----------|
| Backend API | /var/log/sanskriti_setu/api.log | Daily, 30 days |
| Database | /var/log/postgresql/postgresql.log | Weekly, 4 weeks |
| Nginx | /var/log/nginx/access.log | Daily, 14 days |
| Application | /var/log/sanskriti_setu/app.log | Daily, 30 days |

### Viewing Logs

```powershell
# Real-time logs
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend

# Filter by pattern
docker-compose logs backend | Select-String "ERROR"

# Logs from specific time
docker-compose logs --since "2025-11-26T10:00:00" backend
```

### Log Analysis

```powershell
# Count errors by type
docker-compose logs backend | Select-String "ERROR" | Group-Object | Sort-Object Count -Descending

# Find slow requests
docker-compose logs backend | Select-String "took [0-9]+ms" | Where-Object { $_ -match "took (\d+)ms" -and [int]$matches[1] -gt 1000 }

# Export logs for analysis
docker-compose logs --no-color backend > backend_logs.txt
```

### Log Rotation

Logs are rotated automatically via logrotate:

```
/var/log/sanskriti_setu/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 sanskriti sanskriti
}
```

---

## Performance Tuning

### Database Optimization

```powershell
# Analyze query performance
psql -c "
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# Update table statistics
psql -c "ANALYZE;"

# Vacuum tables
psql -c "VACUUM ANALYZE;"

# Check index usage
psql -c "
SELECT relname, idx_scan, seq_scan
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
ORDER BY seq_scan DESC;
"
```

### Connection Pool Tuning

```yaml
# PgBouncer configuration
[databases]
sanskriti_setu = host=localhost port=5432 dbname=sanskriti_setu

[pgbouncer]
pool_mode = transaction
max_client_conn = 200
default_pool_size = 20
min_pool_size = 5
reserve_pool_size = 5
```

### Redis Optimization

```powershell
# Check memory usage
redis-cli INFO memory

# Analyze key sizes
redis-cli --bigkeys

# Set memory policy
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Application Tuning

```python
# Gunicorn configuration
bind = "0.0.0.0:8000"
workers = 4  # 2 * CPU cores + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120
keepalive = 5
```

---

## Security Operations

### Daily Security Checks

```powershell
# Check for failed login attempts
docker-compose logs backend | Select-String "authentication failed" | Measure-Object

# Check for suspicious activity
docker-compose logs backend | Select-String "SECURITY|WARN|unauthorized"

# Verify SSL certificates
openssl s_client -connect api.sanskriti-setu.org:443 -servername api.sanskriti-setu.org < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Credential Rotation

```powershell
# Rotate database password
# 1. Generate new password
$newPassword = python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Update in PostgreSQL
psql -c "ALTER USER sanskriti_setu PASSWORD '$newPassword';"

# 3. Update in secrets manager / environment
# 4. Restart services
docker-compose restart backend
```

### Security Scanning

```powershell
# Dependency vulnerability scan
pip install safety
safety check

# Container vulnerability scan
docker scan sanskriti-setu-backend:latest

# SAST scan
bandit -r core/ -f json -o bandit-report.json
```

---

## Maintenance Windows

### Scheduling

| Type | Window | Duration | Frequency |
|------|--------|----------|-----------|
| Routine | Sunday 02:00-04:00 UTC | 2 hours | Weekly |
| Database | Saturday 02:00-06:00 UTC | 4 hours | Monthly |
| Major | Saturday 00:00-08:00 UTC | 8 hours | Quarterly |

### Pre-Maintenance Checklist

- [ ] Notify stakeholders 48 hours in advance
- [ ] Create backup
- [ ] Prepare rollback plan
- [ ] Update status page
- [ ] Silence non-critical alerts

### Maintenance Mode

```powershell
# Enable maintenance mode
python scripts/maintenance_mode.py --enable --message "Scheduled maintenance in progress"

# Verify maintenance page is showing
curl https://api.sanskriti-setu.org/health

# Disable maintenance mode
python scripts/maintenance_mode.py --disable
```

### Post-Maintenance Verification

```powershell
# Run post-maintenance checks
python scripts/post_maintenance_check.py

# Expected output:
# [OK] API Health
# [OK] Database Connectivity
# [OK] Background Jobs
# [OK] Cache Warmed
# [OK] All Tests Pass
```

---

## Useful Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/morning_health_check.py` | Daily health verification |
| `scripts/weekly_maintenance.py` | Weekly cleanup tasks |
| `scripts/post_deploy_checks.py` | Post-deployment verification |
| `scripts/maintenance_mode.py` | Toggle maintenance mode |
| `scripts/db_health_check.py` | Database connectivity check |
| `scripts/check_external_deps.py` | External service status |
| `scripts/verify_data_integrity.py` | Data consistency check |
| `scripts/analyze_slow_queries.py` | Query performance analysis |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Nov 2025 | Initial version |
