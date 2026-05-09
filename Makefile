.PHONY: help setup setup-docker setup-local setup-prod install-spacy test logs clean

# Default target
help:
	@echo "InTEAM AI Service - Makefile Commands"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make setup-docker    - Complete setup for Docker environment"
	@echo "  make setup-local     - Complete setup for local development (SQLite)"
	@echo "  make setup-prod      - Complete setup for production"
	@echo ""
	@echo "Model Management:"
	@echo "  make install-spacy   - Install Spacy model for PHI detection"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make up              - Start all services"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make rebuild         - Rebuild and restart services"
	@echo "  make logs            - View logs (all services)"
	@echo "  make logs-django     - View Django logs only"
	@echo ""
	@echo "Database Commands:"
	@echo "  make migrate         - Run database migrations"
	@echo "  make populate        - Populate clinical guidelines"
	@echo "  make db-shell        - Open PostgreSQL shell"
	@echo "  make db-status       - Show database status"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make test            - Run Django unit tests"
	@echo "  make test-full       - Run comprehensive system tests"
	@echo "  make test-api        - Test API endpoint"
	@echo "  make health          - Check health endpoint"
	@echo ""
	@echo "Cleanup Commands:"
	@echo "  make clean           - Stop services and remove volumes"
	@echo "  make clean-all       - Remove everything (including images)"

# ==================== Setup Commands ====================

setup-docker:
	@echo "Starting Docker setup..."
	@docker-compose up -d
	@echo "Waiting for services..."
	@sleep 10
	@echo "Installing Spacy model..."
	@docker-compose exec -T -u root django python scripts/install_spacy.py || docker-compose exec -T -u root django python -m spacy download en_core_web_lg
	@docker-compose restart django
	@echo "Running migrations..."
	@docker-compose exec -T django python manage.py migrate
	@docker-compose exec -T django python manage.py populate_guidelines
	@echo "✅ Docker setup complete!"

setup-local:
	@echo "Starting local setup..."
	@pip install -r requirements.txt
	@python scripts/install_spacy.py
	@python manage.py migrate
	@python manage.py populate_guidelines
	@echo "✅ Local setup complete!"

setup-prod:
	@echo "Starting production setup..."
	@docker-compose pull
	@docker-compose up -d
	@sleep 15
	@docker-compose exec -T -u root django python scripts/install_spacy.py
	@docker-compose restart django
	@docker-compose exec -T django python manage.py migrate
	@docker-compose exec -T django python manage.py populate_guidelines
	@docker-compose exec -T django python manage.py collectstatic --noinput
	@echo "✅ Production setup complete!"

install-spacy:
	@echo "Installing Spacy model..."
	@docker-compose exec -T -u root django python -m spacy download en_core_web_lg
	@docker-compose restart django
	@echo "✅ Spacy model installed"

# ==================== Docker Commands ====================

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

rebuild:
	docker-compose up -d --build
	@echo "⚠️  After rebuild, you must reinstall Spacy model:"
	@echo "   make install-spacy"

logs:
	docker-compose logs -f

logs-django:
	docker-compose logs -f django

ps:
	docker-compose ps

# ==================== Database Commands ====================

migrate:
	docker-compose exec -T django python manage.py migrate

populate:
	docker-compose exec -T django python manage.py populate_guidelines

db-shell:
	docker exec -it inteam-ai-postgres psql -U ryhan -d inteam_ai

db-status:
	@echo "Database Status:"
	@docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "\dt"
	@echo ""
	@echo "Clinical Guidelines:"
	@docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "SELECT COUNT(*) FROM clinical_guidelines;"
	@echo ""
	@echo "PHI Detection Logs:"
	@docker exec inteam-ai-postgres psql -U ryhan -d inteam_ai -c "SELECT COUNT(*) FROM phi_detection_logs;"

# ==================== Testing Commands ====================

test:
	docker-compose exec -T django python manage.py test

test-full:
test-full:
	@echo "$(COLOR_CYAN)Running comprehensive system tests...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Note: This test is READ-ONLY and safe for production$(COLOR_RESET)"
	python test_full_system.py

health:
	@curl -s http://localhost:8001/health/ | python -m json.tool

test-api:
	@echo "Testing Clinical Analysis API..."
	@curl -X POST http://localhost:8001/api/v1/clin-gpt/analyze/ \
		-H "Content-Type: application/json" \
		-d '{"age": 65, "gender": "Male", "symptoms": "chest pain", "medical_history": "hypertension"}' \
		-s | python -m json.tool | head -30

# ==================== Cleanup Commands ====================

clean:
	docker-compose down -v

clean-all:
	docker-compose down -v --rmi all

# ==================== Local Development ====================

run-local:
	python manage.py runserver 0.0.0.0:8001

shell:
	docker-compose exec django python manage.py shell

shell-local:
	python manage.py shell
