"""baseline: verify PostgreSQL capability

Creates no schema. Exists as the fixed root of the revision chain and to fail
early, with a clear message, on a PostgreSQL too old for the features the
schema relies on.

No `pgcrypto` extension is created: `gen_random_uuid()` has been built into
PostgreSQL core since 13, and ARCHITECTURE.md targets 15+. Requiring an
extension we do not need would add a superuser step on managed hosts for
nothing. (docs/backend/DATABASE_CONTRACT.md §10 originally listed pgcrypto;
that was over-cautious.)

Revision ID: 0001_baseline
Revises:
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 13 = gen_random_uuid() in core; 12 = generated columns (used by the FTS
# vectors in 0005). 13 is therefore the true floor.
MINIMUM_SERVER_VERSION_NUM = 130000


def upgrade() -> None:
    # Offline mode (`alembic upgrade --sql`) has no connection to query, so the
    # check is skipped rather than breaking SQL generation for DBA review.
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    version_num = bind.execute(sa.text("SHOW server_version_num")).scalar()
    if version_num is not None and int(version_num) < MINIMUM_SERVER_VERSION_NUM:
        raise RuntimeError(
            f"PostgreSQL {MINIMUM_SERVER_VERSION_NUM // 10000}+ is required "
            f"(found server_version_num={version_num}). The schema uses "
            "gen_random_uuid() from core and STORED generated columns."
        )


def downgrade() -> None:
    pass
