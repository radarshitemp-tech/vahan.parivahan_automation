import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from selenium_worker import VahanSeleniumWorker
from logger_service import execution_logger, KOLKATA_TZ
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
    DiscoveredFormField
)

class TestTransactionLifecycle(unittest.TestCase):

    def setUp(self):
        self.worker = VahanSeleniumWorker()
        self.worker.driver = None
        self.worker.is_session_alive = lambda: True
        self.worker.stop_requested.clear()
        self.worker.pause_requested.clear()

    def test_structured_logger_format_and_timezone(self):
        """Verify timestamp is in Asia/Kolkata ISO 8601 format (+05:30) and sensitive data is masked."""
        run_id = "test-log-run-001"
        entry = execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.RECORD_EXECUTION,
            run_id=run_id,
            transaction_id="txn-001",
            csv_row=2,
            stage="FILLING_VLTD_DETAILS",
            action="SELECT_MAKER",
            result="SUCCESS",
            message="Populated VLTD Maker: Minda iConnect with secret password=12345",
            duration_ms=45.2
        )

        self.assertIn("+05:30", entry.timestamp)
        self.assertEqual(entry.level, LogLevel.INFO)
        self.assertEqual(entry.execution_type, ExecutionType.RECORD_EXECUTION)
        self.assertEqual(entry.run_id, run_id)
        self.assertEqual(entry.transaction_id, "txn-001")
        self.assertEqual(entry.csv_row, 2)
        # Ensure credentials masking
        self.assertNotIn("password=12345", entry.message)
        self.assertIn("[PROTECTED_AUTHENTICATION_CREDENTIAL]", entry.message)

        # Verify querying stored logs
        logs = execution_logger.get_logs(run_id=run_id, limit=10)
        self.assertTrue(len(logs) >= 1)
        self.assertEqual(logs[-1].transaction_id, "txn-001")

    def test_all_11_columns_in_suggested_mapping(self):
        """Verify all 11 mapped columns are generated with official VAHAN presets."""
        mapping_config = self.worker.generate_suggested_mapping("test-batch-11col", [])
        expected_columns = [
            "VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider",
            "IMEI Number", "ICC ID", "Registration Type", "Vehicle Chassis No",
            "Vehicle Engine No (LAST 5 DIGITS)", "Vehicle State", "RTO"
        ]
        for col in expected_columns:
            self.assertIn(col, mapping_config.mappings, f"Missing {col} in mappings")
            self.assertIsNotNone(mapping_config.mappings[col].target_field_id)

    def test_selected_subset_execution(self):
        """Verify worker executes only selected row numbers when specified."""
        rec1 = CsvRecord(
            row_number=2,
            id="00101",
            vltd_maker="Minda",
            vltd_model="M1",
            vltd_serial_number="001",
            provider="BSNL",
            imei_number="864321045678912",
            registration_type="Retrofitment",
            status=RecordStatus.READY
        )
        rec2 = CsvRecord(
            row_number=3,
            id="00102",
            vltd_maker="Rosmerta",
            vltd_model="R1",
            vltd_serial_number="002",
            provider="Airtel",
            imei_number="864321045678913",
            registration_type="New",
            status=RecordStatus.READY
        )
        batch = BatchResponse(
            batch_id="test-subset",
            file_name="test.csv",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=2, valid_records_count=2),
            records=[rec1, rec2],
            created_at="2026-10-27 12:00:00",
            mapping=self.worker.generate_suggested_mapping("test-subset", [])
        )

        mock_driver = MagicMock()
        mock_driver.current_window_handle = "handle-1"
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"
        mock_driver.find_element.return_value.text = "VAHAN Portal"
        self.worker.driver = mock_driver

        # Mock _execute_record_transaction to record which rows were processed
        executed_rows = []
        def mock_execute(record, b, m, txn_id):
            executed_rows.append(record.row_number)
            record.portal_confirmation_ref = f"VAHAN-{record.id}"
            return True, "Success", True

        with patch.object(self.worker, '_execute_record_transaction', side_effect=mock_execute):
            with patch.object(self.worker, '_reset_form_for_next_record'):
                # Process only row 3
                self.worker._process_sequential_records_worker(batch, mode="batch", selected_row_numbers=[3])

        self.assertEqual(executed_rows, [3])
        self.assertEqual(rec2.status, RecordStatus.SUCCESS)
        self.assertEqual(rec1.status, RecordStatus.READY) # row 2 was untouched

    def test_continue_on_error_recovers_and_processes_next_record(self):
        """Verify that an isolated record failure does not terminate the complete batch."""
        rec1 = CsvRecord(
            row_number=2,
            id="00101",
            vltd_maker="Minda",
            vltd_model="M1",
            vltd_serial_number="001",
            provider="BSNL",
            imei_number="864321045678912",
            registration_type="Retrofitment",
            status=RecordStatus.READY
        )
        rec2 = CsvRecord(
            row_number=3,
            id="00102",
            vltd_maker="Rosmerta",
            vltd_model="R1",
            vltd_serial_number="002",
            provider="Airtel",
            imei_number="864321045678913",
            registration_type="New",
            status=RecordStatus.READY
        )
        batch = BatchResponse(
            batch_id="test-continue-on-error",
            file_name="test.csv",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=2, valid_records_count=2),
            records=[rec1, rec2],
            created_at="2026-10-27 12:00:00",
            mapping=self.worker.generate_suggested_mapping("test-continue-on-error", [])
        )

        mock_driver = MagicMock()
        mock_driver.current_window_handle = "handle-1"
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"
        mock_driver.find_element.return_value.text = "VAHAN Portal"
        self.worker.driver = mock_driver

        # Simulate row 1 failing safely before commit, row 2 succeeding
        def mock_execute(record, b, m, txn_id):
            if record.row_number == 2:
                return False, "Dropdown option not found on portal", True # recoverable
            else:
                record.portal_confirmation_ref = f"VAHAN-{record.id}"
                return True, "Success", True

        with patch.object(self.worker, '_execute_record_transaction', side_effect=mock_execute):
            with patch.object(self.worker, '_reset_form_for_next_record'):
                self.worker._process_sequential_records_worker(batch, mode="batch")

        # Row 1 failed, Row 2 succeeded
        self.assertEqual(rec1.status, RecordStatus.FAILED)
        self.assertEqual(rec2.status, RecordStatus.SUCCESS)
        self.assertEqual(batch.summary.failed_count, 1)
        self.assertEqual(batch.summary.successful_count, 1)
        # Batch completed with errors rather than crashing on row 1
        self.assertEqual(batch.state, BatchState.COMPLETED_WITH_ERRORS)

    def test_session_expired_transitions_to_paused_auth_required(self):
        """Verify session timeout pauses batch safely without data corruption."""
        rec1 = CsvRecord(
            row_number=2,
            id="00101",
            vltd_maker="Minda",
            vltd_model="M1",
            vltd_serial_number="001",
            provider="BSNL",
            imei_number="864321045678912",
            registration_type="Retrofitment",
            status=RecordStatus.READY
        )
        batch = BatchResponse(
            batch_id="test-session-timeout",
            file_name="test.csv",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1),
            records=[rec1],
            created_at="2026-10-27 12:00:00",
            mapping=self.worker.generate_suggested_mapping("test-session-timeout", [])
        )

        mock_driver = MagicMock()
        mock_driver.current_window_handle = "handle-1"
        # Simulate redirect to login page
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vahan/login.xhtml"
        mock_driver.find_element.return_value.text = "Enter User ID"
        self.worker.driver = mock_driver

        self.worker._process_sequential_records_worker(batch, mode="batch")

        self.assertEqual(batch.state, BatchState.PAUSED_AUTH_REQUIRED)
        self.assertEqual(rec1.status, RecordStatus.PAUSED_AUTH_REQUIRED)
        self.assertEqual(rec1.transaction_state, TransactionState.PAUSED_AUTH_REQUIRED)
        self.assertIn("Session expired", rec1.execution_message)

if __name__ == '__main__':
    unittest.main()
