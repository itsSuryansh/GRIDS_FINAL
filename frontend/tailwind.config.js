/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f3f6fb',
          100: '#e3e9f4',
          200: '#c3cfe4',
          300: '#93a8cd',
          400: '#5d7cb1',
          500: '#3c5c96',
          600: '#2c457a',
          700: '#233862',
          800: '#1b2b4d',
          900: '#121d35',
          950: '#0b1324',
        },
        sig: {
          green: '#0f9d58',
          amber: '#c98a05',
          red: '#c02b45',
          blue: '#1d4ed8',
          cyan: '#0891b2',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '0.95rem' }],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(15, 35, 66, 0.06)',
      },
    },
  },
  plugins: [],
}
