$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exporter = Join-Path $Root "figma_tools\export_figma_board.py"
$OutputRoot = Join-Path $Root "project\output"
$ExportDir = Join-Path $Root "figma_export"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  & $VenvPython $Exporter --output-root $OutputRoot --export-dir $ExportDir
} else {
  python $Exporter --output-root $OutputRoot --export-dir $ExportDir
}
