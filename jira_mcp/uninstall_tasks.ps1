param(
    [string]$TaskPrefix = 'JiraMcp'
)

$taskHeartbeat = "$TaskPrefix`Heartbeat"
$startupDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$startupVbs = Join-Path $startupDir 'JiraMcpAutoStart.vbs'
$startupCmd = Join-Path $startupDir 'JiraMcpAutoStart.cmd'
$appDir = Join-Path $env:APPDATA 'AIPMAssistant'
$ensureDst = Join-Path $appDir 'ensure_jira_mcp.ps1'
$serverDst = Join-Path $appDir 'server.py'
$runVbs = Join-Path $appDir 'run_ensure_hidden.vbs'

schtasks /Delete /TN "\$taskHeartbeat" /F | Out-Null
if (Test-Path $startupVbs) { Remove-Item -Force $startupVbs }
if (Test-Path $startupCmd) { Remove-Item -Force $startupCmd }
if (Test-Path $ensureDst) { Remove-Item -Force $ensureDst }
if (Test-Path $serverDst) { Remove-Item -Force $serverDst }
if (Test-Path $runVbs) { Remove-Item -Force $runVbs }

Write-Host "Removed startup item + heartbeat task ($taskHeartbeat)."

