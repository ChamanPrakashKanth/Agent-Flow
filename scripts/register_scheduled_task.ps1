$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$taskName = 'Local Ollama News Agent'
$scriptPath = Join-Path $PSScriptRoot 'start_news_agent.ps1'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Script file missing: $scriptPath"
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`"" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$description = 'Local Ollama news automation: X/Threads public and YouTube Shorts private, twice after login.'

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -User $currentUser `
    -Force | Out-Null

Write-Host "Successfully registered scheduled task '$taskName' for user '$currentUser'."
Write-Host "Trigger: AtLogOn (runs automatically when PC starts and user signs in)."
Write-Host "Automation: two startup-relative cycles (+15 minutes, then +4 hours)."
Write-Host "Destinations: X/Threads public; YouTube Shorts PRIVATE."
