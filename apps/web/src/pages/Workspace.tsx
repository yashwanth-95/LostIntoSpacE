import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Card, EmptyState, Input, Spinner } from '@/components/ui';
import { DatabaseUnavailable } from '@/components/layout/DatabaseUnavailable';
import { auth, projects } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useMissionStore } from '@/stores/missionStore';
import type { Project } from '@/types';

/**
 * The signed-in workspace: projects, and the current unsaved work.
 *
 * The "current work" panel is here because the design and flight in the mission
 * store are in memory only. Someone who has just flown something should be able
 * to see, from one place, that it is not yet saved — rather than discovering it
 * by closing the tab.
 */
export default function Workspace() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const design = useMissionStore((s) => s.design);
  const result = useMissionStore((s) => s.result);

  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [dbDown, setDbDown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = () => {
    setLoading(true);
    projects
      .list()
      .then(({ items: rows }) => {
        setItems(rows);
        setDbDown(false);
        setError(null);
      })
      .catch((cause: unknown) => {
        const message = cause instanceof Error ? cause.message : 'Projects could not be loaded.';
        setDbDown(/database|unavailable|reach|connect/i.test(message));
        setError(message);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await projects.create({ name: newName.trim() });
      setNewName('');
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The project could not be created.');
    } finally {
      setCreating(false);
    }
  };

  const signOut = async () => {
    try {
      await auth.logout();
    } catch {
      /* the local session is cleared regardless */
    }
    logout();
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">Workspace</h1>
          <p className="text-sm text-space-400">
            {user ? `Signed in as ${user.name || user.email}` : 'Signed in'}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={signOut}>
          Sign out
        </Button>
      </header>

      {/* Current, unsaved work */}
      <Card className="space-y-3">
        <h2 className="font-display text-sm font-semibold text-space-200">Current work</h2>
        {design ? (
          <div className="space-y-2">
            <p className="text-xs text-space-300">
              <span className="text-space-100">{design.name}</span> —{' '}
              {design.stages.length} stage{design.stages.length === 1 ? '' : 's'},{' '}
              {design.components.length} components
              {result && (
                <>
                  {' · last flight: '}
                  <span
                    className={
                      result.outcome === 'success'
                        ? 'text-accent-emerald'
                        : 'text-severity-warning'
                    }
                  >
                    {result.outcome}
                  </span>
                </>
              )}
            </p>
            <p className="text-2xs text-severity-warning leading-relaxed">
              Held in memory only — closing the tab loses it. Saving designs and flights to a
              project is not wired up yet; see MVP_STATUS.md.
            </p>
            <div className="flex gap-2 pt-1">
              <Link to="/builder">
                <Button size="sm" variant="secondary">
                  Open in Builder
                </Button>
              </Link>
              {result && (
                <Link to="/mission-control">
                  <Button size="sm" variant="secondary">
                    Mission Control
                  </Button>
                </Link>
              )}
            </div>
          </div>
        ) : (
          <p className="text-xs text-space-400">
            Nothing in progress.{' '}
            <Link to="/rocket-lab" className="text-accent-cyan hover:underline">
              Start a rocket
            </Link>
            .
          </p>
        )}
      </Card>

      {/* Projects */}
      <section className="space-y-3">
        <h2 className="font-display text-sm font-semibold text-space-200">Projects</h2>

        {dbDown ? (
          <DatabaseUnavailable what="Your projects" />
        ) : (
          <>
            <form onSubmit={create} className="flex gap-2">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New project name…"
                aria-label="New project name"
                className="flex-1"
              />
              <Button type="submit" loading={creating} disabled={!newName.trim()}>
                Create
              </Button>
            </form>

            {error && !dbDown && (
              <p className="text-2xs text-severity-critical">{error}</p>
            )}

            {loading ? (
              <div className="flex justify-center py-10">
                <Spinner />
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                title="No projects yet"
                description="A project groups missions, rockets and simulation runs together."
              />
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((project) => (
                  <li key={project.id}>
                    <Card className="h-full space-y-1.5">
                      <h3 className="font-display text-sm font-semibold text-space-100">
                        {project.name}
                      </h3>
                      {project.description && (
                        <p className="text-2xs text-space-400 leading-relaxed line-clamp-2">
                          {project.description}
                        </p>
                      )}
                      <p className="text-2xs text-space-600">
                        {project.mission_count ?? 0} mission
                        {project.mission_count === 1 ? '' : 's'}
                      </p>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}
