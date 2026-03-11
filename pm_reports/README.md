# PM Reports Engine (v1)

Uses `REPORT_CONTRACT.md` as source-of-truth for report structure and logic.

## Setup (once per machine/user)

1. Configure Jira context and secret:

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_context.ps1 -BaseUrl 'https://your-domain.atlassian.net' -Email 'your.name@company.com'
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_secret.ps1
```

2. Configure project context (variables used by report runner):

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -Project '<project-name>' -ProjectKey '<project-key>'
```

## Fastest usage (live Jira)

Run from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType daily
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType weekly
```

The script loads from:
- Jira context: `%APPDATA%\AIPMAssistant\jira_context.json`
- Jira credentials: `%APPDATA%\AIPMAssistant\jira_secret.xml`
- Project context: `%APPDATA%\AIPMAssistant\project_report_config.json`

## Direct CLI usage

```powershell
& 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe' '.\pm_reports\report_builder.py' --report-type daily --project '<project-name>' --project-key '<project-key>' --live-jira --output '.\outputs\daily_report.md'
```

## JSON input mode (offline/test)

```powershell
& 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe' '.\pm_reports\report_builder.py' --report-type daily --project '<project-name>' --jira '.\pm_reports\sample_jira.json' --output '.\outputs\daily_report.md'
```

## Notes

- Output language is EN.
- Inferred statements are explicitly labeled `(Inference)`.
- Billing v1 uses `Chargeable=True` and `Actual spent` if available.
- Capacity v1 is MD-oriented and ready for Tempo integration.

