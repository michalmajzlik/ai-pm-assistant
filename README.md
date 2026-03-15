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
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_context.ps1 -BaseUrl 'https://your-domain.atlassian.net' -Email 'your.name@company.com'
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_secret.ps1
powershell -ExecutionPolicy Bypass -File .\jira_mcp\install_tasks.ps1 -RunNow
```

Notes:
- Jira context (non-secret) is stored per Windows user in `%APPDATA%\AIPMAssistant\jira_context.json`.
- Jira secret is stored per Windows user in `%APPDATA%\AIPMAssistant\jira_secret.xml`.
- Scheduled tasks are local OS objects, so they must be installed on each machine.

## Project Report Setup (required for reports)

1. Review built-in profile choices:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -ShowProfiles
```

2. Create your local project report config:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -Project '<project-name>' -ProjectKey '<project-key>' -DisplayName '<project-display-name>' -Profile software_delivery
```

Your local project config is stored here and is intentionally kept outside git:
- `%APPDATA%\AIPMAssistant\project_report_config.json`

## Default report profiles
- `software_delivery` (recommended default): `Delivery`, `Scope and estimation`, `Budget`
- `multi_workstream`: two named workstreams plus shared scope/budget
- `managed_service`: `Operations`, `Delivery`, `Scope and estimation`, `Budget`

## Setup questions a human or Claude Code should ask
1. What is the Jira project key?
2. What display name should appear in reports?
3. Which default report profile fits best?
4. Which weekly status sections should be renamed or customized?
5. Which Jira issue/release keywords identify each weekly section?
6. Do you want to keep default daily and steering section labels, or rename them?
7. Should weekly report output also overwrite a Jira project-status issue? If yes, what is the issue key?

## Main Usage

Generate daily report:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType daily
```

Generate weekly report:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType weekly
```

If your local project config has `reports.weekly.publish.enabled = true` and a `jira_issue_key`, the same command will also overwrite that Jira issue description with the generated weekly report.

Compatibility note:
- the repo now uses the neutral runtime directory `%APPDATA%\AIPMAssistant\...`
- if you already have older local files in `%APPDATA%\SensoneoAI\...`, the scripts auto-discover and continue using them

Generated reports are written to the local `outputs\reports\` folders in the repository.

Process meeting transcripts (optional):

```powershell
setx OPENAI_API_KEY '<your-key>'
# open a new terminal
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\Meetings\process_meeting.py
```

## Troubleshooting
- If `-File .\jira_mcp\...` says file not found, first run `cd <repo-root>`.
- If report run fails with missing project context, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -ShowProfiles
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -Project '<project-name>' -ProjectKey '<project-key>' -DisplayName '<project-display-name>' -Profile software_delivery
```
- If Python is not found, rerun bootstrap with explicit path:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_local.ps1 -PythonExe 'C:\Path\To\python.exe'
```
