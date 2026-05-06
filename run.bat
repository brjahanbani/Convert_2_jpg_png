@echo off
setlocal

set VENV=.venv
set PYTHON=%VENV%\Scripts\python.exe
set PIP=%VENV%\Scripts\pip.exe

if not exist "%PYTHON%" (
    echo Setting up environment for the first time...
    python -m venv %VENV%
    if errorlevel 1 (
        echo ERROR: Python not found. Please install Python 3.10+ from python.org
        pause
        exit /b 1
    )
    echo Installing dependencies...
    %PIP% install --quiet customtkinter Pillow
)

start "" "%PYTHON%" main.py
