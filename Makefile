.PHONY: setup sync lint test check infra-up infra-down infra-ps infra-check db-upgrade db-current test-integration test-redis-integration test-kafka-integration test-phase02-failures kafka-init feature-lag feature-worker decision-api investigator-api

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

kafka-init:
	@test -n "$(ARGUS_KAFKA_BOOTSTRAP_SERVERS)" || (echo "ARGUS_KAFKA_BOOTSTRAP_SERVERS is required" >&2; exit 1)
	uv run --locked python -m argus.events.kafka_admin

feature-lag:
	@test -n "$(ARGUS_KAFKA_BOOTSTRAP_SERVERS)" || (echo "ARGUS_KAFKA_BOOTSTRAP_SERVERS is required" >&2; exit 1)
	uv run --locked python -m argus.events.kafka_lag

feature-worker:
	uv run --locked python -m argus.workers.feature_worker

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

# Requires an explicit host-side ARGUS_REDIS_URL.
test-redis-integration:
	@test -n "$(ARGUS_REDIS_URL)" || (echo "ARGUS_REDIS_URL is required" >&2; exit 1)
	uv run --locked pytest tests/integration/test_redis_feature_projection.py

test-kafka-integration:
	@test -n "$(ARGUS_KAFKA_BOOTSTRAP_SERVERS)" || (echo "ARGUS_KAFKA_BOOTSTRAP_SERVERS is required" >&2; exit 1)
	@test -n "$(ARGUS_REDIS_URL)" || (echo "ARGUS_REDIS_URL is required" >&2; exit 1)
	uv run --locked pytest tests/integration/test_kafka_feature_worker.py

test-phase02-failures:
	@test -n "$(ARGUS_KAFKA_BOOTSTRAP_SERVERS)" || (echo "ARGUS_KAFKA_BOOTSTRAP_SERVERS is required" >&2; exit 1)
	@test -n "$(ARGUS_REDIS_URL)" || (echo "ARGUS_REDIS_URL is required" >&2; exit 1)
	@test -n "$(ARGUS_DATABASE_URL)" || (echo "ARGUS_DATABASE_URL is required" >&2; exit 1)
	uv run --locked pytest tests/integration/test_phase02_failure_semantics.py

# Requires explicit host-side Kafka and Redis endpoints.
test-simulation-kafka:
	@test -n "$(ARGUS_KAFKA_BOOTSTRAP_SERVERS)" || (echo "ARGUS_KAFKA_BOOTSTRAP_SERVERS is required" >&2; exit 1)
	@test -n "$(ARGUS_REDIS_URL)" || (echo "ARGUS_REDIS_URL is required" >&2; exit 1)
	uv run --locked pytest tests/integration/test_simulation_kafka_playback.py -q
