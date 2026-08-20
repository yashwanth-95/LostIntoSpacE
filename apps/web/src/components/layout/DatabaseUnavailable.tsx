import { Card } from '@/components/ui';

/**
 * Shown when a database-backed page cannot reach PostgreSQL.
 *
 * Deliberately specific. "Something went wrong" tells a developer nothing they
 * can act on, and this failure has exactly one common cause during setup: the
 * database role, the database itself, or the migrations are not there yet. The
 * commands below are the ones from docs/getting-started/LOCAL_SETUP.md.
 *
 * Pages that do not need the database (Rocket Lab, Builder, Launch, Mission
 * Control, Search, the assistant) keep working while this is true, which is why
 * this is a panel on one page rather than a whole-app error.
 */
export function DatabaseUnavailable({ what = 'This data' }: { what?: string }) {
  return (
    <Card className="space-y-4 border-severity-warning/30">
      <div>
        <h2 className="font-display text-sm font-semibold text-space-100 mb-1">
          {what} needs the database
        </h2>
        <p className="text-xs text-space-400 leading-relaxed">
          The API is running but cannot reach PostgreSQL. Everything that does not need stored
          data — Rocket Lab, the Builder, Launch, Mission Control, Search and the assistant —
          still works.
        </p>
      </div>

      <div>
        <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1.5">To fix it</h3>
        <ol className="space-y-2 text-2xs text-space-400 leading-relaxed list-decimal list-inside">
          <li>
            Create the role and databases:
            <pre className="mt-1 p-2 rounded bg-space-950/70 border border-space-800 overflow-x-auto text-space-300">
{`psql -h 127.0.0.1 -U postgres -d postgres \\
  -v app_password="'your-password'" \\
  -f database/scripts/setup_local_db.sql`}
            </pre>
          </li>
          <li>
            Put that password into <code className="text-space-300">DATABASE_URL</code> in your{' '}
            <code className="text-space-300">.env</code> — it still holds the example default.
          </li>
          <li>
            Apply the migrations:
            <pre className="mt-1 p-2 rounded bg-space-950/70 border border-space-800 overflow-x-auto text-space-300">
{`cd database && alembic upgrade head`}
            </pre>
          </li>
          <li>
            Load the seed data:
            <pre className="mt-1 p-2 rounded bg-space-950/70 border border-space-800 overflow-x-auto text-space-300">
{`python database/seeds/seed_all.py`}
            </pre>
          </li>
        </ol>
      </div>

      <p className="text-2xs text-space-600">
        Full instructions in <code>docs/getting-started/LOCAL_SETUP.md</code>. Check{' '}
        <code>/api/v1/health/ready</code> to confirm the connection.
      </p>
    </Card>
  );
}
