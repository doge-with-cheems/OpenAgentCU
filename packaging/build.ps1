# Build OpenAgentCU portable folder, installer and portable zip.
# Usage: powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/4 icon =="
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "make_icon.ps1")

Write-Host "== 2/4 PyInstaller =="
python -m PyInstaller (Join-Path $PSScriptRoot "OpenAgentCU.spec") `
    --noconfirm --clean --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "== 3/4 Inno Setup =="
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) { throw "ISCC.exe not found; install Inno Setup 6 first" }
& $iscc (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Copy-Item (Join-Path $PSScriptRoot "install.bat") (Join-Path $root "dist\installer\install.bat") -Force

Write-Host "== 4/4 portable zip =="
$zip = Join-Path $root "dist\OpenAgentCU-2.0.1-portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $root "dist\OpenAgentCU\*") -DestinationPath $zip -CompressionLevel Optimal
Copy-Item (Join-Path $PSScriptRoot "README-install.txt") (Join-Path $root "dist\安装说明.txt") -Force

Write-Host ""
Write-Host "portable : dist\OpenAgentCU\OpenAgentCU.exe"
Write-Host "setup    : dist\installer\OpenAgentCU-2.0.1-Setup.exe"
Write-Host "zip      : dist\OpenAgentCU-2.0.1-portable.zip"
