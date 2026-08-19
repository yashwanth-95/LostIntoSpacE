"""Live data for time-sensitive questions."""

import pytest

from ai.assistant import SpaceAssistant
from ai.grounding import GroundedRAG, LiveSourceResolver, NullLiveResolver
from ai.providers import MockAIProvider
from contracts.ai import DataOrigin
from contracts.provenance import SourceType
from data.sources import build_source
from data.tests.mocks import MockEndpoint, MockProvider, load_fixture

ISS = load_fixture("celestrak_iss.json")
EONET = load_fixture("eonet_events.json")


def celestrak_source():
    provider = MockProvider("celestrak_gp").route(
        "/NORAD/elements/gp.php", MockEndpoint(json=ISS)
    )
    return build_source("celestrak_gp", transport=provider.transport)


def eonet_source():
    provider = MockProvider("nasa_eonet").route(
        "/events", MockEndpoint(json=EONET)
    )
    return build_source("nasa_eonet", transport=provider.transport)


class TestRouting:
    def test_iss_questions_route_to_the_satellite_feed(self):
        resolver = LiveSourceResolver()
        assert resolver.can_resolve("Where is the ISS right now?") == "satellite"

    def test_norad_numbers_route_to_the_satellite_feed(self):
        resolver = LiveSourceResolver()
        assert resolver.can_resolve("current elements for NORAD 25544") == (
            "satellite"
        )

    def test_event_questions_route_to_the_event_feed(self):
        resolver = LiveSourceResolver()
        assert resolver.can_resolve("what wildfires are burning now?") == "event"

    def test_a_concept_question_routes_nowhere(self):
        """A resolver that answers everything guarantees a stale answer."""
        resolver = LiveSourceResolver()
        assert resolver.can_resolve("What causes Max-Q?") is None

    def test_a_mission_history_question_routes_nowhere(self):
        resolver = LiveSourceResolver()
        assert resolver.can_resolve("What did Apollo 11 achieve?") is None


class TestSatelliteResolution:
    async def test_it_fetches_current_elements(self):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async("Where is the ISS right now?", None)
        assert items
        assert "ISS" in items[0].title
        await source.aclose()

    async def test_the_item_is_labelled_operational_not_scientific(self):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async("Where is the ISS now?", None)
        assert items[0].source_type is SourceType.SECONDARY_OPERATIONAL
        await source.aclose()

    async def test_it_says_the_elements_are_not_a_position_fix(self):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async("Where is the ISS now?", None)
        assert "not a position fix" in items[0].content
        assert "not a precise ephemeris" in items[0].content
        await source.aclose()

    async def test_the_epoch_and_frame_are_included(self):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async("Where is the ISS now?", None)
        assert "Element set epoch" in items[0].content
        assert "Reference frame" in items[0].content
        await source.aclose()

    async def test_an_unidentifiable_satellite_yields_nothing(self):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async(
            "where is that satellite orbiting right now", None
        )
        assert items == []
        assert "could not identify" in resolver.last_attempt["reason"]
        await source.aclose()

    async def test_no_configured_source_is_reported_not_faked(self):
        resolver = LiveSourceResolver(celestrak=None)
        items = await resolver.resolve_async("Where is the ISS now?", None)
        assert items == []
        assert "no satellite source configured" in resolver.last_attempt["reason"]

    async def test_a_source_failure_yields_nothing_and_records_why(self):
        import httpx

        provider = MockProvider("celestrak_gp").route(
            "/NORAD/elements/gp.php",
            MockEndpoint(raises=httpx.ConnectError("refused")),
        )
        source = build_source("celestrak_gp", transport=provider.transport)
        source.client._sleep = _no_sleep
        resolver = LiveSourceResolver(celestrak=source)
        items = await resolver.resolve_async("Where is the ISS now?", None)
        assert items == []
        assert resolver.last_attempt["reason"]
        await source.aclose()


class TestEventResolution:
    async def test_it_fetches_open_events(self):
        source = eonet_source()
        resolver = LiveSourceResolver(eonet=source)
        items = await resolver.resolve_async(
            "what wildfires are burning right now?", None
        )
        assert items
        await source.aclose()

    async def test_events_may_be_presented_as_current(self):
        source = eonet_source()
        resolver = LiveSourceResolver(eonet=source)
        items = await resolver.resolve_async("current natural events", None)
        assert items[0].may_present_as_live is True
        await source.aclose()

    async def test_events_are_labelled_as_an_agency_api(self):
        source = eonet_source()
        resolver = LiveSourceResolver(eonet=source)
        items = await resolver.resolve_async("current natural events", None)
        assert items[0].source_type is SourceType.AGENCY_PUBLIC_API
        await source.aclose()

    async def test_item_count_is_bounded(self):
        source = eonet_source()
        resolver = LiveSourceResolver(eonet=source, max_items=1)
        items = await resolver.resolve_async("current natural events", None)
        assert len(items) <= 1
        await source.aclose()


class TestAssistantIntegration:
    async def test_live_data_changes_the_answers_origin(self, retriever):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        provider = MockAIProvider(responses=["The ISS element set is current [L1]."])

        class AsyncBridge:
            """The RAG layer calls `resolve` inside a running loop."""

            def __init__(self, inner):
                self.inner = inner
                self.items = []

            def resolve(self, question, intent):
                return self.items

        bridge = AsyncBridge(resolver)
        bridge.items = await resolver.resolve_async(
            "Where is the ISS right now?", None
        )

        assistant = SpaceAssistant(
            GroundedRAG(retriever, provider, live_resolver=bridge)
        )
        response = await assistant.ask("Where is the ISS right now?")
        assert response.data_origin in (DataOrigin.LIVE, DataOrigin.MIXED)
        assert response.diagnostics["live_items"] >= 1
        await source.aclose()

    async def test_without_live_data_the_answer_says_so(self, retriever):
        provider = MockAIProvider(responses=["The ISS orbits at 400 km [S1]."])
        assistant = SpaceAssistant(
            GroundedRAG(retriever, provider, live_resolver=NullLiveResolver())
        )
        response = await assistant.ask("Where is the ISS right now?")
        if not response.insufficient_evidence:
            kinds = {item.kind for item in response.limitations}
            assert "not_current" in kinds

    async def test_a_concept_question_never_triggers_a_live_fetch(self, retriever):
        source = celestrak_source()
        resolver = LiveSourceResolver(celestrak=source)
        provider = MockAIProvider(responses=["Answer [S1]."])
        assistant = SpaceAssistant(
            GroundedRAG(retriever, provider, live_resolver=resolver)
        )
        await assistant.ask("What causes Max-Q?")
        assert resolver.last_attempt == {}
        await source.aclose()

    def test_calling_resolve_inside_a_running_loop_is_refused(self):
        """Blocking would deadlock; pretending to have data would be worse."""
        import asyncio

        resolver = LiveSourceResolver()

        async def inside():
            return resolver.resolve("Where is the ISS now?", None)

        result = asyncio.get_event_loop().run_until_complete(inside())
        assert result == []
        assert "running event loop" in resolver.last_attempt["reason"]


async def _no_sleep(seconds):
    return None
