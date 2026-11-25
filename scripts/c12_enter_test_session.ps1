param([ValidatePattern('^c12-rzp-test-[0-9]{2}$')][string]$SessionId='c12-rzp-test-01', [switch]$ReuseLoadedCredentials, [switch]$GenerateWebhookSecret,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$PgBin)

$ErrorActionPreference = 'Stop'
foreach ($required in @($Python, (Join-Path $PgBin 'pg_ctl.exe'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw 'Prepared Python/PostgreSQL runtime missing; no credentials requested.' }
}
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$Host.UI.RawUI.WindowTitle = "Intervucopilot C12 Test Mode - $SessionId"
$state = Join-Path (Join-Path $root 'tmp') $SessionId
New-Item -ItemType Directory -Path $state -Force | Out-Null
$mutex = New-Object System.Threading.Mutex($false, 'Local\IntervucopilotC12RZPTEST01')
if (-not $mutex.WaitOne(0)) { throw 'Another C12 credential/session workflow is active.' }
try {
    $env:BILLING_ENABLED = 'false'
    if ($ReuseLoadedCredentials) {
        if ($env:RAZORPAY_TEST_KEY_ID -cnotmatch '^rzp_test_[A-Za-z0-9]+$' -or
            [string]::IsNullOrWhiteSpace($env:RAZORPAY_TEST_KEY_SECRET) -or
            $env:RAZORPAY_TEST_ACCOUNT_ID -cnotmatch '^acc_[A-Za-z0-9]+$' -or
            [string]::IsNullOrWhiteSpace($env:RAZORPAY_TEST_WEBHOOK_SECRET) -or
            $env:RAZORPAY_TEST_WEBHOOK_SECRET.Length -lt 32) {
            throw 'Dedicated test values are not loaded in this terminal. No external activity.'
        }
        Write-Host 'Reusing existing process-local test credentials without displaying them.'
    } else {
        @{status='awaiting_masked_input'; billing_enabled=$false; process_id=$PID} | ConvertTo-Json | Set-Content (Join-Path $state 'credential-status.json')
        Write-Host 'C12 TEST MODE ONLY. Enter existing dedicated test credentials. No provider calls yet.'
        Write-Host 'If you do not have them, close this window; do not create keys before the session clock is recorded.'
        & (Join-Path $PSScriptRoot 'c12_test_credentials.ps1') -GenerateWebhookSecret:$GenerateWebhookSecret
    }
    @{status='credentials_loaded'; billing_enabled=$false; process_id=$PID} | ConvertTo-Json | Set-Content (Join-Path $state 'credential-status.json')
    Write-Host 'Credentials loaded. Waiting for local preflight/runner; no external activity.'
    $waitUntil = (Get-Date).AddMinutes(20)
    while (-not (Test-Path (Join-Path $state 'launch')) -and (Get-Date) -lt $waitUntil) {
        if (Test-Path (Join-Path $state 'stop')) { return }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Path (Join-Path $state 'launch'))) { throw 'Local preflight launch wait expired.' }
    $env:PYTHONUTF8='1'
    $env:PYTHONPATH=Join-Path $env:TEMP 'c113c-db-driver'
    & $Python backend/tests/run_razorpay_test_mode.py --session-dir $state --pg-bin $PgBin
    if ($LASTEXITCODE -ne 0) { throw 'C12 runner failed; inspect the redacted session journal for the exact stage and HTTP/error code.' }
} finally {
    & (Join-Path $PSScriptRoot 'c12_test_credentials.ps1') -Clear
    @{status='credentials_cleared'; billing_enabled=$false; process_id=$PID} | ConvertTo-Json | Set-Content (Join-Path $state 'credential-status.json')
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
