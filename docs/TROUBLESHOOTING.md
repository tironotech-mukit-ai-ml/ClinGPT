# InTEAM AI Service - Troubleshooting Guide

Comprehensive troubleshooting guide for common issues, errors, and solutions.

## Table of Contents

1. [Container Issues](#container-issues)
2. [Database Connection Problems](#database-connection-problems)
3. [Test Failures](#test-failures)
4. [Health Check Failures](#health-check-failures)
5. [Deployment Issues](#deployment-issues)
6. [Network Problems](#network-problems)
7. [Performance Issues](#performance-issues)
8. [API Errors](#api-errors)
9. [CI/CD Pipeline Failures](#cicd-pipeline-failures)

---

## Container Issues

### Issue: Container name already in use

**Error**:
```
Error response from daemon: Conflict. The container name "/inteam-ai-django" is already in use
```

**Cause**: A container with that name already exists (running or stopped)

**Solution**:
```bash
# Option 1: Force remove existing container
docker rm -f inteam-ai-django

# Option 2: Stop and remove
docker stop inteam-ai-django
docker rm inteam-ai-django

# Then retry deployment
./deploy.sh

# Verify containers
docker ps --filter "name=inteam-ai-"
```

---

### Issue: Container keeps restarting

**Symptoms**:
```bash
docker ps -a
# Shows container with "Restarting" status or high restart count
```

**Debugging Steps**:

1. **Check container logs**:
```bash
docker logs --tail 200 inteam-ai-django
```

2. **Common causes**:
   - Database connection failed
   - Missing environment variables
   - Port already in use
   - Migration errors
   - Application crash

3. **Disable auto-restart to debug**:
```bash
docker update --restart=no inteam-ai-django
docker stop inteam-ai-django

# Start manually to see error
docker start -a inteam-ai-django
```

4. **Fix the issue**, then re-enable restart:
```bash
docker update --restart=unless-stopped inteam-ai-django
docker start inteam-ai-django
```

---

### Issue: Cannot remove container

**Error**:
```
Error response from daemon: removal of container inteam-ai-django is already in progress
```

**Solution**:
```bash
# Wait a few seconds and retry
sleep 5
docker rm -f inteam-ai-django

# If still stuck, restart Docker daemon
sudo systemctl restart docker

# Last resort: kill container process
docker inspect inteam-ai-django | grep Pid
sudo kill -9 <PID>
docker rm -f inteam-ai-django
```

---

### Issue: Port already in use

**Error**:
```
Error starting userland proxy: listen tcp 0.0.0.0:8001: bind: address already in use
```

**Solution**:

1. **Find process using port**:
```bash
sudo lsof -i :8001
# or
sudo netstat -tlnp | grep 8001
```

2. **Stop conflicting container**:
```bash
docker ps | grep 8001
docker stop <container-id>
```

3. **Kill conflicting process** (if not Docker):
```bash
sudo kill -9 <PID>
```

4. **Verify port is free**:
```bash
sudo lsof -i :8001
# Should return nothing
```

---

## Database Connection Problems

### Issue: Cannot connect to PostgreSQL

**Error**:
```
django.db.utils.OperationalError: could not connect to server: Connection refused
    Is the server running on host "postgres" and accepting TCP/IP connections on port 5432?
```

**Debugging Steps**:

1. **Check if PostgreSQL is running**:
```bash
docker ps | grep postgres
# Should show inteam-ai-postgres with "Up" status
```

2. **Check PostgreSQL logs**:
```bash
docker logs inteam-ai-postgres
# Look for startup errors
```

3. **Verify network connection**:
```bash
# From Django container
docker exec inteam-ai-django ping postgres
docker exec inteam-ai-django nc -zv postgres 5432
```

4. **Check environment variables**:
```bash
docker exec inteam-ai-django env | grep DB_
# Verify: DB_HOST=postgres, DB_PORT=5432
```

5. **Restart PostgreSQL**:
```bash
docker restart inteam-ai-postgres
sleep 10  # Wait for startup
docker exec inteam-ai-postgres pg_isready -U ryhan
```

**Solutions**:

```bash
# Ensure .env.production has correct values
cat .env.production | grep DB_

# Expected values:
DB_HOST=postgres  # NOT localhost!
DB_PORT=5432
DB_NAME=inteam_ai
DB_USER=ryhan
DB_PASSWORD=<your-password>

# Restart containers in correct order
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d postgres redis
sleep 15
# Then start Django
```

---

### Issue: Authentication failed for PostgreSQL

**Error**:
```
FATAL: password authentication failed for user "ryhan"
```

**Solution**:

1. **Check password in .env.production**:
```bash
grep POSTGRES_PASSWORD .env.production
grep DB_PASSWORD .env.production
# Must match!
```

2. **Reset PostgreSQL password**:
```bash
docker exec -it inteam-ai-postgres psql -U postgres -c "ALTER USER ryhan WITH PASSWORD 'new_password';"

# Update .env.production
sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=new_password/" .env.production
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=new_password/" .env.production

# Restart Django
docker restart inteam-ai-django
```

---

### Issue: Database does not exist

**Error**:
```
django.db.utils.OperationalError: FATAL: database "inteam_ai" does not exist
```

**Solution**:

1. **Create database manually**:
```bash
docker exec -it inteam-ai-postgres psql -U ryhan -c "CREATE DATABASE inteam_ai;"
```

2. **Or recreate PostgreSQL container** (CAUTION: Data loss!):
```bash
docker stop inteam-ai-postgres
docker rm inteam-ai-postgres
docker volume rm django-app1_postgres_data  # WARNING: Deletes all data!

# Restart
docker compose -f docker-compose.production.yml up -d postgres
```

---

## Test Failures

### Issue: Tests fail with "OPENAI_API_KEY not set"

**Error**:
```
openai.AuthenticationError: No API key provided
```

**Cause**: `.env` file missing or `OPENAI_API_KEY` not set

**Solution**:

1. **Create .env file**:
```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-your-key-here
DEBUG=True
SECRET_KEY=test-key
EOF
```

2. **Verify key is set**:
```bash
grep OPENAI_API_KEY .env
# Should show your key (starts with sk-proj- or sk-)
```

3. **Retry tests**:
```bash
./run_tests.sh minimal
```

---

### Issue: Tests fail with "Spacy model not found"

**Error**:
```
OSError: [E050] Can't find model 'en_core_web_sm'
```

**Solution**:

```bash
# Inside container
docker exec inteam-ai-django python -m spacy download en_core_web_sm

# Or use install script
docker exec inteam-ai-django python scripts/install_spacy.py

# Verify installation
docker exec inteam-ai-django python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('OK')"

# Restart container
docker restart inteam-ai-django
```

---

### Issue: Layer 2 tests fail (PHI or RAG)

**Common Causes**:

1. **PHI Guardrail not initialized**:
```bash
# Test directly
docker exec inteam-ai-django python -c "
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail
g = get_phi_guardrail()
print('PHI Guardrail OK:', g.enabled)
"
```

2. **RAG Service not initialized**:
```bash
# Test directly
docker exec inteam-ai-django python -c "
from apps.clin_gpt.services.rag_service import get_rag_service
rag = get_rag_service()
print('RAG Service OK:', rag.enabled)
"
```

3. **No clinical guidelines**:
```bash
# Check guideline count
docker exec inteam-ai-django python -c "
from apps.clin_gpt.models import ClinicalGuideline
print('Guidelines:', ClinicalGuideline.objects.count())
"

# Populate if empty
docker exec inteam-ai-django python manage.py populate_guidelines
```

---

### Issue: Layer 3 tests fail (OpenAI integration)

**Debugging**:

1. **Verify OpenAI API key**:
```bash
docker exec inteam-ai-django python -c "
import os
key = os.getenv('OPENAI_API_KEY')
print('Key starts with:', key[:10] if key else 'NOT SET')
"
```

2. **Test OpenAI connection**:
```bash
docker exec inteam-ai-django python -c "
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model='gpt-4-turbo-preview',
    messages=[{'role': 'user', 'content': 'test'}],
    max_tokens=10
)
print('OpenAI OK')
"
```

3. **Check OpenAI account**:
   - Visit: https://platform.openai.com/account/billing
   - Ensure you have credits
   - Verify API key is active

---

## Health Check Failures

### Issue: Health endpoint not responding

**Error**:
```
curl: (7) Failed to connect to localhost port 8001: Connection refused
```

**Debugging Steps**:

1. **Check if Django container is running**:
```bash
docker ps | grep inteam-ai-django
```

2. **Check Django logs**:
```bash
docker logs --tail 100 inteam-ai-django
# Look for startup errors
```

3. **Check if port is bound**:
```bash
sudo netstat -tlnp | grep 8001
# Should show docker-proxy listening
```

4. **Test from inside container**:
```bash
docker exec inteam-ai-django curl -v http://localhost:8001/health/
```

**Solutions**:

```bash
# Restart Django container
docker restart inteam-ai-django

# Wait 30 seconds for startup
sleep 30

# Test health endpoint
curl http://localhost:8001/health/

# If still fails, check migrations
docker exec inteam-ai-django python manage.py showmigrations
docker exec inteam-ai-django python manage.py migrate
```

---

### Issue: Health check returns 500 error

**Error**:
```
HTTP/1.1 500 Internal Server Error
```

**Debugging**:

1. **Check Django logs for error**:
```bash
docker logs inteam-ai-django | grep -A 20 "Internal Server Error"
```

2. **Common causes**:
   - Database connection failed
   - Missing migrations
   - Syntax error in code
   - Missing environment variable

3. **Test database connection**:
```bash
docker exec inteam-ai-django python manage.py check --database default
```

4. **Run migrations**:
```bash
docker exec inteam-ai-django python manage.py migrate
```

---

## Deployment Issues

### Issue: Deployment fails with "image not found"

**Error**:
```
Error response from daemon: manifest for ghcr.io/md-ryhan-uddin/inteam-ai-service:abc1234 not found
```

**Cause**: Image not built or pushed to GHCR

**Solution**:

1. **Check GitHub Actions build phase**:
   - Go to Actions tab
   - Verify "Build and Push" job succeeded

2. **Check GHCR for image**:
   - Go to repository → Packages
   - Verify image with SHA tag exists

3. **Manual build and push** (if needed):
```bash
# Login to GHCR
echo $GHCR_PAT | docker login ghcr.io -u md-ryhan-uddin --password-stdin

# Build image
docker build -t ghcr.io/md-ryhan-uddin/inteam-ai-service:latest -f Dockerfile.production .

# Push image
docker push ghcr.io/md-ryhan-uddin/inteam-ai-service:latest
```

---

### Issue: Deployment fails with ".env.production not found"

**Error**:
```
❌ ERROR: .env.production file not found!
```

**Solution**:

```bash
# SSH to server
ssh user@your-server
cd /srv/apps/django-app1

# Create .env.production file
nano .env.production
# Add all required environment variables (see DEPLOYMENT_GUIDE.md)

# Verify file exists
ls -la .env.production

# Retry deployment
git pull origin main
./deploy.sh
```

---

### Issue: Migration fails during deployment

**Error**:
```
django.db.migrations.exceptions.InconsistentMigrationHistory
```

**Solution**:

1. **Check migration status**:
```bash
docker exec inteam-ai-django python manage.py showmigrations
```

2. **Fake conflicting migrations** (CAUTION):
```bash
docker exec inteam-ai-django python manage.py migrate --fake <app_name> <migration_name>
```

3. **Or reset migrations** (DEVELOPMENT ONLY):
```bash
# Backup database first!
docker exec inteam-ai-postgres pg_dump -U ryhan inteam_ai > backup.sql

# Remove migration history
docker exec inteam-ai-django python manage.py migrate --fake <app_name> zero
docker exec inteam-ai-django python manage.py migrate
```

---

## Network Problems

### Issue: Containers cannot communicate

**Symptoms**: Django cannot reach PostgreSQL or Redis

**Debugging**:

1. **Check if all containers on same network**:
```bash
docker network inspect django-app1_django_ai_network | grep Name
# Should show: inteam-ai-django, inteam-ai-postgres, inteam-ai-redis
```

2. **Test connectivity**:
```bash
docker exec inteam-ai-django ping postgres
docker exec inteam-ai-django ping redis
```

3. **Verify DNS resolution**:
```bash
docker exec inteam-ai-django nslookup postgres
docker exec inteam-ai-django nslookup redis
```

**Solution**:

```bash
# Recreate containers with correct network
docker stop inteam-ai-django
docker rm inteam-ai-django

# Ensure network exists
docker network ls | grep django_ai_network
# If not, create with compose:
docker compose -f docker-compose.production.yml up -d postgres redis

# Start Django with correct network
docker run -d \
  --name inteam-ai-django \
  --network django-app1_django_ai_network \
  ... (other flags) \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:latest
```

---

### Issue: Network not found

**Error**:
```
Error response from daemon: network django-app1_django_ai_network not found
```

**Solution**:

```bash
# Create network with compose
docker compose -f docker-compose.production.yml up -d postgres redis

# Or create manually
docker network create \
  --driver bridge \
  --subnet 172.28.0.0/16 \
  --gateway 172.28.0.1 \
  django-app1_django_ai_network

# Verify
docker network ls | grep django_ai_network
```

---

## Performance Issues

### Issue: Slow API response times

**Symptoms**: API takes >5 seconds to respond

**Debugging**:

1. **Check logs for performance metrics**:
```bash
docker logs inteam-ai-django | grep "Request completed"
# Shows request duration
```

2. **Monitor container resources**:
```bash
docker stats inteam-ai-django
# Check CPU and memory usage
```

3. **Test individual components**:
```bash
# Test PHI detection speed
docker exec inteam-ai-django python -c "
import time
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail
g = get_phi_guardrail()
start = time.time()
g.redact_phi('test text with John Doe and 555-1234')
print(f'PHI detection: {(time.time()-start)*1000:.2f} ms')
"

# Test RAG retrieval speed
docker exec inteam-ai-django python -c "
import time
from apps.clin_gpt.services.rag_service import get_rag_service
rag = get_rag_service()
start = time.time()
rag.retrieve_relevant_guidelines({'symptoms': 'chest pain'})
print(f'RAG retrieval: {(time.time()-start)*1000:.2f} ms')
"
```

**Solutions**:

1. **Increase Gunicorn workers**:
```bash
# Edit deployment command to use more workers
--workers 5  # Increase from 3 to 5
```

2. **Enable caching**:
```bash
# Verify Redis is running
docker ps | grep redis

# Check Redis connection
docker exec inteam-ai-redis redis-cli ping
```

3. **Optimize database queries**:
```bash
# Vacuum PostgreSQL
docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "VACUUM ANALYZE;"

# Create pgvector index (if not exists)
docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "
CREATE INDEX IF NOT EXISTS idx_guideline_embedding
ON clin_gpt_clinicalguideline
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
"
```

---

### Issue: High memory usage

**Symptoms**: Container using >2GB RAM

**Debugging**:
```bash
docker stats inteam-ai-django
```

**Solutions**:

1. **Restart container** (clears memory leaks):
```bash
docker restart inteam-ai-django
```

2. **Reduce Gunicorn workers**:
```bash
# Each worker uses ~200-300MB
--workers 2  # Reduce from 3 to 2
```

3. **Enable worker recycling**:
```bash
# Already configured in deployment
--max-requests 1000  # Restart worker after 1000 requests
```

---

## API Errors

### Issue: API returns 401 Unauthorized

**Error**:
```json
{"detail": "Authentication credentials were not provided."}
```

**Cause**: Missing or invalid authentication token

**Solution**:

1. **Check if authentication is required**:
```bash
# View settings
docker exec inteam-ai-django python -c "
from django.conf import settings
print('Auth required:', bool(settings.REST_FRAMEWORK.get('DEFAULT_AUTHENTICATION_CLASSES')))
"
```

2. **Add authentication header**:
```bash
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{"patient_data": {"symptoms": "test"}}'
```

---

### Issue: API returns 400 Bad Request

**Error**:
```json
{"error": "Invalid request format"}
```

**Debugging**:

1. **Check request format**:
```bash
# Correct format:
{
  "patient_data": {
    "symptoms": "chest pain",
    "age": 45,
    "gender": "male"
  }
}
```

2. **View Django logs for validation errors**:
```bash
docker logs --tail 50 inteam-ai-django | grep "Bad Request"
```

---

### Issue: API returns 500 Internal Server Error

**Debugging**:

```bash
# Check Django logs for traceback
docker logs --tail 100 inteam-ai-django

# Common causes:
# - OpenAI API error
# - Database connection lost
# - RAG/PHI service error
# - Unhandled exception
```

**Solutions**:

1. **Check OpenAI account**:
   - Verify API key is valid
   - Ensure you have credits

2. **Restart services**:
```bash
docker restart inteam-ai-django
docker restart inteam-ai-postgres
docker restart inteam-ai-redis
```

3. **Check error details**:
```bash
# Enable DEBUG temporarily (development only!)
docker exec inteam-ai-django python -c "
from django.conf import settings
print('DEBUG:', settings.DEBUG)
"
```

---

## CI/CD Pipeline Failures

### Issue: Test phase fails in GitHub Actions

**Common Causes**:

1. **OpenAI API key not set**:
   - Add `OPENAI_API_KEY` to GitHub Secrets
   - Settings → Secrets and variables → Actions

2. **Spacy model download fails**:
   - Check GitHub Actions logs
   - Verify `scripts/install_spacy.py` is correct

3. **Integration test fails**:
   - Check OpenAI account has credits
   - Verify test code is correct

---

### Issue: Build phase fails

**Error**:
```
Error response from daemon: dockerfile parse error
```

**Solution**:

1. **Check Dockerfile.production syntax**:
```bash
# Test locally
docker build -f Dockerfile.production -t test-image .
```

2. **Common issues**:
   - Missing backslash in multi-line RUN
   - Incorrect COPY paths
   - Base image not found

---

### Issue: Deploy phase fails - SSH connection

**Error**:
```
ssh: connect to host 159.198.76.203 port 22: Connection refused
```

**Solution**:

1. **Verify server is reachable**:
```bash
ping 159.198.76.203
ssh user@159.198.76.203
```

2. **Check GitHub Secrets**:
   - `SERVER_HOST`: Correct IP/domain
   - `SERVER_USERNAME`: Valid SSH user
   - `SERVER_SSH_KEY`: Complete private key (including headers)
   - `SERVER_PORT`: Correct SSH port (default: 22)

3. **Test SSH key**:
```bash
# From local machine
ssh -i ~/.ssh/github_actions_key user@server-ip
```

---

### Issue: Deploy phase fails - Health check timeout

**Error**:
```
❌ Health check failed after 60s
```

**Debugging**:

1. **Check deployment logs in GitHub Actions**:
   - Scroll to health check section
   - Look for Django logs output

2. **SSH to server and check**:
```bash
ssh user@your-server
docker logs --tail 100 inteam-ai-django
curl http://localhost:8001/health/
```

3. **Common causes**:
   - Migration failed
   - Database connection failed
   - Gunicorn failed to start
   - Port conflict

---

## Quick Diagnostic Commands

### Full System Health Check

```bash
#!/bin/bash
echo "=== Container Status ==="
docker ps --filter "name=inteam-ai-"

echo -e "\n=== Health Endpoint ==="
curl -s http://localhost:8001/health/ | python -m json.tool

echo -e "\n=== Database Connection ==="
docker exec inteam-ai-django python manage.py check --database default

echo -e "\n=== Redis Connection ==="
docker exec inteam-ai-redis redis-cli ping

echo -e "\n=== Clinical Guidelines Count ==="
docker exec inteam-ai-django python -c "from apps.clin_gpt.models import ClinicalGuideline; print(ClinicalGuideline.objects.count())"

echo -e "\n=== Resource Usage ==="
docker stats --no-stream inteam-ai-django inteam-ai-postgres inteam-ai-redis

echo -e "\n=== Recent Errors ==="
docker logs --since 1h inteam-ai-django | grep -i error | tail -10
```

Save as `health_check.sh` and run:
```bash
chmod +x health_check.sh
./health_check.sh
```

---

## Getting Help

### Where to Look

1. **Documentation**:
   - [INDEX.md](INDEX.md) - Documentation overview
   - [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) - Development setup
   - [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deployment procedures

2. **Logs**:
   - Django: `docker logs inteam-ai-django`
   - PostgreSQL: `docker logs inteam-ai-postgres`
   - Redis: `docker logs inteam-ai-redis`
   - CI/CD: GitHub Actions tab

3. **Health Checks**:
   - API: `curl http://localhost:8001/health/`
   - Database: `docker exec inteam-ai-django python manage.py check --database default`
   - Redis: `docker exec inteam-ai-redis redis-cli ping`

---

## Emergency Procedures

### Complete Service Restart

```bash
# Stop all containers
docker stop inteam-ai-django inteam-ai-postgres inteam-ai-redis
docker rm -f inteam-ai-django inteam-ai-postgres inteam-ai-redis

# Start databases
docker compose -f docker-compose.production.yml up -d postgres redis
sleep 15

# Start Django
docker run -d \
  --name inteam-ai-django \
  --restart unless-stopped \
  --env-file .env.production \
  -v "$(pwd)/staticfiles:/app/staticfiles:Z" \
  -v "$(pwd)/media:/app/media:Z" \
  -v "$(pwd)/logs:/app/logs:Z" \
  -p 127.0.0.1:8001:8001 \
  --network django-app1_django_ai_network \
  ghcr.io/md-ryhan-uddin/inteam-ai-service:latest \
  sh -c "python manage.py migrate --noinput && gunicorn ..."

# Wait and verify
sleep 30
curl http://localhost:8001/health/
```

---

**Last Updated**: 2025-11-13
**Version**: 2.0
**Covers**: Container issues, database problems, test failures, health checks, deployment issues
