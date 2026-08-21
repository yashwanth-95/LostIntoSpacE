/**
 * The application shell and route table.
 *
 * Two layouts, deliberately:
 *
 * - **`PublicLayout`** — the landing page, help, and the auth screens. Full
 *   bleed, no sidebar. A first-time visitor should meet the product, not a
 *   dashboard chrome they have no use for yet.
 * - **`AppShell`** — everything you *do* something in: explore, learn, build,
 *   launch, monitor. Persistent sidebar and command bar.
 *
 * Every route below the shell works for a guest. `RequireAuth` guards only the
 * routes that are genuinely per-user (the workspace), because sign-in exists
 * here to enable persistence, not to gate the product.
 *
 * Pages are lazy-loaded. Mission Control pulls in Three.js, which is by far the
 * heaviest thing in the bundle, and someone reading the landing page should not
 * pay for a 3D renderer they may never open.
 */

import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes, useParams } from 'react-router-dom';

import { AppShell } from '@/components/layout/AppShell';
import { PublicLayout } from '@/components/layout/PublicLayout';
import { RequireAuth } from '@/components/layout/RequireAuth';
import { RouteError } from '@/components/layout/RouteError';
import { PageLoader } from '@/components/layout/PageLoader';
import { useSessionRestore } from '@/hooks/useSessionRestore';

const Landing = lazy(() => import('@/pages/Landing'));
const ScienceTopic = lazy(() => import('@/pages/ScienceTopic'));
const Experiments = lazy(() => import('@/pages/Experiments'));
const ExperimentDetail = lazy(() => import('@/pages/ExperimentDetail'));
const MissionDetail = lazy(() => import('@/pages/MissionDetail'));
const Evaluation = lazy(() => import('@/pages/Evaluation'));
const Compare = lazy(() => import('@/pages/Compare'));
const Assets = lazy(() => import('@/pages/Assets'));
const Explore = lazy(() => import('@/pages/Explore'));
const ObjectDetail = lazy(() => import('@/pages/ObjectDetail'));
const Catalog = lazy(() => import('@/pages/Catalog'));
const Learn = lazy(() => import('@/pages/Learn'));
const RocketLab = lazy(() => import('@/pages/RocketLab'));
const Builder = lazy(() => import('@/pages/Builder'));
const Launch = lazy(() => import('@/pages/Launch'));
const MissionControl = lazy(() => import('@/pages/MissionControl'));
const Missions = lazy(() => import('@/pages/Missions'));
const SearchPage = lazy(() => import('@/pages/SearchPage'));
const Assistant = lazy(() => import('@/pages/Assistant'));
const Workspace = lazy(() => import('@/pages/Workspace'));
const Help = lazy(() => import('@/pages/Help'));
const Login = lazy(() => import('@/pages/Login'));
const Signup = lazy(() => import('@/pages/Signup'));
const NotFound = lazy(() => import('@/pages/NotFound'));

/** `/lessons/:slug` was the old path for what is now `/learn/:slug`. */
function LessonRedirect() {
  const { slug } = useParams();
  return <Navigate to={`/learn/${slug ?? ''}`} replace />;
}

export function App() {
  useSessionRestore();

  return (
    <RouteError>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public — full bleed, no shell chrome */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/help" element={<Help />} />
            <Route path="/help/:topic" element={<Help />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
          </Route>

          {/* The application. Everything here works as a guest. */}
          <Route element={<AppShell />}>
            <Route path="/explore" element={<Explore />} />
            <Route path="/explore/:objectId" element={<ObjectDetail />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="/learn/:slug" element={<ScienceTopic />} />
            <Route path="/experiments" element={<Experiments />} />
            <Route path="/experiments/:experimentId" element={<ExperimentDetail />} />
            <Route path="/rocket-lab" element={<RocketLab />} />
            <Route path="/builder" element={<Builder />} />
            <Route path="/launch" element={<Launch />} />
            <Route path="/mission-control" element={<MissionControl />} />
            <Route path="/missions" element={<Missions />} />
            <Route path="/missions/:missionId" element={<MissionDetail />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/assets" element={<Assets />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/assistant" element={<Assistant />} />

            {/* Genuinely per-user */}
            <Route
              path="/workspace"
              element={
                <RequireAuth>
                  <Workspace />
                </RequireAuth>
              }
            />

            {/* Paths from earlier navigation structures, kept working rather
                than 404ing. `/catalog` and `/explore` were two names for one
                data set; `/lessons` is now `/learn`. */}
            <Route path="/simulator" element={<Navigate to="/mission-control" replace />} />
            <Route path="/projects" element={<Navigate to="/workspace" replace />} />
            <Route path="/settings" element={<Navigate to="/workspace" replace />} />
            <Route path="/lessons" element={<Navigate to="/learn" replace />} />
            <Route path="/lessons/:slug" element={<LessonRedirect />} />
            <Route path="/report" element={<Navigate to="/evaluation" replace />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </RouteError>
  );
}

export default App;
