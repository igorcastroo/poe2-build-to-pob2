@echo off
cd /d "%~dp0"
python converter.py --gui
if errorlevel 1 pause
