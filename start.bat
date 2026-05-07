@echo off
chcp 65001 >nul
title TTS MultiModel

echo ============================================================
echo   TTS MultiModel - AI Voice Workshop Pro
echo ============================================================
echo.

set "PYTHON=%~dp0WPy64-312101\python\python.exe"

if not exist "%PYTHON%" (
    echo Error: Python not found at WPy64-312101\python\python.exe
    pause
    exit /b 1
)

if not exist "%~dp0bin\clean_launch.py" (
    echo Error: Launch script not found at bin\clean_launch.py
    pause
    exit /b 1
)

echo Starting TTS MultiModel...
echo.

cd /d "%~dp0"
"%PYTHON%" bin\clean_launch.py

if errorlevel 1 (
    echo.
    echo Application exited with error.
    pause
)
