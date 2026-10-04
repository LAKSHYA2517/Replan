/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        slate: {
          850: '#151e2e',
          900: '#0f172a',
          950: '#020617',
        },
        replan: {
          dark: '#0a0d14',
          card: '#111726',
          border: '#1f293d',
          stale: '#ef4444',
          commit: '#10b981',
          running: '#3b82f6',
          frozen: '#8b5cf6',
          cancelled: '#64748b',
          duplicate: '#eab308',
        },
        hi: '#e2e8f0',
        dim: '#64748b',
        line: 'rgba(255, 255, 255, 0.08)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Menlo', 'Monaco', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
