@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python venv not found:
    echo %PYTHON%
    pause
    exit /b 1
)

if "%~1"=="" (
    "%PYTHON%" "%~dp0app\main.py"
) else (
    set "FIRST=%~1"
    if "!FIRST:~0,2!"=="--" (
        "%PYTHON%" "%~dp0app\main.py" %*
    ) else (
        "%PYTHON%" "%~dp0app\main.py" --video-id "%~1"
    )
)

echo.
echo Done. Outputs are in project\output
pause
