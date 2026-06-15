import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8011'

function manualChunks(id) {
  if (!id.includes('node_modules')) {
    return undefined
  }

  if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) {
    return 'vendor-react'
  }

  if (id.includes('/framer-motion/')) {
    return 'vendor-motion'
  }

  if (id.includes('/lucide-react/')) {
    return 'vendor-icons'
  }

  if (
    id.includes('/react-markdown/') ||
    id.includes('/remark-gfm/') ||
    id.includes('/remark-parse/') ||
    id.includes('/remark-rehype/') ||
    id.includes('/remark-stringify/') ||
    id.includes('/rehype-') ||
    id.includes('/unified/') ||
    id.includes('/mdast-') ||
    id.includes('/micromark/')
  ) {
    return 'vendor-markdown'
  }

  if (
    id.includes('/recharts/') ||
    id.includes('/d3-') ||
    id.includes('/internmap/')
  ) {
    return 'vendor-charts'
  }

  return undefined
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  server: {
    port: 5175,
    proxy: {
      '/api': {
        // In local dev, the API is served separately on 8011 by default.
        target: apiProxyTarget,
        changeOrigin: true,
      },
    }
  }
})
