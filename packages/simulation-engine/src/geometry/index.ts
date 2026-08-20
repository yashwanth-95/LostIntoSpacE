/**
 * Parametric geometry.
 *
 * Pure shape mathematics with no rendering dependency, consumed by the 2D side
 * view, the 3D mesh builder and the aerodynamic model alike. Keeping it here
 * rather than inside the renderer is what guarantees the vehicle a user sees is
 * the vehicle the physics flies.
 *
 * @module geometry
 */

export {
  DEFAULT_PROFILE_SEGMENTS,
  equivalentTrapezoid,
  finArea,
  finOutline,
  noseConeProfile,
  noseRadiusAt,
  nozzleProfile,
  transitionProfile,
  tubeProfile,
  type AxialProfile,
  type Point2,
} from './profiles.js';

export {
  buildVehicleOutline,
  frontalArea,
  radiusAt,
  vehicleSilhouette,
  type FinSetShape,
  type RevolvedShape,
  type SurfaceKind,
  type VehicleOutline,
  type VehicleShape,
} from './vehicle-outline.js';
