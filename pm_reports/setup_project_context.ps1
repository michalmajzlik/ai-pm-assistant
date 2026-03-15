param(
    [switch]$ShowProfiles,

    [Parameter(Mandatory=$false)]
    [string]$Project,

    [Parameter(Mandatory=$false)]
    [string]$ProjectKey,

    [string]$DisplayName,

    [string]$WeeklyStatusIssueKey,

    [ValidateSet('software_delivery','multi_workstream','managed_service')]
    [string]$Profile = 'software_delivery',

    [string]$ConfigFile
)

$ErrorActionPreference = 'Stop'

function Resolve-DefaultConfigFile {
    $primary = Join-Path $env:APPDATA 'AIPMAssistant\project_report_config.json'
    $legacy = Join-Path $env:APPDATA 'SensoneoAI\project_report_config.json'
    if ((Test-Path $primary) -and (Test-Path $legacy)) {
        $primaryItem = Get-Item $primary
        $legacyItem = Get-Item $legacy
        if ($primaryItem.LastWriteTimeUtc -ge $legacyItem.LastWriteTimeUtc) { return $primary }
        return $legacy
    }
    if (Test-Path $primary) { return $primary }
    if (Test-Path $legacy) { return $legacy }
    return $primary
}

if (-not $ConfigFile) {
    $ConfigFile = Resolve-DefaultConfigFile
}

if ($ShowProfiles) {
    Write-Host 'Available profiles:'
    Write-Host '- software_delivery (recommended default for most delivery projects)'
    Write-Host '- multi_workstream (two named workstreams plus shared scope/budget sections)'
    Write-Host '- managed_service (operations/support plus delivery)'
    exit 0
}

if (-not $Project -or -not $ProjectKey) {
    throw 'Missing required parameters. Pass -Project and -ProjectKey, or run with -ShowProfiles first.'
}

if (-not $DisplayName) { $DisplayName = $Project }

$dir = Split-Path -Parent $ConfigFile
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

$templatePath = Join-Path $PSScriptRoot (Join-Path 'config_templates' ($Profile + '.json'))
if (-not (Test-Path $templatePath)) {
    throw "Profile template not found: $templatePath"
}

$config = Get-Content -Path $templatePath -Raw | ConvertFrom-Json
$config.project.name = $Project
$config.project.key = $ProjectKey
$config.project.display_name = $DisplayName
$config.profile = $Profile

if ($WeeklyStatusIssueKey) {
    if (-not $config.reports.weekly.publish) {
        $config.reports.weekly | Add-Member -NotePropertyName publish -NotePropertyValue (@{})
    }
    $config.reports.weekly.publish.enabled = $true
    $config.reports.weekly.publish.jira_issue_key = $WeeklyStatusIssueKey
    $config.reports.weekly.publish.mode = 'overwrite_description'
}

$config | ConvertTo-Json -Depth 20 | Set-Content -Path $ConfigFile -Encoding UTF8

Write-Host "Saved project report config: $ConfigFile"
Write-Host "Project: $Project"
Write-Host "ProjectKey: $ProjectKey"
Write-Host "DisplayName: $DisplayName"
Write-Host "Profile: $Profile"
if ($WeeklyStatusIssueKey) { Write-Host "WeeklyStatusIssueKey: $WeeklyStatusIssueKey" }
Write-Host ''
Write-Host 'Next step:'
Write-Host '- If you need project-specific weekly sections (for example TBS / DRS), edit the local JSON in %APPDATA% and keep it outside git.'
Write-Host '- If you want weekly report publishing into Jira, set reports.weekly.publish.enabled = true and reports.weekly.publish.jira_issue_key in the local JSON (or pass -WeeklyStatusIssueKey during setup).'
