FROM python:3.13-slim AS build
RUN pip install --no-cache-dir uv==0.12.8
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-managed-python

FROM python:3.13-slim
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "argus.apps.decision_api.main"]
