$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentExe = Join-Path $projectRoot '.venv\Scripts\news-agent.exe'
$logDirectory = Join-Path $projectRoot 'logs'
$logFile = Join-Path $logDirectory 'autostart.log'
$automationWorker = Join-Path $PSScriptRoot 'automation_on_startup.ps1'

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
        for ($attempt = 0; $attempt -lt 15 -and -not $ollamaReady; $attempt++) {
            Start-Sleep -Seconds 2
            try {
                $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
                $ollamaReady = $true
            } catch { }
        }
    }
}

if (-not $ollamaReady) {
    "$(Get-Date -Format o) Ollama endpoint unavailable; agent will retain safe recovery behavior" | Add-Content -LiteralPath $logFile
    exit 1
}

"$(Get-Date -Format o) Ollama endpoint ready" | Add-Content -LiteralPath $logFile

# Ensure Chrome Extension Bridge is running on port 8765
$bridgeScript = Join-Path $PSScriptRoot 'start_extension_bridge.py'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bridgeRunning = $false
try {
    $client = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 8765)
    $client.Close()
    $bridgeRunning = $true
} catch { }

if (-not $bridgeRunning -and (Test-Path -LiteralPath $bridgeScript)) {
    Start-Process -FilePath $pythonExe -ArgumentList "`"$bridgeScript`"" -WindowStyle Hidden
    "$(Get-Date -Format o) started background Chrome Extension Bridge server on ws://127.0.0.1:8765" | Add-Content -LiteralPath $logFile
}

if (Test-Path -LiteralPath $automationWorker) {
    $quotedAutomationWorker = '"{0}"' -f $automationWorker
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $quotedAutomationWorker) -WindowStyle Hidden
    "$(Get-Date -Format o) started continuous autonomous background news & publishing daemon" | Add-Content -LiteralPath $logFile
} else {
    "$(Get-Date -Format o) automation worker missing: $automationWorker" | Add-Content -LiteralPath $logFile
    exit 1
}

