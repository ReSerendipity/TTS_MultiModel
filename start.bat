@echo off
chcp 65001 >nul
title TTS MultiModel

echo ============================================================
echo   TTS MultiModel
echo ============================================================
echo.

set "PYTHON=%~dp0WPy64-312101\python\python.exe"

if not exist "%PYTHON%" (
    echo Error: Python not found at WPy64-312101\python\python.exe
    pause
    exit /b 1
)

if not exist "%~dp0bin\integrated_app" (
    echo Error: Application not found at bin\integrated_app
    pause
    exit /b 1
)

echo Starting TTS MultiModel...
echo.

cd /d "%~dp0"
"%PYTHON%" bin\integrated_app\ui\app.py

if errorlevel 1 (
    echo.
    echo Application exited with error.
    pause
)
