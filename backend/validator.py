import csv
import io
import re
from typing import List, Dict, Tuple, Optional
from models import CsvRecord, ValidationError, RecordStatus, TransactionState

from decimal import Decimal

CORE_REQUIRED_COLUMNS = [
    "VLTD Maker",
    "VLTD Model",
    "VLTD serial Number",
    "Provider",
    "IMEI Number",
    "Registration Type"
]

# Normalization map for headers
HEADER_ALIASES = {
    "id": "ID",
    "source_id": "ID",
    "sl_no": "ID",
    "sno": "ID",
    
    # 1. vltd_maker
    "vltd_maker": "VLTD Maker",
    "vltd maker": "VLTD Maker",
    "maker": "VLTD Maker",
    "select vltd maker": "VLTD Maker",
    "maker name": "VLTD Maker",
    "manufacturer": "VLTD Maker",
    
    # 2. vltd_model
    "vltd_model": "VLTD Model",
    "vltd model": "VLTD Model",
    "model": "VLTD Model",
    "select vltd model": "VLTD Model",
    "device model": "VLTD Model",
    
    # 3. vltd_serial_number
    "vltd_serial_number": "VLTD serial Number",
    "vltd serial number": "VLTD serial Number",
    "serial_number": "VLTD serial Number",
    "serial number": "VLTD serial Number",
    "serial_no": "VLTD serial Number",
    "serial no": "VLTD serial Number",
    "device_serial": "VLTD serial Number",
    "device serial": "VLTD serial Number",
    
    # 4. service_provider
    "provider": "Provider",
    "vltd_provider": "Provider",
    "service_provider": "Provider",
    "service provider": "Provider",
    "telecom": "Provider",
    "network": "Provider",
    
    # 5. imei
    "imei_number": "IMEI Number",
    "imei": "IMEI Number",
    "imei number": "IMEI Number",
    "imei_no": "IMEI Number",
    "device_imei": "IMEI Number",
    
    # 6. icc_id
    "icc_id": "ICC ID",
    "iccid": "ICC ID",
    "icc id": "ICC ID",
    "sim_no": "ICC ID",
    "sim number": "ICC ID",
    
    # 7. registration_type
    "registration_type": "Registration Type",
    "reg_type": "Registration Type",
    "registration type": "Registration Type",
    "select registration type": "Registration Type",
    "regn_type": "Registration Type",
    "regntype": "Registration Type",
    
    # 8. chassis_no
    "chassis_no": "Vehicle Chassis No",
    "chassis no": "Vehicle Chassis No",
    "chassis": "Vehicle Chassis No",
    "vehicle_chassis_no": "Vehicle Chassis No",
    "vehicle chassis no": "Vehicle Chassis No",
    "chassis_number": "Vehicle Chassis No",
    "vehicle_chasis_no": "Vehicle Chassis No",
    "vehicle chasis no": "Vehicle Chassis No",
    "chasis no": "Vehicle Chassis No",
    "chasis": "Vehicle Chassis No",
    "vehicle_chasis": "Vehicle Chassis No",
    
    # 9. engine_no
    "engine_no": "Vehicle Engine No (LAST 5 DIGITS)",
    "engine no": "Vehicle Engine No (LAST 5 DIGITS)",
    "engine": "Vehicle Engine No (LAST 5 DIGITS)",
    "vehicle_engine_no": "Vehicle Engine No (LAST 5 DIGITS)",
    "vehicle engine no": "Vehicle Engine No (LAST 5 DIGITS)",
    "vehicle engine no (last 5 digits)": "Vehicle Engine No (LAST 5 DIGITS)",
    "engine_last_5": "Vehicle Engine No (LAST 5 DIGITS)",
    
    # 10. vehicle_state
    "vehicle_state": "Vehicle State",
    "vehicle state": "Vehicle State",
    "state": "Vehicle State",
    "state_name": "Vehicle State",
    
    # 11. rto
    "rto": "RTO",
    "rto_code": "RTO",
    "rto name": "RTO",
    "rto_name": "RTO",
    "registering_authority": "RTO",
    "registering authority": "RTO",
    
    # Optional vehicle registration number
    "vehicle_registration_number": "Vehicle Registration Number",
    "vehicle registration number": "Vehicle Registration Number",
    "vehicle_registration_no": "Vehicle Registration Number",
    "vehicle registration no": "Vehicle Registration Number",
    "vehicle_reg_no": "Vehicle Registration Number",
    "vehicle reg no": "Vehicle Registration Number",
    "regn_no": "Vehicle Registration Number",
    "regn no": "Vehicle Registration Number",
    "vehicle_no": "Vehicle Registration Number",
    "vehicle no": "Vehicle Registration Number",
    "rc_number": "Vehicle Registration Number",
    "rc number": "Vehicle Registration Number",
    "reg_no": "Vehicle Registration Number",
    "reg no": "Vehicle Registration Number",
    "registration_number": "Vehicle Registration Number",
    "registration number": "Vehicle Registration Number",
    "reg_num": "Vehicle Registration Number",
    "reg num": "Vehicle Registration Number",
    "registration": "Vehicle Registration Number",

    # Delete / Unlock module: Reason aliases
    "reason": "Reason",
    "rejection_reason": "Reason",
    "unlock_reason": "Reason",
    "reject_reason": "Reason",
    "remarks": "Reason",
    "remark": "Reason",
    "comments": "Reason",
    "comment": "Reason",
    "notes": "Reason",
}

def normalize_header(header: str) -> str:
    cleaned = header.strip().lstrip('\ufeff').lower().replace("-", "_").replace("  ", " ")
    cleaned = re.sub(r'[\.\:\-_]+$', '', cleaned).strip()
    return HEADER_ALIASES.get(cleaned, header.strip())

def clean_csv_value(val: str) -> str:
    """Cleans newlines and expands integer scientific notation strings."""
    if val is None:
        return ""
    v = str(val).strip()
    if "\n" in v or "\r" in v:
        lines = [line.strip() for line in re.split(r'[\r\n]+', v) if line.strip()]
        v = lines[0] if lines else v.strip()
    if re.match(r'^\d+(\.\d+)?[eE][\+\-]?\d+$', v):
        try:
            d = Decimal(v)
            if d == d.to_integral():
                v = str(int(d))
        except Exception:
            pass
    return v

def validate_imei(imei: str) -> bool:
    """Validate 15-digit numeric IMEI."""
    if not imei:
        return False
    clean_imei = str(imei).strip()
    return bool(re.match(r"^\d{15}$", clean_imei))

def parse_and_validate_csv(csv_content: str, module_type: str = "add_vltd") -> Tuple[List[CsvRecord], List[ValidationError], List[str]]:
    """
    Parses CSV text strictly preserving leading zeros and validates columns and rows.
    Supports modular validation:
    - 'add_vltd': Validates 11 retrofitment columns (Maker, Model, Serial, Provider, IMEI, etc.)
    - 'delete_vltd': Validates 'Vehicle Registration Number' and optional 'Reason'.
    Returns (records, all_errors, detected_headers).
    """
    f = io.StringIO(csv_content)
    sample = csv_content[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    f.seek(0)
    reader = csv.reader(f, delimiter=delimiter)
    
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ValueError("The uploaded CSV file is empty.")

    # Clean and normalize headers
    normalized_headers = [normalize_header(h) for h in raw_headers]
    header_map: Dict[str, int] = {}
    for idx, norm_h in enumerate(normalized_headers):
        header_map[norm_h] = idx

    # Module-specific validation branches
    if module_type == "delete_vltd":
        if "Vehicle Registration Number" not in header_map:
            raise ValueError(
                "Missing required CSV column for Delete module: 'Vehicle Registration Number' "
                "(accepted aliases: registration_number, reg_no, vehicle_no)."
            )

        records: List[CsvRecord] = []
        all_errors: List[ValidationError] = []
        seen_regs: Dict[str, int] = {}

        for row_idx, row in enumerate(reader, start=2):
            if not row or all(c.strip() == "" for c in row):
                continue

            raw_dict: Dict[str, str] = {}
            for norm_h, col_idx in header_map.items():
                val = row[col_idx] if col_idx < len(row) else ""
                raw_dict[norm_h] = clean_csv_value(val)

            reg_no = raw_dict.get("Vehicle Registration Number", "").strip().upper()
            record_id = raw_dict.get("ID", "") or reg_no or f"ROW-{row_idx:04d}"
            reason = raw_dict.get("Reason", "").strip() or "Untag VLTD / Fitment Removal"

            row_errors: List[ValidationError] = []

            if not reg_no:
                row_errors.append(ValidationError(
                    row_number=row_idx,
                    source_id=record_id,
                    column="Vehicle Registration Number",
                    error_message="Missing Vehicle Registration Number."
                ))
            elif len(re.sub(r'[^A-Za-z0-9]', '', reg_no)) < 4:
                row_errors.append(ValidationError(
                    row_number=row_idx,
                    source_id=record_id,
                    column="Vehicle Registration Number",
                    error_message=f"Invalid vehicle registration number format: '{reg_no}'."
                ))
            elif reg_no in seen_regs:
                row_errors.append(ValidationError(
                    row_number=row_idx,
                    source_id=record_id,
                    column="Vehicle Registration Number",
                    error_message=f"Duplicate registration number '{reg_no}' (first seen on row {seen_regs[reg_no]}).",
                    severity="warning"
                ))
            else:
                seen_regs[reg_no] = row_idx

            has_fatal = any(e.severity == "error" for e in row_errors)
            status = RecordStatus.INVALID if has_fatal else RecordStatus.READY

            record = CsvRecord(
                row_number=row_idx,
                id=record_id,
                vehicle_registration_number=reg_no,
                reason=reason,
                raw_data=raw_dict,
                status=status,
                transaction_state=TransactionState.READY if status == RecordStatus.READY else TransactionState.PENDING,
                validation_errors=row_errors
            )
            records.append(record)
            all_errors.extend(row_errors)

        return records, all_errors, normalized_headers

    # Standard Add Module Validation
    required_check = ["ID"] + CORE_REQUIRED_COLUMNS
    missing_headers = [req for req in required_check if req not in header_map]
    if missing_headers:
        if missing_headers == ["ID"]:
            pass
        else:
            raise ValueError(
                f"Missing required CSV column headers: {', '.join(missing_headers)}. "
                f"Expected columns: {', '.join(required_check)}"
            )

    records: List[CsvRecord] = []
    all_errors: List[ValidationError] = []
    seen_ids: Dict[str, int] = {} # id -> first_seen_row

    for row_idx, row in enumerate(reader, start=2): # Start at row 2 (row 1 is header)
        if not row or all(c.strip() == "" for c in row):
            continue # skip empty row

        row_errors: List[ValidationError] = []
        raw_dict: Dict[str, str] = {}

        # Store canonical normalized entries
        for norm_h, col_idx in header_map.items():
            val = row[col_idx] if col_idx < len(row) else ""
            raw_dict[norm_h] = clean_csv_value(val)

        # Extract values strictly as strings, preserving leading zeros
        record_id = raw_dict.get("ID", "") or f"ROW-{row_idx:04d}"
        vltd_maker = raw_dict.get("VLTD Maker", "") or raw_dict.get("vltd_maker", "")
        vltd_model = raw_dict.get("VLTD Model", "") or raw_dict.get("vltd_model", "")
        vltd_serial_number = raw_dict.get("VLTD serial Number", "") or raw_dict.get("vltd_serial_number", "")
        provider = raw_dict.get("Provider", "") or raw_dict.get("service_provider", "")
        imei_number = raw_dict.get("IMEI Number", "") or raw_dict.get("imei", "")
        icc_id = raw_dict.get("ICC ID", "") or raw_dict.get("icc_id", "")
        registration_type = raw_dict.get("Registration Type", "") or raw_dict.get("registration_type", "")
        chassis_no = raw_dict.get("Vehicle Chassis No", "") or raw_dict.get("chassis_no", "")
        engine_no = raw_dict.get("Vehicle Engine No (LAST 5 DIGITS)", "") or raw_dict.get("engine_no", "")
        vehicle_state = raw_dict.get("Vehicle State", "") or raw_dict.get("vehicle_state", "")
        rto = raw_dict.get("RTO", "") or raw_dict.get("rto", "")
        vehicle_reg_no = raw_dict.get("Vehicle Registration Number", "")

        # 1. Validate ID
        if not record_id:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id="UNKNOWN",
                column="ID",
                error_message="Missing ID: Identifier cannot be empty."
            ))
        elif record_id in seen_ids:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="ID",
                error_message=f"Duplicate ID '{record_id}' detected (first seen on CSV row {seen_ids[record_id]})."
            ))
        else:
            seen_ids[record_id] = row_idx

        # 2. Validate VLTD Maker
        if not vltd_maker:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="VLTD Maker",
                error_message="Missing VLTD Maker name."
            ))

        # 3. Validate VLTD Model
        if not vltd_model:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="VLTD Model",
                error_message="Missing VLTD Model."
            ))

        # 4. Validate VLTD Serial Number
        if not vltd_serial_number:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="VLTD serial Number",
                error_message="Missing VLTD serial Number."
            ))

        # 5. Validate Provider
        if not provider:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="Provider",
                error_message="Missing VLTD Provider."
            ))

        # 6. Validate IMEI Number (15 digits numeric, strictly preserving leading zeros)
        if not imei_number:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="IMEI Number",
                error_message="Missing IMEI Number."
            ))
        elif not validate_imei(imei_number):
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="IMEI Number",
                error_message=f"Invalid IMEI Number '{imei_number}'. Must be exactly 15 numeric digits."
            ))

        # 7. Validate Registration Type
        if not registration_type:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="Registration Type",
                error_message="Missing Registration Type."
            ))

        # 8. Validate Engine No format if provided (warning or check length if required)
        if engine_no and len(engine_no) > 30:
            row_errors.append(ValidationError(
                row_number=row_idx,
                source_id=record_id,
                column="Vehicle Engine No (LAST 5 DIGITS)",
                error_message=f"Engine number '{engine_no}' exceeds expected maximum length."
            ))

        status = RecordStatus.READY if not row_errors else RecordStatus.INVALID

        record = CsvRecord(
            row_number=row_idx,
            id=record_id,
            vltd_maker=vltd_maker,
            vltd_model=vltd_model,
            vltd_serial_number=vltd_serial_number,
            provider=provider,
            service_provider=provider,
            imei_number=imei_number,
            imei=imei_number,
            icc_id=icc_id or None,
            registration_type=registration_type,
            chassis_no=chassis_no or None,
            engine_no=engine_no or None,
            vehicle_state=vehicle_state or None,
            rto=rto or None,
            vehicle_registration_number=vehicle_reg_no or None,
            raw_data=raw_dict,
            status=status,
            transaction_state=TransactionState.READY if status == RecordStatus.READY else TransactionState.FAILED,
            validation_errors=row_errors
        )
        records.append(record)
        all_errors.extend(row_errors)

    return records, all_errors, normalized_headers
