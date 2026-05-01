# -*- coding: utf-8 -*-
"""TTS MultiModel 集成应用包"""


def run_integrated(ip, port):
    """启动集成应用（延迟导入，避免启动时加载所有依赖）"""
    from .ui.app import run_integrated as _run_integrated
    return _run_integrated(ip, port)


__all__ = ["run_integrated"]
