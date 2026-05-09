# InTEAM AI Service

> **Production-grade Django REST API** providing **AI-powered clinical decision support** with PHI protection and evidence-based recommendations for the InTEAM medical EMR system.

## 📚 Documentation

**Complete documentation available in [docs/](docs/INDEX.md)**

| Guide | Description |
|-------|-------------|
| **[INDEX](docs/INDEX.md)** | 📖 Start here - Complete navigation |
| **[DEPLOYMENT_GUIDE](docs/DEPLOYMENT.md)** | 🚀 Production deployment with CI/CD |
| **[DEVELOPMENT_GUIDE](docs/DEVELOPMENT.md)** | 💻 Local development setup |
| **[DOCKER_GUIDE](docs/DOCKER.md)** | 🐳 Container management |
| **[CI-CD_GUIDE](docs/CI_CD.md)** | ⚙️ GitHub Actions pipeline |
| **[RAG_SYSTEM](docs/RAG_SYSTEM.md)** | 🔍 Clinical guidelines & vector search |
| **[GUARDRAILS](docs/GUARDRAILS.md)** | 🛡️ PHI protection & HIPAA compliance |
| **[TROUBLESHOOTING](docs/TROUBLESHOOTING.md)** | 🔧 Common issues & solutions |

## Overview

A **HIPAA-compliant** clinical analysis service that intelligently combines:

- **🛡️ PHI Guardrails**: Automatic detection and redaction of Protected Health Information using Microsoft Presidio
- **📚 RAG System**: Evidence-based recommendations from 60+ clinical guidelines (AHA, ACC, ADA, IDSA, KDIGO, WHO)
- **🧠 AI Analysis**: GPT-4 powered clinical insights with confidence scoring
- **🔍 Vector Search**: Semantic similarity using pgvector in PostgreSQL
- **⚡ Performance**: Singleton pattern, Redis caching, optimized for production

**Key Stats:**
- **18+ PHI entity types** detected (names, SSN, phone, dates, locations, medical IDs)
- **20 clinical guidelines** pre-loaded with vector embeddings
- **384-dimensional** semantic search vectors
- **3-stage** automated CI/CD pipeline with Docker deployment

## System Architecture

### Core Request Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Clinical Analysis Pipeline                       │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────┐
│   Laravel   │  1. POST /api/v1/clin-gpt/analyze/
┌─────────────┐  ───────────────────────────────┐
│  EMR System │                                 │
└─────────────┘                                 ▼
  │                            ┌─────────────────────────┐
  │                            │   Django REST API       │
  │                            │   (Port 8001)           │
  │                            └──────────┬──────────────┘
  │                                       │
  │    ┌──────────────────────────────────┼──────────────────────────────┐
  │    │                                   ▼                             │
  │    │        ┌──────────────────────────────────────────────┐         │
  │    │        │  OpenAI Service (Main Orchestrator)          │         │
  │    │        └──────────┬───────────────────────────┬───────┘         │
  │    │                   │                           │                 │
  │    │  ┌────────────────▼─────────────┐   ┌────────▼───────────────┐  │
  │    │  │  STEP 1: Input Guardrails    │   │  STEP 2: RAG Retrieval │  │
  │    │  │  ─────────────────────────── │   │  ───────────────────── │  │
  │    │  │  PHI Guardrail Service       │   │  RAG Service           │  │
  │    │  │  • Detect PHI entities       │   │  • Generate embedding  │  │
  │    │  │  • Redact sensitive data     │   │  • Vector similarity   │  │
  │    │  │  • Log detections            │   │  • Retrieve top-5      │  │
  │    │  │                              │   │                        │  │
  │    │  │  Technology:                 │   │  Technology:           │  │
  │    │  │  • Microsoft Presidio        │   │  • Sentence Transf.    │  │
  │    │  │  • Spacy NER (en_core_web_lg)│   │  • pgvector search     │  │
  │    │  └───────────────┬──────────────┘   └────────┬───────────────┘  │
  │    │                  │                            │                 │
  │    │                  └────────────┬───────────────┘                 │
  │    │                               ▼                                 │
  │    │                  ┌─────────────────────────┐                    │
  │    │                  │  STEP 3: Build Prompt   │                    │
  │    │                  │  • Safe patient data    │                    │
  │    │                  │  • Clinical guidelines  │                    │
  │    │                  │  • Context & history    │                    │
  │    │                  └────────────┬────────────┘                    │
  │    │                               ▼                                 │
  │    │                  ┌─────────────────────────┐                    │
  │    │                  │  STEP 4: OpenAI API     │                    │
  │    │                  │  • GPT-4 Turbo          │                    │
  │    │                  │  • Temp: 0.3            │                    │
  │    │                  │  • Max tokens: 1000     │                    │
  │    │                  │  • Timeout: 60s         │                    │
  │    │                  └────────────┬────────────┘                    │
  │    │                               ▼                                 │
  │    │                  ┌─────────────────────────┐                    │
  │    │                  │  STEP 5: Output Guard   │                    │
  │    │                  │  • Scan for PHI leaks   │                    │
  │    │                  │  • Audit logging        │                    │
  │    │                  │  • Return sanitized     │                    │
  │    │                  └────────────┬────────────┘                    │
  │    │                               ▼                                 │
  │    │                  ┌─────────────────────────┐                    │
  │    │                  │  STEP 6: Cache Result   │                    │
  │    │                  │  • 1-minute TTL         │                    │
  │    │                  │  • Redis storage        │                    │
  │    │                  └────────────┴────────────┘                    │
  │    └─────────────────────────────────────────────────────────────────┘
  │                                   │
  ▼                                   ▼
┌───────────────┐            ┌──────────────────────────────┐
│ MySQL Database│            │  Response JSON               │
│ (Laravel EMR) │            │  • summary                   │
└───────────────┘            │  • concerns                  │
                             │  • Recommendations           │
                             │  • Risk level                │
                             │  • Confidence                │
                             │  • Sources (with relevance)  │
                             │  • Guardrails statistics     │
                             │  • RAG enabled status        │
                             └──────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│                      Supporting Infrastructure                         │
└────────────────────────────────────────────────────────────────────────┘

        ┌─────────────────────┐              ┌─────────────────┐
        │  PostgreSQL 16      │              │   Redis 7       │
        │  + pgvector         │              │                 │
        │                     │              │                 │
        │  Models:            │              │  Usage:         │
        │  • ClinicalGuideline│              │  • Response     │
        │  • PHIDetectionLog  │              │    caching      │
        │                     │              │  • Session      │
        │  Port: 5433         │              │    management   │
        │  (localhost-only)   │              │                 │
        └─────────────────────┘              └─────────────────┘
```

### Production Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Internet (Port 80/443)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                ┌─────────────────────────┐
                │  Apache Web Server      │
                │  (80/443)               │
                │  server1.inteamhealth   │
                │                         │
                │  • SSL/TLS termination  │
                │  • Reverse proxy        │
                └────────────┬────────────┘
                             │
             ┌───────────────┴────────────────┐
             │                                │
             ▼                                ▼
    ┌─────────────────┐          ┌──────────────────────────┐
    │  Laravel EMR    │  HTTP    │  Django AI Service       │
    │  (Main App)     │◄────────►│  (Docker Container)      │
    │                 │  API     │                          │
    │  Port: 8000     │          │  Port: 8001              │
    │  • Patient mgmt │          │  • Clinical analysis     │
    │  • EHR features │          │  • PHI protection        │
    │  • User auth    │          │  • AI recommendations    │
    └────────┬────────┘          └────────┬─────────────────┘
             │                            │
             ▼                            │
    ┌─────────────────┐                   │
    │  MySQL Database │                   │
    │  (Remote)       │                   │
    │                 │                   │
    │  • Patient data │         ┌─────────┴───────┐
    │  • EMR records  │         │                 │
    └─────────────────┘         ▼                 ▼
                    ┌─────────────────┐  ┌─────────────┐
                    │  PostgreSQL 16  │  │  Redis 7    │
                    │  + pgvector     │  │             │
                    │  (Docker)       │  │  (Docker)   │
                    │                 │  │             │
                    │  Port: 5433     │  │  Port: 6379 │
                    │  (localhost)    │  │ (localhost) │
                    └─────────────────┘  └─────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     CI/CD Pipeline (GitHub Actions)              │
└──────────────────────────────────────────────────────────────────┘

    ┌─────────────┐
    │  Git Push   │
    │  to main    │
    └──────┬──────┘
           │
           ▼
┌─────────────────────┐
│  STAGE 1: TEST      │
│  ─────────────────  │
│  • Lint (flake8)    │
│  • Download Spacy   │
│  • Run migrations   │
│  • Populate data    │
│  • Integration tests│
└──────┬──────────────┘
       │ ✅ Pass
       ▼
┌─────────────────────────────┐
│  STAGE 2: BUILD & PUSH      │
│  ────────────────────────── │
│  • Build Docker image       |
│  • Push to ghcr.io          │
│  • Tag: latest, SHA, short  │
└──────┬──────────────────────┘
       │ ✅ Success
       ▼
┌─────────────────────────────┐
│  STAGE 3: DEPLOY            │
│  ────────────────────────── │
│  • SSH to production server │
│  • Pull image by SHA        │
│  • docker-compose up        │
│  • Health check (60s)       │
│  • Rollback on failure      │
└─────────────────────────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenAI API key

### Option 1: Automated Setup (Recommended)
```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env and add your OPENAI_API_KEY
nano .env

# 3. Run automated setup
make setup-docker
```

That's it! This will:
- Start all Docker services
- Install Spacy model for PHI detection
- Run database migrations
- Populate clinical guidelines

### Option 2: Step-by-Step Makefile
```bash
# 1. Setup environment file
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY

# 2. Complete setup
make setup-docker
```

### Option 3: Manual Setup
```bash
# 1. Setup environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 2. Start services
docker-compose up -d

# 3. Setup database
docker-compose exec -T django python manage.py migrate
docker-compose exec -T django python manage.py populate_guidelines
```

### Spacy Model Installation

The Spacy model is **automatically installed** during Docker build. If you need to reinstall it:

```bash
# Using Makefile (easiest)
make install-spacy

# Using Python script directly
python scripts/install_spacy.py

# Direct command
docker-compose exec -T -u root django python -m spacy download en_core_web_lg
docker-compose restart django
```

### 4. Test API
```bash
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -d '{
    "age": 65,
    "gender": "Male",
    "symptoms": "chest pain radiating to left arm",
    "medical_history": "hypertension"
  }'
```

## Services

### Development Environment

| Service | Port | Description | Technology |
|---------|------|-------------|------------|
| Django  | 8001 | REST API service | Python 3.11, Django 4.2, Gunicorn |
| PostgreSQL | 5433 | Database with pgvector | PostgreSQL 15 + pgvector extension |
| Redis | 6380 | Cache layer | Redis 7 Alpine |

### Production Environment

| Service | Port | Description | Technology |
|---------|------|-------------|------------|
| Django  | 8001 (localhost) | REST API service | Gunicorn: 3 workers × 2 threads |
| PostgreSQL | 5433 (localhost) | Optimized database | PostgreSQL 16 + pgvector, 256MB shared buffers |
| Redis | 6379 (localhost) | Persistent cache | Redis 7 with AOF + RDB |

**Note:** Production ports are bound to `127.0.0.1` (localhost-only) for security. Access via Apache reverse proxy.

## Key Features

### Guardrails (PHI Protection)
- Detects 18+ PHI entity types (names, SSN, phone, dates, locations, etc.)
- Automatic redaction before OpenAI
- Output scanning for PHI leaks
- Audit logging in database
- HIPAA compliance features

### RAG (Clinical Guidelines)
- 20 pre-loaded clinical guidelines
- Vector embeddings (384 dimensions)
- Semantic search using pgvector
- Evidence-based recommendations
- Sources: AHA, ACC, ADA, IDSA, KDIGO, etc.

### AI Analysis
- GPT-4 powered insights
- Risk level assessment
- Confidence scoring
- Token usage tracking
- Response caching

## API Endpoints

### Health Check
```bash
GET /health/
```

### Clinical Analysis
```bash
POST /api/v1/clin-gpt/analyze/
Content-Type: application/json

{
  "age": 65,
  "gender": "Male",
  "symptoms": "chest pain",
  "medical_history": "hypertension",
  "current_medications": "lisinopril",
  "allergies": "none"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "summary": "Clinical summary...",
    "concerns": ["Concern 1", "Concern 2"],
    "recommendations": ["Recommendation 1"],
    "risk_level": "high|medium|low",
    "confidence": "high|medium|low",
    "sources": [{"title": "...", "source": "AHA", "relevance": 0.85}],
    "guardrails": {
      "enabled": true,
      "input_phi_detected": 0,
      "output_phi_detected": 2,
      "phi_types_detected": ["DATE_TIME"]
    },
    "rag_enabled": true
  }
}
```

## Environment Variables

```bash
# Django
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo-preview

# Database (Docker)
POSTGRES_DB=inteam_ai
POSTGRES_USER=inteam_ai_user
POSTGRES_PASSWORD=secure-password

# Guardrails
GUARDRAILS_ENABLED=True
GUARDRAILS_LOG_PHI_DETECTIONS=True

# RAG (Retrieval-Augmented Generation)
RAG_ENABLED=True
RAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RAG_EMBEDDING_DIMENSION=384
RAG_TOP_K_RESULTS=5
RAG_SIMILARITY_THRESHOLD=0.3  # 0.3 = balanced, 0.5 = strict, 0.2 = permissive
```

**Note:** RAG uses a singleton pattern for optimal performance. The embedding model loads once on first request (~5 seconds) and is reused for all subsequent requests.

## Common Commands

### Using Makefile (Recommended)
```bash
# Setup
make setup-docker        # Complete setup for Docker
make install-spacy       # Install Spacy model

# Docker Operations
make up                  # Start services
make down                # Stop services
make restart             # Restart services
make rebuild             # Rebuild and restart (remember to reinstall Spacy!)
make logs                # View all logs
make logs-django         # View Django logs only

# Database
make migrate             # Run migrations
make populate            # Populate guidelines
make db-shell            # Open PostgreSQL shell
make db-status           # Show database status

# Testing
make test                # Run Django unit tests
make test-full           # Run comprehensive system tests (READ-ONLY, safe for production)
make test-api            # Test API endpoint
make health              # Check health endpoint

# Cleanup
make clean               # Stop and remove volumes
make clean-all           # Remove everything including images

# Help
make help                # Show all commands
```

### Using Docker Compose Directly
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f django

# Check status
docker-compose ps

# Restart service
docker-compose restart django

# Stop all
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
# ⚠️ After rebuild, reinstall Spacy: make install-spacy

# Run management commands
docker-compose exec -T django python manage.py <command>
```

## Project Structure

```
inteam-ai-service/
├── apps/
│   └── clin_gpt/
│       ├── models.py              # ClinicalGuideline, PHIDetectionLog
│       ├── views.py               # API endpoints
│       ├── serializers.py         # Request/response schemas
│       ├── services/
│       │   ├── openai_service.py  # Main orchestrator
│       │   ├── phi_guardrail.py   # PHI detection/redaction
│       │   └── rag_service.py     # Vector search
│       └── management/commands/
│           ├── populate_guidelines.py
│           └── setup_guardrails_rag.py
├── config/
│   ├── settings.py                # Django configuration
│   ├── urls.py                    # URL routing
│   └── wsgi.py                    # WSGI entry point
├── data/
│   └── sample_guidelines.json     # 20 clinical guidelines
├── docs/                          # Additional documentation
│   ├── DEPLOYMENT_GUIDE.md        # Deployment instructions
│   ├── DEVELOPMENT_GUIDE.md       # Local development setup
│   ├── DOCKER_GUIDE.md            # Docker configuration details
│   ├── CI-CD_GUIDE.md             # CI/CD pipeline guide
│   ├── RAG_SYSTEM.md              # RAG system and vector search
│   └── GUARDRAILS.md              # PHI protection and compliance
├── Dockerfile                     # Production image
├── docker-compose.yml             # Service orchestration
├── Makefile                       # Automation commands
├── requirements.txt               # Python dependencies
├── scripts/
│   └── install_spacy.py           # Spacy model installation
├── tests/
│   ├── test_api.py                # API endpoint tests
│   ├── test_guardrails.py         # PHI guardrails tests
│   └── test_rag.py                # RAG system tests
└── .env.example                   # Environment variable template
```

## Testing

### Comprehensive System Tests (`test_full_system.py`)

The test suite validates all system components and is **READ-ONLY** - safe for production databases.

**What it tests:**
- ✅ Docker services health (django, postgres, redis)
- ✅ Spacy model loading
- ✅ Database connectivity and data
- ✅ API endpoints (health, analysis)
- ✅ PHI detection and redaction
- ✅ RAG system (clinical guidelines)
- ✅ PHI logging to database
- ✅ Makefile commands

**What it does NOT do:**
- ❌ Delete any existing data
- ❌ Modify existing records
- ❌ Drop or truncate tables
- ❌ Change configuration

**What it DOES add:**
- ➕ Creates 4-5 new PHI detection log entries during testing
- ➕ Uses test patient data (not real PHI)

**Usage:**
```bash
# Run all tests (will prompt for confirmation)
make test-full

# Or run directly
python test_full_system.py

# In CI/CD (auto-proceeds without prompt)
CI=true python test_full_system.py
```

**Output:** Test results are printed to terminal with detailed status and summary.

## Documentation

- **[SERVER_SETUP.md](SERVER_SETUP.md)** - **New server setup guide** (start here for new deployments!)
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Production deployment with Laravel integration
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) - Local development setup
- [DOCKER.md](DOCKER.md) - Docker configuration details
- [CI-CD_GUIDE.md](CI-CD_GUIDE.md) - CI/CD pipeline and GitHub Actions
- [RAG.md](RAG.md) - RAG system and vector search
- [GUARDRAILS.md](GUARDRAILS.md) - PHI protection and compliance

## Troubleshooting

### API returns "Internal Server Error" or timeouts
**Cause**: Spacy model is missing

**Solution**:
```bash
# Easiest way
make install-spacy

# Or using Python script
python scripts/install_spacy.py

# Or direct command
docker-compose exec -T -u root django python -m spacy download en_core_web_lg
docker-compose restart django
```

### Services won't start
```bash
docker-compose logs
docker-compose down -v && docker-compose up -d
```

### Spacy model missing (PHI detection fails)
```bash
docker-compose exec -T -u root django python -m spacy download en_core_web_lg
docker-compose restart django
```

### Guidelines not returning
```bash
docker-compose exec -T django python manage.py populate_guidelines
```
