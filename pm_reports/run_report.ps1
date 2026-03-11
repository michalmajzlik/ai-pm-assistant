param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('daily','weekly','steering')]
    [string]$ReportType,

    [string]$Project,
    [string]$ProjectKey,
    [string]$OutputPath,
    [string]$SecretFile = "$env:APPDATA\AIPMAssistant\jira_secret.xml",
    [string]$ProjectConfigFile = "$env:APPDATA\AIPMAssistant\project_report_config.json"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $root

function Resolve-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe")

    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }

    return $null
}

if ((-not $Project -or -not $ProjectKey) -and (Test-Path $ProjectConfigFile)) {
    $cfg = Get-Content $ProjectConfigFile -Raw | ConvertFrom-Json
    if (-not $Project -and $cfg.Project) { $Project = [string]$cfg.Project }
    if (-not $ProjectKey -and $cfg.ProjectKey) { $ProjectKey = [string]$cfg.ProjectKey }
}

if (-not $Project -or -not $ProjectKey) {
    throw "Missing project context. Run .\pm_reports\setup_project_context.ps1 or pass -Project and -ProjectKey."
}

if (-not $OutputPath) {
    $outputsDir = Join-Path $workspaceRoot 'outputs'
    if (-not (Test-Path $outputsDir)) { New-Item -ItemType Directory -Path $outputsDir -Force | Out-Null }
    $OutputPath = Join-Path $outputsDir ("{0}_{1}.md" -f $ReportType, (Get-Date -Format 'yyyyMMdd_HHmm'))
}

if (-not (Test-Path $SecretFile)) {
    throw "Missing Jira secret file: $SecretFile"
}
$secret = Import-Clixml -Path $SecretFile

$env:JIRA_BASE_URL = [string]$secret.JIRA_BASE_URL
$env:JIRA_EMAIL = [string]$secret.JIRA_EMAIL
$env:JIRA_API_TOKEN = [string]$secret.JIRA_API_TOKEN

$python = Resolve-Python
if (-not $python) {
    throw "Python not found. Install Python 3.10+ or ensure python.exe is available in PATH."
}

& $python (Join-Path $root 'report_builder.py') --report-type $ReportType --project $Project --project-key $ProjectKey --live-jira --output $OutputPath
Write-Host "Generated: $OutputPath"



