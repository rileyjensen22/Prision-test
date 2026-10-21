import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Builds the phone demo (demo.html) with no CSP meta: it runs inside a sandboxed page, not a kiosk.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist-demo', rollupOptions: { input: 'demo.html' }, assetsInlineLimit: 100000000 },
})
