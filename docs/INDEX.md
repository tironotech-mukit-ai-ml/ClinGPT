# InTEAM AI Service - Documentation Index

Complete documentation for the InTEAM AI clinical decision support service.

---

## 📚 Documentation Structure

```
docs/
├── INDEX.md (this file)            - Documentation navigation
├── DEPLOYMENT.md                   - Production deployment with CI/CD
├── DEVELOPMENT.md                  - Local development setup
├── DOCKER_GUIDE.md                 - Docker configuration & commands
├── CI_CD.md                        - GitHub Actions pipeline details
├── RAG_SYSTEM.md                   - Clinical guidelines & RAG
├── GUARDRAILS.md                   - PHI protection & HIPAA compliance
└── TROUBLESHOOTING.md              - Common issues & solutions
```

---

## 🚀 Quick Start Guides

### For New Developers
1. **[DEVELOPMENT_GUIDE.md](DEVELOPMENT.md)** - Set up local environment
2. **[DOCKER_GUIDE.md](DOCKER.md)** - Understand Docker setup
3. **Test locally** - Run `./run_tests.sh`

### For DevOps / Deployment
1. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT.md)** - Production deployment
2. **[CI-CD_GUIDE.md](CI_CD.md)** - Configure GitHub Actions
3. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Fix deployment issues

### For System Administrators
1. **[DOCKER_GUIDE.md](DOCKER.md)** - Manage containers
2. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT.md)** - Monitoring & maintenance
3. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Debug issues

---

## 📖 Documentation Files

### Core Documentation

#### [DEPLOYMENT_GUIDE.md](DEPLOYMENT.md)
**Production deployment guide with automated CI/CD**

Topics covered:
- Deployment architecture diagram
- Server setup & prerequisites
- GitHub secrets configuration
- Automated deployment flow
- Manual deployment steps
- Data persistence & backups
- Rollback procedures
- Troubleshooting deployment issues

**When to read**: Before deploying to production, when setting up CI/CD

---

#### [DEVELOPMENT_GUIDE.md](DEVELOPMENT.md)
**Local development setup and workflows**

Topics covered:
- Prerequisites (Python, Docker)
- Local environment setup
- Running development server
- Database migrations
- Testing workflows
- Code structure
- Adding new features

**When to read**: When starting development, adding new features

---

#### [DOCKER_GUIDE.md](DOCKER.md)
**Docker configuration, commands, and best practices**

Topics covered:
- Docker architecture
- Container management
- Volume management
- Network configuration
- Common Docker commands
- Troubleshooting Docker issues

**When to read**: When working with containers, debugging Docker issues

---

#### [CI-CD_GUIDE.md](CI_CD.md)
**GitHub Actions pipeline configuration**

Topics covered:
- CI/CD workflow explanation
- Test phase configuration
- Build & push phase
- Deploy phase
- GitHub secrets setup
- Workflow triggers
- Pipeline optimization

**When to read**: When modifying CI/CD pipeline, troubleshooting deployments

---

### Feature Documentation

#### [RAG_SYSTEM.md](RAG_SYSTEM.md)
**Retrieval-Augmented Generation for clinical guidelines**

Topics covered:
- RAG architecture
- Clinical guidelines database
- Vector embeddings (pgvector)
- Sentence transformers
- Query flow
- Adding new guidelines
- Performance optimization

**When to read**: Understanding how clinical recommendations work

---

#### [GUARDRAILS.md](GUARDRAILS.md)
**PHI protection and HIPAA compliance**

Topics covered:
- PHI detection system
- Spacy NER models
- Redaction policies
- PHI logging
- HIPAA compliance
- Testing PHI detection
- Custom entity types

**When to read**: Understanding privacy protection, compliance requirements

---

### Reference Documentation

#### [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
**Common issues and solutions**

Topics covered:
- Deployment failures
- Container issues
- Database problems
- Network errors
- Test failures
- Performance issues

**When to read**: When encountering errors or issues

---

## 🎯 Common Tasks

### Running Tests

```bash
# Quick validation (no OpenAI cost)
./run_tests.sh minimal

# Full test suite (~$0.01)
./run_tests.sh all

# Comprehensive tests (~$0.13)
python test_full_system.py
```

See: [DEVELOPMENT_GUIDE.md](DEVELOPMENT.md#testing)

---

### Deploying to Production

```bash
# Automated (recommended)
git push origin main  # Triggers CI/CD

# Manual
ssh user@server
cd /srv/apps/django-app1
./deploy.sh
```

See: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#deployment-flow)

---

### Managing Containers

```bash
# View running containers
docker ps --filter "name=inteam-ai-"

# View logs
docker logs -f inteam-ai-django

# Restart service
docker restart inteam-ai-django

# Stop all services
docker compose -f docker-compose.production.yml down
```

See: [DOCKER_GUIDE.md](DOCKER_GUIDE.md#common-commands)

---

### Database Operations

```bash
# Run migrations
docker exec inteam-ai-django python manage.py migrate

# Populate clinical guidelines
docker exec inteam-ai-django python manage.py populate_guidelines

# Backup database
docker exec inteam-ai-postgres pg_dump -U ryhan inteam_ai > backup.sql

# Check guideline count
docker exec inteam-ai-django python -c "from apps.clin_gpt.models import ClinicalGuideline; print(ClinicalGuideline.objects.count())"
```

See: [DEPLOYMENT_GUIDE.md](DEPLOYMENT.md#database-maintenance)

---

## 📊 System Architecture

### High-Level Overview

```
┌────────────────────────────────────────────────────────────┐
│                    CLIENT (Laravel EMR)                    │
└──────────────────────┬─────────────────────────────────────┘
                       │ HTTP POST /api/v1/clin-gpt/analyze/
                       ↓
┌────────────────────────────────────────────────────────────┐
│                  DJANGO AI SERVICE (port 8001)             │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ PHI          │  │ RAG          │  │ OpenAI           │  │
│  │ Guardrail    │  │ Service      │  │ Integration      │  │
│  │ (Spacy NER)  │  │ (pgvector)   │  │ (GPT-4 Turbo)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────┬─────────────────┬───────────────────┬───────────┘
           │                 │                   │
           ↓                 ↓                   ↓
┌──────────────────┐ ┌──────────────────┐ ┌────────────────┐
│ PostgreSQL+      │ │ Redis            │ │ OpenAI API     │
│ pgvector         │ │ Cache/Celery     │ │ (External)     │
│ (port 5433)      │ │ (port 6379)      │ │                │
└──────────────────┘ └──────────────────┘ └────────────────┘
```

---

## 🔐 Security & Compliance

### PHI Protection
- **Automatic PHI detection** using Spacy NER models
- **Redaction** of sensitive information before logging
- **Audit trail** of all PHI detections

See: [GUARDRAILS.md](GUARDRAILS.md)

### HIPAA Compliance
- No PHI stored in logs
- All API requests authenticated
- Secure Docker networking (localhost-only ports)
- Encrypted data at rest (optional: configure encryption)

---

## 📈 Performance & Scalability

### Current Configuration
- **Workers**: 3 Gunicorn workers with 2 threads each
- **Timeout**: 120 seconds for long-running AI requests
- **Cache**: Redis for response caching
- **Database**: PostgreSQL with pgvector for fast similarity search

### Optimization Tips
- Increase workers for higher concurrency
- Enable result caching for repeated queries
- Use batch processing for guideline updates
- Monitor memory usage and adjust accordingly

See: [DEPLOYMENT_GUIDE.md](DEPLOYMENT.md#monitoring--maintenance)

---

## 🧪 Testing Guide

### Test Layers

| Test Suite | OpenAI Calls | Cost | Purpose |
|------------|--------------|------|---------|
| Layer 1 (Infrastructure) | 0 | $0.00 | Docker, DB, Models |
| Layer 2 (Application) | 0 | $0.00 | PHI, RAG, Django |
| Layer 3 (Integration) | 1 | $0.01 | Full API test |
| **Minimal Suite** | 0 | $0.00 | Quick validation |
| **Full Suite (run_tests.sh)** | 1 | $0.01 | All layers |
| **Comprehensive (test_full_system.py)** | 13 | $0.13 | All scenarios |

### Running Tests

```bash
# Minimal (recommended for quick checks)
./run_tests.sh minimal

# Full test suite (recommended before deployment)
./run_tests.sh all

# Comprehensive (for thorough validation)
python test_full_system.py
```

See: [DEVELOPMENT_GUIDE.md](DEVELOPMENT.md#testing)

---

## 🆘 Getting Help

### Documentation Not Clear?
1. Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
2. Search for error messages in documentation
3. Check Docker logs: `docker logs inteam-ai-django`

### Found a Bug?
1. Check if it's a known issue in [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Reproduce locally if possible
3. Report with logs and steps to reproduce

### Need a New Feature?
1. Review [DEVELOPMENT_GUIDE.md](DEVELOPMENT.md) for code structure
2. Write tests first (TDD approach)
3. Submit PR with documentation updates

---

## 📝 Documentation Maintenance

### When to Update Docs
- ✅ Adding new features
- ✅ Changing deployment process
- ✅ Fixing bugs that others might encounter
- ✅ Improving performance or security
- ✅ Updating dependencies

### Documentation Standards
- **Clear headings** with descriptive titles
- **Code examples** for all commands
- **Diagrams** for complex architectures (ASCII art)
- **Cross-references** to related documentation
- **Version information** at bottom of each file

---

## 🔗 External Resources

- **Django Documentation**: https://docs.djangoproject.com/
- **Docker Documentation**: https://docs.docker.com/
- **PostgreSQL + pgvector**: https://github.com/pgvector/pgvector
- **OpenAI API**: https://platform.openai.com/docs
- **Spacy NLP**: https://spacy.io/
- **Sentence Transformers**: https://www.sbert.net/

---

## 📄 License & Support

- **License**: Proprietary (InTEAM Health)
- **Repository**: https://github.com/md-ryhan-uddin/inteam-ai-service
- **Container Registry**: https://ghcr.io/md-ryhan-uddin/inteam-ai-service

---

**Documentation Version**: 2.0
**Last Updated**: 2025-11-13
**Covers**: CI/CD deployment, GHCR integration, automated testing
