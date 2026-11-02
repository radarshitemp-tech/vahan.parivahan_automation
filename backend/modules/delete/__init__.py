# backend/modules/delete/__init__.py
from .router import router as delete_router
from .service import delete_service
from .automation import delete_automation

__all__ = ["delete_router", "delete_service", "delete_automation"]

