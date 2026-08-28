$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'autostart.log'
$automationWorker = Join-Path $PSScriptRoot 'automation_on_startup.ps1'
$extensionRelay = Join-Path $PSScriptRoot 'start_extension_bridge.py'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'

# Low-memory Ollama optimization profile for 4GB VRAM (GTX 1650) / 6GB RAM
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q4_0'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_KEEP_ALIVE = '0'

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

# The extension lives in the user's normal Chrome profile. Start that profile
# minimized when Chrome is not already running; never create an isolated profile.
if (-not (Get-Process -Name chrome -ErrorAction SilentlyContinue)) {
    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chromeExe = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($chromeExe) {
        Start-Process -FilePath $chromeExe -ArgumentList @('--start-minimized', 'about:blank') -WindowStyle Minimized
        "$(Get-Date -Format o) started existing Chrome profile minimized for extension access" | Add-Content -LiteralPath $logFile
        Start-Sleep -Seconds 3
    }
}

# The forked publishing case uses the user's authenticated extension directly,
# so no Hermes model or 64K browser-agent context is allocated.
$bridgeReady = $false
try {
    $bridgeReady = Test-NetConnection -ComputerName '127.0.0.1' -Port 8765 -InformationLevel Quiet -WarningAction SilentlyContinue
} catch { }
if (-not $bridgeReady -and (Test-Path -LiteralPath $pythonExe) -and (Test-Path -LiteralPath $extensionRelay)) {
    $quotedExtensionRelay = '"{0}"' -f $extensionRelay
    Start-Process -FilePath $pythonExe -ArgumentList @($quotedExtensionRelay) -WorkingDirectory $projectRoot -WindowStyle Hidden
    "$(Get-Date -Format o) started authenticated Chrome extension relay" | Add-Content -LiteralPath $logFile
}

if (Test-Path -LiteralPath $automationWorker) {
    $quotedAutomationWorker = '"{0}"' -f $automationWorker
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $quotedAutomationWorker) -WindowStyle Hidden
    "$(Get-Date -Format o) started two-cycle extension worker using the signed-in Chrome profile" | Add-Content -LiteralPath $logFile
} else {
    "$(Get-Date -Format o) automation worker missing: $automationWorker" | Add-Content -LiteralPath $logFile
    exit 1
}
exit 0
