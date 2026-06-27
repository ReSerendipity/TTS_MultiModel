"""Shared pytest fixtures for the TTS MultiModel test suite."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

# Keep tests offline and avoid auto-loading models during test discovery/client creation.
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TTS_AUTO_LOAD_MODEL", "0")


@pytest.fixture
def app():
    """Create the real FastAPI application with all routers discovered."""
    from integrated_app.app_server import create_app

    return create_app()


@pytest.fixture
def client(app):
    """Return a TestClient backed by the real application."""
    return TestClient(app)
