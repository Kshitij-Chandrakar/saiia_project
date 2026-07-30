$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw "Not inside a Git repository."
}

$hookDir = Join-Path $repoRoot ".git/hooks"
$hookPath = Join-Path $hookDir "pre-commit"
$auditScript = Join-Path $repoRoot "scripts/pre_commit_audit.ps1"

if (-not (Test-Path $auditScript)) {
    throw "Missing audit script: $auditScript"
}

$hook = @"
#!/bin/sh
if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoProfile -ExecutionPolicy Bypass -File "scripts/pre_commit_audit.ps1"
elif command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts/pre_commit_audit.ps1"
else
  echo "PowerShell is required to run scripts/pre_commit_audit.ps1" >&2
  exit 1
fi
"@

Set-Content -Path $hookPath -Value $hook -Encoding ASCII

try {
    & git update-index --chmod=+x .git/hooks/pre-commit 2>$null
}
catch {
    # Git does not track hooks; this is best-effort for environments that honor it.
}

Write-Host "Installed pre-commit hook at $hookPath"
Write-Host "The hook runs scripts/pre_commit_audit.ps1 before each commit."
