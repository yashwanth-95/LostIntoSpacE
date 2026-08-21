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

# Third-party dependencies first, in their own layer, so that editing source
# does not reinstall scipy every build.
#
# Listed here rather than read out of the manifests: deriving them in the
# Dockerfile needs a shell substitution that has to word-split correctly, and
# getting that subtly wrong installs one package named after the whole list.
# These mirror `pyproject.toml` and `apps/api/pyproject.toml`; the editable
# installs below re-resolve them, so a drift costs a slower build rather than a
# broken image.
RUN pip install --upgrade pip \
 && pip install \
      'pydantic>=2.7,<3.0' 'pydantic-settings>=2.3,<3.0' 'python-dotenv>=1.0,<2.0' \
      'httpx>=0.24' 'numpy>=1.21' scipy \
      'fastapi>=0.115,<1.0' 'uvicorn[standard]>=0.30,<1.0' \
      'sqlalchemy[asyncio]>=2.0,<3.0' 'asyncpg>=0.29,<1.0' 'alembic>=1.13,<2.0' \
      'bcrypt>=4.1,<5.1' 'python-jose[cryptography]>=3.3,<4.0' 'email-validator>=2.0,<3.0'

COPY . .

# Then the local packages themselves.
#
# This has to come after `COPY . .`: the root pyproject names its packages
# explicitly — `data`, `search`, `ai`, and `contracts` mapped in from
# `packages/contracts/src` — so those directories must exist for the editable
# build to resolve them. Installing before copying is how this failed.
#
# Not `--no-deps`: apps/api declares fastapi, sqlalchemy, bcrypt and the rest,
# and skipping them produces an image that builds and then cannot import its
# own entrypoint.
RUN pip install -e . \
 && pip install -e ./apps/api

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
