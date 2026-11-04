# RouteWise API — production image (Render free web service or any container host).
FROM ghcr.io/astral-sh/uv:0.12.9 AS uv

FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv

# Mirror the repository layout (/app = repo root, /app/backend = backend): app.core.config resolves
# REPO_ROOT and backend/config/ relative to its own location, so a flattened /app layout would look
# for /backend/config/models.yaml and fail at startup.
WORKDIR /app/backend
# Dependencies first (cached layer), from the lockfile only.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY config ./config
COPY app ./app

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 routewise && chown -R routewise /app
USER routewise

EXPOSE 8000
# Migrations are additive and idempotent; running them at start keeps schema and code in step on
# hosts without a pre-deploy hook. --proxy-headers: the host's proxy sets X-Forwarded-For, so
# per-client limits (admin login throttle) see the real client address.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
