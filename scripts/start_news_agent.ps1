$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'autostart.log'
$automationWorker = Join-Path $PSScriptRoot 'automation_on_startup.ps1'

# Hermes requires a 64K context. Quantized KV cache keeps the local Hermes 3 (Llama 3.2 3B)
# publishing model within this PC's memory budget.
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q4_0'

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $agentExe)) {
    "$(Get-Date -Format o) agent executable missing: $agentExe" | Add-Content -LiteralPath $logFile
    exit 1
}

"$(Get-Date -Format o) starting local Ollama news agent" | Add-Content -LiteralPath $logFile

$ollamaReady = $false
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
    $ollamaReady = $true
} catch {
    $ollamaExe = $null
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCommand) {
        $ollamaExe = $ollamaCommand.Source
    } else {
        $candidates = @(
            "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
            'C:\Users\user\AppData\Local\Programs\Ollama\ollama.exe',
            'C:\Program Files\Ollama\ollama.exe'
        )
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate) {
                $ollamaExe = $candidate
                break
            }
        }
    }
    if ($ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
        "$(Get-Date -Format o) requested Ollama server startup with q4_0 KV cache" | Add-Content -LiteralPath $logFile
    }
}

if ($ollamaReady) {
    "$(Get-Date -Format o) Ollama endpoint ready" | Add-Content -LiteralPath $logFile
} else {
    "$(Get-Date -Format o) Ollama is starting; worker will recheck after the startup delay" | Add-Content -LiteralPath $logFile
}

if (Test-Path -LiteralPath $automationWorker) {
    $quotedAutomationWorker = '"{0}"' -f $automationWorker
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $quotedAutomationWorker) -WindowStyle Hidden
    "$(Get-Date -Format o) started two-cycle Hermes Computer Use worker using the signed-in Chrome profile" | Add-Content -LiteralPath $logFile
} else {
    "$(Get-Date -Format o) automation worker missing: $automationWorker" | Add-Content -LiteralPath $logFile
    exit 1
}
exit 0
