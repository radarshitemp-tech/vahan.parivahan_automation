# backend/modules/delete/service.py
import uuid
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from core.browser_manager import browser_manager
from core.session_manager import session_manager
from logger_service import execution_logger
from models import LogLevel, ExecutionType
from .automation import delete_automation

class DeleteSelectRequest(BaseModel):
    registration_number: str

class DeleteSelectResponse(BaseModel):
    success: bool
    registration_number: str
    message: str
    vehicle_info: Optional[Dict[str, str]] = Field(default_factory=dict)
    has_release_section: bool = False

class DeleteOpenModalResponse(BaseModel):
    success: bool
    message: str
    is_modal_ready: bool = False

class DeleteConfirmRequest(BaseModel):
    registration_number: str
    reason: str = "Untag VLTD / Fitment Removal"

class DeleteConfirmResponse(BaseModel):
    transaction_id: str
    registration_number: str
    reason: str
    status: str # "SUCCESS" | "FAILED"
    message: str
    confirmation_ref: Optional[str] = None
    executed_at: str
    duration_seconds: float

class DeleteBatchRequest(BaseModel):
    registrations: List[str]
    default_reason: str = "Untag VLTD / Fitment Removal"

class DeleteBatchResponse(BaseModel):
    batch_id: str
    total_count: int
    successful_count: int
    failed_count: int
    results: List[DeleteConfirmResponse]
    created_at: str

class DeleteVltdService:
    """
    Business service coordinating Delete / Unlock VLTD transactions.
    """

    def get_available_registrations(self) -> List[str]:
        return delete_automation.extract_registration_options()

    def select_registration(self, reg_no: str) -> DeleteSelectResponse:
        ok, msg, veh_info = delete_automation.select_registration_number(reg_no)
        return DeleteSelectResponse(
            success=ok,
            registration_number=reg_no,
            message=msg,
            vehicle_info=veh_info or {},
            has_release_section=ok
        )

    def open_reason_modal(self) -> DeleteOpenModalResponse:
        ok, msg = delete_automation.open_unlock_modal()
        return DeleteOpenModalResponse(
            success=ok,
            message=msg,
            is_modal_ready=ok
        )

    def confirm_and_unlock(self, reg_no: str, reason: str) -> DeleteConfirmResponse:
        start_time = time.time()
        txn_id = f"TXN_DEL_{uuid.uuid4().hex[:8].upper()}"

        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.RECORD_EXECUTION,
            run_id=txn_id,
            transaction_id=txn_id,
            stage="START_UNLOCK",
            action="EXECUTE_TRANSACTION",
            result="IN_PROGRESS",
            message=f"Beginning unlock transaction for vehicle {reg_no}."
        )

        ok, msg, ref_id = delete_automation.execute_final_unlock(
            reg_no=reg_no,
            reason=reason,
            run_id=txn_id
        )

        duration = round(time.time() - start_time, 2)
        status_str = "SUCCESS" if ok else "FAILED"

        return DeleteConfirmResponse(
            transaction_id=txn_id,
            registration_number=reg_no,
            reason=reason,
            status=status_str,
            message=msg,
            confirmation_ref=ref_id,
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            duration_seconds=duration
        )

    def execute_batch_unlock(self, registrations: List[str], default_reason: str) -> DeleteBatchResponse:
        batch_id = f"BATCH_DEL_{uuid.uuid4().hex[:8].upper()}"
        results = []
        success_count = 0
        fail_count = 0

        for reg in registrations:
            reg_clean = reg.strip()
            if not reg_clean:
                continue

            # Step 1: Select
            sel_res = self.select_registration(reg_clean)
            if not sel_res.success:
                results.append(DeleteConfirmResponse(
                    transaction_id=f"TXN_{uuid.uuid4().hex[:6].upper()}",
                    registration_number=reg_clean,
                    reason=default_reason,
                    status="FAILED",
                    message=f"Selection failed: {sel_res.message}",
                    confirmation_ref=None,
                    executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    duration_seconds=0.0
                ))
                fail_count += 1
                continue

            # Step 2: Open modal
            modal_res = self.open_reason_modal()
            if not modal_res.success:
                results.append(DeleteConfirmResponse(
                    transaction_id=f"TXN_{uuid.uuid4().hex[:6].upper()}",
                    registration_number=reg_clean,
                    reason=default_reason,
                    status="FAILED",
                    message=f"Modal failed: {modal_res.message}",
                    confirmation_ref=None,
                    executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    duration_seconds=0.0
                ))
                fail_count += 1
                continue

            # Step 3: Final unlock
            res = self.confirm_and_unlock(reg_clean, default_reason)
            results.append(res)
            if res.status == "SUCCESS":
                success_count += 1
            else:
                fail_count += 1

            time.sleep(1.0)

        return DeleteBatchResponse(
            batch_id=batch_id,
            total_count=len(results),
            successful_count=success_count,
            failed_count=fail_count,
            results=results,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

delete_service = DeleteVltdService()

