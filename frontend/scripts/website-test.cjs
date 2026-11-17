const { spawnSync } = require('node:child_process')
const path = require('node:path')

const [outputDir, port, config] = process.argv.slice(2)
if (!outputDir || !port || !config) throw new Error('Expected output directory, API port and Playwright config.')
const env = { ...process.env, VITE_SUPABASE_URL: `http://127.0.0.1:${port}`, VITE_SUPABASE_ANON_KEY: 'synthetic-anon-key', VITE_BACKEND_URL: `http://127.0.0.1:${port}` }
const commands = [[path.join(__dirname, '../node_modules/vite/bin/vite.js'), 'build', '--outDir', outputDir], [require.resolve('@playwright/test/cli'), 'test', '-c', config]]
for (const args of commands) {
  if (spawnSync(process.execPath, args, { stdio: 'inherit', env }).status !== 0) process.exitCode = 1
  if (process.exitCode) break
}
