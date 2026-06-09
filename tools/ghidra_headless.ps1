# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
<#
ghidra_headless.ps1 - reusable headless Ghidra "dump" for the Starlancer RE project.

Imports a binary into a persistent Ghidra project, runs auto-analysis, and runs
ExportAll.java to dump a function CSV + decompiled C + strings + symbols into
analysis\exports\. Re-runnable (-overwrite). NEVER executes the target binary.

Usage:
  pwsh tools\ghidra_headless.ps1 -Binary "G:\reverse engineering\Starlancer\original\GAME\CAB\LANCER.EXE"
  pwsh tools\ghidra_headless.ps1 -Binary "...\LANCER_decrypted.exe" -TimeoutPerFile 3600
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Binary,
    [string]$ProjectName  = "Starlancer",
    [string]$ProjectDir   = "G:\reverse engineering\Starlancer\analysis\ghidra",
    [string]$ExportDir    = "G:\reverse engineering\Starlancer\analysis\exports",
    [int]   $TimeoutPerFile = 1800
)
$ErrorActionPreference = "Stop"

$GhidraHome = "C:\Tools\Ghidra\ghidra_12.1.2_PUBLIC"
$Headless   = Join-Path $GhidraHome "support\analyzeHeadless.bat"
$ScriptPath = "G:\reverse engineering\Starlancer\tools\ghidra_scripts"

if (-not (Test-Path -LiteralPath $Binary))   { throw "Binary not found: $Binary" }
if (-not (Test-Path -LiteralPath $Headless)) { throw "analyzeHeadless.bat not found: $Headless" }

# Ghidra 12 needs JDK 21. The JDK is nested (C:\Tools\jdk-21\jdk-21.0.11+10\),
# and the only `java` on PATH is Java 8 - so locate bin\java.exe explicitly and
# pin JAVA_HOME + PATH to the real JDK 21 home.
function Find-Jdk21Home {
    if ($env:JAVA_HOME -and (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))) { return $env:JAVA_HOME }
    $j = @(Get-ChildItem 'C:\Tools\jdk-21*\bin\java.exe','C:\Tools\jdk-21*\*\bin\java.exe' -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($j.Count -gt 0) { return (Split-Path (Split-Path $j[0].FullName -Parent) -Parent) }
    return $null
}
$jdkHome = Find-Jdk21Home
if (-not $jdkHome) { throw "JDK 21 not found (need a dir with bin\java.exe under C:\Tools\jdk-21*). Ghidra 12 requires JDK 21; the PATH 'java' is Java 8." }
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
