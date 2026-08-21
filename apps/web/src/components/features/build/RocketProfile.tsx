import { useMemo, useState } from 'react';
import {
  buildVehicleOutline,
  type FinSetShape,
  type RevolvedShape,
  type SurfaceKind,
  type VehicleOutline,
} from '@lostintospace/simulation-engine/geometry';
import type { DesignLayout } from '@lostintospace/simulation-engine/core/builder';

import { cn } from '@/lib/utils';

/**
 * The vehicle, drawn.
 *
 * A scale side elevation generated from the same geometry the physics flies —
 * every profile is the real generating curve, every position is the station the
 * stability model uses, and the whole thing regenerates whenever a component
 * changes. Add a body tube and it gets longer. Swap a conical nose for a von
 * Kármán and the silhouette changes and the centre of pressure moves with it.
 *
 * ## Why SVG rather than 3D here
 *
 * A builder needs a drawing, not a render. A side elevation with a dimension
 * rail and labelled stations is how an engineer reads a vehicle: it is
 * measurable, it prints, it is legible at any size, and it costs nothing to
 * redraw sixty times a second while a slider is being dragged. The 3D view
 * exists too, and is the right tool for flight — but it is the wrong tool for
 * answering "where exactly is my centre of gravity".
 */

/** How each surface class is filled and stroked. */
const SURFACE_STYLE: Record<SurfaceKind, { fill: string; stroke: string }> = {
  airframe: { fill: 'var(--surface-airframe)', stroke: 'var(--edge-airframe)' },
  nose: { fill: 'var(--surface-nose)', stroke: 'var(--edge-nose)' },
  nozzle: { fill: 'var(--surface-nozzle)', stroke: 'var(--edge-nozzle)' },
  tank: { fill: 'var(--surface-tank)', stroke: 'var(--edge-tank)' },
  fin: { fill: 'var(--surface-fin)', stroke: 'var(--edge-fin)' },
  structure: { fill: 'var(--surface-structure)', stroke: 'var(--edge-structure)' },
  payload: { fill: 'var(--surface-payload)', stroke: 'var(--edge-payload)' },
  recovery: { fill: 'var(--surface-recovery)', stroke: 'var(--edge-recovery)' },
  avionics: { fill: 'var(--surface-avionics)', stroke: 'var(--edge-avionics)' },
  separator: { fill: 'var(--surface-separator)', stroke: 'var(--edge-separator)' },
};

export interface RocketProfileProps {
  layout: DesignLayout;
  /** Centre of gravity station from the nose tip. Unit: m */
  cg_m?: number;
  /** Centre of pressure station from the nose tip. Unit: m */
  cp_m?: number;
  /** Reference diameter for the caliber annotation. Unit: m */
  referenceDiameter_m?: number;
  /** Highlight one component — the one selected in the picker. */
  selectedInstanceId?: string | null;
  onSelect?: (instanceId: string | null) => void;
  /** Draw internal structure that the skin would normally hide. */
  cutaway?: boolean;
  /** Draw the dimension rail and station callouts. */
  dimensioned?: boolean;
  className?: string;
}

export function RocketProfile({
  layout,
  cg_m,
  cp_m,
  referenceDiameter_m,
  selectedInstanceId,
  onSelect,
  cutaway = false,
  dimensioned = true,
  className,
}: RocketProfileProps) {
  const outline = useMemo(() => buildVehicleOutline(layout), [layout]);
  const [hovered, setHovered] = useState<string | null>(null);

  if (outline.totalLength_m <= 0 || outline.shapes.length === 0) {
    return (
      <div
        className={cn(
          'plate flex min-h-[280px] items-center justify-center px-8 text-center',
          className,
        )}
      >
        <p className="max-w-xs text-sm leading-relaxed text-ink-400">
          Nothing to draw yet. Add a stage, then an engine and a body tube, and the
          vehicle appears here at scale.
        </p>
      </div>
    );
  }

  // The drawing is done in metres and scaled by the SVG viewBox, so nothing in
  // here has to know about pixels.
  const length = outline.totalLength_m;
  const maxRadius = Math.max(outline.maxRadius_m, finReach(outline), length * 0.02);
  const marginX = length * 0.06;
  const marginY = maxRadius * 0.9;
  const viewWidth = length + marginX * 2;
  const viewHeight = maxRadius * 2 + marginY * 2;
  const axisY = viewHeight / 2;

  const strokeWidth = length * 0.0016;

  return (
    <div className={cn('plate relative overflow-hidden', className)}>
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="block h-full w-full"
        role="img"
        aria-label={`Scale side elevation. Overall length ${length.toFixed(2)} metres.`}
        style={
          {
            '--surface-airframe': '#2b2926',
            '--edge-airframe': '#6f6a60',
            '--surface-nose': '#3a3733',
            '--edge-nose': '#8a8478',
            '--surface-nozzle': '#332b26',
            '--edge-nozzle': '#a8623a',
            '--surface-tank': '#26302f',
            '--edge-tank': '#5f8a86',
            '--surface-fin': '#33302b',
            '--edge-fin': '#8e887c',
            '--surface-structure': '#242220',
            '--edge-structure': '#5a554d',
            '--surface-payload': '#2f2a33',
            '--edge-payload': '#8778a0',
            '--surface-recovery': '#33261f',
            '--edge-recovery': '#b06a45',
            '--surface-avionics': '#212b26',
            '--edge-avionics': '#5f8a6d',
            '--surface-separator': '#302322',
            '--edge-separator': '#a1564c',
          } as React.CSSProperties
        }
        onMouseLeave={() => setHovered(null)}
      >
        {/* Centreline. Every station on the vehicle is measured along it. */}
        <line
          x1={marginX - length * 0.03}
          y1={axisY}
          x2={marginX + length * 1.03}
          y2={axisY}
          stroke="#4a453c"
          strokeWidth={strokeWidth * 0.6}
          strokeDasharray={`${length * 0.012} ${length * 0.008}`}
        />

        <g transform={`translate(${marginX}, ${axisY})`}>
          {/* Fins go down first so the body reads as being in front of them. */}
          {outline.shapes
            .filter((s): s is FinSetShape => s.kind === 'fin_set')
            .map((fin) => (
              <FinSetGlyph
                key={fin.instanceId}
                fin={fin}
                strokeWidth={strokeWidth}
                active={fin.instanceId === selectedInstanceId || fin.instanceId === hovered}
                onEnter={() => setHovered(fin.instanceId)}
                onSelect={() => onSelect?.(fin.instanceId)}
              />
            ))}

          {outline.shapes
            .filter((s): s is RevolvedShape => s.kind === 'revolved')
            .filter((s) => cutaway || !isInternal(s))
            .map((shape) => (
              <RevolvedGlyph
                key={shape.instanceId}
                shape={shape}
                strokeWidth={strokeWidth}
                active={shape.instanceId === selectedInstanceId || shape.instanceId === hovered}
                onEnter={() => setHovered(shape.instanceId)}
                onSelect={() => onSelect?.(shape.instanceId)}
              />
            ))}

          {/* Stage boundaries: where the vehicle is designed to come apart. */}
          {outline.stageStations_m.slice(1).map((station, index) => (
            <g key={`stage-${index}`}>
              <line
                x1={station}
                y1={-maxRadius * 1.35}
                x2={station}
                y2={maxRadius * 1.35}
                stroke="#a1564c"
                strokeWidth={strokeWidth * 0.8}
                strokeDasharray={`${length * 0.006} ${length * 0.006}`}
              />
              <text
                x={station + length * 0.006}
                y={-maxRadius * 1.35 + length * 0.014}
                fill="#a1564c"
                fontSize={length * 0.016}
                fontFamily="'IBM Plex Sans Condensed', sans-serif"
                letterSpacing={length * 0.0012}
              >
                SEP
              </text>
            </g>
          ))}

          {/* The two points that decide whether it flies straight. */}
          {cp_m !== undefined && cp_m > 0 && (
            <StationMarker
              station={cp_m}
              radius={maxRadius}
              length={length}
              label="CP"
              colour="#7FA8B8"
              strokeWidth={strokeWidth}
            />
          )}
          {cg_m !== undefined && cg_m > 0 && (
            <StationMarker
              station={cg_m}
              radius={maxRadius}
              length={length}
              label="CG"
              colour="#E4682E"
              strokeWidth={strokeWidth}
              filled
            />
          )}

          {/* The static margin, drawn as the gap between them. */}
          {cg_m !== undefined && cp_m !== undefined && cp_m > cg_m && (
            <g>
              <line
                x1={cg_m}
                y1={maxRadius * 1.18}
                x2={cp_m}
                y2={maxRadius * 1.18}
                stroke="#8FB573"
                strokeWidth={strokeWidth * 1.4}
              />
              <text
                x={(cg_m + cp_m) / 2}
                y={maxRadius * 1.18 - length * 0.008}
                fill="#AFD292"
                fontSize={length * 0.016}
                textAnchor="middle"
                fontFamily="'IBM Plex Mono', monospace"
              >
                {referenceDiameter_m && referenceDiameter_m > 0
                  ? `${((cp_m - cg_m) / referenceDiameter_m).toFixed(2)} cal`
                  : `${(cp_m - cg_m).toFixed(2)} m`}
              </text>
            </g>
          )}

          {dimensioned && (
            <DimensionRail length={length} radius={maxRadius} strokeWidth={strokeWidth} />
          )}
        </g>
      </svg>

      {/* Hovering a part names it without a tooltip that follows the cursor. */}
      {hovered && (
        <div className="pointer-events-none absolute left-3 top-3 plane px-2 py-1">
          <span className="font-condensed text-micro uppercase tracking-instrument text-ink-300">
            {outline.shapes.find((s) => s.instanceId === hovered)?.name ?? ''}
          </span>
        </div>
      )}
    </div>
  );
}

/** Internal structure is hidden unless the cutaway is on. */
function isInternal(shape: RevolvedShape): boolean {
  return (
    shape.category === 'bulkhead' ||
    shape.category === 'centering_ring' ||
    shape.category === 'motor_mount' ||
    shape.category === 'avionics' ||
    shape.category === 'sensor' ||
    shape.category === 'battery' ||
    shape.category === 'parachute'
  );
}

/** Furthest a fin reaches from the axis, so the viewBox includes them. */
function finReach(outline: VehicleOutline): number {
  let reach = 0;
  for (const shape of outline.shapes) {
    if (shape.kind !== 'fin_set') continue;
    const span = shape.outline.reduce((max, p) => Math.max(max, p.y), 0);
    reach = Math.max(reach, shape.bodyRadius_m + span);
  }
  return reach;
}

/**
 * One body of revolution, drawn as its silhouette.
 *
 * The path traces the upper profile forward-to-aft, then the mirrored lower
 * profile back, which is exactly what lathing the same curve produces in 3D.
 */
function RevolvedGlyph({
  shape,
  strokeWidth,
  active,
  onEnter,
  onSelect,
}: {
  shape: RevolvedShape;
  strokeWidth: number;
  active: boolean;
  onEnter: () => void;
  onSelect: () => void;
}) {
  const style = SURFACE_STYLE[shape.surface];
  const { stations, radii } = shape.profile;

  const upper = stations.map((s, i) => `${shape.station_m + s},${-(radii[i] ?? 0)}`);
  const lower = [...stations]
    .map((s, i) => ({ s, r: radii[i] ?? 0 }))
    .reverse()
    .map(({ s, r }) => `${shape.station_m + s},${r}`);

  const path = `M ${upper.join(' L ')} L ${lower.join(' L ')} Z`;

  return (
    <path
      d={path}
      fill={style.fill}
      stroke={active ? '#F4F0E8' : style.stroke}
      strokeWidth={active ? strokeWidth * 2.2 : strokeWidth}
      strokeLinejoin="round"
      className="cursor-pointer transition-[stroke,stroke-width] duration-quick ease-instrument"
      onMouseEnter={onEnter}
      onClick={onSelect}
    >
      <title>{`${shape.name} — ${shape.mass_kg.toFixed(1)} kg`}</title>
    </path>
  );
}

/**
 * A fin set, drawn in elevation.
 *
 * A side view can only honestly show the two blades edge-on to the viewer, so
 * the set is drawn as one blade up and one down, with the remaining blades
 * indicated by a lighter foreshortened outline. Drawing all of them at full
 * size would imply a vehicle with far more fin area than it has.
 */
function FinSetGlyph({
  fin,
  strokeWidth,
  active,
  onEnter,
  onSelect,
}: {
  fin: FinSetShape;
  strokeWidth: number;
  active: boolean;
  onEnter: () => void;
  onSelect: () => void;
}) {
  const style = SURFACE_STYLE.fin;

  const blade = (sign: 1 | -1, foreshorten: number) => {
    const points = fin.outline
      .map((p) => {
        const x = fin.station_m + p.x;
        const y = sign * (fin.bodyRadius_m + p.y * foreshorten);
        return `${x},${y}`;
      })
      .join(' L ');
    return `M ${points} Z`;
  };

  // How many blades are visible edge-on versus foreshortened depends on the
  // count: a three-fin set shows one up and two angled, a four-fin set shows
  // one up, one down and two edge-on.
  const count = fin.angles_rad.length;
  const foreshortened = count > 2 ? Math.abs(Math.cos(Math.PI / count)) : 0;

  return (
    <g
      className="cursor-pointer"
      onMouseEnter={onEnter}
      onClick={onSelect}
      stroke={active ? '#F4F0E8' : style.stroke}
      strokeWidth={active ? strokeWidth * 2 : strokeWidth}
      strokeLinejoin="round"
    >
      <title>{`${fin.name} — ${count} blades, ${fin.mass_kg.toFixed(1)} kg`}</title>
      {foreshortened > 0.02 && (
        <>
          <path d={blade(1, foreshortened)} fill={style.fill} opacity={0.45} />
          <path d={blade(-1, foreshortened)} fill={style.fill} opacity={0.45} />
        </>
      )}
      <path d={blade(1, 1)} fill={style.fill} />
      <path d={blade(-1, 1)} fill={style.fill} />
      {fin.isLattice && <FinLattice fin={fin} strokeWidth={strokeWidth} />}
    </g>
  );
}

/** Grid fins are a lattice, and drawing them solid misrepresents their drag. */
function FinLattice({ fin, strokeWidth }: { fin: FinSetShape; strokeWidth: number }) {
  const span = fin.outline.reduce((max, p) => Math.max(max, p.y), 0);
  const chord = fin.outline.reduce((max, p) => Math.max(max, p.x), 0);
  const cells = 5;
  const lines: JSX.Element[] = [];

  for (let i = 1; i < cells; i += 1) {
    const t = i / cells;
    for (const sign of [1, -1] as const) {
      lines.push(
        <line
          key={`h${i}${sign}`}
          x1={fin.station_m}
          y1={sign * (fin.bodyRadius_m + span * t)}
          x2={fin.station_m + chord}
          y2={sign * (fin.bodyRadius_m + span * t)}
          strokeWidth={strokeWidth * 0.5}
        />,
        <line
          key={`v${i}${sign}`}
          x1={fin.station_m + chord * t}
          y1={sign * fin.bodyRadius_m}
          x2={fin.station_m + chord * t}
          y2={sign * (fin.bodyRadius_m + span)}
          strokeWidth={strokeWidth * 0.5}
        />,
      );
    }
  }
  return <g opacity={0.55}>{lines}</g>;
}

/** A labelled vertical marker at one station. */
function StationMarker({
  station,
  radius,
  length,
  label,
  colour,
  strokeWidth,
  filled = false,
}: {
  station: number;
  radius: number;
  length: number;
  label: string;
  colour: string;
  strokeWidth: number;
  filled?: boolean;
}) {
  const size = length * 0.011;
  return (
    <g>
      <line
        x1={station}
        y1={-radius * 1.1}
        x2={station}
        y2={radius * 1.1}
        stroke={colour}
        strokeWidth={strokeWidth * 1.1}
        opacity={0.7}
      />
      <circle
        cx={station}
        cy={0}
        r={size}
        fill={filled ? colour : 'none'}
        stroke={colour}
        strokeWidth={strokeWidth * 1.6}
      />
      <text
        x={station}
        y={-radius * 1.1 - length * 0.008}
        fill={colour}
        fontSize={length * 0.018}
        textAnchor="middle"
        fontFamily="'IBM Plex Sans Condensed', sans-serif"
        letterSpacing={length * 0.001}
      >
        {label}
      </text>
    </g>
  );
}

/** The dimension rail beneath the vehicle: overall length and station ticks. */
function DimensionRail({
  length,
  radius,
  strokeWidth,
}: {
  length: number;
  radius: number;
  strokeWidth: number;
}) {
  const y = radius * 1.55;
  // A tick interval that lands on a round number of metres at any vehicle size.
  const rawStep = length / 8;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rawStep) ?? magnitude;

  const ticks: number[] = [];
  for (let s = 0; s <= length + 1e-9; s += step) ticks.push(s);

  return (
    <g stroke="#5a554d" fill="#847D6F">
      <line x1={0} y1={y} x2={length} y2={y} strokeWidth={strokeWidth} />
      {ticks.map((s) => (
        <g key={s}>
          <line x1={s} y1={y - length * 0.006} x2={s} y2={y + length * 0.006} strokeWidth={strokeWidth} />
          <text
            x={s}
            y={y + length * 0.026}
            fontSize={length * 0.015}
            textAnchor="middle"
            stroke="none"
            fontFamily="'IBM Plex Mono', monospace"
          >
            {s.toFixed(step < 1 ? 1 : 0)}
          </text>
        </g>
      ))}
      <text
        x={length / 2}
        y={y + length * 0.052}
        fontSize={length * 0.017}
        textAnchor="middle"
        stroke="none"
        fill="#A9A296"
        fontFamily="'IBM Plex Mono', monospace"
      >
        {length.toFixed(2)} m overall
      </text>
    </g>
  );
}
