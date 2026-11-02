# backend/modules/add/router.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/modules/add", tags=["Add / Fitment VLTD Module"])

@router.get("/status")
def get_add_module_status():
    return {
        "module": "add_vltd",
        "name": "Add / Fitment VLTD",
        "route": "/modules/add",
        "status": "ready"
    }

