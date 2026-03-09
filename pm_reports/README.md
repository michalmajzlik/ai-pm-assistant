# PM Reports Engine (v1)

Uses `REPORT_CONTRACT.md` as source-of-truth for report structure and logic.

## First run

```powershell
& 'C:\Users\Michal\AppData\Local\Python\pythoncore-3.14-64\python.exe' 'C:\Sensoneo AI\pm_reports\report_builder.py' --report-type daily --project RetuRO --jira 'C:\Sensoneo AI\pm_reports\sample_jira.json' --output 'C:\Sensoneo AI\outputs\daily_report.md'
```

## Inputs

- `--jira`: JSON with optional keys:
  - `issues` (array of issue objects)
  - `releases` (array of release objects)
- `--meetings`: JSON
- `--calendar`: JSON
- `--emails`: JSON

## Notes

- Output language is EN.
- Inferred statements are explicitly labeled `(Inference)`.
- Billing v1 uses `chargeable=true` and `actual_spent`.
- Capacity v1 is MD-oriented and ready for Tempo integration.
