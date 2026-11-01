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
  test: { environment: 'node', coverage: { provider: 'v8', include: ['src/utils.ts'], reporter: ['text', 'html'] } },
});
