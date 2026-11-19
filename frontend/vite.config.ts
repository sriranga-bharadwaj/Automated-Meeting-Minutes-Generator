/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The UI calls /api/v1/...; Vite forwards directly to the backend /api/v1 routes
  server: {
    proxy: {
      '/api/v1': { target: 'http://localhost:8000' },
    },
  },
  test: { environment: 'node', coverage: { provider: 'v8', include: ['src/utils.ts'], reporter: ['text', 'html'] } },
});
