# InTEAM AI Service - Docker Guide

Complete guide for Docker configuration, container management, and deployment architecture.

## Table of Contents

1. [Docker Architecture](#docker-architecture)
2. [Container Overview](#container-overview)
3. [Network Configuration](#network-configuration)
4. [Volume Persistence](#volume-persistence)
5. [Production vs Development](#production-vs-development)
6. [Common Docker Commands](#common-docker-commands)
7. [Troubleshooting](#troubleshooting)

---

## Docker Architecture

### Container Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   PRODUCTION DEPLOYMENT                     │
│                 /srv/apps/django-app1/                      │
└─────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│  Docker Compose (docker-compose.production.yml)               │
│  Manages: Databases only (Postgres + Redis)                   │
│                                                               │
│  ┌────────────────────────┐  ┌──────────────────────────┐     │
│  │ inteam-ai-postgres     │  │ inteam-ai-redis          │     │
│  │ Image: pgvector/pg16   │  │ Image: redis:7-alpine    │     │
│  │ Port: 127.0.0.1:5433   │  │ Port: 127.0.0.1:6379     │     │
│  │ Volume: postgres_data  │  │ Volume: redis_data       │     │
│  └────────────────────────┘  └──────────────────────────┘     │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│  Standalone Container (started with docker run)               │
│  NOT managed by docker-compose                                │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ inteam-ai-django                                       │   │
│  │ Image: ghcr.io/md-ryhan-uddin/inteam-ai-service:SHA    │   │
│  │ Port: 127.0.0.1:8001                                   │   │
│  │ Bind Mounts:                                           │   │
│  │   - ./staticfiles → /app/staticfiles                   │   │
│  │   - ./media → /app/media                               │   │
│  │   - ./logs → /app/logs                                 │   │
│  │   - .env.production (env-file)                         │   │
│  │ Command: migrate + collectstatic + gunicorn            │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘

                              │
                              ↓
┌───────────────────────────────────────────────────────────────┐
│              Network: django-app1_django_ai_network           │
│              Driver: bridge                                   │
│              Subnet: 172.28.0.0/16                            │
│                                                               │
│  All 3 containers connected to this network                   │
│  Django can reach postgres:5432 and redis:6379 internally     │
└───────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

**Django runs standalone with `docker run` (not compose) because:**

1. **GHCR Integration**: Uses pre-built image from GitHub Container Registry
2. **No Local Build**: Avoids building on production server (saves time/resources)
3. **Immutable Deployments**: Each deployment uses a specific SHA-tagged image
4. **CI/CD Friendly**: Separates build (GitHub Actions) from deploy (docker run)

**Databases use compose because:**

1. **No Build Required**: Official images (pgvector/pg16, redis:7-alpine)
2. **Configuration Management**: Easier to manage with compose YAML
3. **Dependency Handling**: Health checks and service dependencies
4. **Volume Management**: Named volumes for data persistence

---

## Container Overview

### Django Container

```yaml
Container Name:  inteam-ai-django
Image:           ghcr.io/md-ryhan-uddin/inteam-ai-service:<SHA>
Restart Policy:  unless-stopped
Port:            127.0.0.1:8001:8001 (localhost-only)
Network:         django-app1_django_ai_network
```

**Environment Variables** (from `.env.production`):
- Django settings (SECRET_KEY, DEBUG, ALLOWED_HOSTS)
- Database connection (DB_HOST=postgres, DB_PORT=5432)
- Redis connection (REDIS_URL=redis://redis:6379/0)
- OpenAI API key
- RAG and Guardrails configuration

**Bind Mounts**:
- `./staticfiles:/app/staticfiles:Z` - Static assets (CSS, JS, images)
- `./media:/app/media:Z` - Uploaded files
- `./logs:/app/logs:Z` - Application logs
- `.env.production` - Environment variables (via --env-file)

**Startup Command**:
```bash
sh -c "python manage.py migrate --noinput &&
       python manage.py collectstatic --noinput --clear &&
       gunicorn config.wsgi:application
         --bind 0.0.0.0:8001
         --workers 3
         --worker-class gthread
         --threads 2
         --timeout 120
         --graceful-timeout 30
         --max-requests 1000
         --max-requests-jitter 100
         --access-logfile -
         --error-logfile -
         --log-level info"
```

**Gunicorn Configuration**:
- **3 workers** - Handle concurrent requests
- **2 threads per worker** - Total 6 concurrent request handlers
- **120s timeout** - For long-running AI requests
- **30s graceful timeout** - Clean shutdown
- **1000 max requests** - Worker recycling for memory management

### PostgreSQL Container

```yaml
Container Name:  inteam-ai-postgres
Image:           pgvector/pgvector:pg16
Restart Policy:  unless-stopped
Port:            127.0.0.1:5433:5432 (localhost-only)
Volume:          postgres_data:/var/lib/postgresql/data
Network:         django-app1_django_ai_network
```

**Extensions**:
- **pgvector** - Vector similarity search for RAG system
- **PostgreSQL 16** - Latest stable version

**Init Scripts** (auto-run on first start):
- `scripts/init_pgvector.sql` - Creates pgvector extension
- `scripts/init_readonly_user.sql` - Creates read-only database user

**Configuration**:
- `shared_buffers=256MB` - Memory for caching
- `max_connections=100` - Connection limit
- `effective_cache_size=1GB` - Query optimizer hint

### Redis Container

```yaml
Container Name:  inteam-ai-redis
Image:           redis:7-alpine
Restart Policy:  unless-stopped
Port:            127.0.0.1:6379:6379 (localhost-only)
Volume:          redis_data:/data
Network:         django-app1_django_ai_network
```

**Configuration**:
- `maxmemory 256mb` - Memory limit
- `maxmemory-policy allkeys-lru` - Eviction policy (Least Recently Used)
- `save 60 1000` - RDB snapshot: save if 1000+ keys change in 60s
- `appendonly yes` - AOF persistence for durability

---

## Network Configuration

### Network Name

```
django-app1_django_ai_network
```

**Created by**: `docker-compose.production.yml`

**Driver**: bridge (default)

**Subnet**: 172.28.0.0/16

### Container Communication

**Internal DNS Resolution** (within docker network):
- Django connects to `postgres:5432` (internal DNS)
- Django connects to `redis:6379` (internal DNS)
- No need for localhost or IP addresses

**External Access** (from host machine):
- Django: `localhost:8001` or `127.0.0.1:8001`
- PostgreSQL: `localhost:5433` or `127.0.0.1:5433`
- Redis: `localhost:6379` or `127.0.0.1:6379`

### Port Binding Security

All ports are bound to `127.0.0.1` (localhost-only):

```yaml
ports:
  - "127.0.0.1:8001:8001"   # NOT exposed to internet
```

**Why localhost-only?**
- Prevents direct external access to services
- Forces traffic through reverse proxy (nginx/caddy)
- Adds security layer (HTTPS, rate limiting, auth)

---

## Volume Persistence

### What Happens During Deployment?

```
┌────────────────────────────────────────────────────────┐
│  PERSISTENT DATA (Survives container recreation)       │
├────────────────────────────────────────────────────────┤
│  ✅ postgres_data volume                               │
│     - All database records                             │
│     - Clinical guidelines                              │
│     - PHI detection logs                               │
│     - User sessions                                    │
│                                                        │
│  ✅ redis_data volume                                  │
│     - Cached data                                      │
│     - AOF persistence file                             │
│                                                        │
│  ✅ ./staticfiles bind mount                           │
│     - Collected static files (CSS, JS, images)         │
│                                                        │
│  ✅ ./media bind mount                                 │
│     - Uploaded files                                   │
│                                                        │
│  ✅ ./logs bind mount                                  │
│     - Application logs                                 │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  EPHEMERAL DATA (Lost on container recreation)         │
├────────────────────────────────────────────────────────┤
│  ❌ Container filesystem                               │
│     - Temporary files                                  │
│     - Process memory                                   │
│     - Non-persistent caches                            │
│                                                        │
│  ❌ In-memory data                                     │
│     - Active Django sessions (if not in database)      │
│     - Runtime state                                    │
└────────────────────────────────────────────────────────┘
```

### Named Volumes vs Bind Mounts

**Named Volumes** (Docker-managed):
```yaml
volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
```

**Benefits**:
- Managed by Docker
- Can be backed up with `docker volume` commands
- Portable across different Docker hosts
- Better performance on non-Linux systems

**Location**: `/var/lib/docker/volumes/django-app1_postgres_data/_data`

**Bind Mounts** (Host filesystem):
```yaml
volumes:
  - ./staticfiles:/app/staticfiles:Z
  - ./media:/app/media:Z
  - ./logs:/app/logs:Z
```

**Benefits**:
- Direct access from host (easy to read logs)
- Can be edited from host machine
- Easy to backup with standard tools (rsync, tar)

**Location**: `/srv/apps/django-app1/staticfiles`, etc.

### SELinux `:Z` Flag

The `:Z` flag in volume mounts is for **SELinux** (used on Rocky Linux, RHEL, Fedora):

```yaml
- ./logs:/app/logs:Z
```

**What it does**:
- Sets SELinux context to allow container access
- Without `:Z`, container may get "Permission denied" errors
- Not needed on systems without SELinux (Ubuntu, Debian)

---

## Production vs Development

### Production Deployment

```bash
# Location
cd /srv/apps/django-app1

# Start databases with compose
docker compose -f docker-compose.production.yml up -d postgres redis

# Start Django with docker run (NOT compose)
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
  sh -c "python manage.py migrate && gunicorn ..."
```

**Characteristics**:
- Uses GHCR pre-built image
- PostgreSQL + pgvector (vector search)
- Redis (cache + Celery)
- Gunicorn with 3 workers
- Automatic migrations on startup
- Static files collected automatically

### Local Development

```bash
# Option 1: Use compose for all services
docker compose -f docker-compose.production.yml up -d

# Option 2: Run Python directly
python manage.py runserver 8001
```

**Characteristics**:
- Can use SQLite (no PostgreSQL needed)
- Redis optional (can use in-memory cache)
- Django dev server (single-threaded)
- DEBUG=True
- No Gunicorn

---

## Common Docker Commands

### Container Management

```bash
# View running containers
docker ps

# View only InTEAM containers
docker ps --filter "name=inteam-ai-"

# View all containers (including stopped)
docker ps -a

# Start containers
docker start inteam-ai-django
docker start inteam-ai-postgres
docker start inteam-ai-redis

# Stop containers
docker stop inteam-ai-django
docker stop inteam-ai-postgres
docker stop inteam-ai-redis

# Restart containers
docker restart inteam-ai-django

# Remove containers (stops first if running)
docker rm -f inteam-ai-django
docker rm -f inteam-ai-postgres
docker rm -f inteam-ai-redis

# Stop all InTEAM containers
docker stop $(docker ps -q --filter "name=inteam-ai-")
```

### Logs and Debugging

```bash
# View real-time logs
docker logs -f inteam-ai-django

# View last 100 lines
docker logs --tail 100 inteam-ai-django

# View logs with timestamps
docker logs --timestamps inteam-ai-django

# View logs since 1 hour ago
docker logs --since 1h inteam-ai-django

# Save logs to file
docker logs inteam-ai-django > django-logs.txt

# View Postgres logs
docker logs inteam-ai-postgres

# View Redis logs
docker logs inteam-ai-redis
```

### Execute Commands in Containers

```bash
# Use docker exec (NOT docker-compose exec)
docker exec inteam-ai-django python manage.py migrate
docker exec inteam-ai-django python manage.py shell
docker exec inteam-ai-django python manage.py test

# Interactive shell
docker exec -it inteam-ai-django bash
docker exec -it inteam-ai-django python manage.py shell

# Database shell
docker exec -it inteam-ai-django python manage.py dbshell

# PostgreSQL commands
docker exec -it inteam-ai-postgres psql -U ryhan -d inteam_ai

# Redis commands
docker exec -it inteam-ai-redis redis-cli
```

### Image Management

```bash
# List images
docker images | grep inteam-ai

# Pull latest image from GHCR
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:latest

# Pull specific SHA
docker pull ghcr.io/md-ryhan-uddin/inteam-ai-service:a1b2c3d

# Remove old images
docker image prune -a

# Remove specific image
docker rmi ghcr.io/md-ryhan-uddin/inteam-ai-service:old-sha

# View image history
docker history ghcr.io/md-ryhan-uddin/inteam-ai-service:latest
```

### Network Management

```bash
# List networks
docker network ls

# Inspect network
docker network inspect django-app1_django_ai_network

# View connected containers
docker network inspect django-app1_django_ai_network | grep Name

# Test connectivity between containers
docker exec inteam-ai-django ping postgres
docker exec inteam-ai-django ping redis
```

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect django-app1_postgres_data

# Backup PostgreSQL volume
docker run --rm \
  -v django-app1_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz /data

# Restore PostgreSQL volume
docker run --rm \
  -v django-app1_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres-backup.tar.gz -C /

# Remove unused volumes (CAUTION: Data loss!)
docker volume prune
```

### Resource Monitoring

```bash
# Container stats (CPU, memory, network, disk)
docker stats inteam-ai-django inteam-ai-postgres inteam-ai-redis

# Single container stats
docker stats inteam-ai-django

# Disk usage
docker system df

# Detailed disk usage
docker system df -v

# Container resource limits
docker inspect inteam-ai-django | grep -A 10 Resources
```

### Health Checks

```bash
# Check Django health endpoint
curl http://localhost:8001/health/

# Check container health status
docker inspect inteam-ai-django | grep -A 10 Health

# Check if containers are running
docker ps --filter "name=inteam-ai-" --filter "status=running"

# Test database connection
docker exec inteam-ai-django python -c "
from django.db import connection
connection.ensure_connection()
print('Database connected!')
"

# Test Redis connection
docker exec inteam-ai-redis redis-cli ping
```

---

## Troubleshooting

### Issue: Container name already in use

**Error**:
```
Error response from daemon: Conflict. The container name "/inteam-ai-django" is already in use
```

**Solution**:
```bash
# Stop and remove existing container
docker stop inteam-ai-django
docker rm inteam-ai-django

# Or force remove
docker rm -f inteam-ai-django
```

### Issue: Port already in use

**Error**:
```
Error starting userland proxy: listen tcp 0.0.0.0:8001: bind: address already in use
```

**Solution**:
```bash
# Find process using port
sudo lsof -i :8001
sudo netstat -tlnp | grep 8001

# Kill process or stop conflicting container
docker stop $(docker ps -q --filter "publish=8001")
```

### Issue: Network not found

**Error**:
```
Error response from daemon: network django-app1_django_ai_network not found
```

**Solution**:
```bash
# Create network with compose
docker compose -f docker-compose.production.yml up -d

# Or create manually
docker network create \
  --driver bridge \
  --subnet 172.28.0.0/16 \
  --gateway 172.28.0.1 \
  django-app1_django_ai_network
```

### Issue: Volume permission denied

**Error**:
```
PermissionError: [Errno 13] Permission denied: '/app/logs/django.log'
```

**Solution**:
```bash
# Fix ownership (1000 is the container user ID)
sudo chown -R 1000:1000 logs/ staticfiles/ media/

# Or use current user
sudo chown -R $USER:$USER logs/ staticfiles/ media/

# Verify permissions
ls -la logs/ staticfiles/ media/
```

### Issue: Cannot connect to database

**Error**:
```
django.db.utils.OperationalError: could not connect to server: Connection refused
```

**Solution**:
```bash
# Check if postgres is running
docker ps | grep postgres

# Check postgres logs
docker logs inteam-ai-postgres

# Restart postgres
docker restart inteam-ai-postgres

# Wait for health check
docker inspect inteam-ai-postgres | grep -A 10 Health

# Test connection from Django container
docker exec inteam-ai-django python manage.py check --database default
```

### Issue: Out of disk space

**Error**:
```
Error: No space left on device
```

**Solution**:
```bash
# Check disk usage
df -h
docker system df

# Clean up unused resources
docker system prune -a --volumes

# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes (CAUTION!)
docker volume prune
```

### Issue: Container keeps restarting

**Solution**:
```bash
# Check restart count
docker ps -a | grep inteam-ai

# View logs for crash reason
docker logs --tail 200 inteam-ai-django

# Disable restart to debug
docker update --restart=no inteam-ai-django

# Start manually to see error
docker start -a inteam-ai-django
```

---

## Best Practices

### Security

1. **Bind ports to localhost only**: `127.0.0.1:8001:8001`
2. **Use secrets for sensitive data**: Never hardcode in Dockerfile
3. **Update base images regularly**: `docker pull` latest versions
4. **Use read-only filesystem** (optional): Add `--read-only` flag
5. **Limit container resources**: Use `--memory` and `--cpus` flags

### Performance

1. **Use Docker BuildKit**: `DOCKER_BUILDKIT=1 docker build`
2. **Layer caching**: Order Dockerfile commands from least to most frequently changed
3. **Multi-stage builds**: Separate build and runtime stages
4. **Volume for dependencies**: Cache pip packages
5. **Health checks**: Configure appropriate intervals

### Maintenance

1. **Regular backups**: Use `docker volume` backup commands
2. **Monitor logs**: Set up log rotation
3. **Update regularly**: Pull latest images weekly
4. **Clean unused resources**: Run `docker system prune` monthly
5. **Document configuration**: Keep this guide updated

### Development Workflow

1. **Use docker exec**: More reliable than docker-compose exec
2. **Test locally first**: Before deploying to production
3. **Tag images properly**: Use SHAs for immutable deployments
4. **Version control volumes**: Backup before major changes
5. **Monitor resources**: Use `docker stats` regularly

---

## Docker Compose Reference

### Start Services

```bash
# Start all services
docker compose -f docker-compose.production.yml up -d

# Start specific services
docker compose -f docker-compose.production.yml up -d postgres redis

# Start with logs
docker compose -f docker-compose.production.yml up
```

### Stop Services

```bash
# Stop all services
docker compose -f docker-compose.production.yml stop

# Stop specific service
docker compose -f docker-compose.production.yml stop postgres

# Stop and remove containers
docker compose -f docker-compose.production.yml down

# Stop and remove volumes (CAUTION: Data loss!)
docker compose -f docker-compose.production.yml down -v
```

### View Status

```bash
# List services
docker compose -f docker-compose.production.yml ps

# View logs
docker compose -f docker-compose.production.yml logs -f

# View specific service logs
docker compose -f docker-compose.production.yml logs -f postgres
```

---

## Resources

- **Docker Documentation**: https://docs.docker.com/
- **Docker Compose**: https://docs.docker.com/compose/
- **pgvector**: https://github.com/pgvector/pgvector
- **Redis**: https://redis.io/documentation
- **Gunicorn**: https://docs.gunicorn.org/

---

**Last Updated**: 2025-11-13
**Version**: 2.0
**Covers**: Production docker run deployment, GHCR images, network architecture, volume persistence
