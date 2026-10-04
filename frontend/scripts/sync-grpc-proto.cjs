// Backend proto is the source of truth; this copy is shipped with Electron.
const fs = require('fs')
const path = require('path')
const target = path.join(__dirname, '..', 'electron', 'protos', 'interview_realtime.proto')
fs.mkdirSync(path.dirname(target), { recursive: true })
fs.copyFileSync(path.join(__dirname, '..', '..', 'backend', 'protos', 'interview_realtime.proto'), target)
