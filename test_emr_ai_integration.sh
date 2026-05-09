#!/bin/bash

# ==============================================================================
# InTEAM EMR + AI Service Integration Test Suite
# ==============================================================================
# This script tests the integration between Laravel EMR and Django AI Service
# Works on both local development and production server environments
# Created: November 25, 2025
# ==============================================================================

set -e

# ==============================================================================
# Helper Functions
# ==============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_test() {
    echo -e "\n${YELLOW}TEST $TESTS_RUN:${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_error() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "${BLUE}ℹ INFO:${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠ WARNING:${NC} $1"
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==============================================================================
# Environment Detection and Path Configuration
# ==============================================================================

# Detect environment (local vs server)
if [ -d "/srv/apps/" ]; then
    # Server environment
    ENVIRONMENT="server"
    DJANGO_APP_PATH="/srv/apps/django-app1"
    LARAVEL_APP_PATH="/srv/apps/laravel-app1/src"
    AI_SERVICE_URL="http://localhost:8001"
    EMR_SERVICE_URL="http://localhost:80"
    print_info "Running on SERVER environment"
else
    # Local development environment
    ENVIRONMENT="local"
    DJANGO_APP_PATH="/home/ryhan/Documents/ryhan/www/inteam-ai-service"
    LARAVEL_APP_PATH="/home/ryhan/Documents/ryhan/www/inteam-medical-emr"
    AI_SERVICE_URL="http://localhost:8001"
    EMR_SERVICE_URL="http://localhost:8005"
    print_info "Running on LOCAL environment"
fi

print_info "Django App Path: $DJANGO_APP_PATH"
print_info "Laravel App Path: $LARAVEL_APP_PATH"
print_info "AI Service URL: $AI_SERVICE_URL"
print_info "EMR Service URL: $EMR_SERVICE_URL"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# ==============================================================================
# Helper Functions
# ==============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_test() {
    echo -e "\n${YELLOW}TEST $TESTS_RUN:${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_error() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_info() {
    echo -e "${BLUE}ℹ INFO:${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠ WARNING:${NC} $1"
}

# ==============================================================================
# Test Functions
# ==============================================================================

test_ai_service_health() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "AI Service Health Check"
    
    response=$(curl -s -w "\n%{http_code}" "$AI_SERVICE_URL/health/")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        print_success "AI Service is healthy"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        return 0
    else
        print_error "AI Service health check failed (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

test_basic_clinical_analysis() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "Basic Clinical Analysis Endpoint"
    
    patient_data='{
        "age": 45,
        "gender": "Male",
        "heart_rate": 95,
        "spo2": 97,
        "blood_pressure_systolic": 140,
        "blood_pressure_diastolic": 90,
        "symptoms": "Mild chest discomfort"
    }'
    
    response=$(curl -s -w "\n%{http_code}" -X POST "$AI_SERVICE_URL/api/v1/clin-gpt/analyze/" \
        -H "Content-Type: application/json" \
        -d "$patient_data")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        success=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)
        
        if [ "$success" = "True" ]; then
            print_success "Clinical analysis successful"
            echo "$body" | python3 -m json.tool 2>/dev/null | head -30
            echo "... (truncated)"
            
            # Extract key metrics
            risk_level=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('risk_level', 'N/A'))" 2>/dev/null)
            rag_enabled=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('rag_enabled', False))" 2>/dev/null)
            guardrails_enabled=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('guardrails', {}).get('enabled', False))" 2>/dev/null)
            
            print_info "Risk Level: $risk_level"
            print_info "RAG Enabled: $rag_enabled"
            print_info "Guardrails Enabled: $guardrails_enabled"
            return 0
        else
            print_error "Analysis returned success=false"
            echo "$body"
            return 1
        fi
    else
        print_error "Clinical analysis failed (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

test_emr_analysis_endpoint() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "EMR Analysis Endpoint (Full EMR Data)"
    
    emr_data='{
        "patient_id": 123,
        "emr_id": 456,
        "age": 55,
        "gender": "Male",
        "cc": "Chest pain",
        "durationcc": "2 hours",
        "onset": "Sudden onset at rest",
        "location": "Central chest",
        "character": "Pressure-like",
        "severity": "7/10",
        "heart_rate": 105,
        "blood_pressure_systolic": 150,
        "blood_pressure_diastolic": 95,
        "spo2": 95,
        "respiration_rate": 20,
        "temperature": 98.6,
        "general": "Patient appears anxious",
        "cardiovascular": "Tachycardia",
        "respiratory": "Clear bilaterally"
    }'
    
    response=$(curl -s -w "\n%{http_code}" -X POST "$AI_SERVICE_URL/api/v1/clin-gpt/emr-analysis/" \
        -H "Content-Type: application/json" \
        -d "$emr_data")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "200" ]; then
        success=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)
        
        if [ "$success" = "True" ]; then
            print_success "EMR analysis successful"
            echo "$body" | python3 -m json.tool 2>/dev/null | head -40
            echo "... (truncated)"
            return 0
        else
            print_error "EMR analysis returned success=false"
            echo "$body"
            return 1
        fi
    elif [ "$http_code" = "404" ]; then
        print_warning "EMR endpoint not found - needs deployment update"
        print_info "The endpoint exists in code but not in deployed container"
        return 1
    else
        print_error "EMR analysis failed (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

test_laravel_ai_service_config() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "Laravel EMR AI Service Configuration"
    
    # Check if Laravel .env has the correct AI service URL
    env_file="$LARAVEL_APP_PATH/.env"
    if [ -f "$env_file" ]; then
        django_url=$(grep "^DJANGO_AI_URL=" "$env_file" | cut -d'=' -f2)
        django_timeout=$(grep "^DJANGO_AI_TIMEOUT=" "$env_file" | cut -d'=' -f2)
        
        if [ -n "$django_url" ]; then
            print_success "Laravel EMR configured with AI Service URL: $django_url"
            print_info "Timeout: ${django_timeout:-30} seconds"
            return 0
        else
            print_error "DJANGO_AI_URL not found in Laravel .env"
            return 1
        fi
    else
        print_error "Laravel .env file not found at $env_file"
        return 1
    fi
}

test_laravel_clin_gpt_service() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "Laravel ClinGptService Class"
    
    service_file="$LARAVEL_APP_PATH/app/Services/AI/ClinGptService.php"
    
    if [ -f "$service_file" ]; then
        print_success "ClinGptService.php exists"
        
        # Check for key methods
        if grep -q "function analyzePatient" "$service_file"; then
            print_info "✓ analyzePatient() method found"
        fi
        
        if grep -q "function healthCheck" "$service_file"; then
            print_info "✓ healthCheck() method found"
        fi
        
        if grep -q "DJANGO_AI_URL" "$service_file"; then
            print_info "✓ Uses DJANGO_AI_URL configuration"
        fi
        
        return 0
    else
        print_error "ClinGptService.php not found at $service_file"
        return 1
    fi
}

test_emr_blade_integration() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "EMR Blade Template AI Integration"
    
    blade_file="$LARAVEL_APP_PATH/resources/views/emr/show.blade.php"
    
    if [ -f "$blade_file" ]; then
        print_success "EMR show.blade.php exists"
        
        # Check for AI integration elements
        if grep -q "getAIInsights" "$blade_file"; then
            print_info "✓ AI Insights button found"
        fi
        
        if grep -q "aiServiceUrl" "$blade_file"; then
            print_info "✓ AI Service URL configuration found"
        fi
        
        if grep -q "/api/v1/clin-gpt/emr-analysis/" "$blade_file"; then
            print_info "✓ EMR analysis endpoint call found"
        fi
        
        return 0
    else
        print_error "EMR show.blade.php not found at $blade_file"
        return 1
    fi
}

test_docker_services() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "Docker Services Status"
    
    # Check Django container
    if docker ps | grep -q "inteam-ai-django"; then
        print_success "Django AI service container is running"
        
        # Check container health
        health=$(docker inspect --format='{{.State.Health.Status}}' inteam-ai-django 2>/dev/null)
        if [ "$health" = "healthy" ]; then
            print_info "Container health: $health"
        else
            print_warning "Container health: ${health:-unknown}"
        fi
    else
        print_error "Django AI service container not running"
        return 1
    fi
    
    # Check PostgreSQL
    if docker ps | grep -q "inteam-ai-postgres"; then
        print_info "✓ PostgreSQL container running"
    fi
    
    # Check Redis
    if docker ps | grep -q "inteam-ai-redis"; then
        print_info "✓ Redis container running"
    fi
    
    return 0
}

test_django_env_config() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "Django Environment Configuration"
    
    # Check for Django .env file
    django_env_file="$DJANGO_APP_PATH/.env"
    django_env_prod_file="$DJANGO_APP_PATH/.env.production"
    
    if [ -f "$django_env_file" ]; then
        print_success "Django .env file exists"
        
        # Check for critical environment variables
        if grep -q "OPENAI_API_KEY" "$django_env_file"; then
            print_info "✓ OPENAI_API_KEY configured"
        else
            print_error "OPENAI_API_KEY not found in Django .env"
            return 1
        fi
        
        if grep -q "POSTGRES_DB" "$django_env_file"; then
            print_info "✓ Database configuration found"
        else
            print_error "Database configuration not found in Django .env"
            return 1
        fi
        
        return 0
    elif [ -f "$django_env_prod_file" ]; then
        print_warning "Django uses .env.production instead of .env"
        print_info "This may cause issues if Django settings expect .env"
        print_info "Consider creating a symlink: ln -s .env.production .env"
        print_info "Or update Django settings to load .env.production"
        
        # Check the production file for critical variables
        if grep -q "OPENAI_API_KEY" "$django_env_prod_file"; then
            print_info "✓ OPENAI_API_KEY configured in .env.production"
        else
            print_error "OPENAI_API_KEY not found in Django .env.production"
            return 1
        fi
        
        return 0
    else
        print_error "No Django .env or .env.production file found"
        return 1
    fi
}

test_ai_features() {
    TESTS_RUN=$((TESTS_RUN + 1))
    print_test "AI Service Features Check"
    
    # Test with comprehensive data to trigger all features
    comprehensive_data='{
        "age": 65,
        "gender": "Male",
        "weight": 85,
        "height": 175,
        "heart_rate": 110,
        "spo2": 92,
        "glucose": 180,
        "blood_pressure_systolic": 160,
        "blood_pressure_diastolic": 100,
        "temperature": 99.2,
        "cholesterol": 240,
        "respiration_rate": 24,
        "symptoms": "Severe chest pain radiating to jaw and left arm, sweating",
        "medical_history": "Hypertension, Diabetes Type 2, Smoking history"
    }'
    
    response=$(curl -s -X POST "$AI_SERVICE_URL/api/v1/clin-gpt/analyze/" \
        -H "Content-Type: application/json" \
        -d "$comprehensive_data")
    
    # Check for RAG sources
    rag_sources=$(echo "$response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', {}).get('sources', [])))" 2>/dev/null)
    
    if [ "$rag_sources" -gt 0 ]; then
        print_success "RAG (Retrieval-Augmented Generation) is working"
        print_info "Retrieved $rag_sources clinical guideline sources"
    else
        print_warning "No RAG sources retrieved"
    fi
    
    # Check for PHI detection
    phi_detected=$(echo "$response" | python3 -c "import sys, json; g = json.load(sys.stdin).get('data', {}).get('guardrails', {}); print(g.get('input_phi_detected', 0) + g.get('output_phi_detected', 0))" 2>/dev/null)
    
    if [ "$phi_detected" -gt 0 ]; then
        print_info "PHI Guardrails detected and redacted $phi_detected entities"
    else
        print_info "No PHI detected in this test"
    fi
    
    return 0
}

# ==============================================================================
# Main Test Execution
# ==============================================================================

main() {
    print_header "InTEAM EMR + AI Service Integration Test Suite"
    
    echo -e "\n${BLUE}Starting tests at $(date)${NC}"
    echo -e "${BLUE}Environment: ${ENVIRONMENT^^}${NC}"
    echo -e "${BLUE}Django App: $DJANGO_APP_PATH${NC}"
    echo -e "${BLUE}Laravel App: $LARAVEL_APP_PATH${NC}"
    
    # Run all tests
    test_docker_services
    test_django_env_config
    test_ai_service_health
    test_laravel_ai_service_config
    test_laravel_clin_gpt_service
    test_emr_blade_integration
    test_basic_clinical_analysis
    test_ai_features
    test_emr_analysis_endpoint
    
    # Print summary
    print_header "Test Summary"
    echo -e "Total Tests: ${BLUE}$TESTS_RUN${NC}"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}✓ All tests passed!${NC}"
        echo -e "${GREEN}EMR and AI service integration is working correctly.${NC}"
        exit 0
    else
        echo -e "\n${RED}✗ Some tests failed.${NC}"
        
        # Provide troubleshooting tips
        print_header "Troubleshooting"
        
        if [ $TESTS_FAILED -gt 0 ]; then
            echo -e "${YELLOW}Common Issues:${NC}"
            echo "1. EMR Analysis Endpoint (404) - Run deployment update:"
            if [ "$ENVIRONMENT" = "local" ]; then
                echo "   cd $DJANGO_APP_PATH"
                echo "   docker-compose down && docker-compose up -d --build"
            else
                echo "   cd $DJANGO_APP_PATH"
                echo "   # Run your server deployment script"
            fi
            echo ""
            echo "2. Connection Refused - Check if services are running:"
            echo "   docker ps"
            echo ""
            echo "3. Laravel Configuration - Verify .env settings:"
            echo "   DJANGO_AI_URL=$AI_SERVICE_URL"
            echo ""
        fi
        
        exit 1
    fi
}

# Run main function
main
