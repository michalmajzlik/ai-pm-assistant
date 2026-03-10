# ai-pm-assistant
AI toolkit for IT Project Managers that creates a personal project intelligence assistant.

It aggregates data from Jira, meetings, emails, and calendars to automate reporting, generate summaries, prepare management presentations, and track project progress.

## Quick Start (New PC, Windows)
Run in PowerShell from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_local.ps1
```

This script:
- detects Python 3.10+ (or installs Python 3.12 via winget),
- installs Python dependencies from `requirements.txt`,
- creates local working folders used by the meetings/reporting pipelines.

## Jira Setup (required for live Jira features)

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_secret.ps1 -BaseUrl 'https://sensoneosk.atlassian.net' -Email '<your-email>'
powershell -ExecutionPolicy Bypass -File .\jira_mcp\install_tasks.ps1 -RunNow
```

Notes:
- Jira secret is stored per Windows user in `%APPDATA%\SensoneoAI\jira_secret.xml`.
- Scheduled tasks are local OS objects, so they must be installed on each machine.

## Main Usage

Generate daily report:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType daily -Project RetuRO -ProjectKey RET
```

Generate weekly report:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType weekly -Project RetuRO -ProjectKey RET
```

Process meeting transcripts (optional):

```powershell
setx OPENAI_API_KEY '<your-key>'
# open a new terminal
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\Meetings\process_meeting.py
```

## Troubleshooting
- If `-File .\jira_mcp\...` says file not found, first run `cd <repo-root>`.
- If Python is not found, rerun bootstrap with explicit path:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_local.ps1 -PythonExe 'C:\Path\To\python.exe'
```
