import { useId, type ChangeEvent } from 'react';
import { cn } from '@/lib/utils';

/**
 * A parameter control.
 *
 * The interactive science pages and the what-if experiments are built almost
 * entirely out of this: change one variable, watch the consequence. It shows
 * its current value as a monospaced readout because the point of the exercise
 * is the number, not the position of a knob.
 */
export interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  /** Digits after the decimal point in the readout. */
  precision?: number;
  /** Logarithmic travel, for ranges spanning orders of magnitude. */
  logarithmic?: boolean;
  hint?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
  className?: string;
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  precision = 2,
  logarithmic,
  hint,
  disabled,
  onChange,
  className,
}: SliderProps) {
  const id = useId();

  // A log slider travels in log space and reports in linear space, so a mass
  // range of 1 kg to 100 t is controllable at both ends.
  const toSlider = (v: number) => (logarithmic ? Math.log10(Math.max(v, 1e-9)) : v);
  const fromSlider = (v: number) => (logarithmic ? 10 ** v : v);

  const sliderMin = toSlider(min);
  const sliderMax = toSlider(max);
  const sliderStep = step ?? (logarithmic ? (sliderMax - sliderMin) / 200 : (max - min) / 100);

  const handle = (event: ChangeEvent<HTMLInputElement>) => {
    onChange(fromSlider(Number(event.target.value)));
  };

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="t-label">
          {label}
        </label>
        <span className="font-mono tabular-nums text-xs text-ink-100">
          {value.toFixed(precision)}
          {unit && <span className="ml-1 text-ink-500">{unit}</span>}
        </span>
      </div>
      <input
        id={id}
        type="range"
        disabled={disabled}
        min={sliderMin}
        max={sliderMax}
        step={sliderStep}
        value={toSlider(value)}
        onChange={handle}
        className={cn(
          'w-full h-1 appearance-none bg-ink-800 rounded-none cursor-pointer disabled:opacity-40',
          '[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5',
          '[&::-webkit-slider-thumb]:w-1.5 [&::-webkit-slider-thumb]:bg-signal-flame',
          '[&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing',
          '[&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-1.5 [&::-moz-range-thumb]:border-0',
          '[&::-moz-range-thumb]:bg-signal-flame [&::-moz-range-thumb]:rounded-none',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-signal-flame',
        )}
      />
      {hint && <p className="text-tiny text-ink-500 leading-snug">{hint}</p>}
    </div>
  );
}
