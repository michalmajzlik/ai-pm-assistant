# Local Jira MCP Server

## First-time setup (new machine or first run)
Run these commands from repository root:

1. Save local Jira context (non-secret):

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_context.ps1 -BaseUrl 'https://your-domain.atlassian.net' -Email 'your.name@company.com'
```

2. Save encrypted Jira token (per Windows user):

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\setup_jira_secret.ps1
```

3. Install autostart + heartbeat and start now:

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\install_tasks.ps1 -RunNow
```

## Token and config storage
- Jira secret (encrypted, local only): `%APPDATA%\AIPMAssistant\jira_secret.xml`
- Jira context (non-secret, local only): `%APPDATA%\AIPMAssistant\jira_context.json`

## Manual run

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\run_jira_mcp.ps1
```

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\jira_mcp\uninstall_tasks.ps1
```

