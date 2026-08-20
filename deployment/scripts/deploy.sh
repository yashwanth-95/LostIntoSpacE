#!/usr/bin/env bash
# Roll out a built version to an environment.
#
# Intentionally thin: it applies database migrations, then hands the actual
# rollout to whatever orchestrator the environment defines through
# DEPLOY_COMMAND. That keeps the choice of host (compose, k8s, a PaaS) out of
# the repository while still making "migrate, then release" the enforced order.

set -euo pipefail

ENVIRONMENT="${1:?usage: deploy.sh <environment> <version>}"
VERSION="${2:?usage: deploy.sh <environment> <version>}"

echo "==> Deploying ${VERSION} to ${ENVIRONMENT}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set; refusing to deploy without a database target." >&2
  exit 1
fi

echo "==> Applying migrations"
(cd "$(dirname "$0")/../../database" && alembic upgrade head)

echo "==> Seeding reference data (idempotent)"
python -m database.seeds.seed_all

if [[ -z "${DEPLOY_COMMAND:-}" ]]; then
  echo "DEPLOY_COMMAND is not set. Migrations are applied; nothing was released." >&2
  echo "Set DEPLOY_COMMAND in the ${ENVIRONMENT} environment to complete rollout." >&2
  exit 0
fi

echo "==> Releasing"
VERSION="${VERSION}" ENVIRONMENT="${ENVIRONMENT}" bash -c "${DEPLOY_COMMAND}"
echo "==> Done"
