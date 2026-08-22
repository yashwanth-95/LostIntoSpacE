import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { BodyDisc } from '@/components/features/explore/BodyDisc';
import { Acquiring, Badge, EmptyState, ErrorPanel, Input, SectionRule } from '@/components/ui';
import { useDebounce } from '@/hooks/useDebounce';
import { catalog, type CatalogObject } from '@/services/api';

/**
 * The object explorer.
 *
 * Backed by the catalog rather than by search: 38 objects with published bulk
 * parameters, real photography where one exists, and measured appearance data
 * where one does not. The previous version queried a `space_objects` table
 * nothing had ever seeded, so this page reliably showed nothing at all.
 *
 * ## Grouped by what a thing *is*
 *
 * Not one flat grid. The Sun, the planets, the moons, the small bodies and the
 * spacecraft are different kinds of object with different properties worth
 * reading, and a grid that mixes Jupiter with a 490-metre asteroid implies a
 * comparison that is not meaningful. Each group is a band, ordered outward from
 * the Sun where that ordering exists.
 *
 * ## Bodies are drawn, not photographed
 *
 * In the browse view every object is rendered from its own measured colour,
 * albedo and texture class. That is deliberate rather than a shortfall: a drawn
 * disc reads clearly at 64 px where a photograph becomes a grey smudge, it
 * costs no bandwidth, and it is consistent — a photograph of Titan and a
 * photograph of Enceladus were taken under wildly different illumination, and
 * side by side that reads as a fact about the moons rather than about the
 * cameras. The photographs appear on the detail page, at a size that earns them.
 */

/** The kind bands, in the order the page presents them. */
const KIND_ORDER: readonly { id: string; label: string; blurb: string }[] = [
  { id: 'star', label: 'The star', blurb: '99.86% of the mass of the solar system.' },
  {
    id: 'planet',
    label: 'Planets',
    blurb: 'Ordered outward from the Sun. Every distance here is to scale in the numbers, never in the picture.',
  },
  {
    id: 'dwarf_planet',
    label: 'Dwarf planets',
    blurb: 'Round under their own gravity, but sharing their orbit with a crowd.',
  },
  { id: 'moon', label: 'Moons', blurb: 'Several are larger than Mercury. Two have oceans.' },
  {
    id: 'asteroid',
    label: 'Asteroids',
    blurb: 'Rubble piles and metal cores. Escape velocity measured in centimetres per second.',
  },
  { id: 'comet', label: 'Comets', blurb: 'Ice that grows a tail when the Sun reaches it.' },
  {
    id: 'spacecraft',
    label: 'Spacecraft',
    blurb: 'Built objects, still flying. Two have left the solar system.',
  },
  { id: 'telescope', label: 'Observatories', blurb: 'Instruments that see what eyes cannot.' },
  { id: 'station', label: 'Stations', blurb: 'Crewed, and falling continuously.' },
];

export default function Explore() {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);
  const [objects, setObjects] = useState<CatalogObject[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    catalog
      .objects(debounced.trim() ? { q: debounced.trim() } : {})
      .then((data) => {
        if (!cancelled) setObjects(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The catalog could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const groups = useMemo(() => {
    if (!objects) return [];
    return KIND_ORDER.map((kind) => ({
      ...kind,
      items: objects.filter((object) => object.kind === kind.id),
    })).filter((group) => group.items.length > 0);
  }, [objects]);

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-6 hairline-b pb-5">
        <div>
          <p className="t-label mb-1">Explore</p>
          <h1 className="font-display text-display-sm leading-none text-ink-50">
            The catalog
          </h1>
          <p className="mt-3 max-w-[42rem] text-sm leading-relaxed text-ink-400">
            Thirty-eight objects, with published bulk parameters and the source of every
            number attached. Each body is drawn from its own measured colour and albedo —
            the photographs are on the detail pages, where they are big enough to be worth
            looking at.
          </p>
        </div>

        <div className="w-full max-w-xs">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search objects…"
            aria-label="Search the catalog"
          />
          {objects && (
            <p className="mt-1.5 font-mono text-micro text-ink-600">
              {objects.length} object{objects.length === 1 ? '' : 's'}
              {debounced.trim() ? ` matching “${debounced.trim()}”` : ''}
            </p>
          )}
        </div>
      </header>

      {error && <ErrorPanel message={error} className="mb-6" />}

      {!objects && !error && <Acquiring rows={10} />}

      {objects && objects.length === 0 && (
        <EmptyState
          title="Nothing matches that"
          description={`No object in the catalog matches “${debounced.trim()}”. Try a body, a mission, or a property like “ocean” or “volcanic”.`}
        />
      )}

      <div className="space-y-12">
        {groups.map((group) => (
          <section key={group.id}>
            <SectionRule
              label={group.label}
              aside={
                <span className="font-mono text-micro text-ink-600">{group.items.length}</span>
              }
            />
            <p className="-mt-2 mb-5 max-w-[40rem] text-tiny leading-relaxed text-ink-500">
              {group.blurb}
            </p>

            <ul className="grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {group.items.map((object) => (
                <li key={object.id}>
                  <ObjectTile object={object} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

/**
 * One object in the browse grid.
 *
 * The disc is sized by the *logarithm* of the real radius, not linearly. Linear
 * scaling within a band puts Ganymede at 2,634 km beside Enceladus at 252 km and
 * makes the second one four pixels across; the log keeps both legible while
 * still showing that one is much larger. It is a distortion, so the real radius
 * is printed underneath rather than left to be read off the picture.
 */
function ObjectTile({ object }: { object: CatalogObject }) {
  const headline = object.physical[0] ?? object.orbital[0];

  return (
    <Link
      to={`/explore/${object.id}`}
      className="group block focus-ring"
      aria-label={`${object.name} — ${object.classification}`}
    >
      <div className="relative mb-3 flex aspect-square items-center justify-center">
        <BodyDisc
          appearance={object.appearance}
          size={sizeFor(object)}
          className="transition-transform duration-settle ease-magnetic group-hover:scale-[1.06]"
        />
      </div>

      <h3 className="font-display text-lg leading-tight text-ink-100 transition-colors group-hover:text-ink-50">
        {object.name}
      </h3>
      <p className="mt-0.5 truncate font-condensed text-micro uppercase tracking-label text-ink-500">
        {object.classification}
      </p>

      {headline && (
        <p className="mt-1.5 font-mono text-[0.65rem] tabular-nums text-ink-400">
          {headline.label}{' '}
          <span className="text-ink-200">
            {headline.display ?? formatValue(headline.value, headline.unit)}
          </span>
        </p>
      )}

      {object.image && (
        <Badge variant="outline" className="mt-2">
          photographed
        </Badge>
      )}
    </Link>
  );
}

/**
 * Tile diameter for an object, in pixels.
 *
 * Logarithmic in the real radius and clamped, so a 700,000 km star and a
 * 250-metre asteroid can both appear in the same page without one of them being
 * invisible.
 */
function sizeFor(object: CatalogObject): number {
  const radius = Math.max(object.appearance.radius_km, 0.001);
  const t = (Math.log10(radius) + 3) / (Math.log10(700_000) + 3);
  return Math.round(44 + Math.max(0, Math.min(1, t)) * 76);
}

function formatValue(value?: number | null, unit?: string | null): string {
  if (value === null || value === undefined) return '—';
  const magnitude = Math.abs(value);
  const text =
    magnitude >= 1e6
      ? value.toExponential(2)
      : magnitude >= 1000
        ? value.toLocaleString('en', { maximumFractionDigits: 0 })
        : magnitude >= 10
          ? value.toFixed(1)
          : value.toFixed(2);
  return unit ? `${text} ${unit}` : text;
}
