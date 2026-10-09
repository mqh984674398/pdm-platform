import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // Simulated fixtures live in the repository-level Data/ workspace (single source).
      '@data': fileURLToPath(new URL('../Data', import.meta.url)),
    },
  },
  server: {
    // `vite preview` reuses this proxy; the end-to-end tests point it at their own backend.
    proxy: { '/api': process.env.PDM_API_URL || 'http://127.0.0.1:8000' },
    fs: { allow: ['..'] },
  },
})
