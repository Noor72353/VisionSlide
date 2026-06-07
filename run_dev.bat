@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" dev_autoreload.py
if errorlevel 1 pause

# app auto running command :    .\run_dev.bat
