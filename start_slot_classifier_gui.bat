@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "APP=%PROJECT_ROOT%app\gui_launcher.py"
set "PYTHONW=%PROJECT_ROOT%.venv\Scripts\pythonw.exe"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%APP%" (
    echo Slot Classifier GUI not found:
    echo "%APP%"
    pause
    exit /b 1
)

pushd "%PROJECT_ROOT%" >nul

if exist "%PYTHONW%" (
    start "Slot Classifier" /D "%PROJECT_ROOT%" "%PYTHONW%" "%APP%"
    popd >nul
    exit /b 0
)

if exist "%PYTHON%" (
    start "Slot Classifier" /D "%PROJECT_ROOT%" "%PYTHON%" "%APP%"
    popd >nul
    exit /b 0
)

popd >nul
echo Python virtual environment not found.
echo Expected:
echo "%PYTHONW%"
echo.
echo Please create or copy the .venv folder before launching the GUI.
pause
exit /b 1
