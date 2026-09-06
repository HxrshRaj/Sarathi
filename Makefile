.PHONY: help up down logs build fmt lint test test-api test-web migrate revision seed clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Start the full stack
	docker compose up --build

down: ## Stop the stack
	docker compose down

logs: ## Tail all logs
	docker compose logs -f

build: ## Build all images
	docker compose build

sandbox-images: ## Build the locked-down sandbox toolchain images
	docker compose --profile sandbox-images build

migrate: ## Apply DB migrations (inside api container)
	docker compose run --rm api alembic upgrade head

revision: ## Create a new migration: make revision m="message"
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

fmt: ## Format code
	cd apps/api && ruff format . && ruff check --fix .
	cd apps/web && pnpm run format

lint: ## Lint + typecheck
	cd apps/api && ruff check . && mypy app
	cd apps/web && pnpm run lint && pnpm run typecheck

test: test-api test-web ## Run all tests

test-api: ## Backend tests
	cd apps/api && pytest -q

test-web: ## Frontend tests
	cd apps/web && pnpm run test

seed: ## Load demo user + sample repo benchmark
	docker compose run --rm api python -m app.scripts.seed

clean: ## Remove volumes and caches
	docker compose down -v
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
