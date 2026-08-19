# Provenance, Freshness and Data Lineage

**Owner:** P4 (AI / Search / Data / Integration)
**Implements:** Architecture principle #4 — *Data Provenance: every data point traces to its source.*
**Code:** [`packages/contracts/src/contracts/provenance.py`](../packages/contracts/src/contracts/provenance.py), [`data/provenance/`](../data/provenance/)

---

## 1. Why this exists

A space-education product that shows a number without saying where it came from
is indistinguishable from one that made the number up. Three failure modes this
system is built to prevent:

1. **Unattributed values.** A radius appears on screen and nobody can say which
   archive published it, or when.
2. **Silent staleness.** A satellite element set from last week is shown under a
   heading that says "current position".
3. **Laundered derivation.** A value this project computed gets displayed with
   the same authority as one an archive measured.

Each has a corresponding mechanism below.

---

## 2. `SourceReference` — where a value came from

Defined once, in `packages/contracts/`, because it crosses every team boundary:
the backend stores it, the frontend displays it, the AI layer cites it.

| Field | Meaning |
|---|---|
| `source_name` | Stable machine key, e.g. `jpl_sbdb`, `mpc_orbits`, `celestrak_gp` |
| `source_type` | Authority class — see below |
| `source_url` | Endpoint or landing page. **Never contains credentials** |
| `source_record_id` | The source's own id: SPK-ID, NORAD ID, packed designation, DOI |
| `retrieved_at` | When *we* fetched it |
| `source_timestamp` | The timestamp the *source* attaches to the record |
| `source_version` | Dataset/API version or release tag, when published |
| `license` | Licence the data is published under |
| `attribution` | Human-readable credit line for display |

### 2.1 Authority classes (`SourceType`)

Ordered from most to least authoritative. This ordering is what
`CanonicalRecord.primary_source` uses, and what the data-quality engine will use
to resolve conflicts.

| `SourceType` | Example | Notes |
|---|---|---|
| `PRIMARY_SCIENTIFIC` | JPL SBDB, MPC, NASA Exoplanet Archive | Authoritative archives |
| `LITERATURE` | NASA NTRS | Document metadata and citations |
| `AGENCY_PUBLIC_API` | APOD, NeoWs, EONET | Agency-published, outreach-oriented |
| `EO_CATALOGUE` | Copernicus, Bhoonidhi | Earth-observation product metadata |
| `SECONDARY_OPERATIONAL` | CelesTrak GP/OMM | Useful for current state, not a science archive |
| `BUNDLED_REFERENCE` | Offline fallback JSON | Ships with the app; never live |
| `EDITORIAL` | Human-authored lessons | Written by the team |
| `CALCULATED` | Anything we computed | **Never outranks a published value** |
| `UNKNOWN` | Incomplete provenance | Flagged by the quality engine |

### 2.2 Credential safety

`source_url` rejects anything containing `api_key=`, `token=`, `password=` and
similar markers. This is not paranoia: NASA endpoints take the key as a query
parameter, so a naive `str(request.url)` would persist a secret into the
database *and* into every API response that cites the record. Adapters redact
before constructing the reference.

### 2.3 Per-value attribution

`SourceReference` attaches at two levels:

* **Record level** — `CanonicalRecord.source_references`, a list, because one
  canonical record is routinely assembled from several archives.
* **Value level** — `Quantity.source`, so a record whose mass came from JPL and
  whose rotation period came from a bundled reference can say exactly that.

`collect_citations()` walks both levels, including nested models and dicts, and
`attribution_block()` renders them for display.

---

## 3. Data lineage

`DataLineage` records the path a value took:

```
source -> transformation -> normalized value -> derived value -> final record
```

Each `LineageStep` carries a sequence number, a `TransformationType`, the input
field paths, the output field path, optional before/after scalar snapshots, the
module that performed it, and (for `FETCH`) the `SourceReference`.

### 3.1 Transformation types

`FETCH` · `PARSE` · `UNIT_CONVERSION` · `FIELD_MAPPING` · `EPOCH_CONVERSION` ·
`FRAME_ANNOTATION` · `NAME_NORMALIZATION` · `DERIVATION` · `MERGE` ·
`CONFLICT_RESOLUTION` · `VALIDATION` · `REDACTION` · `FINALIZATION`

### 3.2 Building lineage

`LineageBuilder` assigns sequence numbers automatically, so steps cannot be
recorded out of order by accident:

```python
builder = LineageBuilder("asteroid:1-ceres")
builder.fetched(sbdb_ref, module="data.sources.jpl.sbdb")
builder.parsed("extracted phys_par block")
builder.normalized(
    TransformationType.UNIT_CONVERSION,
    "diameter km -> m",
    inputs=["phys_par.diameter"], output="physical.diameter",
    input_value=939.4, output_value=939400.0,
)
builder.validated("dimension check passed")
builder.finalized()
```

### 3.3 Answering "where did this number come from?"

```python
lineage.explain_field("physical.density")
```

returns the ordered steps that produced that field, and appends an explicit
note when the value was computed rather than received.

### 3.4 Derived values

`derive_quantity()` is the only sanctioned way to produce a computed value. It:

* requires the caller to name the inputs it was computed from,
* tags the result with a `CALCULATED` source reference that lists the
  contributing archives,
* records a `DERIVATION` step in the lineage.

Because `CALCULATED` sits at the bottom of the authority ordering, a derived
density can never displace a published one.

---

## 4. Freshness

### 4.1 Two different questions

These are separate and are modelled separately:

| Concept | Describes | Example |
|---|---|---|
| `SourceCategory` | How often the **publisher** updates | CelesTrak GP → `NEAR_REAL_TIME` (2 h) |
| `FreshnessClass` | How old **this record's content** is | An element set with a 3-day-old epoch → `HISTORICAL` |

A `NEAR_REAL_TIME` source routinely serves `HISTORICAL` records. Conflating the
two is exactly how a stale element set ends up labelled "current".

### 4.2 Source categories

| Category | Update cadence | Cache | May be called live |
|---|---|---|---|
| `REAL_TIME` | seconds–minutes | none / very short | yes |
| `NEAR_REAL_TIME` | 1–6 hours | TTL matched to publisher cadence | yes |
| `DAILY` | ~24 h | 6–24 h | usually not |
| `PERIODIC` | weekly–monthly | days | no |
| `STATIC_REFERENCE` | years / never | bundled | **never** |

### 4.3 Record freshness classes

`REAL_TIME` · `NEAR_REAL_TIME` · `RECENT` · `HISTORICAL` · `STATIC`

Assigned by comparing the record's **temporal anchor** against thresholds in its
source's `FreshnessPolicy`. The anchor is the instant the record's *content*
describes, not the instant we fetched it:

| Record type | Anchor |
|---|---|
| `OrbitRecord` | `epoch` |
| `Observation` | `observed_at` |
| `EphemerisRecord` | `start_time`, else earliest state epoch |
| everything else | `valid_at` |

A record with no anchor is classified `HISTORICAL`, never something more
optimistic — refusing to guess is the safe default.

### 4.4 The two rules, and how they are enforced

Both reduce to a single boolean, `FreshnessAssessment.may_present_as_live`.
Callers must consult it before using the words "current", "live" or "now".

> **Rule 1 — never call a historical orbital element "current".**
> `may_present_as_live` is forced to `False` whenever `freshness_class` is
> `HISTORICAL` or `STATIC`, or whenever the content exceeds the policy's
> `max_age`, regardless of how recently it was fetched.

> **Rule 2 — never call cached data "live" unless its freshness policy allows it.**
> `may_present_as_live` starts from `policy.allows_live_presentation` (false for
> every archive source) and is forced to `False` again once the cached copy is
> past its TTL.

`FreshnessAssessment.reason` always states *why*, so the caveat can be shown to
the user rather than hidden. `freshness_caveat()` renders it as a sentence, and
`Citation.to_text()` appends it inline.

### 4.5 Registered policies

Defaults live in `data/provenance/freshness.py::POLICIES`, keyed by
`source_name`. Highlights:

| Source | Category | TTL | Max age | Live? |
|---|---|---|---|---|
| `celestrak_gp` | `NEAR_REAL_TIME` | 2 h | 3 d | **yes** |
| `nasa_eonet` | `NEAR_REAL_TIME` | 1 h | 30 d | **yes** |
| `nasa_neows` | `DAILY` | 12 h | 7 d | no |
| `jpl_horizons` | `PERIODIC` | 1 d | — | no |
| `jpl_sbdb` | `PERIODIC` | 1 d | 180 d | no |
| `mpc_orbits` | `DAILY` | 1 d | 180 d | no |
| `mpc_observations` | `DAILY` | 7 d | — | no |
| `nasa_exoplanet_archive` | `PERIODIC` | 7 d | 365 d | no |
| `nasa_ntrs` | `PERIODIC` | 30 d | — | no |
| `esa_copernicus` | `DAILY` | 6 h | — | no |
| `isro_bhoonidhi` | `DAILY` | 6 h | — | no |
| `bundled_reference` | `STATIC_REFERENCE` | — | — | **never** |

Sources with no registered policy fall back to `DEFAULT_POLICY`, which is
deliberately conservative: `PERIODIC`, 1 h TTL, never live.

Two entries deserve comment:

* **`jpl_horizons` has no `max_age`.** An ephemeris computed for a requested
  epoch is exact for that epoch and does not decay — but it is never "live"
  either. Both facts are expressed: `max_age=None`,
  `allows_live_presentation=False`.
* **`mpc_observations` has no `max_age`.** An observation is a historical
  measurement by nature. Being old is not the same as being stale, and the
  quality engine must not report it as a problem.

---

## 5. Missing provenance is an error

`require_provenance(record, lineage)` raises `ProvenanceError` when:

* the record has no `source_references`, or
* the lineage records no `FETCH` step carrying a source.

This runs before indexing. An unattributed record cannot be cited, cannot be
refreshed, and cannot be checked against its source, so it does not enter the
index at all. This is stricter than a warning on purpose — a warning would be
ignored and the record would ship.

---

## 6. What this obliges downstream code to do

| Layer | Obligation |
|---|---|
| Adapters (`data/sources/`) | Construct a `SourceReference` per response, redact credentials, record a `FETCH` lineage step. **Must not** set `freshness_class` — they know their source's cadence, not a record's age |
| Normalizers | Record a lineage step per conversion, preserving before/after values |
| Ingestion | Call `apply_freshness()` and `require_provenance()` before indexing |
| Search | Every scientific result exposes its source metadata |
| AI (`ai/rag`, `ai/safety`) | Cite `SourceReference` for every factual claim, and surface `freshness_caveat()` verbatim rather than paraphrasing it away |
| Frontend | Render `attribution_block()` / `Citation.to_dict()` beside the data |

---

## 7. Test coverage

`data/tests/test_provenance_freshness.py` and
`data/tests/test_provenance_lineage.py` cover: source references, multiple
sources on one record, transformation chains, derived data and its authority
ranking, stale data, freshness metadata on every anchored record type, cache
expiry, and missing provenance.

---

*Person 4 document. No Person 1/2/3-owned files were modified.*
