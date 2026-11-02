# backend/modules/untag/service.py
import uuid
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from core.browser_manager import browser_manager
from logger_service import execution_logger
from models import LogLevel, ExecutionType
from .automation import replace_automation, REPLACE_OPTIONS

class ReplaceOptionSelectRequest(BaseModel):
    option_key: str = Field(..., description="Option code (S, D, I) or full option name")

class ReplaceOptionSelectResponse(BaseModel):
    success: bool
    option_key: str
    message: str
    revealed_fields: List[str] = Field(default_factory=list)

class ReplaceFieldInfo(BaseModel):
    id: str
    tag: str
    type: str = ""
    label: str = ""
    text: str = ""
    options: List[Dict[str, str]] = Field(default_factory=list)

class ReplaceInspectResponse(BaseModel):
    success: bool
    fields: List[ReplaceFieldInfo] = Field(default_factory=list)
    portal_url: str

class ReplaceSingleExecuteRequest(BaseModel):
    option_key: str
    maker: Optional[str] = ""
    model: Optional[str] = ""
    serial_no: Optional[str] = ""
    imei: Optional[str] = ""
    iccid: Optional[str] = ""
    reg_type: Optional[str] = "Old Vehicle"
    extra_data: Dict[str, Any] = Field(default_factory=dict)

class ReplaceSingleExecuteResponse(BaseModel):
    transaction_id: str
    status: str # "SUCCESS" | "FAILED"
    message: str
    reference_id: Optional[str] = None
    executed_at: str
    duration_seconds: float

class ReplaceBatchRequest(BaseModel):
    option_key: str
    records: List[Dict[str, Any]]

class ReplaceBatchResponse(BaseModel):
    batch_id: str
    total_count: int
    successful_count: int
    failed_count: int
    results: List[ReplaceSingleExecuteResponse]
    created_at: str

class ReplaceVltdService:
    """
    Business service coordinating Replace Device / Change ICCID transactions.
    """

    def get_options(self) -> List[Dict[str, str]]:
        return replace_automation.get_supported_options()

    def select_option(self, option_key: str) -> ReplaceOptionSelectResponse:
        run_id = execution_logger.current_session_id
        ok, msg, revealed = replace_automation.select_reason_option(option_key, run_id=run_id)
        return ReplaceOptionSelectResponse(
            success=ok,
            option_key=option_key,
            message=msg,
            revealed_fields=revealed
        )

    def inspect_form(self) -> ReplaceInspectResponse:
        fields_data = replace_automation.inspect_revealed_fields()
        driver = browser_manager.driver
        url = driver.current_url if driver else ""
        parsed_fields = [
            ReplaceFieldInfo(
                id=f.get("id", ""),
                tag=f.get("tag", ""),
                type=f.get("type", ""),
                label=f.get("label", ""),
                text=f.get("text", ""),
                options=f.get("options", [])
            )
            for f in fields_data
        ]
        return ReplaceInspectResponse(
            success=True,
            fields=parsed_fields,
            portal_url=url
        )

    def execute_single(self, req: ReplaceSingleExecuteRequest) -> ReplaceSingleExecuteResponse:
        start_time = time.time()
        tx_id = f"tx-rep-{uuid.uuid4().hex[:8]}"
        run_id = execution_logger.current_session_id

        # Merge data
        data = {
            "maker": req.maker,
            "model": req.model,
            "serial_no": req.serial_no,
            "imei": req.imei,
            "iccid": req.iccid,
            "reg_type": req.reg_type,
            **req.extra_data
        }

        ok, msg, ref_id = replace_automation.populate_and_submit_fitment(data, run_id=run_id)
        duration = round(time.time() - start_time, 2)

        return ReplaceSingleExecuteResponse(
            transaction_id=tx_id,
            status="SUCCESS" if ok else "FAILED",
            message=msg,
            reference_id=ref_id,
            executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            duration_seconds=duration
        )

    def execute_batch(self, req: ReplaceBatchRequest) -> ReplaceBatchResponse:
        batch_id = f"batch-rep-{uuid.uuid4().hex[:8]}"
        results: List[ReplaceSingleExecuteResponse] = []
        succ = 0
        fail = 0

        # Ensure option is selected first
        self.select_option(req.option_key)

        for rec in req.records:
            single_req = ReplaceSingleExecuteRequest(
                option_key=req.option_key,
                maker=rec.get("VLTD Maker") or rec.get("maker", ""),
                model=rec.get("VLTD Model") or rec.get("model", ""),
                serial_no=rec.get("VLTD serial Number") or rec.get("serial_no", ""),
                imei=rec.get("IMEI Number") or rec.get("imei", ""),
                iccid=rec.get("ICC ID") or rec.get("iccid", ""),
                reg_type=rec.get("Registration Type") or rec.get("reg_type", "Old Vehicle"),
                extra_data=rec
            )
            res = self.execute_single(single_req)
            results.append(res)
            if res.status == "SUCCESS":
                succ += 1
            else:
                fail += 1

        return ReplaceBatchResponse(
            batch_id=batch_id,
            total_count=len(req.records),
            successful_count=succ,
            failed_count=fail,
            results=results,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

replace_service = ReplaceVltdService()

