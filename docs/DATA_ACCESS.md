# Data-Access Restrictions and Credentials

**Owner:** P4 (AI / Search / Data / Integration)
**Covers:** every external source wired into `data/sources/`.

This document records what each provider actually permits, what credentials are
needed, and what the product does when access is unavailable. It exists because
the failure that matters most here is not a missing feature — it is telling a
user "no data" when the truth is "you are not authorized".

---

## 0. The rule

> An authorization gap is reported as an authorization gap, never as an empty
> result.

Every adapter distinguishes three states:

| State | Meaning | Surfaced as |
|---|---|---|
| Found | The provider returned records | Normal results |
| Not found | The provider searched and has nothing matching | Empty result set |
| Not authorized | We could not ask, or were refused | `SourceAuthError` / `HealthStatus.credentials_missing` / `AccessStatus.CREDENTIALS_REQUIRED` |

`EOProduct.access_explanation()` turns the third state into a sentence a user
can act on.

---

## 1. Credentials by source

Credentials come only from environment variables. Nothing is committed, and no
default credential exists for any gated source.

| Source | Credential needed | Environment variables | Without it |
|---|---|---|---|
| NASA APOD / NeoWs | API key | `NASA_API_KEY` (falls back to `DEMO_KEY`) | Works, but at `DEMO_KEY` limits |
| NASA EONET | none | — | Full access |
| NASA NTRS | none | — | Full access |
| JPL SBDB / Horizons | none | — | Full access |
| MPC Orbits / Observations | none | — | Full access |
| NASA Exoplanet Archive | none | — | Full access |
| CelesTrak | none | — | Full access |
| **ESA / Copernicus** | none to *search*; account to *download* | `COPERNICUS_ACCESS_TOKEN` | Metadata search works; product download does not |
| **ISRO / Bhoonidhi** | account, granted on request | `BHOONIDHI_ACCESS_TOKEN`, or `BHOONIDHI_USERNAME` + `BHOONIDHI_PASSWORD` | Nothing is retrievable; adapter reports `credentials_missing` |

Every variable is also settable under the project's own prefix
(`LIS_<PROVIDER>_API_KEY`), along with per-provider limit overrides
(`LIS_<PROVIDER>_REQUESTS_PER_HOUR`, `_TIMEOUT_SECONDS`, `_MAX_ATTEMPTS`).

---

## 2. NASA

**Limits.** NASA documents 1,000 requests/hour for a registered key, and much
lower limits for the shared `DEMO_KEY` (30/hour, 50/day per IP). Every response
carries `X-RateLimit-Limit` and `X-RateLimit-Remaining`, and the adapter honours
the reported remaining quota over its own estimate.

**Consequence for ingestion.** Running on `DEMO_KEY` will throttle. The gaps
that produces must not be read as objects not existing — `NasaNeoWsSource.
using_demo_key` exists so a run can say which key it used.

**Scope limits.** APOD is media and an editorial caption; it is deliberately not
mapped to `SpaceObject`. EONET events become `NaturalEvent`. NTRS citations
become `DocumentRecord`.

**NTRS full text.** Only metadata is indexed by default. A document's full text
is eligible only when the source's own `copyright.determinationType` is
`GOV_PUBLIC_USE_PERMITTED`; `DocumentRecord.may_index_full_text` gates it, and
defaults to `False`.

---

## 3. JPL

Open, no credentials. JPL asks for reasonable request rates rather than
publishing a hard quota, so the adapters self-limit to roughly one request per
second, and Horizons — which computes on demand — to one every two seconds with
no concurrency.

---

## 4. Minor Planet Center

Open, no credentials. The MPC asks users to query considerately and to prefer
published data files over bulk API scraping. The adapters self-limit to one
request per second with no concurrency, and there is no bulk-download path.

Note the API's unusual calling convention: a `GET` carrying a JSON body with
`Content-Type: application/json`. A plain `GET` is answered with a content-type
error, which is why both MPC adapters override `health_check`.

---

## 5. NASA Exoplanet Archive

Open, no credentials. The archive asks that queries be specific and that bulk
needs be met by downloading a whole table rather than by issuing many small
queries. Accordingly:

* Unfiltered table scans are refused by the adapter.
* Every query is built from a whitelisted table, whitelisted columns and typed
  predicates (`data/sources/adql.py`). No caller-supplied SQL fragment reaches
  the service.
* Requests are self-limited to one every two seconds, never concurrent.

---

## 6. CelesTrak

Open, no credentials, but with an explicit usage expectation: **GP data is
updated every two hours, and users should retrieve only what they need and only
once per update.** Honoured in three places:

1. `FreshnessPolicy` for `celestrak_gp` sets a two-hour cache TTL matching the
   publication cadence.
2. The adapter offers targeted queries only — catalog number, international
   designator, group, special-interest list, name. A whole-catalogue pull is
   refused.
3. The request rate is capped at one every two seconds.

**Authority.** CelesTrak is labelled `SECONDARY_OPERATIONAL`, and every derived
record carries `SECONDARY_OPERATIONAL_ORBIT_FEED`. It must never be presented as
equivalent to a JPL solution.

---

## 7. ESA / Copernicus

**What is open.** The Copernicus Data Space Ecosystem OData catalogue is
queryable without credentials. Product *metadata* — mission, instrument,
processing level, sensing time, footprint, cloud cover — is freely readable, and
that is what this project indexes.

**What is not.** Downloading a product requires a Copernicus Data Space account.
Products are large (a single Sentinel-2 scene is several hundred megabytes), and
account-level quotas and throttling apply to download endpoints.

**What this project does.**

* Metadata-first, by design. No adapter downloads a product, and `EOProduct` has
  no field to hold pixel data.
* Discovered products carry `AccessStatus.CREDENTIALS_REQUIRED` when no token is
  configured, and `AccessStatus.AUTHORIZED` when one is.
* A product the catalogue marks `Online: false` has moved to long-term storage
  and needs a restore request before download; it is reported as
  `AccessStatus.OFFLINE`, which is a different problem from a missing account.
* Collections are restricted to an allow-list, and every `$filter` clause is
  built from typed inputs — an OData filter is a query language, and this is a
  shared public service.

**Licence and attribution.** Copernicus data is free and open under the
Copernicus licence. Products must be credited: *"Contains modified Copernicus
Sentinel data"*. `SourceReference.attribution` carries this automatically.

---

## 8. ISRO / Bhoonidhi

**Access model.** Bhoonidhi publishes an official API specification at
`https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/`, served from
`https://bhoonidhi-api.nrsc.gov.in`, with a STAC-style search surface. It is
**not** an open public API: API access is granted on request, and the
specification directs users to contact `bhoonidhi@nrsc.gov.in`.

**Authentication.** `POST /auth/token` exchanges credentials for a JWT access
token and a refresh token; requests carry `Authorization: Bearer <token>`.

**Documented limits**, configured rather than guessed:

| Limit | Value |
|---|---|
| Authentication | 20 requests/hour per IP |
| Search | 3 requests/second per IP |
| Download | 3 concurrent per user/IP |

The specification asks explicitly that callers not fetch a new token per
request, so the adapter caches the token for its lifetime and refreshes it two
minutes before expiry. The configured search rate is 2/second, leaving margin
under the documented 3/second.

**No scraping.** An official interface exists, so it is the only route. There is
no HTML parsing path and no unauthenticated fallback anywhere in the adapter.

**Without credentials.** `health_check()` returns
`credentials_missing=True` with a message naming the environment variables and
the contact address. `search()` raises `SourceAuthError` *before making any
request*, so the absence of an account can never be mistaken for an absence of
data.

**Test coverage.** The default suite is fully mocked, using a fixture built from
the published specification (a STAC `FeatureCollection`) rather than a
recording — obtaining a real response requires an account this project does not
hold, and the fixture says so in its own test module. An integration path exists
and runs only when `LOSTINTOSPACE_LIVE_TESTS=1` *and* credentials are present.

---

## 9. Live tests

Every source's live tests are opt-in:

```
LOSTINTOSPACE_LIVE_TESTS=1 pytest data/tests -m live
```

The default suite touches no network at all. This is deliberate: CI must not
depend on a third-party archive's availability, and a provider must never be hit
by a routine test run.

---

*Person 4 document. No Person 1/2/3-owned files were modified.*
