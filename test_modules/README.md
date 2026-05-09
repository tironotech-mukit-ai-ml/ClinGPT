# test_modules - Python Testing Suite

## Overview

Modular Python test suite for **comprehensive testing** of all scenarios in InTEAM AI Service.

## Purpose

Thorough validation of all features, edge cases, and conditions with **13 OpenAI API calls** (~$0.13).

## Architecture

### Test Orchestration Flow

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
```

### Module Architecture

```
┌─────────────────────────────────────────────────────────────┐
│          test_modules/ - COMPREHENSIVE TESTING               │
│                   (Python Modules)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_infrastructure.py                            │    │
│  │  Infrastructure Tests ($0.00)                      │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_docker_services()                          │    │
│  │  • test_spacy_model()                              │    │
│  │  • test_database_connection()                      │    │
│  │  • test_database_data()                            │    │
│  │  ─────────────────────────────────────────         │    │
│  │  4 tests, 0 OpenAI calls                           │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_api_basic.py                                 │    │
│  │  Basic API Tests ($0.00)                           │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_health_endpoint()                          │    │
│  │  ─────────────────────────────────────────         │    │
│  │  1 test, 0 OpenAI calls                            │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_phi_detection.py                             │    │
│  │  PHI Detection Tests ($0.04)                       │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_phi_name_detection()          (1 call)     │    │
│  │  • test_phi_contact_detection()       (1 call)     │    │
│  │  • test_phi_dates_detection()         (1 call)     │    │
│  │  • test_phi_output_sanitization()     (1 call)     │    │
│  │  ─────────────────────────────────────────         │    │
│  │  4 tests, 4 OpenAI calls                           │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_rag_system.py                                │    │
│  │  RAG System Tests ($0.03)                          │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_rag_hypertension_guidelines() (1 call)     │    │
│  │  • test_rag_diabetes_guidelines()     (1 call)     │    │
│  │  • test_rag_no_match()                (1 call)     │    │
│  │  ─────────────────────────────────────────         │    │
│  │  3 tests, 3 OpenAI calls                           │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_clinical_scenarios.py                        │    │
│  │  Clinical Scenarios Tests ($0.04)                  │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_critical_hypertensive_crisis() (1 call)    │    │
│  │  • test_moderate_risk_scenario()      (1 call)     │    │
│  │  • test_low_risk_scenario()           (1 call)     │    │
│  │  • test_complex_multi_condition()     (1 call)     │    │
│  │  ─────────────────────────────────────────         │    │
│  │  4 tests, 4 OpenAI calls                           │    │
│  └────────────────────────────────────────────────────┘    │
│                         ▼                                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  test_validation.py                                │    │
│  │  Input Validation Tests ($0.00-$0.02)              │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  • test_invalid_blood_pressure()      (0-1 call)   │    │
│  │  • test_invalid_age()                 (0-1 call)   │    │
│  │  • test_missing_required_fields()     (0 calls)    │    │
│  │  ─────────────────────────────────────────         │    │
│  │  3 tests, 0-2 OpenAI calls                         │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  TOTAL: 19 tests, ~13 OpenAI calls, ~$0.13                  │
│  TIME: ~2-3 minutes                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                   test_full_system.py
                   (Main Orchestrator)
```

## File Structure

```
test_modules/
├── __init__.py
├── README.md (this file)
├── test_infrastructure.py     # Infrastructure tests (0 OpenAI calls)
├── test_api_basic.py          # Basic API tests (0 OpenAI calls)
├── test_phi_detection.py      # PHI detection (4 OpenAI calls)
├── test_rag_system.py         # RAG system (3 OpenAI calls)
├── test_clinical_scenarios.py # Clinical cases (4 OpenAI calls)
└── test_validation.py         # Input validation (0-2 OpenAI calls)
```

## Purpose

These modules are imported by `test_full_system.py` for **COMPREHENSIVE** testing of all scenarios (~13 OpenAI API calls).

## Usage

### Run ALL comprehensive tests (via orchestrator):
```bash
python test_full_system.py
# Cost: $0.13
# Time: 2-3 minutes
```

### Run individual test modules (NEW!):
```bash
# Infrastructure only (no cost)
python test_modules/test_infrastructure.py

# API basic tests (no cost)
python test_modules/test_api_basic.py

# PHI detection tests ($0.04)
python test_modules/test_phi_detection.py

# RAG system tests ($0.03)
python test_modules/test_rag_system.py

# Clinical scenarios ($0.04)
python test_modules/test_clinical_scenarios.py

# Validation tests ($0.00-$0.02)
python test_modules/test_validation.py
```

### Run specific test module programmatically:
```python
from test_modules.test_phi_detection import run_all_phi_tests
from test_modules.test_infrastructure import TestResults

results = TestResults()
all_passed, openai_calls = run_all_phi_tests("http://localhost:8001", results)
print(f"Passed: {results.passed}, Failed: {results.failed}")
print(f"OpenAI calls: {openai_calls} (~${openai_calls * 0.01:.2f})")
```

## Comparison with test_scripts/

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
│ test_scripts/ (Bash) │ 1 call     │ $0.01    │ Deployment  │
│ test_modules/ (this) │ 13 calls   │ $0.13    │ Development │
└──────────────────────┴────────────┴──────────┴─────────────┘
```

## Test Modules Details

### 1. test_infrastructure.py (0 cost)
- ✅ Docker containers status
- ✅ Spacy model installation
- ✅ Database connection
- ✅ Database data population

### 2. test_api_basic.py (0 cost)
- ✅ Health endpoint

### 3. test_phi_detection.py (4 calls = $0.04)
- ✅ Name detection (PERSON entities)
- ✅ Contact info (PHONE, EMAIL, LOCATION)
- ✅ Date detection
- ✅ Output sanitization

### 4. test_rag_system.py (3 calls = $0.03)
- ✅ Hypertension guidelines retrieval
- ✅ Diabetes guidelines retrieval
- ✅ No match scenario

### 5. test_clinical_scenarios.py (4 calls = $0.04)
- ✅ Critical hypertensive crisis
- ✅ Moderate risk scenario
- ✅ Low risk scenario
- ✅ Complex multi-condition

### 6. test_validation.py (0-2 calls = $0.00-$0.02)
- ✅ Invalid blood pressure
- ✅ Invalid age
- ✅ Missing required fields

## Output Example

```bash
$ python test_modules/test_phi_detection.py

================================================================================
  PHI DETECTION TESTS - STANDALONE MODE
================================================================================
  ⚠️  This will make 4 OpenAI API calls (~$0.04)

  Continue? (yes/no): yes

================================================================================
  PHI DETECTION TESTS (4 OpenAI Calls = ~$0.04)
================================================================================

[PHI Detection] Testing Name Detection...
  ✅ Name PHI detected: 1 entities

[PHI Detection] Testing Contact Info Detection...
  ✅ Contact PHI detected: 3 entities (PHONE_NUMBER, EMAIL_ADDRESS, LOCATION)

[PHI Detection] Testing Date Detection...
  ✅ Date PHI detected: 3 entities

[PHI Detection] Testing Output Sanitization...
  ✅ Output sanitized (no PHI leaked)

💰 PHI Tests: 4 OpenAI calls (~$0.04)

================================================================================
  RESULTS
================================================================================
✅ Passed:  4
❌ Failed:  0
⏭️  Skipped: 0
📊 Total:   4
💰 OpenAI calls: 4 (~$0.04)
================================================================================
```

## Troubleshooting

### Import errors
```bash
# Make sure you're in the project root
cd /path/to/inteam-ai-service

# Run with python
python test_modules/test_infrastructure.py
```

### Module not found
```bash
# Check PYTHONPATH
export PYTHONPATH=/path/to/inteam-ai-service:$PYTHONPATH
python test_modules/test_phi_detection.py
```

### API connection failed
```bash
# Check if Django is running
docker ps | grep inteam-ai-django

# Check BASE_URL in .env
cat .env | grep API_BASE_URL
```

### Tests taking too long
```bash
# Use individual modules instead of full suite
python test_modules/test_infrastructure.py  # Fast, no API calls
```

## Best Practices

### 1. Run infrastructure tests first
```bash
# Free and fast - verify system is up
python test_modules/test_infrastructure.py
```

### 2. Use full suite weekly
```bash
# Comprehensive validation
python test_full_system.py  # $0.13
```

### 3. Target specific areas when debugging
```bash
# Only test PHI if working on PHI features
python test_modules/test_phi_detection.py  # $0.04
```

### 4. Use test_scripts/ for deployments
```bash
# Much cheaper for routine checks
bash run_tests.sh all  # $0.01 vs $0.13
```

### 5. Monitor your OpenAI costs
```bash
# Track calls per module
# Infrastructure: 0 calls
# PHI Detection: 4 calls
# RAG System: 3 calls
# Clinical: 4 calls
# Validation: 0-2 calls
```

## Complete Command Reference

### Run Full Test Suite (All Modules)
```bash
cd /home/ryhan/Documents/ryhan/www/inteam-ai-service
python test_full_system.py
# Cost: $0.13, Time: 2-3 minutes
```

### Run Individual Modules

```bash
# Infrastructure tests (no cost)
python test_modules/test_infrastructure.py

# API basic tests (no cost)
python test_modules/test_api_basic.py

# PHI detection tests ($0.04)
python test_modules/test_phi_detection.py

# RAG system tests ($0.03)
python test_modules/test_rag_system.py

# Clinical scenarios ($0.04)
python test_modules/test_clinical_scenarios.py

# Validation tests ($0.00-$0.02)
python test_modules/test_validation.py
```

### Programmatic Usage

```python
# Import specific test module
from test_modules.test_phi_detection import run_all_phi_tests
from test_modules.test_infrastructure import TestResults

# Create results tracker
results = TestResults()

# Run tests
all_passed, openai_calls = run_all_phi_tests("http://localhost:8001", results)

# Check results
print(f"Passed: {results.passed}, Failed: {results.failed}")
print(f"OpenAI calls: {openai_calls} (~${openai_calls * 0.01:.2f})")
```

## Test Coverage Summary

| Module | Tests | OpenAI Calls | Cost | Can Run Standalone |
|--------|-------|--------------|------|-------------------|
| test_infrastructure.py | 4 | 0 | $0.00 | ✅ Yes |
| test_api_basic.py | 1 | 0 | $0.00 | ✅ Yes |
| test_phi_detection.py | 4 | 4 | $0.04 | ✅ Yes |
| test_rag_system.py | 3 | 3 | $0.03 | ✅ Yes |
| test_clinical_scenarios.py | 4 | 4 | $0.04 | ✅ Yes |
| test_validation.py | 3 | 0-2 | $0.00-$0.02 | ✅ Yes |
| **TOTAL** | **19** | **~13** | **~$0.13** | - |

## Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│              WHICH TEST SUITE SHOULD I USE?                  │
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

## Design Philosophy

**test_scripts/** = Minimal cost validation (1 OpenAI call)
- Designed for deployment verification
- Ensures system is working correctly
- Single API call to verify end-to-end flow
- Bash scripts for speed

**test_modules/** = Comprehensive testing (13 OpenAI calls)
- Designed for thorough testing
- Tests all possible scenarios and edge cases
- Multiple API calls to test every condition
- Python modules for flexibility

## When to Use

### ✅ Use test_modules/ when:
- 🧪 Developing new features
- 🔍 Testing all edge cases
- � Weekly comprehensive validation
- 🐛 Debugging specific issues
- 🎯 Testing individual components
- 🚀 CI/CD pipeline on pull requests

### ❌ Don't use test_modules/ for:
- Routine production deployments (too expensive)
- Quick health checks (too slow)
- Multiple daily runs (costs add up)

### 💡 Instead use:
- **test_scripts/** for deployments ($0.01)
- **Individual modules** for targeted testing

## Integration

### In test_full_system.py (orchestrator):
```python
from test_modules.test_infrastructure import run_all_infrastructure_tests
from test_modules.test_phi_detection import run_all_phi_tests
# ... imports all modules and runs sequentially
```

### In deploy.sh (deployment):
```bash
# Uses test_scripts/ for minimal cost
bash run_tests.sh all  # $0.01
```

### In CI/CD (future):
```yaml
# .github/workflows/test.yml
- name: Comprehensive tests
  run: python test_full_system.py  # $0.13
```

## Cost Analysis

### Single Test Run
```
Infrastructure:    $0.00
API Basic:         $0.00
PHI Detection:     $0.04
RAG System:        $0.03
Clinical:          $0.04
Validation:        $0.02
─────────────────────────
Total:             $0.13
```

### Monthly Estimates

**Scenario 1: Development Team**
```
20 deployments (test_scripts/)   × $0.01 = $0.20
4 weekly comprehensive           × $0.13 = $0.52
10 individual module tests       × $0.02 = $0.20 (avg)
                                  TOTAL: $0.92/month
```

**Scenario 2: Active CI/CD**
```
50 deployments (test_scripts/)   × $0.01 = $0.50
20 PR comprehensive tests        × $0.13 = $2.60
                                  TOTAL: $3.10/month
```

**Recommendation**: 
- Use test_scripts/ for ALL deployments
- Use test_modules/ selectively (weekly, PRs)
- Use individual modules for targeted testing
