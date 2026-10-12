@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -B pharma_agent\launch.py
) else (
  python -B pharma_agent\launch.py
)
pause
