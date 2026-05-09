# InTEAM AI Service - Deployment Guide

Complete guide for deploying the InTEAM AI Service to production using automated CI/CD.

## Table of Contents

1. [Deployment Architecture](#deployment-architecture)
2. [Prerequisites](#prerequisites)
3. [Initial Server Setup](#initial-server-setup)
4. [GitHub Secrets Configuration](#github-secrets-configuration)
5. [Deployment Flow](#deployment-flow)
6. [Troubleshooting](#troubleshooting)
8. [Data Persistence](#data-persistence)  
9. [Post-Deployment Verification](#post-deployment-verification)  
10. [Testing Architecture](#testing-architecture)  
11. [Monitoring & Maintenance](#monitoring--maintenance)  
12. [Security Best Practices](#security-best-practices)  
13. [Support & Resources](#support--resources)

---
## Architecture Overview

### Current Production Architecture (After Django Deployment)

```
┌─────────────────────────────────────────────────────┐
│  Internet (Port 80/443)                              │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │   Apache (80/443)      │
        │   server1.inteamhealth │
        └─────────┬──────────────┘
                  │
                  ▼
        ┌──────────────┐
        │ Laravel EMR  │──────HTTP API──────┐
        │ /srv/apps/   │                    │
        │ laravel-app1 │                    │
        └──────┬───────┘                    │
               │                            ▼
               ▼                   ┌──────────────────┐
        ┌─────────────┐            │ Django AI Service│
        │ MySQL       │            │ Port: 8001       │
        │ Remote DB   │            │ (Docker)         │
        │ 101.2.165.  │            └────────┬─────────┘
        │ 171:3306    │                     │
        └─────────────┘            ┌────────┴────────┐
                                   ▼                 ▼
                          ┌─────────────────┐ ┌─────────┐
                          │ PostgreSQL 16   │ │ Redis 7 │
                          │ + pgvector      │ │ Cache   │
                          │ Port: 5433      │ │ 6379    │
                          │ (Docker)        │ │ (Docker)│
                          └─────────────────┘ └─────────┘
```

### Docker Container Structure

```
┌─────────────────────────────────────────────────────────┐
│  Docker Host (Server: 159.198.76.203)                   │
│                                                         |
│  ┌────────────────────────────────────────────────┐     │
│  │  django_ai_network (172.28.0.0/16)             │     │
│  │                                                │     │
│  │  ┌─────────────────────────────────────────┐   │     │
│  │  │  django-ai-service                      │   │     │
│  │  │  - Python 3.11                          │   │     │
│  │  │  - Django 5.1 + Gunicorn                │   │     │
│  │  │  - Port: 8001                           │   │     │
│  │  │  - Workers: 3 x 2 threads               │   │     │
│  │  │  - Non-root user (UID 1000)             │   │     │
│  │  └──────────┬────────────────┬─────────────┘   │     │
│  │             │                │                 │     │
│  │             ▼                ▼                 │     │
│  │  ┌──────────────────┐  ┌─────────────────┐     │     │
│  │  │django-ai-postgres│  │django-ai-redis  │     │     │
│  │  │  - PostgreSQL 16 │  │  - Redis 7      │     │     │
│  │  │  - pgvector ext  │  │  - 256MB cache  │     │     │
│  │  │  - Port: 5432    │  │  - Port: 6379   │     │     │
│  │  └──────────────────┘  └─────────────────┘     │     │
│  │                                                │     │
│  └────────────────────────────────────────────────┘     │
│                                                         │
│  Port Mappings (localhost only):                        │
│  - 127.0.0.1:8001 → django:8001                         │
│  - 127.0.0.1:5433 → postgres:5432                       │
│  - 127.0.0.1:6379 → redis:6379                          │
│                                                         │
│  Volumes (Persistent Data):                             │
│  - postgres_data (Database)                             │
│  - redis_data (Cache)                                   │
│  - ./staticfiles (Django static files)                  │
│  - ./media (Uploads)                                    │
│  - ./logs (Application logs)                            │
│                                                         │
└─────────────────────────────────────────────────────────┘

Host Services (Native):
┌─────────────────────────────────────────────────────────┐
│  - Apache (Port 80/443) → Laravel EMR                   │
│  - MySQL (Remote 101.2.165.171:3306) → Laravel DB       │
└─────────────────────────────────────────────────────────┘
```

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS CI/CD                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. TEST PHASE (ubuntu-latest runner)                           │
│     ├─ Install Python 3.11                                      │
│     ├─ Install dependencies                                     │
│     ├─ Run migrations (SQLite)                                  │
│     ├─ Populate test guidelines                                 │
│     ├─ Start Django server                                      │
│     └─ Run integration tests                                    │
│                                                                 │
│  2. BUILD & PUSH PHASE (ubuntu-latest runner)                   │
│     ├─ Login to GitHub Container Registry (GHCR)                │
│     ├─ Build Docker image from Dockerfile.production            │
│     ├─ Tag: latest, full SHA, short SHA                         │
│     └─ Push to ghcr.io/md-ryhan-uddin/inteam-ai-service         │
│                                                                 │
│  3. DEPLOY PHASE (SSH to production server)                     │
│     ├─ Pull exact SHA image from GHCR                           │
│     ├─ Stop & remove old containers                             │
│     ├─ Start databases (Postgres + Redis) via compose           │
│     └─ Start Django directly with GHCR image (no build!)        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   PRODUCTION SERVER                             │
│                   /srv/apps/django-app1/                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐  ┌───────────────────┐  ┌──────────────┐  │
│  │ inteam-ai-django │  │ inteam-ai-postgres│  │ inteam-ai-   │  │
│  │                  │  │                   │  │ redis        │  │
│  │ Port: 8001       │  │ Port: 5433        │  │ Port: 6379   │  │
│  │ Image: GHCR SHA  │  │ pgvector/pg16     │  │ redis:7      │  │
│  └──────────────────┘  └───────────────────┘  └──────────────┘  │
│          │                      │                      │        │
│          └──────────────────────┴──────────────────────┘        │
│                              │                                  │
│                   django-app1_django_ai_network                 │
│                                                                 │
│  Docker Volumes (Data Persistence):                             │
│  ├─ postgres_data (Database)                                    │
│  └─ redis_data (Cache)                                          │
│                                                                 │
│  Bind Mounts:                                                   │
│  ├─ ./staticfiles  → Static files                               │
│  ├─ ./media        → Uploaded files                             │
│  ├─ ./logs         → Application logs                           │
│  └─ .env.production → Environment config                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
### Port Configuration

```
Service              Port     Binding        Access
════════════════════════════════════════════════════════
Apache/Laravel       80,443   0.0.0.0        Internet ✓
Django AI            8001     127.0.0.1      Localhost only
PostgreSQL           5433     127.0.0.1      Localhost only
Redis (Django)       6379     127.0.0.1      Localhost only
MySQL (Remote)       3306     External       Laravel only
```

**No port conflicts**: Django services are isolated on localhost-only ports.


### Data Flow: Patient AI Analysis

```
1. User → Browser
   │
   ▼
2. http://inteamhealth.com
   │
   ▼
3. Apache:80/443
   │
   ▼
4. Laravel EMR Application
   │
   ├─→ Store patient data → MySQL (Remote)
   │
   └─→ HTTP POST → Django AI Service
       │
       └─→ http://127.0.0.1:8001/api/v1/clin-gpt/analyze/
           │
           ├─→ Check Redis cache (6379)
           │   └─→ Cache miss?
           │
           ├─→ Apply PHI Guardrails (input)
           │
           ├─→ Send to OpenAI GPT-4 API
           │   └─→ Get clinical AI analysis
           │
           ├─→ Apply PHI Guardrails (output)
           │
           ├─→ Store analysis → PostgreSQL (5433)
           │
           ├─→ Cache result → Redis
           │
           └─→ Return JSON response to Laravel
               │
               ▼
           Laravel displays to user
```
---

## Prerequisites

### Server Requirements

- **OS**: Linux (Rocky Linux 9.6 / CentOS / Ubuntu)
- **RAM**: Minimum 2GB, recommended 4GB+
- **Storage**: Minimum 10GB free
- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+

### GitHub Requirements

- GitHub repository with Actions enabled
- GitHub Container Registry (GHCR) access
- Personal Access Token (PAT) with `write:packages` permission

---

## Initial Server Setup

### 1. Install Docker & Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installations
docker --version
docker-compose --version
```

### 2. Create Project Directory

```bash
sudo mkdir -p /srv/apps/django-app1
sudo chown $USER:$USER /srv/apps/django-app1
cd /srv/apps/django-app1
```

### 3. Clone Repository

```bash
git clone https://github.com/md-ryhan-uddin/inteam-ai-service.git .
```

### 4. Create Production Environment File

Create `.env.production` with all required variables:

```bash
# Django Configuration
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=your-domain.com,your-ip-address

# OpenAI Configuration
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_TIMEOUT=60

# Database Configuration
POSTGRES_DB=inteam_ai
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_secure_password

DB_ENGINE=django.db.backends.postgresql
DB_NAME=inteam_ai
DB_USER=your_db_user
DB_PASSWORD=your_secure_password
DB_HOST=postgres
DB_PORT=5432

# Redis Configuration
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Laravel Integration (if applicable)
LARAVEL_API_URL=http://host.docker.internal:8000
LARAVEL_API_KEY=your-laravel-api-key

# Guardrails Configuration
GUARDRAILS_ENABLED=True
GUARDRAILS_LOG_PHI_DETECTIONS=True
SPACY_MODEL=en_core_web_sm

# RAG Configuration
RAG_ENABLED=True
RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_EMBEDDING_DIMENSION=384
RAG_TOP_K_RESULTS=5

# Production Settings
CSRF_TRUSTED_ORIGINS=https://your-domain.com
IMAGE_TAG=latest
```

### 5. Create Required Directories

```bash
mkdir -p staticfiles media logs
sudo chown -R 1000:1000 staticfiles media logs
```

---

## GitHub Secrets Configuration

Add the following secrets to your GitHub repository (`Settings` → `Secrets and variables` → `Actions`):

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `SERVER_HOST` | Production server IP/domain | `159.198.76.203` |
| `SERVER_USERNAME` | SSH username | `root` or `your_user` |
| `SERVER_SSH_KEY` | Private SSH key | Content of `~/.ssh/id_rsa` |
| `SERVER_PORT` | SSH port (optional) | `22` (default) |
| `PROJECT_PATH` | Deployment directory | `/srv/apps/django-app1` |
| `GHCR_PAT` | GitHub Personal Access Token | `ghp_xxxxx...` |
| `OPENAI_API_KEY` | OpenAI API key (for CI tests) | `sk-proj-xxxxx...` |

### Generating SSH Key for GitHub Actions

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions_key

# Copy public key to server
ssh-copy-id -i ~/.ssh/github_actions_key.pub user@your-server

# Add private key content to GitHub Secret SERVER_SSH_KEY
cat ~/.ssh/github_actions_key
```

---

## Deployment Flow

### Automated Deployment (Push to main)

```
1. Developer pushes to `main` branch
2. GitHub Actions triggers CI/CD pipeline
3. Tests run automatically
4. Docker image builds and pushes to GHCR
5. SSH to server and deploy new image
6. Health check verifies deployment
7. Deployment complete!
```

### Manual Deployment Steps

```bash
# SSH to server
ssh user@your-server
cd /srv/apps/django-app1

# Pull latest code
git pull origin main

# Pull latest Docker image
docker login ghcr.io -u md-ryhan-uddin
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:latest

# Stop old containers
docker stop inteam-ai-django inteam-ai-postgres inteam-ai-redis
docker rm -f inteam-ai-django inteam-ai-postgres inteam-ai-redis

# Start databases
docker compose -f docker-compose.production.yml up -d postgres redis

# Wait for databases
sleep 15

# Start Django with GHCR image
docker run -d \
  --name inteam-ai-django \
  --restart unless-stopped \
  --env-file .env.production \
  -e PYTHONUNBUFFERED=1 \
  -e DJANGO_SETTINGS_MODULE=config.settings \
  -v "$(pwd)/staticfiles:/app/staticfiles:Z" \
  -v "$(pwd)/media:/app/media:Z" \
  -v "$(pwd)/logs:/app/logs:Z" \
  -p 127.0.0.1:8001:8001 \
  --network django-app1_django_ai_network \
  --add-host host.docker.internal:host-gateway \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:latest \
  sh -c "python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear && gunicorn config.wsgi:application --bind 0.0.0.0:8001 --workers 3 --worker-class gthread --threads 2 --timeout 120 --access-logfile - --error-logfile - --log-level info"

# Verify deployment
curl http://localhost:8001/health/
docker ps --filter "name=inteam-ai-"
```

---

## Troubleshooting

### Container Name Conflicts

**Error**: `container name already in use`

**Solution**:
```bash
docker rm -f inteam-ai-django
docker compose -f docker-compose.production.yml up -d
```

### Database Connection Issues

**Error**: `FATAL: password authentication failed`

**Solution**:
```bash
# Check .env.production has correct credentials
cat .env.production | grep POSTGRES

# Restart database container
docker restart inteam-ai-postgres

# Check logs
docker logs inteam-ai-postgres
```

### Image Build vs. Pull Issues

**Error**: Docker is building locally instead of using GHCR image

**Solution**:
- Ensure using `docker run` with explicit GHCR image (not compose)
- Remove any `build:` directives from docker-compose files
- Use `--no-build` flag if using compose

### Health Check Failures

**Error**: Health check fails after deployment

**Solution**:
```bash
# Check Django logs
docker logs --tail 100 inteam-ai-django

# Check if migrations ran
docker exec inteam-ai-django python manage.py showmigrations

# Run migrations manually
docker exec inteam-ai-django python manage.py migrate

# Check database connection
docker exec inteam-ai-django python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Connected!')"
```

---

## Rollback Procedures

### Rollback to Previous Deployment

```bash
# Find previous SHA
git log --oneline -n 5

# Pull specific SHA image
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:<SHA>

# Stop current Django
docker stop inteam-ai-django
docker rm -f inteam-ai-django

# Start with previous image
docker run -d \
  --name inteam-ai-django \
  ... (same flags as above) \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:<PREVIOUS_SHA> \
  ...
```

### Database Rollback

**⚠️ CAUTION**: Database migrations are one-way. Plan carefully!

```bash
# Backup database first
docker exec inteam-ai-postgres pg_dump -U ryhan inteam_ai > backup_$(date +%Y%m%d_%H%M%S).sql

# Rollback specific migration
docker exec inteam-ai-django python manage.py migrate app_name migration_name

# Restore from backup (if needed)
docker exec -i inteam-ai-postgres psql -U ryhan inteam_ai < backup_file.sql
```

---

## Data Persistence

### What Data is Preserved?

✅ **PostgreSQL Database** (`postgres_data` volume)
- All database records
- Clinical guidelines
- PHI detection logs
- Django sessions

✅ **Redis Cache** (`redis_data` volume)
- Cached data
- AOF persistence file

✅ **Static Files** (`./staticfiles` bind mount)
- Collected static assets

✅ **Media Files** (`./media` bind mount)
- Uploaded files

✅ **Logs** (`./logs` bind mount)
- Application logs

### What Data is NOT Preserved?

❌ **Container filesystem** - Recreated on each deployment
❌ **Temporary files** - Cleared on restart
❌ **In-memory data** - Lost on container restart

---

## Post-Deployment Verification

```bash
# 1. Check all containers are running
docker ps --filter "name=inteam-ai-"

# 2. Verify health endpoint
curl http://localhost:8001/health/

# 3. Check database connection
docker exec inteam-ai-django python -c "from django.db import connection; connection.ensure_connection(); print('DB OK')"

# 4. Verify clinical guidelines
docker exec inteam-ai-django python -c "from apps.clin_gpt.models import ClinicalGuideline; print(f'Guidelines: {ClinicalGuideline.objects.count()}')"

# 5. Test API endpoint
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_LARAVEL_TOKEN" \
  -d '{"message": "Patient with chest pain", "context": {}}'

# 6. Check logs for errors
docker logs --tail 50 inteam-ai-django
```

---


## Testing Architecture

### Overview

The InTEAM AI Service includes a comprehensive, cost-optimized testing architecture with three testing layers:

```
┌────────────────────────────────────────────────────────────┐
│             TESTING ARCHITECTURE (3 LAYERS)                 │
└────────────────────────────────────────────────────────────┘

                    run_tests.sh (HOST)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────┐
│ LAYER 1:     │  │ LAYER 2:         │  │ LAYER 3:    │
│ Infra Tests  │  │ App Tests        │  │ Integration │
│ (HOST)       │  │ (CONTAINER)      │  │ (HOST→API)  │
│              │  │                  │  │             │
│ Cost: $0.00  │  │ Cost: $0.00      │  │ Cost: $0.01 │
│ Tests: 6     │  │ Tests: 6         │  │ Tests: 3    │
└──────────────┘  └──────────────────┘  └─────────────┘
       │                   │                    │
       ▼                   ▼                    ▼
  Docker health      Django models        API endpoint
  Health endpoint    Spacy NLP            PHI detection
  PostgreSQL         Transformers         RAG system
  Redis              PHI detection        Risk assessment
  Network            RAG retrieval
  Volumes            pgvector
```

### Test Scripts Available

| Script | Tests | OpenAI Calls | Cost | Use Case |
|--------|-------|--------------|------|----------|
| `./run_tests.sh minimal` | 8 | 0 | $0.00 | Daily health checks |
| `./run_tests.sh all` | 15 | 1 | $0.01 | Every deployment ⭐ |
| `python test_full_system.py` | 26 | 13 | $0.13 | Before major releases |

### Quick Testing Commands

```bash
# Navigate to project
cd /srv/apps/django-app1

# Quick health check (free)
./run_tests.sh minimal

# Full test suite (recommended for deployments)
./run_tests.sh all

# Individual layers
./run_tests.sh layer1    # Infrastructure only
./run_tests.sh layer2    # Application only
./run_tests.sh layer3    # Integration with OpenAI

# Help
./run_tests.sh help
```

### Layer 1: Infrastructure Tests ($0.00)

**Run from HOST, no OpenAI costs**

Tests:
- Docker containers running (django, postgres, redis)
- Health endpoint responding (HTTP 200)
- PostgreSQL accepting connections
- Redis responding to ping

### Layer 2: Application Tests ($0.00)

**Run inside CONTAINER via docker exec, no OpenAI costs**

Tests:
- Django models working
- Spacy NLP model loaded (en_core_web_lg/sm)
- Sentence Transformers working (384-dim)
- PHI detection system functional
- RAG system enabled and working
- pgvector extension enabled

### Layer 3: Integration Tests (~$0.01)

**Run from HOST → API, 1 OpenAI call**

Tests:
- End-to-end API call with OpenAI
- Response structure validation
- Risk level assessment
- Guardrails functionality
- RAG data present

### Python Test Modules (Alternative)

Individual Python test scripts are also available in `test_scripts_python/`:

```bash
# Run infrastructure tests
python test_scripts_python/test_infrastructure.py

# Run application tests (inside container)
docker exec inteam-ai-django python /app/test_scripts_python/test_application.py

# Run integration tests
python test_scripts_python/test_integration.py
```

### Cost Comparison

**Monthly Testing Costs:**

| Scenario | Script | Frequency | Cost/Run | Monthly Cost |
|----------|--------|-----------|----------|--------------|
| Daily Health Checks | `minimal` | 30/month | $0.00 | $0.00 |
| Regular Deployments | `run_tests.sh all` | 50/month | $0.01 | $0.50 |
| Weekly Comprehensive | `test_full_system.py` | 4/month | $0.13 | $0.52 |
| **Total Monthly Cost** | - | - | - | **$1.02** |

**Before Optimization:** $6.50/month (13 OpenAI calls per deployment)
**After Optimization:** $1.02/month (1 OpenAI call per deployment)
**Savings:** $5.48/month (84% reduction)

### Testing Best Practices

1. **Daily Development:**
   ```bash
   ./run_tests.sh minimal  # Free, quick validation
   ```

2. **Before Each Deployment:**
   ```bash
   ./run_tests.sh all  # $0.01, comprehensive
   ```

3. **Before Major Release:**
   ```bash
   python test_full_system.py  # $0.13, exhaustive
   ```

### Integration with deploy.sh

The `deploy.sh` script automatically prompts to run tests:

```bash
./deploy.sh
# ... deployment steps ...
# Prompt: "Do you want to run tests? (y/n)"
# Press 'y' to run: ./run_tests.sh all
```

### Troubleshooting Tests

**Issue: Docker containers not running**
```bash
docker-compose ps
./deploy.sh  # Restart services
```

**Issue: Permission denied**
```bash
chmod +x run_tests.sh
chmod +x test_scripts/*.sh
```

**Issue: Python script not found**
```bash
cd /srv/apps/django-app1  # Ensure correct directory
ls -la test_*.py          # Verify files exist
```

---

## Monitoring & Maintenance

### View Logs

```bash
# Real-time logs
docker logs -f inteam-ai-django

# Last 100 lines
docker logs --tail 100 inteam-ai-django

# Logs with timestamps
docker logs --timestamps inteam-ai-django

# Logs for specific timeframe
docker logs --since 1h inteam-ai-django
```

### Resource Usage

```bash
# Container stats
docker stats inteam-ai-django inteam-ai-postgres inteam-ai-redis

# Disk usage
docker system df

# Volume sizes
docker volume ls
docker volume inspect django-app1_postgres_data
```

### Database Maintenance

```bash
# Vacuum database
docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "VACUUM ANALYZE;"

# Check database size
docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "SELECT pg_size_pretty(pg_database_size('inteam_ai'));"

# Backup database
docker exec inteam-ai-postgres pg_dump -U ryhan inteam_ai > backup_$(date +%Y%m%d).sql
```

---

## Security Best Practices

1. **Never commit `.env.production` to Git**
2. **Use strong, unique passwords for database**
3. **Regularly update Docker images**: `docker pull` latest base images
4. **Monitor logs for security issues**
5. **Use HTTPS in production** (configure reverse proxy)
6. **Limit SSH access** to authorized IPs only
7. **Regularly backup database and volumes**
8. **Keep Docker and Docker Compose updated**

---

## Support & Resources

- **GitHub Repository**: https://github.com/md-ryhan-uddin/inteam-ai-service
- **GitHub Container Registry**: https://ghcr.io/md-ryhan-uddin/inteam-ai-service
- **CI/CD Pipeline**: `.github/workflows/deploy.yml`
- **Docker Configuration**: `docker-compose.production.yml`
- **Production Dockerfile**: `Dockerfile.production`

---

**Last Updated**: 2025-11-13
**Version**: 2.0 (CI/CD with GHCR)
