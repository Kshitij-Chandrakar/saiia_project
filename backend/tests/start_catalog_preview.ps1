# Public-only local pricing service. No .env, normal auth or shared database changes.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '../..'))
if (Get-NetTCPConnection -State Listen -LocalPort 5188 -ErrorAction SilentlyContinue) {
    throw 'Local pricing port 5188 is occupied; preserve the existing process.'
}
$previewPython = 'E:/deepfake_envs/SaIIA/python.exe'
$previewLauncher = Join-Path $env:TEMP 'c113c-test-launch.py'
$previewDriver = Join-Path $env:TEMP 'c113c-db-driver'
$previewPgBin = 'C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin'
foreach ($required in @($previewPython, $previewLauncher, $previewDriver, "$previewPgBin/pg_ctl.exe")) {
    if (-not (Test-Path -LiteralPath $required)) { throw 'Retained local test runtime missing; see docs/CATALOG_LOCAL_MANUAL.md.' }
}
$env:PYTHONUTF8 = '1'
$env:CATALOG_MANUAL_WORKBENCH = 'true'
$env:PYTHONPATH = $previewDriver
New-Item -ItemType Directory -Force tmp | Out-Null
New-Item -ItemType File -Force tmp/catalog-local-preview.enabled | Out-Null
& $previewPython $previewLauncher backend/tests/test_local_catalog_preview.py --pg-bin $previewPgBin
exit $LASTEXITCODE
