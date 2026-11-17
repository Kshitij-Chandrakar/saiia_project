import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Explicit owned output, no operational dotenv or historical build-directory writes.
if (!process.env.C15_REMAINING_BUILD_DIR) throw Error('Explicit disposable output required')
export default defineConfig({ envFile: false, plugins: [react()], build: { outDir: process.env.C15_REMAINING_BUILD_DIR, emptyOutDir: false } })
