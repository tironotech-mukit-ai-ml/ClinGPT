#!/bin/bash

###############################################################################
# Layer 2: Application Tests
# Tests: Django models, Spacy, Transformers, PHI detection, RAG, pgvector
# Cost: $0.00 (no OpenAI calls)
###############################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DJANGO_CONTAINER="inteam-ai-django"
POSTGRES_CONTAINER="inteam-ai-postgres"

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Main test function
run_layer2_application() {
    local FAILED=0

    # Test 1: Database models
    print_info "Testing Django database models..."
    if docker exec $DJANGO_CONTAINER python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.clin_gpt.models import ClinicalGuideline, PHIDetectionLog
count = ClinicalGuideline.objects.count()
assert count >= 20, f'Expected >= 20 guidelines, got {count}'
print(f'Found {count} clinical guidelines')
" 2>/dev/null; then
        print_success "Django models working"
    else
        print_error "Django models test failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 2: Spacy model
    print_info "Testing Spacy NLP model..."
    if docker exec $DJANGO_CONTAINER python -c "
import spacy
# Try lg model first (preferred), then sm model
try:
    nlp = spacy.load('en_core_web_lg')
    model_name = 'en_core_web_lg'
except:
    nlp = spacy.load('en_core_web_sm')
    model_name = 'en_core_web_sm'
doc = nlp('John Smith works at ABC Corp')
assert len(doc.ents) > 0, 'No entities detected'
print(f'Spacy model {model_name} loaded, detected {len(doc.ents)} entities')
" 2>/dev/null; then
        print_success "Spacy model loaded and working"
    else
        print_error "Spacy model test failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 3: Sentence Transformers
    print_info "Testing Sentence Transformers model..."
    if docker exec $DJANGO_CONTAINER python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
embedding = model.encode('test query')
assert len(embedding) == 384, f'Expected 384-dim embedding, got {len(embedding)}'
print(f'Sentence Transformers working, embedding dim: {len(embedding)}')
" 2>/dev/null; then
        print_success "Sentence Transformers model working"
    else
        print_error "Sentence Transformers test failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 4: PHI Detection
    print_info "Testing PHI detection system..."
    if docker exec $DJANGO_CONTAINER python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.clin_gpt.services.phi_guardrail import PHIGuardrail
guardrail = PHIGuardrail()
test_text = 'Patient John Smith, phone: 555-123-4567, SSN: 123-45-6789'
redacted, detections = guardrail.redact_phi(test_text)
assert len(detections) > 0, 'No PHI detected in test string'
print(f'PHI detection working, found {len(detections)} PHI entities')
" 2>/dev/null; then
        print_success "PHI detection working"
    else
        print_error "PHI detection test failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 5: RAG System
    print_info "Testing RAG retrieval system..."
    if docker exec $DJANGO_CONTAINER python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.clin_gpt.services.rag_service import get_rag_service
rag = get_rag_service()
assert rag.enabled, 'RAG service not enabled'
assert rag.embedding_model is not None, 'Embedding model not loaded'
# Test with patient data dictionary
patient_data = {
    'symptoms': 'chest pain hypertension',
    'medical_history': 'hypertension',
    'age': 65,
    'gender': 'Male'
}
results = rag.retrieve_relevant_guidelines(patient_data, top_k=5)
assert len(results) > 0, 'RAG search returned no results'
print(f'RAG system working, retrieved {len(results)} guidelines')
" 2>/dev/null; then
        print_success "RAG system working"
    else
        print_error "RAG system test failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 6: pgvector extension
    print_info "Testing pgvector extension..."
    if docker exec $POSTGRES_CONTAINER psql -U ryhan -d inteam_ai -c "SELECT extversion FROM pg_extension WHERE extname='vector';" 2>/dev/null | grep -q "[0-9]"; then
        print_success "pgvector extension enabled"
    else
        print_error "pgvector extension test failed"
        FAILED=$((FAILED + 1))
    fi

    echo ""
    if [ $FAILED -eq 0 ]; then
        print_success "✅ Layer 2: All application tests passed"
        return 0
    else
        print_error "❌ Layer 2: $FAILED application test(s) failed"
        return 1
    fi
}

# Run if called directly
if [ "${BASH_SOURCE[0]}" -ef "$0" ]; then
    run_layer2_application
fi
