param(
    [string]$EnvFile,
    [string]$SecretFile = "$env:APPDATA\AIPMAssistant\jira_secret.xml",
    [string]$PythonExe,
    [string]$ServerScript,
    [string]$LogFile
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $EnvFile) { $EnvFile = Join-Path $scriptRoot '.env' }
if (-not $ServerScript) { $ServerScript = Join-Path $scriptRoot 'server.py' }
if (-not $LogFile) { $LogFile = Join-Path $scriptRoot 'jira_mcp_heartbeat.log' }

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

if (-not $PythonExe) {
    $PythonExe = Resolve-Python
}

function Write-HeartbeatLog([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $Message" | Add-Content -Path $LogFile
}

function Load-EnvFile([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
        }
    }
}

function Load-Secret([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    $secret = Import-Clixml -Path $Path
    if ($null -eq $secret) { return }

    if ($secret.JIRA_BASE_URL) {
        [Environment]::SetEnvironmentVariable('JIRA_BASE_URL', [string]$secret.JIRA_BASE_URL, 'Process')
    }
    if ($secret.JIRA_EMAIL) {
        [Environment]::SetEnvironmentVariable('JIRA_EMAIL', [string]$secret.JIRA_EMAIL, 'Process')
    }
    if ($secret.JIRA_BEARER_TOKEN) {
        [Environment]::SetEnvironmentVariable('JIRA_BEARER_TOKEN', [string]$secret.JIRA_BEARER_TOKEN, 'Process')
    } elseif ($secret.JIRA_API_TOKEN) {
        [Environment]::SetEnvironmentVariable('JIRA_API_TOKEN', [string]$secret.JIRA_API_TOKEN, 'Process')
    }
}

function Get-McpProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -ieq 'python.exe' -and $_.CommandLine -like "*$ServerScript*"
        } |
        Select-Object -First 1
}

if (-not (Test-Path $ServerScript)) {
    Write-HeartbeatLog "ERROR server script not found: $ServerScript"
    exit 1
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    Write-HeartbeatLog "ERROR Python not found."
    exit 1
}

Load-EnvFile -Path $EnvFile
Load-Secret -Path $SecretFile

$existing = Get-McpProcess
if ($null -ne $existing) {
    Write-HeartbeatLog "OK already running pid=$($existing.ProcessId)"
    exit 0
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $PythonExe
$psi.Arguments = "`"$ServerScript`""
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardInput = $false
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false

[System.Diagnostics.Process]::Start($psi) | Out-Null
Start-Sleep -Milliseconds 500

$started = Get-McpProcess
if ($null -ne $started) {
    Write-HeartbeatLog "STARTED pid=$($started.ProcessId)"
    exit 0
}

Write-HeartbeatLog "ERROR failed to start process"
exit 1



