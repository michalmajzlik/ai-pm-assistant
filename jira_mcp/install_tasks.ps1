param(
    [string]$TaskPrefix = 'JiraMcp',
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ensureSrc = Join-Path $root 'ensure_jira_mcp.ps1'
$serverSrc = Join-Path $root 'server.py'
if (-not (Test-Path $ensureSrc)) { throw "Missing $ensureSrc" }
if (-not (Test-Path $serverSrc)) { throw "Missing $serverSrc" }

$appDir = Join-Path $env:APPDATA 'AIPMAssistant'
$ensureDst = Join-Path $appDir 'ensure_jira_mcp.ps1'
$serverDst = Join-Path $appDir 'server.py'
$startupDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$startupVbs = Join-Path $startupDir 'JiraMcpAutoStart.vbs'
$startupCmd = Join-Path $startupDir 'JiraMcpAutoStart.cmd'
$taskHeartbeat = "$TaskPrefix`Heartbeat"

if (-not (Test-Path $appDir)) { New-Item -ItemType Directory -Path $appDir -Force | Out-Null }
Copy-Item -Path $ensureSrc -Destination $ensureDst -Force
Copy-Item -Path $serverSrc -Destination $serverDst -Force

# No console flash on login: run hidden via WScript
$startupVbsText = @(
  'Set objShell = CreateObject("WScript.Shell")',
  ('objShell.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{0}""", 0, False' -f $ensureDst)
) -join "`r`n"
Set-Content -Encoding ASCII -Path $startupVbs -Value $startupVbsText
if (Test-Path $startupCmd) { Remove-Item -Force $startupCmd }

$runVbs = Join-Path $appDir 'run_ensure_hidden.vbs'
$runVbsText = @(
  'Set objShell = CreateObject("WScript.Shell")',
  ('objShell.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{0}""", 0, False' -f $ensureDst)
) -join "`r`n"
Set-Content -Encoding ASCII -Path $runVbs -Value $runVbsText

$tr = 'wscript.exe {0}' -f $runVbs
schtasks /Delete /TN "\$taskHeartbeat" /F | Out-Null
schtasks /Create /TN "\$taskHeartbeat" /TR $tr /SC MINUTE /MO 1 /F | Out-Null

# Add task description/comment
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$task = $folder.GetTask($taskHeartbeat)
$def = $task.Definition
$def.RegistrationInfo.Description = 'Jira MCP heartbeat: checks every minute and starts local Jira MCP server if not running.'
$null = $folder.RegisterTaskDefinition($taskHeartbeat, $def, 6, $null, $null, 3, $null)

if ($RunNow) {
    wscript.exe $runVbs
}

Write-Host "Installed autostart startup item: $startupVbs"
Write-Host "Installed heartbeat task: $taskHeartbeat"
Write-Host "AppData runtime dir: $appDir"

