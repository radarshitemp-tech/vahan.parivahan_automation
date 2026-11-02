import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware

from models import (
    BatchState,
    BatchResponse,
    BatchSummary,
    PortalInventory,
    RecordStatus,
    BatchMappingConfig,
    DryRunResult,
    ExecutionLogEntry
)
from validator import parse_and_validate_csv
from selenium_worker import VahanSeleniumWorker
from logger_service import execution_logger, get_root_log_content, ROOT_LOG_FILE
from modules.registry import module_registry
from modules.delete import delete_router
from modules.add import add_router
from core.browser_manager import browser_manager
from core.session_manager import session_manager

app = FastAPI(title="VAHAN VLTD Bulk Automation API", version="2.0.0")

# Mount Modular Routers
app.include_router(delete_router)
app.include_router(add_router)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "http://127.0.0.1:5173", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BATCH_STORE: Dict[str, BatchResponse] = {}
selenium_worker = VahanSeleniumWorker()

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "VAHAN VLTD Automation Backend", "version": "2.0.0"}

@app.get("/api/modules")
def list_available_modules():
    """Returns all enabled automation modules from the central registry."""
    return module_registry.list_enabled()

@app.get("/api/session")
def get_browser_session_status():
    """Returns active Chrome browser and authentication status."""
    return session_manager.get_session_info()

@app.post("/api/browser/close")
def close_browser_session():
    """Closes the current browser session gracefully."""
    browser_manager.close_browser()
    selenium_worker.driver = None
    return {"message": "Browser session closed successfully."}

@app.post("/api/vahan/batches", response_model=BatchResponse)
async def upload_and_validate_batch(
    file: UploadFile = File(...),
    module_type: str = "add_vltd"
):
    """
    Accepts multipart CSV upload, validates schema and constraints strictly preserving
    leading zeros and data integrity, stores batch, and returns preview and validation errors.
    Supports any file name or link providing CSV data without restricting to strict .csv extension.
    Supports modular validation based on module_type ('add_vltd' or 'delete_vltd').
    """
    try:
        content_bytes = await file.read()
        try:
            csv_text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            csv_text = content_bytes.decode("latin-1", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV content: {str(e)}")

    try:
        records, validation_errors, headers = parse_and_validate_csv(csv_text, module_type=module_type)
    except ValueError as val_err:
        raise HTTPException(status_code=422, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV processing failed: {str(e)}")

    valid_count = sum(1 for r in records if r.status == RecordStatus.READY)
    invalid_count = sum(1 for r in records if r.status == RecordStatus.INVALID)

    state = BatchState.READY_FOR_REVIEW if valid_count > 0 else BatchState.COMPLETED_WITH_ERRORS

    summary = BatchSummary(
        total_records=len(records),
        valid_records_count=valid_count,
        invalid_records_count=invalid_count,
        successful_count=0,
        failed_count=0,
        skipped_count=0,
        unresolved_count=0,
        current_record_index=0,
        current_stage="Validation Complete",
        current_error_message=f"{invalid_count} row(s) contain validation errors." if invalid_count > 0 else None
    )

    batch_id = str(uuid.uuid4())
    fields = selenium_worker.latest_inventory.fields if selenium_worker.latest_inventory else []
    custom_cols = headers if headers else (list(records[0].raw_data.keys()) if (records and records[0].raw_data) else None)
    initial_mapping = selenium_worker.generate_suggested_mapping(batch_id, fields, custom_columns=custom_cols)

    safe_file_name = file.filename if file.filename else "dataset.csv"

    batch_response = BatchResponse(
        batch_id=batch_id,
        file_name=safe_file_name,
        module_type=module_type,
        state=state,
        summary=summary,
        records=records,
        errors=validation_errors,
        mapping=initial_mapping,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    BATCH_STORE[batch_id] = batch_response
    return batch_response

@app.get("/api/vahan/batches/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: str):
    """Retrieves batch details, real-time status, progress metrics, and recent logs."""
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")
    batch = BATCH_STORE[batch_id]
    batch.logs = execution_logger.get_logs(batch_id, limit=50)
    return batch

@app.post("/api/vahan/portal/inspect", response_model=PortalInventory)
def launch_portal_and_inspect():
    """
    Phase B: Opens visible Chrome browser to VAHAN VLTD portal.
    Checks whether login is needed or form is already rendered.
    """
    try:
        inventory = selenium_worker.launch_browser_for_authentication()
        return inventory
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vahan/portal/confirm-login", response_model=PortalInventory)
def confirm_login_and_inspect():
    """
    Phase B: User clicks this after completing manual login/CAPTCHA in Chrome.
    Inspects rendered SLD fitting form and returns discovered field inventory.
    """
    try:
        inventory = selenium_worker.confirm_and_inspect_form()
        return inventory
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/vahan/batches/{batch_id}/mapping", response_model=BatchMappingConfig)
def get_or_generate_mapping(batch_id: str):
    """
    Phase C: Retrieves current mapping or generates a suggested mapping from discovered fields.
    Preserves all existing mappings and never overwrites complete mappings with partial scans.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]
    if batch.mapping and batch.mapping.is_complete:
        return batch.mapping

    fields = selenium_worker.latest_inventory.fields if selenium_worker.latest_inventory else []
    custom_cols = list(batch.records[0].raw_data.keys()) if (batch.records and batch.records[0].raw_data) else None
    suggested = selenium_worker.generate_suggested_mapping(batch_id, fields, custom_columns=custom_cols)

    # Preserve any existing user-configured or previously mapped fields
    if batch.mapping and batch.mapping.mappings:
        for k, item in batch.mapping.mappings.items():
            if item.target_field_id or item.target_field_name:
                suggested.mappings[k] = item
        core_cols = ["VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider", "IMEI Number", "Registration Type"]
        missing = [c for c in core_cols if not (suggested.mappings.get(c) and (suggested.mappings[c].target_field_id or suggested.mappings[c].target_field_name))]
        suggested.missing_required_fields = missing
        suggested.is_complete = len(missing) == 0

    batch.mapping = suggested
    return suggested

@app.post("/api/vahan/batches/{batch_id}/mapping", response_model=BatchMappingConfig)
def save_field_mapping(batch_id: str, mapping_config: BatchMappingConfig):
    """
    Phase C: Saves user-confirmed explicit mapping from CSV columns to portal form elements.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]

    # Recalculate completeness based on mapped IDs for core required fields
    core_cols = ["VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider", "IMEI Number", "Registration Type"]
    missing = []
    for col in core_cols:
        item = mapping_config.mappings.get(col)
        if not item or not (item.target_field_id or item.target_field_name):
            missing.append(col)

    mapping_config.missing_required_fields = missing
    mapping_config.is_complete = (len(missing) == 0)
    mapping_config.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    batch.mapping = mapping_config
    return mapping_config

@app.post("/api/vahan/batches/{batch_id}/dry-run", response_model=DryRunResult)
def execute_dry_run_autofill(batch_id: str, payload: Dict = Body(default={})):
    """
    Phase D: Populates a single test record into the official portal form WITHOUT submitting.
    Reads back every field, compares with intended CSV values, and reports discrepancies.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]
    valid_records = [r for r in batch.records if r.status in [RecordStatus.READY, RecordStatus.PENDING]]
    if not valid_records:
        raise HTTPException(status_code=400, detail="No valid records available in batch for dry-run testing.")

    record_index = payload.get("record_index", 0)
    target_record = valid_records[record_index] if record_index < len(valid_records) else valid_records[0]

    if not batch.mapping:
        fields = selenium_worker.latest_inventory.fields if selenium_worker.latest_inventory else []
        custom_cols = list(batch.records[0].raw_data.keys()) if (batch.records and batch.records[0].raw_data) else None
        batch.mapping = selenium_worker.generate_suggested_mapping(batch_id, fields, custom_columns=custom_cols)

    try:
        dry_run_result = selenium_worker.dry_run_autofill(target_record, batch.mapping)
        batch.dry_run_result = dry_run_result
        if dry_run_result.success:
            batch.state = BatchState.READY_TO_PROCESS
            batch.summary.current_stage = f"Dry-Run Verified (Record {target_record.id})"
        else:
            batch.summary.current_stage = f"Dry-Run Discrepancy (Record {target_record.id})"
            batch.summary.current_error_message = dry_run_result.summary_message

        return dry_run_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dry-run execution failed: {str(e)}")

# Phase E & F: Start Processing (Single or Batch or Selected Subset)
@app.post("/api/vahan/batches/{batch_id}/start", response_model=BatchResponse)
def start_processing(batch_id: str, payload: Dict = Body(default={"mode": "batch"})):
    """
    Phase E & F: Initiates controlled sequential entry.
    mode = "single": Processes 1 record and halts for user review.
    mode = "batch": Processes sequential batch with continue-on-error recovery.
    selected_row_numbers: Optional list of selected row numbers to execute.
    selected_record_ids: Optional list of selected record IDs to execute.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]
    mode = payload.get("mode", "batch")
    selected_rows = payload.get("selected_row_numbers")
    selected_ids = payload.get("selected_record_ids")

    if not batch.mapping:
        fields = selenium_worker.latest_inventory.fields if selenium_worker.latest_inventory else []
        custom_cols = list(batch.records[0].raw_data.keys()) if (batch.records and batch.records[0].raw_data) else None
        batch.mapping = selenium_worker.generate_suggested_mapping(batch_id, fields, custom_columns=custom_cols)

    if not batch.mapping or not batch.mapping.is_complete:
        missing_names = ", ".join(batch.mapping.missing_required_fields) if (batch.mapping and batch.mapping.missing_required_fields) else "required fields"
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start: Field mapping is incomplete. Missing: {missing_names}. Please open Step 3 (Field Mapping) to map these fields or click 'Quick-Apply VAHAN Defaults'."
        )

    valid_records = [r for r in batch.records if r.status in [RecordStatus.READY, RecordStatus.PENDING]]
    if not valid_records:
        raise HTTPException(status_code=400, detail="No valid pending records available to process.")

    try:
        selenium_worker.start_batch_processing_async(
            batch,
            mode=mode,
            selected_row_numbers=selected_rows,
            selected_record_ids=selected_ids
        )
        return batch
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not start batch worker: {str(e)}")

@app.post("/api/vahan/batches/{batch_id}/resume", response_model=BatchResponse)
def resume_processing(batch_id: str):
    """
    Resumes batch processing after user completes manual re-authentication
    when session expired (PAUSED_AUTH_REQUIRED).
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]
    if batch.state != BatchState.PAUSED_AUTH_REQUIRED:
        raise HTTPException(status_code=400, detail="Batch is not in PAUSED_AUTH_REQUIRED state.")

    # Re-verify session
    is_ok, msg = selenium_worker.verify_session()
    if not is_ok:
        raise HTTPException(status_code=400, detail=f"Cannot resume: {msg}. Please log in on Chrome first.")

    batch.state = BatchState.PROCESSING
    batch.summary.current_stage = "Resuming batch processing after re-authentication..."
    selenium_worker.start_batch_processing_async(batch, mode="batch")
    return batch

@app.post("/api/vahan/batches/{batch_id}/stop")
def stop_batch(batch_id: str):
    """
    Requests controlled stop between operations.
    The worker finishes the current atomic action and ceases subsequent rows safely.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    selenium_worker.request_stop()
    batch = BATCH_STORE[batch_id]
    batch.state = BatchState.STOPPED
    batch.summary.current_stage = "Stop requested by user"
    return {"message": "Stop signal acknowledged by worker.", "state": batch.state}

@app.get("/api/vahan/batches/{batch_id}/logs", response_model=List[ExecutionLogEntry])
def get_execution_logs(
    batch_id: str,
    level: Optional[str] = Query(None, description="Filter by LogLevel: INFO, WARNING, ERROR, CRITICAL"),
    execution_type: Optional[str] = Query(None, description="Filter by ExecutionType"),
    csv_row: Optional[int] = Query(None, description="Filter by CSV row number"),
    limit: int = Query(100, description="Max entries to return")
):
    """
    Returns structured, timestamped audit log entries for a batch run.
    """
    return execution_logger.get_logs(
        run_id=batch_id,
        level=level,
        execution_type=execution_type,
        csv_row=csv_row,
        limit=limit
    )

@app.get("/api/vahan/batches/{batch_id}/report")
def get_batch_report(batch_id: str):
    """
    Retrieves record-level execution report with full audit trail and logs.
    """
    if batch_id not in BATCH_STORE:
        raise HTTPException(status_code=404, detail="Batch not found")

    batch = BATCH_STORE[batch_id]
    logs = execution_logger.get_logs(batch_id, limit=200)
    return {
        "batch_id": batch.batch_id,
        "file_name": batch.file_name,
        "state": batch.state,
        "summary": batch.summary,
        "records": batch.records,
        "errors": batch.errors,
        "inventory": batch.inventory,
        "mapping": batch.mapping,
        "dry_run_result": batch.dry_run_result,
        "logs": logs
    }

@app.get("/api/vahan/logs/unified")
def get_unified_log_file(lines: int = Query(200, description="Max lines from root vahan_automation.log")):
    """
    Returns recent entries from the single root directory log file: vahan_automation.log.
    """
    return {
        "log_file": ROOT_LOG_FILE,
        "content": get_root_log_content(lines)
    }
