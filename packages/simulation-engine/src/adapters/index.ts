/**
 * React adapters — the only layer that imports React.
 *
 * P1 consumes the engine through this module. Nothing here contains physics or
 * rendering logic; it is a thin binding over `sim/` and `renderer/`, and the
 * engine is fully usable without it (a Node script or a Web Worker imports
 * `sim/` directly).
 *
 * ```tsx
 * const builder = useRocketBuilder({ initialDesign, registry });
 * const sim = useSimulation({ config, autoStart: true });
 *
 * <RocketViewer layout={builder.analysis.layout} simulationRef={sim.simulationRef} />
 * ```
 *
 * @module adapters
 */

export { useSimulation } from './useSimulation.js';
export type {
  UseSimulationOptions,
  UseSimulationResult,
} from './useSimulation.js';

export { useRocketBuilder } from './useRocketBuilder.js';
export type {
  UseRocketBuilderOptions,
  UseRocketBuilderResult,
} from './useRocketBuilder.js';

export { RocketViewer } from './RocketViewer.js';
export type { RocketViewerProps } from './RocketViewer.js';
