"""
LostIntoSpacE Simulation Engine.

Physics-based rocket flight simulation using 3-DOF translational dynamics
with RK4 integration. Educational fidelity — not flight-certified.

Layers:
    models/     Pure physics models (gravity, atmosphere, drag, thrust)
    engine/     Flight loop, state machine, guidance, failures
    telemetry/  Telemetry generation and sampling
    events/     Event type definitions
    contracts/  Pydantic schemas shared with the TypeScript frontend
"""

__version__ = "0.1.0"
