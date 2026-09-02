import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API base is proxied in dev so the browser only ever talks to one origin,
// which keeps the CORS allowlist tight (Emergent #1).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8080', changeOrigin: true } }
  }
})
