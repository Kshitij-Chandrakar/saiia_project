import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({envFile:false,plugins:[react(),{name:'billing-admin-fixture',configureServer(server){server.middlewares.use((req,_res,next)=>{if(req.url==='/')req.url='/tests/catalog/fixtures/billing-admin.html';next();});}}],server:{host:'127.0.0.1',port:5293,strictPort:true}});
