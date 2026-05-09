#!/bin/bash

###############################################################################
# Layer 1: Infrastructure Tests
# Tests: Docker services, health endpoints, database/redis connectivity
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
REDIS_CONTAINER="inteam-ai-redis"

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Main test function
run_layer1_infrastructure() {
    local FAILED=0

    # Test 1: Docker containers running
    print_info "Testing Docker services..."

    if docker ps | grep -q $DJANGO_CONTAINER; then
        print_success "Django container running"
    else
        print_error "Django container not running"
        FAILED=$((FAILED + 1))
    fi

    if docker ps | grep -q $POSTGRES_CONTAINER; then
        print_success "PostgreSQL container running"
    else
        print_error "PostgreSQL container not running"
        FAILED=$((FAILED + 1))
    fi

    if docker ps | grep -q $REDIS_CONTAINER; then
        print_success "Redis container running"
    else
        print_error "Redis container not running"
        FAILED=$((FAILED + 1))
    fi

    # Test 2: Health endpoint
    print_info "Testing health endpoint..."
    if curl -sf http://localhost:8001/health/ > /dev/null 2>&1; then
        print_success "Health endpoint responding (HTTP 200)"
    else
        print_error "Health endpoint failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 3: Database connectivity
    print_info "Testing database connectivity..."
    if docker exec $POSTGRES_CONTAINER pg_isready -U ryhan -d inteam_ai > /dev/null 2>&1; then
        print_success "PostgreSQL accepting connections"
    else
        print_error "PostgreSQL connection failed"
        FAILED=$((FAILED + 1))
    fi

    # Test 4: Redis connectivity
    print_info "Testing Redis connectivity..."
    if docker exec $REDIS_CONTAINER redis-cli ping 2>/dev/null | grep -q PONG; then
        print_success "Redis responding to ping"
    else
        print_error "Redis connection failed"
        FAILED=$((FAILED + 1))
    fi

    echo ""
    if [ $FAILED -eq 0 ]; then
        print_success "✅ Layer 1: All infrastructure tests passed"
        return 0
    else
        print_error "❌ Layer 1: $FAILED infrastructure test(s) failed"
        return 1
    fi
}

# Run if called directly
if [ "${BASH_SOURCE[0]}" -ef "$0" ]; then
    run_layer1_infrastructure
fi
