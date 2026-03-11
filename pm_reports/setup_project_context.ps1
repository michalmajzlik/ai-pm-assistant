param(
    [Parameter(Mandatory=$true)]
    [string]$Project,

    [Parameter(Mandatory=$true)]
    [string]$ProjectKey,

    [string]$ConfigFile = "$env:APPDATA\AIPMAssistant\project_report_config.json"
)

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $ConfigFile
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$config = [PSCustomObject]@{
    Project = $Project
    ProjectKey = $ProjectKey
}

$config | ConvertTo-Json | Set-Content -Encoding ASCII $ConfigFile
Write-Host "Saved project report config: $ConfigFile"
Write-Host "Project: $Project"
Write-Host "ProjectKey: $ProjectKey"

