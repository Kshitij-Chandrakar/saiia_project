param(
    [Parameter(Mandatory=$true)][string]$PgBin,
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$DriverDirectory,
    [string]$Sender,
    [string]$Recipient,
    [switch]$ExecuteApproved,
    [switch]$SenderDomainVerified,
    [switch]$PublishRedesignedAssets,
    [switch]$ContinueVerifiedRedesign
)
if ($ContinueVerifiedRedesign) { $PublishRedesignedAssets = $true }
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$mutex = New-Object System.Threading.Mutex($false, 'Local\IntervucopilotC12EmailAcceptance')
if (-not $mutex.WaitOne(0)) { throw 'An email acceptance workflow is already running.' }
$originalPath = $env:PYTHONPATH
$secretPointer = [IntPtr]::Zero
$secretValue = $null
try {
    $env:BILLING_ENABLED = 'false'
    $env:EMAIL_ENABLED = 'false'
    $env:EMAIL_DRY_RUN = 'true'
    Remove-Item Env:RESEND_API_KEY -ErrorAction SilentlyContinue
    $env:PYTHONPATH = "$root\backend;$DriverDirectory"
    foreach ($requiredPath in @($Python, $DriverDirectory, (Join-Path $PgBin 'pg_ctl.exe'))) {
        if (-not (Test-Path -LiteralPath $requiredPath)) { throw 'A required local runtime path is missing; no credentials requested.' }
    }
    if ($PublishRedesignedAssets -and -not $ExecuteApproved) { throw 'Publication requires the approved execution mode.' }
    $evidenceName = if ($PublishRedesignedAssets) { 'tmp/c12-email-redesign-01' } elseif ($ExecuteApproved) { 'tmp/c12-email-admin-01' } else { 'tmp/c12-email-admin-preflight-' + [guid]::NewGuid().ToString('N') }
    $evidence = Join-Path $root $evidenceName
    if ($ContinueVerifiedRedesign) {
        $existingJournal = Get-Content -LiteralPath (Join-Path $evidence 'execution.json') -Raw | ConvertFrom-Json
        if ($existingJournal.attempts -ne 0 -or @($existingJournal.published_assets | Where-Object verified).Count -ne 3 -or [DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($existingJournal.deadline_utc)) {
            throw 'Verified-asset continuation unavailable; do not restart or extend.'
        }
    } elseif (Test-Path (Join-Path $evidence 'execution.json')) {
        throw 'Existing acceptance journal retained. Do not reset or rerun it.'
    }
    $arguments = @('backend/tests/c12_email_acceptance.py', '--pg-bin', $PgBin, '--evidence', $evidence)
    if ($PublishRedesignedAssets) { $arguments = @('backend/tests/c12_email_publication.py', '--pg-bin', $PgBin) }
    if ($ContinueVerifiedRedesign) { $arguments += '--continue-verified-email' }
    if ($ExecuteApproved) {
        if (-not $SenderDomainVerified -or -not $Sender -or -not $Recipient) {
            throw 'Approved sender, verified domain and explicit owned test recipient are required.'
        }
        Write-Host 'Approved scope only: up to TWO synthetic-fixture emails, no retries, 15 minutes. No Razorpay or public ingress.'
        $secretValue = Read-Host 'RESEND_API_KEY (masked; process only)' -AsSecureString
        $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretValue)
        $env:RESEND_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
        if ($PublishRedesignedAssets) {
            if ($Sender -ne 'billing@intervucopilot.in' -or $Recipient -match '@[^@]*\.(invalid|test|example|localhost)$') { throw 'Publication requires the approved sender and a deliverable approved recipient.' }
            $arguments += @('--recipient', $Recipient)
            Write-Host 'Combined limit: 3 uploads, 12 scripted Storage reads, 2 sends; no retries or overwrites.'
        } else { $arguments += @('--execute', '--sender', $Sender, '--recipient', $Recipient, '--sender-domain-verified') }
    }
    # Windows PowerShell turns native stderr logging into ErrorRecords. Use the
    # native exit code, so harmless startup logs cannot abort the cleanup path.
    try {
        $ErrorActionPreference = 'Continue'
        & $Python @arguments
        $nativeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    if ($nativeExit -ne 0) { throw 'Acceptance failed; inspect redacted execution.json. Do not retry sends.' }
} finally {
    Remove-Item Env:RESEND_API_KEY -ErrorAction SilentlyContinue
    if ($secretPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
    if ($secretValue) { $secretValue.Dispose() }
    $env:EMAIL_ENABLED = 'false'
    $env:EMAIL_DRY_RUN = 'true'
    $env:BILLING_ENABLED = 'false'
    $env:PYTHONPATH = $originalPath
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    Write-Host 'Temporary credential cleared; email and billing remain disabled in this process.'
}
