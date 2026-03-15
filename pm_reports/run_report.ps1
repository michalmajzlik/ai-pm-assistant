param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('daily','weekly','steering')]
    [string]$ReportType,

    [string]$Project,
    [string]$ProjectKey,
    [string]$OutputPath,
    [string]$SecretFile = "$env:APPDATA\SensoneoAI\jira_secret.xml",
    [string]$ProjectConfigFile = "$env:APPDATA\SensoneoAI\project_report_config.json"
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
    if (-not $Project) {
        if ($cfg.project.display_name) { $Project = [string]$cfg.project.display_name }
        elseif ($cfg.project.name) { $Project = [string]$cfg.project.name }
    }
    if (-not $ProjectKey -and $cfg.project.key) { $ProjectKey = [string]$cfg.project.key }
}

if (-not $Project -or -not $ProjectKey) {
    throw "Missing project context. Run .\pm_reports\setup_project_context.ps1 or pass -Project and -ProjectKey."
}

if (-not $OutputPath) {
    $reportFolder = Join-Path $workspaceRoot (Join-Path 'outputs\reports' $ReportType)
    if (-not (Test-Path $reportFolder)) { New-Item -ItemType Directory -Path $reportFolder -Force | Out-Null }

    $datePart = Get-Date -Format 'yyyy-MM-dd'
    switch ($ReportType) {
        'daily' { $fileName = "daily_report_$datePart.md" }
        'weekly' { $fileName = "weekly_project_status_$datePart.md" }
        'steering' { $fileName = "steering_report_$datePart.md" }
    }
    $OutputPath = Join-Path $reportFolder $fileName
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

$emailArgs = @()
if ($ReportType -eq 'weekly') {
    $m365Token = Join-Path $env:APPDATA 'SensoneoAI\m365_token.json'
    $emailDigestPath = Join-Path $env:APPDATA 'SensoneoAI\cache\outlook_weekly_digest.json'
    if (Test-Path $m365Token) {
        try {
            & $python (Join-Path $root 'outlook_digest.py') --days 7 --output $emailDigestPath | Out-Host
            if (Test-Path $emailDigestPath) {
                $emailArgs = @('--emails', $emailDigestPath)
            }
        }
        catch {
            Write-Warning "Outlook digest generation failed. Weekly report will continue without Outlook signals. $($_.Exception.Message)"
        }
    }
}

& $python (Join-Path $root 'report_builder.py') --report-type $ReportType --project $Project --project-key $ProjectKey --project-config $ProjectConfigFile --live-jira --output $OutputPath @emailArgs
Write-Host "Generated: $OutputPath"
