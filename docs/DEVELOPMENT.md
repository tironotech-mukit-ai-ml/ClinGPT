# InTEAM AI Service - Development Guide

Complete guide for local development setup, testing, and workflows.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Environment Setup](#local-environment-setup)
3. [Running the Development Server](#running-the-development-server)
4. [Testing](#testing)
5. [Code Structure](#code-structure)
6. [Local vs Production Differences](#local-vs-production-differences)
7. [Adding New Features](#adding-new-features)
8. [Common Development Tasks](#common-development-tasks)

---

## Prerequisites

### Required Software

- **Python 3.11+** (for local development)
- **Docker 20.10+** (for containerized development)
- **Docker Compose 2.0+**
- **Git**
- **curl** (for testing API endpoints)

### Required API Keys

- **OpenAI API Key** - Get from https://platform.openai.com/api-keys
  - Minimum $5 credit recommended
  - Used for GPT-4 Turbo integration

---

## Local Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/md-ryhan-uddin/inteam-ai-service.git
cd inteam-ai-service
```

### 2. Create Virtual Environment (Optional - for local Python development)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 3. Create Environment File

Create `.env` file in project root:

```bash
# Django Configuration
DEBUG=True
SECRET_KEY=local-dev-secret-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1

# OpenAI Configuration
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_TIMEOUT=60

# Database Configuration (SQLite for local dev)
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# Redis Configuration (optional for local dev)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Guardrails Configuration
GUARDRAILS_ENABLED=True
GUARDRAILS_LOG_PHI_DETECTIONS=True
SPACY_MODEL=en_core_web_sm

# RAG Configuration
RAG_ENABLED=True
RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_EMBEDDING_DIMENSION=384
RAG_TOP_K_RESULTS=5
RAG_SIMILARITY_THRESHOLD=0.5
```

### 4. Install Spacy Model

```bash
python scripts/install_spacy.py
# or manually:
python -m spacy download en_core_web_sm
```

### 5. Run Database Migrations

```bash
python manage.py migrate
```

### 6. Populate Clinical Guidelines

```bash
python manage.py populate_guidelines
```

This will load clinical guidelines into the database for the RAG system.

---

## Running the Development Server

### Option 1: Docker (Recommended)

```bash
# Start all services (Django, PostgreSQL, Redis)
docker compose -f docker-compose.production.yml up -d

# View logs
docker logs -f inteam-ai-django

# Access Django shell
docker exec -it inteam-ai-django python manage.py shell

# Run migrations inside container
docker exec inteam-ai-django python manage.py migrate
```

**Access the API**: http://localhost:8001

### Option 2: Local Python (Development Only)

```bash
# Activate virtual environment
source venv/bin/activate

# Run development server
python manage.py runserver 8001
```

**Access the API**: http://localhost:8001

---

## Testing

### 3-Layer Testing Architecture

The project uses a layered testing approach to minimize OpenAI API costs during development:

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Infrastructure Tests (No OpenAI Cost)              │
│ ├─ Docker containers running                                │
│ ├─ Database connectivity                                    │
│ ├─ Health endpoint responding                               │
│ └─ Django models functional                                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Application Tests (No OpenAI Cost)                 │
│ ├─ PHI Guardrail (Presidio) detection                       │
│ ├─ RAG Service retrieval (pgvector)                         │
│ ├─ Clinical guidelines database                             │
│ └─ Unit tests for core logic                                │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Integration Tests (1 OpenAI call, ~$0.01)          │
│ ├─ Full API endpoint test                                   │
│ ├─ End-to-end clinical analysis                             │
│ └─ OpenAI GPT-4 integration                                 │
└─────────────────────────────────────────────────────────────┘
```

### Quick Testing Commands

```bash
# Minimal validation (no OpenAI cost, ~10 seconds)
./run_tests.sh minimal

# Full test suite (1 OpenAI call, ~$0.01, ~30 seconds)
./run_tests.sh all

# Individual layers
./run_tests.sh layer1  # Infrastructure only
./run_tests.sh layer2  # Application logic only
./run_tests.sh layer3  # Integration with OpenAI

# Comprehensive test suite (13 OpenAI calls, ~$0.13, ~2 minutes)
python test_full_system.py
```

### Test Commands Use Docker Exec

All test scripts use `docker exec` (NOT `docker-compose exec`):

```bash
# Correct: docker exec
docker exec inteam-ai-django python manage.py test

# Incorrect: docker-compose exec (deprecated)
docker-compose exec django python manage.py test
```

### Running Tests Manually

```bash
# Run Django unit tests inside container
docker exec inteam-ai-django python manage.py test

# Run specific test module
docker exec inteam-ai-django python manage.py test apps.clin_gpt.tests.test_guardrails

# Run with coverage
docker exec inteam-ai-django python -m pytest --cov=apps.clin_gpt

# Test PHI detection directly
docker exec inteam-ai-django python -c "
from apps.clin_gpt.services.phi_guardrail import get_phi_guardrail
g = get_phi_guardrail()
text, detections = g.redact_phi('Patient John Doe called at 555-1234')
print(f'Redacted: {text}')
print(f'Detected: {len(detections)} PHI entities')
"

# Test RAG retrieval
docker exec inteam-ai-django python -c "
from apps.clin_gpt.services.rag_service import get_rag_service
rag = get_rag_service()
results = rag.retrieve_relevant_guidelines({'symptoms': 'chest pain'})
print(f'Found {len(results)} relevant guidelines')
"
```

---

## Code Structure

```
inteam-ai-service/
├── apps/
│   ├── clin_gpt/              # Clinical GPT application
│   │   ├── models.py          # ClinicalGuideline model
│   │   ├── views.py           # API endpoints
│   │   ├── services/
│   │   │   ├── phi_guardrail.py    # PHI detection (Presidio)
│   │   │   ├── rag_service.py      # RAG with pgvector
│   │   │   └── openai_service.py   # OpenAI integration
│   │   ├── middleware.py      # Performance monitoring
│   │   └── tests/             # Unit tests
│   └── core/                  # Core application (health checks)
├── config/
│   ├── settings.py            # Django settings
│   ├── urls.py                # URL routing
│   └── wsgi.py                # WSGI entry point
├── scripts/
│   ├── install_spacy.py       # Spacy model installer
│   └── init_pgvector.sql      # pgvector setup
├── test_scripts/              # Test layer modules
│   ├── test_layer1_infrastructure.sh
│   ├── test_layer2_application.sh
│   └── test_layer3_integration.sh
├── docs/                      # Documentation
├── docker-compose.production.yml
├── Dockerfile.production
├── run_tests.sh               # Test runner script
├── requirements.txt
└── manage.py
```

---

## Local vs Production Differences

### Development Environment (Local)

```
Database:   SQLite (db.sqlite3)
Redis:      Optional (can use LocMemCache)
Docker:     Optional (can run Python directly)
Debug:      DEBUG=True
Workers:    1 (runserver)
Migrations: Manual (python manage.py migrate)
Static:     Served by Django dev server
```

### Production Environment (Server)

```
Database:   PostgreSQL + pgvector (vector similarity)
Redis:      Required (cache + Celery)
Docker:     Required (containerized deployment)
Debug:      DEBUG=False
Workers:    3 Gunicorn workers + 2 threads each
Migrations: Automatic (in docker run command)
Static:     Collected to staticfiles volume
```

### Key Configuration Differences

| Setting | Local | Production |
|---------|-------|------------|
| Database | SQLite | PostgreSQL + pgvector |
| Server | Django runserver | Gunicorn (3 workers) |
| Container Network | Default bridge | `django-app1_django_ai_network` |
| Port Binding | 127.0.0.1:8001 | 127.0.0.1:8001 (localhost-only) |
| Image Source | Built locally | GHCR (ghcr.io) |
| Deployment | Manual start | CI/CD automated |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   CLIENT REQUEST                            │
│        POST /api/v1/clin-gpt/analyze/                       │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              DJANGO AI SERVICE (Port 8001)                  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. API View (apps/clin_gpt/views.py)                 │   │
│  │    - Receives patient data                           │   │
│  │    - Validates request                               │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 2. PHI Guardrail (Presidio Singleton)                │   │
│  │    - Detects PHI (names, phones, locations, etc.)    │   │
│  │    - Redacts sensitive info → [NAME], [PHONE]        │   │
│  │    - Logs detections (if enabled)                    │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 3. RAG Service (Sentence Transformers Singleton)     │   │
│  │    - Generates query embedding                       │   │
│  │    - Searches pgvector for similar guidelines        │   │
│  │    - Returns top 5 relevant guidelines               │   │
│  │    - Threshold: similarity > 0.5                     │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 4. OpenAI Service                                    │   │
│  │    - Builds prompt with clinical guidelines          │   │
│  │    - Calls GPT-4 Turbo API                           │   │
│  │    - Returns clinical recommendations                │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 5. Output Guardrail                                  │   │
│  │    - Scans AI response for PHI leaks                 │   │
│  │    - Redacts any leaked PHI                          │   │
│  │    - Logs warnings if leaks detected                 │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     ↓                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 6. Return Response                                   │   │
│  │    - Clinical analysis                               │   │
│  │    - Evidence-based recommendations                  │   │
│  │    - Referenced guidelines                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  PostgreSQL +   │  │  Redis Cache/   │  │  OpenAI API     │
│  pgvector       │  │  Celery         │  │  (External)     │
│  Port: 5433     │  │  Port: 6379     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Adding New Features

### 1. Add New Clinical Guideline Categories

```bash
# Add guidelines via management command
docker exec inteam-ai-django python manage.py shell

from apps.clin_gpt.models import ClinicalGuideline
from apps.clin_gpt.services.rag_service import get_rag_service

# Create new guideline
guideline = ClinicalGuideline.objects.create(
    title="New Clinical Protocol",
    content="Detailed clinical guideline content...",
    source="Medical Society Name",
    category="cardiology",
    year=2024,
    url="https://example.com/guideline"
)

# Generate and save embedding
rag = get_rag_service()
embedding = rag.generate_embedding(guideline.content)
guideline.embedding = embedding
guideline.save()
```

### 2. Add New PHI Entity Types

Edit `config/settings.py`:

```python
GUARDRAILS_REDACTION_ENTITIES = [
    'PERSON', 'PHONE_NUMBER', 'EMAIL_ADDRESS', 'LOCATION',
    'DATE_TIME', 'US_SSN', 'MEDICAL_LICENSE', 'US_DRIVER_LICENSE',
    'IP_ADDRESS', 'IBAN_CODE', 'CREDIT_CARD', 'URL',
    'YOUR_NEW_ENTITY_TYPE',  # Add custom entity
]
```

### 3. Modify OpenAI Prompt

Edit `apps/clin_gpt/services/openai_service.py`:

```python
def build_prompt(self, patient_data, guidelines):
    # Customize system and user prompts
    system_prompt = "You are a clinical decision support assistant..."
    user_prompt = f"Analyze this patient: {patient_data}..."
    return system_prompt, user_prompt
```

### 4. Add New API Endpoints

1. Define URL in `config/urls.py`
2. Create view in `apps/clin_gpt/views.py`
3. Add serializers if needed
4. Write tests in `apps/clin_gpt/tests/`

---

## Common Development Tasks

### Database Operations

```bash
# Create migration after model changes
docker exec inteam-ai-django python manage.py makemigrations

# Apply migrations
docker exec inteam-ai-django python manage.py migrate

# Access database shell
docker exec inteam-ai-django python manage.py dbshell

# Create superuser
docker exec -it inteam-ai-django python manage.py createsuperuser

# Check guideline count
docker exec inteam-ai-django python -c "
from apps.clin_gpt.models import ClinicalGuideline
print(f'Total guidelines: {ClinicalGuideline.objects.count()}')
"
```

### Debugging

```bash
# View Django logs
docker logs -f inteam-ai-django

# View last 100 lines
docker logs --tail 100 inteam-ai-django

# Access Django shell for debugging
docker exec -it inteam-ai-django python manage.py shell

# Test API endpoint with curl
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "patient_data": {
      "age": 45,
      "gender": "male",
      "symptoms": "chest pain, shortness of breath",
      "blood_pressure_systolic": 150,
      "blood_pressure_diastolic": 95,
      "heart_rate": 110
    }
  }'
```

### Performance Testing

```bash
# Monitor container resources
docker stats inteam-ai-django

# Check API response time
time curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -d '{"patient_data": {"symptoms": "test"}}'

# View middleware performance logs
docker logs inteam-ai-django | grep "Request completed"
```

### Code Quality

```bash
# Run linter
flake8 apps/ config/ --max-line-length=127

# Format code with black
black apps/ config/

# Check for security issues
bandit -r apps/ config/
```

---

## Environment Variables Reference

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `SECRET_KEY` | Django secret key | Random string |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | False | Enable debug mode |
| `ALLOWED_HOSTS` | localhost | Comma-separated hosts |
| `OPENAI_MODEL` | gpt-4-turbo-preview | OpenAI model |
| `OPENAI_TIMEOUT` | 30 | Request timeout (seconds) |
| `RAG_ENABLED` | True | Enable RAG system |
| `RAG_TOP_K_RESULTS` | 5 | Number of guidelines to retrieve |
| `RAG_SIMILARITY_THRESHOLD` | 0.5 | Minimum similarity score |
| `GUARDRAILS_ENABLED` | True | Enable PHI detection |
| `SPACY_MODEL` | en_core_web_sm | Spacy NER model |

---

## Troubleshooting

### Issue: Container not starting

```bash
# Check logs for errors
docker logs inteam-ai-django

# Verify .env file exists
ls -la .env.production

# Restart container
docker restart inteam-ai-django
```

### Issue: Database connection failed

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test database connection
docker exec inteam-ai-django python manage.py check --database default
```

### Issue: Tests failing

```bash
# Ensure .env file exists (tests need OpenAI key)
cat .env

# Run minimal tests first
./run_tests.sh minimal

# Check specific layer
./run_tests.sh layer1  # Infrastructure
./run_tests.sh layer2  # Application
```

### Issue: OpenAI API errors

```bash
# Verify API key is set
docker exec inteam-ai-django python -c "import os; print(os.getenv('OPENAI_API_KEY')[:10])"

# Check OpenAI account has credits
# Visit: https://platform.openai.com/account/billing
```

---

## Best Practices

1. **Always run minimal tests before committing**: `./run_tests.sh minimal`
2. **Use docker exec instead of docker-compose exec**: More reliable
3. **Keep .env files secure**: Never commit to Git
4. **Test PHI detection**: Verify sensitive data is redacted
5. **Monitor OpenAI costs**: Use layer 1 & 2 tests for development
6. **Update clinical guidelines regularly**: Keep knowledge base current
7. **Check logs for PHI leaks**: Review output guardrail warnings

---

## Resources

- **Django Documentation**: https://docs.djangoproject.com/
- **OpenAI API**: https://platform.openai.com/docs
- **Presidio (PHI Detection)**: https://microsoft.github.io/presidio/
- **Sentence Transformers**: https://www.sbert.net/
- **pgvector**: https://github.com/pgvector/pgvector
- **Docker Documentation**: https://docs.docker.com/

---

**Last Updated**: 2025-11-13
**Version**: 2.0
**Covers**: 3-layer testing, docker exec commands, singleton patterns, local vs production
