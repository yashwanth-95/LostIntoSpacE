# Simulation Assumptions and Approximations

This document records the assumptions used by the educational simulation model. These are intentionally explicit. The objective is scientific transparency, not false precision.

## General assumptions

- The simulation is educational and engineering-oriented, not flight-certified.
- The vehicle is treated as a point mass for translational dynamics in the initial model.
- The atmosphere is modeled with a simplified, layered approximation.
- The rocket uses a simplified guidance law rather than a full flight-control loop.
- The launch environment is deterministic unless explicitly configured otherwise.

## Gravity assumptions

- Earth is modeled as a spherical mass with a central inverse-square field.
- The model does not include J2 oblateness, lunar gravity, solar gravity, or atmospheric drag-induced perturbations.
- Gravity is treated as a function of altitude and direction relative to the Earth center.
- Local gravitational variation is approximated rather than computed from a full geophysical model.

## Atmosphere assumptions

- Atmospheric density is represented using a simplified Newtonian/standard-atmosphere approximation.
- Wind is either ignored or treated as a fixed external field at low fidelity.
- The atmosphere model is not a full atmospheric science solver.
- Mach-dependent effects are simplified for the educational MVP.

## Drag assumptions

- Drag is approximated with a quadratic law based on density, relative speed, area, and coefficient.
- The model uses a simplified reference area and drag coefficient.
- Base drag, compressibility effects, and complex flow separation are not fully modeled.
- High-angle-of-attack and rotational aerodynamic effects are not included in the initial simulation.

## Propulsion assumptions

- Propellant flow is treated as constant during an active burn.
- Specific impulse is assumed fixed for a stage during a burn.
- Thrust is applied along the commanded direction and does not include full gimbal dynamics.
- Engine ignition and shutdown are treated as idealized state transitions.
- No throttle scheduling or transient engine behavior is modeled in the MVP.

## Mass and stage assumptions

- Each stage loses mass continuously during burn according to a simple consumption model.
- Stage separation is modeled as a discrete event with a delay, not a full dynamic separation physics model.
- Structural mass is treated as fixed and does not vary during the mission.

## Orbital assumptions

- The simulation tracks a simplified translational orbital trajectory rather than full high-fidelity orbital mechanics.
- Orbital insertion is approximated from translational state and altitude/velocity thresholds.
- The model does not calculate full Keplerian perturbation or multi-body ephemeris for the initial version.

## Guidance and control assumptions

- Guidance is scripted rather than recalculated from a full control system.
- Vehicle attitude follows a simplified pitch program or gravity-turn strategy.
- The model does not include detailed rotational stabilization or full landing guidance.

## Failure assumptions

- Failure modes are educational examples, not exact representations of real accident investigations.
- Failure conditions are rule-based and deterministic based on telemetry thresholds.
- The system intentionally captures failure metadata and event context without pretending to provide a complete engineering diagnosis.

## Numerical method assumptions

- The default numerical integrator is a fixed-step, explicit method chosen for stability and determinism.
- The simulator prioritizes reproducibility over maximum physical realism in the educational MVP.
- The output should be transparent and explainable; the user should be able to see which approximations affect the result.

## Units and precision assumptions

- SI units are used throughout the engine unless explicitly noted.
- Quantities are reported in explicit units, not mixed or implicit units.
- The simulation avoids unrealistic precision claims and identifies where values are estimates.

## Future expansion assumptions

The following are intentionally excluded from the MVP but are valid future enhancements:

- spherical harmonic gravity fields
- J2 and other gravity perturbations
- full aerodynamic coefficient tables
- 6-DOF rotational dynamics
- advanced navigation and guidance loops
- multi-body orbital propagation
- detailed thermal and structural models
- networked live telemetry streaming

## Summary

The simulation is designed to teach real concepts without pretending to be a certificate-level engineering model. All assumptions are intentionally documented so the system remains transparent, extendable, and suitable for engineering education.
