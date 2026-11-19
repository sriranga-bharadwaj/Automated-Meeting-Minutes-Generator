/// <reference types="vitest" />
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

// AMG-SR-010: a Content Security Policy for the production build. It is not applied to the dev
// server, because Vite's hot reload needs inline scripts there.
const csp = (): Plugin => ({
  name: 'ammg-csp',
  apply: 'build',
  transformIndexHtml(html) {
    const policy =
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
      "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
    return html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`);
  },
});

export default defineConfig({
  plugins: [react(), csp()],
  // The UI calls /api/v1/...; the backend serves the same routes without that prefix.
  server: {
    headers: { 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer' },
    proxy: {
      '/api/v1': { target: 'http://localhost:8000', rewrite: (path) => path.replace(/^\/api\/v1/, '') },
    },
  },
  test: { environment: 'jsdom', exclude: ['e2e/**', 'node_modules/**'], coverage: { provider: 'v8', include: ['src/**/*.{ts,tsx}'], exclude: ['src/**/*.test.*', 'src/vite-env.d.ts', 'src/main.tsx'], reportsDirectory: '../docs/coverage/frontend', reporter: ['text', 'html', 'json-summary', 'lcov'] } },
});
