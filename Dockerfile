# wosarcher: the daemon (API and engine), the CLI client, and the built web UI in one image.
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

# --- Export tools -------------------------------------------------------------
# Pinned pandoc and Typst release binaries for report export (PDF and DOCX),
# each checked against its SHA-256. Only the two binaries reach the runtime.
FROM debian:trixie-slim AS tools
ARG TARGETARCH
ARG PANDOC_VERSION=3.7.0.2
ARG TYPST_VERSION=0.14.2
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) typst_arch=x86_64; \
             pandoc_sha=8f8f67fdd540b6519326b0ac49d5c55c5d5d15e43920e80a086e02c8aff83268; \
             typst_sha=a6044cbad2a954deb921167e257e120ac0a16b20339ec01121194ff9d394996d ;; \
      arm64) typst_arch=aarch64; \
             pandoc_sha=4ef2997ff0fa7f86ada5a217722f4f732293e38518b4442ececce16628bd0e44; \
             typst_sha=491b101aa40a3a7ea82a3f8a6232cabb4e6a7e233810082e5ac812d43fdcd47a ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o pandoc.tar.gz \
      "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-linux-${TARGETARCH}.tar.gz"; \
    echo "${pandoc_sha}  pandoc.tar.gz" | sha256sum -c -; \
    tar -xzf pandoc.tar.gz --strip-components=2 -C /usr/local/bin "pandoc-${PANDOC_VERSION}/bin/pandoc"; \
    curl -fsSL -o typst.tar.xz \
      "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-${typst_arch}-unknown-linux-musl.tar.xz"; \
    echo "${typst_sha}  typst.tar.xz" | sha256sum -c -; \
    tar -xJf typst.tar.xz --strip-components=1 -C /usr/local/bin "typst-${typst_arch}-unknown-linux-musl/typst"; \
    rm pandoc.tar.gz typst.tar.xz

# --- Runtime ------------------------------------------------------------------
FROM python:3.13-slim
RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin wosarcher \
    && mkdir -p /data \
    && chown wosarcher:wosarcher /data
COPY --from=backend /app/.venv /app/.venv
COPY --from=web /app/web/dist /app/web/dist
COPY --from=tools /usr/local/bin/pandoc /usr/local/bin/typst /usr/local/bin/

# Config (profiles, password hash, tokens), runs, and caches all live under
# /data, so one volume keeps everything across upgrades.
ENV PATH=/app/.venv/bin:$PATH \
    XDG_CONFIG_HOME=/data/config \
    XDG_DATA_HOME=/data/share \
    XDG_CACHE_HOME=/data/cache \
    WOSARCHER_SERVER__STATIC_DIR=/app/web/dist \
    WOSARCHER_SERVER__SOCKET=/tmp/wosarcher.sock \
    WOSARCHER_SOCKET=/tmp/wosarcher.sock \
    PYTHONUNBUFFERED=1

USER wosarcher
WORKDIR /data
VOLUME /data
EXPOSE 8765

# Binding 0.0.0.0 inside the container needs an admin password: set
# WOSARCHER_AUTH__PASSWORD_HASH (from `wosarcherd auth set-password --print`)
# or run `wosarcherd auth set-password` in the container once. The client
# (`docker exec wosarcher wosarcher runs`) uses the socket in /tmp.
CMD ["wosarcherd", "serve", "--host", "0.0.0.0", "--port", "8765"]
