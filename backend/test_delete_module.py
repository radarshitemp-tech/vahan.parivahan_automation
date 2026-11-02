# backend/test_delete_module.py
import unittest
from validator import parse_and_validate_csv
from models import RecordStatus
from modules.registry import module_registry

class TestDeleteModule(unittest.TestCase):
    def test_module_registry_registration(self):
        modules = module_registry.list_enabled()
        module_ids = [m.module_id for m in modules]
        self.assertIn("add_vltd", module_ids)
        self.assertIn("delete_vltd", module_ids)

        del_mod = module_registry.get("delete_vltd")
        self.assertIsNotNone(del_mod)
        self.assertEqual(del_mod.name, "Delete / Unlock VLTD")
        self.assertEqual(del_mod.frontend_route, "/modules/delete")

    def test_delete_csv_validation_valid(self):
        csv_text = "Vehicle Registration Number,Reason\nDL01AB1234,Old device removed\nUP16XY9999,Replacement"
        records, errors, headers = parse_and_validate_csv(csv_text, module_type="delete_vltd")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].vehicle_registration_number, "DL01AB1234")
        self.assertEqual(records[0].reason, "Old device removed")
        self.assertEqual(records[0].status, RecordStatus.READY)
        self.assertEqual(records[1].vehicle_registration_number, "UP16XY9999")
        self.assertEqual(records[1].status, RecordStatus.READY)

    def test_delete_csv_validation_missing_reg_header(self):
        csv_text = "SomeOtherColumn,Notes\n123,test"
        with self.assertRaises(ValueError):
            parse_and_validate_csv(csv_text, module_type="delete_vltd")

    def test_delete_csv_validation_invalid_reg_format(self):
        csv_text = "Vehicle Registration Number,Reason\nAB,Too short"
        records, errors, headers = parse_and_validate_csv(csv_text, module_type="delete_vltd")
        self.assertEqual(records[0].status, RecordStatus.INVALID)
        self.assertTrue(any(e.severity == "error" for e in records[0].validation_errors))

if __name__ == "__main__":
    unittest.main()

