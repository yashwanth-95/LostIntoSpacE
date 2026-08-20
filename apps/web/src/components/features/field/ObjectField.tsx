import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { drawBody, seedFor, type Appearance } from './drawBody';
import { cn } from '@/lib/utils';

/**
 * The object field.
 *
 * A curated arrangement of real bodies drawn from catalogue data, responding to
 * the cursor as a physical space would rather than as a grid of hover targets.
 *
 * ## What the cursor actually does
 *
 * Four things, none of them a scale-on-hover:
 *
 * 1. **It is the light.** The pointer is the light source, so moving it sweeps
 *    the terminator across every body in the field. This is the effect that
 *    makes the arrangement read as a space with depth rather than as a picture,
 *    and it is honest — a body's lit fraction genuinely depends on where the
 *    light is.
 * 2. **Parallax by depth.** Each object carries a depth from the catalogue.
 *    Near objects track the pointer strongly, far ones barely move. That is the
 *    same cue your eyes use to order things in a real scene.
 * 3. **Magnetic approach.** An object within reach drifts slightly toward the
 *    pointer and grows — a few percent, not a pop. Its orbital path fades in,
 *    and the objects it is related to brighten with it, because the
 *    relationships between these bodies are the actual subject.
 * 4. **Focus.** Attention concentrates: the approached body sharpens and the
 *    rest recede in presence. Nothing blinks, nothing pulses.
 *
 * All of it runs on one canvas at device resolution, animated with a spring
 * toward a target rather than by tweening on a timer, so an interrupted gesture
 * settles instead of finishing an animation nobody is watching any more.
 *
 * Everything here is decorative in the sense that it moves — and *only* in that
 * sense. Every position, colour, size and label comes from the catalogue.
 */

export interface FieldObject {
  id: string;
  name: string;
  kind: string;
  classification: string;
  tagline: string;
  appearance: Appearance;
  /** Placement as a fraction of the field. */
  x: number;
  y: number;
  /** 0 far, 1 near. Drives size, parallax and presence. */
  depth: number;
  headline: { label: string; value?: number | null; unit?: string | null; display?: string | null }[];
  image?: { url: string; alt: string; credit: string; title: string } | null;
}

interface Placed {
  object: FieldObject;
  /** Current screen position, in CSS pixels. */
  x: number;
  y: number;
  /** Base radius before focus scaling, in CSS pixels. */
  radius: number;
  /** Eased focus, 0–1. */
  focus: number;
  /** Eased offset from the magnetic pull. */
  pullX: number;
  pullY: number;
}

export interface ObjectFieldProps {
  objects: readonly FieldObject[];
  /** Called when the pointer settles on an object, or leaves the field. */
  onFocus?: (object: FieldObject | null) => void;
  onSelect?: (object: FieldObject) => void;
  /** Related ids to hold lit alongside the focused object. */
  relatedIds?: readonly string[];
  className?: string;
}

/** How far from a body's edge the pointer starts to affect it, in pixels. */
const REACH_PX = 90;

/** How far a body can be pulled toward the pointer, as a fraction of its radius. */
const MAX_PULL = 0.22;

export function ObjectField({
  objects,
  onFocus,
  onSelect,
  relatedIds = [],
  className,
}: ObjectFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pointer = useRef({ x: 0.5, y: 0.35, inside: false });
  const placed = useRef<Placed[]>([]);
  const frame = useRef(0);
  const [focused, setFocused] = useState<FieldObject | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  const related = useMemo(() => new Set(relatedIds), [relatedIds]);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(query.matches);
    const listen = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    query.addEventListener('change', listen);
    return () => query.removeEventListener('change', listen);
  }, []);

  /**
   * Body radius on screen.
   *
   * *Not* to scale — the Sun is 5,700 times Ceres's radius and drawing that
   * honestly would leave every rocky body sub-pixel. The compression is a
   * fourth root, which preserves the ordering and the sense that Jupiter
   * dwarfs Mars while keeping everything visible. Depth then scales it again,
   * because a nearer object is bigger.
   */
  const radiusFor = useCallback((object: FieldObject, shortSide: number) => {
    const km = Math.max(object.appearance.radius_km, 0.5);
    const compressed = Math.pow(km, 0.25);
    const scale = shortSide / 150;
    return Math.max(6, compressed * scale * (0.55 + object.depth * 0.85));
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = 1;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      const shortSide = Math.min(width, height);
      placed.current = objects.map((object) => {
        const existing = placed.current.find((p) => p.object.id === object.id);
        return {
          object,
          x: object.x * width,
          y: object.y * height,
          radius: radiusFor(object, shortSide),
          focus: existing?.focus ?? 0,
          pullX: existing?.pullX ?? 0,
          pullY: existing?.pullY ?? 0,
        };
      });
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    let lastFocusId: string | null = null;

    const render = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const px = pointer.current.x * width;
      const py = pointer.current.y * height;

      // Depth ordering: far bodies first, so near ones occlude them.
      const ordered = [...placed.current].sort((a, b) => a.object.depth - b.object.depth);

      let nearest: Placed | null = null;
      let nearestDistance = Number.POSITIVE_INFINITY;

      for (const item of ordered) {
        // Parallax. A far object barely responds; a near one tracks strongly.
        // The pointer offset is measured from the field centre so the scene
        // shifts as a whole rather than everything sliding toward the cursor.
        const parallax = reducedMotion ? 0 : (item.object.depth - 0.5) * 2;
        const offsetX = (pointer.current.x - 0.5) * parallax * 34;
        const offsetY = (pointer.current.y - 0.5) * parallax * 22;

        const baseX = item.object.x * width + offsetX;
        const baseY = item.object.y * height + offsetY;

        const distance = Math.hypot(px - baseX, py - baseY) - item.radius;
        const target = pointer.current.inside
          ? Math.max(0, 1 - Math.max(distance, 0) / REACH_PX)
          : 0;

        // Ease toward the target rather than tween on a timer, so an
        // interrupted gesture settles instead of playing out.
        item.focus += (target - item.focus) * (reducedMotion ? 1 : 0.14);

        const pullStrength = item.focus * MAX_PULL;
        const targetPullX = pullStrength * (px - baseX);
        const targetPullY = pullStrength * (py - baseY);
        item.pullX += (targetPullX - item.pullX) * (reducedMotion ? 1 : 0.12);
        item.pullY += (targetPullY - item.pullY) * (reducedMotion ? 1 : 0.12);

        item.x = baseX + item.pullX;
        item.y = baseY + item.pullY;

        if (distance < nearestDistance && target > 0.35) {
          nearestDistance = distance;
          nearest = item;
        }
      }

      // Attention concentrates: with something focused, everything else
      // recedes. Without, the field sits at an even, readable presence.
      const anyFocus = ordered.reduce((max, i) => Math.max(max, i.focus), 0);

      for (const item of ordered) {
        const isRelated = related.has(item.object.id);
        const presence =
          (0.45 + item.object.depth * 0.55) *
          (1 - anyFocus * 0.4 * (1 - item.focus) * (isRelated ? 0.3 : 1)) *
          (isRelated ? 1.15 : 1);

        // Light direction: from the body toward the pointer.
        const dx = px - item.x;
        const dy = py - item.y;
        const length = Math.hypot(dx, dy) || 1;

        // The orbital path, revealed on approach. Only for bodies that orbit
        // something in view — a relationship, drawn.
        if (item.focus > 0.02 && !reducedMotion) {
          drawOrbitHint(ctx, item, width, height, item.focus);
        }

        drawBody(ctx, item.object.appearance, item.object.id, {
          x: item.x,
          y: item.y,
          radius: item.radius * (1 + item.focus * 0.1),
          lightX: dx / length,
          lightY: dy / length,
          presence: Math.min(presence, 1),
          focus: item.focus,
        });

        // The name appears on approach, set beside the body rather than in a
        // tooltip that follows the cursor around.
        if (item.focus > 0.25) {
          drawLabel(ctx, item, item.focus);
        }
      }

      const nextId = nearest?.object.id ?? null;
      if (nextId !== lastFocusId) {
        lastFocusId = nextId;
        setFocused(nearest?.object ?? null);
        onFocus?.(nearest?.object ?? null);
      }

      frame.current = requestAnimationFrame(render);
    };

    frame.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frame.current);
      observer.disconnect();
    };
  }, [objects, radiusFor, onFocus, related, reducedMotion]);

  const handleMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    pointer.current = {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
      inside: true,
    };
  };

  const handleLeave = () => {
    pointer.current.inside = false;
  };

  const handleClick = () => {
    if (focused) onSelect?.(focused);
  };

  return (
    <div
      ref={containerRef}
      className={cn('relative', focused && 'cursor-pointer', className)}
      onPointerMove={handleMove}
      onPointerLeave={handleLeave}
      onClick={handleClick}
    >
      <canvas ref={canvasRef} className="block h-full w-full" aria-hidden="true" />

      {/*
        The canvas is decorative to a screen reader, so the same objects are
        exposed as real, focusable, keyboard-reachable controls. A pointer-only
        field would make the entire front door of the product unusable without
        a mouse.
      */}
      <ul className="sr-only">
        {objects.map((object) => (
          <li key={object.id}>
            <button onClick={() => onSelect?.(object)}>
              {object.name} — {object.classification}. {object.tagline}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * A hint of the path this body travels.
 *
 * An arc centred on the field's focal point, at this body's distance from it.
 * It is a *relationship* made visible — this thing goes round that thing — not
 * a decorative circle, and it only appears when the body is approached.
 */
function drawOrbitHint(
  ctx: CanvasRenderingContext2D,
  item: Placed,
  width: number,
  height: number,
  strength: number,
): void {
  // The Sun sits at the field's left edge by placement, so paths curve about it.
  const focalX = 0.06 * width;
  const focalY = 0.30 * height;
  const radius = Math.hypot(item.x - focalX, item.y - focalY);
  if (radius < 40 || radius > Math.max(width, height) * 2) return;

  const angle = Math.atan2(item.y - focalY, item.x - focalX);
  const span = 0.5 + strength * 0.5;

  ctx.save();
  ctx.beginPath();
  ctx.ellipse(focalX, focalY, radius, radius * 0.86, 0, angle - span, angle + span);
  ctx.strokeStyle = `rgba(169,162,150,${0.16 * strength})`;
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 6]);
  ctx.stroke();
  ctx.restore();
}

/** The body's name, set beside it. */
function drawLabel(ctx: CanvasRenderingContext2D, item: Placed, strength: number): void {
  const alpha = Math.min(1, (strength - 0.25) / 0.4);
  const offset = item.radius * 1.25 + 10;

  ctx.save();
  ctx.globalAlpha = alpha;

  // A leader line from the body out to its label, as an annotated diagram has.
  ctx.beginPath();
  ctx.moveTo(item.x + item.radius * 1.1, item.y);
  ctx.lineTo(item.x + offset, item.y);
  ctx.strokeStyle = 'rgba(169,162,150,0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.font = '500 12px "IBM Plex Sans Condensed", system-ui, sans-serif';
  ctx.fillStyle = 'rgba(244,240,232,0.94)';
  ctx.textBaseline = 'middle';
  ctx.letterSpacing = '0.09em';
  ctx.fillText(item.object.name.toUpperCase(), item.x + offset + 6, item.y);

  ctx.font = '400 10px "IBM Plex Mono", monospace';
  ctx.fillStyle = 'rgba(132,125,111,0.9)';
  ctx.letterSpacing = '0em';
  ctx.fillText(item.object.classification, item.x + offset + 6, item.y + 15);

  ctx.restore();
}

/** A seeded starfield, drawn once behind the objects. */
export function drawStarfield(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  count: number,
  seed = 7,
): void {
  let state = seedFor(String(seed));
  const random = () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };

  for (let i = 0; i < count; i += 1) {
    const x = random() * width;
    const y = random() * height;
    // A realistic magnitude distribution: many faint, very few bright.
    const magnitude = random();
    const size = magnitude > 0.985 ? 1.6 : magnitude > 0.9 ? 1.1 : 0.7;
    const alpha = 0.15 + magnitude * 0.55;
    // Real stars are not white. Most visible ones run warm.
    const warmth = random();
    const colour =
      warmth > 0.86
        ? `rgba(255,214,170,${alpha})`
        : warmth > 0.7
          ? `rgba(210,226,255,${alpha})`
          : `rgba(244,240,232,${alpha})`;
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
  }
}
