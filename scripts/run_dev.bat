@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv (py -3.12 -m venv .venv)
call .venv\Scripts\activate.bat
pip install -r requirements.txt
python -m eregistry
endlocal

