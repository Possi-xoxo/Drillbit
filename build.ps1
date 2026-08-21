$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
if (Test-Path ".\python313\python.exe") {
    $BuildPython = ".\python313\python.exe"
} else {
    if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3.13 -m venv .venv }
    $BuildPython = ".\.venv\Scripts\python.exe"
}
& $BuildPython -m pip install -r requirements.txt
& $BuildPython -m pytest
& $BuildPython -m PyInstaller --noconfirm --clean DiamondArtConverter.spec
Write-Host "Build complete: $ProjectRoot\dist\Diamond Art Converter\Diamond Art Converter.exe"
