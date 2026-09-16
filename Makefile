.PHONY: help up down status backend-dev frontend-dev migrate test reindex

PYTHON ?= python
DOCKER_COMPOSE ?= docker compose -f docker/docker-compose.yml

help:
	@echo "Aegis Development & Operating Commands:"
	@echo "  make up           - Launch PostgreSQL, OpenSearch, Qdrant, Redis via Docker"
	@echo "  make down         - Stop Docker infrastructure services"
	@echo "  make status       - Check status of Docker containers"
	@echo "  make backend-dev  - Start FastAPI development server"
	@echo "  make frontend-dev - Start Next.js development server"
	@echo "  make migrate      - Run Alembic database migrations"
	@echo "  make test         - Run Pytest backend test suite"
	@echo "  make reindex      - Reconstitute derived search indices from Postgres SSOT"

up:
	$(DOCKER_COMPOSE) up -d

down:
	$(DOCKER_COMPOSE) down

status:
	$(DOCKER_COMPOSE) ps

backend-dev:
	cd packages/backend && uvicorn app.main:app --reload --port 8000

frontend-dev:
	cd packages/frontend && npm run dev

migrate:
	cd packages/backend && alembic upgrade head

test:
	cd packages/backend && pytest tests/

reindex:
	$(PYTHON) scripts/reindex.py --target all
