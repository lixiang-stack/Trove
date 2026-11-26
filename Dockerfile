# syntax=docker/dockerfile:1
ARG UV_VERSION=0.12.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

ARG INSTALL_ASR=false
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN if [ "${INSTALL_ASR}" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra asr; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi
# Keep README out of the dependency layer: doc-only changes must not trigger a
# PyTorch download when rebuilding from another worktree.
COPY README.md ./
COPY src ./src
RUN if [ "${INSTALL_ASR}" = "true" ]; then \
        uv sync --frozen --no-dev --no-editable --extra asr; \
    else \
        uv sync --frozen --no-dev --no-editable; \
    fi

FROM python:3.12-slim-bookworm AS runtime

ARG TROVE_BUILD_COMMIT=unknown
ARG TROVE_BUILD_TIME=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    HOME=/home/trove \
    TROVE_HOME=/data \
    MODELSCOPE_CACHE=/data/models \
    TROVE_BIND=0.0.0.0 \
    TROVE_BUILD_COMMIT=${TROVE_BUILD_COMMIT} \
    TROVE_BUILD_TIME=${TROVE_BUILD_TIME}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        libgomp1 \
        libsndfile1 \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 trove \
    && useradd --uid 10001 --gid trove --create-home --home-dir /home/trove \
        --shell /usr/sbin/nologin trove \
    && install -d -o trove -g trove -m 0700 /data /data/models \
    && install -d -o trove -g trove -m 0700 /home/trove/.config/trove

COPY --from=builder /app/.venv /app/.venv
COPY docker/entrypoint.sh /usr/local/bin/trove-entrypoint
RUN chmod 0755 /usr/local/bin/trove-entrypoint \
    && chown -R root:root /app

WORKDIR /app
USER trove
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://127.0.0.1:8765/api/health"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/trove-entrypoint"]
CMD ["serve", "--no-worker", "--host", "0.0.0.0"]
