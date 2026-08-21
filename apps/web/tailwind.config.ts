import type { Config } from 'tailwindcss';

/**
 * The LostIntoSpacE design system.
 *
 * ## Why none of this is blue
 *
 * The obvious palette for a space product is navy and cyan, and it is obvious
 * because everything already uses it. More importantly it is *wrong for the
 * job*: when the whole interface is blue, blue cannot mean anything. Here
 * colour is a channel that carries information — a burning engine is warm, an
 * oxidised planet is red, a nominal system is phosphor green — so the ground it
 * sits on has to be neutral.
 *
 * The ground is therefore a warm neutral black, the colour of a darkroom rather
 * than a night sky, and every hue that appears on it has a meaning attached.
 *
 * ## The bands
 *
 * - `ink`      — the ground and every surface built on it. Warm-neutral, never
 *                navy. 1000 is the void; 50 is archival paper white.
 * - `signal`   — status. Flame, oxide, nominal, caution, cryo, xenon. Used for
 *                state, never for decoration.
 * - `body`     — object classification. Derived from how these worlds actually
 *                look: Mars is iron oxide, Saturn is ammonia haze, Luna is
 *                regolith grey. A planet's colour is data.
 * - `metal`    — engineering surfaces. Titanium, aluminium, copper, steel.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}', '../../packages/**/src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Ground. Warm neutral, deliberately not navy.
        ink: {
          1000: '#060605',
          950: '#0A0A09',
          900: '#0F0E0D',
          850: '#151412',
          800: '#1C1A18',
          750: '#24211D',
          700: '#302C27',
          650: '#3B3730',
          600: '#4A453C',
          500: '#625C51',
          400: '#847D6F',
          300: '#A9A296',
          200: '#CAC3B7',
          100: '#E3DDD3',
          50: '#F4F0E8',
        },

        // ── Status. Each of these means one thing.
        signal: {
          /** Propulsion, ignition, energy release, the primary action. */
          flame: '#E4682E',
          'flame-bright': '#FA8A4A',
          'flame-dim': '#8A3F1C',
          /** Failure, abort, structural loss. Iron oxide, not fire-engine red. */
          oxide: '#C0392B',
          'oxide-bright': '#E05A4A',
          'oxide-dim': '#6E2119',
          /** Nominal, lock, success. Phosphor, as on an instrument. */
          nominal: '#8FB573',
          'nominal-bright': '#AFD292',
          'nominal-dim': '#4C6639',
          /** Caution, out-of-band but not lost. */
          caution: '#D9A441',
          'caution-bright': '#F0C06A',
          'caution-dim': '#7C5C1E',
          /** Atmosphere, cryogenics, water. The one cool hue — used sparingly. */
          cryo: '#7FA8B8',
          'cryo-bright': '#A6C9D6',
          'cryo-dim': '#3E5B67',
          /** Deep space, plasma, the theoretical. Rare by design. */
          xenon: '#8E7CA8',
          'xenon-bright': '#B3A3CB',
          'xenon-dim': '#4B4060',
        },

        // ── Object classification. Colour as data.
        body: {
          sol: '#FFCF87',
          mercury: '#8C8177',
          venus: '#D8B26B',
          terra: '#4E7C8E',
          luna: '#B5AFA3',
          mars: '#B4552F',
          ceres: '#77706A',
          jupiter: '#C8956B',
          saturn: '#D5BD8B',
          uranus: '#7FA8A6',
          neptune: '#5A7495',
          pluto: '#A08D7C',
          comet: '#8FA5A8',
          asteroid: '#7E786C',
          craft: '#B9BDC2',
        },

        // ── Engineering surfaces.
        metal: {
          titanium: '#989AA0',
          aluminium: '#C0C4C9',
          copper: '#B87351',
          steel: '#6D7176',
          carbon: '#3A3B3E',
        },
      },

      fontFamily: {
        /**
         * Editorial display. High-contrast serif, for the name of a thing —
         * a planet, a mission, a section. Never for data.
         */
        display: ['"Instrument Serif"', 'Georgia', 'Times New Roman', 'serif'],
        /** Long-form reading in the science and mission library. */
        editorial: ['Newsreader', 'Georgia', 'serif'],
        /** Interface and technical prose. IBM Plex was drawn for engineering. */
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        /** Dense instrument labels, where horizontal room is scarce. */
        condensed: ['"IBM Plex Sans Condensed"', '"IBM Plex Sans"', 'sans-serif'],
        /** Every number with a unit. Telemetry, coordinates, measurements. */
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      fontSize: {
        // Instrument labels run smaller than web-typical, because an
        // instrument panel is dense on purpose.
        micro: ['0.625rem', { lineHeight: '0.875rem', letterSpacing: '0.08em' }],
        tiny: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.04em' }],
        // Editorial display sizes, for the spatial headings.
        'display-sm': ['2.25rem', { lineHeight: '1.05', letterSpacing: '-0.01em' }],
        'display-md': ['3.5rem', { lineHeight: '1.02', letterSpacing: '-0.015em' }],
        'display-lg': ['5rem', { lineHeight: '0.98', letterSpacing: '-0.02em' }],
        'display-xl': ['7.5rem', { lineHeight: '0.94', letterSpacing: '-0.025em' }],
      },

      letterSpacing: {
        instrument: '0.16em',
        label: '0.09em',
      },

      spacing: {
        // The instrument grid: a 4px base with named rails for panel gutters.
        rail: '3.5rem',
        gutter: '1.75rem',
      },

      borderRadius: {
        // Small radii only. A rounded rectangle everywhere is the single most
        // recognisable tell of a template, and instruments have hard edges.
        instrument: '2px',
        panel: '3px',
      },

      transitionTimingFunction: {
        // Motion that reads as mass rather than as bounce.
        orbital: 'cubic-bezier(0.33, 0.02, 0.15, 1)',
        instrument: 'cubic-bezier(0.4, 0, 0.2, 1)',
        magnetic: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },

      transitionDuration: {
        instant: '80ms',
        quick: '160ms',
        settle: '320ms',
        drift: '720ms',
      },

      backgroundImage: {
        // A faint engineering grid, for surfaces that should read as a plate.
        plate:
          'linear-gradient(rgba(255,255,255,0.016) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.016) 1px, transparent 1px)',
        // The limb of a lit body, for object cards and hero fields.
        limb: 'radial-gradient(120% 120% at 30% 20%, rgba(255,255,255,0.10), transparent 55%)',
      },

      backgroundSize: {
        plate: '32px 32px',
      },

      keyframes: {
        // Data arriving, not decoration.
        acquire: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        sweep: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        // A single, slow breath for a live indicator. Not a shimmer.
        beacon: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        drawIn: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
      },

      animation: {
        acquire: 'acquire 320ms cubic-bezier(0.33, 0.02, 0.15, 1) both',
        beacon: 'beacon 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        sweep: 'sweep 1.4s cubic-bezier(0.4, 0, 0.2, 1) infinite',
        'draw-in': 'drawIn 1.6s cubic-bezier(0.33, 0.02, 0.15, 1) forwards',
      },

      zIndex: {
        field: '0',
        objects: '10',
        annotation: '20',
        chrome: '30',
        overlay: '40',
        modal: '50',
      },
    },
  },
  plugins: [],
} satisfies Config;
