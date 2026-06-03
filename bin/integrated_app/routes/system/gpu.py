import time
import threading
import subprocess
from typing import List, Dict, Any, Optional

from fastapi import APIRouter

import logging
logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])


def _get_gpu_device():
    import torch
    from ...gpu_backend import GPUBackendManager, GPUBackend

    if not GPUBackendManager.is_available():
        return 0

    backend = GPUBackendManager.detect_backend()

    try:
        device = GPUBackendManager.get_device()
        if isinstance(device, torch.device):
            return device.index if device.index is not None else 0
        return device
    except Exception:
        return 0

_nvml_state = {
    "handle": None,
    "initialized": False,
    "init_time": 0.0,
    "init_failed": False,
    "last_error": None,
    "device_index": 0,
}
_nvml_lock = threading.Lock()

_NVML_CACHE_TTL = 300


def _get_nvml_handle() -> Optional[Any]:
    global _nvml_state

    with _nvml_lock:
        current_time = time.time()

        if (_nvml_state["initialized"] and
            _nvml_state["handle"] is not None and
            not _nvml_state["init_failed"]):
            if current_time - _nvml_state["init_time"] < _NVML_CACHE_TTL:
                return _nvml_state["handle"]
            else:
                logger.info("NVML handle cache expired, reinitializing...")
                _nvml_state["initialized"] = False
                _nvml_state["handle"] = None

        if _nvml_state["init_failed"]:
            last_failure_time = _nvml_state.get("failure_time", 0)
            if current_time - last_failure_time < 60:
                logger.debug(f"NVML init failed recently, skipping retry. Last error: {_nvml_state['last_error']}")
                return None
            else:
                logger.info("Retrying NVML initialization after cooldown period...")
                _nvml_state["init_failed"] = False

        try:
            import pynvml

            if not _nvml_state["initialized"]:
                try:
                    pynvml.nvmlInit()
                    logger.info("NVML library initialized successfully")
                except pynvml.NVMLError_LibraryNotLoaded:
                    logger.debug("NVML already initialized")
                except Exception as init_err:
                    logger.warning(f"NVML library initialization failed: {init_err}")
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
                logger.info(f"Successfully obtained NVML handle for GPU #{device_idx}")
            except Exception as handle_err:
                logger.warning(f"Failed to get NVML handle for GPU #{device_idx}: {handle_err}")
                if device_idx != 0:
                    try:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        _nvml_state["handle"] = handle
                        _nvml_state["device_index"] = 0
                        logger.info("Successfully obtained NVML handle for GPU #0 as fallback")
                    except Exception as fallback_err:
                        logger.warning(f"Failed to get NVML handle for GPU #0 fallback: {fallback_err}")
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
            logger.warning("pynvml not installed, GPU monitoring unavailable")
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = "pynvml not installed"
            return None
        except Exception as e:
            logger.error(f"Unexpected error during NVML initialization: {e}", exc_info=True)
            _nvml_state["init_failed"] = True
            _nvml_state["failure_time"] = current_time
            _nvml_state["last_error"] = str(e)
            return None


def _get_gpu_utilization_from_nvml() -> Optional[int]:
    try:
        handle = _get_nvml_handle()
        if handle is None:
            logger.debug("NVML handle not available for GPU utilization")
            return None

        import pynvml
        util_rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
        gpu_util = int(util_rates.gpu)
        logger.debug(f"GPU utilization from NVML: {gpu_util}%")
        return gpu_util

    except Exception as e:
        logger.warning(f"Failed to get GPU utilization from NVML: {e}")
        return None


def _get_gpu_utilization_from_nvidia_smi() -> Optional[int]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        if result.returncode == 0 and result.stdout.strip():
            util_value = int(result.stdout.strip().split("\n")[0].strip())
            logger.debug(f"GPU utilization from nvidia-smi: {util_value}%")
            return util_value

        logger.debug(f"nvidia-smi returned empty or error output: {result.stderr}")
        return None

    except FileNotFoundError:
        logger.debug("nvidia-smi not found in PATH")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("nvidia-smi command timed out")
        return None
    except Exception as e:
        logger.warning(f"Failed to get GPU utilization from nvidia-smi: {e}")
        return None


def _get_gpu_utilization() -> int:
    from ...gpu_backend import GPUBackendManager, GPUBackend

    backend = GPUBackendManager.detect_backend()

    if backend == GPUBackend.CUDA:
        nvml_util = _get_gpu_utilization_from_nvml()
        if nvml_util is not None:
            return nvml_util

        smi_util = _get_gpu_utilization_from_nvidia_smi()
        if smi_util is not None:
            return smi_util

    return 0
