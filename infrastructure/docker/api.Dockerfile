FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api \
    UV_NO_PROGRESS=1
RUN useradd --create-home --uid 10001 appuser \
    && install -d -o appuser -g appuser -m 0755 /var/lib/darknetra/evidence
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.4 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --all-packages --no-dev
COPY apps/api apps/api
USER appuser
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "--app-dir", "apps/api", "darknetra_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
