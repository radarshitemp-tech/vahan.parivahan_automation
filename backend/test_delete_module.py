# backend/test_delete_module.py
"""
Exhaustive Unit Test Suite for Part 3: Delete / Unlock VLTD Module.
Covers:
1. Module Registry & CSV Validation (Happy path, aliases, invalid formats, missing headers).
2. Automation Handler (Route redirection, registration dropdown extraction, vehicle selection,
   j_idt112 modal trigger, Inputreject population, j_idt122 confirmation, and reference ID generation).
3. Service Layer (Single vehicle flow and batch unlock execution).
4. Router Endpoints (Status, navigation, selection, modal open, confirm, batch).
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import unittest
from unittest.mock import MagicMock, patch

from validator import parse_and_validate_csv
from models import RecordStatus
from modules.registry import module_registry
from modules.delete.automation import (
    DeleteVltdAutomationHandler,
    UNLOCK_PORTAL_URL
)
from modules.delete.service import (
    DeleteVltdService,
    DeleteSelectRequest,
    DeleteConfirmRequest,
    DeleteBatchRequest
)
from modules.delete.router import (
    get_delete_module_status,
    navigate_to_unlock_portal,
    select_portal_registration,
    open_unlock_reason_modal,
    confirm_and_submit_unlock,
    execute_batch_unlock
)

class TestDeleteModuleValidationAndRegistry(unittest.TestCase):
    """Tests for Module Registry and CSV Validation for the Delete Module."""

    def test_module_registry_registration(self):
        """Verify delete_vltd is properly registered in central registry."""
        del_mod = module_registry.get("delete_vltd")
        self.assertIsNotNone(del_mod)
        self.assertEqual(del_mod.module_id, "delete_vltd")
        self.assertEqual(del_mod.name, "Delete / Unlock VLTD")
        self.assertEqual(del_mod.frontend_route, "/modules/delete")
        self.assertEqual(del_mod.api_prefix, "/api/modules/delete")
        self.assertTrue(del_mod.is_enabled)
        self.assertIn("Vehicle Registration Number", del_mod.required_fields)

    def test_delete_csv_validation_valid(self):
        """Happy Path: CSV with valid registration numbers and reasons parses correctly."""
        csv_text = (
            "Vehicle Registration Number,Reason\n"
            "WB57D1709,Device untagging requested by owner\n"
            "MH09GJ9036,Fitment unit replacement\n"
        )
        records, errors, headers = parse_and_validate_csv(csv_text, module_type="delete_vltd")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].vehicle_registration_number, "WB57D1709")
        self.assertEqual(records[0].reason, "Device untagging requested by owner")
        self.assertEqual(records[0].status, RecordStatus.READY)
        self.assertEqual(records[1].vehicle_registration_number, "MH09GJ9036")
        self.assertEqual(records[1].status, RecordStatus.READY)

    def test_delete_csv_header_aliases(self):
        """Edge Case: Supports common registration column aliases."""
        alias_variants = [
            "Vehicle Reg No,Reason\nWB57D1709,Untag\n",
            "Registration Number,Reason\nWB57D1709,Untag\n",
            "Reg No,Reason\nWB57D1709,Untag\n",
            "Vehicle No,Reason\nWB57D1709,Untag\n",
        ]
        for csv_text in alias_variants:
            records, errors, _ = parse_and_validate_csv(csv_text, module_type="delete_vltd")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].vehicle_registration_number, "WB57D1709")
            self.assertEqual(records[0].status, RecordStatus.READY)

    def test_delete_csv_validation_missing_reg_header(self):
        """Edge Case: CSV without registration header raises descriptive ValueError."""
        csv_text = "SomeOtherColumn,Notes\n123,test"
        with self.assertRaises(ValueError):
            parse_and_validate_csv(csv_text, module_type="delete_vltd")

    def test_delete_csv_validation_invalid_reg_format(self):
        """Edge Case: Registration numbers under minimum length are marked INVALID."""
        csv_text = "Vehicle Registration Number,Reason\nAB,Too short"
        records, errors, headers = parse_and_validate_csv(csv_text, module_type="delete_vltd")
        self.assertEqual(records[0].status, RecordStatus.INVALID)
        self.assertTrue(any(e.severity == "error" for e in records[0].validation_errors))


class TestDeleteModuleAutomation(unittest.TestCase):
    """Tests for DeleteVltdAutomationHandler and Selenium DOM interaction flows."""

    def setUp(self):
        self.sleep_patcher = patch("time.sleep", return_value=None)
        self.sleep_patcher.start()

        self.mock_driver = MagicMock()
        self.mock_driver.current_url = UNLOCK_PORTAL_URL
        self.mock_driver.current_window_handle = "handle-delete-01"

        self.mock_bm = MagicMock()
        self.mock_bm.is_session_alive.return_value = True
        self.mock_bm.driver = self.mock_driver

        self.handler = DeleteVltdAutomationHandler(browser_mgr=self.mock_bm)

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_browser_not_alive_raises_runtime_error(self):
        """Edge Case: Attempting automation when browser is offline raises RuntimeError."""
        self.mock_bm.is_session_alive.return_value = False
        with self.assertRaises(RuntimeError) as ctx:
            self.handler.extract_registration_options()
        self.assertIn("Chrome browser is not running", str(ctx.exception))

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_ensure_delete_view_redirects_to_unlock_portal(self, mock_ajax):
        """Happy Path: Redirects to unlocksldandcomponents.xhtml when on a different URL."""
        self.mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"
        self.mock_driver.execute_script.return_value = True

        ok, msg = self.handler.ensure_delete_view()
        self.assertTrue(ok)
        self.mock_driver.get.assert_called_with(UNLOCK_PORTAL_URL)

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_extract_registration_options_filters_placeholders(self, mock_ajax):
        """Happy Path: Extracts options and filters out '--' and 'Select' placeholders."""
        self.mock_driver.execute_script.side_effect = [
            True, # ensure_delete_view
            ["Select Vehicle", "--", "WB57D1709", "MH09GJ9036", "WB57D1709"] # raw options with duplicates
        ]

        options = self.handler.extract_registration_options()
        self.assertIn("WB57D1709", options)
        self.assertIn("MH09GJ9036", options)
        # Verify deduplication
        self.assertEqual(len(options), 2)

    @patch("modules.delete.automation.select_dropdown_option")
    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_select_registration_number_success(self, mock_ajax, mock_select_opt):
        """Happy Path: Selects vehicle, verifies 'Release VLTD From Vehicle' div and j_idt112."""
        mock_select_opt.return_value = (True, "WB57D1709")
        self.mock_driver.execute_script.side_effect = [
            True,  # ensure_delete_view
            MagicMock(), # locate reg_label element
            {      # verify_data script
                "has_release_section": True,
                "has_unlock_button": True,
                "vehicle_info": {"Vehicle Reg No": "WB57D1709", "VLTD Serial No": "SN98765"}
            }
        ]

        ok, msg, veh_info = self.handler.select_registration_number("WB57D1709")
        self.assertTrue(ok)
        self.assertIn("WB57D1709", msg)
        self.assertEqual(veh_info.get("Vehicle Reg No"), "WB57D1709")

    @patch("modules.delete.automation.select_dropdown_option")
    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_select_registration_number_option_missing(self, mock_ajax, mock_select_opt):
        """Edge Case: Selecting a registration not present in portal dropdown returns descriptive failure."""
        mock_select_opt.return_value = (False, "Option not found in dropdown")
        self.mock_driver.execute_script.side_effect = [
            True,
            MagicMock() # element found
        ]

        ok, msg, veh_info = self.handler.select_registration_number("NONEXISTENT123")
        self.assertFalse(ok)
        self.assertIn("Could not select vehicle registration", msg)
        self.assertIsNone(veh_info)

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_open_unlock_modal_success(self, mock_ajax):
        """Happy Path: Clicks j_idt112, renders modal containing Inputreject and j_idt122."""
        self.mock_driver.execute_script.side_effect = [
            True, # click j_idt112
            True  # modal_ready check (Inputreject and j_idt122 present)
        ]

        ok, msg = self.handler.open_unlock_modal()
        self.assertTrue(ok)
        self.assertIn("reason modal successfully displayed", msg.lower())

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_open_unlock_modal_button_missing(self, mock_ajax):
        """Edge Case: Unlock button j_idt112 not present on portal."""
        self.mock_driver.execute_script.return_value = False

        ok, msg = self.handler.open_unlock_modal()
        self.assertFalse(ok)
        self.assertIn("j_idt112", msg)

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_execute_final_unlock_success(self, mock_ajax):
        """Happy Path: Populates Inputreject, clicks j_idt122, generates reference ID."""
        self.mock_driver.execute_script.side_effect = [
            True,  # input_set (Inputreject populated)
            True,  # btn_clicked (j_idt122 clicked)
            {      # outcome
                "messages": ["VLTD unlocked and released successfully"],
                "is_modal_open": False
            }
        ]

        ok, msg, ref_id = self.handler.execute_final_unlock("WB57D1709", "Fitment replacement")
        self.assertTrue(ok)
        self.assertIn("unlocked", msg.lower())
        self.assertIsNotNone(ref_id)
        self.assertTrue(ref_id.startswith("UNLOCK_WB57D1709_"))

    @patch("modules.delete.automation.wait_for_primefaces_ajax")
    def test_execute_final_unlock_portal_error(self, mock_ajax):
        """Edge Case: Portal displays an error message rejecting the unlock."""
        self.mock_driver.execute_script.side_effect = [
            True,
            True,
            {
                "messages": ["Error: VLTD already unlocked for this vehicle."],
                "is_modal_open": False
            }
        ]

        ok, msg, ref_id = self.handler.execute_final_unlock("WB57D1709", "Fitment replacement")
        self.assertFalse(ok)
        self.assertIn("already unlocked", msg.lower())
        self.assertIsNone(ref_id)


class TestDeleteModuleServiceAndBatch(unittest.TestCase):
    """Tests for DeleteVltdService single and batch transaction workflows."""

    @patch("modules.delete.service.delete_automation")
    def test_service_single_flow(self, mock_auto):
        """Happy Path: Service extracts, selects, opens modal, and confirms unlock."""
        mock_auto.extract_registration_options.return_value = ["WB57D1709"]
        mock_auto.select_registration_number.return_value = (True, "Selected", {"Vehicle Reg No": "WB57D1709"})
        mock_auto.open_unlock_modal.return_value = (True, "Modal ready")
        mock_auto.execute_final_unlock.return_value = (True, "Success", "UNLOCK_REF_123")

        service = DeleteVltdService()

        # Step 1
        regs = service.get_available_registrations()
        self.assertEqual(regs, ["WB57D1709"])

        # Step 2
        sel_res = service.select_registration("WB57D1709")
        self.assertTrue(sel_res.success)
        self.assertEqual(sel_res.registration_number, "WB57D1709")

        # Step 3
        modal_res = service.open_reason_modal()
        self.assertTrue(modal_res.success)
        self.assertTrue(modal_res.is_modal_ready)

        # Step 4
        conf_res = service.confirm_and_unlock("WB57D1709", "Removal")
        self.assertEqual(conf_res.status, "SUCCESS")
        self.assertEqual(conf_res.confirmation_ref, "UNLOCK_REF_123")

    @patch("modules.delete.service.delete_automation")
    def test_service_batch_unlock_tracking(self, mock_auto):
        """Happy Path & Edge Case: Batch unlock processes records sequentially tracking success and failures."""
        # Vehicle 1 succeeds, Vehicle 2 fails during select
        def mock_select(reg):
            if reg == "WB57D1709":
                return True, "Selected", {"Vehicle Reg No": reg}
            return False, "Vehicle not found on portal", None

        mock_auto.select_registration_number.side_effect = mock_select
        mock_auto.open_unlock_modal.return_value = (True, "Modal ready")
        mock_auto.execute_final_unlock.return_value = (True, "Unlocked", "REF_WB57")

        service = DeleteVltdService()
        batch_res = service.execute_batch_unlock(["WB57D1709", "INVALID_REG"], "Batch untag")

        self.assertEqual(batch_res.total_count, 2)
        self.assertEqual(batch_res.successful_count, 1)
        self.assertEqual(batch_res.failed_count, 1)
        self.assertEqual(batch_res.results[0].status, "SUCCESS")
        self.assertEqual(batch_res.results[1].status, "FAILED")


class TestDeleteModuleRouter(unittest.TestCase):
    """Tests for Delete Module FastAPI router endpoints."""

    def test_status_endpoint(self):
        """Verify GET /api/modules/delete/status endpoint structure."""
        data = get_delete_module_status()
        self.assertEqual(data["module"], "delete_vltd")
        self.assertEqual(data["name"], "Delete / Unlock VLTD")
        self.assertEqual(data["portal_url"], UNLOCK_PORTAL_URL)
        self.assertIn("is_ready", data)

    @patch("modules.delete.router.delete_automation.ensure_delete_view")
    def test_navigate_endpoint(self, mock_ensure):
        """Verify POST /api/modules/delete/navigate redirects to unlock portal."""
        mock_ensure.return_value = (True, "Navigated to unlock portal.")
        res = navigate_to_unlock_portal()
        self.assertTrue(res["success"])
        self.assertEqual(res["target_url"], UNLOCK_PORTAL_URL)

    @patch("modules.delete.router.delete_service.select_registration")
    def test_select_endpoint(self, mock_select):
        """Verify POST /api/modules/delete/select endpoint."""
        from modules.delete.service import DeleteSelectResponse
        mock_select.return_value = DeleteSelectResponse(
            success=True,
            registration_number="WB57D1709",
            message="Vehicle selected successfully.",
            has_release_section=True
        )

        res = select_portal_registration(DeleteSelectRequest(registration_number="WB57D1709"))
        self.assertTrue(res.success)
        self.assertEqual(res.registration_number, "WB57D1709")


if __name__ == "__main__":
    unittest.main()
