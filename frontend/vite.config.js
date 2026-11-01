import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Explicit local opt-in; never redirects authentication/admin or production APIs.
const previewSwitch = fileURLToPath(new URL('../tmp/catalog-local-preview.enabled', import.meta.url))
export function catalogDevProxy(env = process.env, previewEnabled = () => existsSync(previewSwitch)) {
  const normalTarget = env.CATALOG_DEV_PROXY_TARGET || 'http://127.0.0.1:8000'
  return {
    target: normalTarget,
    changeOrigin: true,
    configure(proxy) {
      const forward = proxy.web.bind(proxy)
      proxy.web = (req, res, options) => {
        req.isolatedCatalogPreview = !env.CATALOG_DEV_PROXY_TARGET && req.method === 'GET' && req.url === '/api/catalog' && previewEnabled()
        return forward(req, res, { ...options, target: req.isolatedCatalogPreview ? 'http://127.0.0.1:5188' : normalTarget })
      }
      proxy.on('proxyReq', (outgoing, req) => {
        if (req.isolatedCatalogPreview) for (const name of ['authorization', 'cookie']) outgoing.removeHeader(name)
      })
      proxy.on('proxyRes', (response, req) => {
        if (req.isolatedCatalogPreview) response.headers['x-catalog-environment'] = 'isolated-demo'
      })
    }
  }
}

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '^/api/catalog$': catalogDevProxy() } }
})
