# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
<#
ghidra_headless.ps1 - reusable headless Ghidra "dump" for the Starlancer RE project.

Imports a binary into a persistent Ghidra project, runs auto-analysis, and runs
ExportAll.java to dump a function CSV + decompiled C + strings + symbols into
analysis\exports\. Re-runnable (-overwrite). NEVER executes the target binary.

Usage (set GHIDRA_HOME or pass -GhidraHome first):
  $env:GHIDRA_HOME = "C:\path\to\ghidra_12.x_PUBLIC"
  pwsh tools\ghidra_headless.ps1 -Binary "C:\path\to\your-copy\Lancer.exe"
  pwsh tools\ghidra_headless.ps1 -Binary "C:\path\to\Lancer.exe" -ExportDir out\ -TimeoutPerFile 3600
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Binary,
    [string]$ProjectName    = "Starlancer",
    [string]$ProjectDir     = $(if ($env:SL_GHIDRA_PROJECT) { $env:SL_GHIDRA_PROJECT } else { Join-Path (Get-Location) "ghidra-project" }),
    [string]$ExportDir      = $(if ($env:SL_GHIDRA_EXPORTS) { $env:SL_GHIDRA_EXPORTS } else { Join-Path (Get-Location) "ghidra-exports" }),
    [string]$GhidraHome     = $env:GHIDRA_HOME,
    [int]   $TimeoutPerFile = 1800
)
$ErrorActionPreference = "Stop"

if (-not $GhidraHome) {
    throw "Set -GhidraHome (or the GHIDRA_HOME env var) to your Ghidra install dir (the one containing support\analyzeHeadless.bat)."
}
$Headless   = Join-Path $GhidraHome "support\analyzeHeadless.bat"
$ScriptPath = Join-Path $PSScriptRoot "ghidra_scripts"

if (-not (Test-Path -LiteralPath $Binary))   { throw "Binary not found: $Binary" }
if (-not (Test-Path -LiteralPath $Headless)) { throw "analyzeHeadless.bat not found: $Headless" }

# Ghidra 12 requires JDK 21. Prefer $env:JAVA_HOME; else search common install
# locations, then pin JAVA_HOME + PATH to it (in case the `java` on PATH is older).
function Find-Jdk21Home {
    if ($env:JAVA_HOME -and (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { return $env:JAVA_HOME }
    $globs = @(
        "$env:ProgramFiles\Eclipse Adoptium\jdk-21*\bin\java.exe",
        "$env:ProgramFiles\Java\jdk-21*\bin\java.exe",
        'C:\Tools\jdk-21*\bin\java.exe', 'C:\Tools\jdk-21*\*\bin\java.exe'
    )
    $j = @(Get-ChildItem $globs -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($j.Count -gt 0) { return (Split-Path (Split-Path $j[0].FullName -Parent) -Parent) }
    return $null
}
$jdkHome = Find-Jdk21Home
if (-not $jdkHome) { throw "JDK 21 not found. Set JAVA_HOME to a JDK 21 install (Ghidra 12 requires it; a 'java' already on PATH may be an older version)." }
$env:JAVA_HOME = $jdkHome
$env:PATH = (Join-Path $jdkHome 'bin') + ';' + $env:PATH   # ensure JDK21 wins over Java 8 on PATH
Write-Host "JAVA_HOME = $env:JAVA_HOME"

New-Item -ItemType Directory -Force -Path $ProjectDir, $ExportDir | Out-Null
$log = Join-Path $ExportDir "headless.log"

Write-Host "Importing  : $Binary"
Write-Host "Project    : $ProjectDir [$ProjectName]"
Write-Host "Exports -> : $ExportDir"
Write-Host "Log        : $log"
Write-Host "---- analyzeHeadless ----"

& $Headless $ProjectDir $ProjectName `
    -import $Binary `
    -overwrite `
    -analysisTimeoutPerFile $TimeoutPerFile `
    -scriptPath $ScriptPath `
    -postScript ExportAll.java $ExportDir `
    -log $log

$code = $LASTEXITCODE
Write-Host "---- analyzeHeadless exit code: $code ----"
if ($code -ne 0) { throw "analyzeHeadless failed (exit $code). See $log" }
Get-ChildItem -LiteralPath $ExportDir -File | Sort-Object Name |
    ForEach-Object { '{0,12:N0}  {1}' -f $_.Length, $_.Name }
