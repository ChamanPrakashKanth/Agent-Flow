$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

# Configure low-memory KV cache quantization and Flash Attention for Hermes 3 Llama 3.2 3B
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q4_0'

Write-Host "=== PREPARING HERMES 3 (LLAMA 3.2 3B) WITH KV CACHE COMPRESSION ===" -ForegroundColor Cyan

# Locate Ollama executable
$ollamaExe = $null
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    $ollamaExe = $ollamaCmd.Source
} else {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        'C:\Program Files\Ollama\ollama.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) {
            $ollamaExe = $c
            break
        }
    }
}

if (-not $ollamaExe) {
    Write-Error "Ollama executable not found. Please ensure Ollama is installed."
    exit 1
}

Write-Host "[1/3] Pulling base model: hermes3:3b..." -ForegroundColor Yellow
& $ollamaExe pull hermes3:3b

Write-Host "[2/3] Building extended 64k context model for Hermes publisher from config/Modelfile.hermes..." -ForegroundColor Yellow
$modelfile = Join-Path $projectRoot "config\Modelfile.hermes"
& $ollamaExe create hermes3:3b-hermes -f $modelfile

Write-Host "[3/3] Verifying Ollama models..." -ForegroundColor Yellow
& $ollamaExe list

Write-Host "`n[SUCCESS] Hermes 3 (Llama 3.2 3B) ready with q4_0 KV cache compression and Flash Attention!" -ForegroundColor Green
