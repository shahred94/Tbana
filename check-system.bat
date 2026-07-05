@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
title TBana Stream System Check

echo.
echo ==========================================
echo       TBana Stream System Check
echo ==========================================
echo Project folder: %CD%
echo.

set /a FAILED_CHECKS=0
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "VENV_PYTHON=.venv\Scripts\python.exe"

for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PYTHON_EXE (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_EXE=py"
            set "PYTHON_ARGS=-%%V"
        )
    )
)

for %%D in (Python313 Python312 Python311 Python310) do (
    if not defined PYTHON_EXE (
        if exist "%LocalAppData%\Programs\Python\%%D\python.exe" (
            set "PYTHON_EXE=%LocalAppData%\Programs\Python\%%D\python.exe"
        )
    )
)

if not defined PYTHON_EXE (
    python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

echo [1/5] Python
if defined PYTHON_EXE (
    "%PYTHON_EXE%" %PYTHON_ARGS% --version
    echo [PASS] A supported Python version is installed.
) else (
    echo [FAIL] Python 3.10 through 3.13 was not found.
    echo        Python 3.14 is not currently supported by pygame.
    echo        Install Python 3.13 from https://www.python.org/downloads/windows/
    set /a FAILED_CHECKS+=1
)
echo.

echo [2/5] Virtual environment
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] .venv is broken or uses an unsupported Python version.
        echo        Run install.bat to rebuild it with Python 3.10 through 3.13.
        set /a FAILED_CHECKS+=1
    ) else (
        "%VENV_PYTHON%" --version
        echo [PASS] .venv exists and uses a supported Python version.
    )
) else (
    echo [FAIL] .venv does not exist or is incomplete.
    echo        Run install.bat first.
    set /a FAILED_CHECKS+=1
)
echo.

echo [3/5] pip inside .venv
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -m pip --version
    if errorlevel 1 (
        echo [FAIL] pip is not working inside .venv.
        echo        Run install.bat again.
        set /a FAILED_CHECKS+=1
    ) else (
        echo [PASS] pip is available inside .venv.
    )
) else (
    echo [FAIL] Cannot check pip because .venv is missing.
    set /a FAILED_CHECKS+=1
)
echo.

echo [4/5] Uvicorn inside .venv
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "import uvicorn; print('Uvicorn version:', uvicorn.__version__)"
    if errorlevel 1 (
        echo [FAIL] Uvicorn is not installed inside .venv.
        echo        Run install.bat again.
        set /a FAILED_CHECKS+=1
    ) else (
        echo [PASS] Uvicorn is installed inside .venv.
    )
) else (
    echo [FAIL] Cannot check Uvicorn because .venv is missing.
    set /a FAILED_CHECKS+=1
)
echo.

echo [5/5] TBana Stream application import
if exist "%VENV_PYTHON%" (
    set "PYGAME_HIDE_SUPPORT_PROMPT=1"
    "%VENV_PYTHON%" -c "import app.main" >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] app.main could not be imported.
        echo        Run install.bat again, then repeat this check.
        set /a FAILED_CHECKS+=1
    ) else (
        echo [PASS] app.main imported successfully.
    )
) else (
    echo [FAIL] Cannot check app.main because .venv is missing.
    set /a FAILED_CHECKS+=1
)
echo.

echo ==========================================
if !FAILED_CHECKS! EQU 0 (
    echo [SUCCESS] All system checks passed.
    echo You can run start-tbana-stream.bat.
) else (
    echo [FAILED] !FAILED_CHECKS! check^(s^) failed.
    echo Follow the instructions shown above.
)
echo ==========================================
echo.
pause

if !FAILED_CHECKS! EQU 0 (
    exit /b 0
) else (
    exit /b 1
)
