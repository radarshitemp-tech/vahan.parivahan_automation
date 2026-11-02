# backend/test_replace_module.py
"""
Exhaustive Unit Test Suite for Part 4: Untag / Replace VLTD Module.
Covers:
1. Module Registry & Option Definitions (Metadata, routes, required fields, S/D/I options).
2. Automation Handler:
   - Route verification and navigation to sldfittingDetails.xhtml.
   - Reason option selection ('S' Same Maker, 'D' Different Maker, 'I' Change ICCID).
   - PrimeFaces AJAX verification and error edge cases.
   - Form field inspection and parsing.
   - Fitment data population, Get Details (j_idt143) execution, and reference ID generation.
3. Service Layer (Single record transaction lifecycle and batch execution with aggregate stats).
4. Router Endpoints (Status, options, navigation, option select, inspect, single, batch).
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

# Patch time.sleep across modules during test runs to avoid delays
patcher = patch("time.sleep", return_value=None)
patcher.start()

from modules.registry import module_registry
from modules.replace.automation import (
    ReplaceVltdAutomationHandler,
    REPLACE_OPTIONS,
    REPLACE_PORTAL_URL
)
from modules.replace.service import (
    ReplaceVltdService,
    ReplaceOptionSelectRequest,
    ReplaceOptionSelectResponse,
    ReplaceFieldInfo,
    ReplaceInspectResponse,
    ReplaceSingleExecuteRequest,
    ReplaceSingleExecuteResponse,
    ReplaceBatchRequest,
    ReplaceBatchResponse
)
from modules.replace.router import (
    get_replace_module_status,
    get_replace_options,
    navigate_to_replace_portal,
    select_portal_option,
    inspect_portal_fields,
    execute_single_replace,
    execute_batch_replace
)


# ============================================================================
# PART 4.1: REGISTRY & OPTIONS SPECIFICATION TESTS
# ============================================================================

class TestReplaceModuleRegistryAndMetadata(unittest.TestCase):
    """Verifies module registration, routes, and option definitions."""

    def test_module_registry_registration(self):
        """Verify replace_vltd is properly registered in central registry."""
        mod = module_registry.get("replace_vltd")
        self.assertIsNotNone(mod)
        self.assertEqual(mod.module_id, "replace_vltd")
        self.assertEqual(mod.name, "Replace Device / Change ICCID")
        self.assertEqual(mod.frontend_route, "/modules/untag")
        self.assertEqual(mod.api_prefix, "/api/modules/untag")
        self.assertTrue(mod.is_enabled)
        self.assertIn("Reason / Action", mod.required_fields)
        self.assertIn("VLTD Maker", mod.required_fields)

    def test_replace_options_structure(self):
        """Verify the 3 standard options (S, D, I) have complete metadata."""
        self.assertEqual(len(REPLACE_OPTIONS), 3)
        option_ids = {opt["id"] for opt in REPLACE_OPTIONS}
        self.assertEqual(option_ids, {"S", "D", "I"})

        # Verify Option S
        opt_s = next(o for o in REPLACE_OPTIONS if o["id"] == "S")
        self.assertEqual(opt_s["value"], "S")
        self.assertIn("same maker", opt_s["label"].lower())
        self.assertEqual(opt_s["title"], "REPLACE DEVICE - WITH SAME MARKER")
        self.assertTrue(len(opt_s["description"]) > 10)

        # Verify Option D
        opt_d = next(o for o in REPLACE_OPTIONS if o["id"] == "D")
        self.assertEqual(opt_d["value"], "D")
        self.assertIn("different maker", opt_d["label"].lower())
        self.assertEqual(opt_d["title"], "REPLACE DEVICE - WITH DIFFERENT MARKER")

        # Verify Option I
        opt_i = next(o for o in REPLACE_OPTIONS if o["id"] == "I")
        self.assertEqual(opt_i["value"], "I")
        self.assertIn("change iccid", opt_i["label"].lower())
        self.assertEqual(opt_i["title"], "CHANGE ICCID")

    def test_portal_target_url(self):
        """Verify exact portal URL parity with Parivahan retrofitment portal."""
        expected_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"
        self.assertEqual(REPLACE_PORTAL_URL, expected_url)


# ============================================================================
# PART 4.2: AUTOMATION HANDLER TESTS (VIEW & NAVIGATION)
# ============================================================================

class TestReplaceModuleAutomationEnsureView(unittest.TestCase):
    """Tests for browser session checks and view navigation."""

    def test_ensure_replace_view_offline_browser_raises(self):
        """Browser offline should raise RuntimeError."""
        mock_bm = MagicMock()
        mock_bm.is_session_alive.return_value = False
        handler = ReplaceVltdAutomationHandler(browser_mgr=mock_bm)

        with self.assertRaises(RuntimeError) as ctx:
            handler.ensure_replace_view()
        self.assertIn("Chrome browser is not running", str(ctx.exception))

    def test_ensure_replace_view_already_on_url_with_select(self):
        """Browser already on sldfittingdetails with select_optn present."""
        mock_bm = MagicMock()
        mock_bm.is_session_alive.return_value = True
        mock_driver = MagicMock()
        mock_driver.current_url = REPLACE_PORTAL_URL
        mock_driver.execute_script.return_value = True  # has_select = True
        mock_bm.driver = mock_driver

        handler = ReplaceVltdAutomationHandler(browser_mgr=mock_bm)
        ok, msg = handler.ensure_replace_view()
        self.assertTrue(ok)
        self.assertIn("Replacement view and 'select_optn' are ready", msg)
        mock_driver.get.assert_not_called()

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_ensure_replace_view_redirect_when_on_different_url(self, mock_ajax):
        """Browser on dashboard or other route redirects to REPLACE_PORTAL_URL."""
        mock_bm = MagicMock()
        mock_bm.is_session_alive.return_value = True
        mock_driver = MagicMock()
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/home.xhtml"
        mock_driver.execute_script.return_value = True  # has_select = True
        mock_bm.driver = mock_driver

        handler = ReplaceVltdAutomationHandler(browser_mgr=mock_bm)
        ok, msg = handler.ensure_replace_view()
        self.assertTrue(ok)
        mock_driver.get.assert_called_once_with(REPLACE_PORTAL_URL)

    def test_ensure_replace_view_session_expired_url(self):
        """Portal redirects to sessionexpire.xhtml or login.xhtml."""
        mock_bm = MagicMock()
        mock_bm.is_session_alive.return_value = True
        mock_driver = MagicMock()
        mock_driver.current_url = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sessionexpire.xhtml"
        mock_driver.execute_script.return_value = False  # has_select = False
        mock_bm.driver = mock_driver

        handler = ReplaceVltdAutomationHandler(browser_mgr=mock_bm)
        ok, msg = handler.ensure_replace_view()
        self.assertFalse(ok)
        self.assertIn("session expired or at login page", msg.lower())

    def test_ensure_replace_view_exception_handling(self):
        """Exception during navigation returns (False, error)."""
        mock_bm = MagicMock()
        mock_bm.is_session_alive.return_value = True
        mock_driver = MagicMock()
        mock_driver.current_url = "https://vahan.parivahan.gov.in/other"
        mock_driver.get.side_effect = Exception("Connection reset by peer")
        mock_bm.driver = mock_driver

        handler = ReplaceVltdAutomationHandler(browser_mgr=mock_bm)
        ok, msg = handler.ensure_replace_view()
        self.assertFalse(ok)
        self.assertIn("Connection reset by peer", msg)


# ============================================================================
# PART 4.3: AUTOMATION HANDLER TESTS (OPTION SELECTION & REVEALED FIELDS)
# ============================================================================

class TestReplaceModuleAutomationSelectOption(unittest.TestCase):
    """Tests for reason/option selection in select_optn."""

    def setUp(self):
        self.mock_bm = MagicMock()
        self.mock_bm.is_session_alive.return_value = True
        self.mock_driver = MagicMock()
        self.mock_driver.current_url = REPLACE_PORTAL_URL
        self.mock_bm.driver = self.mock_driver
        self.handler = ReplaceVltdAutomationHandler(browser_mgr=self.mock_bm)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_select_reason_option_same_maker_short_code(self, mock_ajax):
        """Option 'S' selects 'Replace device - with same maker' and reveals fields."""
        def fake_exec(script, *args):
            if "select_optn_input" in script and "arguments[0]" in script:
                self.assertEqual(args[0], "S")
                return {"success": True, "text": "Replace device - with same maker", "value": "S"}
            elif "expectedIds" in script:
                return ["kit_maker_input", "kit_alloted_model_input", "serialNo_input", "tf_imei", "tf_iccID", "reg_type_input", "j_idt143"]
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        ok, msg, revealed = self.handler.select_reason_option("S")

        self.assertTrue(ok)
        self.assertIn("SAME MARKER", msg)
        self.assertIn("kit_maker_input", revealed)
        self.assertEqual(len(revealed), 7)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_select_reason_option_aliases_normalization(self, mock_ajax):
        """Option aliases ('SAME', 'SAME_MAKER', 'REPLACE DEVICE - WITH SAME MARKER') normalize to 'S'."""
        aliases = ["SAME", "SAME_MAKER", "REPLACE DEVICE - WITH SAME MARKER"]
        for alias in aliases:
            captured_val = []
            def fake_exec(script, *args):
                if "select_optn_input" in script and "arguments[0]" in script:
                    captured_val.append(args[0])
                    return {"success": True, "text": "Replace device - with same maker", "value": "S"}
                elif "expectedIds" in script:
                    return ["kit_maker_input"]
                return True

            self.mock_driver.execute_script.side_effect = fake_exec
            ok, msg, revealed = self.handler.select_reason_option(alias)
            self.assertTrue(ok)
            self.assertEqual(captured_val[0], "S")

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_select_reason_option_different_maker(self, mock_ajax):
        """Option 'D' and aliases normalize to 'D'."""
        def fake_exec(script, *args):
            if "select_optn_input" in script and "arguments[0]" in script:
                self.assertEqual(args[0], "D")
                return {"success": True, "text": "Replace device - with different maker", "value": "D"}
            elif "expectedIds" in script:
                return ["kit_maker_input", "kit_alloted_model_input", "serialNo_input", "tf_imei", "tf_iccID", "j_idt143"]
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        ok, msg, revealed = self.handler.select_reason_option("DIFFERENT")
        self.assertTrue(ok)
        self.assertIn("DIFFERENT MARKER", msg)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_select_reason_option_change_iccid(self, mock_ajax):
        """Option 'I' and 'CHANGE ICCID' select subscriber SIM ICCID change."""
        def fake_exec(script, *args):
            if "select_optn_input" in script and "arguments[0]" in script:
                self.assertEqual(args[0], "I")
                return {"success": True, "text": "Change ICCID", "value": "I"}
            elif "expectedIds" in script:
                return ["kit_maker_input", "tf_imei", "tf_iccID", "j_idt143"]
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        ok, msg, revealed = self.handler.select_reason_option("CHANGE_ICCID")
        self.assertTrue(ok)
        self.assertIn("CHANGE ICCID", msg)
        self.assertIn("tf_iccID", revealed)

    def test_select_reason_option_missing_element_in_dom(self):
        """When select_optn_input is absent from the DOM."""
        def fake_exec(script, *args):
            if "select_optn_input" in script and "arguments[0]" in script:
                return {"success": False, "error": "select_optn_input element not found"}
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        ok, msg, revealed = self.handler.select_reason_option("S")
        self.assertFalse(ok)
        self.assertIn("select_optn_input element not found", msg)
        self.assertEqual(revealed, [])

    def test_select_reason_option_not_found_in_options(self):
        """When the requested value does not exist in the dropdown options."""
        def fake_exec(script, *args):
            if "select_optn_input" in script and "arguments[0]" in script:
                return {"success": False, "error": "Option with value/text X not found in select_optn"}
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        ok, msg, revealed = self.handler.select_reason_option("X")
        self.assertFalse(ok)
        self.assertIn("not found in select_optn", msg)
        self.assertEqual(revealed, [])

    def test_select_reason_option_script_exception(self):
        """JavaScript execution error caught gracefully."""
        self.mock_driver.execute_script.side_effect = Exception("WebDriver session crashed")
        ok, msg, revealed = self.handler.select_reason_option("S")
        self.assertFalse(ok)
        self.assertIn("WebDriver session crashed", msg)
        self.assertEqual(revealed, [])


# ============================================================================
# PART 4.4: AUTOMATION HANDLER TESTS (FORM FIELD INSPECTION)
# ============================================================================

class TestReplaceModuleAutomationFieldInspection(unittest.TestCase):
    """Tests for inspecting revealed form fields on the portal."""

    def setUp(self):
        self.mock_bm = MagicMock()
        self.mock_bm.is_session_alive.return_value = True
        self.mock_driver = MagicMock()
        self.mock_bm.driver = self.mock_driver
        self.handler = ReplaceVltdAutomationHandler(browser_mgr=self.mock_bm)

    def test_inspect_revealed_fields_success(self):
        """Extracts visible form inputs, selects with options, and buttons."""
        mock_fields = [
            {"id": "kit_maker_input", "tag": "SELECT", "type": "", "label": "VLTD Maker", "text": "Select", "options": [{"value": "1", "text": "VASP"}]},
            {"id": "kit_alloted_model_input", "tag": "SELECT", "type": "", "label": "VLTD Model", "text": "Select", "options": [{"value": "10", "text": "VASP01"}]},
            {"id": "serialNo_input", "tag": "INPUT", "type": "text", "label": "VLTD Serial No", "text": "", "options": []},
            {"id": "tf_imei", "tag": "INPUT", "type": "text", "label": "IMEI No", "text": "", "options": []},
            {"id": "tf_iccID", "tag": "INPUT", "type": "text", "label": "ICCID No", "text": "", "options": []},
            {"id": "j_idt143", "tag": "BUTTON", "type": "submit", "label": "", "text": "Get Details", "options": []}
        ]
        self.mock_driver.execute_script.return_value = mock_fields

        fields = self.handler.inspect_revealed_fields()
        self.assertEqual(len(fields), 6)
        self.assertEqual(fields[0]["id"], "kit_maker_input")
        self.assertEqual(fields[0]["tag"], "SELECT")
        self.assertEqual(len(fields[0]["options"]), 1)
        self.assertEqual(fields[5]["id"], "j_idt143")

    def test_inspect_revealed_fields_exception_returns_empty(self):
        """Driver error during inspection returns empty list without raising."""
        self.mock_driver.execute_script.side_effect = Exception("DOM not responsive")
        fields = self.handler.inspect_revealed_fields()
        self.assertEqual(fields, [])


# ============================================================================
# PART 4.5: AUTOMATION HANDLER TESTS (POPULATE & SUBMIT FITMENT)
# ============================================================================

class TestReplaceModuleAutomationPopulateAndSubmit(unittest.TestCase):
    """Tests for populating fitment fields and executing submission."""

    def setUp(self):
        self.mock_bm = MagicMock()
        self.mock_bm.is_session_alive.return_value = True
        self.mock_driver = MagicMock()
        self.mock_bm.driver = self.mock_driver
        self.handler = ReplaceVltdAutomationHandler(browser_mgr=self.mock_bm)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_populate_and_submit_all_fields_with_standard_keys(self, mock_ajax):
        """Happy Path: populate with standard keys and click j_idt143."""
        self.mock_driver.execute_script.return_value = True

        data = {
            "maker": "VASP INFOTECH",
            "model": "VASP01",
            "serial_no": "SN9988",
            "imei": "123456789012345",
            "iccid": "89014103211118510720",
            "reg_type": "Old Vehicle"
        }
        ok, msg, ref_id = self.handler.populate_and_submit_fitment(data)
        self.assertTrue(ok)
        self.assertIn("SN9988", msg)
        self.assertTrue(ref_id.startswith("REP_"))
        self.assertTrue(self.mock_driver.execute_script.called)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_populate_and_submit_with_portal_column_aliases(self, mock_ajax):
        """Data dictionary containing Parivahan column aliases correctly handled."""
        self.mock_driver.execute_script.return_value = True

        data = {
            "VLTD Maker": "ROSMEK",
            "VLTD Model": "RS002",
            "VLTD serial Number": "RS-8899",
            "IMEI Number": "999888777666555",
            "ICC ID": "89014103211118510721",
            "Registration Type": "Old Vehicle"
        }
        ok, msg, ref_id = self.handler.populate_and_submit_fitment(data)
        self.assertTrue(ok)
        self.assertIn("RS-8899", msg)
        self.assertTrue(ref_id.startswith("REP_"))

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_populate_and_submit_default_reg_type(self, mock_ajax):
        """When reg_type is omitted, defaults to 'Old Vehicle' without errors."""
        captured_scripts = []
        def fake_exec(script, *args):
            captured_scripts.append((script, args))
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        data = {
            "maker": "VASP INFOTECH",
            "serial_no": "SN001"
        }
        ok, msg, ref_id = self.handler.populate_and_submit_fitment(data)
        self.assertTrue(ok)

        # Check that 'Old Vehicle' was passed in args for reg_type
        reg_args = [args[0] for script, args in captured_scripts if "reg_type_input" in script and args]
        self.assertIn("Old Vehicle", reg_args)

    @patch("modules.replace.automation.wait_for_primefaces_ajax")
    def test_populate_and_submit_get_details_not_found(self, mock_ajax):
        """When j_idt143 button returns false (not found), submission still succeeds."""
        def fake_exec(script, *args):
            if "j_idt143" in script:
                return False  # Button not found
            return True

        self.mock_driver.execute_script.side_effect = fake_exec
        data = {"serial_no": "SN001"}
        ok, msg, ref_id = self.handler.populate_and_submit_fitment(data)
        self.assertTrue(ok)
        self.assertTrue(ref_id.startswith("REP_"))

    def test_populate_and_submit_exception_handling(self):
        """Script execution error returns (False, error, None)."""
        self.mock_driver.execute_script.side_effect = Exception("StaleElementReferenceException")
        data = {"serial_no": "SN001"}
        ok, msg, ref_id = self.handler.populate_and_submit_fitment(data)
        self.assertFalse(ok)
        self.assertIn("StaleElementReferenceException", msg)
        self.assertIsNone(ref_id)


# ============================================================================
# PART 4.6: SERVICE LAYER TESTS
# ============================================================================

class TestReplaceModuleService(unittest.TestCase):
    """Tests for ReplaceVltdService single and batch transaction workflows."""

    def setUp(self):
        self.service = ReplaceVltdService()

    def test_service_get_options(self):
        """get_options returns standard options matching automation definitions."""
        options = self.service.get_options()
        self.assertEqual(len(options), 3)
        self.assertEqual([o["id"] for o in options], ["S", "D", "I"])

    @patch("modules.replace.service.replace_automation")
    def test_service_select_option_success(self, mock_auto):
        """select_option wraps automation response in ReplaceOptionSelectResponse."""
        mock_auto.select_reason_option.return_value = (True, "Selected option S", ["kit_maker_input", "tf_imei"])
        res = self.service.select_option("S")

        self.assertIsInstance(res, ReplaceOptionSelectResponse)
        self.assertTrue(res.success)
        self.assertEqual(res.option_key, "S")
        self.assertEqual(res.message, "Selected option S")
        self.assertEqual(res.revealed_fields, ["kit_maker_input", "tf_imei"])

    @patch("modules.replace.service.browser_manager")
    @patch("modules.replace.service.replace_automation")
    def test_service_inspect_form(self, mock_auto, mock_bm):
        """inspect_form parses dictionary list into typed ReplaceFieldInfo models."""
        mock_bm.driver.current_url = REPLACE_PORTAL_URL
        mock_auto.inspect_revealed_fields.return_value = [
            {"id": "tf_imei", "tag": "INPUT", "type": "text", "label": "IMEI", "text": "", "options": []},
            {"id": "kit_maker_input", "tag": "SELECT", "type": "", "label": "Maker", "text": "Select", "options": [{"value": "1", "text": "VASP"}]}
        ]

        res = self.service.inspect_form()
        self.assertIsInstance(res, ReplaceInspectResponse)
        self.assertTrue(res.success)
        self.assertEqual(len(res.fields), 2)
        self.assertEqual(res.fields[0].id, "tf_imei")
        self.assertEqual(res.fields[0].tag, "INPUT")
        self.assertEqual(res.fields[1].options[0]["text"], "VASP")
        self.assertEqual(res.portal_url, REPLACE_PORTAL_URL)

    @patch("modules.replace.service.replace_automation")
    def test_service_execute_single_success(self, mock_auto):
        """execute_single runs fitment and returns formatted ReplaceSingleExecuteResponse."""
        mock_auto.populate_and_submit_fitment.return_value = (True, "Fitment updated successfully", "REP_1700000000")

        req = ReplaceSingleExecuteRequest(
            option_key="S",
            maker="VASP INFOTECH",
            model="VASP01",
            serial_no="SN1001",
            imei="123456789012345",
            iccid="89014103211118510720",
            reg_type="Old Vehicle",
            extra_data={"custom_tag": "BATCH-1"}
        )
        res = self.service.execute_single(req)

        self.assertIsInstance(res, ReplaceSingleExecuteResponse)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.reference_id, "REP_1700000000")
        self.assertTrue(res.transaction_id.startswith("tx-rep-"))
        self.assertGreaterEqual(res.duration_seconds, 0)
        self.assertTrue(len(res.executed_at) > 10)

    @patch("modules.replace.service.replace_automation")
    def test_service_execute_single_failure(self, mock_auto):
        """execute_single returns FAILED status when automation reports error."""
        mock_auto.populate_and_submit_fitment.return_value = (False, "Device serial not in manufacturer stock", None)

        req = ReplaceSingleExecuteRequest(
            option_key="S",
            serial_no="SN_INVALID"
        )
        res = self.service.execute_single(req)

        self.assertEqual(res.status, "FAILED")
        self.assertIn("not in manufacturer stock", res.message)
        self.assertIsNone(res.reference_id)

    @patch("modules.replace.service.replace_automation")
    def test_service_execute_batch_all_success(self, mock_auto):
        """execute_batch selects reason option first, executes records, and aggregates counts."""
        mock_auto.select_reason_option.return_value = (True, "Selected S", ["kit_maker_input"])
        mock_auto.populate_and_submit_fitment.side_effect = [
            (True, "Saved record 1", "REP_001"),
            (True, "Saved record 2", "REP_002"),
            (True, "Saved record 3", "REP_003")
        ]

        req = ReplaceBatchRequest(
            option_key="S",
            records=[
                {"VLTD Maker": "VASP", "VLTD serial Number": "SN01", "IMEI Number": "11111"},
                {"VLTD Maker": "VASP", "VLTD serial Number": "SN02", "IMEI Number": "22222"},
                {"VLTD Maker": "VASP", "VLTD serial Number": "SN03", "IMEI Number": "33333"}
            ]
        )
        res = self.service.execute_batch(req)

        self.assertIsInstance(res, ReplaceBatchResponse)
        self.assertTrue(res.batch_id.startswith("batch-rep-"))
        self.assertEqual(res.total_count, 3)
        self.assertEqual(res.successful_count, 3)
        self.assertEqual(res.failed_count, 0)
        self.assertEqual(len(res.results), 3)
        mock_auto.select_reason_option.assert_called_once_with("S", run_id=mock_auto.select_reason_option.call_args[1].get("run_id"))

    @patch("modules.replace.service.replace_automation")
    def test_service_execute_batch_partial_failures(self, mock_auto):
        """execute_batch accurately tracks mixed successful and failed records."""
        mock_auto.select_reason_option.return_value = (True, "Selected D", ["kit_maker_input"])
        mock_auto.populate_and_submit_fitment.side_effect = [
            (True, "Saved record 1", "REP_001"),
            (False, "Duplicate IMEI on portal", None),
            (True, "Saved record 3", "REP_003")
        ]

        req = ReplaceBatchRequest(
            option_key="D",
            records=[
                {"serial_no": "SN01", "imei": "11111"},
                {"serial_no": "SN02", "imei": "22222"},
                {"serial_no": "SN03", "imei": "33333"}
            ]
        )
        res = self.service.execute_batch(req)

        self.assertEqual(res.total_count, 3)
        self.assertEqual(res.successful_count, 2)
        self.assertEqual(res.failed_count, 1)
        self.assertEqual(res.results[0].status, "SUCCESS")
        self.assertEqual(res.results[1].status, "FAILED")
        self.assertEqual(res.results[2].status, "SUCCESS")

    @patch("modules.replace.service.replace_automation")
    def test_service_execute_batch_empty_records(self, mock_auto):
        """execute_batch with 0 records returns zero counts without error."""
        mock_auto.select_reason_option.return_value = (True, "Selected I", [])
        req = ReplaceBatchRequest(option_key="I", records=[])
        res = self.service.execute_batch(req)

        self.assertEqual(res.total_count, 0)
        self.assertEqual(res.successful_count, 0)
        self.assertEqual(res.failed_count, 0)
        self.assertEqual(res.results, [])


# ============================================================================
# PART 4.7: ROUTER ENDPOINTS TESTS
# ============================================================================

class TestReplaceModuleRouter(unittest.TestCase):
    """Tests for all Replace Module API routes."""

    @patch("modules.replace.router.session_manager")
    def test_router_get_status_ready(self, mock_sm):
        """get_replace_module_status returns authenticated session and is_ready=True."""
        mock_sm.get_session_info.return_value = {
            "is_alive": True,
            "is_authenticated": True,
            "user_id": "VLTD_MAKER_VASP"
        }
        res = get_replace_module_status()
        self.assertEqual(res["module"], "replace_vltd")
        self.assertTrue(res["is_ready"])
        self.assertEqual(res["portal_url"], REPLACE_PORTAL_URL)
        self.assertEqual(res["session"]["user_id"], "VLTD_MAKER_VASP")

    @patch("modules.replace.router.session_manager")
    def test_router_get_status_not_ready(self, mock_sm):
        """get_replace_module_status returns is_ready=False when unauthenticated."""
        mock_sm.get_session_info.return_value = {
            "is_alive": False,
            "is_authenticated": False
        }
        res = get_replace_module_status()
        self.assertFalse(res["is_ready"])

    def test_router_get_options(self):
        """get_replace_options returns list of 3 supported options."""
        options = get_replace_options()
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0]["id"], "S")
        self.assertEqual(options[1]["id"], "D")
        self.assertEqual(options[2]["id"], "I")

    @patch("modules.replace.router.replace_automation")
    def test_router_navigate_success(self, mock_auto):
        """navigate_to_replace_portal returns success payload."""
        mock_auto.ensure_replace_view.return_value = (True, "Ready on replacement page")
        res = navigate_to_replace_portal()
        self.assertTrue(res["success"])
        self.assertEqual(res["target_url"], REPLACE_PORTAL_URL)
        self.assertEqual(res["message"], "Ready on replacement page")

    @patch("modules.replace.router.replace_automation")
    def test_router_navigate_failure_raises_500(self, mock_auto):
        """navigate_to_replace_portal raises HTTPException(500) on error."""
        mock_auto.ensure_replace_view.side_effect = Exception("Browser crashed")
        with self.assertRaises(HTTPException) as ctx:
            navigate_to_replace_portal()
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("Browser crashed", ctx.exception.detail)

    @patch("modules.replace.router.replace_service")
    def test_router_select_option_success(self, mock_svc):
        """select_portal_option forwards request and returns response model."""
        mock_svc.select_option.return_value = ReplaceOptionSelectResponse(
            success=True,
            option_key="S",
            message="Selected option S",
            revealed_fields=["kit_maker_input"]
        )
        payload = ReplaceOptionSelectRequest(option_key="S")
        res = select_portal_option(payload)
        self.assertTrue(res.success)
        self.assertEqual(res.option_key, "S")

    @patch("modules.replace.router.replace_service")
    def test_router_select_option_failure_raises_500(self, mock_svc):
        """select_portal_option raises HTTPException(500) on error."""
        mock_svc.select_option.side_effect = Exception("AJAX timeout")
        payload = ReplaceOptionSelectRequest(option_key="S")
        with self.assertRaises(HTTPException) as ctx:
            select_portal_option(payload)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("AJAX timeout", ctx.exception.detail)

    @patch("modules.replace.router.replace_service")
    def test_router_inspect_success(self, mock_svc):
        """inspect_portal_fields returns ReplaceInspectResponse."""
        mock_svc.inspect_form.return_value = ReplaceInspectResponse(
            success=True,
            fields=[ReplaceFieldInfo(id="tf_imei", tag="INPUT", type="text", label="IMEI")],
            portal_url=REPLACE_PORTAL_URL
        )
        res = inspect_portal_fields()
        self.assertTrue(res.success)
        self.assertEqual(len(res.fields), 1)
        self.assertEqual(res.fields[0].id, "tf_imei")

    @patch("modules.replace.router.replace_service")
    def test_router_inspect_failure_raises_500(self, mock_svc):
        """inspect_portal_fields raises HTTPException(500) on error."""
        mock_svc.inspect_form.side_effect = Exception("DOM unavailable")
        with self.assertRaises(HTTPException) as ctx:
            inspect_portal_fields()
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("DOM unavailable", ctx.exception.detail)

    @patch("modules.replace.router.replace_service")
    def test_router_execute_single_success(self, mock_svc):
        """execute_single_replace executes fitment and returns response."""
        mock_svc.execute_single.return_value = ReplaceSingleExecuteResponse(
            transaction_id="tx-rep-1234",
            status="SUCCESS",
            message="Submitted",
            reference_id="REP_999",
            executed_at="2026-11-02 18:00:00",
            duration_seconds=1.23
        )
        payload = ReplaceSingleExecuteRequest(option_key="S", serial_no="SN001")
        res = execute_single_replace(payload)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.reference_id, "REP_999")

    @patch("modules.replace.router.replace_service")
    def test_router_execute_single_failure_raises_500(self, mock_svc):
        """execute_single_replace raises HTTPException(500) on exception."""
        mock_svc.execute_single.side_effect = Exception("Fatal hardware error")
        payload = ReplaceSingleExecuteRequest(option_key="S", serial_no="SN001")
        with self.assertRaises(HTTPException) as ctx:
            execute_single_replace(payload)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("Fatal hardware error", ctx.exception.detail)

    @patch("modules.replace.router.replace_service")
    def test_router_execute_batch_success(self, mock_svc):
        """execute_batch_replace processes batch and returns summary."""
        mock_svc.execute_batch.return_value = ReplaceBatchResponse(
            batch_id="batch-rep-001",
            total_count=2,
            successful_count=2,
            failed_count=0,
            results=[],
            created_at="2026-11-02 18:00:00"
        )
        payload = ReplaceBatchRequest(
            option_key="S",
            records=[{"serial_no": "SN01"}, {"serial_no": "SN02"}]
        )
        res = execute_batch_replace(payload)
        self.assertEqual(res.batch_id, "batch-rep-001")
        self.assertEqual(res.total_count, 2)
        self.assertEqual(res.successful_count, 2)

    @patch("modules.replace.router.replace_service")
    def test_router_execute_batch_failure_raises_500(self, mock_svc):
        """execute_batch_replace raises HTTPException(500) on exception."""
        mock_svc.execute_batch.side_effect = Exception("Batch queue corrupted")
        payload = ReplaceBatchRequest(option_key="S", records=[])
        with self.assertRaises(HTTPException) as ctx:
            execute_batch_replace(payload)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("Batch queue corrupted", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
