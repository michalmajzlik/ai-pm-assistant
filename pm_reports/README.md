# PM Reports Engine

Uses `REPORT_CONTRACT.md` as source-of-truth for report structure and logic.

## Setup (once per machine/user)

1. Configure Jira context and secret:

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_context.ps1 -BaseUrl 'https://your-domain.atlassian.net' -Email 'your.name@company.com'
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_secret.ps1
```

2. Choose a local project report profile and create your local config:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -ShowProfiles
powershell -ExecutionPolicy Bypass -File .\pm_reports\setup_project_context.ps1 -Project '<project-name>' -ProjectKey '<project-key>' -DisplayName '<project-display-name>' -Profile software_delivery
```

Local project config is stored here and stays outside git:
- `%APPDATA%\AIPMAssistant\project_report_config.json`

## Default profile choices
- `software_delivery` (recommended): `Delivery`, `Scope and estimation`, `Budget`
- `multi_workstream`: two named workstreams plus shared scope/budget
- `managed_service`: `Operations`, `Delivery`, `Scope and estimation`, `Budget`

## Questions to answer during setup
A human or Claude Code should ask:
1. What is the Jira project key?
2. What project display name should appear in reports?
3. Which default profile fits best?
4. Which keywords identify each weekly status section in Jira issue summaries or release names?
5. Do you want custom daily or steering section labels, or keep the defaults?
6. Should the weekly report also overwrite a Jira project-status issue? If yes, what is its issue key?

## Fastest usage (live Jira)

Run from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType daily
powershell -ExecutionPolicy Bypass -File .\pm_reports\run_report.ps1 -ReportType weekly
```

The script loads from:
- Jira credentials: `%APPDATA%\AIPMAssistant\jira_secret.xml`
- Project report config: `%APPDATA%\AIPMAssistant\project_report_config.json`

If `reports.weekly.publish.enabled = true`, the weekly run also overwrites the configured Jira issue description via `reports.weekly.publish.jira_issue_key`.

Compatibility note:
- the runtime default is `%APPDATA%\AIPMAssistant\...`
- older local files in `%APPDATA%\SensoneoAI\...` are still auto-discovered

## Direct CLI usage

```powershell
& 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe' '.\pm_reports\report_builder.py' --report-type weekly --project '<project-display-name>' --project-key '<project-key>' --project-config '%APPDATA%\AIPMAssistant\project_report_config.json' --live-jira --output '.\outputs\reports\weekly\weekly_project_status_YYYY-MM-DD.md'
```

## Notes
- Output language is EN.
- Project-specific report layout lives in the local JSON config, not in the repository.
- `pm_reports/config_templates/` contains tracked defaults that can be copied and customized locally.
