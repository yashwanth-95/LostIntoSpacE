import { useId } from 'react';
import { cn } from '@/lib/utils';

/**
 * A body, drawn from its own measured appearance.
 *
 * SVG rather than canvas: this renders once and never animates, and an SVG disc
 * stays sharp at any zoom while costing no JavaScript per frame.
 *
 * Everything here comes from the catalog's `appearance` record — the base
 * colour, the albedo, the band palette, the ring geometry, the axial tilt. None
 * of it is decorative: Mars is iron oxide because Mars *is* iron oxide, and
 * Enceladus is near-white because its geometric albedo is 1.375. That is why
 * the same colours mean the same things in the object field, the browse grid
 * and the legend.
 *
 * One light source, warm, from the upper left, matching the illumination model
 * the rest of the interface uses.
 */

export interface BodyAppearance {
  base_color: string;
  accent_color?: string | null;
  band_colors: string[];
  radius_km: number;
  texture: string;
  albedo: number;
  atmosphere_color?: string | null;
  atmosphere_strength: number;
  emissive: boolean;
  ring?: {
    inner_radius_ratio: number;
    outer_radius_ratio: number;
    color: string;
    opacity: number;
    tilt_deg: number;
    gaps: number[];
  } | null;
  axial_tilt_deg: number;
}

export function BodyDisc({
  appearance,
  size = 96,
  className,
  title,
}: {
  appearance: BodyAppearance;
  size?: number;
  className?: string;
  title?: string;
}) {
  const uid = useId().replace(/:/g, '');
  const ring = appearance.ring;

  // The ring extends past the body, so the viewBox has to grow to fit it or the
  // outer edge is clipped.
  const reach = ring ? Math.max(1, ring.outer_radius_ratio) : 1;
  const halo = appearance.emissive ? 1.9 : appearance.atmosphere_strength > 0 ? 1.12 : 1.02;
  const extent = Math.max(reach, halo);
  const box = 100 * extent;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`${-box} ${-box} ${box * 2} ${box * 2}`}
      className={cn('block overflow-visible', className)}
      role={title ? 'img' : 'presentation'}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        {/* Lit limb. Albedo drives how bright the sunward side reads. */}
        <radialGradient id={`lit-${uid}`} cx="32%" cy="28%" r="78%">
          <stop
            offset="0%"
            stopColor={appearance.accent_color ?? appearance.base_color}
            stopOpacity={0.35 + appearance.albedo * 0.55}
          />
          <stop offset="55%" stopColor={appearance.base_color} stopOpacity="1" />
          <stop offset="100%" stopColor="#000000" stopOpacity={appearance.emissive ? 0 : 0.55} />
        </radialGradient>

        {appearance.emissive && (
          <radialGradient id={`corona-${uid}`} cx="50%" cy="50%" r="50%">
            <stop offset="52%" stopColor={appearance.base_color} stopOpacity="0.55" />
            <stop offset="72%" stopColor={appearance.accent_color ?? appearance.base_color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={appearance.base_color} stopOpacity="0" />
          </radialGradient>
        )}

        {appearance.atmosphere_strength > 0 && !appearance.emissive && (
          <radialGradient id={`air-${uid}`} cx="50%" cy="50%" r="50%">
            <stop offset="86%" stopColor={appearance.atmosphere_color ?? '#7FA8B8'} stopOpacity="0" />
            <stop
              offset="97%"
              stopColor={appearance.atmosphere_color ?? '#7FA8B8'}
              stopOpacity={0.16 + appearance.atmosphere_strength * 0.42}
            />
            <stop offset="100%" stopColor={appearance.atmosphere_color ?? '#7FA8B8'} stopOpacity="0" />
          </radialGradient>
        )}

        {/* Latitudinal bands, clipped to the disc. */}
        <clipPath id={`disc-${uid}`}>
          <circle cx="0" cy="0" r="100" />
        </clipPath>
      </defs>

      {appearance.emissive && <circle cx="0" cy="0" r={100 * 1.9} fill={`url(#corona-${uid})`} />}

      {/* The far half of the ring, drawn behind the body. */}
      {ring && <RingArc ring={ring} uid={uid} half="back" />}

      <g transform={`rotate(${-appearance.axial_tilt_deg * 0.35})`}>
        <circle cx="0" cy="0" r="100" fill={appearance.base_color} />

        {appearance.band_colors.length > 0 && (
          <g clipPath={`url(#disc-${uid})`} opacity="0.85">
            {appearance.band_colors.map((colour, index) => {
              const count = appearance.band_colors.length;
              const top = -100 + (index / count) * 200;
              const height = 200 / count;
              return (
                <rect
                  key={index}
                  x={-100}
                  y={top}
                  width={200}
                  height={height + 0.5}
                  fill={colour}
                />
              );
            })}
          </g>
        )}

        {/* Surface character: pits for cratered bodies, mottling for volcanic. */}
        {(appearance.texture === 'cratered' || appearance.texture === 'volcanic') && (
          <g clipPath={`url(#disc-${uid})`} opacity={appearance.texture === 'volcanic' ? 0.5 : 0.28}>
            {CRATERS.map(([cx, cy, r], index) => (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={r}
                fill={
                  appearance.texture === 'volcanic'
                    ? (appearance.accent_color ?? '#E8543A')
                    : '#000000'
                }
              />
            ))}
          </g>
        )}

        {/* Irregular bodies are not round — flatten and notch them. */}
        {appearance.texture === 'irregular' && (
          <circle cx="0" cy="0" r="100" fill={appearance.base_color} transform="scale(1.18 0.74)" />
        )}

        <circle cx="0" cy="0" r="100" fill={`url(#lit-${uid})`} />
      </g>

      {appearance.atmosphere_strength > 0 && !appearance.emissive && (
        <circle cx="0" cy="0" r={100 * 1.12} fill={`url(#air-${uid})`} />
      )}

      {/* The near half of the ring, in front. */}
      {ring && <RingArc ring={ring} uid={uid} half="front" />}
    </svg>
  );
}

/**
 * Half a ring system.
 *
 * Drawn as two halves so the body sits between them, which is what makes a ring
 * read as encircling rather than as a stripe painted on top. Ellipse height
 * comes from the tilt: an edge-on ring is a line, a face-on one is a circle.
 */
function RingArc({
  ring,
  uid,
  half,
}: {
  ring: NonNullable<BodyAppearance['ring']>;
  uid: string;
  half: 'front' | 'back';
}) {
  const inner = ring.inner_radius_ratio * 100;
  const outer = ring.outer_radius_ratio * 100;
  // Tilt of 0° would be face-on; the catalog's values are the body's axial
  // tilt, so the cosine gives a plausible foreshortening.
  const squash = Math.max(0.08, Math.abs(Math.cos((ring.tilt_deg * Math.PI) / 180)) * 0.55 + 0.12);
  const clip = half === 'front' ? `front-${uid}` : `back-${uid}`;

  return (
    <>
      <defs>
        <clipPath id={clip}>
          <rect x={-outer} y={half === 'front' ? 0 : -outer} width={outer * 2} height={outer} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clip})`} opacity={ring.opacity}>
        <ellipse
          cx="0"
          cy="0"
          rx={(inner + outer) / 2}
          ry={((inner + outer) / 2) * squash}
          fill="none"
          stroke={ring.color}
          strokeWidth={outer - inner}
        />
        {ring.gaps.map((gap) => (
          <ellipse
            key={gap}
            cx="0"
            cy="0"
            rx={gap * 100}
            ry={gap * 100 * squash}
            fill="none"
            stroke="#000000"
            strokeOpacity="0.55"
            strokeWidth={4}
          />
        ))}
      </g>
    </>
  );
}

/**
 * Fixed crater positions.
 *
 * Deliberately not random: a body must look the same every render, or it
 * appears to change between the browse grid and the detail page and reads as a
 * rendering fault rather than as the same object.
 */
const CRATERS: readonly [number, number, number][] = [
  [-38, -30, 17],
  [22, -52, 11],
  [54, 12, 20],
  [-16, 38, 14],
  [-62, 20, 9],
  [8, 8, 8],
  [36, 56, 12],
  [-44, 66, 7],
  [70, -34, 8],
  [-72, -8, 6],
];
