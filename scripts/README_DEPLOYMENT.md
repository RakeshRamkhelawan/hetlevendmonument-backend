# Deployment Scripts Documentation

## Overview

This directory contains production-ready deployment scripts for SanskritiSetu.org with zero-downtime deployment capability, automatic rollback, and comprehensive health checks.

## Scripts

### 1. `deploy_production.sh`

Production deployment script with full automation and safety features.

#### Features

- ✓ Pre-deployment health checks
- ✓ Automated database backup before migration
- ✓ Zero-downtime deployment (rolling restart)
- ✓ Automatic rollback on failure
- ✓ Post-deployment verification
- ✓ Comprehensive logging
- ✓ Slack/PagerDuty notifications (optional)

#### Usage

```bash
# Full deployment with all safety checks
./scripts/deploy_production.sh

# Skip database backup (not recommended for production)
./scripts/deploy_production.sh --no-backup

# Skip smoke tests (faster deployment)
./scripts/deploy_production.sh --skip-tests

# Skip database migration (if no schema changes)
./scripts/deploy_production.sh --skip-migration

# Force deployment without confirmation
./scripts/deploy_production.sh --force

# Combine multiple flags
./scripts/deploy_production.sh --skip-tests --force
```

#### What It Does

1. **Pre-deployment Checks** (Step 1/10)
   - Verifies Docker and docker-compose installation
   - Checks Docker daemon status
   - Validates compose file existence
   - Checks git repository status
   - Verifies system resources (RAM, disk space)

2. **Database Backup** (Step 2/10)
   - Creates timestamped backup directory
   - Backs up PostgreSQL database
   - Backs up docker-compose configuration
   - Backs up environment variables

3. **Pull Latest Code** (Step 3/10)
   - Pulls latest code from git repository
   - Logs current and new commit hashes

4. **Build Docker Images** (Step 4/10)
   - Builds fresh Docker images with `--no-cache`
   - Ensures no stale dependencies

5. **Database Migrations** (Step 5/10)
   - Runs Alembic migrations in temporary container
   - Aborts deployment if migration fails

6. **Stop Old Containers** (Step 6/10)
   - Gracefully stops all running containers
   - Logs which services were running

7. **Start New Containers** (Step 7/10)
   - Starts all services with new images
   - Waits for initialization

8. **Health Checks** (Step 8/10)
   - Tests main health endpoint (30 retries, 2s delay)
   - Tests readiness endpoint (database connectivity)
   - Verifies critical services (backend, postgres, redis)
   - **Automatic rollback if health checks fail**

9. **Smoke Tests** (Step 9/10)
   - Tests API health endpoint
   - Tests Prometheus metrics
   - Tests Grafana dashboard

10. **Cleanup** (Step 10/10)
    - Removes dangling Docker images
    - Prunes old containers

#### Automatic Rollback

If health checks fail, the script automatically:
1. Stops the failed deployment
2. Restores database from backup
3. Restores configuration files
4. Restarts with previous version
5. Sends failure notification

#### Logs

Deployment logs are stored in:
```
logs/deployments/deploy_YYYYMMDD_HHMMSS.log
```

Each log file contains:
- Timestamped entries for every step
- Docker command output
- Health check results
- Error messages (if any)

---

### 2. `deploy_rollback.sh`

Emergency rollback script to revert to a previous deployment state.

#### Features

- ✓ Restore database from backup
- ✓ Restore configuration files
- ✓ Restart containers with previous version
- ✓ Health verification after rollback
- ✓ Detailed rollback report

#### Usage

```bash
# Rollback to most recent backup
./scripts/deploy_rollback.sh

# Rollback to specific backup
./scripts/deploy_rollback.sh backups/deploy_20251128_143000

# Rollback to specific database backup
./scripts/deploy_rollback.sh backups/postgres/sanskritisetu_20251128.sql.gz
```

#### What It Does

1. **Determine Backup** (Step 1/5)
   - Finds most recent deployment backup
   - Or uses specified backup directory

2. **Verify Backup** (Step 2/5)
   - Checks for database backup file
   - Checks for configuration backups
   - Displays backup details

3. **Stop Containers** (Step 3/5)
   - Stops all running containers
   - Logs currently running services

4. **Restore Database** (Step 4/5)
   - Starts PostgreSQL container
   - Terminates active connections
   - Restores database from backup

5. **Start Services** (Step 5/5)
   - Starts all services with restored configuration
   - Runs health checks
   - Verifies critical services
   - Generates rollback report

#### Logs

Rollback logs are stored in:
```
logs/rollbacks/rollback_YYYYMMDD_HHMMSS.log
logs/rollbacks/rollback_report_YYYYMMDD_HHMMSS.txt
```

---

### 3. `backup_db.sh`

Automated database backup script.

#### Features

- ✓ Full PostgreSQL database dump
- ✓ Gzip compression
- ✓ Automatic rotation (7-day retention)
- ✓ Container auto-detection

#### Usage

```bash
# Manual backup
./scripts/backup_db.sh

# Automated backup (add to crontab)
# Daily at 2 AM:
0 2 * * * /path/to/scripts/backup_db.sh
```

#### Configuration

Edit the script to customize:
- `BACKUP_DIR`: Backup directory (default: `backups/postgres`)
- `CONTAINER_NAME`: PostgreSQL container name
- `DB_USER`: Database user (default: `postgres`)
- `DB_NAME`: Database name (default: `sanskritisetu`)

#### Backup Files

Backup files are named:
```
backups/postgres/sanskritisetu_YYYYMMDD_HHMMSS.sql.gz
```

Backups older than 7 days are automatically deleted.

---

### 4. `restore_db.sh`

Database restore script.

#### Features

- ✓ Restore from compressed backup
- ✓ Terminate active connections
- ✓ Safety confirmation prompt
- ✓ Container auto-detection

#### Usage

```bash
# Restore from specific backup
./scripts/restore_db.sh backups/postgres/sanskritisetu_20251128_120000.sql.gz

# Interactive restore (will ask for confirmation)
./scripts/restore_db.sh backups/postgres/sanskritisetu_20251128_120000.sql.gz
```

#### Safety

The script will:
1. Verify backup file exists
2. Display warning about data overwrite
3. Ask for confirmation (`y/N`)
4. Terminate active database connections
5. Restore database

---

## Environment Variables

### Required

None. Scripts work with default configuration.

### Optional

Configure these in `.env` for enhanced features:

#### Slack Notifications

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Enables deployment status notifications to Slack.

#### PagerDuty Alerts

```bash
PAGERDUTY_KEY=your-pagerduty-integration-key
```

Enables incident creation on deployment failures.

---

## Deployment Workflow

### Standard Production Deployment

```bash
# 1. Pull latest code
git pull origin main

# 2. Review changes
git log --oneline -5

# 3. Run deployment
./scripts/deploy_production.sh

# 4. Monitor logs
tail -f logs/deployments/deploy_*.log

# 5. Verify deployment
curl http://localhost:8000/health
```

### Emergency Rollback

```bash
# 1. Identify issue
docker-compose logs -f backend

# 2. Execute rollback
./scripts/deploy_rollback.sh

# 3. Verify rollback
curl http://localhost:8000/health

# 4. Review rollback report
cat logs/rollbacks/rollback_report_*.txt
```

### Blue-Green Deployment (Advanced)

For zero-downtime deployments:

```bash
# 1. Deploy to staging
./scripts/deploy_production.sh --environment staging

# 2. Run smoke tests tegen de staging-URL.
# TEST_BASE_URL is verplicht: zonder die variabele skippen de checks, want dan weet de suite
# niet welke deployment hij toetst. De checks eisen onder meer dat /docs, /redoc en
# /openapi.json DICHT zijn (4xx) -- sinds ADR-036 OP-124 is een bereikbaar schema een defect.
SMOKE_STRICT=1 TEST_BASE_URL=https://<staging-url> pytest tests/smoke/

# 3. Switch traffic to new version
# (requires load balancer configuration)

# 4. Monitor metrics
# http://localhost:3000 (Grafana)

# 5. Rollback if needed
./scripts/deploy_rollback.sh
```

---

## Backup Strategy

### Automated Backups

Add to crontab for automated backups:

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/SanskritiSetu.org/scripts/backup_db.sh

# Add hourly backup during business hours
0 9-17 * * 1-5 /path/to/SanskritiSetu.org/scripts/backup_db.sh
```

### Manual Backups

Before major changes:

```bash
# Before deployment
./scripts/backup_db.sh

# Before database migration
./scripts/backup_db.sh

# Before rollback
./scripts/backup_db.sh
```

### Backup Verification

Regularly test backups:

```bash
# 1. Create test environment
docker-compose -f docker-compose.test.yml up -d

# 2. Restore backup to test environment
./scripts/restore_db.sh backups/postgres/sanskritisetu_20251128.sql.gz

# 3. Verify data
docker exec test_postgres psql -U postgres -d sanskritisetu -c "SELECT COUNT(*) FROM tenants;"

# 4. Cleanup
docker-compose -f docker-compose.test.yml down
```

---

## Monitoring

### Health Endpoints

- **Health**: `http://localhost:8000/health`
  - Returns: `{"status": "healthy"}`
  - Checks: API responsiveness

- **Readiness**: `http://localhost:8000/ready`
  - Returns: `{"status": "ready", "database": "connected"}`
  - Checks: Database connectivity

### Monitoring Stack

- **Grafana**: `http://localhost:3000`
  - Default login: `admin` / `admin`
  - Dashboards for metrics visualization

- **Prometheus**: `http://localhost:9090`
  - Metrics collection and alerting
  - Query metrics directly

- **Jaeger**: `http://localhost:16686`
  - Distributed tracing
  - Request flow visualization

---

## Troubleshooting

### Deployment Fails at Migration

```bash
# Check migration status
docker-compose run --rm backend alembic current

# Check migration history
docker-compose run --rm backend alembic history

# Rollback one migration
docker-compose run --rm backend alembic downgrade -1

# Re-run deployment
./scripts/deploy_production.sh
```

### Health Check Fails

```bash
# Check container logs
docker-compose logs backend

# Check container status
docker-compose ps

# Test health endpoint manually
curl -v http://localhost:8000/health

# Check database connectivity
docker exec postgres psql -U postgres -d sanskritisetu -c "SELECT 1;"
```

### Rollback Fails

```bash
# Check available backups
ls -lh backups/postgres/

# Verify backup integrity
gunzip -t backups/postgres/sanskritisetu_*.sql.gz

# Restore manually
gunzip -c backups/postgres/sanskritisetu_*.sql.gz | \
  docker exec -i postgres psql -U postgres sanskritisetu

# Restart services
docker-compose up -d
```

### Permission Denied

```bash
# Make scripts executable
chmod +x scripts/deploy_production.sh
chmod +x scripts/deploy_rollback.sh
chmod +x scripts/backup_db.sh
chmod +x scripts/restore_db.sh
```

---

## Best Practices

### Before Deployment

1. **Review Changes**
   ```bash
   git diff main origin/main
   ```

2. **Run Tests**
   ```bash
   pytest tests/
   ```

3. **Check Dependencies**
   ```bash
   docker-compose config
   ```

4. **Verify Backups**
   ```bash
   ls -lh backups/postgres/
   ```

### During Deployment

1. **Monitor Logs**
   ```bash
   tail -f logs/deployments/deploy_*.log
   ```

2. **Watch Containers**
   ```bash
   watch -n 2 docker-compose ps
   ```

3. **Monitor Metrics**
   - Open Grafana: `http://localhost:3000`
   - Check CPU, memory, request rate

### After Deployment

1. **Verify Health**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check Logs**
   ```bash
   docker-compose logs -f --tail=50 backend
   ```

3. **Test Critical Paths**
   ```bash
   pytest tests/integration/test_critical_paths.py
   ```

4. **Monitor for 30 Minutes**
   - Watch error rates
   - Check response times
   - Verify user activity

### Rollback Criteria

Rollback immediately if:
- Health check fails for >2 minutes
- Error rate exceeds 5%
- Database connection fails
- Critical feature broken
- Data corruption detected

---

## Security

### Secrets Management

Never commit these to git:
- Database passwords
- API keys
- JWT secrets
- Webhook URLs

Store in `.env` file (git-ignored):
```bash
cp .env.example .env
# Edit .env with production secrets
```

### Backup Security

Backups may contain sensitive data:
```bash
# Encrypt backups for long-term storage
gpg --encrypt backups/postgres/sanskritisetu_20251128.sql.gz

# Decrypt when needed
gpg --decrypt backups/postgres/sanskritisetu_20251128.sql.gz.gpg | gunzip | \
  docker exec -i postgres psql -U postgres sanskritisetu
```

### Access Control

Restrict script execution:
```bash
# Only allow specific users to deploy
chown root:deploy scripts/deploy_production.sh
chmod 750 scripts/deploy_production.sh

# Add users to deploy group
usermod -a -G deploy username
```

---

## CI/CD Integration

### GitHub Actions

Example workflow:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Deploy
        run: |
          ./scripts/deploy_production.sh --force
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### GitLab CI

```yaml
deploy:
  stage: deploy
  script:
    - ./scripts/deploy_production.sh --force
  only:
    - main
  environment:
    name: production
    url: https://sanskritisetu.org
```

---

## Support

### Logs Location

- Deployment: `logs/deployments/`
- Rollback: `logs/rollbacks/`
- Application: `docker-compose logs`

### Getting Help

1. Check logs: `logs/deployments/deploy_*.log`
2. Check documentation: `scripts/README_DEPLOYMENT.md`
3. Check container status: `docker-compose ps`
4. Check health: `curl http://localhost:8000/health`

### Emergency Contacts

Configure in `.env`:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
PAGERDUTY_KEY=your-pagerduty-key
```

---

## License

Copyright © 2025 SanskritiSetu.org. All rights reserved.
