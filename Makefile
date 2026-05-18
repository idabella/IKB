.PHONY: up down build test migrate seed lint clean logs ps health

COMPOSE = docker compose -f docker-compose.dev.yml --env-file .env
SERVICES = api_gateway rag_service agent_service telemetry_service knowledge_graph_service ingestion_service

# ── Lifecycle ────────────────────────────────────────────────

up: .env ## Start all services
	$(COMPOSE) up -d --build
	@echo "\n✅ All services started. Run 'make health' to verify."

down: ## Stop and remove all containers
	$(COMPOSE) down --remove-orphans

build: ## Build all images without starting
	$(COMPOSE) build --parallel

clean: ## Stop everything, remove volumes
	$(COMPOSE) down -v --remove-orphans
	@echo "🗑️  Cleaned all containers and volumes."

# ── Development ──────────────────────────────────────────────

.env:
	@cp .env.example .env
	@echo "📋 Created .env from .env.example — edit before starting."

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

ps: ## List running containers
	$(COMPOSE) ps

# ── Testing ──────────────────────────────────────────────────

test: ## Run all tests
	@echo "▶ Running unit tests..."
	poetry run pytest tests/unit -v --tb=short
	@echo "▶ Running integration tests..."
	poetry run pytest tests/integration -v --tb=short

test-unit: ## Run unit tests only
	poetry run pytest tests/unit -v --tb=short -x

test-integration: ## Run integration tests only
	poetry run pytest tests/integration -v --tb=short

test-e2e: ## Run end-to-end tests
	poetry run pytest tests/e2e -v --tb=short

test-load: ## Run load tests with locust
	poetry run locust -f tests/load/locustfile.py --headless -u 100 -r 10 --run-time 60s

# ── Database ─────────────────────────────────────────────────

migrate: ## Run database migrations
	@for svc in $(SERVICES); do \
		echo "▶ Migrating $$svc..."; \
		$(COMPOSE) exec $$(echo $$svc | tr _ -) alembic upgrade head 2>/dev/null || true; \
	done
	@echo "✅ Migrations complete."

seed: ## Seed databases with sample data
	$(COMPOSE) exec api-gateway python -m scripts.seed_data
	@echo "✅ Seed data loaded."

# ── Code Quality ─────────────────────────────────────────────

lint: ## Run all linters
	@echo "▶ Running ruff..."
	poetry run ruff check backend/ ai/ --fix
	@echo "▶ Running mypy..."
	poetry run mypy backend/ ai/ --ignore-missing-imports
	@echo "▶ Running black..."
	poetry run black backend/ ai/ --check
	@echo "✅ Lint complete."

fmt: ## Auto-format code
	poetry run black backend/ ai/
	poetry run ruff check backend/ ai/ --fix
	@echo "✅ Formatted."

# ── Health ───────────────────────────────────────────────────

health: ## Check health of all services
	@bash scripts/health_check.sh

# ── Help ─────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
