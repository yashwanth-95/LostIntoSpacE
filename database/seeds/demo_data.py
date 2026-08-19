"""Deterministic demo data for the SIH prototype.

Covers the full journey in docs/demo/DEMO_RUNBOOK.md:
    User -> Project -> Mission -> Vehicle (+components) -> Lesson ->
    Learning progress -> Conversation (+messages) -> Space objects

DETERMINISTIC BY DESIGN. Every id is a fixed UUID and every loader upserts on
a natural key, so running this twice produces the same database and a demo can
be reset mid-presentation without surprises.

=============================================================================
ALL SCIENTIFIC VALUES HERE ARE ILLUSTRATIVE / EDUCATIONAL, NOT MEASURED DATA.
=============================================================================
Space-object figures are rounded textbook values, tagged `source="bundled"` so
they are distinguishable in the API from anything P4 later ingests from NASA.
The rocket is a plausible teaching example, not a real vehicle. Nothing here
should be presented as a real measurement or a real flight result.

The demo account's password is a throwaway for local/demo use. It is NOT a
production credential: seeding refuses to run when APP_ENV=production.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import build_engine, build_session_factory
from src.core.security import hash_password
from src.models.content import Lesson, SpaceObject
from src.models.conversation import Conversation, Message
from src.models.learning import LearningProgress
from src.models.project import Mission, Project
from src.models.user import User
from src.models.vehicle import Vehicle, VehicleComponent

logger = logging.getLogger("seeds.demo")

DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_PROJECT_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEMO_MISSION_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
DEMO_VEHICLE_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
DEMO_CONVERSATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

DEMO_EMAIL = "demo@lostintospace.local"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-password-123"  # noqa: S105 - non-production demo credential


async def seed_demo_user(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.id == DEMO_USER_ID))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=DEMO_USER_ID,
            email=DEMO_EMAIL,
            username=DEMO_USERNAME,
            password_hash=hash_password(DEMO_PASSWORD),
            display_name="Demo Student",
            role="student",
            preferences={"theme": "dark", "units": "metric"},
        )
        session.add(user)
        await session.flush()
    return user


async def seed_space_objects(session: AsyncSession) -> int:
    """Rounded textbook values, tagged source='bundled' so the API can tell
    them apart from P4's ingested records. Upserts on (source, source_id),
    which is what the partial-unique index exists for."""
    objects = [
        {
            "name": "Mars",
            "category": "planet",
            "subcategory": "terrestrial",
            "description": (
                "The fourth planet from the Sun. Values shown are rounded "
                "reference figures for teaching, not mission-grade data."
            ),
            "physical_data": {"mass_kg": 6.417e23, "radius_km": 3389.5, "gravity_ms2": 3.721},
            "orbital_data": {"semi_major_axis_au": 1.524, "period_days": 687},
            "source": "bundled",
            "source_id": "demo-mars",
        },
        {
            "name": "Earth",
            "category": "planet",
            "subcategory": "terrestrial",
            "description": "Reference body for the atmosphere and gravity models.",
            "physical_data": {"mass_kg": 5.972e24, "radius_km": 6371.0, "gravity_ms2": 9.80665},
            "orbital_data": {"semi_major_axis_au": 1.0, "period_days": 365.25},
            "source": "bundled",
            "source_id": "demo-earth",
        },
        {
            "name": "Moon",
            "category": "moon",
            "subcategory": "natural satellite",
            "description": "Earth's only natural satellite.",
            "physical_data": {"mass_kg": 7.342e22, "radius_km": 1737.4, "gravity_ms2": 1.62},
            "orbital_data": {"semi_major_axis_km": 384400, "period_days": 27.3},
            "source": "bundled",
            "source_id": "demo-moon",
        },
    ]

    for payload in objects:
        statement = (
            pg_insert(SpaceObject)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=["source", "source_id"],
                set_={
                    "name": payload["name"],
                    "description": payload["description"],
                    "physical_data": payload["physical_data"],
                    "orbital_data": payload["orbital_data"],
                    "last_updated": datetime.now(UTC),
                },
            )
        )
        await session.execute(statement)
    await session.flush()
    return len(objects)


async def seed_lessons(session: AsyncSession) -> list[Lesson]:
    """Educational content. Equations are standard textbook forms."""
    lessons = [
        {
            "title": "Thrust-to-Weight Ratio",
            "slug": "thrust-to-weight-ratio",
            "category": "propulsion",
            "difficulty": "beginner",
            "summary": "Why a rocket with too little thrust never leaves the pad.",
            "content": (
                "# Thrust-to-Weight Ratio\n\n"
                "A rocket lifts off only when thrust exceeds weight, i.e. TWR > 1.\n\n"
                "`TWR = F_thrust / (m * g)`\n\n"
                "A TWR below 1 at ignition means the vehicle cannot accelerate "
                "upward - a common first failure in the simulator, and a "
                "deliberately instructive one."
            ),
            "equations": [{"latex": "TWR = \\frac{F}{mg}", "description": "Thrust-to-weight"}],
            "prerequisites": [],
            "sort_order": 1,
        },
        {
            "title": "Atmospheric Drag",
            "slug": "atmospheric-drag",
            "category": "atmosphere",
            "difficulty": "beginner",
            "summary": "How air resistance shapes a launch trajectory.",
            "content": (
                "# Atmospheric Drag\n\n"
                "`F_d = 0.5 * rho * v^2 * Cd * A`\n\n"
                "Drag rises with the square of velocity, which is why max-Q - "
                "the point of peak dynamic pressure - is a structural design "
                "driver rather than a curiosity."
            ),
            "equations": [
                {"latex": "F_d = \\frac{1}{2}\\rho v^2 C_d A", "description": "Drag force"}
            ],
            "prerequisites": ["thrust-to-weight-ratio"],
            "sort_order": 2,
        },
        {
            "title": "Staging Basics",
            "slug": "staging-basics",
            "category": "mission_design",
            "difficulty": "intermediate",
            "summary": "Why dropping empty mass mid-flight beats carrying it.",
            "content": (
                "# Staging\n\n"
                "Shedding spent structure raises the remaining vehicle's "
                "acceleration for the same thrust, which is the core idea "
                "behind the rocket equation's sensitivity to mass ratio."
            ),
            "equations": [
                {
                    "latex": "\\Delta v = I_{sp} g_0 \\ln\\frac{m_0}{m_f}",
                    "description": "Tsiolkovsky rocket equation",
                }
            ],
            "prerequisites": ["thrust-to-weight-ratio", "atmospheric-drag"],
            "sort_order": 3,
        },
    ]

    stored: list[Lesson] = []
    for payload in lessons:
        statement = (
            pg_insert(Lesson)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={"title": payload["title"], "content": payload["content"]},
            )
            .returning(Lesson)
        )
        result = await session.execute(statement)
        stored.append(result.scalar_one())
    await session.flush()
    return stored


async def seed_project_mission_vehicle(session: AsyncSession) -> None:
    """One project -> mission -> vehicle with components, so the builder and
    mission-control screens have something real to load."""
    existing = await session.execute(select(Project).where(Project.id == DEMO_PROJECT_ID))
    if existing.scalar_one_or_none() is None:
        session.add(
            Project(
                id=DEMO_PROJECT_ID,
                user_id=DEMO_USER_ID,
                name="First Sounding Rocket",
                description="A single-stage demo vehicle for the SIH walkthrough.",
                status="active",
                project_metadata={"demo": True, "notes": "Seeded demo project"},
            )
        )
        await session.flush()

    existing_mission = await session.execute(select(Mission).where(Mission.id == DEMO_MISSION_ID))
    if existing_mission.scalar_one_or_none() is None:
        session.add(
            Mission(
                id=DEMO_MISSION_ID,
                project_id=DEMO_PROJECT_ID,
                name="Suborbital Test Flight",
                objective="Reach 10 km altitude and recover the vehicle.",
                target_orbit={"type": "suborbital", "target_altitude_km": 10},
                launch_site={
                    "name": "Satish Dhawan Space Centre",
                    "latitude": 13.7199,
                    "longitude": 80.2304,
                    "altitude_m": 4,
                },
                environment={
                    "temperature_k": 300,
                    "pressure_pa": 101325,
                    "wind_speed_ms": 0,
                },
                status="ready",
            )
        )
        await session.flush()

    existing_vehicle = await session.execute(select(Vehicle).where(Vehicle.id == DEMO_VEHICLE_ID))
    if existing_vehicle.scalar_one_or_none() is None:
        session.add(
            Vehicle(
                id=DEMO_VEHICLE_ID,
                mission_id=DEMO_MISSION_ID,
                name="Demo Rocket Alpha",
                total_height_m=4.2,
            )
        )
        await session.flush()

        # Geometry only. Derived values (total mass, CG, CP, stability margin)
        # are left null on purpose: they are P3's engine's outputs, and filling
        # them with invented numbers would be presenting fabricated results.
        components = [
            {
                "component_type": "nose",
                "name": "Ogive Nose Cone",
                "mass_kg": 5.0,
                "position": {"x": 0, "y": 0, "z": 3.9},
                "dimensions": {"length_m": 0.5, "diameter_m": 0.3},
                "sort_order": 0,
            },
            {
                "component_type": "payload",
                "name": "Instrument Bay",
                "mass_kg": 12.0,
                "position": {"x": 0, "y": 0, "z": 3.3},
                "dimensions": {"length_m": 0.6, "diameter_m": 0.3},
                "sort_order": 1,
            },
            {
                "component_type": "body",
                "name": "Main Body Tube",
                "mass_kg": 40.0,
                "position": {"x": 0, "y": 0, "z": 1.8},
                "dimensions": {"length_m": 2.4, "diameter_m": 0.3},
                "sort_order": 2,
            },
            {
                "component_type": "engine",
                "name": "Demo Motor",
                "mass_kg": 25.0,
                "position": {"x": 0, "y": 0, "z": 0.4},
                "dimensions": {"length_m": 0.8, "diameter_m": 0.3},
                "properties": {"note": "Illustrative motor - not a real product"},
                "sort_order": 3,
            },
            {
                "component_type": "fins",
                "name": "Fin Set (3)",
                "mass_kg": 3.0,
                "position": {"x": 0, "y": 0, "z": 0.3},
                "dimensions": {"span_m": 0.25, "chord_m": 0.3, "count": 3},
                "sort_order": 4,
            },
        ]
        for component in components:
            session.add(VehicleComponent(vehicle_id=DEMO_VEHICLE_ID, **component))
        await session.flush()


async def seed_learning_progress(session: AsyncSession, lessons: list[Lesson]) -> None:
    """One completed lesson and one in progress, so the dashboard isn't empty."""
    if not lessons:
        return
    states = [
        (lessons[0].id, "completed", 100),
        (lessons[1].id, "in_progress", 40) if len(lessons) > 1 else None,
    ]
    now = datetime.now(UTC)
    for entry in states:
        if entry is None:
            continue
        lesson_id, status, percent = entry
        await session.execute(
            pg_insert(LearningProgress)
            .values(
                user_id=DEMO_USER_ID,
                lesson_id=lesson_id,
                status=status,
                progress_percent=percent,
                completed_at=now if status == "completed" else None,
                last_viewed_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "lesson_id"],
                set_={"status": status, "progress_percent": percent},
            )
        )
    await session.flush()


async def seed_conversation(session: AsyncSession) -> None:
    """A short tutor exchange. The assistant message carries `grounding`,
    demonstrating the "AI explains, models calculate" provenance rule."""
    existing = await session.execute(
        select(Conversation).where(Conversation.id == DEMO_CONVERSATION_ID)
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(
        Conversation(
            id=DEMO_CONVERSATION_ID,
            user_id=DEMO_USER_ID,
            title="Why did my rocket not lift off?",
            context_type="tutor",
            context_ref={"type": "mission", "id": str(DEMO_MISSION_ID)},
            status="active",
        )
    )
    await session.flush()

    session.add_all(
        [
            Message(
                conversation_id=DEMO_CONVERSATION_ID,
                role="user",
                content="Why did my rocket not lift off?",
                grounding=[],
            ),
            Message(
                conversation_id=DEMO_CONVERSATION_ID,
                role="assistant",
                content=(
                    "A vehicle only leaves the pad when thrust exceeds weight "
                    "(TWR > 1). This is illustrative demo content, not a "
                    "generated model response."
                ),
                grounding=[{"type": "lesson", "slug": "thrust-to-weight-ratio"}],
            ),
        ]
    )
    await session.flush()


async def run_demo_seed() -> dict[str, int]:
    settings = get_settings()
    if settings.app_env == "production":
        # The demo account has a known password. It must never exist in prod.
        raise RuntimeError("Refusing to seed demo data while APP_ENV=production")

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    counts: dict[str, int] = {}
    try:
        async with session_factory() as session:
            await seed_demo_user(session)
            counts["space_objects"] = await seed_space_objects(session)
            lessons = await seed_lessons(session)
            counts["lessons"] = len(lessons)
            await seed_project_mission_vehicle(session)
            await seed_learning_progress(session, lessons)
            await seed_conversation(session)
            await session.commit()
            counts["users"] = 1
            counts["projects"] = 1
            counts["missions"] = 1
            counts["vehicles"] = 1
            counts["conversations"] = 1
    finally:
        await engine.dispose()
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    counts = asyncio.run(run_demo_seed())
    logger.info("Demo seed complete: %s", counts)
    logger.info("Demo login: %s / %s  (NON-PRODUCTION)", DEMO_EMAIL, DEMO_PASSWORD)


if __name__ == "__main__":
    main()
