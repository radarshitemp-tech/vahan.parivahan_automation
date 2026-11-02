# backend/modules/untag/router.py
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException

from core.session_manager import session_manager
from .service import (
    replace_service,
    ReplaceOptionSelectRequest,
    ReplaceOptionSelectResponse,
    ReplaceInspectResponse,
    ReplaceSingleExecuteRequest,
    ReplaceSingleExecuteResponse,
    ReplaceBatchRequest,
    ReplaceBatchResponse
)
from .automation import replace_automation, REPLACE_PORTAL_URL

router = APIRouter(prefix="/api/modules/untag", tags=["Replace VLTD Module"])
alias_router = APIRouter(prefix="/api/modules/replace", tags=["Replace VLTD Module Alias"])

@router.get("/status")
@alias_router.get("/status")
def get_replace_module_status():
    """Returns status and session info for Replace Device / Change ICCID module."""
    info = session_manager.get_session_info()
    return {
        "module": "replace_vltd",
        "name": "Replace Device / Change ICCID",
        "portal_url": REPLACE_PORTAL_URL,
        "session": info,
        "is_ready": info.get("is_authenticated", False)
    }

@router.get("/options")
@alias_router.get("/options")
def get_replace_options():
    """Returns available replacement options (S, D, I)."""
    return replace_service.get_options()

@router.post("/navigate")
@alias_router.post("/navigate")
def navigate_to_replace_portal():
    """Navigates active browser session to the SLD Fitting / Replacement portal URL."""
    try:
        ok, msg = replace_automation.ensure_replace_view()
        return {"success": ok, "message": msg, "target_url": REPLACE_PORTAL_URL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/select-option", response_model=ReplaceOptionSelectResponse)
@alias_router.post("/select-option", response_model=ReplaceOptionSelectResponse)
def select_portal_option(payload: ReplaceOptionSelectRequest):
    """
    Selects option in field 'select_optn' (S, D, or I) on portal and triggers
    PrimeFaces AJAX to reveal fitment fields.
    """
    try:
        res = replace_service.select_option(payload.option_key)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Option selection failed: {str(e)}")

@router.get("/inspect", response_model=ReplaceInspectResponse)
@alias_router.get("/inspect", response_model=ReplaceInspectResponse)
def inspect_portal_fields():
    """Inspects revealed form fields on the portal."""
    try:
        return replace_service.inspect_form()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to inspect fields: {str(e)}")

@router.post("/execute-single", response_model=ReplaceSingleExecuteResponse)
@alias_router.post("/execute-single", response_model=ReplaceSingleExecuteResponse)
def execute_single_replace(payload: ReplaceSingleExecuteRequest):
    """Executes fitment data entry and submission for a single record."""
    try:
        return replace_service.execute_single(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fitment execution failed: {str(e)}")

@router.post("/batch", response_model=ReplaceBatchResponse)
@alias_router.post("/batch", response_model=ReplaceBatchResponse)
def execute_batch_replace(payload: ReplaceBatchRequest):
    """Executes replacement/change workflow for a batch of records."""
    try:
        return replace_service.execute_batch(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch execution failed: {str(e)}")

