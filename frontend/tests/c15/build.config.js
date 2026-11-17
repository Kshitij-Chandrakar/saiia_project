import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Build the actual application without loading operational dotenv files.
export default defineConfig({ envFile: false, plugins: [react()], build: { outDir: 'dist-c15-local' } })
