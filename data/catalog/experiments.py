"""Runnable experiments.

An experiment here is not a code snippet. It states a question, fixes
everything except one variable, sweeps that variable across real values, and
compares a stated hypothesis against what the simulation actually produced.

That structure is the point. A learner who reads that fin size affects
stability has learned a sentence; a learner who sweeps fin area from 60% to
160% and watches the static margin cross 1.0 caliber has learned the shape of
the relationship, including where it stops being linear.

Every sweep value is passed to the same physics the flight simulation uses, so
an experiment cannot produce a result the simulator would disagree with.
"""

from typing import Dict, List

from .models import Experiment, ExperimentStep

__all__ = ["build_experiments", "experiments_by_id", "EXPERIMENT_IDS"]


def _step(instruction: str, expectation: str = "", **changes) -> ExperimentStep:
    return ExperimentStep(instruction=instruction, changes=changes, expectation=expectation)


def build_experiments() -> List[Experiment]:
    return [
        Experiment(
            id="twr-threshold",
            title="Where exactly does it leave the pad?",
            objective="Find the thrust-to-weight ratio at which a vehicle stops being able to lift itself.",
            question="Is 1.0 really the threshold, or does a vehicle need more than that to fly usefully?",
            category="Propulsion",
            level="foundation",
            base_design="sounding-single-stage",
            variable="thrust_sea_level_N",
            variable_label="Sea-level thrust",
            variable_unit="kN",
            sweep=[180, 220, 240, 250, 260, 300, 380, 500],
            controls=[
                "Launch mass held at 24,500 kg",
                "Specific impulse held at 270 s sea level",
                "Same launch site, same standard-day weather",
                "Same guidance program",
            ],
            measures=["twr_liftoff", "max_altitude_m", "flight_time_s", "outcome"],
            procedure=[
                _step(
                    "Run the baseline at 380 kN and note the liftoff TWR and apogee.",
                    expectation="TWR about 1.58, a clean flight.",
                    thrust_sea_level_N=380_000,
                ),
                _step(
                    "Reduce thrust to 250 kN, just above the vehicle's weight.",
                    expectation="It lifts, but slowly, and apogee collapses.",
                    thrust_sea_level_N=250_000,
                ),
                _step(
                    "Reduce to 240 kN, just below weight.",
                    expectation="It never leaves the pad. The failure analysis names the reason.",
                    thrust_sea_level_N=240_000,
                ),
            ],
            hypothesis=(
                "The vehicle will fly whenever TWR exceeds 1.0, and apogee will rise smoothly "
                "with thrust."
            ),
            explanation=(
                "TWR must exceed 1.0 or nothing happens at all — that part of the hypothesis "
                "holds. The second part does not. Just above 1.0 the vehicle rises so slowly "
                "that it spends most of its propellant fighting gravity rather than "
                "accelerating, and gravity losses eat almost the entire delta-v budget. Apogee "
                "does not rise smoothly with thrust; it rises very steeply just above the "
                "threshold and then flattens, which is why real vehicles target 1.2–1.5 rather "
                "than the minimum that works."
            ),
            topic_slugs=["thrust-to-weight", "delta-v-budget"],
            estimated_runs=8,
        ),

        Experiment(
            id="fin-size-sweep",
            title="How big do the fins need to be?",
            objective="Establish the fin area at which a vehicle becomes stable, and find the point where more stops helping.",
            question="If bigger fins mean more stability, why not fit the biggest fins that will fit?",
            category="Aerodynamics",
            level="foundation",
            base_design="sounding-single-stage",
            variable="fin_area_scale",
            variable_label="Fin area, relative to baseline",
            variable_unit="×",
            sweep=[0.4, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0, 2.6],
            controls=[
                "All masses other than the fins held constant",
                "Same body diameter, so calibers stay comparable",
                "Same launch site and weather",
            ],
            measures=["static_margin_cal", "drag_coefficient", "max_altitude_m",
                      "max_lateral_deviation_m", "outcome"],
            procedure=[
                _step("Start at 0.4× and observe the static margin.",
                      expectation="Below 1 caliber. Marginally stable at best.",
                      fin_area_scale=0.4),
                _step("Step up until the margin crosses 1.0 caliber.",
                      expectation="Stability improves and the flight straightens out.",
                      fin_area_scale=1.0),
                _step("Continue to 2.6× and watch drag and apogee.",
                      expectation="Stability keeps rising; apogee does not.",
                      fin_area_scale=2.6),
            ],
            hypothesis="Larger fins always improve the flight, so the largest fins are best.",
            explanation=(
                "Stability does improve monotonically with fin area, but two costs rise with "
                "it. Drag increases, taking apogee down. And beyond about 2 calibers the "
                "vehicle becomes over-stable — it weathercocks hard into any crosswind, so on "
                "a windy day it turns into the wind and flies there rather than where it was "
                "aimed. Watch the lateral deviation column: it gets worse at both ends of the "
                "sweep, for opposite reasons."
            ),
            topic_slugs=["stability-margin", "atmospheric-drag", "wind-and-shear"],
            estimated_runs=8,
        ),

        Experiment(
            id="payload-mass-sweep",
            title="What does a kilogram of payload cost?",
            objective="Quantify how payload mass trades against altitude and delta-v.",
            question="Payload is a small fraction of launch mass. Does adding some really matter?",
            category="Mission design",
            level="intermediate",
            base_design="orbital-two-stage",
            variable="payload_mass_kg",
            variable_label="Payload mass",
            variable_unit="kg",
            sweep=[0, 250, 500, 1000, 1500, 2000, 3000, 4500],
            controls=[
                "Propellant and dry mass held constant",
                "Same engines, same Isp",
                "Same target orbit and guidance",
            ],
            measures=["total_delta_v_ms", "max_altitude_m", "twr_liftoff",
                      "periapsis_altitude_m", "outcome"],
            procedure=[
                _step("Fly with no payload to establish the ceiling.",
                      expectation="Maximum achievable delta-v for this vehicle.",
                      payload_mass_kg=0),
                _step("Add 1,000 kg.",
                      expectation="Delta-v falls, but by less than proportionally.",
                      payload_mass_kg=1000),
                _step("Keep adding until the vehicle can no longer reach orbit.",
                      expectation="A hard cliff, not a gradual decline.",
                      payload_mass_kg=4500),
            ],
            hypothesis="Delta-v falls linearly with payload mass.",
            explanation=(
                "It does not, because the rocket equation is logarithmic. Payload sits in the "
                "denominator of the mass ratio, so each additional kilogram costs slightly more "
                "delta-v than the last. The important effect is at the end: the mission does "
                "not degrade gracefully. It works, works, works, and then the periapsis drops "
                "below the atmosphere and the vehicle re-enters instead of orbiting. That cliff "
                "is why launch providers quote payload against a named orbit and hold margin "
                "back."
            ),
            topic_slugs=["tsiolkovsky", "payload", "delta-v-budget"],
            estimated_runs=8,
        ),

        Experiment(
            id="staging-comparison",
            title="Is staging worth the complexity?",
            objective="Compare one, two and three stages built from the same total mass.",
            question="Every separation is a chance to fail. What does staging actually buy?",
            category="Propulsion",
            level="intermediate",
            base_design="orbital-two-stage",
            variable="stage_count",
            variable_label="Number of stages",
            sweep=[1, 2, 3],
            controls=[
                "Total launch mass held constant",
                "Same structural fraction per stage",
                "Same propellant type and Isp",
            ],
            measures=["total_delta_v_ms", "max_altitude_m", "stages_separated", "outcome"],
            procedure=[
                _step("Build the whole mass as a single stage.",
                      expectation="A large mass ratio on paper, and disappointing delta-v.",
                      stage_count=1),
                _step("Split into two.", expectation="A substantial jump in delta-v.", stage_count=2),
                _step("Split into three.", expectation="A further gain, but a smaller one.", stage_count=3),
            ],
            hypothesis="More stages always mean more delta-v, so more is better.",
            explanation=(
                "Delta-v does keep rising, but with sharply diminishing returns: the jump from "
                "one stage to two is large, two to three much smaller, and beyond three the "
                "gain is swamped by the mass of the extra interstages and separation systems. "
                "Set against that, every separation is a single-shot mechanism that cannot be "
                "rehearsed in flight and is a recurring cause of launch loss. Two or three "
                "stages is where almost every real vehicle lands, and this is why."
            ),
            topic_slugs=["staging", "tsiolkovsky"],
            estimated_runs=3,
        ),

        Experiment(
            id="crosswind-sweep",
            title="How much wind is too much?",
            objective="Find the surface wind at which the flight becomes unacceptable.",
            question="The pad report says 12 m/s. Is that flyable?",
            category="Environment",
            level="advanced",
            base_design="orbital-two-stage",
            variable="wind_speed_ms",
            variable_label="Surface wind at 10 m",
            variable_unit="m/s",
            sweep=[0, 4, 8, 12, 16, 20, 25, 30],
            controls=[
                "Wind direction held at 270°, a pure crosswind to an eastward launch",
                "Same vehicle, same launch site",
                "Temperature and pressure held at standard",
            ],
            measures=["max_q_alpha_Padeg", "max_angle_of_attack_deg",
                      "max_lateral_deviation_m", "max_altitude_m", "outcome"],
            procedure=[
                _step("Fly in still air for a reference.", expectation="Lateral deviation near zero.",
                      wind_speed_ms=0),
                _step("Step to 12 m/s, a typical operational limit.",
                      expectation="Measurable deviation, q·α climbing.", wind_speed_ms=12),
                _step("Push to 25 m/s and beyond.",
                      expectation="q·α exceeds structural limits.", wind_speed_ms=25),
            ],
            hypothesis="Wind pushes the vehicle sideways; the effect scales linearly with wind speed.",
            explanation=(
                "Lateral deviation does grow roughly with wind speed, but that is not the "
                "constraint that ends the flight. The dangerous quantity is q·α — dynamic "
                "pressure times angle of attack — which is a bending moment on a long thin "
                "tube. It grows faster than linearly, because wind raises angle of attack while "
                "the vehicle is simultaneously accelerating into higher dynamic pressure.\n\n"
                "Note also that the surface wind is not the wind that matters. The profile "
                "amplifies it with altitude toward a jet maximum near 11 km — which is very "
                "close to where max-Q occurs. That coincidence is why launches are scrubbed for "
                "upper-level wind on cloudless days."
            ),
            topic_slugs=["wind-and-shear", "dynamic-pressure"],
            estimated_runs=8,
        ),

        Experiment(
            id="weather-sensitivity",
            title="Does launch-day weather actually change anything?",
            objective="Measure the trajectory difference between a hot humid day and a cold dry one.",
            question="Surface conditions vary by a few percent. Is that worth modelling?",
            category="Environment",
            level="intermediate",
            base_design="sounding-single-stage",
            variable="surface_temperature_K",
            variable_label="Surface temperature",
            variable_unit="K",
            sweep=[258.15, 268.15, 278.15, 288.15, 298.15, 308.15],
            controls=[
                "Wind held at zero, so only density effects appear",
                "Same vehicle and guidance",
                "Pressure and humidity varied together with temperature in the second pass",
            ],
            measures=["air_density_kgm3", "drag_loss_ms", "max_dynamic_pressure_Pa",
                      "max_altitude_m"],
            procedure=[
                _step("Fly a standard day at 288.15 K.", expectation="The reference case.",
                      surface_temperature_K=288.15),
                _step("Fly a cold day at 258.15 K.", expectation="Denser air, more drag, lower apogee.",
                      surface_temperature_K=258.15),
                _step("Fly a hot day at 308.15 K.", expectation="Thinner air, less drag, higher apogee.",
                      surface_temperature_K=308.15),
            ],
            hypothesis="A few degrees of temperature is negligible next to the energy of a launch.",
            explanation=(
                "Between a hot humid low-pressure morning and a cold dry high-pressure one, "
                "surface air density differs by nearly 19% — and drag is directly proportional "
                "to density. The effect on apogee is a fraction of a percent for a high-thrust "
                "vehicle, but it is not zero, and for a marginal design it is the difference "
                "between reaching orbit and not.\n\n"
                "The counter-intuitive part is humidity: humid air is *less* dense than dry air "
                "at the same temperature and pressure, because a water molecule is lighter than "
                "the nitrogen it displaces."
            ),
            topic_slugs=["atmosphere-structure", "atmospheric-drag"],
            estimated_runs=6,
        ),

        Experiment(
            id="drag-area-sweep",
            title="What does a wider fairing cost?",
            objective="Quantify the apogee penalty of increasing frontal area.",
            question="A bigger fairing carries a bigger payload. What does the aerodynamics charge for it?",
            category="Aerodynamics",
            level="intermediate",
            base_design="orbital-two-stage",
            variable="diameter_m",
            variable_label="Body diameter",
            variable_unit="m",
            sweep=[1.2, 1.5, 1.8, 2.2, 2.6, 3.2, 4.0],
            controls=[
                "All masses held constant, so only area changes",
                "Same drag coefficient",
                "Same thrust and propellant",
            ],
            measures=["reference_area_m2", "drag_loss_ms", "max_dynamic_pressure_Pa",
                      "max_altitude_m"],
            procedure=[
                _step("Start narrow at 1.2 m.", expectation="Minimum drag.", diameter_m=1.2),
                _step("Widen to 2.2 m.", expectation="Area up by a factor of 3.4.", diameter_m=2.2),
                _step("Widen to 4.0 m.", expectation="Area up by a factor of 11.", diameter_m=4.0),
            ],
            hypothesis="Widening the vehicle costs performance in proportion to the extra width.",
            explanation=(
                "It costs in proportion to the extra *area*, which goes as the square of "
                "diameter. Going from 1.2 m to 4.0 m is 3.3× the width and 11× the frontal "
                "area, and drag scales directly with it.\n\n"
                "This is why launch vehicles are so slender, and why the fairing — almost always "
                "the widest part of the stack — is the component whose diameter is argued over "
                "hardest. It is also why fairings are jettisoned the moment heating allows: "
                "after that they are pure dead mass on top of the drag they already cost."
            ),
            topic_slugs=["atmospheric-drag", "payload"],
            estimated_runs=7,
        ),

        Experiment(
            id="parachute-sizing",
            title="Sizing a parachute",
            objective="Find the canopy area that brings a vehicle down at a survivable speed.",
            question="How large does a chute have to be, and what happens if it deploys too high?",
            category="Recovery",
            level="foundation",
            base_design="sounding-single-stage",
            variable="canopy_area_m2",
            variable_label="Canopy area",
            variable_unit="m²",
            sweep=[0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0],
            controls=[
                "Descent mass held constant",
                "Canopy drag coefficient held at 1.5",
                "Deployment altitude held at 400 m",
            ],
            measures=["terminal_velocity_ms", "descent_time_s", "opening_shock_N", "outcome"],
            procedure=[
                _step("Start at 0.5 m² and measure the impact speed.",
                      expectation="Far too fast to survive.", canopy_area_m2=0.5),
                _step("Increase until impact speed drops below about 7 m/s.",
                      expectation="A survivable landing.", canopy_area_m2=5.0),
                _step("Then deploy the same chute at 3,000 m instead of 400 m.",
                      expectation="A long, drifting descent — and a much larger opening shock.",
                      deploy_altitude_m=3000),
            ],
            hypothesis="A bigger parachute deployed as early as possible is always safer.",
            explanation=(
                "Terminal velocity falls with the square root of area, so halving the impact "
                "speed needs four times the canopy — the returns diminish quickly.\n\n"
                "Deploying early is worse, not better, for two reasons. The vehicle is still "
                "moving fast in denser air, so the opening shock is much larger and can tear "
                "the canopy or the vehicle apart. And a slow descent from 3 km drifts a very "
                "long way downwind. This is exactly why real recovery uses a small drogue high "
                "for stability and a main chute low for the actual deceleration."
            ),
            topic_slugs=["recovery", "atmospheric-drag"],
            estimated_runs=7,
        ),

        Experiment(
            id="orbit-insertion-sweep",
            title="Getting the periapsis above the atmosphere",
            objective="Find the cutoff velocity at which a trajectory becomes an orbit.",
            question="The vehicle reached 300 km. Why did it come back down?",
            category="Orbital mechanics",
            level="intermediate",
            base_design="orbital-two-stage",
            variable="pitch_program_end_altitude_m",
            variable_label="Pitch program end altitude",
            variable_unit="km",
            sweep=[40, 60, 80, 100, 120, 160],
            controls=[
                "Same vehicle and propellant",
                "Same launch site and target altitude",
                "Only the guidance profile changes",
            ],
            measures=["periapsis_altitude_m", "apoapsis_altitude_m", "eccentricity",
                      "max_altitude_m", "outcome"],
            procedure=[
                _step("Pitch over early, finishing by 40 km.",
                      expectation="Lots of horizontal speed, but not enough altitude.",
                      pitch_program_end_altitude_m=40_000),
                _step("Finish the pitch program at 80 km.",
                      expectation="A more balanced profile.",
                      pitch_program_end_altitude_m=80_000),
                _step("Stay vertical until 160 km.",
                      expectation="Plenty of altitude, nowhere near enough horizontal speed.",
                      pitch_program_end_altitude_m=160_000),
            ],
            hypothesis="Reaching a high enough altitude puts the vehicle in orbit.",
            explanation=(
                "Altitude alone never produces an orbit. What matters is whether periapsis — "
                "the low point of the resulting ellipse — is above the atmosphere. A vehicle "
                "that goes straight up to 300 km has a periapsis below the ground, so its "
                "trajectory intersects Earth and it comes back down.\n\n"
                "Watch the periapsis column rather than the apogee column. It stays deeply "
                "negative for the vertical profiles and only climbs above 100 km when enough of "
                "the burn has gone into horizontal velocity. Orbit is a speed, not a height."
            ),
            topic_slugs=["orbital-mechanics", "guidance-navigation-control"],
            estimated_runs=6,
        ),

        Experiment(
            id="isp-sensitivity",
            title="Efficiency against brute force",
            objective="Compare adding propellant with improving specific impulse.",
            question="Which buys more delta-v: 20% more propellant, or 20% more Isp?",
            category="Propulsion",
            level="intermediate",
            base_design="orbital-two-stage",
            variable="isp_vacuum_s",
            variable_label="Vacuum specific impulse",
            variable_unit="s",
            sweep=[260, 300, 340, 380, 420, 450],
            controls=[
                "Propellant mass held constant",
                "Dry mass and payload held constant",
                "Same mission profile",
            ],
            measures=["total_delta_v_ms", "mass_ratio", "max_altitude_m", "outcome"],
            procedure=[
                _step("Baseline at 340 s.", expectation="The reference case.", isp_vacuum_s=340),
                _step("Raise Isp by 20% to 408 s.", expectation="Delta-v rises by 20%.",
                      isp_vacuum_s=408),
                _step("Instead, raise propellant by 20% at the original Isp.",
                      expectation="A much smaller gain.", isp_vacuum_s=340,
                      propellant_scale=1.2),
            ],
            hypothesis="Both changes are 20%, so both should help about equally.",
            explanation=(
                "They do not. Delta-v is Isp × g₀ × ln(mass ratio), so it is *linear* in Isp "
                "and *logarithmic* in mass. A 20% improvement in Isp gives a 20% improvement in "
                "delta-v, straightforwardly. A 20% increase in propellant changes only the "
                "argument of a logarithm and typically yields under 5%.\n\n"
                "This is why enormous engineering effort goes into a few seconds of specific "
                "impulse, and why hydrogen upper stages exist despite every practical "
                "disadvantage of hydrogen."
            ),
            topic_slugs=["specific-impulse", "tsiolkovsky"],
            estimated_runs=6,
        ),

        Experiment(
            id="gravity-well-comparison",
            title="Launching from somewhere else",
            objective="Compare what it takes to reach orbit from different bodies.",
            question="Why is a Mars ascent vehicle so much smaller than an Earth launch vehicle?",
            category="Orbital mechanics",
            level="foundation",
            base_design="sounding-single-stage",
            variable="body_id",
            variable_label="Launch body",
            sweep=[],
            controls=[
                "Same vehicle in every case",
                "Same target altitude above the surface",
            ],
            measures=["escape_velocity_kms", "orbital_velocity_kms", "required_delta_v_ms",
                      "atmospheric_drag_loss_ms"],
            procedure=[
                _step("Compare Earth, Mars and the Moon.",
                      expectation="Delta-v requirements differ by a large factor."),
            ],
            hypothesis="Mars is a big planet, so leaving it should be nearly as hard as leaving Earth.",
            explanation=(
                "Mars has 38% of Earth's surface gravity and 0.6% of its atmospheric pressure. "
                "Orbital velocity there is 3.6 km/s against Earth's 7.8, and there is almost no "
                "drag or gravity loss to pay. The result is that a Mars ascent vehicle needs "
                "roughly a fifth of the delta-v of an Earth launch vehicle, which by the rocket "
                "equation makes it dramatically smaller.\n\n"
                "The Moon is easier still: 1.68 km/s to orbit and no atmosphere at all, which "
                "is why the Apollo ascent stage was a small pressurised box with a single "
                "engine bolted underneath."
            ),
            topic_slugs=["gravity", "delta-v-budget", "orbital-mechanics"],
            estimated_runs=3,
        ),

        Experiment(
            id="failure-diagnosis",
            title="Diagnose an unexplained loss",
            objective="Work backwards from telemetry to a root cause, then prove it with one change.",
            question="This design fails 46 seconds in. Why, and what one change fixes it?",
            category="Analysis",
            level="advanced",
            base_design="unstable-marginal",
            variable="fin_area_scale",
            variable_label="Fin area, relative to baseline",
            variable_unit="×",
            sweep=[1.0, 1.3, 1.6, 2.0],
            controls=[
                "Everything except the one variable under test",
            ],
            measures=["static_margin_cal", "max_angle_of_attack_deg", "max_q_alpha_Padeg",
                      "failure_time_s", "outcome"],
            procedure=[
                _step("Fly the baseline and read the failure record.",
                      expectation="A specific failure with a measured value and a threshold.",
                      fin_area_scale=1.0),
                _step("Look at the twenty seconds before the failure, not the failure itself.",
                      expectation="Angle of attack is already drifting."),
                _step("Apply the single change the analysis recommends and re-fly.",
                      expectation="If the diagnosis was right, the failure moves or disappears.",
                      fin_area_scale=1.6),
            ],
            hypothesis="The vehicle broke up, so the airframe was too weak.",
            explanation=(
                "The airframe was adequate. Its static margin was 0.42 calibers — marginally "
                "stable — so a small crosswind disturbance was amplified rather than corrected. "
                "Angle of attack grew, and q·α with it, until the lateral bending load exceeded "
                "what the structure could carry.\n\n"
                "The proximate cause is structural. The root cause is aerodynamic stability, "
                "and strengthening the airframe would have produced a heavier vehicle that "
                "failed slightly later in the same way. This is the difference between fixing "
                "the symptom and fixing the design."
            ),
            topic_slugs=["failure-analysis", "stability-margin", "wind-and-shear"],
            estimated_runs=4,
        ),
    ]


EXPERIMENT_IDS = [
    "twr-threshold", "fin-size-sweep", "payload-mass-sweep", "staging-comparison",
    "crosswind-sweep", "weather-sensitivity", "drag-area-sweep", "parachute-sizing",
    "orbit-insertion-sweep", "isp-sensitivity", "gravity-well-comparison",
    "failure-diagnosis",
]


def experiments_by_id() -> Dict[str, Experiment]:
    return {e.id: e for e in build_experiments()}
