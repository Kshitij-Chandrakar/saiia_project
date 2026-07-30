param(
    [switch]$SkipBackendTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipBrowserExtension
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Section {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Section $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Test-RiskyPath {
    param([string]$Path)

    $p = $Path -replace "\\", "/"

    if ($p -eq ".env" -or ($p -match "(^|/)\.env(\.|$)" -and $p -ne ".env.example")) { return $true }
    if ($p -match "^backend/uploads/") { return $true }
    if ($p -match "^tmp/") { return $true }
    if ($p -match "^graphify-out/") { return $true }
    if ($p -match "^\.agents/") { return $true }
    if ($p -match "^backend/debug/") { return $true }
    if ($p -match "\.zip$") { return $true }
    if ($p -match "\.(wav|webm|mp3|m4a|ogg)$") { return $true }
    if ($p -match "\.(png|jpg|jpeg|pdf|docx)$" -and ($p -match "^backend/uploads/" -or $p -match "^tmp/" -or $p -match "^backend/debug/")) { return $true }

    return $false
}

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw "Not inside a Git repository."
}
Set-Location $repoRoot

Invoke-Checked "Whitespace check: git diff --check" {
    git diff --check
}

Invoke-Checked "Staged whitespace check: git diff --cached --check" {
    git diff --cached --check
}

Write-Section "Risky staged file check"
$stagedFiles = @(git diff --cached --name-only --diff-filter=ACMRT)
if ($LASTEXITCODE -ne 0) {
    throw "Could not read staged files."
}

$riskyStagedFiles = @($stagedFiles | Where-Object { Test-RiskyPath $_ })
if ($riskyStagedFiles.Count -gt 0) {
    Write-Error "Risky staged files detected:`n$($riskyStagedFiles -join "`n")"
    exit 1
}
Write-Host "No risky staged files detected."

Invoke-Checked "Backend compile: python -m compileall -q backend/app" {
    python -m compileall -q backend/app
}

if (-not $SkipBackendTests -and (Test-Path "backend/tests")) {
    Invoke-Checked "Backend tests: python -m pytest backend/tests -q -k `"not openai and not openrouter`"" {
        python -m pytest backend/tests -q -k "not openai and not openrouter"
    }
}

if (-not $SkipFrontendBuild -and (Test-Path "frontend/package.json")) {
    Invoke-Checked "Frontend build: npm run build" {
        Push-Location frontend
        try {
            npm run build
        }
        finally {
            Pop-Location
        }
    }
}

Invoke-Checked "Electron main syntax: node --check frontend/electron/main.cjs" {
    node --check frontend/electron/main.cjs
}

Invoke-Checked "Electron preload syntax: node --check frontend/electron/preload.cjs" {
    node --check frontend/electron/preload.cjs
}

if (-not $SkipBrowserExtension -and (Test-Path "browser-extension/package.json")) {
    Invoke-Checked "Browser extension validation: npm run validate" {
        Push-Location browser-extension
        try {
            npm run validate
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host ""
Write-Host "Pre-commit audit passed."
