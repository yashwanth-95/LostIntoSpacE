/**
 * Architecture boundary tests.
 *
 * The layering rule — `physics → core → sim → renderer → adapters` — is the
 * single most valuable property of this package, and the easiest to break by
 * accident. One convenient import of `three` into `sim/` and the engine can no
 * longer run in a Web Worker; one import of React into `renderer/` and P1 loses
 * the freedom to pick their own R3F version.
 *
 * These tests read the source and fail on the import, so the boundary cannot
 * rot quietly between reviews.
 */

import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('../src', import.meta.url));

/** Every `.ts`/`.tsx` file under a directory, recursively. */
function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      found.push(...sourceFiles(path));
    } else if (entry.endsWith('.ts') || entry.endsWith('.tsx')) {
      found.push(path);
    }
  }
  return found;
}

/**
 * Source with comments removed.
 *
 * These modules *document* the rules they follow, so scanning raw text finds
 * "never calls Math.random" in a doc comment and reports it as a violation.
 * Only executable code should be checked.
 */
function codeOnly(path: string): string {
  return readFileSync(path, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** Module specifiers imported by a file. */
function importsOf(path: string): string[] {
  const source = readFileSync(path, 'utf8');
  const specifiers: string[] = [];
  // Matches `import ... from 'x'`, `export ... from 'x'`, and `import('x')`.
  const pattern = /(?:from|import)\s*\(?\s*['"]([^'"]+)['"]/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    specifiers.push(match[1]!);
  }
  return specifiers;
}

/** True if a specifier refers to a package rather than a relative path. */
function isExternal(specifier: string): boolean {
  return !specifier.startsWith('.') && !specifier.startsWith('/');
}

/** Which layer a file belongs to. */
function layerOf(path: string): string {
  return relative(SRC, path).split('/')[0] ?? '';
}

describe('layer boundaries — external dependencies', () => {
  const HEADLESS_LAYERS = ['physics', 'core', 'sim', 'integration'];

  it.each(HEADLESS_LAYERS)(
    '%s/ imports nothing outside the package',
    layer => {
      const offenders: string[] = [];

      for (const file of sourceFiles(join(SRC, layer))) {
        for (const specifier of importsOf(file)) {
          if (isExternal(specifier)) {
            offenders.push(`${relative(SRC, file)} imports "${specifier}"`);
          }
        }
      }

      expect(
        offenders,
        `${layer}/ must have zero external dependencies so it runs in Node and ` +
          'in a Web Worker. Found:\n' + offenders.join('\n'),
      ).toEqual([]);
    },
  );

  it('renderer/ may use three but never React', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles(join(SRC, 'renderer'))) {
      for (const specifier of importsOf(file)) {
        if (!isExternal(specifier)) continue;
        const isAllowed = specifier === 'three' || specifier.startsWith('three/');
        if (!isAllowed) {
          offenders.push(`${relative(SRC, file)} imports "${specifier}"`);
        }
      }
    }

    expect(
      offenders,
      'renderer/ must depend only on three. Importing React here would force ' +
        'P1 onto our React version. Found:\n' + offenders.join('\n'),
    ).toEqual([]);
  });

  it('adapters/ is the only layer that imports React', () => {
    const reactImporters = new Set<string>();

    for (const file of sourceFiles(SRC)) {
      for (const specifier of importsOf(file)) {
        if (specifier === 'react' || specifier.startsWith('react/') ||
            specifier.startsWith('react-dom') || specifier.startsWith('@react-three/')) {
          reactImporters.add(layerOf(file));
        }
      }
    }

    expect([...reactImporters].sort()).toEqual(['adapters']);
  });
});

describe('layer boundaries — internal dependencies', () => {
  /** Layers each layer is allowed to reach into. */
  const ALLOWED: Readonly<Record<string, readonly string[]>> = {
    physics: [],
    core: ['physics'],
    sim: ['physics', 'core'],
    integration: ['physics', 'core', 'sim'],
    renderer: ['physics', 'core', 'sim'],
    adapters: ['physics', 'core', 'sim', 'renderer', 'integration'],
  };

  it.each(Object.keys(ALLOWED))('%s/ only depends on the layers below it', layer => {
    const allowed = new Set(ALLOWED[layer]);
    const offenders: string[] = [];

    for (const file of sourceFiles(join(SRC, layer))) {
      for (const specifier of importsOf(file)) {
        // Only cross-layer relative imports matter: `../<layer>/...`.
        const match = /^\.\.\/([a-z-]+)\//.exec(specifier);
        if (!match) continue;

        const target = match[1]!;
        if (target !== layer && !allowed.has(target)) {
          offenders.push(`${relative(SRC, file)} imports from ${target}/`);
        }
      }
    }

    expect(
      offenders,
      `${layer}/ may only import from [${[...allowed].join(', ')}]. Found:\n` +
        offenders.join('\n'),
    ).toEqual([]);
  });
});

describe('determinism guarantees', () => {
  const DETERMINISTIC_LAYERS = ['physics', 'core', 'sim'];

  it.each(DETERMINISTIC_LAYERS)('%s/ never calls Math.random', layer => {
    const offenders: string[] = [];

    for (const file of sourceFiles(join(SRC, layer))) {
      if (/Math\s*\.\s*random\s*\(/.test(codeOnly(file))) {
        offenders.push(relative(SRC, file));
      }
    }

    expect(
      offenders,
      'Randomness must come from the seeded generator in sim/failures.ts, or ' +
        'two runs of the same config will not match. Found:\n' + offenders.join('\n'),
    ).toEqual([]);
  });

  it('the simulation loop never reads the wall clock', () => {
    const offenders: string[] = [];

    for (const file of sourceFiles(join(SRC, 'sim'))) {
      if (/Date\s*\.\s*now\s*\(|new\s+Date\s*\(|performance\s*\.\s*now\s*\(/.test(codeOnly(file))) {
        offenders.push(relative(SRC, file));
      }
    }

    expect(
      offenders,
      'A simulation must be a pure function of its config. Found:\n' +
        offenders.join('\n'),
    ).toEqual([]);
  });
});
