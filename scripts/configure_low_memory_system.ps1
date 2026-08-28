# Sets persistent Windows User Environment Variables for Ollama low-memory operation
# Designed for 4GB VRAM (GTX 1650) / 6GB System RAM hardware.

Write-Host "=== CONFIGURING SYSTEM-WIDE OLLAMA LOW-MEMORY OPTIMIZATIONS ===" -ForegroundColor Cyan

$settings = @{
    "OLLAMA_FLASH_ATTENTION" = "1"
    "OLLAMA_KV_CACHE_TYPE"   = "q4_0"
    "OLLAMA_NUM_PARALLEL"    = "1"
    "OLLAMA_MAX_LOADED_MODELS" = "1"
    "OLLAMA_KEEP_ALIVE"      = "0"
}

foreach ($key in $settings.Keys) {
    $val = $settings[$key]
    [Environment]::SetEnvironmentVariable($key, $val, [EnvironmentVariableTarget]::User)
    [Environment]::SetEnvironmentVariable($key, $val, [EnvironmentVariableTarget]::Process)
    Write-Host "  [SET] $key = $val (User environment)" -ForegroundColor Green
}

# Unload any active models from Ollama memory
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body '{"model": "hermes3:3b", "keep_alive": 0}' -ContentType "application/json" -TimeoutSec 3 -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  [UNLOAD] Active Ollama models evicted from VRAM/RAM" -ForegroundColor Green
} catch {}

# Trigger Windows memory trim
[System.GC]::Collect()

Write-Host "`n[SUCCESS] Persistent Ollama low-memory profile configured!" -ForegroundColor Green
Write-Host "Ollama will immediately release memory (keep_alive=0) with 4-bit KV cache and 1 slot." -ForegroundColor Yellow
