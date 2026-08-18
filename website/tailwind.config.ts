import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#060605',
        surface:  '#0d0c0b',
        surface2: '#161412',
        accent:   '#ff4d2e',
        'accent-mid': '#ff8a5c',
        cyan:     '#5eb1ff',
        emerald:  '#2dd4a7',
        amber:    '#fbbf24',
        rose:     '#fb7185',
        muted:    '#99958f',
        muted2:   '#322f2a',
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
