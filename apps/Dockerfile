# Atesta API and worker image (issue #236, hosted-environment spec). One build, two targets:
#   docker build -f apps/Dockerfile --target api -t atesta-api .
#   docker build -f apps/Dockerfile --target worker -t atesta-worker .
# The api target also runs migrations (ECS migrate task: alembic -c apps/api/alembic.ini upgrade
# head). Same pinned base as scanner/Dockerfile. Third-party packages install only by hash, from
# an export of uv.lock made at build time (so Dependabot's lock updates need no second file);
# Atesta's own packages build offline from this tree with the hash-locked hatchling. Runs as 10001
# on a read-only root; only /tmp is written.
FROM python:3.12.16-slim-trixie@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07 AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv

FROM base AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY apps/api/pyproject.toml apps/api/
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
COPY apps/worker /src/apps/worker
RUN /opt/build/bin/pip wheel --no-deps --no-build-isolation --no-index -w /wheels \
      /src/packages/core /src/apps/api /src/apps/worker \
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
