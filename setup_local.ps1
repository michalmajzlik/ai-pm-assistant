param(
    [string]$PythonExe,
    [switch]$SkipPythonInstall,
    [switch]$SkipPipInstall
)

$ErrorActionPreference = 'Stop'

function Resolve-Python {
    param([string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return $ExplicitPath
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source -and (Test-Path $pythonCmd.Source)) {
        return $pythonCmd.Source
    }

    return $null
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Resolve-Python -ExplicitPath $PythonExe

if (-not $python -and -not $SkipPythonInstall) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host 'Python not found. Installing Python 3.12 via winget...'
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements | Out-Host
        $python = Resolve-Python -ExplicitPath $PythonExe
    }
}

if (-not $python) {
    throw 'Python was not found. Install Python 3.10+ or rerun with -PythonExe <path>.'
}

Write-Host "Using Python: $python"
& $python --version

if (-not $SkipPipInstall) {
    $requirementsPath = Join-Path $repoRoot 'requirements.txt'
    if (Test-Path $requirementsPath) {
        Write-Host 'Installing Python dependencies from requirements.txt...'
        & $python -m pip install --upgrade pip
        & $python -m pip install -r $requirementsPath
    }
}

$dirsToEnsure = @(
    (Join-Path $repoRoot 'outputs'),
    (Join-Path $repoRoot 'Meetings\VTT'),
    (Join-Path $repoRoot 'Meetings\summaries'),
    (Join-Path $repoRoot 'Meetings\processed'),
    (Join-Path $repoRoot 'Meetings\failed'),
    (Join-Path $repoRoot 'Meetings\run_reports')
)

foreach ($dir in $dirsToEnsure) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Write-Host ''
Write-Host 'Local bootstrap completed.'
Write-Host 'Next steps:'
Write-Host "1) Jira secret: powershell -ExecutionPolicy Bypass -File '$repoRoot\jira_mcp\setup_jira_secret.ps1' -BaseUrl 'https://sensoneosk.atlassian.net' -Email '<your-email>'"
Write-Host "2) Jira MCP autostart: powershell -ExecutionPolicy Bypass -File '$repoRoot\jira_mcp\install_tasks.ps1' -RunNow"
Write-Host "3) Daily report: powershell -ExecutionPolicy Bypass -File '$repoRoot\pm_reports\run_report.ps1' -ReportType daily -Project RetuRO -ProjectKey RET"
Write-Host "4) Meetings (optional): setx OPENAI_API_KEY '<your-key>'"
