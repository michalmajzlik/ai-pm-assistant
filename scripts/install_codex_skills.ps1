param(
    [switch]$UseSymlink,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceSkills = Join-Path $repoRoot 'codex\skills'
$targetRoot = Join-Path $env:USERPROFILE '.codex'
$targetSkills = Join-Path $targetRoot 'skills'

if (-not (Test-Path $sourceSkills)) {
    throw "Source skills folder not found: $sourceSkills"
}

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

if ($UseSymlink) {
    if (Test-Path $targetSkills) {
        if (-not $Force) {
            throw "Target already exists: $targetSkills. Re-run with -Force to replace it."
        }
        Remove-Item -Path $targetSkills -Recurse -Force
    }

    New-Item -ItemType Junction -Path $targetSkills -Target $sourceSkills | Out-Null
    Write-Host "Created junction: $targetSkills -> $sourceSkills"
    exit 0
}

New-Item -ItemType Directory -Force -Path $targetSkills | Out-Null
Copy-Item -Path (Join-Path $sourceSkills '*') -Destination $targetSkills -Recurse -Force
Write-Host "Copied skills from $sourceSkills to $targetSkills"
