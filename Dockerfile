# wosarcher: API, CLI, and the built web UI in one image.
#
#   docker build -t wosarcher .
#   docker run -p 8765:8765 -v wosarcher:/data \
#     -e WOSARCHER_AUTH__PASSWORD_HASH='scrypt$...' wosarcher
#
# See README.md, "Docker".

# --- Frontend build -----------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /app/web
RUN corepack enable && corepack prepare pnpm@11.9.0 --activate
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

# --- Backend build ------------------------------------------------------------
# Same base as the runtime stage, so the virtual environment's interpreter
# path is identical and the copied .venv works unchanged.
FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first: this layer is reused until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY docs/design.md docs/design.md
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

# --- Runtime ------------------------------------------------------------------
FROM python:3.13-slim
RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin wosarcher \
    && mkdir -p /data \
    && chown wosarcher:wosarcher /data
COPY --from=backend /app/.venv /app/.venv
COPY --from=web /app/web/dist /app/web/dist

# Config (profiles, password hash, tokens), runs, and caches all live under
# /data, so one volume keeps everything across upgrades.
ENV PATH=/app/.venv/bin:$PATH \
    XDG_CONFIG_HOME=/data/config \
    XDG_DATA_HOME=/data/share \
    XDG_CACHE_HOME=/data/cache \
    WOSARCHER_SERVER__STATIC_DIR=/app/web/dist \
    PYTHONUNBUFFERED=1

USER wosarcher
WORKDIR /data
VOLUME /data
EXPOSE 8765

# Binding 0.0.0.0 inside the container needs an admin password: set
# WOSARCHER_AUTH__PASSWORD_HASH (from `wosarcher auth set-password --print`)
# or run `wosarcher auth set-password` in the container once.
CMD ["wosarcher", "serve", "--host", "0.0.0.0", "--port", "8765"]
