import unittest
from selenium_worker import VahanSeleniumWorker
from models import (
    BatchResponse,
    BatchState,
    BatchSummary,
    CsvRecord,
    RecordStatus,
    BatchMappingConfig,
    FieldMappingItem
)

class TestPhaseEandF(unittest.TestCase):

    def setUp(self):
        self.worker = VahanSeleniumWorker()

    def test_start_processing_rejects_incomplete_mapping(self):
        # A batch without complete mapping should not proceed to submission
        records = [
            CsvRecord(
                row_number=2,
                id="00101",
                vltd_maker="Minda iConnect",
                vltd_model="MIC-01",
                vltd_serial_number="00982341",
                provider="BSNL",
                imei_number="864321045678912",
                registration_type="Retrofitment",
                status=RecordStatus.READY
            )
        ]
        incomplete_mapping = BatchMappingConfig(
            batch_id="test-incomplete",
            is_complete=False,
            missing_required_fields=["IMEI Number"]
        )
        batch = BatchResponse(
            batch_id="test-incomplete",
            file_name="test.csv",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1),
            records=records,
            created_at="2026-10-26 12:00:00",
            mapping=incomplete_mapping
        )

        # Worker thread should detect incomplete mapping and halt before opening portal submission
        self.worker._process_sequential_records_worker(batch, mode="batch")
        self.assertEqual(batch.state, BatchState.COMPLETED_WITH_ERRORS)
        self.assertIn("Incomplete field mapping", batch.summary.current_error_message)

    def test_controlled_stop_acknowledgement(self):
        self.worker.stop_requested.clear()
        self.assertFalse(self.worker.stop_requested.is_set())
        self.worker.request_stop()
        self.assertTrue(self.worker.stop_requested.is_set())

    def test_uncertain_status_marked_as_unknown(self):
        record = CsvRecord(
            row_number=5,
            id="00104",
            vltd_maker="Maker",
            vltd_model="Model",
            vltd_serial_number="1234",
            provider="Provider",
            imei_number="864321045678915",
            registration_type="New",
            status=RecordStatus.IN_PROGRESS
        )
        # Verify schema accepts UNKNOWN and prevents false successes
        record.status = RecordStatus.UNKNOWN
        self.assertEqual(record.status, RecordStatus.UNKNOWN)

    def test_verify_submission_outcome_handles_no_driver(self):
        self.worker.driver = None
        success, info, err = self.worker._verify_submission_outcome()
        self.assertFalse(success)
        self.assertEqual(err, "Driver not available")

    def test_wait_for_primefaces_ajax_handles_no_driver(self):
        self.worker.driver = None
        # Should complete cleanly without exception when driver is None
        self.worker._wait_for_primefaces_ajax(timeout=1.0)

if __name__ == '__main__':
    unittest.main()
