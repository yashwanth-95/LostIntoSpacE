"""Verifying that a source is what it claims to be.

The attack this closes: a record asserts `source_name="jpl_sbdb"` and
`source_url="https://evil.example/fake-orbit"`. Everything downstream trusts the
name — the authority policy ranks it first, the reranker boosts it, the citation
validator confirms it was supplied — and a user clicking through to check it
lands on the attacker's page.

Nothing in the pipeline caught that before this module, because every layer was
reasoning about the *declared* source rather than the actual one.

The check is a domain allow-list. Each known source declares the hosts it may
legitimately link to, taken from the adapter configuration rather than typed in
twice. A URL outside its source's hosts is an impersonation attempt or a
misconfiguration; both need surfacing, and neither should reach a user as a
clickable citation.
"""

from enum import Enum
from typing import Dict, List, Optional, Sequence, Set
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from contracts.provenance import SourceReference, SourceType

__all__ = [
    "UrlVerdict",
    "SourceCheck",
    "SOURCE_HOSTS",
    "verify_source_reference",
    "verify_context_items",
]

#: Hosts each source may legitimately link to. Derived from the adapter base
#: URLs in `data/sources/`; kept here as a flat map so the check does not need
#: to construct an adapter to validate a record.
SOURCE_HOSTS: Dict[str, Set[str]] = {
    "jpl_sbdb": {"ssd-api.jpl.nasa.gov", "ssd.jpl.nasa.gov"},
    "jpl_horizons": {"ssd.jpl.nasa.gov", "ssd-api.jpl.nasa.gov"},
    "mpc_orbits": {"data.minorplanetcenter.net", "minorplanetcenter.net",
                   "www.minorplanetcenter.net"},
    "mpc_observations": {"data.minorplanetcenter.net", "minorplanetcenter.net",
                         "www.minorplanetcenter.net"},
    "nasa_neows": {"api.nasa.gov", "ssd-api.jpl.nasa.gov"},
    "nasa_apod": {"api.nasa.gov", "apod.nasa.gov"},
    "nasa_eonet": {"eonet.gsfc.nasa.gov", "api.nasa.gov"},
    "nasa_ntrs": {"ntrs.nasa.gov"},
    "nasa_exoplanet_archive": {"exoplanetarchive.ipac.caltech.edu"},
    "celestrak_gp": {"celestrak.org", "celestrak.com", "www.celestrak.org"},
    "esa_copernicus": {"catalogue.dataspace.copernicus.eu",
                       "dataspace.copernicus.eu",
                       "zipper.dataspace.copernicus.eu"},
    "isro_bhoonidhi": {"bhoonidhi-api.nrsc.gov.in", "bhoonidhi.nrsc.gov.in"},
}

#: Sources that legitimately have no URL — they are local, not fetched.
_LOCAL_SOURCES = {
    "lostintospace_editorial", "bundled_reference", "simulation_engine",
    "user_project", "derived",
}

#: Schemes a citation may use. Anything else — `javascript:`, `data:`, `file:` —
#: is either an attack or a bug, and never a scientific reference.
_ALLOWED_SCHEMES = {"https", "http"}


class UrlVerdict(str, Enum):
    """Outcome of checking one source URL."""

    OK = "OK"
    #: No URL. Fine for local sources, noted for remote ones.
    ABSENT = "ABSENT"
    #: The host does not belong to the source that claims it.
    HOST_MISMATCH = "HOST_MISMATCH"
    #: `javascript:`, `data:` and similar.
    UNSAFE_SCHEME = "UNSAFE_SCHEME"
    #: Not parseable as a URL at all.
    MALFORMED = "MALFORMED"
    #: A source this module has no host list for.
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"


class SourceCheck(BaseModel):
    """The result of verifying one source reference."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    verdict: UrlVerdict
    url: Optional[str] = None
    host: Optional[str] = None
    expected_hosts: List[str] = Field(default_factory=list)
    detail: str = ""

    @property
    def is_safe(self) -> bool:
        """Whether this URL may be shown to a user as a citation link."""
        return self.verdict in (UrlVerdict.OK, UrlVerdict.ABSENT)

    @property
    def is_impersonation(self) -> bool:
        """Whether this looks like a source claiming to be another."""
        return self.verdict in (
            UrlVerdict.HOST_MISMATCH, UrlVerdict.UNSAFE_SCHEME
        )


def verify_source_reference(reference: SourceReference) -> SourceCheck:
    """Check that a reference's URL belongs to the source it names."""
    name = reference.source_name
    url = reference.source_url

    if not url:
        if name in _LOCAL_SOURCES:
            return SourceCheck(
                source_name=name, verdict=UrlVerdict.ABSENT,
                detail="local source; no URL expected",
            )
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.ABSENT,
            detail="remote source with no URL; the citation cannot be followed",
        )

    try:
        parsed = urlparse(str(url))
    except Exception:  # noqa: BLE001 - a URL that will not parse is malformed
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.MALFORMED, url=str(url),
            detail="URL could not be parsed",
        )

    scheme = (parsed.scheme or "").lower()
    if scheme and scheme not in _ALLOWED_SCHEMES:
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.UNSAFE_SCHEME, url=str(url),
            detail="scheme {0!r} is not permitted in a citation".format(scheme),
        )
    if not parsed.netloc:
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.MALFORMED, url=str(url),
            detail="URL has no host",
        )

    #: Strip credentials and port before comparing. `evil.example` reached via
    #: `https://ssd-api.jpl.nasa.gov@evil.example/` must not pass.
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.split("@", 1)[1]
    host = host.split(":", 1)[0]

    expected = SOURCE_HOSTS.get(name)
    if expected is None:
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.UNKNOWN_SOURCE, url=str(url),
            host=host,
            detail="no known hosts registered for source {0!r}".format(name),
        )

    if host in expected or any(
        host.endswith("." + allowed) for allowed in expected
    ):
        return SourceCheck(
            source_name=name, verdict=UrlVerdict.OK, url=str(url), host=host,
            expected_hosts=sorted(expected),
        )

    return SourceCheck(
        source_name=name, verdict=UrlVerdict.HOST_MISMATCH, url=str(url),
        host=host, expected_hosts=sorted(expected),
        detail=(
            "reference claims source {0!r} but links to {1!r}, which is not one "
            "of its known hosts".format(name, host)
        ),
    )


def verify_context_items(items: Sequence) -> List[SourceCheck]:
    """Check every context item before it reaches a model or a user."""
    checks: List[SourceCheck] = []
    for item in items:
        source = getattr(item, "source", None)
        if source is None:
            continue
        check = verify_source_reference(source)
        #: An item's own `url` may differ from its source reference's; both are
        #: user-visible, so both are checked.
        item_url = getattr(item, "url", None)
        if item_url and item_url != source.source_url:
            check_item = verify_source_reference(
                source.model_copy(update={"source_url": item_url})
            )
            if not check_item.is_safe:
                check = check_item
        checks.append(check)
    return checks
