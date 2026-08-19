import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        space: {
          950: '#020617',
          900: '#0a0e1a',
          850: '#0f1629',
          800: '#141d33',
          700: '#1e2d4a',
          600: '#2a3f66',
          500: '#3b5998',
          400: '#5b7fc2',
          300: '#8aa5d6',
          200: '#b5c8e8',
          100: '#dde6f5',
          50: '#f0f4fa',
        },
        accent: {
          cyan: '#06d6f2',
          blue: '#3b82f6',
          indigo: '#6366f1',
          violet: '#8b5cf6',
          amber: '#f59e0b',
          emerald: '#10b981',
          rose: '#f43f5e',
        },
        severity: {
          info: '#38bdf8',
          warning: '#fbbf24',
          critical: '#f97316',
          fatal: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        display: ['Space Grotesk', 'Inter', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.65rem', { lineHeight: '1rem' }],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'star-field': 'radial-gradient(1px 1px at 20px 30px, white, transparent), radial-gradient(1px 1px at 40px 70px, rgba(255,255,255,0.8), transparent), radial-gradient(1px 1px at 90px 40px, rgba(255,255,255,0.6), transparent)',
      },
    },
  },
  plugins: [],
} satisfies Config;
