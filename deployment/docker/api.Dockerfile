# LostIntoSpacE API + Python flight simulation.
#
# The simulation engine, the data adapters, the search index and the AI
# grounding all live in sibling trees rather than published packages, so the
# image copies the repository root and puts it on PYTHONPATH — the same wiring
# `_bootstrap.py` does for tests.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build dependencies for scipy/numpy wheels that have no manylinux build.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY apps/api/pyproject.toml apps/api/
RUN pip install --upgrade pip \
 && pip install -e . \
 && pip install -e ./apps/api \
 && pip install scipy alembic asyncpg 'uvicorn[standard]'

COPY . .

ENV PYTHONPATH=/app:/app/packages/contracts/src

# A non-root runtime user: nothing in this container needs to write to its own
# code, and an untrusted `.rkt` upload should never meet a root process.
RUN useradd --create-home --uid 10001 lostintospace \
 && chown -R lostintospace:lostintospace /app
USER lostintospace

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

WORKDIR /app/apps/api
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
