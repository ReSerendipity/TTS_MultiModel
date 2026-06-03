from fastapi import APIRouter
from .health import router as health_router
from .gpu import router as gpu_router
from .logs import router as logs_router
from .settings import router as settings_router

from .health import increment_generation, get_generation_stats
from .logs import log_operation, get_operation_log

router = APIRouter(prefix="/api/system", tags=["system"])
router.include_router(health_router)
router.include_router(gpu_router)
router.include_router(logs_router)
router.include_router(settings_router)
