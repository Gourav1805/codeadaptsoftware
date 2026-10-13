@echo off
setlocal
title SI Pilot - Install C++ Compiler
color 0F
echo.
echo  ============================================================
echo    INSTALLING THE C++ COMPILER
echo  ============================================================
echo.
echo  This downloads about 900 MB and then copies it to C:\mingw64
echo  It can take 5-15 minutes depending on your internet.
echo.
echo  Why C:\mingw64 and not the default location?
echo  The compiler breaks if its own folder path contains a space,
echo  and Windows usernames often do. C:\mingw64 has none.
echo.
pause
echo.

where winget >nul 2>&1
if errorlevel 1 (
  color 0C
  echo  ERROR: "winget" is not available on this PC.
  echo.
  echo  FIX: install "App Installer" from the Microsoft Store,
  echo       or download the compiler manually from
  echo       https://winlibs.com  ^(UCRT, POSIX threads, 64-bit^)
  echo       and unzip it so that this file exists:
  echo           C:\mingw64\bin\g++.exe
  echo.
  pause
  exit /b 1
)

echo  [1/2] Downloading...
winget install --id BrechtSanders.WinLibs.POSIX.UCRT --accept-source-agreements --accept-package-agreements --disable-interactivity
echo.

echo  [2/2] Copying to C:\mingw64 ...
set SRC=
for /d %%d in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs*") do set SRC=%%d\mingw64

if "%SRC%"=="" (
  color 0C
  echo  ERROR: cannot find what winget just installed.
  echo  FIX: install manually from https://winlibs.com so that
  echo       C:\mingw64\bin\g++.exe exists.
  pause
  exit /b 1
)

robocopy "%SRC%" "C:\mingw64" /E /MT:16 /NFL /NDL /NJH /NJS /NP >nul
if exist "C:\mingw64\bin\g++.exe" (
  color 0A
  echo.
  echo  DONE. Now double-click 1-SETUP.bat
) else (
  color 0C
  echo.
  echo  ERROR: the copy did not produce C:\mingw64\bin\g++.exe
  echo  FIX: you may need to right-click this file and choose
  echo       "Run as administrator".
)
echo.
pause
endlocal
