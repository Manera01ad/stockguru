@echo off
:: ═══════════════════════════════════════════════════════════════
:: StockGuru — Register auto-start on Windows login
:: Run this ONCE as Administrator to set up auto-start
:: ═══════════════════════════════════════════════════════════════

set APP_DIR=%~dp0
set START_BAT=%APP_DIR%START.bat
set TASK_NAME=StockGuru_AutoStart

echo.
echo  ██████████████████████████████████████████████
echo   StockGuru Auto-Start Registration
echo  ██████████████████████████████████████████████
echo.
echo  Registering: %START_BAT%
echo  Task Name  : %TASK_NAME%
echo.

:: Remove old task if exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create new task — runs at logon for current user
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%START_BAT%\"" ^
  /sc ONLOGON ^
  /delay 0001:00 ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
    echo  ✅ SUCCESS — StockGuru will auto-start on next login
    echo.
    echo  To remove: schtasks /delete /tn %TASK_NAME% /f
) else (
    echo  ❌ FAILED — Try running this script as Administrator
)

echo.
pause
