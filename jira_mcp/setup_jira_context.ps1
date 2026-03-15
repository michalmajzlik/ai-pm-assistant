param(
    [Parameter(Mandatory=$true)]
    [string]$BaseUrl,

    [Parameter(Mandatory=$true)]
    [string]$Email,

    [string]$ConfigFile
)

$ErrorActionPreference = 'Stop'

if (-not $ConfigFile) {
    $primary = Join-Path $env:APPDATA 'AIPMAssistant\jira_context.json'
    $legacy = Join-Path $env:APPDATA 'SensoneoAI\jira_context.json'
    if (Test-Path $primary) { $ConfigFile = $primary }
    elseif (Test-Path $legacy) { $ConfigFile = $legacy }
    else { $ConfigFile = $primary }
}

$dir = Split-Path -Parent $ConfigFile
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$config = [PSCustomObject]@{
    BaseUrl = $BaseUrl.Trim()
    Email = $Email.Trim()
}

$config | ConvertTo-Json | Set-Content -Encoding ASCII $ConfigFile
Write-Host "Saved Jira local config: $ConfigFile"
Write-Host "BaseUrl: $($config.BaseUrl)"
Write-Host "Email: $($config.Email)"
