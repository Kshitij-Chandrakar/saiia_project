// Separate unsigned C12 installer. Never loads operational dotenv or normal outputs.
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { execFileSync } = require('node:child_process')
const frontend = path.resolve(__dirname, '..')
const root = path.resolve(frontend, '..')
const work = path.join(root, 'tmp/c12-acceptance-installer')
fs.mkdirSync(work, { recursive: true })
const cleanEnv = Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|USERPROFILE|LOCALAPPDATA|APPDATA|COMSPEC|PROCESSOR_ARCHITECTURE|NUMBER_OF_PROCESSORS)$/i.test(key)))
Object.assign(cleanEnv, { CSC_IDENTITY_AUTO_DISCOVERY:'false', ELECTRON_BUILDER_ALLOW_UNRESOLVED_DEPENDENCIES:'false', PYTHON_DOTENV_DISABLED:'true' })
const run = (file, args) => execFileSync(process.execPath, [file,...args], {cwd:frontend,env:cleanEnv,stdio:'inherit'})
const renderer = path.join(work,'renderer')
const config = path.join(work,'vite.config.mjs')
fs.writeFileSync(config, `import react from ${JSON.stringify(path.join(frontend,'node_modules/@vitejs/plugin-react/dist/index.js').replaceAll('\\','/'))};export default {root:${JSON.stringify(frontend)},base:'./',envDir:${JSON.stringify(work)},envPrefix:['C12_PUBLIC_'],plugins:[react()],define:{'import.meta.env.VITE_SUPABASE_URL':JSON.stringify('http://127.0.0.1:5296'),'import.meta.env.VITE_SUPABASE_ANON_KEY':JSON.stringify('synthetic-public-key'),'import.meta.env.VITE_BACKEND_URL':JSON.stringify('http://127.0.0.1:5296')},build:{outDir:${JSON.stringify(renderer)},emptyOutDir:true}}`)
run(path.join(frontend,'node_modules/vite/bin/vite.js'),['build','--config',config])
const builder = path.join(work,'builder.json')
fs.writeFileSync(builder, JSON.stringify({appId:'in.intervucopilot.c12acceptance',productName:'Intervucopilot C12 Acceptance',directories:{output:path.join(work,'artifacts')},electronDist:path.join(frontend,'node_modules/electron/dist'),electronVersion:require('electron/package.json').version,asar:true,npmRebuild:false,forceCodeSigning:false,publish:null,protocols:[],win:{target:[{target:'nsis',arch:['x64']}],signAndEditExecutable:false},nsis:{oneClick:false,perMachine:false,allowElevation:false,allowToChangeInstallationDirectory:true,createDesktopShortcut:false,createStartMenuShortcut:false,runAfterFinish:false,deleteAppDataOnUninstall:false,guid:'dc9ca224-d8dc-49e1-a1ab-bf01c83f812a'},extraMetadata:{name:'intervucopilot-c12-acceptance',version:'0.0.0-c12.1',description:'Isolated synthetic C12 acceptance; not for production',main:'tests/catalog/fixtures/c12-acceptance.cjs'},files:['electron/**/*.cjs','electron/**/*.proto','tests/catalog/fixtures/c12-acceptance.cjs',{from:renderer,to:'dist',filter:['**/*']}]},null,2))
run(path.join(frontend,'node_modules/electron-builder/cli.js'),['--win','--config',builder,'--publish','never'])
const asar = require('asar')
const archive = path.join(work,'artifacts/win-unpacked/resources/app.asar')
const list = asar.listPackage(archive)
if (list.some(name => /(^|[\\/])\.env(?:[./\\]|$)|execution\.json|\.pem$|\.pfx$|credential-status/i.test(name))) throw Error('Forbidden packaged file')
const privateValues = []
for (const dotenv of [path.join(root,'.env'),path.join(frontend,'.env'),path.join(frontend,'.env.local')]) {
  if (!fs.existsSync(dotenv)) continue
  for (const line of fs.readFileSync(dotenv,'utf8').split(/\r?\n/)) {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/)
    if (!match || !/(SECRET|API_KEY|SERVICE_ROLE|PASSWORD|TOKEN)/i.test(match[1]) || /ANON|PUBLIC/i.test(match[1])) continue
    const value = match[2].replace(/^['"]|['"]$/g,'').trim()
    if (value.length >= 12) privateValues.push(value)
  }
}
let scanned = 0
for (const name of list) {
  const relative = name.replace(/^[/\\]/,'')
  if (!/\.(c?js|mjs|json|html|txt|css)$/i.test(name)) continue
  const stat = asar.statFile(archive,relative)
  if (stat.files) continue
  const bytes = asar.extractFile(archive,relative)
  if (privateValues.some(value => bytes.includes(Buffer.from(value)))) throw Error('Private configuration value found in package')
  scanned++
}
const hashes = {}
for (const name of fs.readdirSync(path.join(work,'artifacts')).filter(name=>name.endsWith('.exe'))) hashes[name]=crypto.createHash('sha256').update(fs.readFileSync(path.join(work,'artifacts',name))).digest('hex')
hashes['app.asar']=crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex')
fs.writeFileSync(path.join(work,'package-verification.json'),JSON.stringify({appId:'in.intervucopilot.c12acceptance',version:'0.0.0-c12.1',unsigned:true,forbiddenFiles:0,privateValuesFound:0,textFilesScanned:scanned,hashes,files:list},null,2))
console.log('C12 installer built; package/credential exclusion verified:',scanned,'text files')
