import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks to the backend through a proxy so that relative URLs work
// both locally and inside Docker/preview environments (no hardcoded localhost
// in browser code).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_BACKEND_PROXY || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        '/api': { target, changeOrigin: true, ws: true },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        '/api': { target, changeOrigin: true, ws: true },
      },
    },
    build: { outDir: 'dist', sourcemap: false },
  }
})
