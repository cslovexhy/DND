@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Make sure Python is installed and on your PATH.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    .venv\Scripts\pip install pygame-ce
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo Setup complete.
)

.venv\Scripts\python.exe -m game.main %*
if errorlevel 1 (
    echo.
    echo Game exited with an error. See above for details.
    pause
)
