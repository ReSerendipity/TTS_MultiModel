@echo off
REM Stage E quality gate: run pytest offline (matches CI gate in .github/workflows/ci.yml)
REM Run this script to reproduce the baseline metrics in docs/STAGE_E_QUALITY_REPORT.md
set TRANSFORMERS_OFFLINE=1
set HF_HUB_OFFLINE=1
set MODELSCOPE_OFFLINE=1
set CUDA_VISIBLE_DEVICES=
.\WPy64-312101\python\python.exe -m pytest tests -v --tb=short --cov=bin\integrated_app --cov-report=term-missing --cov-fail-under=20 -k "not gpu and not cuda and not vram" -m "not integration"
exit /b %ERRORLEVEL%
