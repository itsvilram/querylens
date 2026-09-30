import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // In development, forward /api calls to the FastAPI server, so the browser
    // sees a single origin and we need no CORS rules.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  // `vite preview` serves the production build. The end-to-end tests run it
  // against their own API server, so its address can be set with API_URL.
  preview: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://127.0.0.1:8000',
    },
  },
})
