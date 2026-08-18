<![CDATA[# SIH Demo Runbook

## Demo Flow (8–10 minutes)

### Act 1: Hook (1 min)
**Show**: Landing page with animated space background
**Say**: "LostIntoSpacE bridges the gap between curiosity and engineering."
**Fallback**: Pre-recorded landing page video

### Act 2: Explore (1.5 min)
**Show**: Search for "Mars" → Object detail page → related missions
**Say**: "Explore 1000+ space objects with real NASA data"
**Fallback**: Pre-loaded search results from bundled data

### Act 3: Learn (1 min)
**Show**: Click related concept → Lesson page with equations
**Say**: "Every concept links to interactive lessons"
**Fallback**: Static lesson content, no API needed

### Act 4: Build (2 min)
**Show**: Create project → Mission setup → Vehicle builder
- Add stages, set thrust/Isp/mass
- 3D model updates in real-time
- Validation shows stability margin
**Say**: "Students design rockets with real engineering parameters"
**Fallback**: Load pre-configured vehicle from .rkt file

### Act 5: Simulate — Fail (1.5 min)
**Show**: Click Launch → 3D visualization → Telemetry graphs
- Rocket fails (insufficient stability or low TWR)
- Failure event appears
**Say**: "The simulation uses real physics — and failures teach"
**Fallback**: Pre-computed simulation replay

### Act 6: Understand (1 min)
**Show**: "Why Did It Fail?" panel
- AI explains with scientific context
- Links to relevant equations and lessons
**Say**: "AI explains deterministic results — never invents physics"
**Fallback**: Pre-generated explanation (no live AI call)

### Act 7: Improve & Retry (1 min)
**Show**: Modify design → Re-simulate → Improved result
**Say**: "The learn-build-fail-understand loop is the core innovation"
**Fallback**: Load second pre-configured vehicle showing success

### Act 8: Close (30 sec)
**Show**: Export .rkt → Generated report
**Say**: "Save, share, and continue learning"

---

## Demo Modes

### Mode A — LIVE
Real interactions, real API calls, real simulation.
**Risk**: Network issues, slow API, unexpected errors.

### Mode B — GUIDED
Pre-seeded database, known-good vehicle configs, cached API responses.
**Risk**: Still requires running backend.

### Mode C — OFFLINE
Everything bundled. Static data. Pre-computed simulations.
**Risk**: None (fully deterministic).

**Strategy**: Start in Mode A. If anything fails, seamlessly switch to B or C.

---

## Pre-Demo Checklist

- [ ] Backend running and healthy (`/api/v1/health` returns 200)
- [ ] Database seeded with demo data
- [ ] Frontend built and tested
- [ ] Demo user account created
- [ ] Pre-configured vehicles loaded
- [ ] Pre-computed simulation results cached
- [ ] Offline fallback data bundled
- [ ] Network tested (or hotspot ready)
- [ ] Browser cleared (no cache conflicts)
- [ ] Screen resolution set (1920x1080)
- [ ] Presenter mode rehearsed 2x

## Recovery Procedures

| Failure | Recovery |
|---------|----------|
| Backend down | Switch to Mode C (offline) |
| Database error | Restart, use SQLite fallback |
| 3D rendering broken | Show 2D trajectory plot |
| AI API timeout | Show pre-generated explanation |
| Simulation hangs | Load pre-computed result |
| Network down | Switch to Mode C |
| Browser crash | Open backup browser tab |
]]>
