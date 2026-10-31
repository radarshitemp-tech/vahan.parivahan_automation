import unittest
from validator import parse_and_validate_csv, validate_imei
from models import RecordStatus

class TestVahanCsvValidator(unittest.TestCase):

    def test_valid_csv_parsing_and_leading_zeros(self):
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "00101,Minda iConnect,MIC-VLTD-01,00982341,BSNL Telecom,864321045678912,Retrofitment\n"
            "00102,Rosmerta Autotech,RA-VLTD-X1,00982342,Airtel IoT,864321045678913,New\n"
        )
        records, errors, headers = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(errors), 0)
        # Verify leading zeros preserved
        self.assertEqual(records[0].id, "00101")
        self.assertEqual(records[0].vltd_serial_number, "00982341")
        self.assertEqual(records[0].status, RecordStatus.READY)

    def test_missing_required_headers(self):
        csv_content = (
            "ID,VLTD Maker,VLTD Model\n"
            "1,MakerA,ModelB\n"
        )
        with self.assertRaises(ValueError) as context:
            parse_and_validate_csv(csv_content)
        self.assertIn("Missing required CSV column headers", str(context.exception))

    def test_duplicate_id_detection(self):
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "00101,Minda iConnect,MIC-VLTD-01,00982341,BSNL Telecom,864321045678912,Retrofitment\n"
            "00101,Rosmerta Autotech,RA-VLTD-X1,00982342,Airtel IoT,864321045678913,New\n"
        )
        records, errors, headers = parse_and_validate_csv(csv_content)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1].status, RecordStatus.INVALID)
        self.assertTrue(any("Duplicate ID" in e.error_message for e in errors))

    def test_invalid_imei_length(self):
        self.assertTrue(validate_imei("864321045678912"))
        self.assertFalse(validate_imei("12345")) # too short
        self.assertFalse(validate_imei("864321045678912999")) # too long
        self.assertFalse(validate_imei("86432104567891A")) # non-numeric

        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "00101,Minda iConnect,MIC-VLTD-01,00982341,BSNL Telecom,12345,Retrofitment\n"
        )
        records, errors, _ = parse_and_validate_csv(csv_content)
        self.assertEqual(records[0].status, RecordStatus.INVALID)
        self.assertTrue(any("Invalid IMEI" in e.error_message for e in errors))

    def test_missing_required_values(self):
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "00101,,MIC-VLTD-01,00982341,,864321045678912,Retrofitment\n"
        )
        records, errors, _ = parse_and_validate_csv(csv_content)
        self.assertEqual(records[0].status, RecordStatus.INVALID)
        col_errors = [e.column for e in errors]
        self.assertIn("VLTD Maker", col_errors)
        self.assertIn("Provider", col_errors)

    def test_upload_batch_accepts_non_csv_filename_extension(self):
        import asyncio
        import io
        from starlette.datastructures import UploadFile as StarletteUploadFile
        from main import upload_and_validate_batch

        csv_bytes = (
            b"ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            b"00101,Minda iConnect,MIC-VLTD-01,00982341,BSNL Telecom,864321045678912,Retrofitment\n"
        )
        # Uploading with filename without .csv extension (e.g. from link 'pub?output=csv' or direct export)
        upload_file = StarletteUploadFile(file=io.BytesIO(csv_bytes), filename="pub")
        response = asyncio.run(upload_and_validate_batch(upload_file))

        self.assertIsNotNone(response.batch_id)
        self.assertEqual(response.summary.total_records, 1)
        self.assertEqual(response.summary.valid_records_count, 1)
        self.assertEqual(response.summary.invalid_records_count, 0)
        self.assertEqual(response.file_name, "pub")

if __name__ == '__main__':
    unittest.main()
