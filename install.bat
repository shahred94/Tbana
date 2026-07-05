@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title TBana Stream Installer

echo.
echo ==========================================
echo          TBana Stream Installer
echo ==========================================
echo Project folder: %CD%
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="

call :find_supported_python

if not defined PYTHON_EXE (
    echo [INFO] A supported Python version was not found.
    echo [INFO] TBana Stream will now download and install Python 3.13.
    echo        An internet connection is required.
    echo.

    call :download_python_installer
    if errorlevel 1 (
        echo.
        echo [FAILED] Python 3.13 could not be downloaded or verified.
        echo.
        echo Please install it manually from:
        echo https://www.python.org/downloads/release/python-31314/
        echo Then run install.bat again.
        echo.
        pause
        exit /b 1
    )

    echo [INFO] Download verified. Installing Python 3.13.14...
    start /wait "" "%TEMP%\python-3.13.14-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 SimpleInstall=1
    if errorlevel 1 (
        del /q "%TEMP%\python-3.13.14-amd64.exe" >nul 2>&1
        echo.
        echo [FAILED] Python 3.13 could not be installed automatically.
        echo Please run the downloaded installer manually or use:
        echo https://www.python.org/downloads/release/python-31314/
        echo.
        pause
        exit /b 1
    )

    del /q "%TEMP%\python-3.13.14-amd64.exe" >nul 2>&1
    call :find_supported_python
)

if not defined PYTHON_EXE (
    echo [FAILED] Python 3.13 was installed but could not be detected.
    echo.
    echo TBana Stream requires Python 3.10, 3.11, 3.12, or 3.13.
    echo Please restart Windows and run install.bat again.
    echo.
    pause
    exit /b 1
)

echo [OK] Supported Python found:
"%PYTHON_EXE%" %PYTHON_ARGS% --version
echo.

if not exist "requirements.txt" (
    set "FAILED_STEP=requirements.txt was not found in the project folder."
    goto :failed
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Removing a broken or unsupported virtual environment...
        rmdir /s /q ".venv"
        if exist ".venv" (
            set "FAILED_STEP=Could not remove the broken or unsupported .venv folder."
            goto :failed
        )
    )
)

if exist ".venv" if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Removing an incomplete virtual environment...
    rmdir /s /q ".venv"
    if exist ".venv" (
        set "FAILED_STEP=Could not remove the incomplete .venv folder."
        goto :failed
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating the private TBana Stream environment...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv ".venv"
    if errorlevel 1 (
        set "FAILED_STEP=Could not create the virtual environment."
        goto :failed
    )
) else (
    echo [1/3] Existing virtual environment found.
)

echo.
echo [2/3] Upgrading pip inside .venv...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] Pip could not be upgraded. Restoring the bundled pip and continuing...
    ".venv\Scripts\python.exe" -m ensurepip --upgrade
    if errorlevel 1 (
        set "FAILED_STEP=Could not restore pip inside .venv."
        goto :failed
    )
    ".venv\Scripts\python.exe" -m pip --version >nul 2>&1
    if errorlevel 1 (
        set "FAILED_STEP=pip is not working inside .venv."
        goto :failed
    )
)

echo.
echo [3/3] Installing TBana Stream dependencies...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (
    set "FAILED_STEP=Could not install dependencies. Check the messages above."
    goto :failed
)

echo.
echo ==========================================
echo [SUCCESS] TBana Stream is ready to use.
echo ==========================================
echo.
echo Next: Double-click start-tbana-stream.bat
echo.
pause
exit /b 0

:failed
echo.
echo ==========================================
echo [FAILED] TBana Stream installation failed.
echo ==========================================
echo Reason: %FAILED_STEP%
echo.
echo Nothing was installed globally.
echo You can fix the issue and run install.bat again.
echo.
pause
exit /b 1

:download_python_installer
set "PYTHON_DOWNLOAD_URL=https://www.python.org/ftp/python/3.13.14/python-3.13.14-amd64.exe"
set "PYTHON_INSTALLER=%TEMP%\python-3.13.14-amd64.exe"
del /q "%PYTHON_INSTALLER%" >nul 2>&1

echo [DOWNLOAD] Downloading Python 3.13.14 ^(27.9 MB^)...
where curl.exe >nul 2>&1
if errorlevel 1 goto :download_python_with_powershell

curl.exe --location --fail --progress-bar --output "%PYTHON_INSTALLER%" "%PYTHON_DOWNLOAD_URL%"
if not errorlevel 1 goto :verify_python_download

echo [INFO] curl download failed. Trying PowerShell...
del /q "%PYTHON_INSTALLER%" >nul 2>&1

:download_python_with_powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='Continue'; Invoke-WebRequest -Uri '%PYTHON_DOWNLOAD_URL%' -OutFile '%PYTHON_INSTALLER%'"
if errorlevel 1 exit /b 1

:verify_python_download
echo [VERIFY] Checking the downloaded installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$actual=(Get-FileHash -LiteralPath '%PYTHON_INSTALLER%' -Algorithm SHA256).Hash.ToLowerInvariant(); if($actual -ne 'c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0'){Write-Error 'Checksum verification failed.'; exit 1}"
if errorlevel 1 (
    del /q "%PYTHON_INSTALLER%" >nul 2>&1
    exit /b 1
)

exit /b 0

:find_supported_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

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

exit /b 0
