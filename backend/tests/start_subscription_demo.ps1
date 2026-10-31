# Explicit test process only. Does not edit .env, services or global PATH.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '../..'))
if (Get-NetTCPConnection -State Listen -LocalPort 5187 -ErrorAction SilentlyContinue) {
    throw 'Port 5187 is occupied; stop only an existing task-owned demo first.'
}
$demoPython = 'E:/deepfake_envs/SaIIA/python.exe'
$demoLauncher = Join-Path $env:TEMP 'c113c-test-launch.py'
$demoDriver = Join-Path $env:TEMP 'c113c-db-driver'
$demoPgBin = 'C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin'
foreach ($required in @($demoPython, $demoLauncher, $demoDriver, "$demoPgBin/pg_ctl.exe")) {
    if (-not (Test-Path -LiteralPath $required)) { throw 'Existing isolated test runtime is missing; see docs/CATALOG_LOCAL_MANUAL.md.' }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $demoDriver
& $demoPython $demoLauncher backend/tests/test_subscription_manual_demo.py --pg-bin $demoPgBin
exit $LASTEXITCODE
