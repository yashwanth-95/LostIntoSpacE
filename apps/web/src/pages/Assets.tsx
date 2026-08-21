import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Acquiring, Badge, ErrorPanel, Input, Modal, SectionRule } from '@/components/ui';
import { catalog, type AssetRecord } from '@/services/api';
import { useDebounce } from '@/hooks/useDebounce';
import { cn } from '@/lib/utils';

/**
 * The asset library.
 *
 * Every image the platform can show, with what it depicts, who took it, what
 * licence it carries and which parts of the product reference it. That last
 * field is why this is a catalog rather than a folder.
 *
 * The grid is deliberately irregular. A uniform grid of identical tiles is the
 * house style of every stock-photo site, and these are scientific records with
 * genuinely different shapes and importance.
 */
export default function Assets() {
  const [assets, setAssets] = useState<AssetRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<string | null>(null);
  const [selected, setSelected] = useState<AssetRecord | null>(null);
  const debounced = useDebounce(query, 200);

  useEffect(() => {
    catalog
      .assets()
      .then(setAssets)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'The asset library could not be loaded.'),
      );
  }, []);

  const kinds = useMemo(
    () => [...new Set((assets ?? []).map((a) => a.kind))],
    [assets],
  );

  const visible = useMemo(() => {
    if (!assets) return [];
    const needle = debounced.trim().toLowerCase();
    return assets.filter((asset) => {
      if (kind && asset.kind !== kind) return false;
      if (!needle) return true;
      return (
        asset.title.toLowerCase().includes(needle) ||
        asset.description.toLowerCase().includes(needle) ||
        asset.tags.some((tag) => tag.includes(needle))
      );
    });
  }, [assets, debounced, kind]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel message={error} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1500px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-6 hairline-b pb-5">
        <div>
          <p className="t-label mb-1">Explore · Assets</p>
          <h1 className="font-display text-display-sm leading-none text-ink-50">
            The image library
          </h1>
          <p className="mt-3 max-w-[38rem] text-sm leading-relaxed text-ink-400">
            Every photograph in this platform, with its provenance. All of it is NASA public
            domain, all of it was verified to resolve before it was catalogued, and all of it
            carries hand-written alternative text.
          </p>
        </div>
        <div className="w-full max-w-xs">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search titles, tags, subjects"
          />
        </div>
      </header>

      <div className="mb-6 flex flex-wrap gap-1">
        <FilterChip active={kind === null} onClick={() => setKind(null)}>
          All ({assets?.length ?? 0})
        </FilterChip>
        {kinds.map((option) => (
          <FilterChip key={option} active={kind === option} onClick={() => setKind(option)}>
            {option.replace(/_/g, ' ')}
          </FilterChip>
        ))}
      </div>

      {!assets ? (
        <Acquiring rows={10} />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {visible.map((asset, index) => (
            <button
              key={asset.id}
              onClick={() => setSelected(asset)}
              className={cn(
                'group relative overflow-hidden bg-ink-900 text-left focus-ring',
                // Every seventh tile runs double-width, so the field reads as a
                // curated wall rather than as a spreadsheet of thumbnails.
                index % 7 === 0 && 'sm:col-span-2 sm:row-span-2',
              )}
            >
              <img
                src={asset.thumbnail_url ?? asset.url}
                alt={asset.alt}
                loading="lazy"
                decoding="async"
                className={cn(
                  'w-full object-cover transition-transform duration-drift ease-orbital',
                  'group-hover:scale-[1.03]',
                  index % 7 === 0 ? 'aspect-square' : 'aspect-[4/3]',
                )}
              />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-ink-1000 via-ink-1000/70 to-transparent p-2.5 pt-8">
                <span className="block truncate font-condensed text-tiny uppercase tracking-label text-ink-100">
                  {asset.title}
                </span>
                <span className="block truncate font-mono text-[0.6rem] text-ink-500">
                  {asset.credit}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}

      {visible.length === 0 && assets && (
        <p className="py-16 text-center text-sm text-ink-500">
          Nothing matches that. Try a broader term.
        </p>
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.title}
        size="xl"
      >
        {selected && (
          <div className="space-y-4">
            <img
              src={selected.url}
              alt={selected.alt}
              className="max-h-[60vh] w-full object-contain"
            />

            <p className="text-sm leading-relaxed text-ink-200">{selected.description}</p>

            <SectionRule label="Provenance" />
            <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
              <Field label="Credit" value={selected.credit} />
              <Field label="NASA id" value={selected.nasa_id ?? '—'} mono />
              <Field label="Date" value={selected.date ?? '—'} mono />
              <Field label="Category" value={selected.kind.replace(/_/g, ' ')} />
            </dl>

            <div>
              <p className="t-label mb-1.5">Licence</p>
              <p className="text-tiny leading-relaxed text-ink-400">{selected.license}</p>
            </div>

            <div>
              <p className="t-label mb-1.5">Alternative text</p>
              <p className="text-tiny italic leading-relaxed text-ink-400">{selected.alt}</p>
            </div>

            {selected.subject_ids.length > 0 && (
              <div>
                <p className="t-label mb-1.5">Depicts</p>
                <div className="flex flex-wrap gap-1.5">
                  {selected.subject_ids.map((id) => (
                    <Link key={id} to={`/explore/${id}`} onClick={() => setSelected(null)}>
                      <Badge variant="flame">{id.replace(/-/g, ' ')}</Badge>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="t-label mb-1.5">Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {selected.tags.map((tag) => (
                  <Badge key={tag} variant="outline">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-instrument border px-2.5 py-1 font-condensed text-micro uppercase tracking-label',
        'transition-colors duration-quick focus-ring',
        active
          ? 'border-signal-flame/40 bg-signal-flame/10 text-signal-flame-bright'
          : 'border-ink-700 bg-ink-850 text-ink-500 hover:text-ink-200',
      )}
    >
      {children}
    </button>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="t-label">{label}</dt>
      <dd className={cn('mt-0.5 text-xs text-ink-200', mono && 'font-mono')}>{value}</dd>
    </div>
  );
}
