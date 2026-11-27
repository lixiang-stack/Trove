# syntax=docker/dockerfile:1
ARG UV_VERSION=0.12.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

ARG INSTALL_ASR=true

# The locked dependencies install from wheels or pure-Python sdists; crcmod
# falls back to its pure-Python implementation when no compiler is present.
# The uv cache survives lockfile changes, so dependency rebuilds reuse wheels.
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    if [ "${INSTALL_ASR}" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra asr; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    HOME=/home/trove

# Keep apt packages in their own layer; changing app paths or build metadata
# must not invalidate this download.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        curl \
        ffmpeg \
        libgomp1 \
        libsndfile1 \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 trove \
    && useradd --uid 10001 --gid trove --create-home --home-dir /home/trove \
        --shell /usr/sbin/nologin trove \
    && install -d -o trove -g trove -m 0700 \
        /home/trove/Trove /home/trove/Trove/models

# Dependencies are stable across source changes and stay in their own layer.
COPY --from=builder /app/.venv /app/.venv
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/trove-entrypoint
COPY --chmod=0755 docker/trove /usr/local/bin/trove
COPY src /app/src
ENV PYTHONPATH=/app/src

# Runtime paths and build metadata go last so releases only rebuild tiny layers.
ARG TROVE_BUILD_COMMIT=unknown
ARG TROVE_BUILD_TIME=unknown
ENV MODELSCOPE_CACHE=/home/trove/Trove/models \
    TROVE_BUILD_COMMIT=${TROVE_BUILD_COMMIT} \
    TROVE_BUILD_TIME=${TROVE_BUILD_TIME}

WORKDIR /app
USER trove
VOLUME ["/home/trove/Trove"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "--fail", "--silent", "--show-error", "http://127.0.0.1:8765/api/health"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/trove-entrypoint"]
CMD ["serve", "--no-worker"]
