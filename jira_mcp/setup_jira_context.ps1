param(
    [Parameter(Mandatory=$true)]
    [string]$BaseUrl,

    [Parameter(Mandatory=$true)]
    [string]$Email,

    [string]$ConfigFile = "$env:APPDATA\AIPMAssistant\jira_context.json"
)

$ErrorActionPreference = 'Stop'
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

