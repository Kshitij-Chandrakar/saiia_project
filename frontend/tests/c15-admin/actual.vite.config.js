import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const backend = process.env.C15_ADMIN_BACKEND, auth = process.env.C15_ADMIN_AUTH;
if (![backend, auth].every(url => /^http:\/\/127\.0\.0\.1:\d+$/.test(url || ''))) throw Error('isolated loopback endpoints required');
export default defineConfig({ envFile: false, plugins: [react(), { name: 'admin-acceptance-entry', configureServer(server) { server.middlewares.use((req, _res, next) => { if (process.env.C15_ADMIN_FULL_APP !== 'true' && req.url.startsWith('/auth/') && !req.url.startsWith('/auth/v1/')) req.url = '/tests/c15-admin/actual.html'; next(); }); } }], server: { host: '127.0.0.1', port: Number(process.env.C15_ADMIN_PORT), strictPort: true, proxy: { '/api/': backend, '/auth/v1/': { target: auth, rewrite: path => path.replace('/auth/v1', '') } } } });
