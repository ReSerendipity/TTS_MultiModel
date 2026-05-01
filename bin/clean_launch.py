import os
import sys

# --- 【暴力补丁：必须在最前面】 ---
# 注意：以下 SSL 相关补丁仅适用于本地离线部署场景。
# 如果项目部署在有网络访问的环境中，应移除这些补丁以确保安全性。
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['MODELSCOPE_OFFLINE'] = '1'
os.environ['PYTHONHTTPSVERIFY'] = '0'  # ⚠️ 安全风险：全局禁用 HTTPS 证书验证（仅本地离线部署时使用）

# VoxCPM2 缓存路径
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_bin_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.join(_root_dir, "faster-qwen3-tts-main")

sys.path.insert(0, _src_dir)
sys.path.insert(0, _bin_dir)
sys.path.insert(0, _root_dir)

os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.join(_root_dir, 'cache', 'huggingface')
os.environ['MODELSCOPE_CACHE'] = os.path.join(_root_dir, 'cache', 'modelscope')
os.environ['TORCH_HOME'] = os.path.join(_root_dir, 'cache', 'torch')
os.environ['XDG_CACHE_HOME'] = os.path.join(_root_dir, 'cache')

# httpx SSL 验证：已在 Gradio launch 中通过 ssl_verify=False 处理
# 不再全局 monkey-patch httpx，保持其他模块的 SSL 安全性

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=UserWarning)
import asyncio
import logging
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
    print(f"[系统] 正在等待引擎加载...")
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((ip, int(port))) == 0: break
            if sock.connect_ex((ip, 7860)) == 0:
                url = f"http://{ip}:7860"; break
        time.sleep(1)
    time.sleep(2)
    print(f"[系统] 服务就绪，正在弹出网页...")
    webbrowser.open(url)

def start_app():
    ip, port = "127.0.0.1", "7869"
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    wpy_path = os.path.join(_root_dir, "WPy64-312101", "python")
    sox_dir = os.path.join(bin_dir, "sox-14.4.2-win32", "sox-14.4.2")
    os.environ["PATH"] = wpy_path + os.pathsep + os.path.join(wpy_path, "Scripts") + os.pathsep + os.environ.get("PATH", "")
    if os.path.isdir(sox_dir):
        os.environ["PATH"] = sox_dir + os.pathsep + os.environ["PATH"]
    threading.Thread(target=auto_open_browser, args=(ip, port), daemon=True).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(silent_exception_handler)

    try:
        import integrated_app
        integrated_app.run_integrated(ip, port)
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("\n按任意键退出...")

if __name__ == "__main__":
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)
    os.system("") 
    start_app()