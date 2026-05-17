# -*- coding: utf-8 -*-
import os
import sys
import pytest
from unittest.mock import MagicMock

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


def _install_route_mocks():
    mock_router = MagicMock()
    mock_modules = {}
    route_names = [
        "integrated_app.routes.pages",
        "integrated_app.routes.tabs",
        "integrated_app.routes.audio",
        "integrated_app.routes.generate",
        "integrated_app.routes.persona",
        "integrated_app.routes.sse",
        "integrated_app.routes.system",
        "integrated_app.routes.training",
    ]
    for name in route_names:
        mod = MagicMock()
        mod.router = mock_router
        sys.modules[name] = mod
        mock_modules[name] = mod

    model_mod = MagicMock()
    model_mod.router = mock_router
    model_mod.switch_router = mock_router
    sys.modules["integrated_app.routes.model"] = model_mod
    mock_modules["integrated_app.routes.model"] = model_mod

    return mock_modules


def _remove_route_mocks(mock_modules):
    for name in list(mock_modules.keys()):
        if name in sys.modules and sys.modules[name] is mock_modules[name]:
            del sys.modules[name]


def _patch_add_event_handler():
    from fastapi import FastAPI
    if not hasattr(FastAPI, "add_event_handler"):
        def _add_event_handler(self, event_type, func):
            pass
        FastAPI.add_event_handler = _add_event_handler


@pytest.fixture
def app():
    _patch_add_event_handler()
    mock_modules = _install_route_mocks()
    try:
        from integrated_app.app_server import create_app
        application = create_app()
    finally:
        _remove_route_mocks(mock_modules)
    return application


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient
    return TestClient(app)
