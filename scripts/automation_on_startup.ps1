$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$publisherScript = Join-Path $PSScriptRoot 'publish_news.ps1'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'automation_worker.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\LocalNewsAgentAutomationWorker')
$ownsMutex = $false
$topic = 'artificial intelligence, semiconductors, quantum mechanics, theoretical physics, defense engineering'

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location -LiteralPath $projectRoot

try {
    try {
        $ownsMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }

    if (-not $ownsMutex) {
        "$(Get-Date -Format o) another login automation worker is already active; exiting" | Add-Content -LiteralPath $logFile
        exit 0
    }

    $env:PUBLISH_MODE = 'AUTO'
    $env:YOUTUBE_DRAFTS_ENABLED = 'true'

    "$(Get-Date -Format o) 24/7 autonomous background daemon active" | Add-Content -LiteralPath $logFile
    "$(Get-Date -Format o) policy: X/Threads public; YouTube PRIVATE only; Budgeted Working Memory active" | Add-Content -LiteralPath $logFile

    # First, immediately drain any pending queue drafts
    & $agentExe publish-due *>> $logFile

    # Main continuous background loop: runs every 60 minutes indefinitely
    while ($true) {
        try {
            "$(Get-Date -Format o) starting automated research cycle..." | Add-Content -LiteralPath $logFile
            & $agentExe run --topic $topic *>> $logFile

            "$(Get-Date -Format o) checking and publishing verified drafts..." | Add-Content -LiteralPath $logFile
            & $agentExe publish-due *>> $logFile
        } catch {
            "$(Get-Date -Format o) cycle error: $_" | Add-Content -LiteralPath $logFile
        }

        # Sleep for 1 hour (3600 seconds) before next automated research cycle
        Start-Sleep -Seconds 3600
    }
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}

