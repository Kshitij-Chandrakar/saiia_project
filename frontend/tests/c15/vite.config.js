import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ envFile: false, plugins: [react(), { name: 'c15-isolated-fixture', configureServer(server) { server.middlewares.use((req, _res, next) => { if (req.url.startsWith('/auth/')) req.url = '/tests/c15/fixture.html'; next() }) } }], server: { host: '127.0.0.1', port: 5396, strictPort: true } })
