# PM Reports Engine (v1)

Uses `REPORT_CONTRACT.md` as source-of-truth for report structure and logic.

## Fastest usage (live Jira)

```powershell
powershell -ExecutionPolicy Bypass -File .\run_report.ps1 -ReportType daily -Project RetuRO -ProjectKey RET
powershell -ExecutionPolicy Bypass -File .\run_report.ps1 -ReportType weekly -Project RetuRO -ProjectKey RET
```

The script loads Jira credentials from:
- `%APPDATA%\SensoneoAI\jira_secret.xml`

## Direct CLI usage

```powershell
& 'C:\Users\Michal\AppData\Local\Python\pythoncore-3.14-64\python.exe' 'C:\Sensoneo AI\pm_reports\report_builder.py' --report-type daily --project RetuRO --project-key RET --live-jira --output 'C:\Sensoneo AI\outputs\daily_report.md'
```

## JSON input mode (offline/test)

```powershell
& 'C:\Users\Michal\AppData\Local\Python\pythoncore-3.14-64\python.exe' 'C:\Sensoneo AI\pm_reports\report_builder.py' --report-type daily --project RetuRO --jira 'C:\Sensoneo AI\pm_reports\sample_jira.json' --output 'C:\Sensoneo AI\outputs\daily_report.md'
```

## Notes

- Output language is EN.
- Inferred statements are explicitly labeled `(Inference)`.
- Billing v1 uses `Chargeable=True` and `Actual spent` if available.
- Capacity v1 is MD-oriented and ready for Tempo integration.
