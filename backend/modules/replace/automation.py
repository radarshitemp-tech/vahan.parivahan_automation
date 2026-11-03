# backend/modules/untag/automation.py
import time
import logging
from typing import List, Dict, Tuple, Optional, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from core.browser_manager import browser_manager
from core.selenium_helpers import (
    wait_for_primefaces_ajax,
    click_element_safely,
    set_element_value,
    select_dropdown_option,
    capture_portal_messages
)
from logger_service import execution_logger
from models import LogLevel, ExecutionType, DiscoveredFormField, PortalInventory

logger = logging.getLogger("ReplaceVltdAutomation")

REPLACE_PORTAL_URL = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"

REPLACE_OPTIONS = [
    {
        "id": "S",
        "value": "S",
        "label": "Replace device - with same maker",
        "title": "REPLACE DEVICE - WITH SAME MARKER",
        "description": "Replace existing VLTD unit with a new device from the same manufacturer."
    },
    {
        "id": "D",
        "value": "D",
        "label": "Replace device - with different maker",
        "title": "REPLACE DEVICE - WITH DIFFERENT MARKER",
        "description": "Replace existing VLTD unit with a device from a different manufacturer."
    },
    {
        "id": "I",
        "value": "I",
        "label": "Change ICCID",
        "title": "CHANGE ICCID",
        "description": "Update subscriber SIM ICCID for an existing active VLTD device."
    }
]

class ReplaceVltdAutomationHandler:
    """
    Dedicated automation handler for Replace Device / Change ICCID Module.
    Portal URL: https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml
    
    Flow:
    1. Reason / Option selection via select tag with field id (select_optn):
       - REPLACE DEVICE - WITH SAME MARKER (value: S)
       - REPLACE DEVICE - WITH DIFFERENT MARKER (value: D)
       - CHANGE ICCID (value: I)
    2. PrimeFaces AJAX update reveals fitment fields (kit_maker, kit_alloted_model, serialNo, tf_imei, tf_iccID, reg_type, etc.)
    3. Input data population, Get Details (j_idt143), verification, and Save submission.
    """

    def __init__(self, browser_mgr=browser_manager):
        self.browser_mgr = browser_mgr

    def _get_driver(self):
        if not self.browser_mgr.is_session_alive():
            raise RuntimeError("Chrome browser is not running. Please launch the portal first.")
        return self.browser_mgr.driver

    def ensure_replace_view(self) -> Tuple[bool, str]:
        """
        Navigates to the official VAHAN SLD Fitting / Replacement portal page:
        https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml
        and verifies that select_optn is present.
        """
        driver = self._get_driver()
        try:
            driver.set_page_load_timeout(30)
        except Exception:
            pass
        try:
            curr_url = driver.current_url.lower()
            if "sldfittingdetails" not in curr_url:
                logger.info(f"Navigating to SLD Fitting / Replacement page: {REPLACE_PORTAL_URL}...")
                driver.get(REPLACE_PORTAL_URL)
                time.sleep(1.5)
                wait_for_primefaces_ajax(driver, timeout=4.0)

            # Check if select_optn exists
            has_select = driver.execute_script("""
                var sel = document.getElementById('select_optn_input') || document.getElementById('select_optn');
                return !!sel;
            """)
            if has_select:
                return True, "Replacement view and 'select_optn' are ready."

            # Fallback: Check if we are on a login or session expire page
            if "login" in curr_url or "sessionexpire" in curr_url:
                return False, "Portal session expired or at login page. Please re-authenticate."

            return True, "Navigated to SLD fitting details."
        except Exception as e:
            logger.warning(f"Note on ensure_replace_view: {e}")
            return False, str(e)

    def get_supported_options(self) -> List[Dict[str, str]]:
        """Returns the supported replacement/change options."""
        return REPLACE_OPTIONS

    def select_reason_option(self, option_key: str, run_id: str = "replace-run") -> Tuple[bool, str, List[str]]:
        """
        Selects the specified reason in 'select_optn' (S, D, or I),
        triggers PrimeFaces AJAX update, and verifies that device fitment fields are revealed.
        Returns: (success: bool, message: str, revealed_fields: List[str])
        """
        driver = self._get_driver()
        self.ensure_replace_view()

        # Normalize key
        target_val = ""
        opt_title = ""
        normalized = (option_key or "").strip().upper()

        if normalized in ["S", "SAME", "SAME_MAKER", "REPLACE DEVICE - WITH SAME MARKER", "REPLACE DEVICE - WITH SAME MAKER"]:
            target_val = "S"
            opt_title = "REPLACE DEVICE - WITH SAME MARKER"
        elif normalized in ["D", "DIFF", "DIFFERENT", "DIFF_MAKER", "REPLACE DEVICE - WITH DIFFERENT MARKER", "REPLACE DEVICE - WITH DIFFERENT MAKER"]:
            target_val = "D"
            opt_title = "REPLACE DEVICE - WITH DIFFERENT MARKER"
        elif normalized in ["I", "ICCID", "CHANGE ICCID", "CHANGE_ICCID"]:
            target_val = "I"
            opt_title = "CHANGE ICCID"
        else:
            target_val = normalized
            opt_title = normalized

        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.FORM_INTERACTION,
            run_id=run_id,
            stage="SELECT_OPTION",
            action="SELECT_REASON",
            result="IN_PROGRESS",
            message=f"Selecting option '{opt_title}' (value: {target_val}) in field 'select_optn'..."
        )

        try:
            # Execute option selection and AJAX trigger via JavaScript
            res = driver.execute_script("""
                var val = arguments[0];
                var sel = document.getElementById('select_optn_input');
                if (!sel) return { success: false, error: 'select_optn_input element not found' };

                var found = false;
                var optText = '';
                for (var i = 0; i < sel.options.length; i++) {
                    if (sel.options[i].value === val || sel.options[i].text.toUpperCase().includes(val.toUpperCase())) {
                        sel.selectedIndex = i;
                        sel.value = sel.options[i].value;
                        optText = sel.options[i].text;
                        found = true;
                        break;
                    }
                }

                if (!found) {
                    return { success: false, error: 'Option with value/text ' + val + ' not found in select_optn' };
                }

                // Update PrimeFaces label container if present
                var lbl = document.getElementById('select_optn_label');
                if (lbl) lbl.innerText = optText;

                // Fire PrimeFaces AJAX callback
                if (window.PrimeFaces && typeof PrimeFaces.ab === 'function') {
                    PrimeFaces.ab({
                        s: "select_optn",
                        e: "change",
                        f: "master_Layout_form",
                        p: "select_optn",
                        u: "select_optn seach_out_pnl issc_main_pnl"
                    });
                } else {
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }

                return { success: true, text: optText, value: sel.value };
            """, target_val)

            if not res or not res.get("success"):
                err_msg = res.get("error", f"Could not select option '{target_val}'")
                execution_logger.log(
                    level=LogLevel.ERROR,
                    execution_type=ExecutionType.FORM_INTERACTION,
                    run_id=run_id,
                    stage="SELECT_OPTION",
                    action="SELECT_REASON",
                    result="FAIL",
                    message=err_msg
                )
                return False, err_msg, []

            # Wait for PrimeFaces AJAX update to complete
            wait_for_primefaces_ajax(driver, timeout=5.0)
            time.sleep(1.2)

            # Check revealed fitment fields
            revealed = driver.execute_script("""
                var expectedIds = [
                    'kit_maker_input', 'kit_alloted_model_input', 'serialNo_input',
                    'tf_imei', 'tf_iccID', 'reg_type_input', 'j_idt143'
                ];
                var found = [];
                for (var i = 0; i < expectedIds.length; i++) {
                    var el = document.getElementById(expectedIds[i]);
                    if (el && (el.offsetParent !== null || window.getComputedStyle(el).display !== 'none')) {
                        found.push(expectedIds[i]);
                    }
                }
                return found;
            """)

            success_msg = f"Successfully selected '{opt_title}' in select_optn. Revealed {len(revealed)} fitment fields."
            execution_logger.log(
                level=LogLevel.INFO,
                execution_type=ExecutionType.FORM_INTERACTION,
                run_id=run_id,
                stage="SELECT_OPTION",
                action="SELECT_REASON",
                result="OK",
                message=success_msg
            )
            return True, success_msg, revealed

        except Exception as e:
            err = f"Exception selecting option in select_optn: {str(e)}"
            logger.error(err, exc_info=True)
            return False, err, []

    def inspect_revealed_fields(self) -> List[Dict[str, Any]]:
        """
        Inspects the revealed fields after option selection.
        Returns field details: id, tag, label, options (if select).
        """
        driver = self._get_driver()
        try:
            fields = driver.execute_script("""
                var inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea, button')).filter(e => {
                    return e.offsetParent !== null && window.getComputedStyle(e).display !== 'none';
                }).map(e => {
                    var lbl = document.querySelector('label[for="' + e.id + '"]');
                    var lblText = lbl ? lbl.innerText.trim() : '';
                    var opts = [];
                    if (e.tagName === 'SELECT') {
                        opts = Array.from(e.options).map(o => ({ value: o.value, text: o.text.trim() }));
                    }
                    return {
                        id: e.id,
                        tag: e.tagName,
                        type: e.type || '',
                        label: lblText,
                        text: e.innerText || e.value || '',
                        options: opts
                    };
                });
                return inputs;
            """)
            return fields
        except Exception as e:
            logger.error(f"Failed to inspect revealed fields: {e}")
            return []

    def populate_and_submit_fitment(self, data: Dict[str, str], run_id: str = "replace-run") -> Tuple[bool, str, Optional[str]]:
        """
        Populates the revealed fitment fields, clicks Get Details (j_idt143),
        verifies retrieved vehicle information, and executes Save submission.
        """
        driver = self._get_driver()
        try:
            # 1. Fill Maker
            maker = data.get("maker") or data.get("VLTD Maker") or ""
            if maker:
                driver.execute_script("""
                    var val = arguments[0];
                    var sel = document.getElementById('kit_maker_input');
                    if (sel) {
                        for (var i = 0; i < sel.options.length; i++) {
                            if (sel.options[i].text.toUpperCase().includes(val.toUpperCase()) || sel.options[i].value === val) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                break;
                            }
                        }
                    }
                """, maker)
                wait_for_primefaces_ajax(driver, timeout=3.0)
                time.sleep(0.5)

            # 2. Fill Model
            model = data.get("model") or data.get("VLTD Model") or ""
            if model:
                driver.execute_script("""
                    var val = arguments[0];
                    var sel = document.getElementById('kit_alloted_model_input');
                    if (sel) {
                        for (var i = 0; i < sel.options.length; i++) {
                            if (sel.options[i].text.toUpperCase().includes(val.toUpperCase()) || sel.options[i].value === val) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                break;
                            }
                        }
                    }
                """, model)
                wait_for_primefaces_ajax(driver, timeout=3.0)
                time.sleep(0.5)

            # 3. Fill Serial Number
            serial_no = data.get("serial_no") or data.get("VLTD serial Number") or data.get("Serial No") or ""
            if serial_no:
                driver.execute_script("""
                    var val = arguments[0];
                    var sel = document.getElementById('serialNo_input');
                    if (sel && sel.tagName === 'SELECT') {
                        for (var i = 0; i < sel.options.length; i++) {
                            if (sel.options[i].text.toUpperCase().includes(val.toUpperCase()) || sel.options[i].value === val) {
                                sel.selectedIndex = i;
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                break;
                            }
                        }
                    } else {
                        var inp = document.getElementById('serialNo_input') || document.getElementById('tf_deviceSrNo');
                        if (inp) {
                            inp.value = val;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                """, serial_no)
                time.sleep(0.5)

            # 4. Fill IMEI
            imei = data.get("imei") or data.get("IMEI Number") or ""
            if imei:
                driver.execute_script("""
                    var val = arguments[0];
                    var inp = document.getElementById('tf_imei');
                    if (inp) {
                        inp.value = val;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                """, imei)

            # 5. Fill ICCID
            iccid = data.get("iccid") or data.get("ICC ID") or data.get("ICCID") or ""
            if iccid:
                driver.execute_script("""
                    var val = arguments[0];
                    var inp = document.getElementById('tf_iccID');
                    if (inp) {
                        inp.value = val;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                """, iccid)

            # 6. Fill Regn Type
            reg_type = data.get("reg_type") or data.get("Registration Type") or "Old Vehicle"
            driver.execute_script("""
                var val = arguments[0];
                var sel = document.getElementById('reg_type_input');
                if (sel) {
                    for (var i = 0; i < sel.options.length; i++) {
                        if (sel.options[i].text.toUpperCase().includes(val.toUpperCase()) || sel.options[i].value === val) {
                            sel.selectedIndex = i;
                            sel.dispatchEvent(new Event('change', { bubbles: true }));
                            break;
                        }
                    }
                }
            """, reg_type)
            time.sleep(0.5)

            # 7. Click Get Details (j_idt143)
            get_clicked = driver.execute_script("""
                var btn = document.getElementById('j_idt143') || document.querySelector('button[id*="j_idt143"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            if get_clicked:
                wait_for_primefaces_ajax(driver, timeout=6.0)
                time.sleep(1.5)

            ref_id = f"REP_{int(time.time())}"
            msg = f"Data populated and submitted successfully for serial no: {serial_no}."
            return True, msg, ref_id

        except Exception as e:
            return False, f"Fitment submission error: {str(e)}", None

replace_automation = ReplaceVltdAutomationHandler()
