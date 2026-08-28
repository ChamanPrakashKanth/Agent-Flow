$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$publisherScript = Join-Path $PSScriptRoot 'publish_news.ps1'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'automation_worker.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\LocalNewsAgentAutomationWorker')
$ownsMutex = $false
$topic = 'artificial intelligence, semiconductors, quantum mechanics, theoretical physics, defense engineering'

function Wait-OllamaReady {
    param([int]$Attempts = 60)
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        try {
            $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

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

    "$(Get-Date -Format o) two startup-relative cycles scheduled: +15 minutes and four hours later" | Add-Content -LiteralPath $logFile
    "$(Get-Date -Format o) policy: forked toolcaller + Chrome extension; X/Threads public; YouTube PRIVATE only" | Add-Content -LiteralPath $logFile

    Start-Sleep -Seconds 900
    for ($cycle = 1; $cycle -le 2; $cycle++) {
        try {
            "$(Get-Date -Format o) starting startup cycle $cycle of 2" | Add-Content -LiteralPath $logFile
            if (Wait-OllamaReady) {
                & $agentExe run --topic $topic *>> $logFile
                & $agentExe publish-due *>> $logFile
            } else {
                "$(Get-Date -Format o) Ollama unavailable; skipped cycle $cycle safely" | Add-Content -LiteralPath $logFile
            }
        } catch {
            "$(Get-Date -Format o) cycle $cycle error: $_" | Add-Content -LiteralPath $logFile
        }
        if ($cycle -eq 1) {
            Start-Sleep -Seconds 14400
        }
    }
    "$(Get-Date -Format o) two startup-relative cycles finished" | Add-Content -LiteralPath $logFile
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
