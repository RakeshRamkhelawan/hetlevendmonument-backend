# SanskritiSetu Paperclip Pipeline - Deployment Runbook

**Version:** 1.0.0
**Last Updated:** March 29, 2026
**Owner:** DevOps Team
**Status:** Production Ready

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [System Requirements](#system-requirements)
3. [Environment Setup](#environment-setup)
4. [Deployment Procedures](#deployment-procedures)
5. [Verification Steps](#verification-steps)
6. [Rollback Procedures](#rollback-procedures)
7. [Post-Deployment Tasks](#post-deployment-tasks)
8. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

### 1 Week Before

- [ ] Code freeze announced to team
- [ ] All feature branches merged to main
- [ ] All tests passing (unit, integration, E2E)
- [ ] Security scan completed (Bandit, pip-audit)
- [ ] Performance benchmarks established
- [ ] Database migration scripts reviewed
- [ ] Rollback plan documented and tested
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified

### 1 Day Before

- [ ] Production database backup verified
- [ ] SSL certificates valid (>30 days remaining)
- [ ] Environment variables configured
- [ ] Monitoring dashboards ready
- [ ] Alert routes tested
- [ ] On-call engineer assigned
- [ ] Communication plan ready

### Deployment Day

- [ ] Team standup completed
- [ ] All checklists reviewed
- [ ] Rollback decision criteria agreed
- [ ] Go/No-Go decision made

---

## System Requirements

### Infrastructure

```yaml
Production Environment:
  Servers:
    - API Server: 2x 4 vCPU, 8GB RAM
    - Worker Server: 2x 2 vCPU, 4GB RAM
    - Database: PostgreSQL 15+ (managed)
    - Cache: Redis 7+ (managed)

  Storage:
    - Application: 20GB SSD
    - Database: 100GB SSD (expandable)
    - Backups: 500GB (30-day retention)
    - ML Models: 10GB

  Network:
    - Bandwidth: 1Gbps
    - Latency: <50ms to users
    - SSL/TLS: Required for all traffic
```

### Software Versions

```yaml
Required Versions:
  Python: 3.11+
  Node.js: 18+
  PostgreSQL: 15+
  Redis: 7+
  Docker: 24+
  Kubernetes: 1.28+ (if using K8s)
```

### Dependencies

```bash
# Python
pip install -r requirements.txt
pip install -r requirements-ml.txt  # For ML features

# Node.js
cd frontend && npm ci
```

---

## Environment Setup

### 1. Production Environment Variables

Create `/opt/sanskritisetu/.env.production`:

```bash
# =============================================================================
# Core Application
# =============================================================================
APP_ENV=production
DEBUG=false
APP_DEBUG=false
SECRET_KEY=<generate-64-char-secret>
JWT_SECRET_KEY=<generate-64-char-secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# =============================================================================
# Database
# =============================================================================
DATABASE_URL=postgresql+asyncpg://sanskritisetu:${DB_PASSWORD}@prod-db.internal:5432/sanskritisetu
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_TIMEOUT=30

# =============================================================================
# Redis
# =============================================================================
REDIS_URL=redis://:${REDIS_PASSWORD}@prod-redis.internal:6379/0
REDIS_POOL_SIZE=50
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# =============================================================================
# Message Queue (Dramatiq)
# =============================================================================
DRAMATIQ_BROKER_URL=redis://:${REDIS_PASSWORD}@prod-redis.internal:6379/1
DRAMATIQ_THREADS=8
DRAMATIQ_PROCESSES=2

# =============================================================================
# Paperclip Pipeline - Core
# =============================================================================
PACK_ACTIVATION_AUTO_THRESHOLD=0.70
PACK_DEACTIVATION_WARNING_DAYS=60
PACK_DEACTIVATION_CRITICAL_DAYS=90
PACK_DEACTIVATION_AUTO_ENABLED=false
PACK_DEACTIVATION_GRACE_PERIOD_DAYS=30

# =============================================================================
# Paperclip Pipeline - ML
# =============================================================================
ML_MODEL_PATH=/var/lib/sanskritisetu/models/pack_recommendation.pkl
ML_MIN_TRAINING_SAMPLES=100
ML_TRAINING_LOOKBACK_DAYS=90
ML_RECOMMENDATIONS_ENABLED=true
ML_MIN_CONFIDENCE_THRESHOLD=0.6

# =============================================================================
# Paperclip Pipeline - A/B Testing
# =============================================================================
EXPERIMENT_FRAMEWORK_ENABLED=true
EXPERIMENT_DEFAULT_TRAFFIC_SPLIT=0.5

# =============================================================================
# Paperclip Pipeline - Analytics
# =============================================================================
CROSS_COMPANY_ANALYTICS_ENABLED=true
ANALYTICS_HASH_SALT=<generate-32-char-salt>
ANALYTICS_OPT_OUT_COMPANIES=""
ANALYTICS_RETENTION_DAYS=730

# =============================================================================
# Feature Flags
# =============================================================================
FEATURE_FLAG_PACK_LIFECYCLE=true
FEATURE_FLAG_EXPERIMENTS=true
FEATURE_FLAG_ML_RECOMMENDATIONS=true
FEATURE_FLAG_PACK_HEALTH_AGGREGATION=true
FEATURE_FLAG_CROSS_COMPANY_ANALYTICS=true

# =============================================================================
# Observability
# =============================================================================
OTEL_EXPORTER_OTLP_ENDPOINT=https://jaeger.sanskritisetu.org:4317
OTEL_SERVICE_NAME=sanskritisetu-api
PROMETHEUS_PORT=8000

# =============================================================================
# Email (for notifications)
# =============================================================================
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=${SENDGRID_API_KEY}
EMAIL_FROM=noreply@sanskritisetu.org
```

### 2. Generate Secrets

```bash
# Generate secure secrets
cd /opt/sanskritisetu

# Application secret
python3 -c "import secrets; print(secrets.token_urlsafe(64))" > .secret_key

# JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(64))" > .jwt_secret

# Analytics salt
python3 -c "import secrets; print(secrets.token_hex(16))" > .analytics_salt

# Set permissions
chmod 600 .secret_key .jwt_secret .analytics_salt
```

### 3. Directory Structure

```bash
sudo mkdir -p /opt/sanskritisetu/{logs,models,backups,tmp}
sudo chown -R sanskritisetu:sanskritisetu /opt/sanskritisetu
sudo chmod 750 /opt/sanskritisetu
sudo chmod 700 /opt/sanskritisetu/{logs,models,backups}
```

---

## Deployment Procedures

### Option A: Blue-Green Deployment (Recommended)

```bash
#!/bin/bash
# deploy_blue_green.sh

set -e

ENVIRONMENT="production"
VERSION=$(git describe --tags --always)
BLUE="sanskritisetu-api-blue"
GREEN="sanskritisetu-api-green"
CURRENT=$(docker-compose ps -q api-blue > /dev/null 2>&1 && echo "blue" || echo "green")
NEW=$(if [ "$CURRENT" = "blue" ]; then echo "green"; else echo "blue"; fi)

echo "Current: $CURRENT, Deploying to: $NEW, Version: $VERSION"

# Step 1: Deploy to new environment
echo "Deploying to $NEW..."
docker-compose up -d api-$NEW

# Step 2: Run database migrations
echo "Running database migrations..."
docker-compose exec api-$NEW alembic upgrade head

# Step 3: Health check
echo "Health check..."
sleep 10
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health)

if [ "$HEALTH_STATUS" != "200" ]; then
    echo "Health check failed! Rolling back..."
    docker-compose stop api-$NEW
    exit 1
fi

# Step 4: Switch traffic
echo "Switching traffic to $NEW..."
sudo nginx -s reload

# Step 5: Verify
echo "Verification..."
sleep 5
curl -f https://api.sanskritisetu.org/health

echo "Deployment successful! Active: $NEW"
```

### Option B: Rolling Deployment

```bash
#!/bin/bash
# deploy_rolling.sh

set -e

# Update first server
ssh api-01 "cd /opt/sanskritisetu && ./scripts/deploy_single.sh"
sleep 30

# Verify
if ! curl -f https://api-01.sanskritisetu.org/health; then
    echo "api-01 failed! Stopping deployment."
    exit 1
fi

# Update second server
ssh api-02 "cd /opt/sanskritisetu && ./scripts/deploy_single.sh"
sleep 30

# Final verification
curl -f https://api.sanskritisetu.org/health

echo "Rolling deployment complete!"
```

### Option C: Kubernetes Deployment

```yaml
# k8s/paperclip-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sanskritisetu-api
  namespace: production
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: sanskritisetu-api
  template:
    metadata:
      labels:
        app: sanskritisetu-api
        version: "1.0.0"
    spec:
      containers:
      - name: api
        image: sanskritisetu/api:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: APP_ENV
          value: "production"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

Deploy:
```bash
kubectl apply -f k8s/paperclip-deployment.yaml
kubectl rollout status deployment/sanskritisetu-api -n production
```

---

## Verification Steps

### Immediate Verification (0-5 min)

```bash
#!/bin/bash
# verify_deployment.sh

API_URL="https://api.sanskritisetu.org"

echo "=== Health Checks ==="
curl -f "$API_URL/health" || exit 1
curl -f "$API_URL/health/paperclip" || exit 1

echo "=== API Endpoints ==="
curl -f "$API_URL/api/v1/pack-selector" -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TEST_TOKEN" \
  -d '{"company_id": "test", "department_id": "test"}' || exit 1

echo "=== Metrics ==="
curl -f "$API_URL/metrics" | grep "pack_activations_total" || exit 1

echo "=== Background Jobs ==="
docker-compose exec worker dramatiq-dashboard --url redis://redis:6379/1 | grep "pack_health_aggregation" || exit 1

echo "=== All checks passed! ==="
```

### Extended Verification (5-30 min)

- [ ] Response times < 200ms (p95)
- [ ] Error rate < 0.1%
- [ ] Database connections stable
- [ ] No critical alerts firing
- [ ] ML model loaded (check logs)
- [ ] Background jobs running
- [ ] WebSocket connections working

---

## Rollback Procedures

### Automated Rollback

```bash
#!/bin/bash
# rollback.sh

VERSION=$1  # Previous version tag

if [ -z "$VERSION" ]; then
    echo "Usage: ./rollback.sh <version>"
    exit 1
fi

echo "Rolling back to version $VERSION..."

# Stop current version
docker-compose down

# Checkout previous version
git checkout $VERSION

# Start previous version
docker-compose up -d

# Verify
curl -f https://api.sanskritisetu.org/health

echo "Rollback complete!"
```

### Database Rollback

```bash
# If migration failed:
alembic downgrade -1

# If data corruption:
pg_restore -h prod-db -U postgres -d sanskritisetu backup_YYYYMMDD.sql
```

---

## Post-Deployment Tasks

### Immediate (0-1 hour)

- [ ] Monitor error rates
- [ ] Check application logs
- [ ] Verify background jobs
- [ ] Test critical user flows
- [ ] Confirm monitoring data

### Short-term (1-24 hours)

- [ ] Performance baseline established
- [ ] User feedback collected
- [ ] Any issues documented
- [ ] Team debrief scheduled

### Long-term (1-7 days)

- [ ] Performance report generated
- [ ] Lessons learned documented
- [ ] Documentation updated
- [ ] Next release planned

---

## Troubleshooting

### Common Issues

#### 1. Database Migration Fails

```bash
# Check migration status
alembic current
alembic history

# View SQL before applying
alembic upgrade --sql head

# If locked
psql -h prod-db -U postgres -c "SELECT * FROM alembic_version;"
```

#### 2. ML Model Not Loading

```bash
# Check model file exists
ls -la /var/lib/sanskritisetu/models/

# Check permissions
sudo chown sanskritisetu:sanskritisetu /var/lib/sanskritisetu/models/*.pkl

# Check logs
tail -f /var/log/sanskritisetu/ml.log
```

#### 3. High Memory Usage

```bash
# Check memory usage
docker stats sanskritisetu-api

# Restart if needed
docker-compose restart api

# Check for memory leaks
# (monitor over time)
```

#### 4. WebSocket Connection Issues

```bash
# Check Redis
redis-cli ping

# Check connection pool
redis-cli INFO clients

# Restart WebSocket server
docker-compose restart ws
```

### Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| On-Call Engineer | TBD | Slack: #on-call |
| Database Admin | TBD | Slack: #dba |
| DevOps Lead | TBD | Slack: #devops |
| Product Owner | TBD | Slack: #product |

---

## Appendix

### A. Checksum Verification

```bash
# Verify deployment integrity
find src -type f -name "*.py" | xargs md5sum > checksums.txt
```

### B. Log Locations

```
/var/log/sanskritisetu/
├── api.log
├── worker.log
├── ml.log
└── access.log
```

### C. Backup Locations

```
/srv/backups/sanskritisetu/
├── database/
│   └── daily/
├── models/
│   └── weekly/
└── configs/
    └── on-change/
```

---

**End of Runbook**

For updates, see: https://wiki.sanskritisetu.org/deployment
