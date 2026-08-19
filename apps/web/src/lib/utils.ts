import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number, decimals = 2): string {
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(decimals)}B`;
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(decimals)}M`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(decimals)}K`;
  return value.toFixed(decimals);
}

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatMass(kg: number): string {
  if (kg >= 1000) return `${(kg / 1000).toFixed(2)} t`;
  return `${kg.toFixed(1)} kg`;
}

export function formatAltitude(km: number): string {
  if (km >= 1e6) return `${(km / 1e6).toFixed(2)} M km`;
  if (km >= 1000) return `${(km / 1000).toFixed(1)}K km`;
  return `${km.toFixed(1)} km`;
}

export function formatVelocity(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} km/s`;
  return `${ms.toFixed(1)} m/s`;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
