$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'publisher.log'

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $agentExe)) {
    "$(Get-Date -Format o) agent executable missing: $agentExe" | Add-Content -LiteralPath $logFile
    exit 1
}

"$(Get-Date -Format o) starting X/Threads publishing plus private YouTube upload" | Add-Content -LiteralPath $logFile
& $agentExe publish-due *>> $logFile
$result = $LASTEXITCODE
"$(Get-Date -Format o) publishing attempt completed with exit code $result" | Add-Content -LiteralPath $logFile
exit $result
