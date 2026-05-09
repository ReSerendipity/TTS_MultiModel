import os
import sys

# --- 【暴力补丁：必须在最前面】 ---
# 注意：以下 SSL 相关补丁仅适用于本地离线部署场景。
# 如果项目部署在有网络访问的环境中，应移除这些补丁以确保安全性。
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['MODELSCOPE_OFFLINE'] = '1'

# 修复 OpenMP 重复加载错误 (libiomp5md.dll conflict)
# 当多个库（如 numpy、torch、funasr）各自携带 libiomp5md.dll 时会触发此错误
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

# VoxCPM2 缓存路径
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_bin_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _bin_dir)
sys.path.insert(0, _root_dir)

os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.join(_root_dir, 'cache', 'huggingface')
os.environ['MODELSCOPE_CACHE'] = os.path.join(_root_dir, 'cache', 'modelscope')
os.environ['TORCH_HOME'] = os.path.join(_root_dir, 'cache', 'torch')
os.environ['XDG_CACHE_HOME'] = os.path.join(_root_dir, 'cache')

# httpx SSL 验证：已在服务启动中通过 ssl_verify=False 处理
# 不再全局 monkey-patch httpx，保持其他模块的 SSL 安全性

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=UserWarning)
import asyncio
import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
from logging.handlers import RotatingFileHandler

log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)
file_handler = RotatingFileHandler(
    os.path.join(log_dir, "app.log"),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger("tts_multimodel")
import threading
import webbrowser
import time
import socket

def silent_exception_handler(loop, context):
    exception = context.get('exception')
    if isinstance(exception, ConnectionResetError) or (exception and "10054" in str(exception)):
        return
    loop.default_exception_handler(context)

def auto_open_browser(ip, port):
    url = f"http://{ip}:{port}"
    logger.info("正在等待引擎加载...")
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((ip, int(port))) == 0: break
            if sock.connect_ex((ip, 7860)) == 0:
                url = f"http://{ip}:7860"; break
        time.sleep(1)
    time.sleep(2)
    logger.info("服务就绪，正在弹出网页...")
    webbrowser.open(url)

def start_app():
    ip, port = "127.0.0.1", "7869"
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    wpy_path = os.path.join(_root_dir, "WPy64-312101", "python")
    sox_dir = os.path.join(bin_dir, "sox-14.4.2-win32", "sox-14.4.2")
    os.environ["PATH"] = wpy_path + os.pathsep + os.path.join(wpy_path, "Scripts") + os.pathsep + os.environ.get("PATH", "")
    if os.path.isdir(sox_dir):
        os.environ["PATH"] = sox_dir + os.pathsep + os.environ["PATH"]

    # Auto-select port if 7869 is occupied
    def _find_available_port(start_port, max_attempts=10):
        import socket
        for attempt in range(max_attempts):
            test_port = start_port + attempt
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((ip, test_port))
                    return test_port
            except OSError:
                continue
        return start_port

    actual_port = str(_find_available_port(int(port)))
    if actual_port != port:
        logger.info(f"端口 {port} 被占用，使用可用端口 {actual_port}")

    threading.Thread(target=auto_open_browser, args=(ip, actual_port), daemon=True).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(silent_exception_handler)

    import signal

    def signal_handler(sig, frame):
        logging.info("Received shutdown signal, stopping server...")
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        from integrated_app.app_server import run_server
        run_server(ip, actual_port)
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("\n按任意键退出...")

if __name__ == "__main__":
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)
    os.system("") 
    start_app()