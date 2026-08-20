import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { ObjectField, type FieldObject } from '@/components/features/field/ObjectField';
import { Starfield } from '@/components/features/field/Starfield';
import { Button } from '@/components/ui';
import { catalog, type CatalogObject, type CatalogSummary } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

/**
 * The front door.
 *
 * Not a hero and a grid of feature cards. The page opens *into* the object
 * field: a curated arrangement of real bodies, drawn from catalogue data, lit
 * by the cursor. Approaching one reveals its name, then its measured
 * properties, then a way in. The composition asks you to look before it asks
 * you to click.
 *
 * ## Why this shape
 *
 * The product's whole argument is that space is a thing you inspect and
 * experiment on rather than read about. A landing page made of cards asserts
 * that; a landing page you can move a cursor through and watch a terminator
 * sweep across Jupiter *demonstrates* it before a single word is read.
 *
 * Everything shown is real. The bodies are placed and coloured from the
 * catalogue, their properties come from published bulk parameters, and the
 * photograph in the inspection panel is verified NASA imagery with its
 * attribution attached. Nothing here is a mock-up of a feature that does not
 * exist.
 *
 * The journey below the fold is laid out as a path rather than a row of tiles,
 * because it *is* a sequence: explore, understand, build, simulate, evaluate.
 */

export default function Landing() {
  const navigate = useNavigate();
  const continueAsGuest = useAuthStore((s) => s.continueAsGuest);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [objects, setObjects] = useState<FieldObject[]>([]);
  const [summary, setSummary] = useState<CatalogSummary | null>(null);
  const [focused, setFocused] = useState<FieldObject | null>(null);
  const [detail, setDetail] = useState<CatalogObject | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    catalog
      .field()
      .then(({ objects: field }) => {
        if (!cancelled) setObjects(field);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    catalog
      .summary()
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // The full record is fetched only when a body is actually approached, so the
  // first paint ships eleven small objects rather than every property table.
  useEffect(() => {
    if (!focused) return;
    let cancelled = false;
    catalog
      .object(focused.id)
      .then((object) => {
        if (!cancelled) setDetail(object);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [focused]);

  const relatedIds = useMemo(
    () => (detail && focused && detail.id === focused.id ? detail.related_ids : []),
    [detail, focused],
  );

  const enterAsGuest = () => {
    continueAsGuest();
    navigate('/explore');
  };

  const active = focused && detail && detail.id === focused.id ? detail : null;

  return (
    <div className="relative">
      {/* ── The field ─────────────────────────────────────────── */}
      <section className="relative min-h-[92vh] overflow-hidden">
        <Starfield className="absolute inset-0" density={0.00016} />

        {/* A deep-field photograph, held far back so it reads as depth rather
            than as a background image. */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.22] mix-blend-screen"
          aria-hidden="true"
          style={{
            backgroundImage:
              'url(https://images-assets.nasa.gov/image/PIA25434/PIA25434~medium.jpg)',
            backgroundSize: 'cover',
            backgroundPosition: '62% 38%',
            maskImage: 'radial-gradient(ellipse 70% 60% at 70% 40%, black 0%, transparent 72%)',
            WebkitMaskImage:
              'radial-gradient(ellipse 70% 60% at 70% 40%, black 0%, transparent 72%)',
          }}
        />

        {objects.length > 0 && (
          <ObjectField
            objects={objects}
            onFocus={setFocused}
            onSelect={(object) => navigate(`/explore/${object.id}`)}
            relatedIds={relatedIds}
            className="absolute inset-0 z-field"
          />
        )}

        {/*
          A scrim over the text column. Painted *after* the field and before
          the copy, so it dims the bodies behind the words without touching the
          rest of the composition. The field is the point, so the copy cannot
          simply be moved off it — but text over a lit planet is unreadable,
          and unreadable text is worse than no field at all.
        */}
        <div
          className="pointer-events-none absolute inset-y-0 left-0 z-objects w-full max-w-[46rem]"
          aria-hidden="true"
          style={{
            background:
              'linear-gradient(100deg, rgba(6,6,5,0.94) 0%, rgba(6,6,5,0.88) 26%, rgba(6,6,5,0.55) 52%, rgba(6,6,5,0) 100%)',
          }}
        />


        {/* ── The word, set over the field ────────────────────── */}
        <div className="pointer-events-none relative z-annotation flex min-h-[92vh] flex-col justify-between px-6 py-10 md:px-12 md:py-14">
          <div className="max-w-xl">
            <p className="t-label mb-5">
              Space laboratory · {summary ? `${summary.space_objects.total} objects` : 'loading'}
            </p>

            <h1 className="font-display text-display-md leading-[0.95] text-ink-50 md:text-display-lg">
              You are not reading
              <br />
              about space.
            </h1>

            <p className="mt-6 max-w-md text-base leading-relaxed text-ink-300">
              Move through the field. Every body here is drawn from its measured
              properties — colour, radius, albedo, ring geometry — and lit from wherever
              your cursor is. Approach one and it will tell you what it is.
            </p>

            <div className="pointer-events-auto mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={() => navigate('/rocket-lab')}>
                Build a rocket
              </Button>
              <Button size="lg" variant="outline" onClick={() => navigate('/explore')}>
                Explore the catalogue
              </Button>
              {!isAuthenticated && (
                <button
                  onClick={enterAsGuest}
                  className="h-11 px-3 text-sm text-ink-400 transition-colors hover:text-ink-100 focus-ring"
                >
                  Continue as guest →
                </button>
              )}
            </div>

            <p className="mt-4 font-mono text-tiny text-ink-600">
              No account needed. Signing in saves your designs and flights.
            </p>
          </div>

          {/* A hint that the field is interactive, retired once it has been. */}
          <div
            className={cn(
              'font-mono text-tiny text-ink-600 transition-opacity duration-drift',
              focused ? 'opacity-0' : 'opacity-100',
            )}
          >
            ← move the cursor across the field
          </div>
        </div>

        {/* ── Inspection ──────────────────────────────────────── */}
        <ObjectInspector object={active} loading={!!focused && !active} />

        {loadFailed && (
          <div className="absolute bottom-8 left-6 z-annotation plane px-3 py-2 md:left-12">
            <p className="text-tiny text-signal-caution">
              The catalogue could not be reached, so the field is empty. The rest of the
              product still works.
            </p>
          </div>
        )}
      </section>

      {/* ── The path ──────────────────────────────────────────── */}
      <Journey summary={summary} />

      {/* ── What it is honest about ───────────────────────────── */}
      <Honesty />
    </div>
  );
}

/**
 * The panel that opens when a body is approached.
 *
 * Anchored to the right edge rather than following the cursor: a panel that
 * chases the pointer is unreadable, and this one is meant to be read. The
 * numbers come from the catalogue record, and the photograph carries its
 * attribution because NASA imagery is public domain but not uncredited.
 */
function ObjectInspector({
  object,
  loading,
}: {
  object: CatalogObject | null;
  loading: boolean;
}) {
  const visible = !!object || loading;

  return (
    <aside
      className={cn(
        'pointer-events-none absolute right-0 top-1/2 z-annotation w-[22rem] -translate-y-1/2 pr-6 md:pr-12',
        'transition-[opacity,transform] duration-settle ease-orbital',
        visible ? 'translate-x-0 opacity-100' : 'translate-x-6 opacity-0',
      )}
      aria-live="polite"
    >
      {object && (
        <div className="pointer-events-auto plane-raised">
          {object.image && (
            <figure className="relative">
              <img
                src={object.image.url}
                alt={object.image.alt}
                loading="lazy"
                decoding="async"
                className="h-36 w-full object-cover"
              />
              <figcaption className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-ink-1000 to-transparent px-3 pb-1.5 pt-6">
                <span className="font-mono text-[0.6rem] text-ink-400">
                  {object.image.instrument
                    ? `${object.image.instrument} · ${object.image.credit}`
                    : object.image.credit}
                </span>
              </figcaption>
            </figure>
          )}

          <div className="space-y-3 p-4">
            <div>
              <p className="t-label">{object.classification}</p>
              <h2 className="font-display text-3xl leading-none text-ink-50">{object.name}</h2>
              {object.designation && object.designation !== object.name && (
                <p className="mt-1 font-mono text-tiny text-ink-500">{object.designation}</p>
              )}
            </div>

            <p className="text-xs leading-relaxed text-ink-300">{object.tagline}</p>

            <dl className="space-y-1.5 hairline-t pt-3">
              {[...object.physical, ...object.orbital].slice(0, 5).map((property) => (
                <div key={property.label} className="flex items-baseline justify-between gap-3">
                  <dt className="t-label truncate">{property.label}</dt>
                  <dd className="shrink-0 font-mono text-xs tabular-nums text-ink-100">
                    {formatProperty(property)}
                  </dd>
                </div>
              ))}
            </dl>

            <div className="flex items-center gap-3 hairline-t pt-3">
              <Link
                to={`/explore/${object.id}`}
                className="font-condensed text-micro uppercase tracking-instrument text-signal-flame transition-colors hover:text-signal-flame-bright"
              >
                Inspect {object.name} →
              </Link>
              {object.concept_slugs[0] && (
                <Link
                  to={`/learn/${object.concept_slugs[0]}`}
                  className="font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200"
                >
                  The science
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

/** Render one catalogue property the way its record says to. */
function formatProperty(property: {
  value?: number | null;
  unit?: string | null;
  display?: string | null;
  precision?: number | null;
}): string {
  if (property.display) return property.display;
  if (property.value === null || property.value === undefined) return '—';

  const value = property.value;
  const magnitude = Math.abs(value);
  let text: string;

  if (magnitude >= 1e6 || (magnitude > 0 && magnitude < 0.001)) {
    // Scientific notation, rendered the way a reference table would.
    const exponent = Math.floor(Math.log10(magnitude));
    const mantissa = value / 10 ** exponent;
    text = `${mantissa.toFixed(2)}×10${superscript(exponent)}`;
  } else if (magnitude >= 1000) {
    text = value.toLocaleString('en', { maximumFractionDigits: 0 });
  } else {
    text = value.toFixed(property.precision ?? (magnitude < 10 ? 2 : 1));
  }

  return property.unit ? `${text} ${property.unit}` : text;
}

const SUPERSCRIPTS = '⁰¹²³⁴⁵⁶⁷⁸⁹';
function superscript(n: number): string {
  const sign = n < 0 ? '⁻' : '';
  return (
    sign +
    Math.abs(n)
      .toString()
      .split('')
      .map((d) => SUPERSCRIPTS[Number(d)] ?? d)
      .join('')
  );
}

/**
 * The product loop, laid out as a path.
 *
 * A numbered sequence connected by a rule rather than five equal tiles,
 * because the steps are not equal or interchangeable — each one only makes
 * sense after the one before it.
 */
function Journey({ summary }: { summary: CatalogSummary | null }) {
  const steps = [
    {
      index: '01',
      title: 'Explore',
      to: '/explore',
      body:
        'Planets, moons, spacecraft and comets, with published bulk parameters and the ' +
        'source of every number attached.',
      count: summary ? `${summary.space_objects.total} objects` : null,
    },
    {
      index: '02',
      title: 'Understand',
      to: '/learn',
      body:
        'Orbital mechanics, propulsion, atmospheric flight — each with a figure you ' +
        'change and watch respond.',
      count: summary ? `${summary.science.total} topics · ${summary.science.interactive} interactive` : null,
    },
    {
      index: '03',
      title: 'Build',
      to: '/rocket-lab',
      body:
        'Assemble a vehicle from real components. It is drawn to scale as you go, and ' +
        'mass, thrust, Δv and stability update with every part.',
      count: '81 components',
    },
    {
      index: '04',
      title: 'Simulate',
      to: '/launch',
      body:
        'Pick a real launch site, pull the live weather, and fly it. RK4 integration, ' +
        'US Standard Atmosphere, staging, and the wind that is actually blowing there.',
      count: summary ? `${summary.launch_sites.total} launch sites` : null,
    },
    {
      index: '05',
      title: 'Evaluate',
      to: '/mission-control',
      body:
        'Watch the telemetry, read what failed and against which threshold, change one ' +
        'thing, and fly it again.',
      count: summary ? `${summary.experiments.total} experiments` : null,
    },
  ];

  return (
    <section className="relative mx-auto max-w-6xl px-6 py-24 md:px-12">
      <div className="mb-14 max-w-2xl">
        <p className="t-label mb-4">The loop</p>
        <h2 className="font-display text-display-sm leading-tight text-ink-50">
          One continuous path, not six disconnected tools
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-ink-400">
          What you learn feeds what you build; what you build gets flown; every flight
          gives you something to understand. You can join it anywhere.
        </p>
      </div>

      <ol className="relative">
        {/* The rule that makes it a path rather than a list. */}
        <span
          className="absolute left-[3.25rem] top-4 bottom-8 hidden w-px bg-[color:var(--rule)] md:block"
          aria-hidden="true"
        />

        {steps.map((step) => (
          <li key={step.index} className="relative">
            <Link
              to={step.to}
              className="group grid gap-4 py-6 hairline-b transition-colors md:grid-cols-[6.5rem_1fr_auto] md:items-baseline"
            >
              <div className="flex items-baseline gap-4">
                <span className="relative z-annotation font-mono text-xs text-ink-600">
                  {step.index}
                </span>
                <span
                  className="relative z-annotation -ml-1 h-1.5 w-1.5 rounded-full bg-ink-700 transition-colors group-hover:bg-signal-flame"
                  aria-hidden="true"
                />
              </div>

              <div className="max-w-2xl">
                <h3 className="font-display text-2xl leading-none text-ink-100 transition-colors group-hover:text-ink-50">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-400">{step.body}</p>
              </div>

              {step.count && (
                <span className="font-mono text-tiny text-ink-600 md:text-right">
                  {step.count}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * What the product is honest about.
 *
 * Kept because an educational simulator that does not state its approximations
 * is teaching something false about how engineering works.
 */
function Honesty() {
  const panels = [
    {
      label: 'Physics',
      title: 'Real, and honestly labelled',
      body:
        'RK4 integration, inverse-square gravity, the US Standard Atmosphere with a ' +
        'non-standard-day correction, transonic drag rise, staging, and mass flow from ' +
        'actual specific impulse. An educational simulation with documented ' +
        'approximations — never presented as flight-certified engineering.',
    },
    {
      label: 'Data',
      title: 'Sourced, not invented',
      body:
        'Bulk parameters come from NASA planetary fact sheets and JPL Solar System ' +
        'Dynamics, and every record carries its provenance. All 59 photographs were ' +
        'fetched and verified before being written down. The assistant answers from ' +
        'retrieved evidence and says so when it has none.',
    },
    {
      label: 'Weather',
      title: 'Live, and it changes the flight',
      body:
        'Conditions at your launch site are fetched from a real provider and fed ' +
        'straight into the physics: surface density shifts drag, and the wind profile ' +
        'drives angle of attack and lateral deviation. When no provider answers you get ' +
        'a standard day, labelled as one.',
    },
    {
      label: 'Failure',
      title: 'The lesson, not the error state',
      body:
        'A vehicle that cannot lift its own weight will not leave the pad, and you will ' +
        'be told exactly why, at which second, against which threshold, with the change ' +
        'that fixes it and what that change will cost you.',
    },
  ];

  return (
    <section className="hairline-t">
      <div className="mx-auto grid max-w-6xl gap-x-12 gap-y-10 px-6 py-20 md:grid-cols-2 md:px-12">
        {panels.map((panel) => (
          <div key={panel.label} className="rail">
            <p className="t-label mb-2">{panel.label}</p>
            <h3 className="font-display text-xl leading-tight text-ink-100">{panel.title}</h3>
            <p className="mt-2.5 text-sm leading-relaxed text-ink-400">{panel.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
