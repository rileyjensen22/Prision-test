import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

// Strict kiosk CSP (CLAUDE.md section 3): our own origin only. Content hosts are added here
// once the approved_content_sources allowlist is wired in. Injected at build time only,
// because the dev server's hot reload needs inline scripts.
export const KIOSK_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ')

const cspPlugin = (): Plugin => ({
  name: 'kiosk-csp',
  apply: 'build',
  transformIndexHtml: () => [
    {
      tag: 'meta',
      attrs: { 'http-equiv': 'Content-Security-Policy', content: KIOSK_CSP },
      injectTo: 'head-prepend',
    },
  ],
})

const apiTarget = process.env.E2E_API ?? 'http://localhost:8000'
const proxy = { '/api': { target: apiTarget, rewrite: (p: string) => p.replace(/^\/api/, '') } }

export default defineConfig({
  plugins: [react(), cspPlugin()],
  server: { proxy },
  preview: { proxy },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
