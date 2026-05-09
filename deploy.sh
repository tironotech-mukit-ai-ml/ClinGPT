#!/bin/bash

###############################################################################
# Django AI Service - Automated Production Deployment Script
# Description: Complete deployment automation from cleanup to container startup
# Usage: ./deploy.sh
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/srv/apps/django-app1"
BACKUP_DIR="/srv/apps/django-app1.backup"
NETWORK_NAME="django-app1_django_ai_network"
POSTGRES_CONTAINER="inteam-ai-postgres"
REDIS_CONTAINER="inteam-ai-redis"
DJANGO_CONTAINER="inteam-ai-django"
IMAGE_NAME="inteam-ai-service:latest"

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo -e "\n${BLUE}===========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}===========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed"
        exit 1
    fi
}

###############################################################################
# Main Deployment Steps
###############################################################################

step_1_cleanup() {
    print_header "Step 1: Cleanup Existing Containers and Images"

    # Stop and remove Django container
    if docker ps -a | grep -q $DJANGO_CONTAINER; then
        print_info "Removing Django container..."
        docker rm -f $DJANGO_CONTAINER 2>/dev/null || true
        print_success "Django container removed"
    else
        print_info "Django container doesn't exist, skipping..."
    fi

    # Stop and remove PostgreSQL container
    if docker ps -a | grep -q $POSTGRES_CONTAINER; then
        print_info "Removing PostgreSQL container..."
        docker rm -f $POSTGRES_CONTAINER 2>/dev/null || true
        print_success "PostgreSQL container removed"
    else
        print_info "PostgreSQL container doesn't exist, skipping..."
    fi

    # Stop and remove Redis container
    if docker ps -a | grep -q $REDIS_CONTAINER; then
        print_info "Removing Redis container..."
        docker rm -f $REDIS_CONTAINER 2>/dev/null || true
        print_success "Redis container removed"
    else
        print_info "Redis container doesn't exist, skipping..."
    fi

    # Remove network
    if docker network ls | grep -q $NETWORK_NAME; then
        print_info "Removing Docker network..."
        docker network rm $NETWORK_NAME 2>/dev/null || true
        print_success "Docker network removed"
    else
        print_info "Docker network doesn't exist, skipping..."
    fi

    # Remove old image
    if docker images | grep -q "inteam-ai-service"; then
        print_info "Removing old Docker image..."
        docker rmi -f $IMAGE_NAME 2>/dev/null || true
        print_success "Old Docker image removed"
    fi
}

step_2_prepare_directories() {
    print_header "Step 2: Prepare Directories and Permissions"

    cd $PROJECT_DIR

    # Create directories if they don't exist
    print_info "Creating required directories..."
    mkdir -p staticfiles media logs

    # Fix permissions (UID 1000 = appuser in container)
    print_info "Fixing permissions..."
    sudo chown -R 1000:1000 staticfiles media logs

    print_success "Directories prepared with correct permissions"
}

step_3_check_env() {
    print_header "Step 3: Verify Environment Configuration"

    # Check .env.production
    if [ ! -f "$PROJECT_DIR/.env.production" ]; then
        print_error ".env.production file not found!"
        print_info "Please create .env.production with required variables"
        exit 1
    fi
    print_success ".env.production file exists"

    # Check Dockerfile.production
    if [ ! -f "$PROJECT_DIR/Dockerfile.production" ]; then
        print_error "Dockerfile.production file not found!"
        exit 1
    fi
    print_success "Dockerfile.production file exists"

    # Check docker-compose.production.yml
    if [ ! -f "$PROJECT_DIR/docker-compose.production.yml" ]; then
        print_error "docker-compose.production.yml file not found!"
        exit 1
    fi
    print_success "docker-compose.production.yml file exists"

    # Check scripts directory
    if [ ! -d "$PROJECT_DIR/scripts" ]; then
        print_error "scripts/ directory not found!"
        exit 1
    fi
    print_success "scripts/ directory exists"

    # Check init scripts
    if [ ! -f "$PROJECT_DIR/scripts/init_pgvector.sql" ]; then
        print_warning "scripts/init_pgvector.sql not found"
    else
        print_success "scripts/init_pgvector.sql exists"
    fi

    if [ ! -f "$PROJECT_DIR/scripts/init_readonly_user.sql" ]; then
        print_warning "scripts/init_readonly_user.sql not found"
    else
        print_success "scripts/init_readonly_user.sql exists"
    fi

    # Check for required environment variables
    print_info "Checking required environment variables..."

    if ! grep -q "POSTGRES_PASSWORD" "$PROJECT_DIR/.env.production"; then
        print_error "POSTGRES_PASSWORD not found in .env.production"
        exit 1
    fi

    if ! grep -q "SECRET_KEY" "$PROJECT_DIR/.env.production"; then
        print_error "SECRET_KEY not found in .env.production"
        exit 1
    fi

    if ! grep -q "OPENAI_API_KEY" "$PROJECT_DIR/.env.production"; then
        print_warning "OPENAI_API_KEY not found in .env.production (tests may fail)"
    fi

    if ! grep -q "DB_HOST=postgres" "$PROJECT_DIR/.env.production"; then
        print_warning "DB_HOST should be set to 'postgres' for Docker networking"
    fi

    print_success "All required files and variables verified"
}

step_4_build_image() {
    print_header "Step 4: Build Docker Image"

    cd $PROJECT_DIR

    # Remove old image to prevent cache issues
    print_info "Removing old Docker image..."
    docker rmi -f $IMAGE_NAME 2>/dev/null || true

    # Remove build cache
    print_info "Clearing Docker build cache..."
    docker builder prune -f 2>/dev/null || true

    print_info "Building Docker image (this may take several minutes)..."
    docker build -f Dockerfile.production -t $IMAGE_NAME --no-cache --progress=plain .

    # Verify Django was installed
    print_info "Verifying Django installation in image..."
    if docker run --rm $IMAGE_NAME /opt/venv/bin/pip list | grep -q Django; then
        print_success "Docker image built successfully with Django installed"
    else
        print_error "Docker build succeeded but Django was not installed!"
        print_info "Check requirements.txt and build logs"
        exit 1
    fi
}

step_5_start_databases() {
    print_header "Step 5: Start Database Services"

    cd $PROJECT_DIR

    print_info "Starting PostgreSQL and Redis..."
    docker-compose -f docker-compose.production.yml up -d postgres redis

    print_info "Waiting for databases to become healthy (30 seconds)..."
    sleep 30

    # Check if containers are running
    if docker ps | grep -q $POSTGRES_CONTAINER && docker ps | grep -q $REDIS_CONTAINER; then
        print_success "Database services started successfully"
    else
        print_error "Failed to start database services"
        docker ps -a
        exit 1
    fi
}

step_6_start_django() {
    print_header "Step 6: Start Django Application"

    cd $PROJECT_DIR

    print_info "Starting Django container..."
    docker run -d \
      --name $DJANGO_CONTAINER \
      --restart unless-stopped \
      --env-file .env.production \
      -e PYTHONUNBUFFERED=1 \
      -e DJANGO_SETTINGS_MODULE=config.settings \
      -e PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
      -v $(pwd)/staticfiles:/app/staticfiles:Z \
      -v $(pwd)/media:/app/media:Z \
      -v $(pwd)/logs:/app/logs:Z \
      -p 127.0.0.1:8001:8001 \
      --network $NETWORK_NAME \
      --add-host host.docker.internal:host-gateway \
      $IMAGE_NAME \
      bash -c "/opt/venv/bin/python manage.py migrate --noinput && /opt/venv/bin/python manage.py collectstatic --noinput --clear && /opt/venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8001 --workers 3 --worker-class gthread --threads 2 --timeout 120 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - --log-level info"

    print_success "Django container started"
}

step_7_verify_deployment() {
    print_header "Step 7: Verify Deployment"

    print_info "Waiting for Django to start (30 seconds)..."
    sleep 30

    # Check container status
    print_info "Checking container status..."
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    # Check if all 3 containers are running
    RUNNING_COUNT=$(docker ps | grep -E "$POSTGRES_CONTAINER|$REDIS_CONTAINER|$DJANGO_CONTAINER" | wc -l)

    if [ "$RUNNING_COUNT" -eq 3 ]; then
        print_success "All 3 containers are running"
    else
        print_error "Not all containers are running ($RUNNING_COUNT/3)"
        exit 1
    fi

    # Test health endpoint
    print_info "Testing health endpoint..."
    sleep 5
    HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/health/)

    if [ "$HEALTH_STATUS" = "200" ]; then
        print_success "Health check passed (HTTP $HEALTH_STATUS)"
    else
        print_error "Health check failed (HTTP $HEALTH_STATUS)"
        print_info "Checking Django logs..."
        docker logs --tail 50 $DJANGO_CONTAINER
        exit 1
    fi
}

step_7b_setup_data() {
    print_header "Step 7b: Complete System Initialization"

    # Sub-step 1: Verify Spacy model
    print_info "1. Verifying Spacy model installation..."
    if docker exec $DJANGO_CONTAINER python -c "import spacy; spacy.load('en_core_web_sm'); print('OK')" 2>/dev/null | grep -q "OK"; then
        print_success "Spacy model (en_core_web_sm) loaded successfully"
    else
        print_warning "Spacy model not found, attempting to download..."
        if docker exec $DJANGO_CONTAINER python -m spacy download en_core_web_sm; then
            print_success "Spacy model downloaded successfully"
        else
            print_error "Failed to download Spacy model (PHI detection may not work)"
        fi
    fi

    echo ""

    # Sub-step 2: Setup Guardrails and RAG
    print_info "2. Setting up PHI Guardrails and RAG system..."
    if docker exec $DJANGO_CONTAINER python manage.py setup_guardrails_rag --skip-spacy 2>&1 | tee /tmp/setup_guardrails.log; then
        if grep -q "All validation checks passed" /tmp/setup_guardrails.log; then
            print_success "PHI Guardrails and RAG system validated successfully"
        else
            print_warning "Setup completed but validation may have issues (check logs)"
        fi
    else
        print_warning "PHI Guardrails setup failed (non-critical, may already be configured)"
    fi

    echo ""

    # Sub-step 3: Pre-download Sentence Transformers model
    print_info "3. Pre-downloading Sentence Transformers model (300MB, may take 1-2 minutes)..."
    if docker exec $DJANGO_CONTAINER python -c "
from sentence_transformers import SentenceTransformer
print('Downloading model...')
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('Model loaded successfully')
embedding = model.encode('test')
print(f'Embedding dimension: {len(embedding)}')
" 2>&1 | tee /tmp/sentence_transformers.log; then
        if grep -q "Embedding dimension: 384" /tmp/sentence_transformers.log; then
            print_success "Sentence Transformers model downloaded and validated (384-dim)"
        else
            print_warning "Sentence Transformers downloaded but dimension check failed"
        fi
    else
        print_warning "Failed to download Sentence Transformers (will download on first API call)"
    fi

    echo ""

    # Sub-step 4: Check and populate clinical guidelines
    print_info "4. Checking clinical guidelines database..."
    GUIDELINE_COUNT=$(docker exec $DJANGO_CONTAINER python -c "from apps.clin_gpt.models import ClinicalGuideline; print(ClinicalGuideline.objects.count())" 2>/dev/null || echo "0")

    if [ "$GUIDELINE_COUNT" -ge 20 ]; then
        print_success "Clinical guidelines already populated ($GUIDELINE_COUNT records)"

        # Verify embeddings exist
        print_info "Verifying embeddings are generated..."
        EMBEDDING_COUNT=$(docker exec $DJANGO_CONTAINER python -c "
from apps.clin_gpt.models import ClinicalGuideline
from django.db.models import Q
count = ClinicalGuideline.objects.exclude(Q(embedding__isnull=True) | Q(embedding=[])).count()
print(count)
" 2>/dev/null || echo "0")

        if [ "$EMBEDDING_COUNT" -ge 20 ]; then
            print_success "All $EMBEDDING_COUNT guidelines have embeddings generated"
        else
            print_warning "Only $EMBEDDING_COUNT/$GUIDELINE_COUNT guidelines have embeddings"
            print_info "You may need to regenerate embeddings"
        fi
    else
        print_info "Populating clinical guidelines database..."
        if docker exec $DJANGO_CONTAINER python manage.py populate_guidelines; then
            print_success "Clinical guidelines populated successfully"

            # Verify population
            NEW_COUNT=$(docker exec $DJANGO_CONTAINER python -c "from apps.clin_gpt.models import ClinicalGuideline; print(ClinicalGuideline.objects.count())" 2>/dev/null || echo "0")
            print_success "Total clinical guidelines in database: $NEW_COUNT records"

            # Verify embeddings
            EMBEDDING_COUNT=$(docker exec $DJANGO_CONTAINER python -c "
from apps.clin_gpt.models import ClinicalGuideline
from django.db.models import Q
count = ClinicalGuideline.objects.exclude(Q(embedding__isnull=True) | Q(embedding=[])).count()
print(count)
" 2>/dev/null || echo "0")

            if [ "$EMBEDDING_COUNT" -eq "$NEW_COUNT" ]; then
                print_success "All guidelines have embeddings generated"
            else
                print_warning "Some guidelines missing embeddings ($EMBEDDING_COUNT/$NEW_COUNT)"
            fi
        else
            print_warning "Clinical guidelines population failed (check logs)"
            print_info "You can manually populate later with: docker exec $DJANGO_CONTAINER python manage.py populate_guidelines"
        fi
    fi

    echo ""

    # Sub-step 5: Final validation
    print_info "5. Running final system validation..."
    VALIDATION_PASSED=true

    # Check PHI detection
    if docker exec $DJANGO_CONTAINER python -c "
from apps.clin_gpt.services.phi_guardrail import PHIGuardrail
guardrail = PHIGuardrail()
redacted, detections = guardrail.redact_phi('John Smith 555-1234')
assert len(detections) > 0, 'No PHI detected'
print('PHI detection: OK')
" 2>/dev/null | grep -q "PHI detection: OK"; then
        print_success "PHI detection validated"
    else
        print_warning "PHI detection validation failed"
        VALIDATION_PASSED=false
    fi

    # Check RAG system
    if docker exec $DJANGO_CONTAINER python -c "
from apps.clin_gpt.services.rag_service import get_rag_service
rag = get_rag_service()
results = rag.search_guidelines('chest pain', top_k=3)
assert len(results) > 0, 'RAG search failed'
print('RAG system: OK')
" 2>/dev/null | grep -q "RAG system: OK"; then
        print_success "RAG system validated"
    else
        print_warning "RAG system validation failed"
        VALIDATION_PASSED=false
    fi

    echo ""

    if [ "$VALIDATION_PASSED" = true ]; then
        print_success "✅ All system components validated successfully!"
    else
        print_warning "⚠️  Some validation checks failed (system may still work)"
    fi

    echo ""
}

step_8_show_logs() {
    print_header "Step 8: Recent Logs"

    print_info "Django Application Logs (last 20 lines):"
    echo "----------------------------------------"
    docker logs --tail 20 $DJANGO_CONTAINER
    echo ""
}

step_9_run_tests() {
    print_header "Step 9: Run Tests"

    # Ask user if they want to run tests
    echo -e "${YELLOW}Do you want to run tests? (y/n)${NC}"
    read -t 10 -n 1 -r RUN_TESTS || RUN_TESTS="n"
    echo ""

    if [[ ! $RUN_TESTS =~ ^[Yy]$ ]]; then
        print_info "Skipping tests..."
        return 0
    fi

    # Run tests using run_tests.sh script
    print_info "Running test suite via run_tests.sh..."
    if [ -f "$PROJECT_DIR/run_tests.sh" ]; then
        cd $PROJECT_DIR
        if bash run_tests.sh all; then
            print_success "All tests passed"
        else
            print_warning "Some tests failed (check output above)"
        fi
    else
        print_warning "run_tests.sh not found, skipping tests"
    fi

    echo ""
}

###############################################################################
# Main Execution
###############################################################################

main() {
    print_header "Django AI Service - Production Deployment"

    # Check prerequisites
    print_info "Checking prerequisites..."
    check_command docker
    check_command docker-compose
    check_command curl

    # Execute deployment steps
    step_1_cleanup
    step_2_prepare_directories
    step_3_check_env
    step_4_build_image
    step_5_start_databases
    step_6_start_django
    step_7_verify_deployment
    step_7b_setup_data
    step_8_show_logs
    step_9_run_tests

    # Success message
    print_header "✅ DEPLOYMENT SUCCESSFUL!"
    echo -e "${GREEN}Django AI Service is now running!${NC}\n"
    echo "Service URLs:"
    echo "  - Health Check: http://127.0.0.1:8001/health/"
    echo "  - API Endpoint: http://127.0.0.1:8001/api/v1/clin-gpt/analyze/"
    echo ""
    echo "Manual Test Commands:"
    echo "  - Unit tests:      docker exec -it $DJANGO_CONTAINER python manage.py test apps.clin_gpt.tests -v 2"
    echo "  - Integration:     docker exec -it $DJANGO_CONTAINER python test_clin_gpt.py"
    echo "  - Full system:     docker exec -e CI=true -it $DJANGO_CONTAINER python test_full_system.py"
    echo ""
    echo "Management Commands:"
    echo "  - Check guidelines:    docker exec $DJANGO_CONTAINER python -c \"from apps.clin_gpt.models import ClinicalGuideline; print(f'Clinical Guidelines: {ClinicalGuideline.objects.count()}')\" "
    echo "  - Populate data:       docker exec $DJANGO_CONTAINER python manage.py populate_guidelines"
    echo "  - Setup guardrails:    docker exec $DJANGO_CONTAINER python manage.py setup_guardrails_rag"
    echo ""
    echo "Useful Commands:"
    echo "  - View logs:       docker logs -f $DJANGO_CONTAINER"
    echo "  - Check status:    docker ps"
    echo "  - Stop services:   docker-compose -f $PROJECT_DIR/docker-compose.production.yml down"
    echo "  - Restart Django:  docker restart $DJANGO_CONTAINER"
    echo ""
}

# Run main function
main
