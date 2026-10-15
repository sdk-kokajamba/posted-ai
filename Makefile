.DEFAULT_GOAL := help
.PHONY: help install hooks run migrate revision fmt lint typecheck test check up down logs

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv sync

hooks:  ## Install git pre-commit hooks
	uv run pre-commit install

run:  ## Apply migrations and start the bot
	uv run alembic upgrade head
	uv run python -m bot

migrate:  ## Apply database migrations
	uv run alembic upgrade head

revision:  ## Create a migration: make revision m="add orders table"
	uv run alembic revision --autogenerate -m "$(m)"

fmt:  ## Format the code and fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

typecheck:  ## Run mypy
	uv run mypy

test:  ## Run the tests
	uv run pytest

check: lint typecheck test  ## Run all checks (same as CI)

up:  ## Start the bot with PostgreSQL and Redis in Docker
	docker compose up --build -d

down:  ## Stop the Docker services
	docker compose down

logs:  ## Follow the bot logs
	docker compose logs -f bot
