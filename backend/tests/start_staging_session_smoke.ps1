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
$gatePath = Join-Path $root ('tmp\c132-launch-' + $runId + '.ready')
$job = [IntPtr]::Zero
$jobAttached = $false
$ownedProcess = $null
if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class C132Job {
 [StructLayout(LayoutKind.Sequential)] struct Basic {
  public long ProcessTime, JobTime; public uint Flags;
  public UIntPtr MinWorking, MaxWorking; public uint ActiveLimit;
  public UIntPtr Affinity; public uint Priority, Scheduling;
 }
 [StructLayout(LayoutKind.Sequential)] struct Io {
  public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
 }
 [StructLayout(LayoutKind.Sequential)] struct Extended {
  public Basic Basic; public Io Io; public UIntPtr ProcessMemory, JobMemory, PeakProcess, PeakJob;
 }
 [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int kind, IntPtr data, uint length);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job, int kind, IntPtr data, uint length, IntPtr returned);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
 [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateJobObject(IntPtr job, uint code);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
 public static IntPtr Create() {
  IntPtr job=CreateJobObject(IntPtr.Zero,null);
  if(job==IntPtr.Zero) throw new InvalidOperationException("Owned job creation failed");
  Extended limits=new Extended(); limits.Basic.Flags=0x2000;
  int size=Marshal.SizeOf(typeof(Extended)); IntPtr data=Marshal.AllocHGlobal(size);
  try {
   Marshal.StructureToPtr(limits,data,false);
   if(!SetInformationJobObject(job,9,data,(uint)size)) { CloseHandle(job); throw new InvalidOperationException("Owned job limits failed"); }
  } finally { Marshal.FreeHGlobal(data); }
  return job;
 }
 public static void Attach(IntPtr job, IntPtr process) {
  if(!AssignProcessToJobObject(job,process)) throw new InvalidOperationException("Owned process containment failed");
 }
 public static void Stop(IntPtr job) {
  if(!TerminateJobObject(job,1)) throw new InvalidOperationException("Owned job termination failed");
 }
 public static bool Empty(IntPtr job) {
  IntPtr data=Marshal.AllocHGlobal(48);
  try {
   if(!QueryInformationJobObject(job,1,data,48,IntPtr.Zero)) throw new InvalidOperationException("Owned job verification failed");
   return Marshal.ReadInt32(data,40)==0;
  } finally { Marshal.FreeHGlobal(data); }
 }
}
'@
    $job = [C132Job]::Create()
}
function Stop-OwnedTree {
    if ($job -ne [IntPtr]::Zero) {
        [C132Job]::Stop($job)
        $end = [DateTimeOffset]::UtcNow.AddSeconds(5)
        while (-not [C132Job]::Empty($job) -and [DateTimeOffset]::UtcNow -lt $end) { Start-Sleep -Milliseconds 50 }
        if (-not [C132Job]::Empty($job)) { throw 'Owned process tree stop unverified.' }
        if (-not $jobAttached -and $null -ne $ownedProcess -and -not $ownedProcess.HasExited) { $ownedProcess.Kill() }
    } elseif ($null -ne $ownedProcess) {
        & /bin/kill -KILL -- ('-' + $ownedProcess.Id) 2>$null
        if (-not $ownedProcess.HasExited) { $ownedProcess.Kill() }
        $end = [DateTimeOffset]::UtcNow.AddSeconds(5)
        do {
            $alive = @(& /bin/ps -eo pgid=,stat= | Where-Object { $_ -match ('^\s*' + $ownedProcess.Id + '\s+[^Z\s]') })
            if ($alive.Count -eq 0) { break }
            Start-Sleep -Milliseconds 50
        } while ([DateTimeOffset]::UtcNow -lt $end)
        if ($alive.Count -ne 0) { throw 'Owned process group stop unverified.' }
    }
    if ($null -ne $ownedProcess) { $ownedProcess.WaitForExit(5000) | Out-Null }
    Write-Host 'OWNED PROCESS TREE STOPPED'
}
try {
    $env:PYTHONPATH = @((Join-Path $root 'backend'), (Join-Path $root 'backend\tests'), (Join-Path ([IO.Path]::GetTempPath()) 'c113c-db-driver')) -join [IO.Path]::PathSeparator
    $scriptPath = Join-Path $root 'backend\tests\run_staging_session_workflow.py'
    $nonSecretArgs = @($scriptPath, '--ca', (Resolve-Path -LiteralPath $Ca).Path, '--run-id', $runId, '--launcher-gate', $gatePath)
    if ($CleanupOnly) { $nonSecretArgs += '--cleanup-only' }
    if ($Application) { $nonSecretArgs += '--application' }
    $quotedArgs = @($nonSecretArgs | ForEach-Object { '"' + $_ + '"' })
    # Console inherited for getpass. No password/environment credential transfer.
    $ownedProcess = Start-Process -FilePath $Python -ArgumentList $quotedArgs -NoNewWindow -PassThru
    $ownedProcess.Handle | Out-Null
    if ($job -ne [IntPtr]::Zero) {
        [C132Job]::Attach($job, $ownedProcess.Handle)
        $jobAttached = $true
    }
    New-Item -ItemType File -Path $gatePath -Force | Out-Null
    $remaining = [Math]::Max(0, ($deadline - [DateTimeOffset]::UtcNow).TotalMilliseconds)
    if (-not $ownedProcess.WaitForExit([int][Math]::Min($remaining, [int]::MaxValue))) {
        Stop-OwnedTree
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
    try {
        if ($null -ne $ownedProcess) { Stop-OwnedTree }
    } finally {
        if ($job -ne [IntPtr]::Zero) { [C132Job]::CloseHandle($job) | Out-Null }
        Remove-Item -LiteralPath $gatePath -ErrorAction SilentlyContinue
        $env:PYTHONPATH = $priorPythonPath
    }
}
