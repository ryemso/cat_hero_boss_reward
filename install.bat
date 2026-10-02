@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo Boss Settlement v1 - First-time install
echo ========================================
echo.

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3.11"
)
if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERROR] Python was not found.
    echo Install Python 3.11, check "Add Python to PATH", then run this file again.
    echo https://www.python.org/downloads/release/python-3119/
    echo.
    pause
    exit /b 1
)

echo [1/4] Python check...
%PY_CMD% --version
if errorlevel 1 goto :fail

echo.
echo [2/4] Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    %PY_CMD% -m venv ".venv"
    if errorlevel 1 goto :fail
) else (
    echo Existing .venv found - reusing it.
)

echo.
echo [3/4] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo [4/4] Installing packages...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto :fail

echo.
echo ========================================
echo Installation complete.
echo Double-click run.bat to start the app.
echo ========================================
pause
exit /b 0

:fail
echo.
echo ========================================
echo [ERROR] Installation failed.
echo Take a screenshot of this window and send it to ChatGPT.
echo ========================================
pause
exit /b 1
