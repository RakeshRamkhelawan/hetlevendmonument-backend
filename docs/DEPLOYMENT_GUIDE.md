# SanskritiSetu Deployment Guide

> **Versie:** 3.0
> **Laatst bijgewerkt:** Maart 2026
> **Doelgroep:** DevOps Engineers, System Administrators

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Environment Setup](#3-environment-setup)
4. [Docker Deployment](#4-docker-deployment)
5. [Kubernetes Deployment](#5-kubernetes-deployment)
6. [Database Setup](#6-database-setup)
7. [SSL/TLS Configuration](#7-ssltls-configuration)
8. [Monitoring Setup](#8-monitoring-setup)
9. [Backup & Recovery](#9-backup--recovery)
10. [Security Hardening](#10-security-hardening)

---

## 1. Overview

### 1.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        LOAD BALANCER                         │
│                      (Traefik / Nginx)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
│   FRONTEND   │ │  BACKEND  │ │  BACKEND    │
│  (React/Vite)│ │  (API)    │ │  (API)      │
└──────────────┘ └─────┬─────┘ └─────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐
│  PostgreSQL  │ │   Redis   │ │  RabbitMQ   │
└──────────────┘ └───────────┘ └─────────────┘
```

### 1.2 Component Versions

| Component | Version | Purpose |
|-----------|---------|---------|
| PostgreSQL | 15+ | Primary database |
| Redis | 7+ | Caching, sessions, queues |
| RabbitMQ | 3.12+ | Message broker |
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |

---

## 2. Prerequisites

### 2.1 System Requirements

**Minimum (Development):**
- CPU: 4 cores
- RAM: 8 GB
- Storage: 50 GB SSD
- OS: Linux (Ubuntu 22.04 LTS recommended)

**Recommended (Production):**
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 200+ GB SSD
- OS: Linux (Ubuntu 22.04 LTS or RHEL 9)

### 2.2 Required Software

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Git
sudo apt-get update && sudo apt-get install -y git
```

### 2.3 Network Requirements

| Port | Service | Direction | Description |
|------|---------|-----------|-------------|
| 80 | HTTP | Inbound | Web traffic |
| 443 | HTTPS | Inbound | Secure web traffic |
| 5432 | PostgreSQL | Internal | Database |
| 6379 | Redis | Internal | Cache |
| 5672 | RabbitMQ | Internal | AMQP |
| 15672 | RabbitMQ | Internal | Management UI |
| 8110 | Backend | Internal | API |
| 5174 | Frontend | Internal | Web UI |
| 9090 | Prometheus | Internal | Metrics |
| 3000 | Grafana | Internal | Dashboards |

---

## 3. Environment Setup

### 3.1 Clone Repository

```bash
git clone https://github.com/your-org/sanskritisetu.git
cd sanskritisetu
```

### 3.2 Environment Files

Create environment-specific configuration files:

**`.env.prod`:**
```bash
# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-32-character-secret-key-here
JWT_SECRET_KEY=your-32-character-jwt-secret-key

# Database
DATABASE_URL=postgresql+asyncpg://postgres:secure_password@postgres:5432/sanskritisetu
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=sanskritisetu

# Redis
REDIS_URL=redis://redis:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# API Keys (replace with real keys)
GOOGLE_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_key

# Frontend
VITE_API_URL=https://api.yourdomain.com
VITE_WS_URL=wss://api.yourdomain.com/ws

# Email
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your_sendgrid_key

# S3/Storage
S3_BUCKET=sanskritisetu-prod
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
```

### 3.3 Secrets Management

**Option 1: Docker Secrets (Recommended)**
```bash
# Create secrets
echo "your_secure_password" | docker secret create db_password -
echo "your_jwt_secret" | docker secret create jwt_secret -
echo "your_api_key" | docker secret create google_api_key -
```

**Option 2: External Vault**
```bash
# HashiCorp Vault example
export VAULT_ADDR='https://vault.yourdomain.com'
vault login -method=userpass username=admin
vault kv get secret/sanskritisetu/prod
```

---

## 4. Docker Deployment

### 4.1 Production Deployment

```bash
# 1. Create network
docker network create sanskritisetu-prod

# 2. Start infrastructure services
docker-compose -f docker-compose.yml up -d postgres redis rabbitmq

# 3. Wait for databases to be ready
sleep 30

# 4. Run migrations
docker-compose exec backend alembic upgrade head

# 5. Start application services
docker-compose -f docker-compose.yml up -d backend frontend

# 6. Verify deployment
docker-compose ps
curl http://localhost:8110/health
```

### 4.2 Docker Compose Production

**`docker-compose.prod.yml`:**
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - sanskritisetu
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - sanskritisetu
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  backend:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - sanskritisetu
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    environment:
      - VITE_API_URL=${VITE_API_URL}
    networks:
      - sanskritisetu
    restart: unless-stopped
    deploy:
      replicas: 2

  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@yourdomain.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    networks:
      - sanskritisetu
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:

networks:
  sanskritisetu:
    driver: bridge
```

### 4.3 Rolling Updates

```bash
# Zero-downtime deployment
docker-compose up -d --no-deps --scale backend=3 --no-recreate backend
sleep 10
docker-compose up -d --no-deps --scale backend=2 --no-recreate backend
```

---

## 5. Kubernetes Deployment

### 5.1 Namespace & Secrets

```bash
# Create namespace
kubectl create namespace sanskritisetu

# Create secrets
kubectl create secret generic app-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://..." \
  --from-literal=SECRET_KEY="..." \
  --from-literal=JWT_SECRET_KEY="..." \
  -n sanskritisetu
```

### 5.2 PostgreSQL StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: sanskritisetu
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_USER
          value: "postgres"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: DB_PASSWORD
        - name: POSTGRES_DB
          value: "sanskritisetu"
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 100Gi
```

### 5.3 Backend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: sanskritisetu
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: ghcr.io/your-org/sanskritisetu-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: DATABASE_URL
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: SECRET_KEY
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### 5.4 Ingress Configuration

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sanskritisetu-ingress
  namespace: sanskritisetu
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - api.yourdomain.com
    - app.yourdomain.com
    secretName: sanskritisetu-tls
  rules:
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 8000
  - host: app.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80
```

---

## 6. Database Setup

### 6.1 Initial Migration

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Or with kubectl
kubectl exec -it deployment/backend -n sanskritisetu -- alembic upgrade head
```

### 6.2 Backup Strategy

**Automated Backups (Daily):**
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
docker exec postgres pg_dump -U postgres sanskritisetu > /backups/sanskritisetu_$DATE.sql
gzip /backups/sanskritisetu_$DATE.sql
# Keep only last 30 days
find /backups -name "*.sql.gz" -mtime +30 -delete
```

**Kubernetes CronJob:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: sanskritisetu
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15-alpine
            command:
            - /bin/sh
            - -c
            - |
              pg_dump -h postgres -U postgres sanskritisetu > /backup/sanskritisetu_$(date +%Y%m%d).sql
            env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: DB_PASSWORD
            volumeMounts:
            - name: backup-volume
              mountPath: /backup
          volumes:
          - name: backup-volume
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

### 6.3 Recovery Procedure

```bash
# Restore from backup
docker exec -i postgres psql -U postgres -d sanskritisetu < backup_file.sql

# Or for compressed backups
gunzip < backup_file.sql.gz | docker exec -i postgres psql -U postgres -d sanskritisetu
```

---

## 7. SSL/TLS Configuration

### 7.1 Let's Encrypt with Traefik

Traefik handles SSL automatically when configured with Let's Encrypt:

```yaml
# Already configured in docker-compose.prod.yml
command:
  - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
  - "--certificatesresolvers.letsencrypt.acme.email=admin@yourdomain.com"
  - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
```

### 7.2 Custom Certificates

```bash
# Place certificates in the appropriate directory
cp your-cert.crt ./ssl/cert.crt
cp your-key.key ./ssl/cert.key

# Reference in compose
volumes:
  - ./ssl:/ssl:ro
```

### 7.3 Certificate Renewal

```bash
# Test renewal
certbot renew --dry-run

# Force renewal
certbot renew --force-renewal
```

---

## 8. Monitoring Setup

### 8.1 Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'sanskritisetu-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: /metrics

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']
```

### 8.2 Grafana Dashboards

**Import dashboards:**
```bash
# Copy dashboards to provisioning folder
cp dashboards/*.json ./grafana/dashboards/

# Restart Grafana
docker-compose restart grafana
```

### 8.3 Alerting Rules

```yaml
# alert_rules.yml
groups:
- name: sanskritisetu
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"

  - alert: DatabaseDown
    expr: up{job="postgres-exporter"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Database is down"
```

---

## 9. Backup & Recovery

### 9.1 Full System Backup

```bash
#!/bin/bash
# full_backup.sh

BACKUP_DIR="/backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Database
docker exec postgres pg_dump -U postgres sanskritisetu > $BACKUP_DIR/database.sql

# Redis
docker exec redis redis-cli BGSAVE
sleep 5
docker cp redis:/data/dump.rdb $BACKUP_DIR/redis.rdb

# Configuration
cp .env.prod $BACKUP_DIR/
cp docker-compose.yml $BACKUP_DIR/

# Compress
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

# Upload to S3
aws s3 cp $BACKUP_DIR.tar.gz s3://sanskritisetu-backups/
```

### 9.2 Disaster Recovery

**Recovery Steps:**

1. **Provision new infrastructure**
2. **Restore database:**
   ```bash
   docker-compose up -d postgres
   docker exec -i postgres psql -U postgres -c "CREATE DATABASE sanskritisetu;"
   docker exec -i postgres psql -U postgres sanskritisetu < database.sql
   ```
3. **Restore configuration:**
   ```bash
   cp .env.prod .env
   ```
4. **Start services:**
   ```bash
   docker-compose up -d
   ```
5. **Verify:**
   ```bash
   curl http://localhost:8110/health
   ```

---

## 10. Security Hardening

### 10.1 Network Security

```bash
# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw enable
```

### 10.2 Container Security

**Run as non-root:**
```dockerfile
FROM python:3.11-slim
RUN useradd -m appuser
USER appuser
WORKDIR /home/appuser
COPY --chown=appuser:appuser . .
```

**Security scanning:**
```bash
# Scan images
docker scan sanskritisetu-backend:latest
trivy image sanskritisetu-backend:latest
```

### 10.3 Secrets Management

**Use Docker Secrets or external vault:**
```yaml
secrets:
  db_password:
    external: true
  jwt_secret:
    external: true

services:
  backend:
    secrets:
      - db_password
      - jwt_secret
```

---

## Quick Commands Reference

```bash
# Start all services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f --tail=100 postgres

# Scale backend
docker-compose up -d --scale backend=3

# Database shell
docker-compose exec postgres psql -U postgres -d sanskritisetu

# Redis CLI
docker-compose exec redis redis-cli

# Health check
curl http://localhost:8110/health
curl http://localhost:8110/health/deep

# Restart service
docker-compose restart backend

# Full rebuild
docker-compose down -v
docker-compose -f docker-compose.prod.yml up -d --build
```

---

**Need help?** Contact [devops@sanskritisetu.org](mailto:devops@sanskritisetu.org)

*Last updated: 12 March 2026*
