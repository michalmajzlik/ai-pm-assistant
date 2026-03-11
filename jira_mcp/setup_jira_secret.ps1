param(
    [string]$BaseUrl,
    [string]$Email,
    [switch]$UseBearer,
    [string]$SecretFile = "$env:APPDATA\AIPMAssistant\jira_secret.xml",
    [string]$ConfigFile = "$env:APPDATA\AIPMAssistant\jira_context.json"
)

$ErrorActionPreference = 'Stop'

if ((-not $BaseUrl -or -not $Email) -and (Test-Path $ConfigFile)) {
    $cfg = Get-Content $ConfigFile -Raw | ConvertFrom-Json
    if (-not $BaseUrl -and $cfg.BaseUrl) { $BaseUrl = [string]$cfg.BaseUrl }
    if (-not $Email -and $cfg.Email) { $Email = [string]$cfg.Email }
}

if (-not $BaseUrl -or -not $Email) {
    throw "Missing BaseUrl/Email. Run setup_jira_context.ps1 first or pass -BaseUrl and -Email."
}

$dir = Split-Path -Parent $SecretFile
if (-not (Test-Path $dir)) {
    New-Item -Path $dir -ItemType Directory -Force | Out-Null
}

if ($UseBearer) {
    $secure = Read-Host "Enter JIRA_BEARER_TOKEN" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Bearer token cannot be empty."
    }

    [pscustomobject]@{
        JIRA_BASE_URL     = $BaseUrl
        JIRA_EMAIL        = $Email
        JIRA_BEARER_TOKEN = $token
        JIRA_API_TOKEN    = ""
    } | Export-Clixml -Path $SecretFile -Force
} else {
    $secure = Read-Host "Enter JIRA_API_TOKEN" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }

    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "API token cannot be empty."
    }

    [pscustomobject]@{
        JIRA_BASE_URL     = $BaseUrl
        JIRA_EMAIL        = $Email
        JIRA_BEARER_TOKEN = ""
        JIRA_API_TOKEN    = $token
    } | Export-Clixml -Path $SecretFile -Force
}

Write-Host "Saved encrypted Jira credentials to: $SecretFile"
Write-Host "Next run: powershell -ExecutionPolicy Bypass -File '.\\jira_mcp\\run_jira_mcp.ps1'"

