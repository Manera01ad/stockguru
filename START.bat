@echo off
title StockGuru
color 0A

cd /d "%~dp0"

echo.
echo  STOCKGURU v2.0 - Starting...
echo.

:: Use the exact Python path from pyenv (most reliable - no PATH issues)
set "PYTHON=%USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe"

if not exist "%PYTHON%" (
    :: Fallback: try PATH-based python
    set "PYTHON=python"
    python --version >nul 2>&1
    if errorlevel 1 (
        set "PYTHON=py"
        py --version >nul 2>&1
        if errorlevel 1 (
            echo.
            echo  ERROR: Python not found.
            echo  Looked at: %USERPROFILE%\.pyenv\pyenv-win\versions\3.10.11\python.exe
            echo.
            pause
            exit /b 1
        )
    )
)

:: Kill any stale process on port 5000
echo  Clearing port 5000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Write browser-open script to temp file (avoids quote hell)
echo for($i=1;$i-le50;$i++){Start-Sleep -Milliseconds 800;try{$r=Invoke-WebRequest -Uri 'http://localhost:5000/api/status' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop;if($r.StatusCode -eq 200){Start-Process 'http://localhost:5000';exit}}catch{}} > "%TEMP%\sg_open.ps1"

:: Start browser-opener in background (hidden, no window)
start /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%TEMP%\sg_open.ps1"

echo  Server starting... browser will open automatically.
echo  Dashboard: http://localhost:5000
echo  Close this window to stop the server.
echo.
echo  ------------------------------------------------

:: Run server HERE (errors visible in this window)
"%PYTHON%" app.py

echo.
echo  Server stopped.
pause
