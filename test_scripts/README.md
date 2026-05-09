# test_scripts - Bash Testing Suite

## Overview

Bash-based testing suite for **minimal-cost deployment validation** of InTEAM AI Service.

## Purpose

Quick validation that the deployed system is working correctly with **only 1 OpenAI API call** (~$0.01).

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                  LAYERED TEST ARCHITECTURE                      │
└────────────────────────────────────────────────────────────────┘
                         deploy.sh
                             │
                             ▼
                       run_tests.sh (HOST)
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────────┐  ┌─────────────┐
    │  LAYER 1:    │  │    LAYER 2:      │  │  LAYER 3:   │
    │ Infra Tests  │  │   App Tests      │  │ Integration │
    │   (HOST)     │  │  (CONTAINER)     │  │ (HOST→API)  │
    └──────────────┘  └──────────────────┘  └─────────────┘
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────────┐  ┌─────────────┐
    │ docker ps    │  │  docker exec     │  │  curl API   │
    │ docker logs  │  │  python test_    │  │  endpoints  │
    │ container    │  │  application.py  │  │             │
    │ health       │  │                  │  │  POST /api  │
    │              │  │ ┌──────────────┐ │  │  GET /health│
    │ Network      │  │ │ Django tests │ │  │             │
    │ checks       │  │ │ Spacy import │ │  │ End-to-end  │
    │              │  │ │ DB query     │ │  │ workflows   │
    │ Volume       │  │ │ File check   │ │  │             │
    │ mounts       │  │ └──────────────┘ │  │             │
    └──────────────┘  └──────────────────┘  └─────────────┘
            │                │                │
            └────────────────┼────────────────┘
                             ▼
                    Aggregate Results
                             │
                             ▼
                      ✅ or ❌ Exit Code


Layer Details:
┌─────────────────────────────────────────────────────────────┐
│           test_scripts/ - DEPLOYMENT VALIDATION              │
│                    (Bash Scripts)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Layer 1: Infrastructure Tests ($0.00)             │    │
│  │  test_layer1_infrastructure.sh                     │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • Docker container status                         │    │
│  │    ├─ inteam-ai-django   (running?)               │    │
│  │    ├─ inteam-ai-postgres (running?)               │    │
│  │    └─ inteam-ai-redis    (running?)               │    │
│  │  • PostgreSQL connection test                      │    │
│  │  • Redis connectivity check                        │    │
│  │  • Database tables verification                    │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Layer 2: Application Tests ($0.00)                │    │
│  │  test_layer2_application.sh                        │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • Django app availability                         │    │
│  │  • Spacy model loaded (PHI detection)              │    │
│  │  • Sentence transformers (embeddings)              │    │
│  │  • Clinical guidelines count (≥20)                 │    │
│  │  • pgvector extension installed                    │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Layer 3: Integration Test ($0.01)                 │    │
│  │  test_layer3_integration.sh                        │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • End-to-end API call                             │    │
│  │    └─ POST /api/v1/clin-gpt/analyze/              │    │
│  │  • PHI detection verification                      │    │
│  │  • RAG system check                                │    │
│  │  • Response structure validation                   │    │
│  │  • 1 OpenAI API call (~$0.01)                      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  TOTAL COST: ~$0.01 per run                                 │
│  TOTAL TIME: ~30 seconds                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## File Structure

```
test_scripts/
├── test_layer1_infrastructure.sh   (93 lines)
├── test_layer2_application.sh      (152 lines)
└── test_layer3_integration.sh      (74 lines)
```

## Usage

### Run all layers (recommended for deployments)
```bash
bash run_tests.sh all
# Cost: $0.01
# Time: ~30 seconds
```

### Run minimal tests only (no OpenAI cost)
```bash
bash run_tests.sh minimal
# Cost: $0.00
# Time: ~15 seconds
```

### Run specific layers
```bash
# Infrastructure only
bash run_tests.sh layer1

# Infrastructure + Application
bash run_tests.sh layer2

# Full test (all layers)
bash run_tests.sh all
```

## Test Details

### Layer 1: Infrastructure ($0.00)
| Test | Command | Success Criteria |
|------|---------|-----------------|
| Docker services | `docker ps` | All 3 containers running |
| PostgreSQL | `pg_isready` | Connection accepted |
| Redis | `redis-cli ping` | PONG response |
| Database tables | `psql \dt` | Required tables exist |

### Layer 2: Application ($0.00)
| Test | Command | Success Criteria |
|------|---------|-----------------|
| Django health | `curl /health/` | HTTP 200 |
| Spacy model | `python -c "import spacy..."` | Model loads |
| Guidelines | `SELECT COUNT(*)` | ≥20 records |
| pgvector | `SELECT * FROM pg_extension` | Extension present |

### Layer 3: Integration ($0.01)
| Test | API Call | Success Criteria |
|------|----------|-----------------|
| API analysis | POST with patient data | success: true |
| PHI detection | Check guardrails | PHI entities detected |
| RAG system | Check sources | Guidelines retrieved |

## Integration

### In deploy.sh
```bash
step_9_run_tests() {
    print_header "Running Tests"
    
    read -p "Run tests? (yes/no): " run_tests
    if [[ "$run_tests" == "yes" ]]; then
        bash run_tests.sh all
    fi
}
```

### In CI/CD (future)
```yaml
- name: Quick validation
  run: bash run_tests.sh all
  cost: ~$0.01
```

## Cost Analysis

### Single Run
```
Layer 1: $0.00
Layer 2: $0.00
Layer 3: $0.01
─────────────
Total:   $0.01
```

### Monthly (100 deployments)
```
100 deployments × $0.01 = $1.00/month
```

## Comparison with test_modules/

| Feature | test_scripts/ (Bash) | test_modules/ (Python) |
|---------|---------------------|----------------------|
| **Language** | Bash | Python |
| **OpenAI Calls** | 1 | 13 |
| **Cost per run** | $0.01 | $0.13 |
| **Execution time** | ~30 seconds | ~2-3 minutes |
| **Test coverage** | Basic validation | All scenarios |
| **PHI tests** | 1 combined | 4 separate scenarios |
| **RAG tests** | 1 basic check | 3 different cases |
| **Clinical tests** | 1 critical case | 4 risk levels |
| **Validation tests** | None | 3 input checks |
| **Modularity** | 3 layer scripts | 6 test modules |
| **Primary use** | Deployment | Development/CI/CD |
| **Orchestrator** | run_tests.sh | test_full_system.py |
| **Integration** | deploy.sh | Future CI/CD |

### Quick Comparison

```
┌──────────────────────┬────────────┬──────────┬─────────────┐
│ Test Suite           │ OpenAI API │ Cost     │ Purpose     │
├──────────────────────┼────────────┼──────────┼─────────────┤
│ test_scripts/ (this) │ 1 call     │ $0.01    │ Deployment  │
│ test_modules/        │ 13 calls   │ $0.13    │ Development │
└──────────────────────┴────────────┴──────────┴─────────────┘
```

## When to Use

### ✅ Use test_scripts/ for:
- Production deployments
- Quick health checks
- Verifying system is operational
- Cost-sensitive testing
- Fast validation needs

### ❌ Don't use test_scripts/ for:
- Comprehensive testing (use test_modules/)
- Testing all edge cases
- PHI detection scenarios
- RAG system validation
- Clinical risk assessments

## Output Example

```
================================================================================
  LAYER 1: INFRASTRUCTURE TESTS
================================================================================
  ✅ Docker service: inteam-ai-django is running
  ✅ Docker service: inteam-ai-postgres is running
  ✅ Docker service: inteam-ai-redis is running
  ✅ PostgreSQL connection successful
  ✅ Redis connection successful
  ✅ Required database tables exist

================================================================================
  LAYER 2: APPLICATION TESTS
================================================================================
  ✅ Django health endpoint responding
  ✅ Spacy model en_core_web_lg loaded
  ✅ Clinical guidelines populated (23 records)
  ✅ pgvector extension installed

================================================================================
  LAYER 3: INTEGRATION TEST
================================================================================
  ✅ API endpoint responding
  ✅ PHI detection working (3 entities detected)
  ✅ RAG system enabled (2 guidelines retrieved)
  ✅ Response structure valid

================================================================================
  TEST SUMMARY
================================================================================
✅ All tests passed
💰 OpenAI API calls: 1 (~$0.01)
⏱️  Total time: 28 seconds
```

## Troubleshooting

### Docker services not running
```bash
docker-compose up -d
```

### PostgreSQL connection failed
```bash
docker exec inteam-ai-postgres pg_isready -U ryhan
```

### Layer 3 integration failed
```bash
# Check API logs
docker logs inteam-ai-django

# Test manually
curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
  -H "Content-Type: application/json" \
  -d '{"age":50,"symptoms":"test"}'
```

## Best Practices

1. **Always run before deployment**
   ```bash
   bash run_tests.sh all
   ```

2. **Use minimal for quick checks**
   ```bash
   bash run_tests.sh minimal  # Skip OpenAI call
   ```

3. **Integrate in deployment scripts**
   - Already integrated in `deploy.sh`
   - Prompts before running

4. **Monitor costs**
   - 1 call per run = $0.01
   - Budget: ~$1-2/month for deployments

## Complete Command Reference

### Local Machine Commands

```bash
# Navigate to project
cd /home/ryhan/Documents/ryhan/www/inteam-ai-service

# Quick health check (no cost)
./run_tests.sh minimal

# Full test suite (recommended for deployments)
./run_tests.sh all

# Individual layers
./run_tests.sh layer1    # Infrastructure tests
./run_tests.sh layer2    # Application tests
./run_tests.sh layer3    # Integration test with OpenAI

# Default (same as 'all')
./run_tests.sh

# Show help
./run_tests.sh help
```

### Server Commands

```bash
# Navigate to project
cd /srv/apps/django-app1

# Quick health check (no cost)
./run_tests.sh minimal

# Full test suite (recommended for deployments)
./run_tests.sh all

# Individual layers
./run_tests.sh layer1    # Infrastructure tests
./run_tests.sh layer2    # Application tests
./run_tests.sh layer3    # Integration test with OpenAI

# Default (same as 'all')
./run_tests.sh

# Show help
./run_tests.sh help
```

## Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│                    QUICK DECISION TREE                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Are you deploying to production?                           │
│  ├─ YES → Use test_scripts/ (bash run_tests.sh all)        │
│  │         Cost: $0.01, Time: 30s                           │
│  │                                                          │
│  └─ NO → Are you testing a new feature?                    │
│           ├─ YES → Use test_modules/ (python)               │
│           │         Cost: $0.13, Time: 2-3min              │
│           │                                                  │
│           └─ NO → Just checking if system works?            │
│                    └─ Use test_scripts/ (bash)              │
│                       Cost: $0.01, Time: 30s                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Monthly Cost Estimates

### Scenario 1: Small Team
```
20 deployments/month    × $0.01 = $0.20
4 weekly dev tests      × $0.13 = $0.52
5 PR validations        × $0.13 = $0.65
                        TOTAL: $1.37/month
```

### Scenario 2: Active Development
```
50 deployments/month    × $0.01 = $0.50
10 dev tests            × $0.13 = $1.30
20 PR validations       × $0.13 = $2.60
                        TOTAL: $4.40/month
```

### Scenario 3: Production Heavy
```
100 deployments/month   × $0.01 = $1.00
4 weekly validations    × $0.13 = $0.52
10 PR tests             × $0.13 = $1.30
                        TOTAL: $2.82/month
```

## Related Documentation

- [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) - Full deployment guide
- [test_modules/README.md](../test_modules/README.md) - Comprehensive Python tests
