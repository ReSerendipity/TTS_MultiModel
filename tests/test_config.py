# -*- coding: utf-8 -*-
import os


def test_config_imports():
    from integrated_app.config import VERSION, ROOT_DIR, SAVE_DIR
    assert isinstance(VERSION, str)
    assert os.path.isabs(ROOT_DIR)
    assert "outputs" in SAVE_DIR


def test_config_models_validation():
    from integrated_app.config_models import ServerConfig, AppConfig, load_config_dict
    server = ServerConfig()
    assert server.host == "127.0.0.1"

    config = load_config_dict({})
    assert config.server.host == "127.0.0.1"


def test_config_models_invalid_workers():
    import pytest
    from pydantic import ValidationError
    from integrated_app.config_models import AppConfig, ServerConfig

    with pytest.raises(ValidationError):
        AppConfig(server=ServerConfig(workers=4))


def test_api_auth_config():
    from integrated_app.config import API_AUTH
    assert isinstance(API_AUTH, dict)
    assert "enabled" in API_AUTH
    assert "token" in API_AUTH
    assert API_AUTH["enabled"] is False
