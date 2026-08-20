import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

/**
 * Shared test setup.
 *
 * jsdom implements neither of the browser APIs this app relies on for motion:
 * `matchMedia` (the starfield honours prefers-reduced-motion) and a canvas 2D
 * context. Both are stubbed here rather than in each test.
 */

afterEach(() => {
  cleanup();
});

if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

// The starfield draws to a canvas; jsdom has no 2D context and returning null
// is exactly the case the component already guards against.
HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as never;
