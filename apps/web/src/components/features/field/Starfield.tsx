import { useEffect, useRef } from 'react';

import { drawStarfield } from './ObjectField';
import { cn } from '@/lib/utils';

/**
 * A star background.
 *
 * Drawn once to a canvas and left alone. There is no twinkle, no drift and no
 * parallax loop, for two reasons: a background that moves competes with the
 * object field in front of it, and a permanently animating canvas is a
 * permanently running frame loop on a page where nothing else needs one.
 *
 * The distribution is not uniform noise. Most stars are faint and a handful are
 * bright, which is how a real sky looks — an even scatter of identical dots
 * reads immediately as a texture rather than as a sky. Colour runs warm more
 * often than cool, for the same reason.
 */
export function Starfield({
  className,
  /** Stars per square pixel. */
  density = 0.00012,
  seed = 7,
}: {
  className?: string;
  density?: number;
  seed?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (!parent) return;

    const paint = () => {
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const rect = parent.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      drawStarfield(
        ctx,
        rect.width,
        rect.height,
        Math.round(rect.width * rect.height * density),
        seed,
      );
    };

    paint();
    const observer = new ResizeObserver(paint);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [density, seed]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={cn('pointer-events-none block', className)}
    />
  );
}
