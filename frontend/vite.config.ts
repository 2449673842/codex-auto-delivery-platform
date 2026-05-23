import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendTarget = process.env.CODEX_BACKEND_TARGET || 'http://127.0.0.1:8700'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 9700,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
})
