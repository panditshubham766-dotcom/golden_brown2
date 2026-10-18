/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
// Production: FastAPI serves the built assets at the same origin.
// Development: Vite proxies /api/* to the local FastAPI server.
// All API calls use relative paths (/api/...) — no hardcoded host.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false, // Keep origin as-is to respect FastAPI host validation
      },
    },
  },
  build: {
    // Ensure all assets are local — no CDN references
    assetsDir: 'assets',
    sourcemap: false, // Do not expose source maps in production
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
