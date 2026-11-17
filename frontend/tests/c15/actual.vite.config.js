import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
const target = process.env.C15_GATEWAY
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(target || '')) throw Error('isolated gateway required')
export default defineConfig({ envFile: false, plugins: [react(), { name: 'actual-c15-entry', configureServer(server) { server.middlewares.use((req, _res, next) => { if (req.url.startsWith('/auth/') && !req.url.startsWith('/auth/v1/')) req.url = '/tests/c15/actual.html'; next() }) } }], server: { host: '127.0.0.1', port: 5397, strictPort: true, proxy: { '/api/': target, '/auth/v1/': target, '/rest/v1/': target, '/storage/v1/': target } } })
