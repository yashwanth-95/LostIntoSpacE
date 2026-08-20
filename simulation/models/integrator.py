"""
Numerical integrators for second-order translational dynamics.

Ported from packages/simulation-engine/src/physics/integrator.ts — the two
implementations must stay numerically identical, and
`simulation/tests/test_cross_engine.py` asserts that they do.

The state being advanced is (position, velocity); acceleration is supplied by a
caller-provided function. Nothing here knows about rockets, which keeps the
integrator testable against analytic solutions (free fall, circular orbit) with
no vehicle model in the way.

Why mass is not part of the state
---------------------------------
Propellant flow is constant while an engine burns, so mass is *exactly* linear
in time: m(t) = m0 - mdot*(t - t0). Folding it into the RK4 state vector would
add error rather than remove it. The acceleration function evaluates mass
analytically at each substep time instead. This is operator splitting, and here
the split is exact.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from .gravity import Vec3, add, scale


class KinematicState(NamedTuple):
    """Position and velocity at one instant."""

    #: Position. Unit: m.
    position: Vec3
    #: Velocity. Unit: m/s.
    velocity: Vec3


#: Acceleration as a function of time, position and velocity. Unit: m/s².
#:
#: Must be pure: RK4 calls it four times per step at different substep times,
#: and a function with side effects will corrupt the result.
AccelerationFn = Callable[[float, Vec3, Vec3], Vec3]


def rk4_step(
    state: KinematicState,
    t: float,
    dt: float,
    accel: AccelerationFn,
) -> KinematicState:
    """
    Advance one step with classical fourth-order Runge-Kutta.

    Local truncation error is O(dt^5), global error O(dt^4). This is the
    engine's default: at the standard 0.05 s powered-flight step it tracks an
    analytic circular orbit to better than a metre per revolution, far below the
    fidelity of the force models feeding it.

    Args:
        state: Current position and velocity.
        t: Current time. Unit: s.
        dt: Timestep. Unit: s.
        accel: Acceleration function.

    Returns:
        The state at t + dt.
    """
    p0, v0 = state.position, state.velocity
    half = dt / 2.0

    a1 = accel(t, p0, v0)

    # k2 — midpoint using k1
    p2 = add(p0, scale(v0, half))
    v2 = add(v0, scale(a1, half))
    a2 = accel(t + half, p2, v2)

    # k3 — midpoint using k2
    p3 = add(p0, scale(v2, half))
    v3 = add(v0, scale(a2, half))
    a3 = accel(t + half, p3, v3)

    # k4 — endpoint using k3
    p4 = add(p0, scale(v3, dt))
    v4 = add(v0, scale(a3, dt))
    a4 = accel(t + dt, p4, v4)

    # Weighted average: (k1 + 2*k2 + 2*k3 + k4) / 6
    d_position = scale(add(add(v0, scale(add(v2, v3), 2.0)), v4), dt / 6.0)
    d_velocity = scale(add(add(a1, scale(add(a2, a3), 2.0)), a4), dt / 6.0)

    return KinematicState(add(p0, d_position), add(v0, d_velocity))


def euler_step(
    state: KinematicState,
    t: float,
    dt: float,
    accel: AccelerationFn,
) -> KinematicState:
    """
    Advance one step with explicit (forward) Euler.

    First-order and unconditionally energy-gaining for orbital motion, so it is
    unsuitable for flight. It exists as a teaching contrast: running the same
    mission under ``euler`` and ``rk4`` and watching the trajectories diverge is
    a good demonstration of why integrator choice matters.
    """
    a = accel(t, state.position, state.velocity)
    return KinematicState(
        add(state.position, scale(state.velocity, dt)),
        add(state.velocity, scale(a, dt)),
    )


def velocity_verlet_step(
    state: KinematicState,
    t: float,
    dt: float,
    accel: AccelerationFn,
) -> KinematicState:
    """
    Advance one step with velocity Verlet.

    Second-order and symplectic, so it conserves orbital energy over long coasts
    far better than its order suggests. Costs two acceleration evaluations per
    step against RK4's four.
    """
    a0 = accel(t, state.position, state.velocity)

    position = add(
        add(state.position, scale(state.velocity, dt)),
        scale(a0, 0.5 * dt * dt),
    )

    # Velocity at t+dt needs a(t+dt), which needs v(t+dt). Use the drift
    # estimate — exact for velocity-independent forces, first-order for drag.
    v_predicted = add(state.velocity, scale(a0, dt))
    a1 = accel(t + dt, position, v_predicted)

    return KinematicState(
        position,
        add(state.velocity, scale(add(a0, a1), 0.5 * dt)),
    )


_INTEGRATORS = {
    "rk4": rk4_step,
    "euler": euler_step,
    "velocity_verlet": velocity_verlet_step,
}


def get_integrator(method: str) -> Callable[..., KinematicState]:
    """
    Resolve an integrator method name to its step function.

    Args:
        method: One of ``rk4``, ``euler``, ``velocity_verlet``.

    Returns:
        The corresponding step function.

    Raises:
        ValueError: If the method is not recognised.
    """
    try:
        return _INTEGRATORS[method]
    except KeyError:
        raise ValueError(
            f"unknown integrator {method!r}; expected one of {sorted(_INTEGRATORS)}"
        ) from None
