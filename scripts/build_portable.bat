@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv (py -3.12 -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
pyinstaller packaging\eRegistry.spec --noconfirm --clean
echo.
echo Portable build created in dist\eRegistry\
endlocal

