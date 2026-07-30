param(
    [switch]$SkipBackendTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipBrowserExtension
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw "Not inside a Git repository."
}
Set-Location $repoRoot

Write-Host "Branch:"
git branch --show-current

Write-Host ""
Write-Host "Status:"
git status --short --branch

Write-Host ""
Write-Host "Running branch health audit..."

& "$repoRoot/scripts/pre_commit_audit.ps1" `
    -SkipBackendTests:$SkipBackendTests `
    -SkipFrontendBuild:$SkipFrontendBuild `
    -SkipBrowserExtension:$SkipBrowserExtension
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Branch health check passed."
