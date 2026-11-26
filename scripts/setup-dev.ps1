param([string]$Python, [switch]$WithTests)

$ErrorActionPreference = 'Stop'
function Invoke-SetupCommand([string]$Executable, [string[]]$CommandArguments) {
    $priorPreference = $ErrorActionPreference
    try {
        # Windows PowerShell treats ordinary pip/Git stderr progress as errors
        # when output is redirected. The native exit code is authoritative.
        $ErrorActionPreference = 'Continue'
        & $Executable @CommandArguments
        $commandSucceeded = $?
        $commandExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $priorPreference }
    if (-not $commandSucceeded -or $commandExit -ne 0) { throw "Dependency command failed (exit $commandExit). Fix the reported error and rerun setup." }
}
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    foreach ($command in @('git', 'node', 'npm')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Install $command before running setup." }
    }
    if (-not $Python) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $Python = & py -3.11 -c 'import sys; print(sys.executable)'
        } else {
            $Python = & python -c 'import sys; print(sys.executable)'
        }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required. Install it or pass -Python with its executable path.' }
    }
    & $Python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required.' }
    $nodeVersion = [version](& node -p 'process.versions.node')
    if ($LASTEXITCODE -ne 0 -or -not (($nodeVersion.Major -eq 20 -and $nodeVersion.Minor -ge 19) -or ($nodeVersion.Major -eq 22 -and $nodeVersion.Minor -ge 12) -or $nodeVersion.Major -gt 22)) { throw 'Use Node.js 20.19+ or 22.12+ (or a compatible newer version).' }
    if (-not (Test-Path '.venv')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    $venvPython = if ($env:OS -eq 'Windows_NT') { Join-Path $projectRoot '.venv/Scripts/python.exe' } else { Join-Path $projectRoot '.venv/bin/python' }
    & $venvPython -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Existing .venv is incompatible; no packages were changed.' }
    $install = @('-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '-r', 'requirements.txt')
    if ($WithTests) { $install += @('-r', 'backend/requirements-test.txt') }
    Invoke-SetupCommand $venvPython $install
    Invoke-SetupCommand $venvPython @('-m', 'pip', 'check')
    Invoke-SetupCommand (Get-Command npm -ErrorAction Stop).Source @('ci', '--prefix', 'frontend')
    Write-Host 'Dependencies installed. Configure your private environment and required services before starting the application.'
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning 'ffmpeg is not on PATH; install it or configure FFMPEG_PATH before testing local audio transcription.' }
} finally {
    Pop-Location
}
