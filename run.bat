@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run detected. Starting installation...
    call "install.bat"
    if errorlevel 1 exit /b 1
)

echo Starting Boss Settlement v1...
echo Keep this window open while using the app.
echo.
".venv\Scripts\python.exe" -m streamlit run "app.py"

if errorlevel 1 (
    echo.
    echo [ERROR] The app stopped with an error.
    echo Take a screenshot of this window and send it to ChatGPT.
    pause
)
