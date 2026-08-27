$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$publisherScript = Join-Path $PSScriptRoot 'publish_news.ps1'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'publisher.log'
$mutex = New-Object System.Threading.Mutex($false, 'Local\LocalNewsAgentPublishingWorker')
$ownsMutex = $false

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

try {
    try {
        $ownsMutex = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }

    if (-not $ownsMutex) {
        "$(Get-Date -Format o) another login publishing worker is already active; exiting" | Add-Content -LiteralPath $logFile
        exit 0
    }

    "$(Get-Date -Format o) login publishing cycle scheduled: attempt 1 at +15 minutes, attempt 2 four hours later" | Add-Content -LiteralPath $logFile
    Start-Sleep -Seconds 900
    & $publisherScript

    Start-Sleep -Seconds 14400
    & $publisherScript
    "$(Get-Date -Format o) two-attempt login publishing cycle finished" | Add-Content -LiteralPath $logFile
} finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
