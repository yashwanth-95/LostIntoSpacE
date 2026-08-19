"""Seed loaders.

OWNERSHIP BOUNDARY (DECISION_LOG #18): this package contains LOADING LOGIC ONLY.
The seed *content* - space object records, lesson text, fallback datasets - is
authored by P4 and lives in `data/seeds/` and `data/fallback/`. These scripts
read that content and upsert it into PostgreSQL.

Do not add data files here, and do not add loading logic to `data/seeds/`.

Every loader must be IDEMPOTENT: running it twice must leave the database in the
same state as running it once. For `space_objects` the partial unique index on
(source, source_id) is what makes that an upsert rather than a duplicate insert.
"""
