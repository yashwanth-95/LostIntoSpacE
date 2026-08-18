<![CDATA[# Frontend — `apps/web/`

## Owner: P1 (Frontend / UX / 3D)

## Tech Stack
- React 18 + TypeScript
- Vite (build tool)
- React Three Fiber + Drei (3D)
- Tailwind CSS v3 (styling)
- Zustand (local state)
- TanStack Query (server state)
- React Router (routing)

## Page Tree (MVP)

```
/                       Landing
/explore                Space object catalog
/explore/:id            Object detail
/search                 Search results
/learn                  Lesson catalog
/learn/:slug            Lesson detail
/dashboard              User dashboard
/projects/:id           Project overview
/build/:missionId       Vehicle builder
/simulate/:missionId    Mission control + 3D
/analysis/:simId        Post-flight analysis
/reports/:id            Generated report
/login                  Auth - login
/register               Auth - register
/settings               User settings
```

## Allowed Imports
- `packages/contracts/` — shared types
- `packages/ui/` — shared UI components
- NO imports from `apps/api/`, `simulation/`, `scientific/`

## Key Directories
- `components/ui/` — Design system atoms (Button, Card, Input, Modal)
- `components/layout/` — Shell, Nav, Sidebar, Footer
- `components/features/` — Feature-specific components
- `pages/` — Route-level page components
- `hooks/` — Custom React hooks
- `lib/` — Utilities, API client, WebSocket client
- `stores/` — Zustand stores
- `services/` — API service functions
- `types/` — Frontend-specific types
- `styles/` — Global CSS, Tailwind config
- `assets/` — Static assets used by frontend
]]>
