/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        display: ['"Inter Variable"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
        '3xs': ['0.625rem', { lineHeight: '0.9rem' }],
        '4xs': ['0.5625rem', { lineHeight: '0.8rem' }],
      },
      colors: {
        ink: {
          950: '#080c15',
          900: '#0d1421',
          850: '#111a2b',
          800: '#16203375',
        },
      },
      borderRadius: { xl2: '0.875rem' },
      boxShadow: {
        panel: '0 1px 2px rgba(15,23,42,0.05), 0 8px 24px -18px rgba(15,23,42,0.35)',
        float: '0 10px 30px -12px rgba(15,23,42,0.28), 0 2px 6px rgba(15,23,42,0.06)',
        inset: 'inset 0 1px 0 rgba(255,255,255,0.6)',
      },
      keyframes: {
        'fade-up': { '0%': { opacity: 0, transform: 'translateY(4px)' }, '100%': { opacity: 1, transform: 'none' } },
        'pulse-ring': { '0%': { boxShadow: '0 0 0 0 rgba(16,185,129,0.45)' }, '70%': { boxShadow: '0 0 0 6px rgba(16,185,129,0)' }, '100%': { boxShadow: '0 0 0 0 rgba(16,185,129,0)' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: {
        'fade-up': 'fade-up 180ms ease-out both',
        'pulse-ring': 'pulse-ring 1.8s ease-out infinite',
        shimmer: 'shimmer 2.5s linear infinite',
      },
    },
  },
  plugins: [],
}
