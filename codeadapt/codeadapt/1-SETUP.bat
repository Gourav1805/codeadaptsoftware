@echo off
setlocal
title SI Pilot - Setup Check
color 0F
echo.
echo  ============================================================
echo    SI PILOT  -  STEP 1 of 2:  SETUP CHECK
echo  ============================================================
echo.
echo  This checks your computer has what it needs. It changes
echo  nothing except installing 3 small Python packages.
echo.

set FAIL=0

REM ---------------------------------------------------------------- Python
echo  [1/4] Looking for Python...
set PYEXE=
where py >nul 2>&1 && set PYEXE=py -3
if "%PYEXE%"=="" ( where python >nul 2>&1 && set PYEXE=python )

if "%PYEXE%"=="" (
  echo        NOT FOUND.
  echo.
  echo        FIX: Install Python from  https://www.python.org/downloads/
  echo             IMPORTANT: on the first screen of the installer, TICK
  echo             the box that says "Add python.exe to PATH".
  echo             Then close this window and run 1-SETUP again.
  set FAIL=1
  goto :done
)

for /f "tokens=2" %%v in ('%PYEXE% --version 2^>^&1') do set PYVER=%%v
echo        Found Python %PYVER%
%PYEXE% -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo        TOO OLD. This needs Python 3.10 or newer.
  echo        FIX: install the latest from https://www.python.org/downloads/
  set FAIL=1
  goto :done
)

REM ------------------------------------------------------------- Packages
echo.
echo  [2/4] Installing the 3 Python packages it needs...
echo        (this may take a minute the first time)
%PYEXE% -m pip install --quiet --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo        FAILED. You are probably offline, or behind a firewall.
  echo        FIX: connect to the internet and run 1-SETUP again.
  set FAIL=1
  goto :done
)
echo        Done.

REM ------------------------------------------------------------- Compiler
echo.
echo  [3/4] Looking for the C++ compiler...
set GXX=
if exist "C:\mingw64\bin\g++.exe" set GXX=C:\mingw64\bin\g++.exe

if "%GXX%"=="" (
  echo        NOT FOUND at C:\mingw64
  echo.
  echo        FIX: double-click  INSTALL-COMPILER.bat  in this folder,
  echo             wait for it to finish, then run 1-SETUP again.
  set FAIL=1
  goto :done
)
echo        Found C:\mingw64\bin\g++.exe

REM -------------------------------------------------------- Real compile
echo.
echo  [4/4] Testing that it can actually build and run a program...
%PYEXE% "%~dp0check_setup.py"
if errorlevel 1 (
  set FAIL=1
  goto :done
)

:done
echo.
echo  ============================================================
if "%FAIL%"=="1" (
  color 0C
  echo    SETUP INCOMPLETE  -  fix the item marked FIX above,
  echo    then double-click 1-SETUP.bat again.
) else (
  color 0A
  echo    ALL GOOD.  Now double-click  2-START.bat
)
echo  ============================================================
echo.
pause
endlocal
