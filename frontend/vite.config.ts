import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend is served by the Flask app in production (frontend/ is copied
// into the image), so the dev server proxies /api to the backend.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      // index.html is the legacy multi-page generator Flask serves at '/'.
      // The React shell has its own entry so the two never collide.
      input: {
        main: 'app.html',
      },
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
        },
      },
    },
  },
})
