.PHONY: up down build test migrate migrate-001 migrate-003 migrate-004 migrate-sql seed lint fmt clean logs logs-gw logs-ke logs-ta ps health shell-ke shell-ta shell-gw test-unit test-integration test-e2e test-load test-cov

COMPOSE  = docker compose -f docker-compose.dev.yml --env-file .env

# Consolidated backend services (was 6 microservices, now 3)
SERVICES = api-gateway knowledge-engine telemetry-aggregator

# ── Lifecycle ────────────────────────────────────────────────────────────────

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

.env:
	@cp .env.example .env
	@echo "📋 Created .env from .env.example — edit before starting."

# ── Development ──────────────────────────────────────────────────────────────

logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

logs-gw: ## Tail API Gateway logs only
	$(COMPOSE) logs -f --tail=100 api-gateway

logs-ke: ## Tail Knowledge Engine logs only
	$(COMPOSE) logs -f --tail=100 knowledge-engine

logs-ta: ## Tail Telemetry Aggregator logs only
	$(COMPOSE) logs -f --tail=100 telemetry-aggregator

ps: ## List running containers
	$(COMPOSE) ps

shell-ke: ## Open shell in Knowledge Engine container
	$(COMPOSE) exec knowledge-engine /bin/bash

shell-ta: ## Open shell in Telemetry Aggregator container
	$(COMPOSE) exec telemetry-aggregator /bin/bash

shell-gw: ## Open shell in API Gateway container
	$(COMPOSE) exec api-gateway /bin/bash

# ── Database ─────────────────────────────────────────────────────────────────

migrate: ## Run ALL migrations in order (safe, idempotent)
	@echo "▶ Migration 001 (baseline schema)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/001_initial_schema.sql
	@echo "▶ Migration 002 (consolidated architecture)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/002_consolidated_architecture.sql 2>/dev/null || true
	@echo "▶ Migration 003 (TimescaleDB)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/003_timescaledb.sql 2>/dev/null || true
	@echo "▶ Migration 004 (performance hardening)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/004_performance_hardening.sql 2>/dev/null || true
	@echo "▶ Migration 005 (missing tables)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/005_missing_tables.sql 2>/dev/null || true
	@echo "▶ Migration 006 (schema alignment)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/006_schema_alignment.sql 2>/dev/null || true
	@echo "✅ All migrations applied."

migrate-001: ## Apply baseline schema migration only
	@echo "▶ Running migration 001..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/001_initial_schema.sql
	@echo "✅ Migration 001 done."

migrate-003: ## Apply TimescaleDB migration (Phase 3)
	@echo "▶ Running migration 003 (TimescaleDB)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/003_timescaledb.sql
	@echo "✅ Migration 003 done."

migrate-004: ## Apply performance hardening migration (Phase 4)
	@echo "▶ Running migration 004 (performance hardening)..."
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-ikb_admin} -d $${POSTGRES_DB:-ikb_main} \
		-f /dev/stdin < infrastructure/docker/migrations/004_performance_hardening.sql
	@echo "✅ Migration 004 done."

migrate-sql: ## Show pending migration SQL (dry-run, no apply)
	@echo "=== 003_timescaledb.sql ==="
	@cat infrastructure/docker/migrations/003_timescaledb.sql 2>/dev/null || echo "(not found)"
	@echo "\n=== 004_performance_hardening.sql ==="
	@cat infrastructure/docker/migrations/004_performance_hardening.sql 2>/dev/null || echo "(not found)"
	@echo "\n=== 005_missing_tables.sql ==="
	@cat infrastructure/docker/migrations/005_missing_tables.sql 2>/dev/null || echo "(not found)"

seed: ## Seed databases with sample data
	$(COMPOSE) exec telemetry-aggregator python -m scripts.seed_data
	@echo "✅ Seed data loaded."

# ── Testing ──────────────────────────────────────────────────────────────────

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

test-cov: ## Run all tests with coverage report (min 70%)
	poetry run pytest tests/ --cov=backend --cov-report=term-missing --cov-fail-under=70

# ── Code Quality ─────────────────────────────────────────────────────────────

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

# ── Health ───────────────────────────────────────────────────────────────────

health: ## Check health of all consolidated services
	@echo "🔍 Checking service health..."
	@for svc in api-gateway knowledge-engine telemetry-aggregator; do \
		port=$$(case $$svc in \
			api-gateway) echo 8000;; \
			knowledge-engine) echo 8001;; \
			telemetry-aggregator) echo 8002;; \
		esac); \
		status=$$(curl -sf --max-time 5 http://localhost:$$port/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unreachable"); \
		echo "  $$svc (port $$port): $$status"; \
	done
	@echo "\n📊 Infrastructure:"
	@curl -sf http://localhost:9090/-/healthy 2>/dev/null && echo "  prometheus: healthy" || echo "  prometheus: unreachable"
	@curl -sf http://localhost:3001/api/health 2>/dev/null && echo "  grafana: healthy" || echo "  grafana: unreachable"
	@echo "✅ Health check complete."

# ── Help ─────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
