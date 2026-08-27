$ErrorActionPreference = 'Stop'
$chromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (-not (Test-Path -LiteralPath $chromePath)) {
    $chromePath = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
}
if (-not (Test-Path -LiteralPath $chromePath)) {
    throw 'Google Chrome was not found.'
}

Write-Host 'Opening X and Threads in your normal Chrome profile.' -ForegroundColor Cyan
Start-Process -FilePath $chromePath -ArgumentList 'https://x.com/ChamanKant44703'
Start-Process -FilePath $chromePath -ArgumentList 'https://www.threads.com/@chamanprakashkanth'
Write-Host 'Confirm both accounts are signed in. The extension uses this existing Chrome session.' -ForegroundColor Green
