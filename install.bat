@echo off
chcp 65001 >nul
title TTS MultiModel - Installer

echo ============================================================
echo   TTS MultiModel - Installation Script
echo ============================================================
echo.
echo This script will:
echo   1. Check Python environment
echo   2. Install required dependencies
echo   3. Download required models
echo   4. Verify installation
echo.
echo ============================================================
echo.

cd /d "%~dp0"

:: Check if Python is available
set "PYTHON_PATH="
if exist "WPy64-312101\python\python.exe" (
    set "PYTHON_PATH=%~dp0WPy64-312101\python\python.exe"
    echo [OK] Found bundled Python: WPy64-312101
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "delims=" %%i in ('where python') do set "PYTHON_PATH=%%i"
        echo [OK] Found system Python: %PYTHON_PATH%
    ) else (
        echo [ERROR] Python not found!
        echo.
        echo Please install Python 3.12+ from https://www.python.org/downloads/
        echo Or place WinPython in WPy64-312101 folder
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo   Step 1: Installing Python Dependencies
echo ============================================================
echo.

if exist "requirements.txt" (
    echo Installing dependencies from requirements.txt...
    "%PYTHON_PATH%" -m pip install --upgrade pip
    "%PYTHON_PATH%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed successfully
) else (
    echo [WARNING] requirements.txt not found, skipping dependency installation
)

echo.
echo ============================================================
echo   Step 2: Creating Required Directories
echo ============================================================
echo.

if not exist "pretrained_models" mkdir "pretrained_models"
if not exist "personas" mkdir "personas"
if not exist "outputs" mkdir "outputs"
if not exist "cache" mkdir "cache"
if not exist "lora" mkdir "lora"
if not exist "logs" mkdir "logs"

echo [OK] Required directories created

echo.
echo ============================================================
echo   Step 3: Model Download Guide
echo ============================================================
echo.
echo IMPORTANT: You need to download the following models before using this app.
echo.
echo Models should be placed in the pretrained_models folder:
echo.
echo   1. VoxCPM2 (Main TTS model)
echo      - Place in: pretrained_models\VoxCPM2\
echo.
echo   2. SenseVoiceSmall (ASR model)
echo      - Place in: pretrained_models\SenseVoiceSmall\
echo.
echo   3. speech_zipenhancer (Audio denoiser)
echo      - Place in: pretrained_models\speech_zipenhancer\
echo.
echo Download links:
echo   - HuggingFace: https://huggingface.co
echo   - ModelScope: https://modelscope.cn
echo.
echo Or use the model download script (if available):
if exist "download_models.py" (
    echo.
    echo Running download_models.py...
    "%PYTHON_PATH%" download_models.py
) else (
    echo [INFO] No download_models.py found. Please download models manually.
)

echo.
echo ============================================================
echo   Step 4: Verification
echo ============================================================
echo.

set "ALL_MODELS_OK=1"

if exist "pretrained_models\VoxCPM2" (
    echo [OK] VoxCPM2 model found
) else (
    echo [MISSING] VoxCPM2 model not found
    set "ALL_MODELS_OK=0"
)

if exist "pretrained_models\SenseVoiceSmall" (
    echo [OK] SenseVoiceSmall model found
) else (
    echo [MISSING] SenseVoiceSmall model not found
    set "ALL_MODELS_OK=0"
)

if exist "pretrained_models\speech_zipenhancer" (
    echo [OK] speech_zipenhancer model found
) else (
    echo [MISSING] speech_zipenhancer model not found
    set "ALL_MODELS_OK=0"
)

echo.

if "%ALL_MODELS_OK%"=="1" (
    echo ============================================================
    echo   Installation Complete!
    echo ============================================================
    echo.
    echo You can now start the application by running:
    echo   start.bat
    echo.
) else (
    echo ============================================================
    echo   Installation Partially Complete
    echo ============================================================
    echo.
    echo Some models are missing. Please download them before starting.
    echo.
    echo You can still try starting by running:
    echo   start.bat
    echo.
)

echo ============================================================
echo.
pause
