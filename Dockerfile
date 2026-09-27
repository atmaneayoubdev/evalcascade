# syntax=docker/dockerfile:1
#
# EvalCascade: local API + dashboard in one image.
#
#   docker build -t evalcascade .
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v evalcascade-data:/data evalcascade
#
# Secrets are never baked into the image. Supply them at runtime (--env-file / -e or
# docker compose env_file). The build context excludes .env files (see .dockerignore).

# ---------------------------------------------------------------------------
# Stage 1: build the dashboard (Next.js static export -> /web/out)
# ---------------------------------------------------------------------------
FROM node:22-alpine AS web

WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1

# Dependencies first, so this layer is cached until the lockfile changes.
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Third-party dependencies (cached until pyproject.toml / uv.lock change).
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# The project itself, installed non-editable into /app/.venv.
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# The dashboard bundle from stage 1.
COPY --from=web /web/out /app/dashboard

# Unprivileged runtime user; /data holds the SQLite database and imported datasets.
RUN groupadd --gid 10001 evalcascade \
    && useradd --uid 10001 --gid evalcascade --home-dir /data --no-create-home \
       --shell /usr/sbin/nologin evalcascade \
    && mkdir -p /data \
    && chown evalcascade:evalcascade /data

ENV PATH="/app/.venv/bin:${PATH}" \
    EVALCASCADE_HOME=/data \
    EVALCASCADE_DASHBOARD_DIR=/app/dashboard \
    EVALCASCADE_DISABLE_DOTENV=1

USER evalcascade
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); sys.exit(0 if r.status == 200 else 1)"]

# Binding 0.0.0.0 is required inside the container. Publish the port on 127.0.0.1 only, or
# set EVALCASCADE_API_TOKEN before exposing it more widely.
CMD ["evalcascade", "serve", "--host", "0.0.0.0", "--port", "8000"]
