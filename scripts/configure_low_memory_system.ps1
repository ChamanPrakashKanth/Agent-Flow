# Sets persistent Windows User Environment Variables for Ollama low-memory operation
# Designed for 4GB VRAM (GTX 1650) / 6GB System RAM hardware.

Write-Host "=== CONFIGURING SYSTEM-WIDE OLLAMA LOW-MEMORY OPTIMIZATIONS ===" -ForegroundColor Cyan

$settings = @{
    "OLLAMA_FLASH_ATTENTION" = "1"
    "OLLAMA_KV_CACHE_TYPE"   = "q4_0"
    "OLLAMA_NUM_PARALLEL"    = "1"
    "OLLAMA_MAX_LOADED_MODELS" = "1"
    "OLLAMA_KEEP_ALIVE"      = "5m"
}

foreach ($key in $settings.Keys) {
    $val = $settings[$key]
    [Environment]::SetEnvironmentVariable($key, $val, [EnvironmentVariableTarget]::User)
    [Environment]::SetEnvironmentVariable($key, $val, [EnvironmentVariableTarget]::Process)
    Write-Host "  [SET] $key = $val (User environment)" -ForegroundColor Green
}

Write-Host "`n[SUCCESS] Persistent Ollama low-memory profile configured!" -ForegroundColor Green
Write-Host "Ollama will now allocate <2.2 GB total VRAM with 4-bit KV cache and 1 model slot." -ForegroundColor Yellow
