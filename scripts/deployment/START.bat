@echo off
title StockGuru Intelligence Hub
color 0A
cd /d "%~dp0"

:: ════════════════════════════════════════════════════════════════
::  AUTO-INSTALLER & UPDATER
:: ════════════════════════════════════════════════════════════════
echo  [SYSTEM] Initializing StockGuru v2.0...

:: ════════════════════════════════════════════════════════════════
::  FIND PYTHON
:: ════════════════════════════════════════════════════════════════
set "PYTHON="

:: 1. Try the known pyenv version (user's install)
if exist "%USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe" (
    set "PYTHON=%USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe"
    goto :python_ok
)

:: 2. Try generic pyenv path
if exist "%USERPROFILE%\.pyenv\pyenv-win\bin\python.exe" (
    set "PYTHON=%USERPROFILE%\.pyenv\pyenv-win\bin\python.exe"
    goto :python_ok
)

:: 3. Scan all pyenv versions
for /d %%V in ("%USERPROFILE%\.pyenv\pyenv-win\versions\*") do (
    if exist "%%V\python.exe" (
        set "PYTHON=%%V\python.exe"
        goto :python_ok
    )
)

:: 4. Try standard Windows Python installs
for %%V in (Python313 Python312 Python311 Python310 Python39) do (
    if exist "%LOCALAPPDATA%\Programs\Python\%%V\python.exe" (
        set "PYTHON=%LOCALAPPDATA%\Programs\Python\%%V\python.exe"
        goto :python_ok
    )
)

:: 5. PATH fallback
where python >nul 2>&1
if not errorlevel 1 ( set "PYTHON=python" & goto :python_ok )

echo  [ERROR] Python not found.
echo  Please install Python 3.10+ and ensure it's in your PATH.
echo.
pause
exit /b 1

:python_ok
echo  [OK] Found Python: %PYTHON%

:: ════════════════════════════════════════════════════════════════
::  INSTALL REQUIREMENTS
:: ════════════════════════════════════════════════════════════════
echo  [SYSTEM] Checking dependencies...
"%PYTHON%" -m pip install -r requirements.txt --quiet --no-warn-script-location
if errorlevel 1 (
    echo  [WARNING] Dependency check failed. Trying to start anyway...
) else (
    echo  [OK] Dependencies verified.
)

:: ════════════════════════════════════════════════════════════════
::  SELF-REGISTER in Startup (only runs once)
:: ════════════════════════════════════════════════════════════════
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER_FILE=%STARTUP_DIR%\StockGuru_AutoStart.bat"
if not exist "%LAUNCHER_FILE%" (
    echo @echo off > "%LAUNCHER_FILE%"
    echo cd /d "%~dp0" >> "%LAUNCHER_FILE%"
    echo start "" "START.bat" >> "%LAUNCHER_FILE%"
    echo  [OK] Registered for Auto-Start on Boot.
)

:: ════════════════════════════════════════════════════════════════
::  CLEAR PORT 5050 (Aggressive)
:: ════════════════════════════════════════════════════════════════
echo  [SYSTEM] Clearing port 5050...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5050') do (
    echo  [KILL] Port 5050 occupied by PID %%a - Terminating...
    taskkill /PID %%a /F >nul 2>&1
)

:: ════════════════════════════════════════════════════════════════
::  BROWSER TRIGGER (PowerShell) — cache-busted URL
:: ════════════════════════════════════════════════════════════════
:: Waits for port 5050, then opens browser with ?v=<timestamp> to force fresh load
set "PS_SCRIPT=%TEMP%\sg_trigger_%RANDOM%.ps1"
> "%PS_SCRIPT%" (
    echo $ts = [int][double]::Parse^(^(Get-Date -UFormat %%s^)^)
    echo $url = "http://localhost:5050/?v=$ts"
    echo $max_retries = 60
    echo for ^($i = 0; $i -lt $max_retries; $i++^) {
    echo     try {
    echo         $tcp = New-Object System.Net.Sockets.TcpClient
    echo         $ar = $tcp.BeginConnect^('127.0.0.1', 5050, $null, $null^)
    echo         Start-Sleep -Milliseconds 500
    echo         if ^($ar.IsCompleted^) {
    echo             $tcp.EndConnect^($ar^)
    echo             $tcp.Close^(^)
    echo             Start-Process $url
    echo             exit
    echo         }
    echo         $tcp.Close^(^)
    echo     } catch { }
    echo     Start-Sleep -Seconds 1
    echo }
)
start /b powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   STOCKGURU v2.0  Intelligence Hub      ║
echo  ║   ──────────────────────────────────    ║
echo  ║   Port: 5050                            ║
echo  ║   Mode: Forest ^& Cyan Premium          ║
echo  ╚══════════════════════════════════════════╝
echo.
echo  [LOGS] Starting server...
"%PYTHON%" app.py
echo.
echo  [SYSTEM] Server stopped.
del "%PS_SCRIPT%" >nul 2>&1
pause
