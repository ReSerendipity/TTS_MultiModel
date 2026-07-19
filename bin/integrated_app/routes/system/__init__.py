from fastapi import APIRouter

from .gpu import router as gpu_router
from .health import get_generation_stats as get_generation_stats
from .health import increment_generation as increment_generation
from .health import router as health_router
from .logs import get_operation_log as get_operation_log
from .logs import log_operation as log_operation
from .logs import router as logs_router
from .settings import router as settings_router

router = APIRouter(prefix="/api/system", tags=["system"])
router.include_router(health_router)
router.include_router(gpu_router)
router.include_router(logs_router)
router.include_router(settings_router)
