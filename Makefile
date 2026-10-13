.PHONY: setup sync lint test check

setup sync:
	uv sync --locked

lint:
	uv run --locked ruff check src tests
	uv run --locked ruff format --check src tests

test:
	uv run --locked pytest

check: lint test
