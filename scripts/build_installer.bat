@echo off
setlocal
cd /d "%~dp0\.."
call scripts\build_portable.bat
where iscc >nul 2>nul
if errorlevel 1 (
  echo Inno Setup Compiler ^(iscc.exe^) was not found in PATH.
  echo Install Inno Setup 6 and add its compiler directory to PATH.
  exit /b 1
)
iscc packaging\eRegistry.iss
echo Installer created in dist\installer\
endlocal

