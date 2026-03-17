/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0B1426',
        'bg-panel': '#111B2E',
        'border-subtle': '#1E3A5F',
        'accent-cyan': '#00D4FF',
        'accent-blue': '#4DA8DA',
        'status-ok': '#06D6A0',
        'status-warn': '#F4A261',
        'status-danger': '#E63946',
        'status-charge': '#FFD166',
        'status-offline': '#6C757D',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
