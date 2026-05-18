$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Checker = Join-Path $Root "check_environment.py"
python $Checker
