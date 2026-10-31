import os
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from models import ExecutionLogEntry, ExecutionType, LogLevel

# Timezone: Asia/Kolkata (+05:30)
KOLKATA_TZ = timezone(timedelta(hours=5, minutes=30))

# Single unified root log file in project root directory
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ROOT_LOG_FILE = os.path.join(ROOT_DIR, "vahan_automation.log")

_log_lock = threading.Lock()

def append_to_root_log(log_line: str):
    """
    Safely appends a log line to the single unified root directory log file
    (vahan_automation.log) with immediate flush.
    """
    with _log_lock:
        try:
            with open(ROOT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line.rstrip() + "\n")
                f.flush()
        except Exception:
            pass

def get_root_log_content(limit_lines: int = 300) -> str:
    """Reads the most recent lines from the single root vahan_automation.log file."""
    if not os.path.exists(ROOT_LOG_FILE):
        return ""
    try:
        with _log_lock:
            with open(ROOT_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-limit_lines:])
    except Exception as e:
        return f"Error reading root log file: {str(e)}"

def get_clean_timestamp() -> str:
    """Returns concise, easily readable timestamp: YYYY-MM-DD HH:MM:SS."""
    return datetime.now(KOLKATA_TZ).strftime("%Y-%m-%d %H:%M:%S")

def simplify_operation_keyword(stage: Optional[str], action: Optional[str]) -> str:
    """
    Simplifies stage and action into standard, easily recognizable uppercase keywords:
    START_BATCH, START_RECORD, FILL_VLTD, SELECT_REG_TYPE, FILL_VEHICLE,
    GET_DETAILS, CONFIRM_SUBMIT, VERIFY_RESULT, TRANSACTION_FAIL, BATCH_FINISH,
    AUTH_CHECK, NAVIGATE_LOGIN, NAVIGATE_PORTAL, VALIDATE_MAPPING, RESET_FORM, DRY_RUN, ERROR.
    """
    s = (stage or "").upper()
    a = (action or "").upper()
    combined = f"{s} {a}".strip()

    if "DRY_RUN" in combined:
        return "DRY_RUN"
    if "VLTD" in combined or "MAKER" in combined or "IMEI" in combined:
        return "FILL_VLTD"
    if "REGISTRATION" in combined or "REG_TYPE" in combined:
        return "SELECT_REG_TYPE"
    if "CHASSIS" in combined or "ENGINE" in combined or ("VEHICLE" in combined and "FETCH" not in combined and "GET" not in combined):
        return "FILL_VEHICLE"
    if "GET_DETAIL" in combined or "FETCH" in combined:
        return "GET_DETAILS"
    if "CONFIRM" in combined or "MODAL" in combined or "SAVE" in combined:
        return "CONFIRM_SUBMIT"
    if "HANDLE_FAILURE" in combined:
        return "TRANSACTION_FAIL"
    if "VERIFY_RESULT" in combined or "RESULT" in combined:
        return "VERIFY_RESULT"
    if "START_RECORD" in combined or "PREPARE_TRANSACTION" in combined:
        return "START_RECORD"
    if "START_BATCH" in combined or "BATCH_INIT" in combined:
        return "START_BATCH"
    if "FINISH_BATCH" in combined or "BATCH_COMPLETION" in combined:
        return "BATCH_FINISH"
    if "SESSION" in combined or "AUTH" in combined:
        return "AUTH_CHECK"
    if "NAVIGATE_TO_LOGIN" in combined or "LOGIN" in combined:
        return "NAVIGATE_LOGIN"
    if "NAVIGATE_TO_FITTING" in combined or "PORTAL" in combined:
        return "NAVIGATE_PORTAL"
    if "MAPPING" in combined:
        return "VALIDATE_MAPPING"
    if "RESET" in combined:
        return "RESET_FORM"
    if "STOP" in combined:
        return "STOP_BATCH"
    if "PROCESS_SEQUENTIAL" in combined:
        return "BATCH_PROCESS"
    if "EXECUTE_RECORD" in combined:
        return "RECORD_TXN"
    if "EXCEPTION" in combined or "RECOVERY" in combined:
        return "ERROR"

    clean_action = a or s or "SYSTEM"
    return clean_action.replace(" ", "_")

def simplify_status_keyword(result: Optional[str]) -> str:
    """Simplifies execution result into standard short status tags: OK, FAIL, RUNNING, AUTH_PAUSE, DONE."""
    r = (result or "").upper()
    if r in ["SUCCESS", "MATCHED", "OK"]:
        return "OK"
    if r in ["FAILED", "ERROR", "MISMATCH"]:
        return "FAIL"
    if r in ["IN_PROGRESS", "RUNNING"]:
        return "RUNNING"
    if r in ["PAUSED_AUTH_REQUIRED", "AUTH_REQUIRED", "AUTH_PAUSE"]:
        return "AUTH_PAUSE"
    if r in ["COMPLETED_WITH_ERRORS"]:
        return "DONE_WITH_ERRORS"
    if r in ["COMPLETED"]:
        return "COMPLETED"
    return r or "INFO"

class UnifiedRootLogHandler(logging.Handler):
    """
    Directs general Python logging (e.g. from VahanSeleniumWorker, FastAPI, etc.)
    into the single root log file, formatted with simple keywords and timestamps.
    """
    def emit(self, record: logging.LogRecord):
        # Avoid duplicate logging if the record originated from execution_logger
        if getattr(record, "_from_execution_logger", False):
            return
        clean_time = get_clean_timestamp()
        op_kw = simplify_operation_keyword(None, getattr(record, "operation", getattr(record, "funcName", "SYSTEM")))
        log_line = f"[{clean_time}] [{record.levelname}] [OP: {op_kw}] {record.getMessage()}"
        append_to_root_log(log_line)

# Configure standard logger to pipe into the single root log file
standard_logger = logging.getLogger("VahanAutomation")
_unified_handler = UnifiedRootLogHandler()
_unified_handler.setLevel(logging.INFO)
standard_logger.addHandler(_unified_handler)
logging.getLogger("VahanSeleniumWorker").addHandler(_unified_handler)

class DurableExecutionLogger:
    """
    Single-file structured execution audit logger conforming to VAHAN VLTD requirements:
    - Single unified root directory log file: vahan_automation.log
    - ISO 8601 Asia/Kolkata timestamps
    - Explicit OPERATION tag on every log line
    - Run and Transaction IDs, Row numbers, and Result states
    - Sensitive data masking (passwords, CAPTCHA, session secrets)
    - Thread-safe storage & immediate durable flush
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DurableExecutionLogger, cls).__new__(cls)
            cls._instance._init_logger()
        return cls._instance

    def _init_logger(self):
        # run_id -> list of ExecutionLogEntry (in-memory for active UI session queries)
        self._memory_logs: Dict[str, List[ExecutionLogEntry]] = {}

    def get_timestamp(self) -> str:
        """Returns ISO 8601 timestamp in Asia/Kolkata timezone with explicit offset (+05:30)."""
        now_kolkata = datetime.now(KOLKATA_TZ)
        return now_kolkata.isoformat()

    def mask_sensitive(self, text: str) -> str:
        """Masks any potential credentials, passwords, or CAPTCHA tokens."""
        if not text:
            return ""
        for sensitive_keyword in ["password", "pwd", "captcha", "cookie", "token", "sessionid", "jsessionid"]:
            if sensitive_keyword in text.lower():
                return "[PROTECTED_AUTHENTICATION_CREDENTIAL]"
        return text

    def log(
        self,
        level: LogLevel,
        execution_type: ExecutionType,
        run_id: str,
        stage: str,
        action: str,
        result: str,
        message: str,
        transaction_id: Optional[str] = None,
        csv_row: Optional[int] = None,
        error_code: Optional[str] = None,
        duration_ms: Optional[float] = None
    ) -> ExecutionLogEntry:
        """
        Creates, persists, and records a structured audit log entry into the single root log file:
        - Format: [TIMESTAMP] [LEVEL] [OPERATION: ...] [RESULT: ...] run=... txn=... row=... - message
        """
        clean_msg = self.mask_sensitive(message)
        timestamp = self.get_timestamp()

        # Format operation clearly: "STAGE -> ACTION" or just "ACTION"
        if stage and action and stage != action:
            operation = f"{stage} -> {action}"
        else:
            operation = action or stage or "GENERAL_OPERATION"

        entry = ExecutionLogEntry(
            timestamp=timestamp,
            level=level,
            execution_type=execution_type,
            run_id=run_id,
            transaction_id=transaction_id,
            csv_row=csv_row,
            stage=stage,
            action=action,
            result=result,
            message=clean_msg,
            error_code=error_code,
            execution_duration_ms=round(duration_ms, 2) if duration_ms is not None else None
        )

        # 1. In-memory append for active session UI queries
        if run_id not in self._memory_logs:
            self._memory_logs[run_id] = []
        self._memory_logs[run_id].append(entry)

        # 2. Formatted log line with clean timestamp, simplified operation and status keywords
        clean_time = get_clean_timestamp()
        op_kw = simplify_operation_keyword(stage, action)
        status_kw = simplify_status_keyword(result)
        row_str = f" [Row {entry.csv_row}]" if entry.csv_row is not None else ""
        dur_str = f" ({round(duration_ms, 1)}ms)" if duration_ms is not None else ""
        err_str = f" [ERR: {error_code}]" if error_code else ""

        log_line = (
            f"[{clean_time}] [{entry.level.value}] [OP: {op_kw}] [{status_kw}]{row_str}{dur_str}{err_str} {entry.message}"
        )

        # 3. Echo to console logger without re-triggering unified handler
        try:
            extra = {"_from_execution_logger": True, "operation": operation}
            if level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                standard_logger.error(log_line, extra=extra)
            elif level == LogLevel.WARNING:
                standard_logger.warning(log_line, extra=extra)
            else:
                standard_logger.info(log_line, extra=extra)
        except Exception:
            pass

        # 4. Save to ONE file only (vahan_automation.log in root directory) with immediate flush
        append_to_root_log(log_line)

        return entry

    def get_logs(
        self,
        run_id: str,
        level: Optional[str] = None,
        execution_type: Optional[str] = None,
        csv_row: Optional[int] = None,
        limit: int = 100
    ) -> List[ExecutionLogEntry]:
        """Queries stored logs for a run with optional filtering."""
        logs = self._memory_logs.get(run_id, [])
        filtered = logs
        if level and level != "ALL":
            filtered = [l for l in filtered if l.level.value == level.upper()]
        if execution_type and execution_type != "ALL":
            filtered = [l for l in filtered if l.execution_type.value == execution_type.upper()]
        if csv_row is not None:
            filtered = [l for l in filtered if l.csv_row == csv_row]
        
        return filtered[-limit:]

execution_logger = DurableExecutionLogger()
