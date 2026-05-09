#!/bin/bash

###############################################################################
# Layer 3: Integration Tests
# Tests: End-to-end API functionality with OpenAI
# Cost: ~$0.01 (1 OpenAI API call)
###############################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Main test function
run_layer3_integration() {
    local FAILED=0

    print_info "Running end-to-end API test..."
    print_warning "This will make 1 OpenAI API call (estimated cost: ~\$0.01)"

    # Make API request
    RESPONSE=$(curl -s -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
      -H "Content-Type: application/json" \
      -d '{
        "age": 65,
        "gender": "Male",
        "symptoms": "chest pain",
        "medical_history": "hypertension"
      }')

    # Check response structure
    if echo "$RESPONSE" | grep -q '"success":true'; then
        print_success "API returned success response"
    else
        print_error "API returned error response"
        echo "$RESPONSE"
        FAILED=$((FAILED + 1))
    fi

    if echo "$RESPONSE" | grep -q '"risk_level"'; then
        print_success "Response contains risk_level"
    else
        print_error "Response missing risk_level"
        FAILED=$((FAILED + 1))
    fi

    if echo "$RESPONSE" | grep -q '"guardrails"'; then
        print_success "Response contains guardrails data"
    else
        print_error "Response missing guardrails"
        FAILED=$((FAILED + 1))
    fi

    echo ""
    if [ $FAILED -eq 0 ]; then
        print_success "✅ Layer 3: Integration test passed"
        return 0
    else
        print_error "❌ Layer 3: Integration test failed"
        return 1
    fi
}

# Run if called directly
if [ "${BASH_SOURCE[0]}" -ef "$0" ]; then
    run_layer3_integration
fi
