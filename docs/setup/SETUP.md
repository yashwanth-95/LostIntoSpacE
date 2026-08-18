<![CDATA[# Setup Guide

## Prerequisites

- **Node.js** 18+ (for frontend)
- **Python** 3.11+ (for backend & simulation)
- **PostgreSQL** 15+ (database)
- **Redis** (optional, for caching)
- **Git**

## Step 1 — Clone & Environment

```bash
git clone <repo-url>
cd LostIntoSpacE
cp .env.example .env
# Edit .env with your database credentials and API keys
```

## Step 2 — Database Setup

```bash
# Create database
createdb lostintospace

# Run migrations
cd database
pip install alembic psycopg2-binary
alembic upgrade head

# Seed initial data
python seeds/seed_all.py
```

## Step 3 — Backend Setup

```bash
cd apps/api
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

## Step 4 — Frontend Setup

```bash
cd apps/web
npm install
npm run dev
```

Frontend available at: `http://localhost:5173`

## Step 5 — Verify

1. Open `http://localhost:5173` — should see landing page
2. Open `http://localhost:8000/docs` — should see Swagger UI
3. Register a test account
4. Create a project

## Development Scripts

```bash
# From project root:
scripts/dev/start.sh        # Start all services
scripts/dev/reset_db.sh     # Drop & recreate database
scripts/dev/seed.sh         # Seed sample data
scripts/dev/test.sh         # Run all tests
```

## Environment Variables

See `.env.example` for all available variables with descriptions.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Database connection refused | Ensure PostgreSQL is running, check DATABASE_URL |
| Port 8000 in use | Kill existing process or change API_PORT |
| Node module errors | Delete `node_modules` and `npm install` |
| Python import errors | Ensure virtualenv is activated |
]]>
