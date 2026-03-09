param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('daily','weekly','steering')]
    [string]$ReportType,

    [string]$Project = 'RetuRO',
    [string]$ProjectKey = 'RET',
    [string]$OutputPath,
    [string]$SecretFile = "$env:APPDATA\SensoneoAI\jira_secret.xml"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputPath) {
    $OutputPath = Join-Path 'C:\Sensoneo AI\outputs' ("{0}_{1}.md" -f $ReportType, (Get-Date -Format 'yyyyMMdd_HHmm'))
}

if (-not (Test-Path $SecretFile)) {
    throw "Missing Jira secret file: $SecretFile"
}
$secret = Import-Clixml -Path $SecretFile

$env:JIRA_BASE_URL = [string]$secret.JIRA_BASE_URL
$env:JIRA_EMAIL = [string]$secret.JIRA_EMAIL
$env:JIRA_API_TOKEN = [string]$secret.JIRA_API_TOKEN

$python = 'C:\Users\Michal\AppData\Local\Python\pythoncore-3.14-64\python.exe'
if (-not (Test-Path $python)) {
    throw "Python not found at $python"
}

& $python (Join-Path $root 'report_builder.py') --report-type $ReportType --project $Project --project-key $ProjectKey --live-jira --output $OutputPath
Write-Host "Generated: $OutputPath"
