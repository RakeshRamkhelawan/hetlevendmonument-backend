# Paperclip Pipeline - Administrator Runbook

**Version:** 1.0.0
**Last Updated:** March 29, 2026
**Audience:** System Administrators, DevOps Engineers
**Status:** Production Ready

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Weekly Maintenance](#weekly-maintenance)
3. [Monthly Tasks](#monthly-tasks)
4. [Pack Lifecycle Management](#pack-lifecycle-management)
5. [ML Model Management](#ml-model-management)
6. [A/B Testing Operations](#ab-testing-operations)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Procedures](#emergency-procedures)

---

## Daily Operations

### Morning Health Check (9:00 AM)

Run the daily health check script:

```bash
#!/bin/bash
# daily_health_check.sh

echo "=== Paperclip Pipeline Daily Health Check ==="

# API Health
curl -s https://api.sanskritisetu.org/health/paperclip | jq .

# Worker Queue Status
redis-cli LLEN dramatiq:default | awk '{print "Queue depth: " $1}'

# Active Packs Count
psql -h prod-db -U admin sanskritisetu -c "SELECT COUNT(*) FROM pack_activations WHERE status='active';"

# Failed Jobs (last 24h)
psql -h prod-db -U admin sanskritisetu -c "SELECT COUNT(*) FROM dramatiq_messages WHERE state='failed' AND created_at > NOW() - INTERVAL '24 hours';"

# ML Model Status
ls -la /var/lib/sanskritisetu/models/
```

### Monitoring Dashboards

Access these dashboards daily:

| Dashboard | URL | Key Metrics |
|-----------|-----|-------------|
| Grafana | https://grafana.sanskritisetu.org | Pack activations, latency, errors |
| Prometheus | https://prometheus.sanskritisetu.org | Raw metrics, queries |
| Jaeger | https://jaeger.sanskritisetu.org | Distributed traces |

### Alert Review

Check and acknowledge alerts:

```bash
# View firing alerts
curl -s https://prometheus.sanskritisetu.org/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'

# Critical alerts requiring immediate action:
# - pack_deactivation_rate_spike
# - ml_model_prediction_error_high
# - websocket_connection_failure
# - database_connection_pool_exhausted
```

---

## Weekly Maintenance

### Monday: Pack Health Review

```sql
-- Packs approaching deactivation warning (55-60 days inactive)
SELECT
    pa.pack_id,
    pa.department_id,
    pa.activated_at,
    pa.last_activity_at,
    EXTRACT(DAY FROM NOW() - pa.last_activity_at) as days_inactive,
    c.name as company_name
FROM pack_activations pa
JOIN companies c ON pa.company_id = c.id
WHERE pa.status = 'active'
    AND pa.last_activity_at < NOW() - INTERVAL '55 days'
ORDER BY days_inactive DESC;
```

### Wednesday: Performance Review

```bash
# Generate weekly performance report
python scripts/generate_weekly_report.py \
    --start-date $(date -d '7 days ago' +%Y-%m-%d) \
    --end-date $(date +%Y-%m-%d) \
    --output reports/weekly_$(date +%Y%m%d).pdf
```

Key metrics to review:
- Average pack activation score
- Time to activate (from recommendation)
- Health score distribution
- Deactivation rate
- ML model accuracy

### Friday: Backup Verification

```bash
# Verify latest backup
BACKUP_FILE=$(ls -t /srv/backups/database/daily/ | head -1)
pg_restore --list /srv/backups/database/daily/$BACKUP_FILE | head -20

# Test restore (on staging)
pg_restore -h staging-db -U admin -d test_restore /srv/backups/database/daily/$BACKUP_FILE
```

---

## Monthly Tasks

### ML Model Retraining

The ML model retrains automatically on the 1st of each month, but verify:

```bash
# Check if training completed
ls -la /var/lib/sanskritisetu/models/ | grep $(date +%Y-%m)

# Manual trigger if needed
python -m src.ml.pack_recommendation_model --retrain --output /var/lib/sanskritisetu/models/

# Validate new model
python scripts/validate_ml_model.py --model-path /var/lib/sanskritisetu/models/pack_recommendation_$(date +%Y%m).pkl
```

### Audit Log Review

```sql
-- Suspicious activity
SELECT
    action,
    COUNT(*) as count,
    COUNT(DISTINCT company_id) as companies
FROM pack_activation_audit_log
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY action
ORDER BY count DESC;

-- Unusual deactivation patterns
SELECT
    company_id,
    COUNT(*) as deactivation_count,
    DATE_TRUNC('day', created_at) as day
FROM pack_activation_audit_log
WHERE action = 'deactivated'
    AND created_at > NOW() - INTERVAL '30 days'
GROUP BY company_id, DATE_TRUNC('day', created_at)
HAVING COUNT(*) > 5;
```

### Capacity Planning

```bash
# Database growth
du -sh /var/lib/postgresql/data/

# Model storage
find /var/lib/sanskritisetu/models/ -name "*.pkl" -exec ls -lh {} \;

# Log rotation
logrotate -f /etc/logrotate.d/sanskritisetu
```

---

## Pack Lifecycle Management

### Automated Lifecycle

The system automatically manages pack lifecycles:

| Days Inactive | Action | Notification |
|---------------|--------|--------------|
| 60 | Warning status | Email to dept head |
| 75 | Reminder | Email + in-app |
| 90 | Critical | Email to admin + dept head |
| 120 | Deactivation | All stakeholders |

### Manual Intervention

#### Force Deactivate

```bash
# Emergency deactivation (bypass grace period)
curl -X POST https://api.sanskritisetu.org/api/v1/admin/packs/force-deactivate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "pack_id": "problematic-pack",
    "company_id": "...",
    "reason": "Security concern",
    "immediate": true
  }'
```

#### Extend Grace Period

```sql
-- Extend grace period for specific pack
UPDATE pack_activations
SET grace_period_end = NOW() + INTERVAL '60 days'
WHERE pack_id = '...'
  AND company_id = '...'
  AND status = 'grace_period';
```

### Bulk Operations

```bash
# Deactivate all packs for a company (e.g., offboarding)
python scripts/bulk_deactivate.py \
    --company-id "..." \
    --reason "Account closure" \
    --dry-run  # Remove for actual execution
```

---

## ML Model Management

### Model Deployment

```bash
# Deploy new model version
python scripts/deploy_ml_model.py \
    --model-file /path/to/new_model.pkl \
    --version "2026.03" \
    --canary 0.1  # 10% traffic initially

# Monitor canary
# After 24 hours with good metrics:
python scripts/deploy_ml_model.py \
    --version "2026.03" \
    --promote  # 100% traffic
```

### Model Rollback

```bash
# Rollback to previous version
python scripts/deploy_ml_model.py \
    --rollback \
    --version "2026.02"
```

### Feature Engineering Updates

```bash
# Update feature engineering
python scripts/update_features.py \
    --config configs/features_v2.yaml \
    --validate

# Apply to staging first
python scripts/update_features.py \
    --config configs/features_v2.yaml \
    --env staging
```

### Model Performance Monitoring

```sql
-- Model prediction accuracy over time
SELECT
    DATE_TRUNC('day', predicted_at) as day,
    AVG(CASE WHEN activated THEN 1 ELSE 0 END) as actual_activation_rate,
    AVG(predicted_probability) as avg_predicted_prob,
    COUNT(*) as predictions
FROM ml_predictions
WHERE predicted_at > NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', predicted_at)
ORDER BY day;
```

---

## A/B Testing Operations

### Experiment Lifecycle

```
Draft → Running → Analysis → Decision → Rolled Out/Stopped
```

### Creating an Experiment

```bash
# Create experiment via API
curl -X POST https://api.sanskritisetu.org/api/v1/admin/experiments \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Scoring Algorithm",
    "description": "Test v2 scoring algorithm",
    "hypothesis": "v2 will improve activation rate by 10%",
    "start_date": "2026-04-01",
    "end_date": "2026-04-30",
    "traffic_split": 0.5,
    "metrics": ["activation_rate", "activation_score", "user_satisfaction"],
    "min_sample_size": 1000,
    "target_segments": {
      "sectors": ["technology"],
      "company_sizes": ["11-50", "51-200"]
    }
  }'
```

### Monitoring Experiments

```bash
# Real-time experiment status
python scripts/experiment_status.py --experiment-id exp_001

# Sample output:
# Experiment: exp_001
# Status: running
# Days remaining: 15
# Control: 523 participants, 68% activation rate
# Treatment: 527 participants, 75% activation rate
# Statistical significance: p=0.003 (achieved!)
```

### Stopping Experiments

```bash
# Manual stop (emergency)
curl -X POST https://api.sanskritisetu.org/api/v1/admin/experiments/exp_001/stop \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# With winner declaration
curl -X POST https://api.sanskritisetu.org/api/v1/admin/experiments/exp_001/stop \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"winner": "treatment", "rollout": true}'
```

### Experiment Post-Mortem

After each experiment, document:
- Hypothesis (confirmed/rejected)
- Actual vs expected results
- Sample size and duration
- Statistical significance
- Business impact
- Technical learnings

---

## Troubleshooting

### Common Issues

#### 1. Pack Selector Slow Response

```bash
# Check database query time
psql -h prod-db -U admin sanskritisetu -c "
SELECT query, mean_exec_time
FROM pg_stat_statements
WHERE query LIKE '%pack%'
ORDER BY mean_exec_time DESC
LIMIT 10;
"

# Add index if missing
CREATE INDEX CONCURRENTLY idx_pack_activations_lookup
ON pack_activations(company_id, department_id, status);
```

#### 2. ML Model Not Predicting

```bash
# Check model file
test -f /var/lib/sanskritisetu/models/pack_recommendation.pkl || echo "Model file missing!"

# Check permissions
ls -la /var/lib/sanskritisetu/models/

# Reload model
curl -X POST https://api.sanskritisetu.org/api/v1/admin/ml/reload \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

#### 3. WebSocket Connection Issues

```bash
# Check Redis connection pool
redis-cli INFO clients | grep connected_clients

# Restart WebSocket server
docker-compose restart websocket-server

# Check connections
ss -tuln | grep :8080
```

#### 4. Background Jobs Stuck

```bash
# List stuck jobs
redis-cli --raw LRANGE dramatiq:default.msgs 0 -1 | jq -r '. | select(.options.redeliveries > 5)'

# Clear dead letter queue
redis-cli DEL dramatiq:default.dlq

# Restart workers
docker-compose restart worker
```

### Log Analysis

```bash
# Search for errors
grep -i "error\|exception" /var/log/sanskritisetu/api.log | tail -50

# Pack-specific logs
grep "pack_id=hr-onboarding" /var/log/sanskritisetu/api.log

# ML prediction logs
grep "ml_prediction" /var/log/sanskritisetu/ml.log | jq .

# Real-time tail
tail -f /var/log/sanskritisetu/api.log | grep -i "pack-selector"
```

---

## Emergency Procedures

### 1. Complete System Outage

```bash
# 1. Verify status
curl -s https://api.sanskritisetu.org/health

# 2. Check infrastructure
docker-compose ps
systemctl status postgresql
systemctl status redis

# 3. If all services down, restart
docker-compose down
docker-compose up -d

# 4. Verify
curl -s https://api.sanskritisetu.org/health/paperclip
```

### 2. Data Corruption

```bash
# 1. Stop writes
curl -X POST https://api.sanskritisetu.org/api/v1/admin/maintenance-mode \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true}'

# 2. Assess damage
psql -h prod-db -U admin sanskritisetu -c "CHECKPOINT;"

# 3. Restore from backup
pg_restore -h prod-db -U admin -d sanskritisetu --clean --if-exists /srv/backups/database/daily/latest.sql

# 4. Resume
curl -X POST https://api.sanskritisetu.org/api/v1/admin/maintenance-mode \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": false}'
```

### 3. Security Incident

```bash
# 1. Revoke all sessions
redis-cli FLUSHDB

# 2. Rotate secrets
# Edit /opt/sanskritisetu/.env.production
# Generate new JWT_SECRET_KEY and SECRET_KEY

# 3. Restart services
docker-compose restart

# 4. Audit access logs
grep "suspicious_ip" /var/log/nginx/access.log

# 5. Notify security team
# Follow incident response playbook
```

### 4. ML Model Producing Bad Predictions

```bash
# 1. Disable ML (fallback to heuristic)
curl -X POST https://api.sanskritisetu.org/api/v1/admin/ml/disable \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Rollback to previous model
python scripts/deploy_ml_model.py --rollback

# 3. Analyze bad predictions
python scripts/analyze_predictions.py \
    --since "2026-03-29T10:00:00Z" \
    --accuracy-threshold 0.5

# 4. Re-enable after fix
curl -X POST https://api.sanskritisetu.org/api/v1/admin/ml/enable \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Contact & Escalation

| Severity | Response Time | Contact |
|----------|---------------|---------|
| Critical (P1) | 15 minutes | On-call engineer |
| High (P2) | 1 hour | DevOps team |
| Medium (P3) | 4 hours | Engineering lead |
| Low (P4) | 24 hours | Regular ticket |

### Escalation Path

1. On-call engineer
2. DevOps lead
3. Engineering manager
4. CTO

---

**End of Admin Runbook**

For updates, see: https://wiki.sanskritisetu.org/admin-runbook
