import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const FRONTEND_PORT = parseInt(process.env.FRONTEND_PORT || '9700', 10)
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8700'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: FRONTEND_PORT,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})
