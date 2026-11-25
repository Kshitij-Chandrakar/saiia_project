# One private Python process owns credentials, smoke tests and cleanup.
param(
    [Parameter(Mandatory=$true)][string]$Ca,
    [string]$Python = 'E:\deepfake_envs\SaIIA\python.exe',
    [switch]$CleanupOnly,
    [switch]$Application
)
$ErrorActionPreference = 'Stop'
$deadline = [DateTimeOffset]::Parse('2026-10-26T13:08:53Z')
if ([DateTimeOffset]::UtcNow -ge $deadline) { throw 'Approval expired; no remote work.' }
if (-not (Test-Path -LiteralPath $Ca -PathType Leaf)) { throw 'Dashboard CA file missing.' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable missing.' }
if ($Application) { Write-Host 'MODE: STAGING APPLICATION ACCEPTANCE; standalone smoke is skipped.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$priorPythonPath = $env:PYTHONPATH
$runId = [Guid]::NewGuid().ToString()
$resultPath = Join-Path $root ('tmp\c132-session-' + $runId + '.json')
try {
    $env:PYTHONPATH = @((Join-Path $root 'backend'), (Join-Path $root 'backend\tests'), (Join-Path ([IO.Path]::GetTempPath()) 'c113c-db-driver')) -join [IO.Path]::PathSeparator
    $scriptPath = Join-Path $root 'backend\tests\run_staging_session_workflow.py'
    $nonSecretArgs = @($scriptPath, '--ca', (Resolve-Path -LiteralPath $Ca).Path, '--run-id', $runId)
    if ($CleanupOnly) { $nonSecretArgs += '--cleanup-only' }
    if ($Application) { $nonSecretArgs += '--application' }
    $quotedArgs = @($nonSecretArgs | ForEach-Object { '"' + $_ + '"' })
    # Console inherited for getpass. No password/environment credential transfer.
    $ownedProcess = Start-Process -FilePath $Python -ArgumentList $quotedArgs -NoNewWindow -PassThru
    $ownedProcess.Handle | Out-Null
    $remaining = [Math]::Max(0, ($deadline - [DateTimeOffset]::UtcNow).TotalMilliseconds)
    if (-not $ownedProcess.WaitForExit([int][Math]::Min($remaining, [int]::MaxValue))) {
        $ownedProcess.Kill()
        $ownedProcess.WaitForExit(5000) | Out-Null
        throw 'Approval expired: owned client stopped. Cleanup unverified; stop remote work and report.'
    }
    $ownedProcess.Refresh()
    if ($null -eq $ownedProcess.ExitCode) { throw 'Workflow result uncertain; inspect sanitized result and report cleanup status.' }
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
        throw 'No result for this invocation. Workflow did not report completion; cleanup unverified. Inspect preceding safe stage; do not provision again.'
    }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if ($result.run_id -ne $runId -or $result.target -ne 'cfmvqbjmnwklxqlpelxe') {
        throw 'Result identity mismatch; cleanup unverified. Stop without provisioning.'
    }
    $safeStage = if ($null -eq $result.error -and $null -eq $result.failed_stage) { 'NONE' } elseif ($result.failed_stage -match '^[A-Z_]+(_[a-z_]+)?$') { $result.failed_stage } else { 'UNREPORTED' }
    $safeCause = if ($null -eq $result.error -and $null -eq $result.cause) { 'NONE' } elseif ($result.cause -match '^[a-zA-Z_]+$') { $result.cause } else { 'UNREPORTED' }
    $safeCleanupCause = if ($result.cleanup_cause -match '^[a-zA-Z_]+$') { $result.cleanup_cause } else { 'UNREPORTED' }
    Write-Host ('RESULT: failed_stage=' + $safeStage + '; cause=' + $safeCause + '; cleanup_verified=' + ($result.cleanup_verified -eq $true))
    if ($result.failure_check -match '^[a-zA-Z0-9_:-]{1,200}$') { Write-Host ('CHECK: ' + $result.failure_check) }
    if ($Application -and $result.application_failure) {
        $appStage = if ($result.application_failure.stage -match '^[a-z_]+$') { $result.application_failure.stage } else { 'UNREPORTED' }
        $appCheck = if ($result.application_failure.check -match '^[a-zA-Z0-9_:-]{1,200}$') { $result.application_failure.check } else { 'REDACTED' }
        Write-Host ('APPLICATION FAILURE: stage=' + $appStage + '; check=' + $appCheck)
    }
    if ($result.cleanup_verified -ne $true) {
        throw ('Cleanup not verified; cause=' + $safeCleanupCause + '. Use -CleanupOnly with one hidden staging password within the existing deadline; do not provision.')
    }
    if ($ownedProcess.ExitCode -ne 0 -or $null -ne $result.error) {
        throw ('Workflow failed at ' + $safeStage + '; cause=' + $safeCause + '; cleanup verified. Stop; do not retry provisioning blindly.')
    }
    Write-Host 'COMPLETE: requested workflow passed and credential/session cleanup verified.'
} finally {
    $env:PYTHONPATH = $priorPythonPath
}
