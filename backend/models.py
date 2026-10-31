from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

class BatchState(str, Enum):
    IDLE = "IDLE"
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    WAITING_FOR_AUTHENTICATION = "WAITING_FOR_AUTHENTICATION"
    INSPECTING_FORM = "INSPECTING_FORM"
    READY_TO_PROCESS = "READY_TO_PROCESS"
    PROCESSING = "PROCESSING"
    PAUSED_AUTH_REQUIRED = "PAUSED_AUTH_REQUIRED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"

class TransactionState(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    AUTHENTICATING = "AUTHENTICATING"
    READY = "READY"
    FILLING_VLTD_DETAILS = "FILLING_VLTD_DETAILS"
    SELECTING_REGISTRATION_TYPE = "SELECTING_REGISTRATION_TYPE"
    FILLING_VEHICLE_DETAILS = "FILLING_VEHICLE_DETAILS"
    FETCHING_VEHICLE_DETAILS = "FETCHING_VEHICLE_DETAILS"
    VALIDATING_VEHICLE_DETAILS = "VALIDATING_VEHICLE_DETAILS"
    AWAITING_SAVE_MODAL = "AWAITING_SAVE_MODAL"
    AWAITING_FINAL_CONFIRMATION = "AWAITING_FINAL_CONFIRMATION"
    SUBMITTING = "SUBMITTING"
    VERIFYING_RESULT = "VERIFYING_RESULT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PAUSED_AUTH_REQUIRED = "PAUSED_AUTH_REQUIRED"
    UNKNOWN = "UNKNOWN"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"

class RecordStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    INVALID = "INVALID"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED_FILLED = "VERIFIED_FILLED"
    SUBMITTED = "SUBMITTED" # Kept for backward compatibility
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PAUSED_AUTH_REQUIRED = "PAUSED_AUTH_REQUIRED"
    UNKNOWN = "UNKNOWN"
    REQUIRES_RECONCILIATION = "REQUIRES_RECONCILIATION"

class ExecutionType(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"
    RECORD_EXECUTION = "RECORD_EXECUTION"
    FIELD_VALIDATION = "FIELD_VALIDATION"
    FORM_INTERACTION = "FORM_INTERACTION"
    CONFIRMATION = "CONFIRMATION"
    TRANSACTION_RESULT = "TRANSACTION_RESULT"
    RECOVERY = "RECOVERY"
    BATCH_SUMMARY = "BATCH_SUMMARY"

class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ExecutionLogEntry(BaseModel):
    timestamp: str # ISO 8601 Asia/Kolkata (+05:30)
    level: LogLevel = LogLevel.INFO
    execution_type: ExecutionType = ExecutionType.RECORD_EXECUTION
    run_id: str
    transaction_id: Optional[str] = None
    csv_row: Optional[int] = None
    stage: str
    action: str
    result: str # SUCCESS | FAILED | PENDING | etc.
    message: str
    error_code: Optional[str] = None
    execution_duration_ms: Optional[float] = None

class ValidationError(BaseModel):
    row_number: int
    source_id: Optional[str] = None
    column: str
    error_message: str
    severity: str = "error" # "error" | "warning"

class CsvRecord(BaseModel):
    row_number: int
    id: str
    # 11 Mapped CSV Columns
    vltd_maker: str
    vltd_model: str
    vltd_serial_number: str
    provider: str
    service_provider: Optional[str] = None
    imei_number: str
    imei: Optional[str] = None
    icc_id: Optional[str] = None
    registration_type: str
    chassis_no: Optional[str] = None
    engine_no: Optional[str] = None
    vehicle_state: Optional[str] = None
    rto: Optional[str] = None
    vehicle_registration_number: Optional[str] = None

    raw_data: Dict[str, str] = Field(default_factory=dict)
    status: RecordStatus = RecordStatus.PENDING
    transaction_state: Optional[TransactionState] = TransactionState.PENDING
    transaction_id: Optional[str] = None
    validation_errors: List[ValidationError] = Field(default_factory=list)
    portal_confirmation_ref: Optional[str] = None
    execution_message: Optional[str] = None
    executed_at: Optional[str] = None
    duration_seconds: Optional[float] = None

class BatchSummary(BaseModel):
    total_records: int = 0
    valid_records_count: int = 0
    invalid_records_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    unresolved_count: int = 0
    current_record_index: int = 0
    current_source_id: Optional[str] = None
    current_stage: str = "Initialized"
    last_confirmed_record: Optional[str] = None
    current_error_message: Optional[str] = None

class FormFieldOption(BaseModel):
    label: str
    value: str

class DiscoveredFormField(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    tag: str # input, select, textarea
    input_type: Optional[str] = None # text, number, date, etc.
    label: Optional[str] = None
    is_required: Optional[bool] = False
    is_disabled: Optional[bool] = False
    current_value: Optional[str] = None
    options: List[FormFieldOption] = Field(default_factory=list)

class PortalInventory(BaseModel):
    portal_url: str
    page_title: str
    is_authenticated: bool = False
    is_sld_form_available: bool = False
    fields: List[DiscoveredFormField] = Field(default_factory=list)
    discovered_at: Optional[str] = None
    message: Optional[str] = None

# Phase C: Field Mapping Schemas
class FieldMappingItem(BaseModel):
    csv_column: str
    target_field_id: Optional[str] = None
    target_field_name: Optional[str] = None
    target_field_label: Optional[str] = None
    element_tag: Optional[str] = "input" # input | select
    is_required: bool = True

class BatchMappingConfig(BaseModel):
    batch_id: str
    is_complete: bool = False
    missing_required_fields: List[str] = Field(default_factory=list)
    mappings: Dict[str, FieldMappingItem] = Field(default_factory=dict)
    updated_at: Optional[str] = None

# Phase D: Dry-Run Verification Schemas
class FieldVerificationResult(BaseModel):
    csv_column: str
    portal_field: str
    expected_value: str
    actual_value: str
    matched: bool
    status: str # "MATCHED" | "MISMATCH" | "FIELD_NOT_FOUND" | "OPTION_NOT_FOUND"
    message: Optional[str] = None

class DryRunResult(BaseModel):
    record_id: str
    row_number: int
    success: bool
    executed_at: str
    verifications: List[FieldVerificationResult] = Field(default_factory=list)
    portal_url: str
    summary_message: str

class BatchStartRequest(BaseModel):
    mode: str = "batch" # "single" | "batch"
    selected_row_numbers: Optional[List[int]] = None
    selected_record_ids: Optional[List[str]] = None

class BatchResponse(BaseModel):
    batch_id: str
    file_name: str
    state: BatchState
    summary: BatchSummary
    records: List[CsvRecord] = Field(default_factory=list)
    errors: List[ValidationError] = Field(default_factory=list)
    created_at: str
    inventory: Optional[PortalInventory] = None
    mapping: Optional[BatchMappingConfig] = None
    dry_run_result: Optional[DryRunResult] = None
    logs: List[ExecutionLogEntry] = Field(default_factory=list)
