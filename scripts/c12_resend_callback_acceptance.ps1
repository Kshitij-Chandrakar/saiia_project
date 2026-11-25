param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$PgBin,
    [Parameter(Mandatory=$true)][string]$DriverDirectory,
    [Parameter(Mandatory=$true)][string]$Recipient
)
$ErrorActionPreference = 'Stop'
$priorPythonPath = $env:PYTHONPATH
$priorDotenvDisabled = $env:PYTHON_DOTENV_DISABLED
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location $taskRoot
$mutex = New-Object System.Threading.Mutex($false, 'Local\IntervucopilotC12ResendCallbacks')
if (-not $mutex.WaitOne(0)) { throw 'A callback acceptance process is already running.' }
try {
    foreach ($requiredPath in @($Python, $DriverDirectory, (Join-Path $PgBin 'pg_ctl.exe'), (Join-Path $env:LOCALAPPDATA 'C12Tools\cloudflared.exe'))) {
        if (-not (Test-Path -LiteralPath $requiredPath)) { throw 'Missing runtime prerequisite; no provider activity.' }
    }
    if (Test-Path (Join-Path $taskRoot 'tmp/c12-resend-callback-01/execution.json')) { throw 'Retained session journal exists; do not reset or retry.' }
    $env:PYTHONPATH = "$taskRoot\tmp\c12-svix;$taskRoot\backend;$taskRoot;$DriverDirectory"
    $env:PYTHON_DOTENV_DISABLED = 'true'
    $env:BILLING_ENABLED = 'false'
    $env:EMAIL_ENABLED = 'false'
    $env:EMAIL_DRY_RUN = 'true'
    Remove-Item Env:RESEND_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:RESEND_BILLING_WEBHOOK_SECRET -ErrorAction SilentlyContinue
    Write-Host 'Approved C12 scope: ONE synthetic send, ONE manual replay, 12 forwarded callbacks, 15 minutes.'
    Write-Host 'Keys are entered in the Python masked prompts here only. Keep this window open through cleanup.'
    try {
        $ErrorActionPreference = 'Continue'
        & $Python (Join-Path $taskRoot 'backend/tests/c12_resend_callback_acceptance.py') --pg-bin $PgBin --evidence 'tmp/c12-resend-callback-01' --cloudflared (Join-Path $env:LOCALAPPDATA 'C12Tools\cloudflared.exe') --execute --recipient $Recipient
        $nativeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    if ($nativeExit -ne 0) { throw 'Acceptance stopped; inspect redacted journal. Do not resend or restart.' }
} finally {
    Remove-Item Env:RESEND_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:RESEND_BILLING_WEBHOOK_SECRET -ErrorAction SilentlyContinue
    $env:EMAIL_ENABLED = 'false'
    $env:EMAIL_DRY_RUN = 'true'
    $env:BILLING_ENABLED = 'false'
    $env:PYTHONPATH = $priorPythonPath
    $env:PYTHON_DOTENV_DISABLED = $priorDotenvDisabled
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    Write-Host 'Credential process has ended; verify cleanup in the redacted execution journal.'
}
