#!/bin/bash

# Job Scraper Agent Setup Script
echo "Setting up Job Scraper Agent..."

# Check if Python 3.12 is available
if [ ! -f "/opt/homebrew/bin/python3.12" ]; then
    echo "Error: Python 3.12 is not installed. Please install it with: brew install python@3.12"
    exit 1
fi

echo "Using Python 3.12:"
/opt/homebrew/bin/python3.12 --version

# Create virtual environment with Python 3.12
echo "Creating virtual environment with Python 3.12..."
/opt/homebrew/bin/python3.12 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install Playwright browsers (required for browser-use)
echo "Installing Playwright browsers..."
playwright install chromium

echo "Setup complete! To activate the virtual environment, run:"
echo "source venv/bin/activate"
