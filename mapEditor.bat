@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: venv not found. Run:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install pygame-ce
    exit /b 1
)
.venv\Scripts\python.exe map_editor.py %*
