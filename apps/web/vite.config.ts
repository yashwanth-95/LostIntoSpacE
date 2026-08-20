import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const ENGINE_SRC = path.resolve(__dirname, '../../packages/simulation-engine/src');

/**
 * Resolve the simulation engine's own `.js` specifiers back to its `.ts` files.
 *
 * The engine is written as spec-compliant ESM: `import './vec3.js'` referring to
 * `vec3.ts`, which is what Node requires and what `moduleResolution: bundler`
 * in TypeScript already understands. Rollup does not, so without this the build
 * fails on every internal import in the package while `tsc` reports no errors.
 *
 * Scoped to the engine directory deliberately — this must not rewrite a genuine
 * `.js` import anywhere else.
 */
function resolveEngineTypeScript(): Plugin {
  return {
    name: 'lostintospace:resolve-engine-ts',
    enforce: 'pre',
    async resolveId(source, importer) {
      if (!importer || !importer.startsWith(ENGINE_SRC)) return null;
      if (!source.startsWith('.') || !source.endsWith('.js')) return null;

      const candidate = path.resolve(path.dirname(importer), source.replace(/\.js$/, '.ts'));
      const resolved = await this.resolve(candidate, importer, { skipSelf: true });
      if (resolved) return resolved;

      // A .tsx file (the React adapters) rather than .ts.
      return this.resolve(candidate.replace(/\.ts$/, '.tsx'), importer, { skipSelf: true });
    },
  };
}

export default defineConfig({
  plugins: [resolveEngineTypeScript(), react()],
  resolve: {
    alias: [
      // Must mirror the `paths` entries in tsconfig.json, or the build fails on
      // imports that typecheck cleanly.
      {
        find: /^@lostintospace\/simulation-engine\/(.*)$/,
        replacement: `${ENGINE_SRC}/$1`,
      },
      { find: '@lostintospace/simulation-engine', replacement: `${ENGINE_SRC}/index.ts` },
      { find: '@', replacement: path.resolve(__dirname, './src') },
    ],
  },
  server: {
    port: 3000,
    proxy: {
      // Same-origin in development, so no CORS negotiation is involved and
      // `VITE_API_URL` can stay unset.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    // Three.js alone is over 600 kB; the warning is expected and the renderer
    // is already split into its own lazily-loaded chunk.
    chunkSizeWarningLimit: 900,
  },
});
