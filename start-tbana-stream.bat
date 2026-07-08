@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title TBana Stream
set "PYGAME_HIDE_SUPPORT_PROMPT=1"

if exist "desktop.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("desktop.env") do (
        if not "%%A"=="" if not defined %%A set "%%A=%%B"
    )
)

echo.
echo ==========================================
echo             TBana Stream
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [FAILED] TBana Stream has not been installed yet.
    echo.
    echo Please double-click install.bat first.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [FAILED] TBana Stream's private Python environment is broken or unsupported.
    echo.
    echo Please double-click install.bat to rebuild it.
    echo.
    pause
    exit /b 1
)

echo Dashboard URL:
echo http://127.0.0.1:8000
echo.
echo Keep this window open while using TBana Stream.
echo Press Ctrl+C to stop the server.
echo.

echo Opening the dashboard automatically when the server is ready...
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/health' -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:8000/dashboard/events.html'; break } catch { Start-Sleep -Milliseconds 250 } }"

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning --no-access-log
set "SERVER_EXIT=%ERRORLEVEL%"

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo ==========================================
    echo [FAILED] TBana Stream stopped with an error.
    echo ==========================================
    echo.
    echo Review the error messages above.
    echo You may also run check-system.bat for help.
    echo.
    pause
    exit /b %SERVER_EXIT%
)

exit /b 0
