import path from 'path';
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

/**
 * Test configuration, layered over the app's own Vite config so the engine
 * alias and the `.js`-to-`.ts` resolver apply in tests exactly as they do in a
 * build. Duplicating them here is how they drift.
 *
 * `root` is pinned to this directory: without it Vitest walks up and collects
 * `packages/simulation-engine`'s 570 tests as well, which then run under this
 * project's jsdom setup instead of their own node environment.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    root: path.resolve(__dirname),
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: [path.resolve(__dirname, 'src/test/setup.ts')],
      include: ['src/**/*.test.{ts,tsx}'],
      // The e2e journey needs a live API and is run separately.
      exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    },
  }),
);
