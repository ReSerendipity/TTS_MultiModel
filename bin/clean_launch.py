import os
import sys

# --- 【暴力补丁：必须在最前面】 ---
# 注意：以下 SSL 相关补丁仅适用于本地离线部署场景。
# 如果项目部署在有网络访问的环境中，应移除这些补丁以确保安全性。
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["MODELSCOPE_OFFLINE"] = "1"

# 修复 OpenMP 重复加载错误 (libiomp5md.dll conflict)
# 当多个库（如 numpy、torch、funasr）各自携带 libiomp5md.dll 时会触发此错误
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

# VoxCPM2 缓存路径
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_bin_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _bin_dir)
sys.path.insert(0, _root_dir)

_config_yaml_path = os.path.join(_root_dir, "config.yaml")
if os.path.exists(_config_yaml_path):
    try:
        import yaml

        with open(_config_yaml_path, encoding="utf-8") as _f:
            _cfg = yaml.safe_load(_f)
        if _cfg and _cfg.get("server", {}).get("auto_load_model", False):
            os.environ["TTS_AUTO_LOAD_MODEL"] = "1"
    except Exception:
        pass

os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(_root_dir, "cache", "huggingface")
os.environ["MODELSCOPE_CACHE"] = os.path.join(_root_dir, "cache", "modelscope")
os.environ["TORCH_HOME"] = os.path.join(_root_dir, "cache", "torch")
os.environ["XDG_CACHE_HOME"] = os.path.join(_root_dir, "cache")

# httpx SSL 验证：已在服务启动中通过 ssl_verify=False 处理
# 不再全局 monkey-patch httpx，保持其他模块的 SSL 安全性

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=UserWarning)
import asyncio
import atexit
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
from logging.handlers import RotatingFileHandler

# Add file handler only if not already present (avoid duplicates with app_server.setup_logging)
root_logger = logging.getLogger()
if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    root_logger.addHandler(file_handler)

logger = logging.getLogger("tts_multimodel")
import threading
import webbrowser
import time
import socket
import subprocess


def silent_exception_handler(loop, context):
    exception = context.get("exception")
    if isinstance(exception, ConnectionResetError) or (exception and "10054" in str(exception)):
        return
    loop.default_exception_handler(context)


def auto_open_browser(ip, port, timeout=300):
    url = f"http://{ip}:{port}"
    logger.info("正在等待引擎加载...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((ip, int(port))) == 0:
                break
        time.sleep(1)
    else:
        logger.warning(f"等待引擎加载超时（{timeout}秒），未打开浏览器")
        return
    time.sleep(2)
    logger.info("服务就绪，正在弹出网页...")
    webbrowser.open(url)


def _kill_port_occupant(port, ip="127.0.0.1"):
    """Kill any process listening on the specified port (Windows only)."""
    try:
        import psutil

        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    if proc.pid != os.getpid():
                        logger.info(f"端口 {port} 被进程 {conn.pid} ({proc.name()}) 占用，正在终止...")
                        proc.kill()
                        proc.wait(timeout=5)
                        logger.info(f"已终止进程 {conn.pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        time.sleep(1)
    except ImportError:
        # Fallback: use netstat + taskkill
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    if pid != os.getpid():
                        logger.info(f"端口 {port} 被进程 {pid} 占用，正在终止...")
                        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5)
            time.sleep(1)
        except Exception:
            pass


def start_app():
    ip, port = "127.0.0.1", "7869"
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    wpy_path = os.path.join(_root_dir, "WPy64-312101", "python")
    sox_dir = os.path.join(bin_dir, "sox-14.4.2-win32", "sox-14.4.2")
    os.environ["PATH"] = (
        wpy_path + os.pathsep + os.path.join(wpy_path, "Scripts") + os.pathsep + os.environ.get("PATH", "")
    )
    if os.path.isdir(sox_dir):
        os.environ["PATH"] = sox_dir + os.pathsep + os.environ["PATH"]

    # Kill any leftover process on the target port before selecting
    _kill_port_occupant(int(port), ip)

    # Auto-select port if 7869 is occupied
    def _find_available_port(start_port, max_attempts=10):
        for attempt in range(max_attempts):
            test_port = start_port + attempt
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    # connect_ex returns 0 if connection succeeds (port occupied)
                    if s.connect_ex((ip, test_port)) == 0:
                        logger.debug(f"端口 {test_port} 被占用，尝试下一个")
                        continue  # port is occupied, try next
                    # Port appears free, verify by binding
                    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        s2.bind((ip, test_port))
                        s2.close()
                        logger.info(f"选中可用端口 {test_port}")
                        return test_port
                    except OSError:
                        s2.close()
                        logger.debug(f"端口 {test_port} bind 失败，尝试下一个")
                        continue
            except OSError:
                continue
        logger.warning(f"未找到可用端口，回退到 {start_port}")
        return start_port

    actual_port = str(_find_available_port(int(port)))
    if actual_port != port:
        logger.info(f"端口 {port} 被占用，使用可用端口 {actual_port}")

    _port_file = os.path.join(_root_dir, ".server_port")

    # Clean up port file on exit
    def _cleanup_port_file():
        try:
            if os.path.exists(_port_file):
                os.remove(_port_file)
        except Exception:
            pass

    atexit.register(_cleanup_port_file)

    # Write port file atomically (write to temp file, then rename)
    try:
        _tmp_port_file = _port_file + ".tmp"
        with open(_tmp_port_file, "w", encoding="utf-8") as pf:
            pf.write(actual_port)
        if os.path.exists(_port_file):
            os.remove(_port_file)
        os.rename(_tmp_port_file, _port_file)
    except Exception:
        # Fallback to direct write if rename fails
        try:
            with open(_port_file, "w", encoding="utf-8") as pf:
                pf.write(actual_port)
        except Exception:
            pass

    # --- Pre-flight model integrity check ---
    sys.path.insert(0, os.path.join(_root_dir, "bin"))
    from integrated_app.config import check_models_available, get_download_hints

    models_ok, missing = check_models_available()
    if not models_ok:
        print()
        print("=" * 60)
        print("  ERROR: Model files incomplete or missing")
        print("=" * 60)
        print()
        for item in missing:
            print(f"  - {item}")
        print()
        hints = get_download_hints()
        for engine, hint in hints.items():
            print(f"[{engine}]")
            for line in hint.splitlines():
                print(f"  {line}")
            print()
        print("=" * 60)
        print("  Please download the models, then restart the application.")
        print("=" * 60)
        print()
        input("Press Enter to exit...")
        sys.exit(1)

    threading.Thread(target=auto_open_browser, args=(ip, actual_port), daemon=True).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(silent_exception_handler)

    import signal

    def signal_handler(sig, frame):
        logging.info("Received shutdown signal, stopping server...")
        # Use sys.exit instead of os._exit to allow atexit handlers to run
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        from integrated_app.app_server import run_server

        run_server(ip, actual_port)
    except Exception:
        import traceback

        traceback.print_exc()
        input("\n按任意键退出...")


if __name__ == "__main__":
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    os.system("")
    start_app()
