@echo off
setlocal
title SI Pilot - Running (keep this window open)
color 0F
echo.
echo  ============================================================
echo    SI PILOT  -  STEP 2 of 2:  START
echo  ============================================================
echo.

set PYEXE=
where py >nul 2>&1 && set PYEXE=py -3
if "%PYEXE%"=="" ( where python >nul 2>&1 && set PYEXE=python )
if "%PYEXE%"=="" (
  color 0C
  echo  Python not found. Double-click 1-SETUP.bat first.
  echo.
  pause
  exit /b 1
)

echo  Starting...
echo.
echo  Your browser will open in a few seconds.
echo  If Windows asks about the firewall, click "Allow access".
echo.
echo  ------------------------------------------------------------
echo   KEEP THIS BLACK WINDOW OPEN while you use the site.
echo   To stop: close this window, or press Ctrl+C.
echo  ------------------------------------------------------------
echo.

start "" /b cmd /c "timeout /t 4 >nul & start http://localhost:8077"

cd /d "%~dp0"
%PYEXE% -m uvicorn app:app --port 8077 --app-dir backend

echo.
echo  Server stopped.
pause
endlocal
