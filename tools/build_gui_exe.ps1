$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$Entry = Join-Path $ProjectRoot "app\gui_launcher.py"
$Dist = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot "build\pyinstaller"
$Work = Join-Path $BuildRoot "work"
$SpecPath = Join-Path $BuildRoot "spec"

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUSERBASE = Join-Path $BuildRoot "pyuserbase"
New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE, $SpecPath | Out-Null

if (!(Test-Path $Python)) {
    throw "Python venv not found: $Python"
}

if (!(Test-Path $PyInstaller)) {
    & $Python -m pip install pyinstaller
}

& $PyInstaller `
    --noconfirm `
    --windowed `
    --name "SlotClassifier" `
    --distpath $Dist `
    --workpath $Work `
    --specpath $SpecPath `
    --paths (Join-Path $ProjectRoot "app") `
    --add-data "$(Join-Path $ProjectRoot 'app');app" `
    $Entry

Write-Host "Built:" (Join-Path $Dist "SlotClassifier\SlotClassifier.exe")
