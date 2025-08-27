@echo off
echo Setting up Job Scraper Agent...

REM Check if Python 3.11+ is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python 3 is not installed. Please install Python 3.11 or higher.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Current Python version: %PYTHON_VERSION%
REM This is a basic check - you may need to manually verify it's 3.11+

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Install Playwright browsers (required for browser-use)
echo Installing Playwright browsers...
playwright install chromium

echo Setup complete! To activate the virtual environment, run:
echo venv\Scripts\activate.bat
pause
