import logging
import threading
from collections import deque
from datetime import datetime

from fastapi import APIRouter

logger = logging.getLogger("tts_multimodel")

router = APIRouter(tags=["system"])


class OperationLog:
    def __init__(self, maxlen=200):
        self._logs: deque = deque(maxlen=maxlen)
        self._lock = threading.RLock()
        self._counter = 0

    def add(self, operation_type: str, message: str, details: dict = None):
        with self._lock:
            self._counter += 1
            entry = {
                "id": self._counter,
                "timestamp": datetime.now().isoformat(),
                "type": operation_type,
                "message": message,
                "details": details or {},
            }
            self._logs.appendleft(entry)

    def get_latest(self, limit=50, filter_type=None):
        with self._lock:
            logs = list(self._logs)
            if filter_type and filter_type != "all":
                logs = [log for log in logs if log["type"] == filter_type]
            return logs[:limit]


_operation_log = OperationLog()


def get_operation_log() -> OperationLog:
    return _operation_log


def log_operation(operation_type: str, message: str, details: dict = None):
    _operation_log.add(operation_type, message, details)


@router.get("/logs", summary="系统日志", description="获取最近的系统日志")
def get_logs(limit: int = 50, filter_type: str = "all"):
    valid_types = {"all", "generation", "model", "config"}
    if filter_type not in valid_types:
        filter_type = "all"

    logs = _operation_log.get_latest(limit=limit, filter_type=filter_type)
    return {"logs": logs, "total": len(logs)}
