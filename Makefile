.PHONY: setup sync lint test check infra-up infra-down infra-ps infra-check db-upgrade db-current test-integration decision-api investigator-api

setup sync:
	uv sync --locked

lint:
	uv run --locked ruff check src tests migrations
	uv run --locked ruff format --check src tests migrations

test:
	uv run --locked pytest --ignore=tests/integration

check: lint test

decision-api:
	uv run --locked python -m argus.apps.decision_api.main

investigator-api:
	uv run --locked python -m argus.apps.investigator_api.main

infra-up:
	docker compose up -d

infra-down:
	docker compose down

infra-ps:
	docker compose ps

infra-check:
	docker compose exec -T postgres pg_isready -U argus -d argus
	docker compose exec -T redis redis-cli ping
	docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --list

# Host-side migrations and real PostgreSQL tests require ARGUS_DATABASE_URL.
db-upgrade:
	uv run --locked alembic upgrade head

db-current:
	uv run --locked alembic current

test-integration:
	uv run --locked pytest tests/integration
