import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#07070f',
        surface:  '#0d0d1a',
        surface2: '#12121f',
        accent:   '#7c3aed',
        'accent-mid': '#a78bfa',
        cyan:     '#67e8f9',
        emerald:  '#34d399',
        amber:    '#fcd34d',
        rose:     '#f87171',
        muted:    '#6b6b8a',
        muted2:   '#3a3a5c',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'Fira Code', 'monospace'],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
    },
  },
  plugins: [],
} satisfies Config
