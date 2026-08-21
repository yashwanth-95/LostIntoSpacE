#!/usr/bin/env python3
"""Check that the Python and TypeScript sides describe the same rocket.

This project runs its physics twice. `simulation/` is the authority — the
server flies every mission with it — and `packages/simulation-engine/` is a
TypeScript port that the builder uses to analyse a design live in the browser,
because a round trip per keystroke is not an interface.

Two implementations of one model drift. When they do, the builder shows a
delta-v the flight then disagrees with, and there is no error anywhere — just
two numbers that should match and do not. That failure is silent, which is
exactly the kind CI should be made to catch.

So this compares the two by structure rather than by behaviour:

1. **Telemetry and summary fields.** Every field the Python `TelemetryPoint` and
   `SimSummary` record must exist in the TypeScript interfaces the client reads
   them into, or the client silently drops data the engine produced.
2. **Enumerations.** Mission states, flight phases, stage statuses, failure
   subsystems and severities must agree member for member, or a state the
   engine emits renders as an unknown string.
3. **Physical constants.** Earth's radius, standard gravity, the gas constant,
   sea-level conditions — a disagreement here is a disagreement about physics.

What it deliberately does *not* do is compare trajectories. That needs both
engines running and is worth building; this is the cheap structural check that
catches the common case, which is someone adding a field to one side.

Exit codes: 0 agreement, 1 drift found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
TS_ENGINE = ROOT / "packages" / "simulation-engine" / "src"
WEB_TYPES = ROOT / "apps" / "web" / "src" / "types" / "simulation.ts"

#: Fields the Python contract carries that the TypeScript side is not expected
#: to mirror, with the reason. Anything not listed here must match.
TELEMETRY_EXEMPT: Dict[str, str] = {}

#: Constants to compare, as (description, python path, python name, ts file, ts name).
CONSTANT_CHECKS: List[Tuple[str, str, str, str, str]] = [
    ("standard gravity", "simulation/models/constants.py", "G0", "physics/constants.ts", "G0"),
    ("Earth radius", "simulation/models/constants.py", "R_EARTH", "physics/constants.ts", "R_EARTH"),
    ("sea-level temperature", "simulation/models/constants.py", "T0", "physics/constants.ts", "T0_SEA_LEVEL"),
    ("sea-level pressure", "simulation/models/constants.py", "P0", "physics/constants.ts", "P0_SEA_LEVEL"),
    ("ratio of specific heats", "simulation/models/constants.py", "GAMMA_AIR", "physics/constants.ts", "GAMMA_AIR"),
]

#: Enumerations to compare, as (description, python class, ts type name, ts file).
ENUM_CHECKS: List[Tuple[str, str, str, str]] = [
    ("mission state", "MissionState", "MissionState", "sim/mission-state.ts"),
    ("flight phase", "FlightPhase", "FlightPhase", "sim/state.ts"),
    ("stage status", "StageStatus", "StageStatus", "sim/state.ts"),
    ("failure subsystem", "FailureSubsystem", "FailureSubsystem", "sim/events.ts"),
    ("event severity", "EventSeverity", "EventSeverity", "sim/events.ts"),
    ("sim outcome", "SimOutcome", "SimOutcome", "sim/events.ts"),
]

_PROBLEMS: List[str] = []
_CHECKS_RUN = 0


def problem(message: str) -> None:
    _PROBLEMS.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def ts_interface_fields(source: str, name: str) -> Set[str]:
    """Field names of a TypeScript interface, ignoring comments and nesting."""
    match = re.search(
        r"(?:export\s+)?interface\s+" + re.escape(name) + r"\b[^{]*\{", source
    )
    if not match:
        return set()

    depth = 0
    body_start = match.end() - 1
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body = source[body_start + 1 : index]
                break
    else:
        return set()

    # Strip comments before looking for field declarations, so a field name
    # mentioned in a doc comment is not mistaken for a declaration.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return set(re.findall(r"^\s*(?:readonly\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\??\s*:", body, re.M))


def ts_union_members(source: str, name: str) -> Set[str]:
    """String-literal members of a TypeScript union or enum."""
    union = re.search(
        r"(?:export\s+)?type\s+" + re.escape(name) + r"\s*=\s*([^;]+);", source, re.S
    )
    if union:
        return set(re.findall(r"['\"]([^'\"]+)['\"]", union.group(1)))

    enum = re.search(
        r"(?:export\s+)?enum\s+" + re.escape(name) + r"\s*\{([^}]*)\}", source, re.S
    )
    if enum:
        return set(re.findall(r"=\s*['\"]([^'\"]+)['\"]", enum.group(1)))

    const = re.search(
        r"(?:export\s+)?const\s+" + re.escape(name) + r"\s*=\s*\[([^\]]*)\]", source, re.S
    )
    if const:
        return set(re.findall(r"['\"]([^'\"]+)['\"]", const.group(1)))

    return set()


def ts_number(source: str, name: str) -> float | None:
    """The numeric value of an exported TypeScript constant."""
    match = re.search(
        r"(?:export\s+)?const\s+" + re.escape(name) + r"(?:\s*:\s*number)?\s*=\s*([0-9_.eE+\-*/ ()]+);",
        source,
    )
    if not match:
        return None
    expression = match.group(1).replace("_", "").strip()
    try:
        # The expression comes from our own source and matched a numeric-only
        # character class above, so there is nothing here to execute.
        return float(eval(expression, {"__builtins__": {}}, {}))
    except Exception:
        return None


def python_number(path: Path, name: str) -> float | None:
    match = re.search(
        r"^" + re.escape(name) + r"\s*(?::\s*float)?\s*=\s*([0-9_.eE+\-*/ ()]+)",
        read(path),
        re.M,
    )
    if not match:
        return None
    try:
        return float(eval(match.group(1).replace("_", ""), {"__builtins__": {}}, {}))
    except Exception:
        return None


def check_telemetry_fields() -> None:
    """Every Python telemetry field must have somewhere to land on the client."""
    global _CHECKS_RUN
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "packages" / "contracts" / "src"))
    from simulation.contracts import SimSummary, TelemetryPoint

    web = read(WEB_TYPES)
    if not web:
        problem("apps/web/src/types/simulation.ts is missing; the client has no contract at all.")
        return

    for model, interface in ((TelemetryPoint, "TelemetryPoint"), (SimSummary, "SimSummary")):
        _CHECKS_RUN += 1
        ts_fields = ts_interface_fields(web, interface)
        if not ts_fields:
            problem("Could not find interface {0} in {1}.".format(interface, WEB_TYPES.name))
            continue
        missing = set(model.model_fields) - ts_fields - set(TELEMETRY_EXEMPT)
        if missing:
            problem(
                "{0}: the engine emits {1} that the client cannot read: {2}. "
                "Add them to {3} or the data is silently dropped.".format(
                    interface,
                    "a field" if len(missing) == 1 else "fields",
                    ", ".join(sorted(missing)),
                    WEB_TYPES.name,
                )
            )


def check_enums() -> None:
    """A state one engine can emit and the other cannot name is a bug waiting."""
    global _CHECKS_RUN
    import simulation.contracts as contracts

    for description, py_name, ts_name, ts_file in ENUM_CHECKS:
        _CHECKS_RUN += 1
        enum = getattr(contracts, py_name, None)
        if enum is None:
            problem("Python contract has no {0!r} enum.".format(py_name))
            continue

        source = read(TS_ENGINE / ts_file)
        if not source:
            problem("Missing TypeScript source {0}.".format(ts_file))
            continue

        ts_members = ts_union_members(source, ts_name)
        if not ts_members:
            problem(
                "Could not find {0!r} in {1}; the {2} enum has no TypeScript counterpart.".format(
                    ts_name, ts_file, description
                )
            )
            continue

        py_members = {member.value for member in enum}
        only_python = py_members - ts_members
        only_ts = ts_members - py_members
        if only_python:
            problem(
                "{0}: Python has {1} that TypeScript does not.".format(
                    description, ", ".join(sorted(only_python))
                )
            )
        if only_ts:
            problem(
                "{0}: TypeScript has {1} that Python does not.".format(
                    description, ", ".join(sorted(only_ts))
                )
            )


def check_constants() -> None:
    """A disagreement about a constant is a disagreement about physics."""
    global _CHECKS_RUN
    for description, py_file, py_name, ts_file, ts_name in CONSTANT_CHECKS:
        _CHECKS_RUN += 1
        py_value = python_number(ROOT / py_file, py_name)
        ts_value = ts_number(read(TS_ENGINE / ts_file), ts_name)

        if py_value is None:
            problem("Could not read {0} ({1}) from {2}.".format(description, py_name, py_file))
            continue
        if ts_value is None:
            problem("Could not read {0} ({1}) from {2}.".format(description, ts_name, ts_file))
            continue

        # Relative tolerance: these are the same number written by hand twice,
        # so anything beyond a rounding difference is a real disagreement.
        if abs(py_value - ts_value) > abs(py_value) * 1e-9:
            problem(
                "{0} disagrees: Python {1} = {2!r}, TypeScript {3} = {4!r}.".format(
                    description, py_name, py_value, ts_name, ts_value
                )
            )


def main() -> int:
    check_telemetry_fields()
    check_enums()
    check_constants()

    if _PROBLEMS:
        print("Contract parity: {0} problem(s) found.\n".format(len(_PROBLEMS)))
        for issue in _PROBLEMS:
            print("  - {0}".format(issue))
        print(
            "\nThe Python engine flies every mission and the TypeScript engine analyses\n"
            "designs in the browser. When they disagree the builder shows a number the\n"
            "flight then contradicts, with no error anywhere. Reconcile them."
        )
        return 1

    print("Contract parity: {0} checks, no drift.".format(_CHECKS_RUN))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
