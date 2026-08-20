/**
 * Drawing a celestial body from its measured appearance.
 *
 * No textures are loaded. Every body in the object field is synthesised from
 * the data the catalogue already carries — base colour, band colours, albedo,
 * texture class, ring geometry, axial tilt — which means a planet's appearance
 * on screen is derived from the same record as its physical properties.
 *
 * That is not a shortcut. At the sizes these are drawn, a synthesised body is
 * *more* legible than a photograph: it can be lit consistently from one source,
 * it scales to any size without resampling, it costs no bandwidth, and it reads
 * clearly at 24 pixels where a photograph becomes mud. Real photography appears
 * where it earns its place — in the inspection overlay, on object pages, in the
 * mission library.
 *
 * ## Lighting
 *
 * One light source, and its direction is the cursor. Moving the pointer across
 * the field moves the terminator across every body in it, which is what makes
 * the field feel like a space rather than a picture — and it is honest, because
 * a body's lit fraction really is a function of where the light is.
 *
 * @module features/field/drawBody
 */

/** Appearance data as the catalogue publishes it. */
export interface Appearance {
  base_color: string;
  accent_color?: string | null;
  band_colors?: string[];
  radius_km: number;
  texture: string;
  albedo: number;
  atmosphere_color?: string | null;
  atmosphere_strength: number;
  emissive: boolean;
  axial_tilt_deg: number;
  ring?: {
    inner_radius_ratio: number;
    outer_radius_ratio: number;
    color: string;
    opacity: number;
    tilt_deg: number;
    gaps?: number[];
  } | null;
}

export interface DrawBodyOptions {
  /** Centre of the body, in canvas pixels. */
  readonly x: number;
  readonly y: number;
  /** Drawn radius, in canvas pixels. */
  readonly radius: number;
  /** Unit vector toward the light. */
  readonly lightX: number;
  readonly lightY: number;
  /** 0 is far and faint, 1 is near and fully present. */
  readonly presence: number;
  /** 0–1, how strongly this body is the focus of attention. */
  readonly focus: number;
}

/**
 * A small deterministic hash, so a body's surface detail is stable frame to
 * frame instead of boiling.
 */
function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/** Hash a string into a seed, so each object gets its own stable surface. */
export function seedFor(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i += 1) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/** Mix two hex colours. */
function mix(a: string, b: string, t: number): string {
  const pa = parseHex(a);
  const pb = parseHex(b);
  const r = Math.round(pa[0] + (pb[0] - pa[0]) * t);
  const g = Math.round(pa[1] + (pb[1] - pa[1]) * t);
  const bl = Math.round(pa[2] + (pb[2] - pa[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function parseHex(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean;
  return [
    parseInt(full.slice(0, 2), 16) || 0,
    parseInt(full.slice(2, 4), 16) || 0,
    parseInt(full.slice(4, 6), 16) || 0,
  ];
}

function withAlpha(hex: string, alpha: number): string {
  const [r, g, b] = parseHex(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * Draw one body.
 *
 * Order matters: the far half of a ring goes down before the planet so the
 * planet occludes it, then the body, then the near half of the ring on top.
 * Drawing a ring as a single ellipse in front of the planet is the giveaway
 * that nobody thought about it.
 */
export function drawBody(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  id: string,
  options: DrawBodyOptions,
): void {
  const { x, y, radius, lightX, lightY, presence, focus } = options;
  if (radius <= 0.4) return;

  const random = seeded(seedFor(id));
  const alpha = 0.35 + 0.65 * presence;

  ctx.save();
  ctx.globalAlpha = alpha;

  if (appearance.ring) {
    drawRing(ctx, appearance, x, y, radius, 'far');
  }

  // ── The disc, lit from one side ────────────────────────────
  const lit = ctx.createRadialGradient(
    x + lightX * radius * 0.45,
    y + lightY * radius * 0.45,
    radius * 0.05,
    x,
    y,
    radius,
  );

  const base = appearance.base_color;
  // Albedo drives how bright the lit limb gets. A body that reflects 4% of the
  // light falling on it should not look like one that reflects 99%.
  const brightness = 0.35 + Math.min(appearance.albedo, 1) * 0.65;
  lit.addColorStop(0, mix(base, '#ffffff', 0.34 * brightness));
  lit.addColorStop(0.55, base);
  lit.addColorStop(1, mix(base, '#000000', appearance.emissive ? 0.1 : 0.72));

  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = lit;
  ctx.fill();

  // ── Surface detail ─────────────────────────────────────────
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.clip();

  // Detail is expensive and invisible on a distant body, so it is only drawn
  // where it can actually be seen.
  const detail = presence > 0.25 && radius > 8;

  if (detail) {
    switch (appearance.texture) {
      case 'banded':
      case 'gaseous':
        drawBands(ctx, appearance, x, y, radius, random);
        break;
      case 'cratered':
        drawCraters(ctx, appearance, x, y, radius, random);
        break;
      case 'oceanic':
        drawContinents(ctx, appearance, x, y, radius, random);
        break;
      case 'volcanic':
        drawVolcanic(ctx, appearance, x, y, radius, random);
        break;
      case 'icy':
        drawFractures(ctx, appearance, x, y, radius, random);
        break;
      case 'metallic':
        drawSpecular(ctx, x, y, radius, lightX, lightY);
        break;
      case 'stellar':
        drawGranulation(ctx, appearance, x, y, radius, random);
        break;
      case 'rocky':
      case 'irregular':
      default:
        drawMottling(ctx, appearance, x, y, radius, random);
        break;
    }
  }

  // The terminator: the shadowed limb. This is what makes a disc read as a
  // sphere rather than as a coloured circle.
  if (!appearance.emissive) {
    const shadow = ctx.createRadialGradient(
      x + lightX * radius * 0.7,
      y + lightY * radius * 0.7,
      radius * 0.25,
      x - lightX * radius * 0.35,
      y - lightY * radius * 0.35,
      radius * 1.5,
    );
    shadow.addColorStop(0, 'rgba(0,0,0,0)');
    shadow.addColorStop(0.55, 'rgba(0,0,0,0.28)');
    shadow.addColorStop(1, 'rgba(0,0,0,0.86)');
    ctx.fillStyle = shadow;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }

  ctx.restore();

  // ── Atmosphere ─────────────────────────────────────────────
  if (appearance.atmosphere_strength > 0.02 && appearance.atmosphere_color) {
    const reach = radius * (1 + 0.10 + appearance.atmosphere_strength * 0.14);
    const halo = ctx.createRadialGradient(x, y, radius * 0.94, x, y, reach);
    halo.addColorStop(0, withAlpha(appearance.atmosphere_color, 0));
    halo.addColorStop(0.4, withAlpha(appearance.atmosphere_color, 0.34 * appearance.atmosphere_strength));
    halo.addColorStop(1, withAlpha(appearance.atmosphere_color, 0));
    ctx.beginPath();
    ctx.arc(x, y, reach, 0, Math.PI * 2);
    ctx.fillStyle = halo;
    ctx.fill();
  }

  // ── Emission ───────────────────────────────────────────────
  if (appearance.emissive) {
    const corona = ctx.createRadialGradient(x, y, radius * 0.9, x, y, radius * 2.6);
    corona.addColorStop(0, withAlpha(appearance.accent_color ?? base, 0.5));
    corona.addColorStop(0.35, withAlpha(appearance.accent_color ?? base, 0.14));
    corona.addColorStop(1, withAlpha(base, 0));
    ctx.beginPath();
    ctx.arc(x, y, radius * 2.6, 0, Math.PI * 2);
    ctx.fillStyle = corona;
    ctx.fill();
  }

  if (appearance.ring) {
    drawRing(ctx, appearance, x, y, radius, 'near');
  }

  // A hairline on the focused body, so the thing under the cursor is
  // unambiguous without a glow effect.
  if (focus > 0.01) {
    ctx.beginPath();
    ctx.arc(x, y, radius * 1.14, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(244,240,232,${0.34 * focus})`;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  ctx.restore();
}

// ============================================================
// Surface treatments
// ============================================================

/** Latitudinal bands, as a gas giant has. */
function drawBands(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const colours = appearance.band_colors?.length
    ? appearance.band_colors
    : [appearance.base_color, mix(appearance.base_color, '#ffffff', 0.14)];

  const tilt = (appearance.axial_tilt_deg * Math.PI) / 180;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(Math.sin(tilt) * 0.35);
  ctx.globalAlpha = 0.55;

  const count = colours.length * 2;
  for (let i = 0; i < count; i += 1) {
    const t0 = -1 + (2 * i) / count;
    const t1 = -1 + (2 * (i + 1)) / count;
    const colour = colours[i % colours.length] ?? appearance.base_color;
    // Bands are drawn as ellipse segments so they curve with the limb rather
    // than reading as flat stripes across a circle.
    ctx.beginPath();
    ctx.moveTo(-radius, t0 * radius);
    for (let s = 0; s <= 12; s += 1) {
      const t = t0 + ((t1 - t0) * s) / 12;
      const halfWidth = radius * Math.sqrt(Math.max(1 - t * t, 0));
      ctx.lineTo(halfWidth * (1 - 2 * (s % 2 === 0 ? 0 : 0)), t * radius);
    }
    for (let s = 12; s >= 0; s -= 1) {
      const t = t0 + ((t1 - t0) * s) / 12;
      const halfWidth = radius * Math.sqrt(Math.max(1 - t * t, 0));
      ctx.lineTo(-halfWidth, t * radius);
    }
    ctx.closePath();
    ctx.fillStyle = colour;
    ctx.fill();
  }

  // A storm, where the body is big enough to show one.
  if (radius > 26 && random() > 0.35) {
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.ellipse(
      radius * (random() * 0.5 - 0.1),
      radius * (random() * 0.5 - 0.1),
      radius * 0.19,
      radius * 0.11,
      0,
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = mix(appearance.accent_color ?? appearance.base_color, '#8a3a20', 0.5);
    ctx.fill();
  }

  ctx.restore();
}

/** Impact craters, as an airless body has. */
function drawCraters(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const count = Math.min(46, Math.round(radius * 0.9));
  for (let i = 0; i < count; i += 1) {
    const angle = random() * Math.PI * 2;
    // Square-rooted so craters distribute evenly over the disc's area rather
    // than clustering at the centre.
    const distance = Math.sqrt(random()) * radius * 0.94;
    const cx = x + Math.cos(angle) * distance;
    const cy = y + Math.sin(angle) * distance;
    const size = radius * (0.03 + random() * 0.1);

    ctx.beginPath();
    ctx.arc(cx, cy, size, 0, Math.PI * 2);
    ctx.fillStyle = withAlpha(mix(appearance.base_color, '#000000', 0.45), 0.42);
    ctx.fill();

    // A bright rim on the larger ones.
    if (size > radius * 0.06) {
      ctx.beginPath();
      ctx.arc(cx, cy - size * 0.14, size * 0.86, 0, Math.PI * 2);
      ctx.strokeStyle = withAlpha(
        mix(appearance.accent_color ?? appearance.base_color, '#ffffff', 0.4),
        0.3,
      );
      ctx.lineWidth = Math.max(0.5, size * 0.13);
      ctx.stroke();
    }
  }
}

/** Landmasses on an ocean world. */
function drawContinents(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const land = appearance.accent_color ?? mix(appearance.base_color, '#7B9E6A', 0.7);
  const count = 7;
  for (let i = 0; i < count; i += 1) {
    const angle = random() * Math.PI * 2;
    const distance = Math.sqrt(random()) * radius * 0.75;
    const cx = x + Math.cos(angle) * distance;
    const cy = y + Math.sin(angle) * distance;

    ctx.beginPath();
    // A blobby outline, so continents do not read as circles.
    const lobes = 5 + Math.floor(random() * 4);
    for (let l = 0; l <= lobes; l += 1) {
      const a = (l / lobes) * Math.PI * 2;
      const r = radius * (0.1 + random() * 0.19);
      const px = cx + Math.cos(a) * r;
      const py = cy + Math.sin(a) * r * 0.75;
      if (l === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = withAlpha(land, 0.55);
    ctx.fill();
  }

  // Cloud bands, which is what actually dominates Earth's appearance.
  ctx.globalAlpha = 0.22;
  for (let i = 0; i < 5; i += 1) {
    const cy = y + (random() - 0.5) * radius * 1.5;
    ctx.beginPath();
    ctx.ellipse(x, cy, radius * (0.55 + random() * 0.4), radius * 0.09, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

/** Volcanic deposits, as Io has. */
function drawVolcanic(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const accent = appearance.accent_color ?? '#E8543A';
  for (let i = 0; i < 22; i += 1) {
    const angle = random() * Math.PI * 2;
    const distance = Math.sqrt(random()) * radius * 0.9;
    const size = radius * (0.04 + random() * 0.13);
    ctx.beginPath();
    ctx.arc(x + Math.cos(angle) * distance, y + Math.sin(angle) * distance, size, 0, Math.PI * 2);
    ctx.fillStyle = withAlpha(random() > 0.5 ? accent : '#6b4a12', 0.4);
    ctx.fill();
  }
}

/** Fracture lines across an ice shell. */
function drawFractures(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const accent = appearance.accent_color ?? mix(appearance.base_color, '#8A6A52', 0.6);
  ctx.strokeStyle = withAlpha(accent, 0.44);
  for (let i = 0; i < 12; i += 1) {
    const a0 = random() * Math.PI * 2;
    const a1 = a0 + (random() - 0.5) * 1.6;
    ctx.beginPath();
    ctx.lineWidth = Math.max(0.5, radius * (0.008 + random() * 0.014));
    ctx.moveTo(x + Math.cos(a0) * radius * 0.95, y + Math.sin(a0) * radius * 0.95);
    ctx.quadraticCurveTo(
      x + (random() - 0.5) * radius,
      y + (random() - 0.5) * radius,
      x + Math.cos(a1) * radius * 0.95,
      y + Math.sin(a1) * radius * 0.95,
    );
    ctx.stroke();
  }
}

/** A metallic specular highlight. */
function drawSpecular(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  lightX: number,
  lightY: number,
): void {
  const spot = ctx.createRadialGradient(
    x + lightX * radius * 0.5,
    y + lightY * radius * 0.5,
    0,
    x + lightX * radius * 0.5,
    y + lightY * radius * 0.5,
    radius * 0.6,
  );
  spot.addColorStop(0, 'rgba(255,255,255,0.5)');
  spot.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = spot;
  ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
}

/** Granulation and a limb-darkened photosphere. */
function drawGranulation(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const accent = appearance.accent_color ?? '#FF9A3C';
  for (let i = 0; i < 60; i += 1) {
    const angle = random() * Math.PI * 2;
    const distance = Math.sqrt(random()) * radius * 0.95;
    const size = radius * (0.02 + random() * 0.05);
    ctx.beginPath();
    ctx.arc(x + Math.cos(angle) * distance, y + Math.sin(angle) * distance, size, 0, Math.PI * 2);
    ctx.fillStyle = withAlpha(random() > 0.5 ? '#ffffff' : accent, 0.18);
    ctx.fill();
  }
  // Limb darkening: the Sun really is dimmer at its edge, because there you
  // see higher, cooler layers of the photosphere.
  const limb = ctx.createRadialGradient(x, y, radius * 0.55, x, y, radius);
  limb.addColorStop(0, 'rgba(0,0,0,0)');
  limb.addColorStop(1, withAlpha(accent, 0.4));
  ctx.fillStyle = limb;
  ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
}

/** Generic mottling for rocky and irregular bodies. */
function drawMottling(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  random: () => number,
): void {
  const dark = mix(appearance.base_color, '#000000', 0.4);
  const light = mix(appearance.accent_color ?? appearance.base_color, '#ffffff', 0.24);
  for (let i = 0; i < 26; i += 1) {
    const angle = random() * Math.PI * 2;
    const distance = Math.sqrt(random()) * radius * 0.92;
    const size = radius * (0.06 + random() * 0.2);
    ctx.beginPath();
    ctx.ellipse(
      x + Math.cos(angle) * distance,
      y + Math.sin(angle) * distance,
      size,
      size * (0.5 + random() * 0.5),
      random() * Math.PI,
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = withAlpha(random() > 0.5 ? dark : light, 0.2);
    ctx.fill();
  }
}

/**
 * A ring system, in two halves.
 *
 * The far half is drawn before the planet so the planet occludes it, and the
 * near half after so it passes in front. Drawing the whole ellipse in one pass
 * makes the ring look painted onto the sky rather than orbiting anything.
 */
function drawRing(
  ctx: CanvasRenderingContext2D,
  appearance: Appearance,
  x: number,
  y: number,
  radius: number,
  half: 'far' | 'near',
): void {
  const ring = appearance.ring;
  if (!ring) return;

  const tilt = (ring.tilt_deg * Math.PI) / 180;
  // A steeply tilted ring is seen more edge-on, so its minor axis collapses.
  const flatten = Math.max(0.08, Math.abs(Math.cos(tilt)) * 0.42 + 0.1);

  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-0.22);
  ctx.globalAlpha *= ring.opacity;

  const inner = radius * ring.inner_radius_ratio;
  const outer = radius * ring.outer_radius_ratio;
  const steps = 26;

  for (let i = 0; i < steps; i += 1) {
    const t0 = i / steps;
    const t1 = (i + 1) / steps;
    const r0 = inner + (outer - inner) * t0;
    const r1 = inner + (outer - inner) * t1;
    const ratio = ring.inner_radius_ratio + (ring.outer_radius_ratio - ring.inner_radius_ratio) * t0;

    // Gaps are real structure — Cassini's Division is 4,700 km of nearly empty
    // space — so a declared gap is drawn as a gap.
    const inGap = (ring.gaps ?? []).some((g) => Math.abs(ratio - g) < 0.05);
    if (inGap) continue;

    ctx.beginPath();
    ctx.ellipse(
      0,
      0,
      r1,
      r1 * flatten,
      0,
      half === 'far' ? Math.PI : 0,
      half === 'far' ? Math.PI * 2 : Math.PI,
    );
    ctx.ellipse(
      0,
      0,
      r0,
      r0 * flatten,
      0,
      half === 'far' ? Math.PI * 2 : Math.PI,
      half === 'far' ? Math.PI : 0,
      true,
    );
    ctx.closePath();
    // Slight density variation across the ring, so it does not read as a
    // uniform band.
    ctx.fillStyle = withAlpha(ring.color, 0.28 + 0.42 * Math.sin(t0 * Math.PI));
    ctx.fill();
  }

  ctx.restore();
}
