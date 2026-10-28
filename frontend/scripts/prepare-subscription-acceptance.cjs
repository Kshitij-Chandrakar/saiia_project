// Builds an unsigned, test-only package without loading/changing .env or downloading Electron.
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const frontend = path.resolve(__dirname, '..')
const work = path.resolve(frontend, '../tmp')
fs.mkdirSync(work, { recursive: true })
const run = (script, args) => execFileSync(process.execPath, [script, ...args], {
  cwd: frontend, stdio: 'inherit',
  env: { ...process.env, VITE_SUPABASE_URL: 'http://127.0.0.1:1', VITE_SUPABASE_ANON_KEY: 'synthetic-public-key',
    VITE_BACKEND_URL: 'http://127.0.0.1:1', VITE_SAIIA_WEB_AUTH_URL: 'http://127.0.0.1:5186/auth/desktop-login' },
})
const vite = path.join(frontend, 'node_modules/vite/bin/vite.js')
run(vite, ['build', '--base', './', '--outDir', path.join(work, 'c132-packaged-renderer')])
const panel = path.join(work, 'c132-physical-vite.mjs')
fs.writeFileSync(panel, `export default ${JSON.stringify({ build: { outDir: path.join(work, 'c132-physical-panel'), lib: { entry: path.join(frontend, 'tests/catalog/fixtures/physical-auto.js'), name: 'PhysicalAcceptance', formats: ['iife'], fileName: 'physical-auto' } } })}`)
run(vite, ['build', '--config', panel])
const configuration = path.join(work, 'c132-builder.json')
fs.writeFileSync(configuration, JSON.stringify({
  appId: 'local.intervucopilot.subscription.acceptance', productName: 'Intervucopilot Isolated Acceptance',
  directories: { output: path.join(work, 'c132-packaged') },
  electronDist: path.join(frontend, 'node_modules/electron/dist'),
  electronVersion: require('electron/package.json').version,
  asar: true, npmRebuild: false, forceCodeSigning: false,
  win: { target: 'dir', signAndEditExecutable: false },
  extraMetadata: { main: 'tests/catalog/fixtures/electron-subscription.cjs' },
  files: ['electron/**/*', 'tests/catalog/fixtures/electron-subscription.cjs', { from: path.join(work, 'c132-packaged-renderer'), to: 'dist', filter: ['**/*'] }],
}, null, 2))
run(path.join(frontend, 'node_modules/electron-builder/cli.js'), ['--dir', '--win', '--config', configuration])
