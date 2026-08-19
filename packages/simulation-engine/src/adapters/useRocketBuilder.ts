/**
 * `useRocketBuilder` — edit a rocket design from React.
 *
 * Wraps the pure functions in `core/rocket-design.ts` with the things a UI
 * needs on top of them: undo/redo, memoised analysis, and validation that
 * refreshes as the design changes.
 *
 * The design itself stays a plain immutable object, so P1 can lift it into
 * Zustand, persist it through P2, or hand it to the renderer without any
 * conversion.
 *
 * @module adapters/useRocketBuilder
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import type { ComponentRegistry } from '../core/component-registry.js';
import type { RocketDesign, ConnectionType } from '../core/component-types.js';
import {
  addStage as addStageOp,
  removeStage as removeStageOp,
  setStageIgnitionDelay as setStageIgnitionDelayOp,
  addComponent as addComponentOp,
  removeComponent as removeComponentOp,
  configureComponent as configureComponentOp,
  moveComponent as moveComponentOp,
  connectComponents as connectComponentsOp,
  disconnectComponents as disconnectComponentsOp,
  RocketDesignError,
} from '../core/rocket-design.js';
import { analyzeRocket, type RocketAnalysis } from '../core/builder.js';
import {
  validateRocket,
  type ValidationResult,
  type ValidateRocketOptions,
} from '../core/validation.js';
import { toVehicle } from '../core/vehicle.js';
import type { Vehicle } from '../core/types.js';

/** How deep the undo stack goes. */
const DEFAULT_HISTORY_LIMIT = 50;

/** Options for {@link useRocketBuilder}. */
export interface UseRocketBuilderOptions {
  /** The design to start from. */
  readonly initialDesign: RocketDesign;
  /** Registry resolving component definitions. */
  readonly registry: ComponentRegistry;
  /** Validation thresholds and mission requirements. */
  readonly validationOptions?: ValidateRocketOptions;
  /** Undo stack depth. */
  readonly historyLimit?: number;
  /** Called whenever the design changes. */
  readonly onChange?: (design: RocketDesign) => void;
}

/** What {@link useRocketBuilder} returns. */
export interface UseRocketBuilderResult {
  /** The current design. */
  readonly design: RocketDesign;
  /** Engineering analysis, recomputed when the design changes. */
  readonly analysis: RocketAnalysis;
  /** Validation result, recomputed when the design changes. */
  readonly validation: ValidationResult;
  /** The simulation-ready vehicle, recomputed when the design changes. */
  readonly vehicle: Vehicle;

  /** The last operation's error, or null. Cleared by the next success. */
  readonly lastError: RocketDesignError | null;

  /** Whether an undo is available. */
  readonly canUndo: boolean;
  /** Whether a redo is available. */
  readonly canRedo: boolean;
  /** Step back one edit. */
  readonly undo: () => void;
  /** Step forward one edit. */
  readonly redo: () => void;

  readonly addStage: (name: string, ignitionDelay_s?: number) => void;
  readonly removeStage: (stageIndex: number) => void;
  readonly setStageIgnitionDelay: (stageIndex: number, delay_s: number) => void;
  readonly addComponent: (
    defId: string,
    stageIndex: number,
    offset?: { x?: number; y?: number; z?: number },
  ) => void;
  readonly removeComponent: (instanceId: string) => void;
  readonly configureComponent: (
    instanceId: string,
    overrides: Readonly<Record<string, number>>,
  ) => void;
  readonly moveComponent: (
    instanceId: string,
    offset: { x?: number; y?: number; z?: number },
  ) => void;
  readonly connect: (
    fromInstanceId: string,
    fromAttachmentId: string,
    toInstanceId: string,
    toAttachmentId: string,
    type?: ConnectionType,
  ) => void;
  readonly disconnect: (connectionId: string) => void;
  /** Replace the whole design, e.g. after loading one from the backend. */
  readonly replaceDesign: (design: RocketDesign) => void;
}

/**
 * Edit a rocket design with undo, analysis, and validation.
 *
 * @param options - Starting design, registry, and validation settings.
 * @returns The design, its derived data, and the editing operations.
 */
export function useRocketBuilder(
  options: UseRocketBuilderOptions,
): UseRocketBuilderResult {
  const {
    initialDesign,
    registry,
    validationOptions,
    historyLimit = DEFAULT_HISTORY_LIMIT,
    onChange,
  } = options;

  const [design, setDesign] = useState<RocketDesign>(initialDesign);
  const [lastError, setLastError] = useState<RocketDesignError | null>(null);

  const undoStack = useRef<RocketDesign[]>([]);
  const redoStack = useRef<RocketDesign[]>([]);
  const [historyVersion, setHistoryVersion] = useState(0);

  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  /**
   * Apply an operation, recording the previous design for undo.
   *
   * Design operations throw `RocketDesignError` on invalid input — a component
   * that does not exist, an attachment that does not fit. Catching here and
   * surfacing through `lastError` means an invalid drag in the builder shows a
   * message instead of unmounting the tree through an error boundary.
   */
  const apply = useCallback(
    (operation: (current: RocketDesign) => RocketDesign): void => {
      setDesign(current => {
        try {
          const next = operation(current);

          undoStack.current.push(current);
          if (undoStack.current.length > historyLimit) undoStack.current.shift();
          redoStack.current.length = 0;

          setLastError(null);
          setHistoryVersion(v => v + 1);
          onChangeRef.current?.(next);
          return next;
        } catch (error) {
          if (error instanceof RocketDesignError) {
            setLastError(error);
            return current;
          }
          throw error;
        }
      });
    },
    [historyLimit],
  );

  // Derived data. Analysis walks every component, so it is memoised on the
  // design identity — which changes only when an operation actually succeeds.
  const analysis = useMemo(
    () => analyzeRocket(design, registry),
    [design, registry],
  );

  const validation = useMemo(
    () => validateRocket(design, registry, validationOptions),
    [design, registry, validationOptions],
  );

  const vehicle = useMemo(() => toVehicle(design, registry), [design, registry]);

  const undo = useCallback((): void => {
    const previous = undoStack.current.pop();
    if (!previous) return;
    setDesign(current => {
      redoStack.current.push(current);
      onChangeRef.current?.(previous);
      return previous;
    });
    setHistoryVersion(v => v + 1);
  }, []);

  const redo = useCallback((): void => {
    const next = redoStack.current.pop();
    if (!next) return;
    setDesign(current => {
      undoStack.current.push(current);
      onChangeRef.current?.(next);
      return next;
    });
    setHistoryVersion(v => v + 1);
  }, []);

  const replaceDesign = useCallback((next: RocketDesign): void => {
    setDesign(current => {
      undoStack.current.push(current);
      redoStack.current.length = 0;
      onChangeRef.current?.(next);
      return next;
    });
    setLastError(null);
    setHistoryVersion(v => v + 1);
  }, []);

  return {
    design,
    analysis,
    validation,
    vehicle,
    lastError,

    // historyVersion forces these to re-evaluate when the stacks change; the
    // stacks themselves live in refs so pushing to them does not re-render.
    canUndo: historyVersion >= 0 && undoStack.current.length > 0,
    canRedo: historyVersion >= 0 && redoStack.current.length > 0,
    undo,
    redo,

    addStage: useCallback(
      (name: string, ignitionDelay_s?: number) =>
        apply(d => addStageOp(d, name, ignitionDelay_s)),
      [apply],
    ),
    removeStage: useCallback(
      (stageIndex: number) => apply(d => removeStageOp(d, stageIndex)),
      [apply],
    ),
    setStageIgnitionDelay: useCallback(
      (stageIndex: number, delay_s: number) =>
        apply(d => setStageIgnitionDelayOp(d, stageIndex, delay_s)),
      [apply],
    ),
    addComponent: useCallback(
      (defId: string, stageIndex: number, offset?: { x?: number; y?: number; z?: number }) =>
        apply(d => addComponentOp(d, registry, defId, stageIndex, offset)),
      [apply, registry],
    ),
    removeComponent: useCallback(
      (instanceId: string) => apply(d => removeComponentOp(d, instanceId)),
      [apply],
    ),
    configureComponent: useCallback(
      (instanceId: string, overrides: Readonly<Record<string, number>>) =>
        apply(d => configureComponentOp(d, instanceId, overrides)),
      [apply],
    ),
    moveComponent: useCallback(
      (instanceId: string, offset: { x?: number; y?: number; z?: number }) =>
        apply(d => moveComponentOp(d, instanceId, offset)),
      [apply],
    ),
    connect: useCallback(
      (
        fromInstanceId: string,
        fromAttachmentId: string,
        toInstanceId: string,
        toAttachmentId: string,
        type?: ConnectionType,
      ) =>
        apply(d =>
          connectComponentsOp(
            d,
            fromInstanceId,
            fromAttachmentId,
            toInstanceId,
            toAttachmentId,
            type,
            registry,
          ),
        ),
      [apply, registry],
    ),
    disconnect: useCallback(
      (connectionId: string) => apply(d => disconnectComponentsOp(d, connectionId)),
      [apply],
    ),
    replaceDesign,
  };
}
