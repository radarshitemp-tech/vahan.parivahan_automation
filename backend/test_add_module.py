# backend/test_add_module.py
"""
Exhaustive Unit Test Suite for Part 2: Add / Fitment VLTD Module.
Covers:
1. CSV Ingestion & Validation (Happy path, missing columns, malformed data, header aliases, edge cases).
2. Field Mapping & Progressive Discovery (11 columns, complete/incomplete configurations, dry-run).
3. Transaction Lifecycle & State Transitions (Success, error recovery, session timeout pause, user stop).
4. Add Module Router & Central Registry Integration.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import io
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from validator import parse_and_validate_csv, validate_imei
from models import (
    BatchResponse,
    BatchState,
    BatchSummary,
    CsvRecord,
    RecordStatus,
    TransactionState,
    ExecutionType,
    LogLevel,
    BatchMappingConfig,
    FieldMappingItem,
    DiscoveredFormField,
    FormFieldOption
)
from selenium_worker import VahanSeleniumWorker
from modules.registry import module_registry
from modules.add.router import router as add_router

class TestAddModuleValidation(unittest.TestCase):
    """Tests for CSV validation and parsing in the Add Module."""

    def test_valid_11_column_csv_parsing(self):
        """Happy Path: Standard valid CSV parses successfully preserving types and leading zeros."""
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type,Vehicle Registration Number,Chassis Number,Engine Number,State\n"
            "00101,VASP INFOTECH,VASP-01,00891234,BSNL IoT,864321045678912,Retrofitment,WB57D1709,CHAS1234567890123,ENG1234567,West Bengal\n"
            "00102,MINDA ICONNECT,MIC-X1,00891235,Airtel IoT,864321045678913,New Vehicle,MH09GJ9036,CHAS1234567890124,ENG1234568,Maharashtra\n"
        )
        records, errors, headers = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(errors), 0)
        self.assertEqual(records[0].id, "00101")
        self.assertEqual(records[0].vltd_serial_number, "00891234")
        self.assertEqual(records[0].status, RecordStatus.READY)
        self.assertEqual(records[1].id, "00102")

    def test_header_casing_and_whitespace_trimming(self):
        """Edge Case: Headers with irregular whitespace and casing are normalized."""
        csv_content = (
            "  id  ,  vltd maker , VLTD MODEL , vltd serial number , PROVIDER , imei number , registration type  \n"
            "00101,VASP INFOTECH,VASP-01,00891234,BSNL Telecom,864321045678912,Retrofitment\n"
        )
        records, errors, _ = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, RecordStatus.READY)
        self.assertEqual(records[0].vltd_maker, "VASP INFOTECH")

    def test_utf8_bom_and_crlf_handling(self):
        """Edge Case: CSV formatted with UTF-8 BOM and Windows CRLF line terminators."""
        csv_content = (
            "\ufeffID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\r\n"
            "00101,VASP INFOTECH,VASP-01,00891234,BSNL,864321045678912,Retrofitment\r\n"
        )
        records, errors, _ = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, "00101")
        self.assertEqual(len(errors), 0)

    def test_missing_mandatory_columns_raises_error(self):
        """Edge Case: CSV missing required column 'IMEI Number' raises descriptive ValueError."""
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,Registration Type\n"
            "00101,VASP,VASP-01,00891234,BSNL,Retrofitment\n"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_and_validate_csv(csv_content)
        self.assertIn("Missing required CSV column headers", str(ctx.exception))
        self.assertIn("IMEI Number", str(ctx.exception))

    def test_empty_csv_and_headers_only(self):
        """Edge Case: Completely empty CSV or headers-only CSV."""
        with self.assertRaises(ValueError):
            parse_and_validate_csv("")

        with self.assertRaises(ValueError):
            parse_and_validate_csv("   \n  \n  ")

        # Headers only: valid headers but 0 data rows
        headers_only = "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
        records, errors, headers = parse_and_validate_csv(headers_only)
        self.assertEqual(len(records), 0)
        self.assertEqual(len(errors), 0)

    def test_imei_validation_rules(self):
        """Edge Cases: IMEI validation with valid, invalid length, and non-numeric inputs."""
        self.assertTrue(validate_imei("864321045678912"))
        self.assertFalse(validate_imei("12345"))             # Under 15 digits
        self.assertFalse(validate_imei("86432104567891234")) # Over 15 digits
        self.assertFalse(validate_imei("86432104567891A"))   # Non-numeric
        self.assertFalse(validate_imei(""))                  # Empty
        self.assertFalse(validate_imei(None))                # None

    def test_duplicate_record_id_handling(self):
        """Edge Case: Duplicate IDs within the same CSV batch are marked INVALID."""
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "REC-01,VASP,VASP-01,SN001,BSNL,864321045678912,Retrofitment\n"
            "REC-01,VASP,VASP-01,SN002,BSNL,864321045678913,Retrofitment\n"
        )
        records, errors, _ = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].status, RecordStatus.READY)
        self.assertEqual(records[1].status, RecordStatus.INVALID)
        self.assertTrue(any("Duplicate ID" in e.error_message for e in errors))


class TestAddModuleMappingAndDryRun(unittest.TestCase):
    """Tests for field discovery, auto-mapping, and dry-run execution."""

    def setUp(self):
        self.worker = VahanSeleniumWorker()

    def test_complete_field_mapping_generation(self):
        """Happy Path: Generates 100% complete suggested mapping for all discovered portal fields."""
        portal_fields = [
            DiscoveredFormField(id="kit_maker_input", name="maker", tag="select", input_type="select", label="VLTD Maker*", is_required=True, options=[FormFieldOption(label="VASP INFOTECH", value="VASP")]),
            DiscoveredFormField(id="kit_alloted_model_input", name="model", tag="select", input_type="select", label="VLTD Model*", is_required=True, options=[FormFieldOption(label="VASP-01", value="M01")]),
            DiscoveredFormField(id="serialNo_input", name="serialNo", tag="input", input_type="text", label="VLTD serial Number:*", is_required=True),
            DiscoveredFormField(id="tf_serPro", name="provider", tag="input", input_type="text", label="Network Service Provider", is_required=True),
            DiscoveredFormField(id="tf_imei", name="imei", tag="input", input_type="text", label="IMEI Number:", is_required=True),
            DiscoveredFormField(id="reg_type_input", name="regType", tag="select", input_type="select", label="Registration Type*", is_required=True, options=[FormFieldOption(label="Retrofitment", value="RETRO")]),
        ]

        custom_cols = ["ID", "VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider", "IMEI Number", "Registration Type"]
        mapping_config = self.worker.generate_suggested_mapping("batch-add-101", portal_fields, custom_columns=custom_cols)

        self.assertTrue(mapping_config.is_complete)
        self.assertEqual(len(mapping_config.missing_required_fields), 0)
        self.assertEqual(mapping_config.mappings["VLTD Maker"].target_field_id, "kit_maker_input")
        self.assertEqual(mapping_config.mappings["IMEI Number"].target_field_id, "tf_imei")
        self.assertEqual(mapping_config.mappings["VLTD serial Number"].target_field_id, "serialNo_input")

    def test_incomplete_mapping_detects_missing_fields(self):
        """Edge Case: Missing required target fields on portal marks mapping incomplete."""
        partial_fields = [
            DiscoveredFormField(id="kit_maker_input", name="maker", tag="select", label="VLTD Maker"),
        ]
        mapping_config = self.worker.generate_suggested_mapping("batch-add-102", partial_fields)
        self.assertFalse(mapping_config.is_complete)
        self.assertIn("IMEI Number", mapping_config.missing_required_fields)
        self.assertIn("VLTD serial Number", mapping_config.missing_required_fields)

    def test_dry_run_requires_active_browser_session(self):
        """Edge Case: Dry-run rejects execution if browser is not launched."""
        record = CsvRecord(
            row_number=2,
            id="00101",
            vltd_maker="VASP INFOTECH",
            vltd_model="VASP-01",
            vltd_serial_number="00891234",
            provider="BSNL",
            imei_number="864321045678912",
            registration_type="Retrofitment",
            raw_data={"ID": "00101", "VLTD Maker": "VASP INFOTECH", "VLTD Model": "VASP-01", "VLTD serial Number": "00891234", "Provider": "BSNL", "IMEI Number": "864321045678912", "Registration Type": "Retrofitment"},
            status=RecordStatus.READY
        )
        mapping_config = BatchMappingConfig(batch_id="batch-add-103", is_complete=True, mappings={})

        self.worker.is_session_alive = lambda: False
        with self.assertRaises(RuntimeError) as ctx:
            self.worker.dry_run_autofill(record, mapping_config)
        self.assertIn("Active Chrome browser session not found", str(ctx.exception))


class TestAddModuleTransactionLifecycle(unittest.TestCase):
    """Tests for batch processing lifecycle, error handling, session pausing, and stop signals."""

    def setUp(self):
        self.worker = VahanSeleniumWorker()
        mock_driver = MagicMock()
        mock_driver.current_window_handle = "handle-1"
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"
        mock_driver.find_element.return_value.text = "VAHAN Portal"
        self.worker.driver = mock_driver
        self.worker.is_session_alive = lambda: True
        self.worker.stop_requested.clear()
        self.worker.pause_requested.clear()

    def _create_mock_batch(self, batch_id: str, record_count: int = 2) -> BatchResponse:
        records = []
        for i in range(1, record_count + 1):
            records.append(
                CsvRecord(
                    row_number=i + 1,
                    id=f"0010{i}",
                    vltd_maker="VASP INFOTECH",
                    vltd_model="VASP-01",
                    vltd_serial_number=f"SN00{i}",
                    provider="BSNL",
                    imei_number=f"86432104567891{i}",
                    registration_type="Retrofitment",
                    raw_data={
                        "ID": f"0010{i}",
                        "VLTD Maker": "VASP INFOTECH",
                        "VLTD Model": "VASP-01",
                        "VLTD serial Number": f"SN00{i}",
                        "Provider": "BSNL",
                        "IMEI Number": f"86432104567891{i}",
                        "Registration Type": "Retrofitment"
                    },
                    status=RecordStatus.READY
                )
            )

        mappings = {
            "VLTD Maker": FieldMappingItem(csv_column="VLTD Maker", target_field_id="kit_maker_input", target_field_label="VLTD Maker*", is_required=True),
            "VLTD Model": FieldMappingItem(csv_column="VLTD Model", target_field_id="kit_alloted_model_input", target_field_label="VLTD Model*", is_required=True),
            "VLTD serial Number": FieldMappingItem(csv_column="VLTD serial Number", target_field_id="serialNo_input", target_field_label="VLTD serial Number:*", is_required=True),
            "Provider": FieldMappingItem(csv_column="Provider", target_field_id="tf_serPro", target_field_label="Provider", is_required=True),
            "IMEI Number": FieldMappingItem(csv_column="IMEI Number", target_field_id="tf_imei", target_field_label="IMEI Number:", is_required=True),
            "Registration Type": FieldMappingItem(csv_column="Registration Type", target_field_id="reg_type_input", target_field_label="Registration Type", is_required=True),
        }

        mapping_config = BatchMappingConfig(batch_id=batch_id, is_complete=True, mappings=mappings)
        return BatchResponse(
            batch_id=batch_id,
            file_name="test_add.csv",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=record_count, valid_records_count=record_count),
            records=records,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            mapping=mapping_config
        )

    def test_incomplete_mapping_halts_batch_immediately(self):
        """Edge Case: Batch with incomplete mapping halts without interacting with portal."""
        batch = self._create_mock_batch("batch-incomplete", record_count=1)
        batch.mapping.is_complete = False
        batch.mapping.missing_required_fields = ["IMEI Number"]

        self.worker._process_sequential_records_worker(batch, mode="batch")
        self.assertEqual(batch.state, BatchState.COMPLETED_WITH_ERRORS)
        self.assertIn("Incomplete field mapping", batch.summary.current_error_message)

    def test_successful_sequential_batch_processing(self):
        """Happy Path: Two records processed sequentially to complete SUCCESS status."""
        batch = self._create_mock_batch("batch-success-2", record_count=2)

        def mock_execute(record, b, m, txn_id):
            record.status = RecordStatus.SUCCESS
            record.portal_confirmation_ref = f"CONF_{record.id}"
            record.execution_message = "Successfully Fit"
            return True, "Successfully Fit", True

        with patch.object(self.worker, '_execute_record_transaction', side_effect=mock_execute):
            with patch.object(self.worker, '_reset_form_for_next_record'):
                self.worker._process_sequential_records_worker(batch, mode="batch")

        self.assertEqual(batch.state, BatchState.COMPLETED)
        self.assertEqual(batch.summary.successful_count, 2)
        self.assertEqual(batch.summary.failed_count, 0)
        self.assertEqual(batch.records[0].status, RecordStatus.SUCCESS)
        self.assertEqual(batch.records[0].portal_confirmation_ref, "CONF_00101")
        self.assertEqual(batch.records[1].status, RecordStatus.SUCCESS)

    def test_row_error_recovery_continues_to_next_record(self):
        """Edge Case: Row 2 fails safely before commit; form restores and Row 3 succeeds."""
        batch = self._create_mock_batch("batch-error-recovery", record_count=2)

        def mock_execute(record, b, m, txn_id):
            if record.row_number == 2:
                record.status = RecordStatus.FAILED
                record.execution_message = "Dropdown option not found on portal"
                return False, "Dropdown option not found on portal", True
            record.status = RecordStatus.SUCCESS
            record.portal_confirmation_ref = f"CONF_{record.id}"
            record.execution_message = "Success"
            return True, "Success", True

        with patch.object(self.worker, '_execute_record_transaction', side_effect=mock_execute):
            with patch.object(self.worker, '_reset_form_for_next_record'):
                self.worker._process_sequential_records_worker(batch, mode="batch")

        self.assertEqual(batch.state, BatchState.COMPLETED_WITH_ERRORS)
        self.assertEqual(batch.summary.successful_count, 1)
        self.assertEqual(batch.summary.failed_count, 1)
        self.assertEqual(batch.records[0].status, RecordStatus.FAILED)
        self.assertEqual(batch.records[1].status, RecordStatus.SUCCESS)

    def test_session_expiry_pauses_batch(self):
        """Edge Case: Portal session redirect to login.xhtml pauses batch in PAUSED_AUTH_REQUIRED."""
        batch = self._create_mock_batch("batch-session-timeout", record_count=1)

        # Mock auth failure simulating session timeout
        auth_err = "Portal session expired or at login page (https://vahan.parivahan.gov.in/vahan/login.xhtml)."
        with patch.object(VahanSeleniumWorker, "verify_session", return_value=(False, auth_err)):
            self.worker._process_sequential_records_worker(batch, mode="batch")

        self.assertEqual(batch.state, BatchState.PAUSED_AUTH_REQUIRED)
        self.assertEqual(batch.summary.successful_count, 0)
        self.assertEqual(batch.summary.failed_count, 0)

    def test_user_stop_request_acknowledgement(self):
        """Edge Case: User triggers request_stop(), halts execution between atomic steps."""
        self.worker.stop_requested.clear()
        self.assertFalse(self.worker.stop_requested.is_set())
        self.worker.request_stop()
        self.assertTrue(self.worker.stop_requested.is_set())


class TestAddModuleRouterAndRegistry(unittest.TestCase):
    """Tests for Add Module FastAPI router and Module Registry configuration."""

    def test_registry_registration(self):
        """Verify Add Module registration in centralized registry."""
        mod = module_registry.get("add_vltd")
        self.assertIsNotNone(mod)
        self.assertEqual(mod.module_id, "add_vltd")
        self.assertEqual(mod.frontend_route, "/modules/add")
        self.assertEqual(mod.api_prefix, "/api/modules/add")
        self.assertTrue(mod.is_enabled)
        self.assertIn("VLTD Maker", mod.required_fields)

    def test_router_status_endpoint(self):
        """Verify GET /api/modules/add/status endpoint response."""
        from modules.add.router import get_add_module_status

        data = get_add_module_status()
        self.assertEqual(data["module"], "add_vltd")
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["route"], "/modules/add")


if __name__ == "__main__":
    unittest.main()
