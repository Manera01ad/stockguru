@echo off
title StockGuru Intelligence Hub
color 0A
cd /d "%~dp0"

:: ════════════════════════════════════════════════════════════════
::  SELF-REGISTER in Windows Startup folder — runs ONCE ever
::  No admin needed. Creates a tiny launcher so StockGuru starts
::  automatically every time you log into Windows.
:: ════════════════════════════════════════════════════════════════
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\StockGuru_AutoStart.bat"
set "SELF=%~f0"

if not exist "%LAUNCHER%" (
    echo @echo off > "%LAUNCHER%"
    echo start "" "%SELF%" >> "%LAUNCHER%"
    echo.
    echo  [OK] Auto-start registered -- StockGuru will now start on every login.
    echo.
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   STOCKGURU v2.0  Intelligence Hub      ║
echo  ╚══════════════════════════════════════════╝
echo.

:: ════════════════════════════════════════════════════════════════
::  FIND PYTHON
:: ════════════════════════════════════════════════════════════════
set "PYTHON="

:: 1. Try the known pyenv version (your current install)
if exist "%USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe" (
    set "PYTHON=%USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe"
    goto :python_ok
)

:: 2. Scan all pyenv versions
for /d %%V in ("%USERPROFILE%\.pyenv\pyenv-win\versions\*") do (
    if exist "%%V\python.exe" (
        set "PYTHON=%%V\python.exe"
        goto :python_ok
    )
)

:: 3. Try standard Windows Python installs
for %%V in (Python313 Python312 Python311 Python310 Python39) do (
    if exist "%LOCALAPPDATA%\Programs\Python\%%V\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\%%V\python.exe"
        goto :python_ok
    )
)
for %%V in (Python313 Python312 Python311 Python310 Python39) do (
    if exist "C:\%%V\python.exe" (
        set "PYTHON=C:\%%V\python.exe"
        goto :python_ok
    )
)

:: 4. Last resort -- use py launcher or PATH
where py >nul 2>&1
if not errorlevel 1 ( set "PYTHON=py" & goto :python_ok )
where python >nul 2>&1
if not errorlevel 1 ( set "PYTHON=python" & goto :python_ok )

echo  [ERROR] Python not found.
echo  Please install Python 3.10+ from https://python.org
echo.
pause
exit /b 1

:python_ok
echo  Python  : %PYTHON%

:: ════════════════════════════════════════════════════════════════
::  KILL ANY STALE PROCESS ON PORT 5000
:: ════════════════════════════════════════════════════════════════
echo  Clearing port 5000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr " :5000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: ════════════════════════════════════════════════════════════════
::  WRITE BROWSER-OPENER (polls until server is ready, then opens)
:: ════════════════════════════════════════════════════════════════
> "%TEMP%\sg_open.ps1" (
    echo $url = 'http://localhost:5000'
    echo for ^($i = 0; $i -lt 60; $i++^) {
    echo     try {
    echo         $null = Invoke-WebRequest "$url/api/status" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    echo         Start-Process $url
    echo         exit
    echo     } catch { Start-Sleep 1 }
    echo }
)
start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%TEMP%\sg_open.ps1"

echo  Browser : will open automatically when server is ready
echo  Stop    : close this window
echo  ─────────────────────────────────────────
echo.

:: ════════════════════════════════════════════════════════════════
::  START FLASK SERVER (stays open — output visible here)
:: ════════════════════════════════════════════════════════════════
"%PYTHON%" app.py

echo.
echo  Server stopped. Press any key to exit.
pause >nul
