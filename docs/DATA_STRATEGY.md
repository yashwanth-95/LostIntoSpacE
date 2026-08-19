# Live, Cached, Static and Simulated Data

**Owner:** P4 (AI / Search / Data / Integration)
**Covers:** how the product decides where data comes from, how long it stays
usable, and what the user is told about it.

---

## 0. The rule

> Every piece of information the product shows carries a label saying whether it
> is **LIVE**, **CACHED**, **STATIC** or **SIMULATED** — and the label is
> derived from where the data came from, never asserted by the layer that
> displays it.

The label is `DataOrigin` on `AIResponse`, and `FreshnessClass` on every
canonical record. Neither is optional, and neither can be set by prompt text.

---

## 1. The four tiers

| Tier | What it is | Freshness | Where it comes from |
|---|---|---|---|
| **LIVE** | Fetched from a source during this request | Current, within the source's own cadence | `ai/grounding/live_sources.py` |
| **CACHED** | Previously fetched, still within its policy TTL | Current *as of* its fetch time | `data/cache/` |
| **STATIC** | Curated content that does not change | Not time-sensitive | `data/seeds/`, `data/offline/` |
| **SIMULATED** | Output of the educational simulator | A model result, not an observation | P3's engine, via `ai/analysis/` |

`MIXED` exists for answers drawing on more than one tier, and
`MODEL_KNOWLEDGE` for anything resting on the language model's own weights —
which the grounding rules make rare, and which is always disclosed.

---

## 2. LIVE — what actually gets fetched

Live fetching happens only when the intent classifier marks a question as being
about the present (`IntentAssessment.is_time_sensitive`), **and** a source
genuinely covers it. Two sources qualify today:

| Question kind | Source | Cadence | Authority |
|---|---|---|---|
| Satellite position, current orbital elements | CelesTrak GP | Every 2 hours | `SECONDARY_OPERATIONAL` |
| Current natural events | NASA EONET | Continuous | `AGENCY_PUBLIC_API` |

**Everything else returns nothing, deliberately.** A resolver that produced
something for every time-sensitive question would guarantee an answer, and
guaranteeing an answer is precisely how stale data gets presented as current.
When no live source applies, the answer carries a `not_current` limitation and
drops to `LOW` confidence.

### 2.1 "Live" does not mean "now"

A CelesTrak element set fetched this second describes the orbit **at its
epoch**, which may be up to two hours old, and is a mean element set for SGP4 —
not a position fix. The context item says so in its own text, and
`may_present_as_live` is set from the freshness assessment rather than from the
fact that a fetch happened.

This is the difference between "we just fetched it" and "it is current", and
the product must never collapse the two.

---

## 3. CACHED — freshness-aware, not TTL-only

`FreshnessAwareCache` returns three outcomes, not two:

| State | Meaning | May serve? |
|---|---|---|
| `FRESH` | Within the source's policy TTL | Yes, labelled `CACHED` |
| `STALE` | Present, past its TTL | Only with the caveat it supplies |
| `MISS` | Absent | No |

A stale entry is **not** a hit. `CacheLookup.hit` is false for it, and
`CacheLookup.caveat()` returns the sentence a caller must show.

### 3.1 What is cached, and for how long

TTLs come from `data/provenance/freshness.py`, so the cache and the answer layer
cannot disagree about what "current" means.

| Content | Source category | TTL |
|---|---|---|
| Satellite element sets | `NEAR_REAL_TIME` | 2 hours (CelesTrak's own cadence) |
| Natural events | `NEAR_REAL_TIME` | 2 hours |
| Small-body orbits, physical parameters | `PERIODIC` | 7 days |
| Exoplanet tables | `PERIODIC` | 7 days |
| Document metadata (NTRS) | `STATIC_REFERENCE` | No expiry |
| Embeddings | n/a | Invalidated by content hash, not by time |
| Bundled reference values | `STATIC_REFERENCE` | No expiry |

Embeddings are the exception that proves the rule: they are invalidated by a
content hash rather than a clock, because an embedding does not go stale — it
becomes wrong only when its source text or its model changes.

### 3.2 Degrading on failure

`get_or_fetch` will return a stale value when the source is unreachable, with
`CacheState.STALE` and the age attached. Degraded-but-labelled beats
unavailable. What it will not do is return stale data as though it were fresh —
the caller receives the state and must act on it.

---

## 4. STATIC — the offline knowledge package

`data/offline/` holds what the product can answer with no network at all:
fundamental astronomy constants, the eight planets, rocket-engineering
terminology, and the curated concept and mission sets in `data/seeds/`.

### 4.1 Every item names its source and version

This is the requirement, and it exists because offline data is the easiest kind
to present dishonestly: always available, always fast, never obviously out of
date. A planet's mass does not change, but the *value shipped* came from a
particular authority at a particular time.

Each `OfflineItem` carries `upstream_source` — the actual authority, such as
"NASA planetary fact sheet" — separately from `bundled_reference`, which only
says where it is stored. Every rendering states both, plus the dataset version.

### 4.2 The version is a content hash

`offline-20260819-<12 hex chars>`, computed from the items themselves. A
hand-maintained version number is wrong the first time someone edits a value and
forgets to bump it — and a wrong version is worse than none, because it is
trusted. A test asserts that changing any value changes the version.

---

## 5. SIMULATED — never an observation

Simulator output carries `SourceType.SIMULATION`, and every claim resting on it
is typed `ClaimType.SIMULATION`. `SpaceAssistant` enforces this after
generation rather than trusting the prompt: if any cited item came from the
simulator, `data_origin` becomes `SIMULATED` or `MIXED`, the citations are
retyped, and a `simulation_not_reality` limitation is attached.

`FailureAnalysis` goes further — it will not validate at all unless it states
which of the engine's documented approximations bear on its conclusion.

---

## 6. How a caller knows which tier it got

Three places, all machine-readable:

1. **`AIResponse.data_origin`** — the tier for the answer as a whole.
2. **`ContextItem.may_present_as_live`** — per source item, whether present-tense
   language is permissible about it.
3. **`AIResponse.freshness` and `.freshness_note`** — the answer is only as
   current as its least-current load-bearing source, and the note says which.

`AIResponse.may_present_as_current` combines these into the single boolean a UI
needs before writing "the ISS is currently at…".

---

## 7. What is not implemented

Stated so nobody assumes otherwise:

* **No Redis or shared cache.** The cache is in-process. The interface is five
  methods and a Redis backing swaps in behind them, but adding an operational
  dependency before there is a second node would be cost without benefit.
* **No background refresh.** Entries are refreshed on demand, not by a
  scheduler. A warming job is the obvious next step once request patterns are
  known — guessing them now would optimise for imagined traffic.
* **No live mission-status source.** Agency mission status is not available
  through any API this project has verified, so mission data is `STATIC` and
  labelled as such. It is not presented as current.
* **Live coverage is two sources.** Satellite elements and natural events. Every
  other time-sensitive question is answered with an explicit "this is not
  current" caveat rather than a guess.

---

*Person 4 document. No Person 1/2/3-owned files were modified.*
