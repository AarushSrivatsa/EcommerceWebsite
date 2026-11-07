import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // `npm run dev`: send the API calls to the backend (in production the backend serves this app itself)
  server: { proxy: { '/scripts': 'http://localhost:8000', '/convert_into_video': 'http://localhost:8000' } },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
})
