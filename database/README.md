<![CDATA[# Database — `database/`

## Owner: P2 (Backend / Database)

## Structure
- `migrations/` — Alembic migration files (auto-generated + manual)
- `seeds/` — Seed data scripts (space objects, lessons, demo data)
- `scripts/` — DB admin scripts (reset, backup, etc.)

## Commands
```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Seed data
python seeds/seed_all.py
```

## Rules
- Never edit a released migration
- Always test migrations on a fresh database
- Seed data must be idempotent (safe to run multiple times)
]]>
