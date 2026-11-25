import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({plugins:[react(),{name:'c12-isolated-pages',configureServer(server){server.middlewares.use((req,_res,next)=>{if(req.url==='/'||req.url.startsWith('/auth/checkout?'))req.url='/tests/catalog/fixtures/razorpay.html';next();});}}],server:{proxy:{'/api':'http://127.0.0.1:8120','/__c12':'http://127.0.0.1:8120'}}});
