param(
    [string]$ModelPath = "",
    [string]$Topic = "AI, quantum mechanics, defence systems, theoretical physics",
    [string]$Browser = "extension",
    [switch]$Publish = $true,
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$serverExe = Join-Path $projectRoot "tools\llama.cpp\llama-server.exe"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

# 1. Check if llama-server is already running on the target port
$serverReady = $false
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    $serverReady = $true
} catch {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 2 -ErrorAction SilentlyContinue
        $serverReady = $true
    } catch { }
}

if (-not $serverReady) {
    if (-not $ModelPath) {
        # Check if any .gguf exists in models/ or tools/
        $found = Get-ChildItem -Path $projectRoot -Filter *.gguf -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $ModelPath = $found.FullName
        }
    }

    if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath)) {
        Write-Error "llama-server is not running on port $Port and no valid -ModelPath was provided.`nUsage: .\scripts\start_qwen_agent.ps1 -ModelPath 'C:\path\to\qwen2.5-coder-3b.gguf'"
        exit 1
    }

    Write-Host "[1/3] Starting llama-server on port $Port with $ModelPath..." -ForegroundColor Cyan
    Start-Process -FilePath $serverExe -ArgumentList @("-m", "`"$ModelPath`"", "-c", "2048", "--port", "$Port", "--threads", "4") -WindowStyle Minimized

    # Wait up to 30s for server to become responsive
    $attempts = 0
    while (-not $serverReady -and $attempts -lt 30) {
        Start-Sleep -Seconds 1
        $attempts++
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -TimeoutSec 1 -ErrorAction SilentlyContinue
            $serverReady = $true
        } catch { }
    }

    if (-not $serverReady) {
        Write-Error "llama-server failed to respond within 30 seconds."
        exit 1
    }
}

Write-Host "[2/3] llama.cpp server is ready on http://127.0.0.1:$Port" -ForegroundColor Green

# 2. If browser mode is extension, ensure bridge relay is running
if ($Browser -eq "extension") {
    $bridgeReady = $false
    try {
        $bridgeReady = Test-NetConnection -ComputerName '127.0.0.1' -Port 8765 -InformationLevel Quiet -WarningAction SilentlyContinue
    } catch { }
    if (-not $bridgeReady) {
        Write-Host "[*] Starting Chrome extension bridge on port 8765..." -ForegroundColor Yellow
        $bridgeScript = Join-Path $projectRoot "scripts\start_extension_bridge.py"
        Start-Process -FilePath $pythonExe -ArgumentList @("`"$bridgeScript`"") -WindowStyle Minimized
        Start-Sleep -Seconds 2
    }
}

# 3. Run Qwen Autonomous Agent Harness
Write-Host "[3/3] Launching Qwen Autonomous Harness (Topic: '$Topic')..." -ForegroundColor Cyan
$cmdArgs = @("qwen-run", "--browser", $Browser, "--topic", $Topic)
if ($Publish) { $cmdArgs += "--publish" }
& $pythonExe -m local_news_agent.cli @cmdArgs
