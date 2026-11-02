# backend/test_api_routers.py
"""
Exhaustive Unit Test Suite for Part 5: FastAPI Router & HTTP Integration.
Covers:
1. Core System & Discovery Endpoints (/api/health, /api/modules, /api/session, /api/browser/close, CORS).
2. Delete / Unlock Module API Routes (/api/modules/delete/ status, registrations/options, navigate, select, open-modal, confirm-unlock/confirm, batch-unlock/batch).
3. Replace / Untag Module API Routes (/api/modules/replace & /api/modules/untag/ status, options, navigate, select-option, inspect, single, batch).
4. Add / Fitment & Batch Management API Routes (/api/vahan/ batches, inspect, confirm-login, mapping, dry-run, start, resume, stop, logs, report).
5. Cross-Cutting HTTP Error Handling (404 Not Found, 422 Unprocessable Entity, 400 Bad Request, 500 Server Error).
"""

import os
import sys
import io
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Patch time.sleep across tests to ensure instantaneous test runs
patcher = patch("time.sleep", return_value=None)
patcher.start()

import unittest
from fastapi.testclient import TestClient
from main import app, BATCH_STORE, selenium_worker
from models import (
    BatchResponse,
    BatchState,
    BatchSummary,
    CsvRecord,
    RecordStatus,
    BatchMappingConfig,
    FieldMappingItem,
    PortalInventory,
    DiscoveredFormField,
    DryRunResult
)
from modules.delete.automation import UNLOCK_PORTAL_URL
from modules.delete.service import (
    DeleteSelectResponse,
    DeleteOpenModalResponse,
    DeleteConfirmResponse,
    DeleteBatchResponse
)
from modules.replace.automation import REPLACE_PORTAL_URL
from modules.replace.service import (
    ReplaceOptionSelectResponse,
    ReplaceFieldInfo,
    ReplaceInspectResponse,
    ReplaceSingleExecuteResponse,
    ReplaceBatchResponse
)


# ============================================================================
# PART 5.1: CORE SYSTEM & DISCOVERY ENDPOINTS
# ============================================================================

class TestSystemAndDiscoveryEndpoints(unittest.TestCase):
    """Tests for platform health, module discovery, session, and browser management."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        """GET /api/health returns 200 OK with service and version info."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "2.0.0")
        self.assertIn("VAHAN", data["service"])

    def test_list_available_modules(self):
        """GET /api/modules returns all registered and enabled modules."""
        res = self.client.get("/api/modules")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        module_ids = [m["module_id"] for m in data]
        self.assertIn("add_vltd", module_ids)
        self.assertIn("delete_vltd", module_ids)
        self.assertIn("replace_vltd", module_ids)

    @patch("main.session_manager")
    def test_browser_session_status(self, mock_sm):
        """GET /api/session returns active browser session and auth metadata."""
        mock_sm.get_session_info.return_value = {
            "is_alive": True,
            "is_authenticated": True,
            "user_id": "TEST_USER_01",
            "current_url": "https://vahan.parivahan.gov.in"
        }
        res = self.client.get("/api/session")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["is_alive"])
        self.assertTrue(data["is_authenticated"])
        self.assertEqual(data["user_id"], "TEST_USER_01")

    @patch("main.browser_manager")
    def test_close_browser_session(self, mock_bm):
        """POST /api/browser/close closes session gracefully."""
        res = self.client.post("/api/browser/close")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("closed successfully", data["message"])
        mock_bm.close_browser.assert_called_once()
        self.assertIsNone(selenium_worker.driver)

    def test_cors_headers_present(self):
        """Verifies CORS headers allow origin and credentials."""
        res = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        self.assertIn(res.status_code, [200, 204])
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://localhost:3000")


# ============================================================================
# PART 5.2: DELETE / UNLOCK MODULE ROUTER INTEGRATION
# ============================================================================

class TestDeleteModuleApiEndpoints(unittest.TestCase):
    """Tests for all Delete / Unlock Module HTTP endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("modules.delete.router.session_manager")
    def test_delete_status(self, mock_sm):
        """GET /api/modules/delete/status returns module metadata."""
        mock_sm.get_session_info.return_value = {"is_alive": True, "is_authenticated": True}
        res = self.client.get("/api/modules/delete/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["module"], "delete_vltd")
        self.assertEqual(data["portal_url"], UNLOCK_PORTAL_URL)
        self.assertTrue(data["is_ready"])

    @patch("modules.delete.router.delete_service")
    def test_delete_options_success(self, mock_svc):
        """GET /api/modules/delete/registrations and /options return available registrations."""
        mock_svc.get_available_registrations.return_value = ["WB57D1709", "MH09GJ9036"]

        for path in ["/api/modules/delete/registrations", "/api/modules/delete/options"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data, ["WB57D1709", "MH09GJ9036"])

    @patch("modules.delete.router.delete_service")
    def test_delete_options_failure_500(self, mock_svc):
        """GET /api/modules/delete/registrations returns 500 on extraction failure."""
        mock_svc.get_available_registrations.side_effect = Exception("Portal dropdown not loaded")
        res = self.client.get("/api/modules/delete/registrations")
        self.assertEqual(res.status_code, 500)
        self.assertIn("Portal dropdown not loaded", res.json()["detail"])

    @patch("modules.delete.router.delete_automation")
    def test_delete_navigate_success(self, mock_auto):
        """POST /api/modules/delete/navigate redirects to unlock portal."""
        mock_auto.ensure_delete_view.return_value = (True, "Ready on unlock page")
        res = self.client.post("/api/modules/delete/navigate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["target_url"], UNLOCK_PORTAL_URL)

    @patch("modules.delete.router.delete_automation")
    def test_delete_navigate_failure_500(self, mock_auto):
        """POST /api/modules/delete/navigate returns 500 when browser offline."""
        mock_auto.ensure_delete_view.side_effect = RuntimeError("Chrome browser is not running.")
        res = self.client.post("/api/modules/delete/navigate")
        self.assertEqual(res.status_code, 500)
        self.assertIn("Chrome browser is not running", res.json()["detail"])

    @patch("modules.delete.router.delete_service")
    def test_delete_select_success(self, mock_svc):
        """POST /api/modules/delete/select selects vehicle and returns success."""
        mock_svc.select_registration.return_value = DeleteSelectResponse(
            success=True,
            registration_number="WB57D1709",
            message="Selected WB57D1709",
            vehicle_info={"owner": "ABC", "chassis": "CH123"},
            has_release_section=True
        )
        res = self.client.post("/api/modules/delete/select", json={"registration_number": "WB57D1709"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["registration_number"], "WB57D1709")
        self.assertTrue(data["has_release_section"])

    def test_delete_select_missing_payload_422(self):
        """POST /api/modules/delete/select with missing body returns 422."""
        res = self.client.post("/api/modules/delete/select", json={})
        self.assertEqual(res.status_code, 422)

    @patch("modules.delete.router.delete_service")
    def test_delete_select_failure_500(self, mock_svc):
        """POST /api/modules/delete/select returns 500 when service raises."""
        mock_svc.select_registration.side_effect = Exception("Vehicle dropdown not found")
        res = self.client.post("/api/modules/delete/select", json={"registration_number": "WB57D1709"})
        self.assertEqual(res.status_code, 500)
        self.assertIn("Vehicle dropdown not found", res.json()["detail"])

    @patch("modules.delete.router.delete_service")
    def test_delete_open_modal_success(self, mock_svc):
        """POST /api/modules/delete/open-modal triggers j_idt112 modal."""
        mock_svc.open_reason_modal.return_value = DeleteOpenModalResponse(
            success=True,
            message="Reason modal visible",
            is_modal_ready=True
        )
        res = self.client.post("/api/modules/delete/open-modal")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertTrue(res.json()["is_modal_ready"])

    @patch("modules.delete.router.delete_service")
    def test_delete_open_modal_failure_500(self, mock_svc):
        """POST /api/modules/delete/open-modal returns 500 on modal failure."""
        mock_svc.open_reason_modal.side_effect = Exception("Modal container missing")
        res = self.client.post("/api/modules/delete/open-modal")
        self.assertEqual(res.status_code, 500)
        self.assertIn("Modal container missing", res.json()["detail"])

    @patch("modules.delete.router.delete_service")
    def test_delete_confirm_success(self, mock_svc):
        """POST /api/modules/delete/confirm-unlock and /confirm submit unlock."""
        mock_svc.confirm_and_unlock.return_value = DeleteConfirmResponse(
            transaction_id="tx-del-1234",
            registration_number="WB57D1709",
            reason="Replacement",
            status="SUCCESS",
            message="Unlocked successfully",
            confirmation_ref="UNLOCK_WB57D1709_12345",
            executed_at="2026-11-02 18:00:00",
            duration_seconds=1.2
        )
        payload = {"registration_number": "WB57D1709", "reason": "Replacement"}

        for path in ["/api/modules/delete/confirm-unlock", "/api/modules/delete/confirm"]:
            res = self.client.post(path, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "SUCCESS")
            self.assertEqual(data["confirmation_ref"], "UNLOCK_WB57D1709_12345")

    def test_delete_confirm_missing_fields_422(self):
        """POST /api/modules/delete/confirm without registration number returns 422."""
        res = self.client.post("/api/modules/delete/confirm", json={"reason": "Replacement"})
        self.assertEqual(res.status_code, 422)

    @patch("modules.delete.router.delete_service")
    def test_delete_confirm_failure_500(self, mock_svc):
        """POST /api/modules/delete/confirm returns 500 when confirm_and_unlock fails."""
        mock_svc.confirm_and_unlock.side_effect = Exception("Submission failed")
        payload = {"registration_number": "WB57D1709", "reason": "Replacement"}
        res = self.client.post("/api/modules/delete/confirm", json=payload)
        self.assertEqual(res.status_code, 500)
        self.assertIn("Submission failed", res.json()["detail"])

    @patch("modules.delete.router.delete_service")
    def test_delete_batch_success(self, mock_svc):
        """POST /api/modules/delete/batch-unlock and /batch process list of records."""
        mock_svc.execute_batch_unlock.return_value = DeleteBatchResponse(
            batch_id="batch-del-01",
            total_count=1,
            successful_count=1,
            failed_count=0,
            results=[],
            created_at="2026-11-02 18:00:00"
        )
        payload = {"registrations": ["WB57D1709"], "default_reason": "Untag"}

        for path in ["/api/modules/delete/batch-unlock", "/api/modules/delete/batch"]:
            res = self.client.post(path, json=payload)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["batch_id"], "batch-del-01")

    @patch("modules.delete.router.delete_service")
    def test_delete_batch_failure_500(self, mock_svc):
        """POST /api/modules/delete/batch returns 500 on batch failure."""
        mock_svc.execute_batch_unlock.side_effect = Exception("Batch queue corrupted")
        payload = {"registrations": ["WB57D1709"]}
        res = self.client.post("/api/modules/delete/batch", json=payload)
        self.assertEqual(res.status_code, 500)
        self.assertIn("Batch queue corrupted", res.json()["detail"])


# ============================================================================
# PART 5.3: REPLACE / UNTAG MODULE ROUTER INTEGRATION
# ============================================================================

class TestReplaceModuleApiEndpoints(unittest.TestCase):
    """Tests for all Replace / Untag Module HTTP endpoints under both /untag and /replace."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("modules.replace.router.session_manager")
    def test_replace_status_endpoints(self, mock_sm):
        """GET /api/modules/untag/status and /api/modules/replace/status both return 200."""
        mock_sm.get_session_info.return_value = {"is_alive": True, "is_authenticated": True}

        for path in ["/api/modules/untag/status", "/api/modules/replace/status"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["module"], "replace_vltd")
            self.assertEqual(data["portal_url"], REPLACE_PORTAL_URL)
            self.assertTrue(data["is_ready"])

    def test_replace_options_endpoints(self):
        """GET /api/modules/untag/options and /api/modules/replace/options return 3 options."""
        for path in ["/api/modules/untag/options", "/api/modules/replace/options"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(len(data), 3)
            ids = [o["id"] for o in data]
            self.assertEqual(ids, ["S", "D", "I"])

    @patch("modules.replace.router.replace_automation")
    def test_replace_navigate_success(self, mock_auto):
        """POST /api/modules/untag/navigate and /api/modules/replace/navigate redirect to portal."""
        mock_auto.ensure_replace_view.return_value = (True, "Ready on replace page")

        for path in ["/api/modules/untag/navigate", "/api/modules/replace/navigate"]:
            res = self.client.post(path)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["target_url"], REPLACE_PORTAL_URL)

    @patch("modules.replace.router.replace_automation")
    def test_replace_navigate_failure_500(self, mock_auto):
        """POST /api/modules/replace/navigate returns 500 when automation fails."""
        mock_auto.ensure_replace_view.side_effect = Exception("Browser not attached")
        res = self.client.post("/api/modules/replace/navigate")
        self.assertEqual(res.status_code, 500)
        self.assertIn("Browser not attached", res.json()["detail"])

    @patch("modules.replace.router.replace_service")
    def test_replace_select_option_success(self, mock_svc):
        """POST /api/modules/replace/select-option selects option and triggers AJAX."""
        for opt in ["S", "D", "I"]:
            mock_svc.select_option.return_value = ReplaceOptionSelectResponse(
                success=True,
                option_key=opt,
                message=f"Selected {opt}",
                revealed_fields=["kit_maker_input", "tf_imei"]
            )
            res = self.client.post("/api/modules/replace/select-option", json={"option_key": opt})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["option_key"], opt)

    def test_replace_select_option_missing_payload_422(self):
        """POST /api/modules/replace/select-option with missing option_key returns 422."""
        res = self.client.post("/api/modules/replace/select-option", json={})
        self.assertEqual(res.status_code, 422)

    @patch("modules.replace.router.replace_service")
    def test_replace_select_option_failure_500(self, mock_svc):
        """POST /api/modules/replace/select-option returns 500 on service exception."""
        mock_svc.select_option.side_effect = Exception("AJAX timeout")
        res = self.client.post("/api/modules/replace/select-option", json={"option_key": "S"})
        self.assertEqual(res.status_code, 500)
        self.assertIn("AJAX timeout", res.json()["detail"])

    @patch("modules.replace.router.replace_service")
    def test_replace_inspect_fields_success(self, mock_svc):
        """GET /api/modules/replace/inspect returns discovered form elements."""
        mock_svc.inspect_form.return_value = ReplaceInspectResponse(
            success=True,
            fields=[ReplaceFieldInfo(id="tf_imei", tag="INPUT", type="text", label="IMEI")],
            portal_url=REPLACE_PORTAL_URL
        )
        for path in ["/api/modules/untag/inspect", "/api/modules/replace/inspect"]:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])

    @patch("modules.replace.router.replace_service")
    def test_replace_execute_single_success(self, mock_svc):
        """POST /api/modules/replace/execute-single runs fitment and returns response."""
        mock_svc.execute_single.return_value = ReplaceSingleExecuteResponse(
            transaction_id="tx-rep-001",
            status="SUCCESS",
            message="Submitted",
            reference_id="REP_12345",
            executed_at="2026-11-02 18:00:00",
            duration_seconds=1.0
        )
        payload = {"option_key": "S", "serial_no": "SN001", "imei": "123456789012345"}
        res = self.client.post("/api/modules/replace/execute-single", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "SUCCESS")

    @patch("modules.replace.router.replace_service")
    def test_replace_execute_batch_success(self, mock_svc):
        """POST /api/modules/replace/batch executes batch and returns summary."""
        mock_svc.execute_batch.return_value = ReplaceBatchResponse(
            batch_id="batch-rep-001",
            total_count=2,
            successful_count=2,
            failed_count=0,
            results=[],
            created_at="2026-11-02 18:00:00"
        )
        payload = {"option_key": "S", "records": [{"serial_no": "SN01"}, {"serial_no": "SN02"}]}
        res = self.client.post("/api/modules/replace/batch", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["batch_id"], "batch-rep-001")


# ============================================================================
# PART 5.4: ADD / FITMENT & BATCH MANAGEMENT API ROUTES
# ============================================================================

class TestAddModuleAndBatchApiEndpoints(unittest.TestCase):
    """Tests for CSV upload, mapping, dry-run, start, resume, stop, and logs."""

    def setUp(self):
        self.client = TestClient(app)
        BATCH_STORE.clear()

    def test_add_module_status(self):
        """GET /api/modules/add/status returns 200 OK."""
        res = self.client.get("/api/modules/add/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["module"], "add_vltd")
        self.assertEqual(data["status"], "ready")

    def test_upload_csv_add_vltd_success(self):
        """POST /api/vahan/batches with valid Add VLTD CSV creates batch."""
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "001,VASP INFOTECH,VASP01,SN-1001,BSNL,123456789012345,Old Vehicle\n"
        )
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res = self.client.post("/api/vahan/batches?module_type=add_vltd", files=files)

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("batch_id", data)
        self.assertEqual(data["state"], "READY_FOR_REVIEW")
        self.assertEqual(data["summary"]["valid_records_count"], 1)
        self.assertIn(data["batch_id"], BATCH_STORE)

    def test_upload_csv_delete_vltd_success(self):
        """POST /api/vahan/batches with valid Delete VLTD CSV creates delete batch."""
        csv_content = (
            "Vehicle Registration Number,Reason\n"
            "WB57D1709,Fitment replacement\n"
        )
        files = {"file": ("delete.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res = self.client.post("/api/vahan/batches?module_type=delete_vltd", files=files)

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["module_type"], "delete_vltd")
        self.assertEqual(data["summary"]["valid_records_count"], 1)

    def test_upload_csv_empty_file_422(self):
        """POST /api/vahan/batches with empty content returns 422."""
        files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
        res = self.client.post("/api/vahan/batches", files=files)
        self.assertEqual(res.status_code, 422)

    def test_upload_csv_invalid_rows_completed_with_errors(self):
        """POST /api/vahan/batches with invalid rows sets COMPLETED_WITH_ERRORS when no rows valid."""
        csv_content = (
            "ID,VLTD Maker,VLTD Model,VLTD serial Number,Provider,IMEI Number,Registration Type\n"
            "001,,,,,,Old Vehicle\n"
        )
        files = {"file": ("invalid.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res = self.client.post("/api/vahan/batches", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["state"], "COMPLETED_WITH_ERRORS")
        self.assertGreater(data["summary"]["invalid_records_count"], 0)

    def test_get_batch_existing(self):
        """GET /api/vahan/batches/{batch_id} returns batch details."""
        b_id = "test-batch-001"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.get(f"/api/vahan/batches/{b_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["batch_id"], b_id)

    def test_get_batch_not_found_404(self):
        """GET /api/vahan/batches/{batch_id} returns 404 for unknown ID."""
        res = self.client.get("/api/vahan/batches/non-existent-batch")
        self.assertEqual(res.status_code, 404)

    @patch("main.selenium_worker")
    def test_portal_inspect_success(self, mock_worker):
        """POST /api/vahan/portal/inspect launches browser and returns inventory."""
        mock_worker.launch_browser_for_authentication.return_value = PortalInventory(
            portal_url="https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml",
            page_title="SLD Fitting",
            fields=[DiscoveredFormField(tag="select", field_id="kit_maker", field_name="kit_maker", element_type="select")]
        )
        res = self.client.post("/api/vahan/portal/inspect")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["fields"]), 1)

    @patch("main.selenium_worker")
    def test_portal_inspect_failure_500(self, mock_worker):
        """POST /api/vahan/portal/inspect returns 500 when Chrome crashes."""
        mock_worker.launch_browser_for_authentication.side_effect = Exception("Chrome binary not found")
        res = self.client.post("/api/vahan/portal/inspect")
        self.assertEqual(res.status_code, 500)
        self.assertIn("Chrome binary not found", res.json()["detail"])

    @patch("main.selenium_worker")
    def test_portal_confirm_login_success(self, mock_worker):
        """POST /api/vahan/portal/confirm-login inspects form after login."""
        mock_worker.confirm_and_inspect_form.return_value = PortalInventory(
            portal_url="https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml",
            page_title="SLD Fitting",
            fields=[]
        )
        res = self.client.post("/api/vahan/portal/confirm-login")
        self.assertEqual(res.status_code, 200)

    def test_get_batch_mapping_success(self):
        """GET /api/vahan/batches/{batch_id}/mapping returns mapping."""
        b_id = "test-batch-mapping"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            mapping=BatchMappingConfig(batch_id=b_id, is_complete=True, mappings={}),
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.get(f"/api/vahan/batches/{b_id}/mapping")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_complete"])

    def test_get_batch_mapping_not_found_404(self):
        """GET /api/vahan/batches/{batch_id}/mapping returns 404 for unknown batch."""
        res = self.client.get("/api/vahan/batches/unknown/mapping")
        self.assertEqual(res.status_code, 404)

    def test_save_batch_mapping_success(self):
        """POST /api/vahan/batches/{batch_id}/mapping updates mapping config."""
        b_id = "test-batch-save-mapping"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        payload = {
            "batch_id": b_id,
            "mappings": {
                "VLTD Maker": {"csv_column": "VLTD Maker", "target_field_id": "kit_maker", "target_field_name": "kit_maker", "element_type": "select", "is_required": True},
                "VLTD Model": {"csv_column": "VLTD Model", "target_field_id": "kit_model", "target_field_name": "kit_model", "element_type": "select", "is_required": True},
                "VLTD serial Number": {"csv_column": "VLTD serial Number", "target_field_id": "serial_no", "target_field_name": "serial_no", "element_type": "input", "is_required": True},
                "Provider": {"csv_column": "Provider", "target_field_id": "provider", "target_field_name": "provider", "element_type": "select", "is_required": True},
                "IMEI Number": {"csv_column": "IMEI Number", "target_field_id": "imei", "target_field_name": "imei", "element_type": "input", "is_required": True},
                "Registration Type": {"csv_column": "Registration Type", "target_field_id": "reg_type", "target_field_name": "reg_type", "element_type": "select", "is_required": True}
            }
        }
        res = self.client.post(f"/api/vahan/batches/{b_id}/mapping", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["is_complete"])

    @patch("main.selenium_worker")
    def test_dry_run_success(self, mock_worker):
        """POST /api/vahan/batches/{batch_id}/dry-run executes dry-run without commit."""
        b_id = "batch-dry-run-01"
        rec = CsvRecord(row_number=2, id="001", source_row_number=2, status=RecordStatus.READY, raw_data={})
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[rec],
            errors=[],
            mapping=BatchMappingConfig(batch_id=b_id, is_complete=True, mappings={}),
            created_at="2026-11-02 18:00:00"
        )
        mock_worker.dry_run_autofill.return_value = DryRunResult(
            record_id="001",
            row_number=2,
            success=True,
            executed_at="2026-11-02 18:00:00",
            portal_url="https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml",
            summary_message="Autofill verified"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/dry-run", json={"record_index": 0})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(BATCH_STORE[b_id].state, BatchState.READY_TO_PROCESS)

    def test_dry_run_no_valid_records_400(self):
        """POST /api/vahan/batches/{batch_id}/dry-run with 0 valid records returns 400."""
        b_id = "batch-dry-run-invalid"
        rec = CsvRecord(row_number=2, id="001", source_row_number=2, status=RecordStatus.INVALID, raw_data={})
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.COMPLETED_WITH_ERRORS,
            summary=BatchSummary(total_records=1, valid_records_count=0, invalid_records_count=1),
            records=[rec],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/dry-run", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("No valid records available", res.json()["detail"])

    @patch("main.selenium_worker")
    def test_start_processing_success(self, mock_worker):
        """POST /api/vahan/batches/{batch_id}/start launches async worker."""
        b_id = "batch-start-01"
        rec = CsvRecord(row_number=2, id="001", source_row_number=2, status=RecordStatus.READY, raw_data={})
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_TO_PROCESS,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[rec],
            errors=[],
            mapping=BatchMappingConfig(batch_id=b_id, is_complete=True, mappings={}),
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/start", json={"mode": "batch"})
        self.assertEqual(res.status_code, 200)
        mock_worker.start_batch_processing_async.assert_called_once()

    def test_start_processing_incomplete_mapping_400(self):
        """POST /api/vahan/batches/{batch_id}/start returns 400 when mapping is incomplete."""
        b_id = "batch-start-incomplete"
        rec = CsvRecord(row_number=2, id="001", source_row_number=2, status=RecordStatus.READY, raw_data={})
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[rec],
            errors=[],
            mapping=BatchMappingConfig(batch_id=b_id, is_complete=False, missing_required_fields=["IMEI Number"], mappings={}),
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/start", json={"mode": "batch"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Field mapping is incomplete", res.json()["detail"])

    @patch("main.selenium_worker")
    def test_resume_processing_success(self, mock_worker):
        """POST /api/vahan/batches/{batch_id}/resume resumes paused batch after session re-check."""
        b_id = "batch-resume-01"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.PAUSED_AUTH_REQUIRED,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        mock_worker.verify_session.return_value = (True, "Session active")
        res = self.client.post(f"/api/vahan/batches/{b_id}/resume")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(BATCH_STORE[b_id].state, BatchState.PROCESSING)

    def test_resume_processing_not_paused_400(self):
        """POST /api/vahan/batches/{batch_id}/resume returns 400 if state is not PAUSED_AUTH_REQUIRED."""
        b_id = "batch-not-paused"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.READY_FOR_REVIEW,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/resume")
        self.assertEqual(res.status_code, 400)
        self.assertIn("not in PAUSED_AUTH_REQUIRED state", res.json()["detail"])

    @patch("main.selenium_worker")
    def test_stop_batch_success(self, mock_worker):
        """POST /api/vahan/batches/{batch_id}/stop signals worker to halt."""
        b_id = "batch-stop-01"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.PROCESSING,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.post(f"/api/vahan/batches/{b_id}/stop")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(BATCH_STORE[b_id].state, BatchState.STOPPED)
        mock_worker.request_stop.assert_called_once()

    def test_batch_report_and_logs(self):
        """GET /api/vahan/batches/{batch_id}/report returns full execution audit report."""
        b_id = "batch-report-01"
        BATCH_STORE[b_id] = BatchResponse(
            batch_id=b_id,
            file_name="test.csv",
            module_type="add_vltd",
            state=BatchState.COMPLETED,
            summary=BatchSummary(total_records=1, valid_records_count=1, invalid_records_count=0),
            records=[],
            errors=[],
            created_at="2026-11-02 18:00:00"
        )
        res = self.client.get(f"/api/vahan/batches/{b_id}/report")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["batch_id"], b_id)
        self.assertEqual(data["state"], "COMPLETED")

    def test_log_management_endpoints(self):
        """Tests unified logs, structured logs, and starting new log sessions."""
        res_unified = self.client.get("/api/vahan/logs/unified")
        self.assertEqual(res_unified.status_code, 200)
        self.assertIn("content", res_unified.json())

        res_struct = self.client.get("/api/vahan/logs/session-structured")
        self.assertEqual(res_struct.status_code, 200)

        res_new = self.client.post("/api/vahan/logs/new-session", json={"session_id": "TEST_SES_999"})
        self.assertEqual(res_new.status_code, 200)
        self.assertEqual(res_new.json()["session_id"], "TEST_SES_999")


if __name__ == "__main__":
    unittest.main()
