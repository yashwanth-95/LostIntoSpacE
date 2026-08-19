"""Sample simulation runs, built from Person 3's documented specification.

**These are constructed, not recorded.** The `simulation/` package contains
only `.gitkeep` files at the time of writing — there is no engine to run and no
output to capture. Every field name, event type, severity level, failure rule
and unit here comes from `docs/simulation/SIMULATION.md`, so these exercise the
contract P3 published rather than one invented for convenience.

When the engine lands, these should be replaced with real recorded runs. The
parser is deliberately tolerant of shape differences so that swap does not
require rewriting the analysis.
"""

__all__ = [
    "TWR_FAILURE",
    "MAX_Q_FAILURE",
    "STRUCTURAL_FAILURE",
    "FUEL_EXHAUSTION",
    "INSTABILITY_FAILURE",
    "SUCCESSFUL_RUN",
    "UNDOCUMENTED_FAILURE",
    "MALFORMED_RUN",
    "ALL_RUNS",
]


def _telemetry(rows):
    """Rows of (t, altitude_m, velocity_ms, accel_ms2, q_pa, mass_kg)."""
    return [
        {
            "time_s": row[0],
            "altitude_m": row[1],
            "velocity_ms": row[2],
            "acceleration_ms2": row[3],
            "dynamic_pressure_pa": row[4],
            "mass_kg": row[5],
        }
        for row in rows
    ]


#: Thrust-to-weight below 1.0 at ignition — the vehicle never leaves the pad.
TWR_FAILURE = {
    "id": "sim-twr-001",
    "succeeded": False,
    "outcome": "Vehicle failed to lift off",
    "termination_reason": "Critical failure event",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {
            "time_s": 0.0,
            "event_type": "failure_insufficient_twr",
            "severity": "fatal",
            "phase": "PRELAUNCH",
            "message": "thrust/weight = 0.87 at ignition",
            "thrust_n": 780000.0,
            "weight_n": 896000.0,
        },
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 0.0, 0.0, 91300.0),
        (0.5, 0.0, 0.0, 0.0, 0.0, 91100.0),
    ]),
}

#: Dynamic pressure exceeds the configured limit during ascent.
MAX_Q_FAILURE = {
    "id": "sim-maxq-002",
    "succeeded": False,
    "outcome": "Airframe exceeded dynamic pressure limit",
    "termination_reason": "Critical failure event",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {"time_s": 1.2, "event_type": "liftoff", "severity": "info"},
        {"time_s": 38.0, "event_type": "supersonic", "severity": "info"},
        {
            "time_s": 48.5,
            "event_type": "failure_excessive_q",
            "severity": "critical",
            "phase": "POWERED",
            "component": "interstage",
            "message": "dynamic pressure 58200 Pa exceeded limit 45000 Pa",
            "dynamic_pressure_pa": 58200.0,
            "limit_pa": 45000.0,
        },
        {
            "time_s": 91.0,
            "event_type": "impact",
            "severity": "critical",
            "message": "altitude reached zero",
        },
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 12.4, 0.0, 42000.0),
        (20.0, 2100.0, 240.0, 14.1, 21000.0, 34000.0),
        (38.0, 8400.0, 402.0, 16.8, 41000.0, 27000.0),
        (48.5, 13100.0, 486.0, 18.2, 58200.0, 23000.0),
        (60.0, 18000.0, 410.0, -9.8, 30000.0, 23000.0),
        (91.0, 0.0, -310.0, -9.8, 12000.0, 23000.0),
    ]),
}

#: Acceleration exceeds the configured structural g-limit late in the burn.
STRUCTURAL_FAILURE = {
    "id": "sim-struct-003",
    "succeeded": False,
    "outcome": "Structural limit exceeded during ascent",
    "termination_reason": "Critical failure event",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {"time_s": 1.0, "event_type": "liftoff", "severity": "info"},
        {"time_s": 44.0, "event_type": "max_q", "severity": "info"},
        {
            "time_s": 62.0,
            "event_type": "failure_structural_overload",
            "severity": "critical",
            "phase": "POWERED",
            "component": "stage-1 tank",
            "message": "acceleration 91.4 m/s^2 exceeded g-limit 78.5 m/s^2",
            "acceleration_ms2": 91.4,
            "limit_ms2": 78.5,
        },
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 11.2, 0.0, 48000.0),
        (30.0, 5200.0, 320.0, 21.0, 33000.0, 33000.0),
        (44.0, 11800.0, 470.0, 38.4, 44100.0, 26000.0),
        (62.0, 24500.0, 780.0, 91.4, 18000.0, 14000.0),
    ]),
}

#: Propellant runs out before the stage completes its job.
FUEL_EXHAUSTION = {
    "id": "sim-fuel-004",
    "succeeded": False,
    "outcome": "Second stage exhausted propellant before orbital insertion",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {"time_s": 148.0, "event_type": "meco", "severity": "info"},
        {"time_s": 152.0, "event_type": "staging", "severity": "info"},
        {
            "time_s": 402.0,
            "event_type": "failure_fuel_exhaustion",
            "severity": "critical",
            "phase": "POWERED",
            "component": "stage-2",
            "message": "propellant depleted with 1240 m/s of delta-v remaining",
            "delta_v_shortfall_ms": 1240.0,
        },
        {"time_s": 640.0, "event_type": "apogee", "severity": "info"},
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 12.0, 0.0, 52000.0),
        (148.0, 62000.0, 2400.0, 34.0, 200.0, 12000.0),
        (402.0, 180000.0, 6300.0, 8.2, 0.0, 2100.0),
    ]),
}

#: Static margin goes negative — the vehicle is aerodynamically unstable.
INSTABILITY_FAILURE = {
    "id": "sim-stab-005",
    "succeeded": False,
    "outcome": "Vehicle became aerodynamically unstable",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {"time_s": 0.9, "event_type": "liftoff", "severity": "info"},
        {
            "time_s": 6.4,
            "event_type": "failure_instability",
            "severity": "critical",
            "phase": "POWERED",
            "message": "static margin -0.42 calibres; CP ahead of CG",
            "static_margin_cal": -0.42,
        },
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 9.4, 0.0, 1200.0),
        (6.4, 180.0, 62.0, 11.0, 2400.0, 980.0),
    ]),
}

#: A run that succeeded. Analysis must handle it without inventing a failure.
SUCCESSFUL_RUN = {
    "id": "sim-ok-006",
    "succeeded": True,
    "outcome": "Target orbit achieved",
    "engine_version": "sim-0.3.1",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {"time_s": 1.1, "event_type": "liftoff", "severity": "info"},
        {"time_s": 51.0, "event_type": "max_q", "severity": "info"},
        {"time_s": 160.0, "event_type": "meco", "severity": "info"},
        {"time_s": 164.0, "event_type": "staging", "severity": "info"},
    ],
    "telemetry": _telemetry([
        (0.0, 0.0, 0.0, 12.0, 0.0, 50000.0),
        (51.0, 12000.0, 480.0, 24.0, 41000.0, 30000.0),
        (480.0, 402000.0, 7670.0, 2.1, 0.0, 4200.0),
    ]),
}

#: A failure identifier the engine's documentation does not list. The analysis
#: must say it cannot attribute the cause rather than guess at one.
UNDOCUMENTED_FAILURE = {
    "id": "sim-unknown-007",
    "succeeded": False,
    "outcome": "Run terminated by an unrecognised condition",
    "events": [
        {"time_s": 0.0, "event_type": "ignition", "severity": "info"},
        {
            "time_s": 33.0,
            "event_type": "failure_quantum_flux_inversion",
            "severity": "critical",
            "message": "not a documented failure mode",
        },
    ],
    "telemetry": _telemetry([(0.0, 0.0, 0.0, 10.0, 0.0, 5000.0)]),
}

#: A payload with unexpected field names and extra keys, to prove the parser
#: degrades rather than raising.
MALFORMED_RUN = {
    "run_identifier": "sim-weird-008",
    "status": "failed",
    "occurrences": [{"t": 12.0, "kind": "failure_excessive_q", "level": "critical"}],
    "samples": [{"t": 12.0, "alt_m": 900.0, "v": 210.0, "q": 51000.0}],
    "extra_diagnostic_channel": {"noise": True},
}

ALL_RUNS = {
    "twr": TWR_FAILURE,
    "max_q": MAX_Q_FAILURE,
    "structural": STRUCTURAL_FAILURE,
    "fuel": FUEL_EXHAUSTION,
    "instability": INSTABILITY_FAILURE,
    "success": SUCCESSFUL_RUN,
    "undocumented": UNDOCUMENTED_FAILURE,
    "malformed": MALFORMED_RUN,
}
