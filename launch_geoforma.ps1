param([string]$Project = '', [string]$Python = '', [switch]$Recover)
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $manifest = Join-Path $env:USERPROFILE '.conda\environments.txt'
    if (Test-Path -LiteralPath $manifest) {
        $environment = Get-Content -LiteralPath $manifest | Where-Object {
            (Split-Path -Leaf $_) -eq 'GeoForma' -and (Test-Path -LiteralPath (Join-Path $_ 'pythonw.exe'))
        } | Select-Object -First 1
        if ($environment) { $Python = Join-Path $environment 'pythonw.exe' }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'GeoForma Python environment not found. Run main.py in PyCharm, or pass -Python with the environment interpreter path.'
}
$entry = Join-Path $PSScriptRoot 'main.py'
$launchArgs = '"' + $entry + '"'
if ($Project) { $launchArgs += ' "' + $Project + '"' }
if ($Recover) { $launchArgs += ' --recover' }
# This is the interactive desktop application, so its main window must be visible.
Start-Process -FilePath $Python -ArgumentList $launchArgs -WorkingDirectory $PSScriptRoot -WindowStyle Normal
