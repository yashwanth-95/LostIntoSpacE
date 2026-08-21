#!/usr/bin/env bash
# Start, stop and check the local LostIntoSpacE stack.
#
#   scripts/dev/stack.sh start     database, API and web
#   scripts/dev/stack.sh stop
#   scripts/dev/stack.sh status
#   scripts/dev/stack.sh reset-db  drop, migrate and reseed
#
# The database is a cluster owned by the current user rather than the system
# PostgreSQL service, so no sudo and no shared-instance surprises. It lives in
# $PGDATA (default ~/.lis-pgdata) and listens on 5433 to stay out of the way of
# anything already using 5432.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PGDATA="${PGDATA:-$HOME/.lis-pgdata}"
PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
PGPORT="${PGPORT:-5433}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
RUN_DIR="$ROOT/.run"
VENV="$ROOT/.venv"

mkdir -p "$RUN_DIR"

py() { "$VENV/bin/python" "$@"; }

load_env() {
  if [[ -f "$ROOT/.env" ]]; then
    set -a; . "$ROOT/.env"; set +a
  fi
  # The sibling Python trees are imported by path rather than installed.
  export PYTHONPATH="$ROOT/apps/api:$ROOT:$ROOT/packages/contracts/src${PYTHONPATH:+:$PYTHONPATH}"
}

db_running() { "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" -q 2>/dev/null; }

start_db() {
  if db_running; then echo "  database  already running on $PGPORT"; return; fi
  if [[ ! -d "$PGDATA" ]]; then
    echo "  database  initialising cluster at $PGDATA"
    "$PGBIN/initdb" -D "$PGDATA" -U lostintospace \
      --auth-local=trust --auth-host=trust -E UTF8 >/dev/null
  fi
  "$PGBIN/pg_ctl" -D "$PGDATA" -l "$RUN_DIR/postgres.log" \
    -o "-p $PGPORT -k /tmp -c listen_addresses=127.0.0.1" -w start >/dev/null
  psql -h 127.0.0.1 -p "$PGPORT" -U lostintospace -d postgres -qtAc \
    "ALTER ROLE lostintospace WITH PASSWORD 'lostintospace'" >/dev/null 2>&1 || true
  for db in lostintospace lostintospace_test; do
    psql -h 127.0.0.1 -p "$PGPORT" -U lostintospace -d postgres -qtAc \
      "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || \
      psql -h 127.0.0.1 -p "$PGPORT" -U lostintospace -d postgres -qtAc \
        "CREATE DATABASE $db OWNER lostintospace" >/dev/null
  done
  echo "  database  started on $PGPORT"
}

migrate_and_seed() {
  ( cd "$ROOT/database" && "$VENV/bin/alembic" upgrade head >/dev/null )
  py "$ROOT/database/seeds/seed_all.py"
  py "$ROOT/database/seeds/demo_data.py" 2>/dev/null | tail -2 || true
}

start_api() {
  if curl -sf "http://127.0.0.1:$API_PORT/api/v1/health" >/dev/null 2>&1; then
    echo "  api       already running on $API_PORT"; return
  fi
  ( cd "$ROOT/apps/api" && nohup "$VENV/bin/python" -m uvicorn src.main:app \
      --host 127.0.0.1 --port "$API_PORT" --log-level warning \
      >"$RUN_DIR/api.log" 2>&1 & echo $! >"$RUN_DIR/api.pid" )
  for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:$API_PORT/api/v1/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  echo "  api       started on $API_PORT"
}

start_web() {
  if curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1; then
    echo "  web       already running on $WEB_PORT"; return
  fi
  ( cd "$ROOT/apps/web" && nohup npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" \
      >"$RUN_DIR/web.log" 2>&1 & echo $! >"$RUN_DIR/web.pid" )
  for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 && break
    sleep 0.5
  done
  echo "  web       started on $WEB_PORT"
}

stop_one() {
  local name="$1" pidfile="$RUN_DIR/$1.pid"
  [[ -f "$pidfile" ]] || { echo "  $name       not running"; return; }
  local pid; pid="$(cat "$pidfile")"
  # Kill the process group: vite and uvicorn both spawn children.
  kill -TERM -- "-$(ps -o pgid= "$pid" 2>/dev/null | tr -d ' ')" 2>/dev/null \
    || kill "$pid" 2>/dev/null || true
  rm -f "$pidfile"
  echo "  $name       stopped"
}

case "${1:-start}" in
  start)
    load_env
    echo "Starting LostIntoSpacE"
    start_db
    migrate_and_seed
    start_api
    start_web
    echo
    echo "  Application   http://127.0.0.1:$WEB_PORT"
    echo "  API docs      http://127.0.0.1:$API_PORT/docs"
    ;;
  stop)
    stop_one web
    stop_one api
    "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop >/dev/null 2>&1 && echo "  database  stopped" || true
    ;;
  status)
    load_env
    db_running && echo "  database  up   ($PGPORT)" || echo "  database  down"
    curl -sf "http://127.0.0.1:$API_PORT/api/v1/health" >/dev/null 2>&1 \
      && echo "  api       up   ($API_PORT)" || echo "  api       down"
    curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1 \
      && echo "  web       up   ($WEB_PORT)" || echo "  web       down"
    ;;
  reset-db)
    load_env
    psql -h 127.0.0.1 -p "$PGPORT" -U lostintospace -d postgres -qc \
      "DROP DATABASE IF EXISTS lostintospace" >/dev/null
    psql -h 127.0.0.1 -p "$PGPORT" -U lostintospace -d postgres -qc \
      "CREATE DATABASE lostintospace OWNER lostintospace" >/dev/null
    migrate_and_seed
    echo "  database  reset"
    ;;
  *)
    echo "usage: $0 {start|stop|status|reset-db}" >&2; exit 2 ;;
esac
