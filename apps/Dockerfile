# Atesta API and worker image (issue #236, hosted-environment spec). One build, two targets:
#   docker build -f apps/Dockerfile --target api -t atesta-api .
#   docker build -f apps/Dockerfile --target worker -t atesta-worker .
# The api target also runs migrations (ECS migrate task: alembic -c apps/api/alembic.ini upgrade
# head). Same pinned base as scanner/Dockerfile. Third-party packages install only by hash, from
# an export of uv.lock made at build time (so Dependabot's lock updates need no second file);
# Atesta's own packages build offline from this tree with the hash-locked hatchling. Runs as 10001
# on a read-only root; only /tmp is written.
FROM python:3.13.18-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM base AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY apps/api/pyproject.toml apps/api/
COPY apps/mcp/pyproject.toml apps/mcp/
COPY apps/worker/pyproject.toml apps/worker/
COPY scanner/pyproject.toml scanner/
COPY apps/build-requirements.txt /tmp/
RUN uv export --frozen --no-dev --package atesta-worker --no-emit-workspace \
      --format requirements-txt --no-header -o /tmp/requirements.txt \
 && python -m venv /opt/build \
 && /opt/build/bin/pip install --require-hashes -r /tmp/build-requirements.txt \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --no-deps -r /tmp/requirements.txt
COPY packages/core /src/packages/core
COPY apps/api /src/apps/api
COPY apps/mcp /src/apps/mcp
COPY apps/worker /src/apps/worker
RUN /opt/build/bin/pip wheel --no-deps --no-build-isolation --no-index -w /wheels \
      /src/packages/core /src/apps/api /src/apps/mcp /src/apps/worker \
 && /opt/venv/bin/pip install --no-deps --no-index /wheels/*.whl

FROM base AS runtime
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin atesta
COPY --from=build /opt/venv /opt/venv
COPY catalog /app/catalog
COPY scanner/expected /app/scanner/expected
COPY apps/api/alembic.ini /app/apps/api/alembic.ini
COPY apps/api/migrations /app/apps/api/migrations
ENV PATH=/opt/venv/bin:$PATH \
    ATESTA_CATALOG_DIR=/app/catalog \
    ATESTA_SCANNER_EXPECTED=/app/scanner/expected
WORKDIR /app
USER 10001

FROM runtime AS api
EXPOSE 8000
CMD ["uvicorn", "atesta_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-access-log"]

FROM runtime AS worker
CMD ["atesta-worker"]
