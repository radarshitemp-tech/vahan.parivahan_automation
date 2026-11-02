# backend/modules/delete/automation.py
import time
import logging
from typing import List, Dict, Tuple, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from core.browser_manager import browser_manager
from core.session_manager import session_manager, TARGET_PORTAL_URL
from core.selenium_helpers import (
    wait_for_primefaces_ajax,
    click_element_safely,
    set_element_value,
    select_dropdown_option,
    capture_portal_messages
)
from logger_service import execution_logger
from models import LogLevel, ExecutionType

logger = logging.getLogger("DeleteVltdAutomation")

class DeleteVltdAutomationHandler:
    """
    Dedicated automation handler for Delete / Untag / Unlock VLTD module.
    Executes the 4-step sequence:
    1. Registration number selection via select tag with label id (reg_label).
    2. Detection of 'Release VLTD From Vehicle' container and first button (j_idt112).
    3. Reason input in modal (Inputreject) and final confirmation button (j_idt122).
    4. Authoritative verification of transaction outcome.
    """

    def __init__(self, browser_mgr=browser_manager):
        self.browser_mgr = browser_mgr

    def _get_driver(self):
        if not self.browser_mgr.is_session_alive():
            raise RuntimeError("Chrome browser is not running. Please launch the portal first.")
        return self.browser_mgr.driver

    def ensure_delete_view(self) -> Tuple[bool, str]:
        """
        Navigates to retrofitment portal and ensures the Delete/Release VLTD view is active.
        If 'reg_label' is not already rendered, checks and activates the Release/Unlock radio button.
        """
        driver = self._get_driver()
        try:
            curr_url = driver.current_url.lower()
            if "sldfittingdetails" not in curr_url and "retrofitment" in curr_url:
                logger.info("Navigating to sldfittingDetails.xhtml...")
                driver.get(TARGET_PORTAL_URL)
                time.sleep(1.5)
                wait_for_primefaces_ajax(driver, timeout=4.0)

            # Check if reg_label or select is already visible
            has_reg = driver.execute_script("""
                var lbl = document.getElementById('reg_label') || document.querySelector('[id$="reg_label"]');
                var sel = document.getElementById('reg_input') || document.querySelector('select[id*="reg"]');
                return !!((lbl && lbl.offsetParent !== null) || (sel && sel.offsetParent !== null));
            """)
            if has_reg:
                return True, "Delete view and registration selector are ready."

            # If not rendered, look for Release/Unlock radio button (e.g. rb:1 or text matching)
            logger.info("Registration selector not visible yet. Checking for Release/Unlock radio button...")
            clicked = driver.execute_script("""
                // Check radio buttons with label containing release/unlock/delete
                var labels = document.querySelectorAll('label[for^="rb"], .ui-radiobutton-box, label');
                for (var i = 0; i < labels.length; i++) {
                    var t = (labels[i].innerText || '').toLowerCase();
                    if (t.includes('release') || t.includes('unlock') || t.includes('untag') || t.includes('delete') || t.includes('remove')) {
                        labels[i].click();
                        return 'clicked_label: ' + t;
                    }
                }
                var rb1 = document.getElementById('rb:1');
                if (rb1) {
                    rb1.click();
                    return 'clicked_rb1';
                }
                var label1 = document.querySelector('label[for="rb:1"]');
                if (label1) {
                    label1.click();
                    return 'clicked_label_rb1';
                }
                return 'not_found';
            """)
            logger.info(f"Radio action result: {clicked}")
            wait_for_primefaces_ajax(driver, timeout=4.0)
            time.sleep(1.0)

            return True, "Delete section activated."
        except Exception as e:
            logger.warning(f"Note on ensure_delete_view: {e}")
            return False, str(e)

    def extract_registration_options(self) -> List[str]:
        """
        Reads all available vehicle registration options from the portal select tag (reg_label / reg_input).
        """
        driver = self._get_driver()
        self.ensure_delete_view()

        try:
            wait_for_primefaces_ajax(driver, timeout=3.0)
            options = driver.execute_script("""
                var results = [];
                var sel = document.getElementById('reg_input') || 
                          document.querySelector('select[id*="reg"]') || 
                          (document.getElementById('reg_label') ? document.getElementById('reg_label').closest('.ui-selectonemenu')?.querySelector('select') : null);

                if (sel && sel.options) {
                    for (var i = 0; i < sel.options.length; i++) {
                        var txt = sel.options[i].text.trim();
                        var val = sel.options[i].value.trim();
                        var target = txt || val;
                        if (target && !target.toLowerCase().includes('select') && target !== '--' && target !== '0') {
                            results.push(target);
                        }
                    }
                }

                // Also check PrimeFaces panel list items if select had no options
                if (results.length === 0) {
                    var items = document.querySelectorAll('#reg_panel li, [id$="reg_panel"] li, .ui-selectonemenu-item');
                    for (var j = 0; j < items.length; j++) {
                        var itxt = items[j].innerText.trim();
                        if (itxt && !itxt.toLowerCase().includes('select') && itxt !== '--') {
                            results.push(itxt);
                        }
                    }
                }

                return results;
            """)
            return list(dict.fromkeys(options or [])) # Unique ordered list
        except Exception as e:
            logger.error(f"Failed to extract registration options: {e}")
            return []

    def select_registration_number(self, reg_no: str) -> Tuple[bool, str, Optional[Dict[str, str]]]:
        """
        Step 1: Selects the requested registration number from the dropdown with label id 'reg_label'.
        Step 2: Verifies that the 'Release VLTD From Vehicle' div and button 'j_idt112' appear.
        """
        driver = self._get_driver()
        clean_reg = "".join(filter(str.isalnum, reg_no)).upper()

        self.ensure_delete_view()

        # Locate label or select
        elem = driver.execute_script("""
            return document.getElementById('reg_label') || 
                   document.querySelector('[id$="reg_label"]') ||
                   document.getElementById('reg_input') ||
                   document.querySelector('select[id*="reg"]');
        """)
        if not elem:
            return False, "Registration selector element ('reg_label') was not found on portal page.", None

        ok, matched_text = select_dropdown_option(driver, elem, reg_no)
        if not ok:
            return False, f"Could not select vehicle registration '{reg_no}': {matched_text}", None

        wait_for_primefaces_ajax(driver, timeout=5.0)
        time.sleep(1.0)

        # Verify Release VLTD From Vehicle div and button j_idt112
        verify_data = driver.execute_script("""
            var btn = document.getElementById('j_idt112') || document.querySelector('[id$="j_idt112"]');
            var releaseDiv = null;
            var divs = document.querySelectorAll('div, table, p, h3, h4');
            for (var i = 0; i < divs.length; i++) {
                if (divs[i].innerText && divs[i].innerText.toLowerCase().includes('release vltd from vehicle')) {
                    releaseDiv = divs[i];
                    break;
                }
            }

            var hasRelease = !!(btn || releaseDiv);
            var isBtnVisible = !!(btn && btn.offsetParent !== null);

            // Read displayed vehicle information if present
            var vehInfo = {};
            var infoElements = document.querySelectorAll('.ui-panelgrid tr, table tr');
            for (var j = 0; j < infoElements.length; j++) {
                var row = infoElements[j];
                var cells = row.querySelectorAll('td, th');
                if (cells.length >= 2) {
                    var k = cells[0].innerText.replace(/:/g, '').trim();
                    var v = cells[1].innerText.trim();
                    if (k && v && k.length < 50) {
                        vehInfo[k] = v;
                    }
                }
            }

            return {
                has_release_section: hasRelease,
                has_unlock_button: isBtnVisible || !!btn,
                button_id: btn ? btn.id : null,
                vehicle_info: vehInfo
            };
        """)

        if not verify_data.get("has_release_section") and not verify_data.get("has_unlock_button"):
            return False, f"Selected '{reg_no}', but 'Release VLTD From Vehicle' section did not appear.", None

        return True, f"Registration '{reg_no}' loaded. 'Release VLTD' section is ready.", verify_data.get("vehicle_info", {})

    def open_unlock_modal(self) -> Tuple[bool, str]:
        """
        Clicks the first 'Unlock VLTD' button with field id 'j_idt112'
        and awaits the unlock reason modal dialog.
        """
        driver = self._get_driver()
        try:
            clicked = driver.execute_script("""
                var btn = document.getElementById('j_idt112') || 
                          document.querySelector('[id$="j_idt112"]') ||
                          document.querySelector('button[value*="Unlock"], input[value*="Unlock"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            if not clicked:
                return False, "Could not find 'Unlock VLTD' button (field id: 'j_idt112')."

            wait_for_primefaces_ajax(driver, timeout=4.0)
            time.sleep(1.0)

            # Wait for modal containing Inputreject and j_idt122
            modal_ready = driver.execute_script("""
                var input = document.getElementById('Inputreject') || document.querySelector('[id$="Inputreject"]');
                var btn = document.getElementById('j_idt122') || document.querySelector('[id$="j_idt122"]');
                return !!(input && btn);
            """)

            if not modal_ready:
                # Wait up to 5s
                try:
                    WebDriverWait(driver, 5.0).until(
                        lambda d: d.execute_script("""
                            return !!(document.getElementById('Inputreject') || document.querySelector('[id$="Inputreject"]'));
                        """)
                    )
                    modal_ready = True
                except Exception:
                    modal_ready = False

            if modal_ready:
                return True, "Unlock reason modal successfully displayed."
            return False, "Unlock button clicked, but reason modal ('Inputreject') did not render."

        except Exception as e:
            return False, f"Error opening unlock modal: {str(e)}"

    def execute_final_unlock(self, reg_no: str, reason: str, run_id: str = "delete-run") -> Tuple[bool, str, Optional[str]]:
        """
        Fills the reason into field id 'Inputreject', verifies input,
        and clicks the final confirmation button 'j_idt122'.
        Waits for the portal response and evaluates authoritative success/failure.
        """
        driver = self._get_driver()
        clean_reason = (reason or "").strip()
        if not clean_reason:
            clean_reason = "Untag VLTD / Fitment Removal"

        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.CONFIRMATION,
            run_id=run_id,
            stage="CONFIRM_UNLOCK",
            action="INPUT_REASON_AND_SUBMIT",
            result="IN_PROGRESS",
            message=f"Submitting final unlock for vehicle {reg_no} with reason: '{clean_reason}'."
        )

        try:
            # 1. Populate Inputreject
            input_set = driver.execute_script("""
                var input = document.getElementById('Inputreject') || document.querySelector('[id$="Inputreject"]');
                if (input) {
                    input.value = arguments[0];
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            """, clean_reason)

            if not input_set:
                return False, "Could not locate reason field 'Inputreject' in modal.", None

            time.sleep(0.5)

            # 2. Click final unlock button j_idt122
            btn_clicked = driver.execute_script("""
                var btn = document.getElementById('j_idt122') || document.querySelector('[id$="j_idt122"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            if not btn_clicked:
                return False, "Could not find final confirmation button 'j_idt122'.", None

            # 3. Wait for PrimeFaces AJAX outcome
            wait_for_primefaces_ajax(driver, timeout=6.0)
            time.sleep(1.5)

            # 4. Scrape outcome messages and dialog status
            outcome = driver.execute_script("""
                var msgs = [];
                var els = document.querySelectorAll('.ui-messages-info, .ui-messages-error, .ui-growl-message, .ui-messages-info-detail, .ui-messages-error-detail');
                for (var i = 0; i < els.length; i++) {
                    var t = els[i].innerText.trim();
                    if (t) msgs.push(t);
                }

                // Check if reason modal has closed
                var input = document.getElementById('Inputreject');
                var isModalOpen = !!(input && input.offsetParent !== null && window.getComputedStyle(input).display !== 'none');

                return {
                    messages: msgs,
                    is_modal_open: isModalOpen
                };
            """)

            messages = outcome.get("messages", [])
            is_modal_open = outcome.get("is_modal_open", True)
            combined_msg = " | ".join(messages) if messages else ""

            is_error = any("fail" in m.lower() or "error" in m.lower() or "already" in m.lower() for m in messages)
            is_success = any("success" in m.lower() or "released" in m.lower() or "unlocked" in m.lower() for m in messages)

            if not is_error and (is_success or not is_modal_open):
                ref_id = f"UNLOCK_{clean_reg}_{int(time.time())}"
                success_msg = combined_msg or f"VLTD successfully unlocked/released for vehicle {reg_no}."
                execution_logger.log(
                    level=LogLevel.INFO,
                    execution_type=ExecutionType.TRANSACTION_RESULT,
                    run_id=run_id,
                    stage="FINAL_VERIFICATION",
                    action="UNLOCK_VLTD",
                    result="SUCCESS",
                    message=success_msg
                )
                return True, success_msg, ref_id
            else:
                fail_msg = combined_msg or f"Portal rejected or did not confirm VLTD unlock for vehicle {reg_no}."
                execution_logger.log(
                    level=LogLevel.ERROR,
                    execution_type=ExecutionType.TRANSACTION_RESULT,
                    run_id=run_id,
                    stage="FINAL_VERIFICATION",
                    action="UNLOCK_VLTD",
                    result="FAILED",
                    message=fail_msg
                )
                return False, fail_msg, None

        except Exception as e:
            err = f"Execution exception during final unlock: {str(e)}"
            logger.error(err, exc_info=True)
            return False, err, None

delete_automation = DeleteVltdAutomationHandler()

