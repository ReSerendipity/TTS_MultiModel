#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI-only test server - skips model checks for UI/UX validation"""
import os
import sys

# Set environment variables
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["MODELSCOPE_OFFLINE"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"
os.environ["TTS_SKIP_MODEL_CHECK"] = "1"

# Add paths
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_bin_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _bin_dir)
sys.path.insert(0, _root_dir)

import uvicorn

# Monkey-patch model check to always return True
import integrated_app.config as config_module
config_module.check_models_available = lambda: (True, [])

print("=" * 60)
print("  TTS MultiModel - UI Test Server (No Model Loading)")
print("=" * 60)
print(f"  URL: http://127.0.0.1:7869")
print("  Press Ctrl+C to stop")
print("=" * 60)
print()

if __name__ == "__main__":
    uvicorn.run(
        "integrated_app.app_server:create_app",
        host="127.0.0.1",
        port=7869,
        factory=True,
        workers=1,
        log_level="info",
        reload=False,
    )
