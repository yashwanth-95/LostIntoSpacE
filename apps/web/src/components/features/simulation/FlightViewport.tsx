import { useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Line, OrbitControls, Stars } from '@react-three/drei';
import * as THREE from 'three';
import type { TelemetryPoint } from '@/types/simulation';

/**
 * The 3D flight view.
 *
 * ## The division of labour
 *
 * This file renders. It computes no physics. Every position it draws comes from
 * a telemetry sample the Python engine produced — the renderer's only job is to
 * map metres onto a scene that a camera can frame, and it must never be the
 * thing that decides where the rocket is.
 *
 * ## Scale
 *
 * A 200 km ascent next to a 6,371 km planet cannot be drawn at 1:1 — the rocket
 * would be sub-pixel long before the Earth fit on screen. So the *planet* is
 * drawn at a reduced radius and altitude is exaggerated, which keeps both the
 * curvature and the trajectory legible in one frame. That is a presentation
 * choice, stated here so nobody reads distances off this view.
 */

/** Scene units per metre of altitude. */
const ALTITUDE_SCALE = 1 / 20_000;
/** Scene units per metre downrange. */
const DOWNRANGE_SCALE = 1 / 60_000;
/** Earth's drawn radius, in scene units. Not to scale with the above. */
const PLANET_RADIUS = 12;

interface FlightViewportProps {
  telemetry: readonly TelemetryPoint[];
  /** Index of the sample currently being shown. */
  index: number;
  className?: string;
}

/** Map one telemetry sample into scene coordinates. */
function toScene(point: TelemetryPoint): THREE.Vector3 {
  return new THREE.Vector3(
    point.downrange_m * DOWNRANGE_SCALE,
    PLANET_RADIUS + point.altitude_m * ALTITUDE_SCALE,
    0,
  );
}

export function FlightViewport({ telemetry, index, className }: FlightViewportProps) {
  const flownPath = useMemo(() => {
    if (telemetry.length === 0) return [];
    // Thin the path: a polyline with 5,000 vertices costs more than it shows.
    const stride = Math.max(1, Math.floor(telemetry.length / 400));
    const points: THREE.Vector3[] = [];
    for (let i = 0; i <= index; i += stride) points.push(toScene(telemetry[i]));
    if (index >= 0 && telemetry[index]) points.push(toScene(telemetry[index]));
    return points;
  }, [telemetry, index]);

  const current = telemetry[index] ?? null;

  return (
    <div className={className}>
      <Canvas
        camera={{ position: [26, 22, 26], fov: 45, near: 0.1, far: 4000 }}
        dpr={[1, 2]}
        gl={{ antialias: true }}
      >
        <color attach="background" args={['#020617']} />
        <ambientLight intensity={0.25} />
        <directionalLight position={[40, 30, 20]} intensity={1.8} color="#fff6e8" />

        <Stars radius={300} depth={60} count={4000} factor={5} fade speed={0} />

        <Planet />
        {flownPath.length > 1 && (
          <Line points={flownPath} color="#06d6f2" lineWidth={1.6} transparent opacity={0.85} />
        )}
        {current && <Rocket point={current} />}

        <OrbitControls
          enablePan={false}
          minDistance={16}
          maxDistance={220}
          target={[0, PLANET_RADIUS + 4, 0]}
        />
      </Canvas>
    </div>
  );
}

function Planet() {
  return (
    <group>
      <mesh>
        <sphereGeometry args={[PLANET_RADIUS, 64, 64]} />
        <meshStandardMaterial color="#1d4470" roughness={0.85} metalness={0.05} />
      </mesh>
      {/* Atmosphere shell — back-face rendered so it reads as a limb glow. */}
      <mesh>
        <sphereGeometry args={[PLANET_RADIUS * 1.035, 48, 48]} />
        <meshBasicMaterial
          color="#3b82f6"
          transparent
          opacity={0.14}
          side={THREE.BackSide}
          depthWrite={false}
        />
      </mesh>
      {/* The Kármán line, so "space" has a visible boundary. */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[PLANET_RADIUS + 100_000 * ALTITUDE_SCALE, PLANET_RADIUS + 100_000 * ALTITUDE_SCALE + 0.03, 128]} />
        <meshBasicMaterial color="#8aa5d6" transparent opacity={0.25} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function Rocket({ point }: { point: TelemetryPoint }) {
  const group = useRef<THREE.Group>(null);

  useFrame(() => {
    if (!group.current) return;
    const target = toScene(point);
    // Ease toward the target rather than snapping: telemetry arrives at 1 Hz
    // and the display runs at 60, so interpolating is what makes the motion
    // continuous. Position still comes only from the engine's samples.
    group.current.position.lerp(target, 0.25);
    // Pitch is commanded attitude from the engine, not derived here.
    group.current.rotation.z = point.pitch_rad - Math.PI / 2;
  });

  const burning = point.engine_on && point.thrust_N > 0;

  return (
    <group ref={group}>
      <mesh>
        <coneGeometry args={[0.16, 1.1, 12]} />
        <meshStandardMaterial color="#dde6f5" roughness={0.4} metalness={0.5} />
      </mesh>
      {burning && (
        <mesh position={[0, -0.85, 0]}>
          <coneGeometry args={[0.12, 0.9, 10]} />
          <meshBasicMaterial color="#f59e0b" transparent opacity={0.85} />
        </mesh>
      )}
      <pointLight
        position={[0, -0.8, 0]}
        color="#f59e0b"
        intensity={burning ? 6 : 0}
        distance={7}
      />
    </group>
  );
}
