@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Boss Settlement v1 Diagnostics ===
echo Folder: %CD%
echo.
where py 2>nul
py --version 2>nul
echo.
where python 2>nul
python --version 2>nul
echo.
if exist ".venv\Scripts\python.exe" (
    echo VENV: FOUND
    ".venv\Scripts\python.exe" --version
    ".venv\Scripts\python.exe" -m pip --version
) else (
    echo VENV: NOT FOUND
)
echo.
if exist "requirements.txt" (echo requirements.txt: FOUND) else (echo requirements.txt: NOT FOUND)
if exist "app.py" (echo app.py: FOUND) else (echo app.py: NOT FOUND)
echo.
pause
