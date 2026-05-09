# InTEAM AI Service - CI/CD Guide

Complete guide for GitHub Actions CI/CD pipeline, automated testing, Docker image building, and deployment.

## Table of Contents

1. [Overview](#overview)
2. [Pipeline Architecture](#pipeline-architecture)
3. [Workflow Phases](#workflow-phases)
4. [GitHub Secrets Configuration](#github-secrets-configuration)
5. [GHCR Integration](#ghcr-integration)
6. [Deployment Strategy](#deployment-strategy)
7. [Triggers and Conditions](#triggers-and-conditions)
8. [Monitoring and Debugging](#monitoring-and-debugging)

---

## Overview

The InTEAM AI Service uses **GitHub Actions** for automated CI/CD with a 3-phase pipeline:

```
1. TEST     → Run tests with Python + Django
2. BUILD    → Build Docker image, push to GHCR
3. DEPLOY   → SSH to server, pull image, deploy
```

### Key Features

- **Automated Testing**: Runs on every push/PR
- **Immutable Deployments**: Each deployment uses a specific SHA-tagged image
- **GHCR Integration**: Uses GitHub Container Registry for image storage
- **Direct Docker Run**: Deploys with `docker run` (not compose)
- **Health Checks**: Validates deployment success
- **Zero Downtime**: Graceful shutdown with health monitoring

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GITHUB REPOSITORY                         │
│         github.com/md-ryhan-uddin/inteam-ai-service        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓  (git push origin main)
┌─────────────────────────────────────────────────────────────┐
│              GITHUB ACTIONS WORKFLOW                        │
│          .github/workflows/deploy.yml                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ PHASE 1: TEST (ubuntu-latest runner)               │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ ✓ Checkout code                                    │   │
│  │ ✓ Set up Python 3.11                               │   │
│  │ ✓ Install dependencies                             │   │
│  │ ✓ Lint with flake8 (optional)                      │   │
│  │ ✓ Download Spacy model                             │   │
│  │ ✓ Run Django migrations (SQLite)                   │   │
│  │ ✓ Populate clinical guidelines                     │   │
│  │ ✓ Start Django server (background)                 │   │
│  │ ✓ Run integration tests (test_clin_gpt.py)         │   │
│  │                                                     │   │
│  │ Cost: ~$0.01 (1 OpenAI API call)                   │   │
│  │ Time: ~2-3 minutes                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                     ↓                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ PHASE 2: BUILD & PUSH (ubuntu-latest runner)       │   │
│  │ (Only on push to main, after tests pass)           │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ ✓ Checkout code                                    │   │
│  │ ✓ Prune Docker cache (free space)                  │   │
│  │ ✓ Set up Docker Buildx                             │   │
│  │ ✓ Compute short SHA (first 7 chars)                │   │
│  │ ✓ Log in to GHCR (ghcr.io)                         │   │
│  │ ✓ Build Docker image (Dockerfile.production)       │   │
│  │ ✓ Tag with: latest, full SHA, short SHA            │   │
│  │ ✓ Push to ghcr.io/md-ryhan-uddin/inteam-ai-service│   │
│  │                                                     │   │
│  │ Cache: GitHub Actions cache (faster rebuilds)      │   │
│  │ Time: ~5-8 minutes                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                     ↓                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ PHASE 3: DEPLOY (SSH to production server)         │   │
│  │ (Only on push to main, after build succeeds)       │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ ✓ SSH to production server                         │   │
│  │ ✓ Navigate to project directory                    │   │
│  │ ✓ Log in to GHCR (if private)                      │   │
│  │ ✓ Pull exact SHA image from GHCR                   │   │
│  │ ✓ Tag as :latest locally                           │   │
│  │ ✓ Update IMAGE_TAG in .env.production              │   │
│  │ ✓ Stop old containers                              │   │
│  │ ✓ Start databases (postgres + redis)               │   │
│  │ ✓ Wait 15 seconds for DBs to be ready              │   │
│  │ ✓ Start Django with docker run (GHCR image)        │   │
│  │ ✓ Run migrations + collectstatic                   │   │
│  │ ✓ Start Gunicorn (3 workers, 2 threads)            │   │
│  │ ✓ Health check (12 retries, 5s interval)           │   │
│  │ ✓ Verify deployment success                        │   │
│  │                                                     │   │
│  │ Time: ~2-3 minutes                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              PRODUCTION SERVER                              │
│            /srv/apps/django-app1/                          │
├─────────────────────────────────────────────────────────────┤
│  Running containers:                                        │
│  - inteam-ai-django (GHCR image, specific SHA)             │
│  - inteam-ai-postgres (pgvector/pg16)                      │
│  - inteam-ai-redis (redis:7-alpine)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow Phases

### Phase 1: Test

**File**: `.github/workflows/deploy.yml` (lines 14-98)

**Purpose**: Validate code quality and functionality before deployment

**Steps**:

1. **Checkout code** (`actions/checkout@v4`)
2. **Set up Python 3.11** (`actions/setup-python@v4`)
3. **Cache dependencies** (pip packages)
4. **Install dependencies** (`pip install -r requirements.txt`)
5. **Lint with flake8** (optional, continues on error)
6. **Download Spacy model** (`scripts/install_spacy.py`)
7. **Run Django migrations** (SQLite for CI)
8. **Populate clinical guidelines** (`manage.py populate_guidelines`)
9. **Start Django server** (background, port 8001)
10. **Run integration tests** (`test_clin_gpt.py`)

**Environment**:
- OS: `ubuntu-latest`
- Python: 3.11
- Database: SQLite (temporary, in-memory)
- OpenAI: Uses `OPENAI_API_KEY` secret

**Test Coverage**:
- Linting (code quality)
- Database migrations
- Model creation
- API endpoint functionality
- OpenAI integration (1 API call)

**Cost**: ~$0.01 per run (OpenAI API call)

---

### Phase 2: Build & Push

**File**: `.github/workflows/deploy.yml` (lines 100-148)

**Purpose**: Build production Docker image and push to GHCR

**Conditions**:
- Only runs on `push` to `main` branch
- Requires Phase 1 (tests) to pass
- Skipped on pull requests

**Steps**:

1. **Checkout code**
2. **Prune Docker cache** (free space on runner)
   ```bash
   docker system prune -af
   docker builder prune -af
   docker volume prune -f
   ```
3. **Set up Docker Buildx** (multi-platform builds)
4. **Compute short SHA** (first 7 characters of commit SHA)
   ```bash
   echo "SHORT_SHA=${GITHUB_SHA::7}" >> $GITHUB_ENV
   ```
5. **Log in to GHCR**
   - Registry: `ghcr.io`
   - Username: `${{ github.repository_owner }}`
   - Password: `GHCR_PAT` or `GITHUB_TOKEN`
6. **Build and push Docker image**
   - Context: `.` (project root)
   - Dockerfile: `Dockerfile.production`
   - Tags:
     - `ghcr.io/md-ryhan-uddin/inteam-ai-service:latest`
     - `ghcr.io/md-ryhan-uddin/inteam-ai-service:<full-sha>`
     - `ghcr.io/md-ryhan-uddin/inteam-ai-service:<short-sha>`
   - Cache: GitHub Actions cache (faster rebuilds)

**Image Tags Explained**:

```
latest       → Always points to most recent build
<full-sha>   → Immutable, specific commit (e.g., abc123...xyz789)
<short-sha>  → Human-readable, specific commit (e.g., abc1234)
```

**Permissions Required**:
```yaml
permissions:
  contents: read    # Read repository
  packages: write   # Push to GHCR
```

---

### Phase 3: Deploy

**File**: `.github/workflows/deploy.yml` (lines 150-253)

**Purpose**: Deploy Docker image to production server via SSH

**Conditions**:
- Only runs on `push` to `main` branch
- Requires Phase 2 (build) to pass
- Uses concurrency control (prevents parallel deployments)

**Concurrency Control**:
```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: true
```
Ensures only one deployment runs at a time.

**SSH Deployment Steps**:

1. **Connect to server** (`appleboy/ssh-action@v1.2.0`)
   - Host: `SERVER_HOST` secret
   - User: `SERVER_USERNAME` secret
   - SSH Key: `SERVER_SSH_KEY` secret
   - Port: `SERVER_PORT` secret (default: 22)

2. **Navigate to project directory**
   ```bash
   cd ${{ secrets.PROJECT_PATH }}  # /srv/apps/django-app1
   ```

3. **Log in to GHCR** (if image is private)
   ```bash
   echo "$GHCR_PAT" | docker login ghcr.io -u "${{ github.repository_owner }}" --password-stdin
   ```

4. **Pull exact SHA image**
   ```bash
   docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:${{ github.sha }}
   ```

5. **Tag as :latest locally**
   ```bash
   docker tag ghcr.io/md-ryhan-uddin/inteam-ai-service:${{ github.sha }} \
              ghcr.io/md-ryhan-uddin/inteam-ai-service:latest
   ```

6. **Update .env.production**
   ```bash
   sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${{ github.sha }}/" .env.production
   ```

7. **Stop old containers**
   ```bash
   docker compose -f docker-compose.production.yml down
   docker stop inteam-ai-django inteam-ai-postgres inteam-ai-redis
   docker rm -f inteam-ai-django inteam-ai-postgres inteam-ai-redis
   ```

8. **Start databases only**
   ```bash
   docker compose -f docker-compose.production.yml up -d postgres redis
   sleep 15  # Wait for databases to be ready
   ```

9. **Start Django with docker run**
   ```bash
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
     ghcr.io/md-ryhan-uddin/inteam-ai-service:${{ github.sha }} \
     sh -c "python manage.py migrate --noinput && \
            python manage.py collectstatic --noinput --clear && \
            gunicorn config.wsgi:application \
              --bind 0.0.0.0:8001 \
              --workers 3 \
              --worker-class gthread \
              --threads 2 \
              --timeout 120 \
              --graceful-timeout 30 \
              --max-requests 1000 \
              --max-requests-jitter 100 \
              --access-logfile - \
              --error-logfile - \
              --log-level info"
   ```

10. **Health check** (12 retries, 5s interval, ~60s total)
    ```bash
    for i in {1..12}; do
      if curl -fsS http://localhost:8001/health/ >/dev/null; then
        echo "✅ Healthy after $i checks"
        break
      fi
      sleep 5
      if [ "$i" -eq 12 ]; then
        echo "❌ Health check failed after 60s"
        docker logs --tail 200 inteam-ai-django
        exit 1
      fi
    done
    ```

11. **Verify deployment**
    ```bash
    docker ps --filter "name=inteam-ai-"
    ```

**Why docker run instead of docker-compose?**

1. **GHCR Integration**: Uses pre-built image (no local build)
2. **Immutable Deployments**: Exact SHA-tagged image
3. **No Build on Server**: Saves time and resources
4. **CI/CD Friendly**: Separates build from deploy

---

## GitHub Secrets Configuration

### Required Secrets

Navigate to: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `SERVER_HOST` | Production server IP or domain | `159.198.76.203` |
| `SERVER_USERNAME` | SSH username | `root` or `your_user` |
| `SERVER_SSH_KEY` | Private SSH key (full content) | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `SERVER_PORT` | SSH port (optional) | `22` (default) |
| `PROJECT_PATH` | Deployment directory on server | `/srv/apps/django-app1` |
| `GHCR_PAT` | GitHub Personal Access Token | `ghp_xxxxx...` (with `write:packages`) |
| `OPENAI_API_KEY` | OpenAI API key (for tests) | `sk-proj-xxxxx...` |

### Generating SSH Key

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_key

# Copy public key to server
ssh-copy-id -i ~/.ssh/github_actions_key.pub user@your-server

# Test SSH connection
ssh -i ~/.ssh/github_actions_key user@your-server

# Copy private key content (everything, including headers)
cat ~/.ssh/github_actions_key

# Add to GitHub Secret: SERVER_SSH_KEY
```

### Generating GitHub PAT (Personal Access Token)

1. Go to: https://github.com/settings/tokens
2. Click **Generate new token** → **Generate new token (classic)**
3. Name: `GHCR Deploy Token`
4. Select scopes:
   - `write:packages` (push to GHCR)
   - `read:packages` (pull from GHCR)
   - `delete:packages` (optional, for cleanup)
5. Click **Generate token**
6. Copy token (starts with `ghp_`)
7. Add to GitHub Secret: `GHCR_PAT`

---

## GHCR Integration

### GitHub Container Registry (GHCR)

**Registry URL**: `ghcr.io`

**Image Repository**: `ghcr.io/md-ryhan-uddin/inteam-ai-service`

### Why GHCR?

1. **Free for public repos**: Unlimited storage and bandwidth
2. **Integrated with GitHub**: Uses same authentication
3. **Fast**: Close to GitHub Actions runners
4. **Versioning**: Multiple tags per image
5. **Security**: Automatic vulnerability scanning

### Image Tags

Each push to `main` creates 3 tags:

```bash
# Latest tag (always overwritten)
ghcr.io/md-ryhan-uddin/inteam-ai-service:latest

# Full SHA tag (immutable)
ghcr.io/md-ryhan-uddin/inteam-ai-service:abc123def456789...

# Short SHA tag (human-readable)
ghcr.io/md-ryhan-uddin/inteam-ai-service:abc1234
```

### Viewing Images

**Via GitHub UI**:
1. Go to repository page
2. Click **Packages** (right sidebar)
3. View all image versions

**Via Docker CLI**:
```bash
# List available tags
docker search ghcr.io/md-ryhan-uddin/inteam-ai-service

# Pull specific tag
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:abc1234

# Pull latest
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:latest
```

### Image Visibility

**Public** (default for public repos):
- Anyone can pull images
- No authentication needed

**Private** (for private repos):
- Requires GitHub authentication
- Use GHCR_PAT for CI/CD

---

## Deployment Strategy

### Direct Docker Run Strategy

**Approach**: Django runs as standalone container via `docker run`, NOT via compose.

**Why?**

1. **GHCR Image**: Uses pre-built image from registry
2. **No Build on Server**: Faster deployments
3. **Immutable**: Exact SHA-tagged image
4. **Rollback-Friendly**: Easy to switch between SHAs

**Compose vs Docker Run**:

```yaml
# Compose (NOT used for Django)
docker compose -f docker-compose.production.yml up -d django
# ❌ Would try to build locally or use generic :latest tag

# Docker Run (USED for Django)
docker run -d \
  --name inteam-ai-django \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:abc1234
# ✅ Uses exact SHA image from GHCR
```

**Databases still use compose** because:
- Official images (no build needed)
- Configuration via YAML
- Health checks and dependencies

### Zero-Downtime Strategy

1. **Graceful Shutdown**: `--graceful-timeout 30`
   - Gunicorn waits 30s for active requests to complete
2. **Health Checks**: Validates new container before considering deployment successful
3. **Quick Rollback**: If health check fails, deployment aborts

### Rollback Procedure

```bash
# SSH to server
ssh user@your-server
cd /srv/apps/django-app1

# Find previous SHA from git history
git log --oneline -n 5

# Stop current container
docker stop inteam-ai-django
docker rm -f inteam-ai-django

# Pull and deploy previous SHA
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:<previous-sha>
docker run -d \
  --name inteam-ai-django \
  ... (same flags as deployment) \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:<previous-sha> \
  ...
```

---

## Triggers and Conditions

### Workflow Triggers

```yaml
on:
  push:
    branches: [ main ]   # Runs on push to main
  pull_request:
    branches: [ main ]   # Runs on PR to main
```

### Job Conditions

**Test Phase**:
- Runs on: `push` and `pull_request`
- No conditions (always runs)

**Build Phase**:
```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```
- Only runs on direct push to `main`
- Skipped on PRs

**Deploy Phase**:
```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
needs: build-and-push
```
- Only runs on direct push to `main`
- Requires build phase to succeed
- Skipped on PRs

### Workflow Execution Matrix

| Event | Branch | Test | Build | Deploy |
|-------|--------|------|-------|--------|
| Push to `main` | main | ✅ | ✅ | ✅ |
| Push to `dev` | dev | ✅ | ❌ | ❌ |
| PR to `main` | feature-x | ✅ | ❌ | ❌ |
| Manual workflow | main | ✅ | ✅ | ✅ |

---

## Monitoring and Debugging

### Viewing Workflow Runs

**GitHub UI**:
1. Go to repository
2. Click **Actions** tab
3. Select workflow run
4. View job logs

### Debugging Failed Tests

```bash
# View test phase logs
# GitHub Actions → Workflow run → test → Run integration tests

# Common issues:
# - OpenAI API key missing/invalid
# - Spacy model download failed
# - Django migrations failed
```

### Debugging Failed Builds

```bash
# View build phase logs
# GitHub Actions → Workflow run → build-and-push → Build and push Docker image

# Common issues:
# - Dockerfile syntax error
# - Missing dependencies
# - GHCR authentication failed
```

### Debugging Failed Deployments

```bash
# View deploy phase logs
# GitHub Actions → Workflow run → deploy → Deploy to server via SSH

# Common issues:
# - SSH connection failed
# - .env.production missing
# - Health check timeout
# - Container name conflict

# SSH to server to debug
ssh user@your-server
docker logs inteam-ai-django
docker ps -a
```

### Manual Workflow Run

Trigger workflow manually:

1. Go to **Actions** tab
2. Select **CI/CD Pipeline** workflow
3. Click **Run workflow**
4. Select branch (`main`)
5. Click **Run workflow**

### Re-running Failed Jobs

1. Go to failed workflow run
2. Click **Re-run jobs**
3. Select **Re-run failed jobs** or **Re-run all jobs**

---

## Best Practices

### Development Workflow

1. **Create feature branch**: `git checkout -b feature-xyz`
2. **Develop and test locally**: `./run_tests.sh all`
3. **Create PR to main**: Tests run automatically
4. **Review and merge**: Triggers full CI/CD pipeline
5. **Monitor deployment**: Check Actions logs

### Security

1. **Protect secrets**: Never commit to repository
2. **Rotate SSH keys**: Regularly update deployment keys
3. **Use least privilege**: SSH user with minimal permissions
4. **Audit logs**: Review deployment logs regularly
5. **Enable 2FA**: On GitHub account

### Performance

1. **Cache dependencies**: Use GitHub Actions cache
2. **Prune Docker**: Free space before builds
3. **Parallel jobs**: Tests run independently
4. **BuildKit**: Faster Docker builds

### Reliability

1. **Health checks**: Always validate deployments
2. **Graceful shutdown**: Avoid dropping active requests
3. **Rollback plan**: Keep previous images available
4. **Monitor**: Set up alerts for failed deployments

---

## Resources

- **GitHub Actions**: https://docs.github.com/en/actions
- **Docker Buildx**: https://docs.docker.com/buildx/working-with-buildx/
- **GHCR**: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- **SSH Actions**: https://github.com/appleboy/ssh-action

---

**Last Updated**: 2025-11-13
**Version**: 2.0
**Covers**: 3-phase pipeline, GHCR integration, direct docker run deployment, health checks
