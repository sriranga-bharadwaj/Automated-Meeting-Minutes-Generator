/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The UI calls /api/v1/...; the backend serves the same routes without that prefix.
  server: {
    proxy: {
      '/api/v1': { target: 'http://localhost:8000', rewrite: (path) => path.replace(/^\/api\/v1/, '') },
    },
  },
  test: { environment: 'jsdom', exclude: ['e2e/**', 'node_modules/**'], coverage: { provider: 'v8', include: ['src/**/*.{ts,tsx}'], exclude: ['src/**/*.test.*', 'src/vite-env.d.ts', 'src/main.tsx'], reportsDirectory: '../docs/coverage/frontend', reporter: ['text', 'html', 'json-summary', 'lcov'] } },
});
