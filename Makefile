.PHONY: setup sync lint test check infra-up infra-down infra-ps infra-check

setup sync:
	uv sync --locked

lint:
	uv run --locked ruff check src tests
	uv run --locked ruff format --check src tests

test:
	uv run --locked pytest

check: lint test

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
