import unittest
from selenium_worker import VahanSeleniumWorker
from models import DiscoveredFormField, FormFieldOption, CsvRecord, RecordStatus, FieldMappingItem, BatchMappingConfig

class TestPhaseCandD(unittest.TestCase):

    def setUp(self):
        self.worker = VahanSeleniumWorker()

    def test_field_mapping_generation_complete(self):
        # Discovered fields from portal
        mock_fields = [
            DiscoveredFormField(id="vahan_maker_id", name="maker", tag="select", input_type="select", label="VLTD Maker Name", is_required=True, options=[FormFieldOption(label="Minda iConnect", value="MINDA")]),
            DiscoveredFormField(id="vahan_model_id", name="model", tag="input", input_type="text", label="Device Model", is_required=True),
            DiscoveredFormField(id="vahan_serial_id", name="serialNo", tag="input", input_type="text", label="VLTD Serial Number", is_required=True),
            DiscoveredFormField(id="vahan_provider_id", name="provider", tag="input", input_type="text", label="Network Provider", is_required=True),
            DiscoveredFormField(id="vahan_imei_id", name="imeiNo", tag="input", input_type="text", label="Device IMEI", is_required=True),
            DiscoveredFormField(id="vahan_regtype_id", name="regType", tag="select", input_type="select", label="Registration Type", is_required=True, options=[FormFieldOption(label="Retrofitment", value="RETRO")]),
        ]

        mapping_config = self.worker.generate_suggested_mapping("test-batch-001", mock_fields)
        self.assertTrue(mapping_config.is_complete)
        self.assertEqual(len(mapping_config.missing_required_fields), 0)
        self.assertEqual(mapping_config.mappings["VLTD Maker"].target_field_id, "vahan_maker_id")
        self.assertEqual(mapping_config.mappings["IMEI Number"].target_field_id, "vahan_imei_id")
        self.assertEqual(mapping_config.mappings["VLTD serial Number"].target_field_id, "vahan_serial_id")

    def test_field_mapping_generation_incomplete(self):
        # Discovered fields missing IMEI and Serial Number
        mock_fields = [
            DiscoveredFormField(id="vahan_maker_id", name="maker", tag="select", label="VLTD Maker"),
            DiscoveredFormField(id="vahan_model_id", name="model", tag="input", label="Device Model"),
        ]

        mapping_config = self.worker.generate_suggested_mapping("test-batch-002", mock_fields)
        self.assertFalse(mapping_config.is_complete)
        self.assertIn("IMEI Number", mapping_config.missing_required_fields)
        self.assertIn("VLTD serial Number", mapping_config.missing_required_fields)

    def test_dry_run_requires_active_browser(self):
        record = CsvRecord(
            row_number=2,
            id="00101",
            vltd_maker="Minda iConnect",
            vltd_model="MIC-VLTD-01",
            vltd_serial_number="00982341",
            provider="BSNL Telecom",
            imei_number="864321045678912",
            registration_type="Retrofitment",
            raw_data={"ID": "00101", "VLTD Maker": "Minda iConnect", "VLTD Model": "MIC-VLTD-01", "VLTD serial Number": "00982341", "Provider": "BSNL Telecom", "IMEI Number": "864321045678912", "Registration Type": "Retrofitment"},
            status=RecordStatus.READY
        )
        mapping_config = BatchMappingConfig(batch_id="test-batch-003", is_complete=True, mappings={})
        
        # When browser is not launched, must throw RuntimeError protecting against silent failure
        self.worker.is_session_alive = lambda: False
        with self.assertRaises(RuntimeError) as ctx:
            self.worker.dry_run_autofill(record, mapping_config)
        self.assertIn("Active Chrome browser session not found", str(ctx.exception))

    def test_custom_columns_mapping(self):
        custom_cols = ["ID", "maker", "model", "serial"]
        mock_fields = [
            DiscoveredFormField(id="tf_maker", name="tf_maker", tag="select", label="Maker"),
            DiscoveredFormField(id="tf_model", name="tf_model", tag="select", label="Model"),
            DiscoveredFormField(id="tf_serial", name="tf_serial", tag="input", label="Serial"),
        ]
        mapping_config = self.worker.generate_suggested_mapping("test-batch-custom", mock_fields, custom_columns=custom_cols)
        self.assertIn("maker", mapping_config.mappings)
        self.assertEqual(mapping_config.mappings["maker"].target_field_id, "tf_maker")

if __name__ == '__main__':
    unittest.main()
