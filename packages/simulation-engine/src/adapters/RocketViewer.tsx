/**
 * `RocketViewer` — a React component that mounts the 3D scene.
 *
 * The whole component is about forty lines of actual logic, because all it does
 * is own a canvas and a {@link SceneManager}. Every frame it reads the
 * simulation through a ref and pushes it into the scene. React re-renders only
 * when its props change — never because the rocket moved.
 *
 * ## Using this inside an existing React Three Fiber canvas
 *
 * If P1 already has an R3F `<Canvas>` and wants the rocket inside it rather
 * than in a canvas of its own, skip this component. Call `buildRocketMesh` from
 * `renderer/` and drop the result in with `<primitive object={mesh.root} />`.
 * Every renderer builder returns a plain `THREE.Object3D` for exactly that
 * reason.
 *
 * @module adapters/RocketViewer
 */

import { useEffect, useRef } from 'react';
import type { CSSProperties, ReactElement, RefObject } from 'react';
import type { DesignLayout } from '../core/builder.js';
import type { Simulation } from '../sim/runner.js';
import {
  createSceneManager,
  type SceneManager,
  type SceneManagerOptions,
} from '../renderer/scene-manager.js';
import type { CameraMode } from '../renderer/camera-rig.js';
import type { ScaleBand } from '../renderer/scale.js';

/** Props for {@link RocketViewer}. */
export interface RocketViewerProps {
  /** The rocket to draw, from `analyzeRocket(...).layout`. */
  readonly layout: DesignLayout | null;
  /**
   * The live simulation, from `useSimulation().simulationRef`.
   *
   * Null renders the rocket standing still, which is the builder view.
   */
  readonly simulationRef?: RefObject<Simulation | null>;
  /** Camera mode. */
  readonly cameraMode?: CameraMode;
  /** Scale band. */
  readonly scaleBand?: ScaleBand;
  /** Scene display options. */
  readonly sceneOptions?: Omit<SceneManagerOptions, 'canvas' | 'scaleBand' | 'cameraMode'>;
  /** Style applied to the wrapping element. */
  readonly style?: CSSProperties;
  /** Class applied to the wrapping element. */
  readonly className?: string;
  /** Called once the scene is mounted, for attaching OrbitControls. */
  readonly onSceneReady?: (manager: SceneManager) => void;
}

/**
 * A self-contained 3D view of a rocket, optionally flying a simulation.
 *
 * @param props - Layout, simulation, and display options.
 * @returns The viewer element.
 */
export function RocketViewer(props: RocketViewerProps): ReactElement {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const managerRef = useRef<SceneManager | null>(null);
  const frameRef = useRef<number | null>(null);

  const onSceneReadyRef = useRef(props.onSceneReady);
  onSceneReadyRef.current = props.onSceneReady;

  const { scaleBand, cameraMode, sceneOptions } = props;

  // Mount the scene once. Deliberately not depending on `layout` — rebuilding
  // the whole WebGL context every time a component is added would be visibly
  // slow and would lose the camera position.
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const manager = createSceneManager({
      canvas,
      ...(scaleBand ? { scaleBand } : {}),
      ...(cameraMode ? { cameraMode } : {}),
      ...sceneOptions,
    });
    managerRef.current = manager;

    const resize = (): void => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth > 0 && clientHeight > 0) {
        manager.resize(clientWidth, clientHeight);
      }
    };
    resize();

    // ResizeObserver rather than a window listener, so the view also reacts to
    // a sidebar opening or a panel being dragged.
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    onSceneReadyRef.current?.(manager);

    let lastTime = performance.now();
    const tick = (now: number): void => {
      frameRef.current = requestAnimationFrame(tick);
      const dt = Math.min(0.1, (now - lastTime) / 1000);
      lastTime = now;

      const simulation = props.simulationRef?.current;
      if (simulation) {
        // Read the simulation directly. React is not involved in this path,
        // which is the whole point.
        manager.syncState(simulation.getState());
      }
      manager.render(dt);
    };
    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      observer.disconnect();
      manager.dispose();
      managerRef.current = null;
    };
    // props.simulationRef is a stable ref object; reading `.current` inside the
    // loop is what picks up a new simulation without remounting the scene.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scaleBand, cameraMode, sceneOptions]);

  // Rebuild the rocket geometry when the design changes.
  useEffect(() => {
    const manager = managerRef.current;
    if (!manager || !props.layout) return;
    manager.setRocket(props.layout);
    if (!props.simulationRef?.current) manager.frameRocket();
  }, [props.layout, props.simulationRef]);

  // Camera mode changes without remounting.
  useEffect(() => {
    if (cameraMode) managerRef.current?.setCameraMode(cameraMode);
  }, [cameraMode]);

  return (
    <div
      ref={containerRef}
      className={props.className}
      style={{ position: 'relative', width: '100%', height: '100%', ...props.style }}
    >
      <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
    </div>
  );
}
