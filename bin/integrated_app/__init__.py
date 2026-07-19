"""TTS MultiModel 集成应用包"""


def run_integrated(ip, port):
    """启动集成应用（延迟导入，避免启动时加载所有依赖）"""
    from .app_server import run_server

    return run_server(ip, port)


__all__ = ["run_integrated"]
