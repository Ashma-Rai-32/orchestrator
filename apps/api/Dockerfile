# Build from the repo root (uv workspace):  docker compose build api
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
# Docker CLI: the worker reaches the sandbox's browser via `docker exec -i` (MCP stdio).
COPY --from=docker:29.8.2-cli /usr/local/bin/docker /usr/local/bin/docker
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --locked --package staffroom-api --no-install-workspace

COPY apps/api apps/api
RUN uv sync --locked --package staffroom-api

RUN useradd --create-home app
USER app

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "staffroom_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
