# backend/modules/delete/router.py
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from core.session_manager import session_manager
from .service import (
    delete_service,
    DeleteSelectRequest,
    DeleteSelectResponse,
    DeleteOpenModalResponse,
    DeleteConfirmRequest,
    DeleteConfirmResponse,
    DeleteBatchRequest,
    DeleteBatchResponse
)
from .automation import delete_automation, UNLOCK_PORTAL_URL

router = APIRouter(prefix="/api/modules/delete", tags=["Delete / Unlock VLTD Module"])

@router.get("/status")
def get_delete_module_status():
    """Returns portal session info and readiness for delete operations."""
    info = session_manager.get_session_info()
    return {
        "module": "delete_vltd",
        "name": "Delete / Unlock VLTD",
        "portal_url": UNLOCK_PORTAL_URL,
        "session": info,
        "is_ready": info.get("is_authenticated", False)
    }

@router.post("/navigate")
def navigate_to_unlock_portal():
    """
    Explicitly redirects the active browser session to the official Unlock VLTD portal URL:
    https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/unlocksldandcomponents.xhtml
    """
    try:
        ok, msg = delete_automation.ensure_delete_view()
        return {"success": ok, "message": msg, "target_url": UNLOCK_PORTAL_URL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/registrations", response_model=List[str])
@router.get("/options", response_model=List[str])
def get_portal_registrations():
    """
    Extracts currently available vehicle registration numbers from the portal
    dropdown (select#reg_input / label#reg_label).
    """
    try:
        registrations = delete_service.get_available_registrations()
        return registrations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract registrations: {str(e)}")

@router.post("/select", response_model=DeleteSelectResponse)
def select_portal_registration(payload: DeleteSelectRequest):
    """
    Selects a vehicle registration number from dropdown and verifies that
    the 'Release VLTD From Vehicle' div and button 'j_idt112' appear.
    """
    try:
        res = delete_service.select_registration(payload.registration_number)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration selection failed: {str(e)}")

@router.post("/open-modal", response_model=DeleteOpenModalResponse)
def open_unlock_reason_modal():
    """
    Clicks the first 'Unlock VLTD' button (field id 'j_idt112') and waits for
    the reason modal containing 'Inputreject' and 'j_idt122'.
    """
    try:
        res = delete_service.open_reason_modal()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open unlock modal: {str(e)}")

@router.post("/confirm-unlock", response_model=DeleteConfirmResponse)
@router.post("/confirm", response_model=DeleteConfirmResponse)
def confirm_and_submit_unlock(payload: DeleteConfirmRequest):
    """
    Populates reason into 'Inputreject' and clicks the final confirmation button 'j_idt122'.
    Returns authoritative execution result.
    """
    try:
        res = delete_service.confirm_and_unlock(payload.registration_number, payload.reason)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unlock execution failed: {str(e)}")

@router.post("/batch-unlock", response_model=DeleteBatchResponse)
@router.post("/batch", response_model=DeleteBatchResponse)
def execute_batch_unlock(payload: DeleteBatchRequest):
    """
    Executes sequential untag/unlock on a batch of vehicle registration numbers.
    """
    try:
        res = delete_service.execute_batch_unlock(payload.registrations, payload.default_reason)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch unlock failed: {str(e)}")

