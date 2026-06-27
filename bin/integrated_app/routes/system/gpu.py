import logging
import subprocess
import threading
import time
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])


def _get_gpu_device():
    import torch

    from ...gpu_backend import GPUBackendManager

    if not GPUBackendManager.is_available():
        return 0

    try:
        device = GPUBackendManager.get_device()
        if isinstance(device, torch.device):
            return device.index if device.index is not None else 0
        return device
    except Exception:
        return 0


_nvml_state: dict[str, Any] = {
    "handle": None,
    "initialized": False,
    "init_time": 0.0,
    "init_failed": False,
    "last_error": None,
    "device_index": 0,
}
_nvml_lock = threading.Lock()

_NVML_CACHE_TTL = 300


def _get_nvml_handle() -> Any | None:
    global _nvml_state

    with _nvml_lock:
        current_time = time.time()

        if _nvml_state["initialized"] and _nvml_state["handle"] is not None and not _nvml_state["init_failed"]:
            if current_time - _nvml_state["init_time"] < _NVML_CACHE_TTL:
                return _nvml_state["handle"]
            else:
                logger.info("NVML 句柄缓存已过期，正在重新初始化...")
                _nvml_state["initialized"] = False
                _nvml_state["handle"] = None

        if _nvml_state["init_failed"]:
            last_failure_time = _nvml_state.get("failure_time", 0)
            if current_time - last_failure_time < 60:
                logger.debug(f"NVML 最近初始化失败，跳过重试。上次错误: {_nvml_state['last_error']}")
                return None
            else:
                logger.info("冷却期后重试 NVML 初始化...")
                _nvml_state["init_failed"] = False

        try:
            import pynvml

            if not _nvml_state["initialized"]:
                try:
                    pynvml.nvmlInit()
                    logger.info("NVML 库初始化成功")
                except pynvml.NVMLError_LibraryNotLoaded:
                    logger.debug("NVML 已初始化")
                except Exception as init_err:
                    logger.warning(f"NVML 库初始化失败: {init_err}")
                    _nvml_state["init_failed"] = True
                    _nvml_state["failure_time"] = current_time
                    _nvml_state["last_error"] = str(init_err)
                    return None

                _nvml_state["initialized"] = True
                _nvml_state["init_time"] = current_time

            device_idx = _get_gpu_device()
            _nvml_state["device_index"] = device_idx

            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(device_idx)
                _nvml_state["handle"] = handle
                logger.info(f"成功获取 GPU #{device_idx} 的 NVML 句柄")
            except Exception as handle_err:
                logger.warning(f"获取 GPU #{device_idx} 的 NVML 句柄失败: {handle_err}")
                if device_idx != 0:
                    try:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        _nvml_state["handle"] = handle
                        _nvml_state["device_index"] = 0
                        logger.info("已成功获取 GPU #0 的 NVML 句柄作为回退")
                    except Exception as fallback_err:
                        logger.warning(f"获取 GPU #0 回退 NVML 句柄失败: {fallback_err}")
                        _nvml_state["init_failed"] = True
                        _nvml_state["failure_time"] = current_time
                        _nvml_state["last_error"] = str(fallback_err)
                        return None
                else:
                    _nvml_state["init_failed"] = True
                    _nvml_state["failure_time"] = current_time
                    _nvml_state["last_error"] = str(handle_err)
                    return None

            return _nvml_state["handle"]

        except ImportError:
            logger.warning("未安装 pynvml，GPU 监控不可用")
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = "pynvml not installed"
            return None
        except Exception as e:
            logger.error(f"NVML 初始化期间发生意外错误: {e}", exc_info=True)
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = str(e)
            return None


def _get_gpu_utilization_from_nvml() -> int | None:
    try:
        handle = _get_nvml_handle()
        if handle is None:
            logger.debug("NVML 句柄不可用，无法获取 GPU 利用率")
            return None

        import pynvml

        util_rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        gpu_util = int(util_rates.gpu)
        logger.debug(f"NVML 获取的 GPU 利用率: {gpu_util}%")
        return gpu_util

    except Exception as e:
        logger.warning(f"从 NVML 获取 GPU 利用率失败: {e}")
        return None


def _get_gpu_utilization_from_nvidia_smi() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            util_value = int(result.stdout.strip().split("\n")[0].strip())
            logger.debug(f"nvidia-smi 获取的 GPU 利用率: {util_value}%")
            return util_value

        logger.debug(f"nvidia-smi 返回空输出或错误: {result.stderr}")
        return None

    except FileNotFoundError:
        logger.debug("nvidia-smi 未在 PATH 中找到")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi 命令超时")
        return None
    except Exception as e:
        logger.warning(f"从 nvidia-smi 获取 GPU 利用率失败: {e}")
        return None


def _get_gpu_utilization() -> int:
    from ...gpu_backend import GPUBackend, GPUBackendManager

    backend = GPUBackendManager.detect_backend()

    if backend == GPUBackend.CUDA:
        nvml_util = _get_gpu_utilization_from_nvml()
        if nvml_util is not None:
            return nvml_util

        smi_util = _get_gpu_utilization_from_nvidia_smi()
        if smi_util is not None:
            return smi_util

    return 0
