FROM ghcr.io/astral-sh/uv:0.11.0 AS uv
FROM python:3.12-slim-bookworm AS runtime
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN groupadd --gid 10001 darknetra && useradd --uid 10001 --gid darknetra --create-home darknetra
WORKDIR /app/backend
ARG DARKNETRA_EMBEDDINGS=0
COPY backend/pyproject.toml backend/uv.lock ./
RUN if [ "$DARKNETRA_EMBEDDINGS" = "1" ]; then uv sync --frozen --no-dev --no-install-project --extra embed; else uv sync --frozen --no-dev --no-install-project; fi
COPY backend/ ./
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY third_party/ /app/third_party/
RUN if [ "$DARKNETRA_EMBEDDINGS" = "1" ]; then uv sync --frozen --no-dev --extra embed; else uv sync --frozen --no-dev; fi
RUN mkdir -p /var/lib/darknetra/vault /app/models/cache && chown -R darknetra:darknetra /var/lib/darknetra /app/models
ENV PATH="/app/backend/.venv/bin:$PATH" DARKNETRA_VAULT_PATH=/var/lib/darknetra/vault
USER darknetra
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3)"
CMD ["uvicorn", "darknetra.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
