# Explicit test process only. Does not edit .env, services or global PATH.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '../..'))
if (Get-NetTCPConnection -State Listen -LocalPort 5187 -ErrorAction SilentlyContinue) {
    throw 'Port 5187 is occupied; stop only an existing task-owned demo first.'
}
$demoPython = $env:SUBSCRIPTION_DEMO_PYTHON
$demoLauncher = Join-Path $env:TEMP 'c113c-test-launch.py'
$demoDriver = Join-Path $env:TEMP 'c113c-db-driver'
$demoPgBin = $env:SUBSCRIPTION_DEMO_PG_BIN
if ([string]::IsNullOrWhiteSpace($demoPython) -or [string]::IsNullOrWhiteSpace($demoPgBin)) {
    throw 'Set SUBSCRIPTION_DEMO_PYTHON and SUBSCRIPTION_DEMO_PG_BIN to the isolated test runtime paths.'
}
foreach ($required in @($demoPython, $demoLauncher, $demoDriver, "$demoPgBin/pg_ctl.exe")) {
    if (-not (Test-Path -LiteralPath $required)) { throw 'Existing isolated test runtime is missing; see docs/CATALOG_LOCAL_MANUAL.md.' }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $demoDriver
& $demoPython $demoLauncher backend/tests/test_subscription_manual_demo.py --pg-bin $demoPgBin
exit $LASTEXITCODE
