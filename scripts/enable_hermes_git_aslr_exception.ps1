$ErrorActionPreference = 'Stop'
$gitRoot = 'C:\Users\user\AppData\Local\hermes\git'
$expectedRoot = 'C:\Users\user\AppData\Local\hermes\git'
$resolvedRoot = (Resolve-Path -LiteralPath $gitRoot).Path

if ($resolvedRoot -ne $expectedRoot) {
    throw "Refusing unexpected target: $resolvedRoot"
}

$targets = @(Get-Item -LiteralPath "$gitRoot\bin\bash.exe") +
           @(Get-Item -Path "$gitRoot\usr\bin\*.exe" -ErrorAction Stop)

foreach ($target in $targets) {
    Set-ProcessMitigation -Name $target.FullName -Disable ForceRelocateImages | Out-Null
}

$marker = 'C:\Users\user\Downloads\Agent Flow\artifacts\hermes-aslr-exception-complete.txt'
"Completed $(Get-Date -Format o); targets=$($targets.Count)" | Set-Content -LiteralPath $marker
