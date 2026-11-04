# SanskritiSetu Troubleshooting Guide

> **Versie:** 3.0
> **Laatst bijgewerkt:** Maart 2026

---

## Table of Contents

1. [Quick Diagnostics](#1-quick-diagnostics)
2. [Installation Issues](#2-installation-issues)
3. [Database Issues](#3-database-issues)
4. [API Issues](#4-api-issues)
5. [Frontend Issues](#5-frontend-issues)
6. [External Agent Issues](#6-external-agent-issues)
7. [Board Governance Issues](#7-board-governance-issues)
8. [Performance Issues](#8-performance-issues)
9. [Security Issues](#9-security-issues)
10. [Getting Help](#10-getting-help)

---

## 1. Quick Diagnostics

### 1.1 System Health Check

Run the comprehensive health check:

```bash
# Backend health
curl http://localhost:8110/health
curl http://localhost:8110/health/ready
curl http://localhost:8110/health/deep

# Frontend
curl http://localhost:5174

# Database
docker-compose exec postgres pg_isready -U postgres

# Redis
docker-compose exec redis redis-cli ping

# RabbitMQ
curl http://localhost:15672/api/overview -u guest:guest
```

### 1.2 Log Inspection

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f --tail=100 frontend

# Filter by time
docker-compose logs --since=10m backend
docker-compose logs --until=2026-03-12T10:00:00 backend
```

### 1.3 Status Overview

```bash
# Container status
docker-compose ps
docker stats

# Resource usage
docker system df
docker system prune -f  # Clean up unused resources
```

---

## 2. Installation Issues

### 2.1 Docker Not Found

**Error:**
```
docker: command not found
```

**Solution:**
```bash
# Linux
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Windows/macOS
# Install Docker Desktop from https://www.docker.com/products/docker-desktop
```

### 2.2 Port Already in Use

**Error:**
```
Bind for 0.0.0.0:5435 failed: port is already allocated
```

**Solution:**
```bash
# Find process using port
# Linux/macOS
lsof -i :5435
sudo lsof -i :5435  # if nothing shows

# Windows (PowerShell)
netstat -ano | findstr :5435

# Kill process
# Linux/macOS
kill -9 <PID>

# Windows
taskkill /PID <PID> /F

# Or change port in .env
# POSTGRES_PORT=5436
```

### 2.3 Permission Denied

**Error:**
```
permission denied while trying to connect to Docker daemon
```

**Solution:**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Or use sudo (not recommended for production)
sudo docker-compose up -d
```

### 2.4 Container Fails to Start

**Check logs:**
```bash
docker-compose logs <service-name>
docker-compose logs --tail=50 backend
```

**Common causes:**
- Missing environment variables
- Database not ready
- Port conflicts
- Insufficient memory

---

## 3. Database Issues

### 3.1 Connection Refused

**Error:**
```
Connection refused - Is the server running on host "postgres" and accepting TCP/IP connections?
```

**Solution:**
```bash
# 1. Check if postgres container is running
docker-compose ps postgres

# 2. Check postgres logs
docker-compose logs postgres

# 3. Wait for postgres to be ready
sleep 30

# 4. Verify connection
docker-compose exec postgres pg_isready -U postgres

# 5. Check environment variables
cat .env | grep DATABASE_URL
```

### 3.2 Migration Failures

**Error:**
```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solution:**
```bash
# Check current revision
alembic current

# View history
alembic history --verbose

# Fix migration head conflict
alembic merge heads -m "merge heads"

# Reset database (WARNING: DATA LOSS)
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head

# Or stamp to specific revision
alembic stamp <revision_id>
alembic upgrade head
```

### 3.3 Migration Locked

**Error:**
```
psycopg2.errors.LockNotAvailable: canceling statement due to lock timeout
```

**Solution:**
```bash
# Connect to database
docker-compose exec postgres psql -U postgres -d sanskritisetu

# Check for locks
SELECT * FROM pg_locks WHERE NOT granted;

# Kill blocking process
SELECT pg_terminate_backend(<pid>);
```

### 3.4 Slow Queries

**Diagnose:**
```sql
-- Find slow queries
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Solutions:**
```sql
-- Add index
CREATE INDEX CONCURRENTLY idx_name ON table_name(column_name);

-- Analyze table
ANALYZE table_name;

-- Vacuum
VACUUM ANALYZE table_name;
```

### 3.5 Database Corruption

**Error:**
```
ERROR: could not read block 0 in file "...": read only 0 of 8192 bytes
```

**Solution:**
```bash
# Restore from backup
docker-compose exec -T postgres psql -U postgres -d sanskritisetu < backup.sql

# If no backup, try pg_resetwal (last resort!)
docker-compose stop postgres
docker-compose run --rm postgres pg_resetwal /var/lib/postgresql/data
docker-compose start postgres
```

---

## 4. API Issues

### 4.1 500 Internal Server Error

**Check logs:**
```bash
docker-compose logs backend | grep ERROR
```

**Common causes:**
- Missing environment variables
- Database connection issues
- Import errors
- Invalid configuration

**Debug mode:**
```bash
# Enable debug logging
export DEBUG=true
docker-compose restart backend
```

### 4.2 401 Unauthorized

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "AUTH_INVALID_TOKEN",
    "message": "Invalid authentication token"
  }
}
```

**Solution:**
```bash
# Check token expiration
curl -H "Authorization: Bearer <token>" http://localhost:8110/auth/verify

# Generate new token
curl -X POST http://localhost:8110/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "password"}'
```

### 4.3 403 Forbidden

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "TENANT_ISOLATION_VIOLATION",
    "message": "Cross-tenant access denied"
  }
}
```

**Solution:**
- Verify user belongs to correct tenant
- Check tenant_id in JWT token
- Ensure proper permissions

### 4.4 404 Not Found

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "COMPANY_NOT_FOUND",
    "message": "Company not found"
  }
}
```

**Solution:**
```bash
# Verify company exists
curl -H "Authorization: Bearer <token>" \
  http://localhost:8110/api/v1/companies

# Check company_id in token
curl -H "Authorization: Bearer <token>" \
  http://localhost:8110/auth/me
```

### 4.5 Rate Limiting

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests"
  }
}
```

**Solution:**
```bash
# Check rate limit headers
curl -i -H "Authorization: Bearer <token>" \
  http://localhost:8110/api/v1/companies/1

# Response headers:
# X-RateLimit-Limit: 1000
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1647085200

# Wait for reset or increase limits in config
```

---

## 5. Frontend Issues

### 5.1 Build Failures

**Error:**
```
Module not found: Error: Can't resolve '@/components/ui/Button'
```

**Solution:**
```bash
cd frontend

# Clean install
rm -rf node_modules package-lock.json
npm install

# Check TypeScript
npm run type-check

# Build
npm run build
```

### 5.2 API Connection Errors

**Error in browser console:**
```
Failed to fetch: NetworkError when attempting to fetch resource
```

**Solution:**
```bash
# 1. Check if backend is running
curl http://localhost:8110/health

# 2. Check CORS configuration
grep -r "CORS" src/core/

# 3. Verify VITE_API_URL
cat frontend/.env.local | grep VITE_API_URL

# 4. Check for network issues
ping localhost
```

### 5.3 White Screen

**Cause:** JavaScript error preventing render

**Solution:**
```bash
# 1. Check browser console for errors
# Open DevTools (F12) → Console

# 2. Check for missing env variables
cat frontend/.env.local

# 3. Clear cache and reload
# Ctrl+Shift+R (hard reload)

# 4. Rebuild
npm run build
```

### 5.4 Slow Performance

**Diagnose:**
```bash
# Check bundle size
npm run build
ls -la frontend/dist/assets/

# Analyze bundle
npm run analyze
```

**Solutions:**
```javascript
// Lazy load components
const HeavyComponent = React.lazy(() => import('./HeavyComponent'));

// Memoize expensive calculations
const memoizedValue = useMemo(() => computeExpensiveValue(a, b), [a, b]);

// Virtualize long lists
import { VirtualList } from 'react-virtualized';
```

---

## 6. External Agent Issues

### 6.1 Agent Offline

**Status:** Offline
**Last Heartbeat:** 2 hours ago

**Diagnose:**
```bash
# Check agent logs
docker logs external-agent-container

# Verify API key
curl -X POST http://localhost:8110/api/v1/agents/{agent_id}/heartbeat \
  -H "X-API-Key: {api_key}" \
  -d '{"status": "idle"}'

# Response should be 200
```

**Solutions:**
```bash
# 1. Restart agent
docker restart external-agent

# 2. Re-register agent (if API key invalid)
curl -X POST http://localhost:8110/api/v1/company/1/external-agents \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "New Agent", "runtime": "python"}'

# 3. Check network connectivity
docker exec external-agent ping api.sanskritisetu.org
```

### 6.2 Invalid API Key

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "AGENT_INVALID_API_KEY",
    "message": "Invalid API key provided"
  }
}
```

**Solution:**
- API keys are shown only once during registration
- You must re-register the agent to get a new key
- Store keys securely (environment variables, not code)

### 6.3 Missing Heartbeats

**Diagnose:**
```bash
# Check heartbeat frequency
# Expected: every 30 seconds

# View agent details
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/company/1/external-agents/{agent_id}

# Check missed_heartbeats count
```

**Solution:**
```python
# Ensure heartbeat loop runs
import time
import requests

while True:
    try:
        requests.post(
            f"{BASE_URL}/agents/{AGENT_ID}/heartbeat",
            headers={"X-API-Key": API_KEY},
            json={"status": "idle"},
            timeout=10
        )
    except Exception as e:
        print(f"Heartbeat failed: {e}")

    time.sleep(30)  # Send every 30 seconds
```

### 6.4 Webhook Not Receiving

**Diagnose:**
```bash
# Test webhook endpoint
curl -X POST https://your-agent.example.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": true}'

# Check webhook URL in agent config
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/company/1/external-agents/{agent_id} | jq '.webhook_url'
```

**Solution:**
```bash
# 1. Ensure webhook URL is accessible from internet
# 2. Check firewall rules
# 3. Verify SSL certificate is valid
# 4. Check webhook logs on agent side
```

---

## 7. Board Governance Issues

### 7.1 Decision Not Visible

**Problem:** Decision doesn't appear in approval queue

**Diagnose:**
```bash
# Check decision exists
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/board/decisions/{decision_id}

# Check user's board role
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/auth/me | jq '.board_role'

# Verify required_role matches
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/board/decisions/{decision_id} | jq '.required_role'
```

**Solution:**
- Decisions are only visible to users with the required board role
- Check if user has been assigned the correct role
- Verify tenant isolation (decisions are per-company)

### 7.2 Cannot Approve/Reject

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "BOARD_INVALID_ROLE",
    "message": "User does not have required board role"
  }
}
```

**Solution:**
```bash
# 1. Verify user's role
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/auth/me

# 2. Check decision routing
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/board/decisions/{decision_id} | jq '.required_role'

# 3. Decision may be already decided
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/board/decisions/{decision_id} | jq '.decision'
```

### 7.3 Escalation Not Working

**Problem:** Decisions not escalating after timeout

**Diagnose:**
```bash
# Check decision age
curl -H "Authorization: Bearer {token}" \
  http://localhost:8110/api/v1/board/decisions/{decision_id} | jq '.created_at'

# Check if escalation job is running
docker-compose logs worker | grep escalate
```

**Solution:**
```bash
# Ensure worker is running
docker-compose ps worker
docker-compose up -d worker

# Check dramatiq queues
docker-compose exec redis redis-cli LRANGE dramatiq:default 0 -1
```

---

## 8. Performance Issues

### 8.1 Slow API Responses

**Diagnose:**
```bash
# Check response times
curl -w "@curl-format.txt" -o /dev/null -s \
  http://localhost:8110/api/v1/companies/1/dashboard

# curl-format.txt:
# time_namelookup:  %{time_namelookup}\n
# time_connect:  %{time_connect}\n
# time_appconnect:  %{time_appconnect}\n
# time_pretransfer:  %{time_pretransfer}\n
# time_redirect:  %{time_redirect}\n
# time_starttransfer:  %{time_starttransfer}\n
# time_total:  %{time_total}\n
# Check database performance
docker-compose exec postgres psql -U postgres -c "
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
"
```

**Solutions:**
```bash
# 1. Scale backend
docker-compose up -d --scale backend=3

# 2. Enable caching
# Check Redis is configured

# 3. Add database indexes
# See Database Issues section

# 4. Optimize queries
# Enable SQLAlchemy query logging
```

### 8.2 High Memory Usage

**Diagnose:**
```bash
# Check memory usage
docker stats --no-stream
free -h

# Check for memory leaks
docker-compose logs backend | grep -i memory
```

**Solutions:**
```bash
# 1. Restart services
docker-compose restart backend

# 2. Limit container memory
docker-compose up -d --memory=1g backend

# 3. Adjust Python garbage collection
export PYTHONMALLOC=malloc
export MALLOC_ARENA_MAX=2
```

### 8.3 High CPU Usage

**Diagnose:**
```bash
# Check CPU usage
top -p $(pgrep -d',' -f python)
docker stats --no-stream
```

**Solutions:**
```bash
# 1. Scale horizontally
docker-compose up -d --scale backend=3

# 2. Check for runaway processes
docker-compose logs backend | grep -i "timeout\|error"

# 3. Optimize expensive operations
# Enable profiling
```

---

## 9. Security Issues

### 9.1 CORS Errors

**Browser Error:**
```
Access to fetch at 'http://localhost:8110/api/v1/...' from origin 'http://localhost:5174'
has been blocked by CORS policy
```

**Solution:**
```python
# backend/src/core/middleware/cors.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 9.2 SSL Certificate Errors

**Error:**
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Solution:**
```bash
# Update CA certificates
sudo update-ca-certificates

# Or disable verification (development only!)
curl -k https://localhost:8110/health
```

### 9.3 Failed Security Scans

**Bandit Report:**
```
Issue: Use of hardcoded password
Severity: Medium
```

**Solution:**
```bash
# Run security scan
bandit -r src/

# Fix issues
# - Move secrets to environment variables
# - Use secrets management
# - Update dependencies
pip-audit
npm audit fix
```

---

## 10. Getting Help

### 10.1 Information to Provide

When reporting issues, include:

1. **Error Message:** Full error text or screenshot
2. **Logs:** Relevant log excerpts (50 lines)
3. **Environment:**
   ```bash
   docker --version
   docker-compose --version
   git log --oneline -5
   ```
4. **Configuration:** Sanitized `.env` (remove secrets)
5. **Steps to Reproduce:** Clear, step-by-step instructions

### 10.2 Debug Mode

Enable debug logging:

```bash
# Backend
export LOG_LEVEL=DEBUG
docker-compose restart backend

# Frontend
# Open DevTools (F12) → Network → Preserve log
```

### 10.3 Emergency Contacts

| Issue Type | Contact |
|------------|---------|
| Production Outage | ops-oncall@sanskritisetu.org |
| Security Incident | security@sanskritisetu.org |
| General Support | support@sanskritisetu.org |
| GitHub Issues | https://github.com/your-org/sanskritisetu/issues |

---

## Quick Fix Commands

```bash
# Full reset (development only!)
docker-compose down -v
docker-compose up -d --build

# Restart everything
docker-compose restart

# Clean Docker
docker system prune -af
docker volume prune -f

# Rebuild single service
docker-compose up -d --build backend

# Database reset
alembic downgrade base
alembic upgrade head

# Clear Redis
docker-compose exec redis redis-cli FLUSHALL
```

---

**Document ID:** TROUBLESHOOTING-V3
**Last Updated:** 12 March 2026
