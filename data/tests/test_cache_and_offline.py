"""Live / cached / static separation: cache freshness, offline package."""

from datetime import datetime, timedelta, timezone

import pytest

from contracts.provenance import FreshnessClass, SourceType
from data.cache import CacheState, FreshnessAwareCache
from data.offline import build_offline_package
from data.provenance.freshness import POLICIES, policy_for

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class Clock:
    """A movable clock, so expiry is tested by advancing time not sleeping."""

    def __init__(self, start=NOW):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class TestCacheFreshness:
    def test_a_fresh_entry_is_a_hit(self):
        cache = FreshnessAwareCache(now=Clock())
        cache.put("k", "value", "celestrak_gp")
        lookup = cache.get("k")
        assert lookup.state is CacheState.FRESH
        assert lookup.hit
        assert lookup.value == "value"

    def test_an_expired_entry_is_stale_not_a_hit(self):
        """The distinction the whole cache exists for."""
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        cache.put("k", "value", "celestrak_gp")
        clock.advance(hours=6)

        lookup = cache.get("k")
        assert lookup.state is CacheState.STALE
        assert lookup.hit is False
        assert lookup.has_value is True

    def test_a_stale_lookup_carries_a_caveat(self):
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        cache.put("k", "value", "celestrak_gp")
        clock.advance(hours=6)

        caveat = cache.get("k").caveat(clock())
        assert caveat
        assert "past its freshness window" in caveat
        assert "hour(s) ago" in caveat

    def test_a_fresh_lookup_has_no_caveat(self):
        cache = FreshnessAwareCache(now=Clock())
        cache.put("k", "v", "celestrak_gp")
        assert cache.get("k").caveat() is None

    def test_a_miss(self):
        lookup = FreshnessAwareCache().get("absent")
        assert lookup.state is CacheState.MISS
        assert not lookup.has_value

    def test_ttl_comes_from_the_source_policy(self):
        """CelesTrak publishes every two hours; the TTL must match."""
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        entry = cache.put("k", "v", "celestrak_gp")
        expected = policy_for("celestrak_gp").cache_ttl
        assert entry.expires_at == clock() + expected

    def test_different_sources_get_different_ttls(self):
        cache = FreshnessAwareCache(now=Clock())
        operational = cache.put("a", "v", "celestrak_gp")
        archive = cache.put("b", "v", "jpl_sbdb")
        assert operational.expires_at != archive.expires_at

    def test_static_content_never_expires(self):
        cache = FreshnessAwareCache(now=Clock())
        entry = cache.put("k", "v", "bundled_reference")
        if policy_for("bundled_reference").cache_ttl is None:
            assert entry.expires_at is None
            assert entry.is_fresh(NOW + timedelta(days=3650))

    def test_an_explicit_ttl_overrides_the_policy(self):
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        entry = cache.put("k", "v", "jpl_sbdb", ttl=timedelta(seconds=30))
        assert entry.expires_at == clock() + timedelta(seconds=30)

    def test_the_source_category_is_recorded(self):
        cache = FreshnessAwareCache(now=Clock())
        entry = cache.put("k", "v", "celestrak_gp")
        assert entry.source_category == "NEAR_REAL_TIME"

    def test_the_freshness_class_is_computed_from_current_age(self):
        """An entry that was near-real-time at write is not still so later."""
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        entry = cache.put("k", "v", "celestrak_gp")

        fresh = entry.freshness_class(clock())
        clock.advance(days=10)
        aged = entry.freshness_class(clock())
        assert fresh != aged

    def test_age_is_described_readably(self):
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        entry = cache.put("k", "v", "celestrak_gp")
        clock.advance(minutes=45)
        assert "minute(s) ago" in entry.describe_age(clock())


class TestCacheMechanics:
    def test_key_construction_is_order_independent(self):
        first = FreshnessAwareCache.make_key("s", "op", a=1, b=2)
        second = FreshnessAwareCache.make_key("s", "op", b=2, a=1)
        assert first == second

    def test_keys_separate_sources_and_operations(self):
        assert FreshnessAwareCache.make_key("a", "op") != (
            FreshnessAwareCache.make_key("b", "op")
        )

    def test_invalidate(self):
        cache = FreshnessAwareCache()
        cache.put("k", "v", "jpl_sbdb")
        assert cache.invalidate("k") is True
        assert cache.get("k").state is CacheState.MISS
        assert cache.invalidate("k") is False

    def test_invalidate_by_source(self):
        cache = FreshnessAwareCache()
        cache.put("a", "v", "jpl_sbdb")
        cache.put("b", "v", "jpl_sbdb")
        cache.put("c", "v", "celestrak_gp")
        assert cache.invalidate_source("jpl_sbdb") == 2
        assert len(cache) == 1

    def test_lru_eviction(self):
        cache = FreshnessAwareCache(max_entries=3)
        for index in range(5):
            cache.put("k{0}".format(index), index, "jpl_sbdb")
        assert len(cache) == 3
        assert cache.stats.evictions == 2

    def test_reading_an_entry_makes_it_recently_used(self):
        cache = FreshnessAwareCache(max_entries=2)
        cache.put("a", 1, "jpl_sbdb")
        cache.put("b", 2, "jpl_sbdb")
        cache.get("a")
        cache.put("c", 3, "jpl_sbdb")
        assert "a" in cache
        assert "b" not in cache

    def test_purge_expired(self):
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        cache.put("k", "v", "celestrak_gp")
        clock.advance(hours=6)
        assert cache.purge_expired() == 1
        assert len(cache) == 0

    def test_stats_are_recorded(self):
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        cache.put("k", "v", "celestrak_gp")
        cache.get("k")
        cache.get("absent")
        clock.advance(hours=6)
        cache.get("k")

        assert cache.stats.hits == 1
        assert cache.stats.misses == 1
        assert cache.stats.stale_hits == 1
        assert 0.0 < cache.stats.hit_rate < 1.0
        assert "hit rate" in cache.stats.summary()

    async def test_get_or_fetch_stores_on_a_miss(self):
        cache = FreshnessAwareCache(now=Clock())
        calls = []

        async def fetch():
            calls.append(1)
            return "fetched"

        value, state = await cache.get_or_fetch("k", "jpl_sbdb", fetch)
        assert value == "fetched"
        assert state is CacheState.MISS

        value, state = await cache.get_or_fetch("k", "jpl_sbdb", fetch)
        assert state is CacheState.FRESH
        assert len(calls) == 1

    async def test_get_or_fetch_falls_back_to_stale_on_error(self):
        """Degraded but labelled beats unavailable."""
        clock = Clock()
        cache = FreshnessAwareCache(now=clock)
        cache.put("k", "old", "celestrak_gp")
        clock.advance(hours=6)

        async def failing():
            raise RuntimeError("source down")

        value, state = await cache.get_or_fetch("k", "celestrak_gp", failing)
        assert value == "old"
        assert state is CacheState.STALE

    async def test_get_or_fetch_raises_when_stale_is_not_allowed(self):
        cache = FreshnessAwareCache(now=Clock())

        async def failing():
            raise RuntimeError("source down")

        with pytest.raises(RuntimeError):
            await cache.get_or_fetch(
                "k", "jpl_sbdb", failing, allow_stale_on_error=False
            )


class TestOfflinePackage:
    @pytest.fixture(scope="class")
    def package(self):
        return build_offline_package()

    def test_it_covers_the_required_categories(self, package):
        kinds = {item.kind for item in package.items}
        assert {"planet", "astronomy", "terminology"} <= kinds

    def test_common_planets_are_present(self, package):
        names = {item.name for item in package.by_kind("planet")}
        assert {"Mars", "Jupiter", "Earth", "Saturn"} <= names

    def test_terminology_is_present(self, package):
        assert package.lookup("Delta-v") is not None
        assert package.lookup("Apogee") is not None

    def test_fundamental_astronomy_is_present(self, package):
        assert package.lookup("Astronomical unit") is not None
        assert package.lookup("Standard gravity") is not None

    def test_every_item_names_its_upstream_source(self, package):
        """The requirement: offline data must show where it came from."""
        for item in package.items:
            assert item.upstream_source, item.id

    def test_every_item_renders_with_source_and_version(self, package):
        item = package.lookup("Mars")
        text = package.describe_item(item)
        assert "NASA planetary fact sheet" in text
        assert package.version in text
        assert package.dataset_date.isoformat() in text

    def test_the_version_is_derived_from_content(self, package):
        assert package.version.startswith("offline-2026")
        assert len(package.version.split("-")[-1]) == 12

    def test_the_version_is_stable_across_builds(self):
        assert build_offline_package().version == build_offline_package().version

    def test_changing_a_value_changes_the_version(self, package):
        """A hand-maintained version is wrong the first time someone forgets."""
        from data.offline.package import _compute_version

        original = _compute_version(package.items, package.dataset_date)
        mutated = [item.model_copy() for item in package.items]
        mutated[0] = mutated[0].model_copy(
            update={"detail": dict(mutated[0].detail, mass_kg="999")}
        )
        assert _compute_version(mutated, package.dataset_date) != original

    def test_the_package_is_always_static(self, package):
        assert package.freshness_class is FreshnessClass.STATIC

    def test_the_source_reference_carries_the_version(self, package):
        reference = package.source_reference()
        assert reference.source_type is SourceType.BUNDLED_REFERENCE
        assert reference.source_version == package.version
        assert package.version in reference.attribution

    def test_lookup_is_case_insensitive(self, package):
        assert package.lookup("mars") is not None
        assert package.lookup("MARS") is not None

    def test_lookup_finds_aliases(self, package):
        assert package.lookup("Isp") is not None
        assert package.lookup("NORAD ID") is not None

    def test_an_unknown_name_returns_nothing(self, package):
        assert package.lookup("Zzyzx") is None

    def test_planet_values_carry_units_in_their_field_names(self, package):
        mars = package.lookup("Mars")
        assert "mass_kg" in mars.detail
        assert "equatorial_radius_km" in mars.detail

    def test_items_have_unique_ids(self, package):
        ids = [item.id for item in package.items]
        assert len(ids) == len(set(ids))
