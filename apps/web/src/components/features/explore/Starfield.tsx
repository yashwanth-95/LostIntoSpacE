import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface StarfieldProps {
  className?: string;
  /** Roughly how many stars to draw. Scaled by viewport area. */
  density?: number;
}

/**
 * A canvas starfield for the landing hero.
 *
 * Canvas rather than a few hundred DOM nodes: this is decoration, and it should
 * not put a thousand elements into the accessibility tree or the layout engine.
 * It is marked `aria-hidden` for the same reason.
 *
 * Honours `prefers-reduced-motion` by drawing a still field. The twinkle is a
 * slow sine on each star's own phase, so nothing pulses in unison.
 */
export function Starfield({ className, density = 200 }: StarfieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    let stars: { x: number; y: number; r: number; phase: number; speed: number }[] = [];

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Scale the count with area so a wide monitor is not sparse and a phone
      // is not overdrawn.
      const count = Math.round((density * width * height) / (1440 * 800));
      stars = Array.from({ length: Math.max(40, count) }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 1.1 + 0.25,
        phase: Math.random() * Math.PI * 2,
        speed: 0.4 + Math.random() * 0.8,
      }));
    };

    const draw = (t: number) => {
      const { width, height } = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, width, height);

      for (const star of stars) {
        const twinkle = reduceMotion
          ? 0.75
          : 0.55 + 0.45 * Math.sin(t * 0.0006 * star.speed + star.phase);
        ctx.globalAlpha = Math.max(0.08, twinkle * (star.r / 1.35));
        ctx.fillStyle = '#e8f1ff';
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (!reduceMotion) frame = requestAnimationFrame(draw);
    };

    resize();
    frame = requestAnimationFrame(draw);
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
    };
  }, [density]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn('w-full h-full pointer-events-none', className)}
    />
  );
}
