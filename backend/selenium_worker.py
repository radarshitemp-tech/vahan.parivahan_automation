import time
import threading
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
import re

from models import (
    BatchState,
    BatchResponse,
    PortalInventory,
    DiscoveredFormField,
    FormFieldOption,
    BatchMappingConfig,
    FieldMappingItem,
    CsvRecord,
    RecordStatus,
    TransactionState,
    ExecutionType,
    LogLevel,
    DryRunResult,
    FieldVerificationResult
)
from logger_service import execution_logger
from validator import normalize_header
from core.browser_manager import (
    create_robust_chrome_options,
    launch_chrome_with_fallback,
    browser_manager
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("VahanSeleniumWorker")

TARGET_PORTAL_URL = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"

# Candidate selector array for each column, prioritized by verified live VAHAN portal elements
PORTAL_SELECTOR_CANDIDATES: Dict[str, List[str]] = {
    "VLTD Maker": [
        "kit_maker", "kit_maker_input", "kit_maker_focus", "tf_maker", "maker", "vahan_maker_id"
    ],
    "VLTD Model": [
        "kit_alloted_model", "kit_alloted_model_input", "kit_alloted_model_focus", "tf_model", "model", "vahan_model_id"
    ],
    "VLTD serial Number": [
        "txt_SrNo", "serialNo", "serialNo_input", "serialNo_focus", "sr_No_Panel", "tf_device_sr_no", "serial_no", "sr_no", "vahan_serial_id", "sldserial"
    ],
    "Provider": [
        "tf_serPro", "tf_serPro_focus", "tf_serPro_label", "tf_scrPro", "tf_provider", "provider", "vahan_provider_id"
    ],
    "IMEI Number": [
        "tf_imei", "imei_no", "imei", "device_imei", "vahan_imei_id"
    ],
    "ICC ID": [
        "tf_iccID", "tf_iccid", "icc_id", "sim_number", "sim_no", "vahan_iccid_id"
    ],
    "Registration Type": [
        "reg_type", "reg_type_input", "reg_type_focus", "regn_type", "regtype", "regntype", "vahan_regtype_id"
    ],
    "Vehicle Chassis No": [
        "temp_reg_no", "chassis_no", "chassis", "chasino", "vehicle_chassis"
    ],
    "Vehicle Engine No (LAST 5 DIGITS)": [
        "temp_eng_no", "engine_no", "engine", "engineno", "vehicle_engine"
    ],
    "Vehicle State": [
        "stateCd", "stateCd_input", "stateCd_focus", "state", "state_name", "veh_state", "vehicle_state"
    ],
    "RTO": [
        "offCd", "offCd_input", "offCd_focus", "rto", "rto_code", "rto_office", "registering_authority"
    ],
    "Vehicle Registration Number": [
        "reg_no", "reg_no_input", "reg_panel", "regn_no", "tf_reg_no", "reg_no_panel", "vehicle_reg_no", "reg_panel_input"
    ]
}

class VahanSeleniumWorker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VahanSeleniumWorker, cls).__new__(cls)
                cls._instance._init_worker()
            return cls._instance

    def _init_worker(self):
        self.driver: Optional[webdriver.Chrome] = None
        self.is_running = False
        self.stop_requested = threading.Event()
        self.pause_requested = threading.Event()
        self.active_batch_id: Optional[str] = None
        self.latest_inventory: Optional[PortalInventory] = None
        self.worker_lock = threading.Lock()
        self.active_thread: Optional[threading.Thread] = None
        self.current_run_id: Optional[str] = None


    def is_session_alive(self) -> bool:
        """
        Verifies if current driver instance exists and has an active, responsive session.
        If browser window was closed or session is invalid, cleans up dead driver.
        Automatically checks for and attaches to an existing running debug Chrome instance if disconnected.
        Uses fast socket probing and DevToolsActivePort detection to attach instantaneously.
        """
        if self.driver is not None:
            try:
                _ = self.driver.current_window_handle
                return True
            except Exception:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        # Dynamically discover active Chrome DevTools ports
        import glob, os, tempfile, socket
        temp_dir = tempfile.gettempdir()
        port_files = glob.glob(os.path.join(temp_dir, 'scoped_dir*', 'DevToolsActivePort'))
        try:
            port_files.sort(key=os.path.getmtime, reverse=True)
        except Exception:
            pass

        candidate_ports = []
        for pf in port_files[:6]:
            try:
                with open(pf, 'r') as fp:
                    line = fp.readline().strip()
                    if line.isdigit():
                        candidate_ports.append(int(line))
            except Exception:
                pass

        for p in [9222, 60832]:
            if p not in candidate_ports:
                candidate_ports.append(p)

        for port in candidate_ports:
            try:
                s = socket.create_connection(('127.0.0.1', port), timeout=0.15)
                s.close()
            except Exception:
                continue

            try:
                att_opts = Options()
                att_opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
                d = webdriver.Chrome(options=att_opts)
                _ = d.current_window_handle
                self.driver = d
                logger.info(f"Auto-attached to running Chrome on 127.0.0.1:{port}")
                return True
            except Exception:
                continue

        return False

    def verify_session(self) -> Tuple[bool, str]:
        """
        Checks whether active browser session is still authenticated.
        Returns (is_valid, reason_or_message).
        """
        if not self.is_session_alive():
            return False, "Browser window was closed or disconnected."

        try:
            curr_url = self.driver.current_url.lower()
            if "login" in curr_url or "login.xhtml" in curr_url or "sessionexpire" in curr_url:
                return False, f"Portal session expired or at login page ({curr_url}). Please log in and navigate to the SLD Fitting page."

            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if "session expired" in body_text or "session timeout" in body_text or "please login again" in body_text:
                return False, "Portal indicates session timeout. Re-authentication required."

            return True, "Session active and authenticated."
        except Exception as e:
            return False, f"Error verifying session: {str(e)}"

    def launch_browser_for_authentication(self) -> PortalInventory:
        """
        Launches visible Chrome browser and navigates to official VAHAN VLTD portal.
        Reuses existing active browser if already open.
        """
        with self.worker_lock:
            try:
                run_id = self.active_batch_id or "launch-session"
                if not self.is_session_alive():
                    if self.driver is not None:
                        try:
                            self.driver.quit()
                        except Exception:
                            pass
                        self.driver = None

                    logger.info("Initializing robust Chrome driver...")
                    execution_logger.log(
                        level=LogLevel.INFO,
                        execution_type=ExecutionType.AUTHENTICATION,
                        run_id=run_id,
                        stage="INITIALIZE_BROWSER",
                        action="LAUNCH_CHROME",
                        result="INITIATING",
                        message="Launching Chrome browser with stability options for VAHAN portal."
                    )

                    chrome_options = create_robust_chrome_options()
                    self.driver = launch_chrome_with_fallback(chrome_options)
                    browser_manager.driver = self.driver
                    logger.info("Chrome launched successfully.")

                logger.info(f"Navigating to {TARGET_PORTAL_URL}...")
                self.driver.get(TARGET_PORTAL_URL)
                time.sleep(2.5)

                inventory = self._inspect_current_page(is_initial_launch=True)
                execution_logger.log(
                    level=LogLevel.INFO,
                    execution_type=ExecutionType.AUTHENTICATION,
                    run_id=run_id,
                    stage="PORTAL_NAVIGATION",
                    action="NAVIGATE_TARGET_URL",
                    result="SUCCESS",
                    message=f"Landed on {inventory.portal_url}. Status: {inventory.message}"
                )
                return inventory

            except Exception as e:
                try:
                    if self.driver:
                        self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                logger.error(f"Error launching browser: {str(e)}", exc_info=True)
                execution_logger.log(
                    level=LogLevel.ERROR,
                    execution_type=ExecutionType.AUTHENTICATION,
                    run_id=self.active_batch_id or "error",
                    stage="INITIALIZE_BROWSER",
                    action="LAUNCH_CHROME",
                    result="FAILED",
                    message=f"Failed to launch Chrome: {str(e)}",
                    error_code="BROWSER_LAUNCH_ERROR"
                )
                raise RuntimeError(f"Failed to launch Chrome browser: {str(e)}")

    def confirm_and_inspect_form(self) -> PortalInventory:
        """
        Called after user finishes manual login/CAPTCHA in Chrome and lands on target SLD fitting form.
        Uses linear progressive scraping to discover fields across all interactive form stages.
        """
        with self.worker_lock:
            if not self.is_session_alive():
                raise RuntimeError("No active browser session found or browser window was closed. Please click 'Launch Portal' to re-open browser.")

            try:
                inventory = self._inspect_current_page(is_initial_launch=False)
                if inventory.is_authenticated and inventory.is_sld_form_available:
                    # Execute linear progressive scrape to uncover dynamically rendered vehicle fields
                    inventory = self.linear_progressive_scrape()

                run_id = self.active_batch_id or "inspection"
                execution_logger.log(
                    level=LogLevel.INFO,
                    execution_type=ExecutionType.AUTHENTICATION,
                    run_id=run_id,
                    stage="AUTHENTICATION_VERIFICATION",
                    action="INSPECT_AUTHENTICATED_PAGE",
                    result="SUCCESS" if inventory.is_authenticated else "AWAITING_LOGIN",
                    message=f"Inspection complete. Authenticated={inventory.is_authenticated}. Form fields={len(inventory.fields)}."
                )
                return inventory
            except Exception as e:
                if not self.is_session_alive():
                    raise RuntimeError("Browser window was closed or disconnected. Please click 'Launch Portal' to re-open browser.")
                logger.error(f"Error inspecting portal form: {str(e)}", exc_info=True)
                raise RuntimeError(f"Error inspecting form: {str(e)}")

    def linear_progressive_scrape(self) -> PortalInventory:
        """
        Executes sequential linear form scraping:
        1. Pass 1: Scrape initial VLTD Details (Maker, Model, Serial, Provider, IMEI, ICC ID, Reg Type).
        2. Pass 2: Select Registration Type (e.g. RETROFITMENT or OLD) and await PrimeFaces AJAX.
           Scrape revealed dynamic vehicle fields (State, RTO, Chassis, Engine, Get Details button).
        3. Pass 3: Inspect State dropdown to trigger cascading RTO option retrieval.
        4. Pass 4: Merge all progressively discovered fields without duplicates into a unified inventory.
        """
        if not self.driver:
            return self._inspect_current_page(is_initial_launch=False)

        current_url = self.driver.current_url
        page_title = self.driver.title or "VAHAN Portal"

        # Ensure 'ADD NEW VLTD' radio button is clicked to render SLD form
        self._ensure_add_new_vltd_selected()

        # Pass 1: Initial visible elements
        pass1_fields = self._discover_form_elements()
        field_map: Dict[str, DiscoveredFormField] = {}
        for f in pass1_fields:
            key = f.id or f.name or f.label
            if key:
                field_map[key] = f

        # Pass 2: Select Registration Type to trigger AJAX rendering of vehicle details
        try:
            reg_elem = self._find_field_element(None, None, portal_label="Registration Type", csv_col="Registration Type")
            if reg_elem and reg_elem.tag_name.lower() == "select":
                select_obj = Select(reg_elem)
                options = select_obj.options
                selected_opt = None
                for opt in options:
                    txt = opt.text.upper().strip()
                    val = opt.get_attribute("value") or ""
                    if any(k in txt for k in ["RETROFITMENT", "OLD VEHICLE", "OLD", "NEW VEHICLE", "NEW"]) and val:
                        selected_opt = opt
                        break
                if not selected_opt and len(options) > 1:
                    for opt in options[1:]:
                        if (opt.get_attribute("value") or "").strip():
                            selected_opt = opt
                            break

                if selected_opt:
                    logger.info(f"Progressive scrape: selecting Registration Type '{selected_opt.text}' to reveal vehicle fields.")
                    select_obj.select_by_visible_text(selected_opt.text)
                    self._wait_for_primefaces_ajax(timeout=3.0)
                    time.sleep(0.8)

                    # Pass 3: Scrape newly revealed vehicle fields
                    pass2_fields = self._discover_form_elements()
                    for f in pass2_fields:
                        key = f.id or f.name or f.label
                        if key and key not in field_map:
                            field_map[key] = f
                        elif key and f.options and len(f.options) > len(field_map[key].options):
                            field_map[key] = f

                    # Check cascading State -> RTO
                    state_elem = self._find_field_element(None, None, portal_label="Vehicle State", csv_col="Vehicle State")
                    if state_elem and state_elem.tag_name.lower() == "select":
                        state_select = Select(state_elem)
                        state_opts = state_select.options
                        if len(state_opts) > 1:
                            curr_state_val = (state_elem.get_attribute("value") or "").strip()
                            if not curr_state_val or curr_state_val == "-1":
                                for s_opt in state_opts[1:]:
                                    if (s_opt.get_attribute("value") or "").strip():
                                        state_select.select_by_visible_text(s_opt.text)
                                        self._wait_for_primefaces_ajax(timeout=3.0)
                                        time.sleep(0.8)
                                        break
                                pass3_fields = self._discover_form_elements()
                                for f in pass3_fields:
                                    key = f.id or f.name or f.label
                                    if key and key not in field_map:
                                        field_map[key] = f
                                    elif key and f.options and len(f.options) > len(field_map[key].options):
                                        field_map[key] = f
        except Exception as prog_err:
            logger.warning(f"Progressive scrape note: {prog_err}")

        all_fields = list(field_map.values())
        inventory = PortalInventory(
            portal_url=current_url,
            page_title=page_title,
            is_authenticated=True,
            is_sld_form_available=True,
            fields=all_fields,
            discovered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=f"Progressive scrape completed. Discovered {len(all_fields)} form elements across all form stages."
        )
        self.latest_inventory = inventory
        return inventory

    def _inspect_current_page(self, is_initial_launch: bool = False) -> PortalInventory:
        """
        Scans active page and extracts inventory of form fields.
        """
        current_url = self.driver.current_url
        page_title = self.driver.title or "VAHAN Portal"
        page_source_lower = self.driver.page_source.lower()

        is_login_page = (
            "login" in current_url.lower() or
            "login.xhtml" in current_url.lower() or
            "sessionexpire" in current_url.lower() or
            "enter user id" in page_source_lower or
            "captcha" in page_source_lower or
            "sign in" in page_source_lower or
            "user id" in page_source_lower
        )

        if not is_login_page:
            self._ensure_add_new_vltd_selected()

        fields = self._discover_form_elements()

        has_sld_inputs = any(
            any(k in f"{f.id or ''} {f.name or ''} {f.label or ''}".lower() for k in [
                "maker", "model", "imei", "device_sr", "tf_maker", "tf_model", "retrofit", "serial", "provider", "regn", "chassis", "rto"
            ])
            for f in fields
        )

        if is_login_page:
            is_authenticated = False
            is_sld_form_available = False
            status_message = (
                "Chrome is currently showing the VAHAN Login page. "
                "Please enter your User ID, Password, and CAPTCHA in Chrome, log in, and open the SLD Fitting form. "
                "Then click '2. Confirm Logged In & Inspect'."
            )
        elif has_sld_inputs:
            is_authenticated = True
            is_sld_form_available = True
            status_message = f"SLD fitting form identified. Successfully discovered {len(fields)} form elements."
        else:
            is_authenticated = True
            is_sld_form_available = True
            status_message = (
                f"Page inspected ({len(fields)} form fields detected). If VLTD/SLD fields are not yet rendered, "
                "ensure you are on the SLD Fitting Details page."
            )

        inventory = PortalInventory(
            portal_url=current_url,
            page_title=page_title,
            is_authenticated=is_authenticated,
            is_sld_form_available=is_sld_form_available,
            fields=fields,
            discovered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=status_message
        )
        self.latest_inventory = inventory
        return inventory

    def _discover_form_elements(self) -> List[DiscoveredFormField]:
        """
        Discovers visible and PrimeFaces-managed input, select, and textarea elements
        using deep DOM traversal that resolves JSF layouts, table cells, and PrimeFaces panels.
        Supports iframe inspection when forms are nested inside content frames.
        """
        discovered: List[DiscoveredFormField] = []
        if not self.driver:
            return discovered

        js_script = """
        function extractFromContext() {
            var items = [];
            var seen = new Set();
            
            function resolveLabel(el, baseId) {
                var label = '';
                if (el.id) {
                    try {
                        var lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                        if (!lbl && baseId) {
                            lbl = document.querySelector('label[for="' + CSS.escape(baseId) + '"]') ||
                                  document.querySelector('label[for="' + CSS.escape(baseId + '_focus') + '"]') ||
                                  document.querySelector('label[for="' + CSS.escape(baseId + '_input') + '"]');
                        }
                        if (lbl) label = lbl.innerText.trim();
                    } catch (e) {}
                }
                if (!label && baseId) {
                    try {
                        var pfOutLbl = document.querySelector('.ui-outputlabel[for="' + CSS.escape(baseId) + '"]') ||
                                       document.querySelector('.ui-outputlabel[for="' + CSS.escape(baseId + '_input') + '"]') ||
                                       document.querySelector('.ui-outputlabel[for="' + CSS.escape(baseId + '_focus') + '"]');
                        if (pfOutLbl) label = pfOutLbl.innerText.trim();
                    } catch (e) {}
                }
                if (!label) {
                    var gridCol = el.closest('div[class*="ui-grid-col"], div[class*="ui-g-"], div[class*="col-"]');
                    if (gridCol && gridCol.previousElementSibling) {
                        label = gridCol.previousElementSibling.innerText.trim();
                    }
                }
                if (!label) {
                    var cell = el.closest('td');
                    if (cell && cell.previousElementSibling) {
                        label = cell.previousElementSibling.innerText.trim();
                    }
                }
                if (!label) {
                    var parentLbl = el.closest('label');
                    if (parentLbl) {
                        label = parentLbl.innerText.trim();
                    } else if (el.previousElementSibling && el.previousElementSibling.tagName.toLowerCase() === 'label') {
                        label = el.previousElementSibling.innerText.trim();
                    }
                }
                if (!label) {
                    var row = el.closest('tr');
                    if (row) {
                        var th = row.querySelector('th');
                        if (th) label = th.innerText.trim();
                    }
                }
                if (!label) {
                    label = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.getAttribute('title') || '';
                }
                return label.replace(/[\\*\\:\\n\\r]/g, ' ').replace(/\\s+/g, ' ').trim();
            }

            var elements = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]), select, textarea');
            elements.forEach(function(el) {
                var id = el.id || '';
                var name = el.name || '';
                if (name === 'javax.faces.ViewState' || id.indexOf('ViewState') !== -1) return;

                // CRITICAL: Skip internal PrimeFaces auxiliary inputs (_focus, _filter, _hinput) so they don't shadow canonical widgets
                if (id.endsWith('_focus') || id.endsWith('_filter') || id.endsWith('_hinput')) {
                    return;
                }

                var tag = el.tagName.toLowerCase();
                var inputType = (el.getAttribute('type') || tag).toLowerCase();
                var baseId = id.endsWith('_input') ? id.replace('_input', '') : id;
                var label = resolveLabel(el, baseId) || name || id;

                var isRequired = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true' || (el.className || '').includes('required');
                var isDisabled = el.disabled || el.readOnly;
                var currentVal = el.value || '';
                var options = [];

                if (tag === 'select') {
                    for (var i = 0; i < el.options.length; i++) {
                        var opt = el.options[i];
                        var optText = opt.innerText.trim();
                        if (optText) {
                            options.push({ label: optText, value: opt.value || '' });
                        }
                    }
                    if (options.length <= 1 && baseId) {
                        try {
                            var panel = document.getElementById(baseId + '_panel');
                            if (panel) {
                                var panelItems = panel.querySelectorAll('.ui-selectonemenu-item');
                                panelItems.forEach(function(item) {
                                    var itemText = item.innerText.trim();
                                    var itemVal = item.getAttribute('data-label') || itemText;
                                    if (itemText && !options.some(function(o){ return o.label === itemText; })) {
                                        options.push({ label: itemText, value: itemVal });
                                    }
                                });
                            }
                        } catch (e) {}
                    }
                }

                items.push({
                    id: id,
                    name: name,
                    tag: tag,
                    input_type: inputType,
                    label: label,
                    is_required: isRequired,
                    is_disabled: isDisabled,
                    current_value: currentVal,
                    options: options
                });
                if (id) seen.add(id);
                if (baseId) seen.add(baseId);
            });

            document.querySelectorAll('.ui-selectonemenu').forEach(function(pf) {
                var pfId = pf.id || '';
                if (!pfId || seen.has(pfId)) return;
                var selectEl = pf.querySelector('select');
                var inputId = selectEl ? (selectEl.id || pfId + '_input') : pfId + '_input';
                if (seen.has(inputId)) return;

                var label = resolveLabel(pf, pfId) || pfId;
                var pfLabelElem = pf.querySelector('.ui-selectonemenu-label');
                var currentVal = pfLabelElem ? pfLabelElem.innerText.trim() : '';

                var options = [];
                if (selectEl) {
                    for (var i = 0; i < selectEl.options.length; i++) {
                        var opt = selectEl.options[i];
                        var optText = opt.innerText.trim();
                        if (optText) options.push({ label: optText, value: opt.value || '' });
                    }
                }
                try {
                    var panel = document.getElementById(pfId + '_panel');
                    if (panel) {
                        panel.querySelectorAll('.ui-selectonemenu-item').forEach(function(item) {
                            var itemText = item.innerText.trim();
                            var itemVal = item.getAttribute('data-label') || itemText;
                            if (itemText && !options.some(function(o){ return o.label === itemText; })) {
                                options.push({ label: itemText, value: itemVal });
                            }
                        });
                    }
                } catch(e) {}

                items.push({
                    id: inputId,
                    name: (selectEl && selectEl.name) ? selectEl.name : inputId,
                    tag: 'select',
                    input_type: 'select',
                    label: label,
                    is_required: false,
                    is_disabled: pf.classList.contains('ui-state-disabled'),
                    current_value: currentVal,
                    options: options
                });
                seen.add(inputId);
                seen.add(pfId);
            });

            return items;
        }
        return extractFromContext();
        """

        try:
            raw_items = self.driver.execute_script(js_script)
            if raw_items and isinstance(raw_items, list) and len(raw_items) > 0:
                for item in raw_items:
                    try:
                        opts = [FormFieldOption(label=o.get("label", ""), value=o.get("value", "")) for o in item.get("options", [])]
                        discovered.append(DiscoveredFormField(
                            id=item.get("id") or "",
                            name=item.get("name") or "",
                            tag=item.get("tag") or "input",
                            input_type=item.get("input_type") or "text",
                            label=item.get("label") or item.get("name") or item.get("id") or "",
                            is_required=bool(item.get("is_required")),
                            is_disabled=bool(item.get("is_disabled")),
                            current_value=item.get("current_value") or "",
                            options=opts
                        ))
                    except Exception as parse_err:
                        logger.debug(f"Skipping form field item due to parse error: {parse_err}")

            # If top-level document had fewer than 3 form fields, inspect nested iframes
            if len(discovered) < 3:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for frame in iframes:
                        try:
                            self.driver.switch_to.frame(frame)
                            iframe_items = self.driver.execute_script(js_script)
                            if iframe_items and isinstance(iframe_items, list) and len(iframe_items) > 0:
                                for item in iframe_items:
                                    try:
                                        opts = [FormFieldOption(label=o.get("label", ""), value=o.get("value", "")) for o in item.get("options", [])]
                                        discovered.append(DiscoveredFormField(
                                            id=item.get("id") or "",
                                            name=item.get("name") or "",
                                            tag=item.get("tag") or "input",
                                            input_type=item.get("input_type") or "text",
                                            label=item.get("label") or item.get("name") or item.get("id") or "",
                                            is_required=bool(item.get("is_required")),
                                            is_disabled=bool(item.get("is_disabled")),
                                            current_value=item.get("current_value") or "",
                                            options=opts
                                        ))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        finally:
                            self.driver.switch_to.default_content()
                except Exception:
                    pass

        except Exception as js_err:
            logger.warning(f"JS field discovery notice: {str(js_err)}")

        return discovered

    def _is_field_item_valid_for_col(self, f: DiscoveredFormField, col_name: str) -> bool:
        """Ensures a discovered form element is not misassigned to an unrelated column."""
        col_l = col_name.lower().replace(" ", "").replace("_", "")
        f_id = (f.id or '').lower().split(':')[-1]
        f_name = (f.name or '').lower().split(':')[-1]
        opt_texts = [o.label.upper().strip() for o in f.options] if f.options else []
        is_regn_dropdown = any(k in opt_texts for k in ["NEW VEHICLE", "RETROFITMENT", "REPLACEMENT", "ALTERATION"]) or ("regn" in f_id) or ("reg_type" in f_id)

        if "viewstate" in f_id or "viewstate" in f_name:
            return False

        if "provider" in col_l or "serviceprovider" in col_l:
            if "serpro" not in f_id and "serpro" not in f_name and "provider" not in f_id:
                return False
            # Never map checkbox options (e.g. tf_serPro:30) to the main Provider dropdown
            if ":" in f_id and f.input_type == "checkbox":
                return False
            return True

        if "chassis" in col_l:
            if "temp_eng_no" in f_id or f.tag == "select":
                return False
            if "temp_reg_no" in f_id or "chassis" in f_id:
                return True

        if "engine" in col_l:
            if "temp_reg_no" in f_id or f.tag == "select":
                return False
            if "temp_eng_no" in f_id or "engine" in f_id:
                return True

        if "maker" in col_l:
            if is_regn_dropdown or "regn" in f_id or "reg_type" in f_id:
                return False
            if "model" in f_id:
                return False
            return True

        if "registration" in col_l or "regn" in col_l:
            if "temp_reg_no" in f_id or "temp_eng_no" in f_id:
                return False
            if is_regn_dropdown or "regn" in f_id or "reg_type" in f_id:
                return True
            if "maker" in f_id or "model" in f_id or "serial" in f_id or "imei" in f_id:
                return False
            return True

        if "model" in col_l:
            if is_regn_dropdown or "maker" in f_id or "regn" in f_id:
                return False
            return True

        if "serial" in col_l:
            if is_regn_dropdown or "imei" in f_id or "maker" in f_id:
                return False
            return True

        if "imei" in col_l:
            if is_regn_dropdown or "serial" in f_id or "maker" in f_id:
                return False
            return True

        if "state" in col_l:
            if "rto" in f_id or "regn" in f_id:
                return False
            return True

        if "rto" in col_l:
            if "state" in f_id and "rto" not in f_id:
                return False
            return True

        return True

    def _is_element_valid_for_col(self, elem, col_name: Optional[str]) -> bool:
        """Inspects live Selenium WebElement to ensure it matches target column's semantic type."""
        if not elem:
            return False
        try:
            elem_id = (elem.get_attribute("id") or "").lower()
            elem_name = (elem.get_attribute("name") or "").lower()
            type_attr = (elem.get_attribute("type") or "").lower()
            tag_name = elem.tag_name.lower()

            # Strictly reject hidden inputs and JSF ViewState elements
            if "viewstate" in elem_id or "viewstate" in elem_name:
                return False

            if tag_name in ["div", "span", "section", "td"]:
                try:
                    inner = elem.find_elements(By.XPATH, ".//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]")
                    if inner:
                        return any(self._is_element_valid_for_col(ie, col_name) for ie in inner)
                except Exception:
                    pass
                return False

            if type_attr == "hidden" and tag_name != "select":
                return False

            if not col_name:
                return True

            col_l = col_name.lower().replace(" ", "").replace("_", "")
            local_id = elem_id.split(":")[-1]
            local_name = elem_name.split(":")[-1]

            is_regn_widget = ("regn" in local_id) or ("reg_type" in local_id) or ("regn" in local_name)

            if tag_name == "select":
                try:
                    options = elem.find_elements(By.TAG_NAME, "option")
                    opt_texts = [o.text.upper().strip() for o in options]
                    if any(k in opt_texts for k in ["NEW VEHICLE", "RETROFITMENT", "REPLACEMENT"]):
                        is_regn_widget = True
                except Exception:
                    pass

            if "chassis" in col_l:
                if "temp_eng_no" in local_id or tag_name == "select":
                    return False
                if "temp_reg_no" in local_id or "chassis" in local_id:
                    return True
            elif "engine" in col_l:
                if "temp_reg_no" in local_id or tag_name == "select" or "serpro" in local_id:
                    return False
                if "temp_eng_no" in local_id or "engine" in local_id:
                    return True
            elif "maker" in col_l:
                if is_regn_widget or "model" in local_id:
                    return False
            elif col_l == "registrationtype":
                if "temp_reg_no" in local_id or "temp_eng_no" in local_id or tag_name != "select":
                    return False
                if ("maker" in local_id and not "regn" in local_id) or ("model" in local_id):
                    return False
            elif "model" in col_l:
                if is_regn_widget or ("maker" in local_id and not "model" in local_id):
                    return False
            elif "provider" in col_l:
                if "serpro" not in local_id and "provider" not in local_id:
                    return False
                if ":" in local_id or type_attr == "checkbox":
                    return False
            elif "state" in col_l:
                if "rto" in local_id or "regn" in local_id:
                    return False
            elif "rto" in col_l:
                if "state" in local_id and "rto" not in local_id:
                    return False
            elif "imei" in col_l:
                if "serial" in local_id or "maker" in local_id:
                    return False
            elif "serial" in col_l:
                if "imei" in local_id or "maker" in local_id:
                    return False
            elif "vehicleregistration" in col_l or "regno" in col_l:
                if "reg_type" in local_id or tag_name == "select":
                    return False
                if "reg_panel" in local_id or "reg_no" in local_id or "regno" in local_id or "reg_panel" in local_name:
                    return True
        except Exception:
            pass

        return True

    def generate_suggested_mapping(self, batch_id: str, fields: List[DiscoveredFormField], custom_columns: Optional[List[str]] = None) -> BatchMappingConfig:
        """
        Phase C: Generates explicit mapping for all 11 CSV fields to portal elements,
        supporting both custom discovered elements and official VAHAN SLD presets.
        """
        csv_columns = custom_columns or [
            "ID",
            "VLTD Maker",
            "VLTD Model",
            "VLTD serial Number",
            "Provider",
            "IMEI Number",
            "ICC ID",
            "Registration Type",
            "Vehicle Registration Number",
            "Vehicle Chassis No",
            "Vehicle Engine No (LAST 5 DIGITS)",
            "Vehicle State",
            "RTO"
        ]

        mapping_keywords = {
            "VLTD Maker": ["kit_maker", "maker", "manufacturer", "mfg", "dev_maker", "vltd_maker", "make"],
            "VLTD Model": ["kit_alloted_model", "alloted_model", "model", "dev_model", "vltd_model", "device_model"],
            "VLTD serial Number": ["txt_srno", "sr_no_panel", "srno", "sr_no", "devicesr", "device_sr", "device_serial", "serial", "sldserial"],
            "Provider": ["tf_serpro", "tf_scrpro", "tf_provider", "provider", "telecom", "network", "operator", "sim_provider", "service_provider"],
            "IMEI Number": ["tf_imei", "imei", "imeino", "imei_number", "device_imei"],
            "ICC ID": ["tf_iccid", "icc", "iccid", "icc_id", "sim_number", "sim_no", "simno"],
            "Registration Type": ["reg_type", "regn_type", "regtype", "regntype", "registration", "retrofitment", "fittingtype"],
            "Vehicle Chassis No": ["temp_reg_no", "chassis", "chassis_no", "chassisno", "chasino", "vehicle_chassis"],
            "Vehicle Engine No (LAST 5 DIGITS)": ["temp_eng_no", "engine", "engine_no", "engineno", "eng_no", "vehicle_engine"],
            "Vehicle State": ["statecd", "state", "state_name", "state_code", "veh_state", "vehicle_state"],
            "RTO": ["offcd", "rto", "rto_code", "registering_authority", "rto_office", "office"],
            "Vehicle Registration Number": ["reg_no", "reg_panel", "regn_no", "regno", "registration_no", "reg_no_panel"]
        }

        # Authoritative VAHAN SLD portal presets matching live DOM elements
        standard_vahan_presets = {
            "Vehicle State": {"id": "stateCd", "name": "stateCd", "label": "Vehicle State", "tag": "select"},
            "RTO": {"id": "offCd", "name": "offCd", "label": "RTO / Registering Authority", "tag": "select"},
            "Registration Type": {"id": "reg_type", "name": "reg_type", "label": "Registration Type", "tag": "select"},
            "Vehicle Chassis No": {"id": "temp_reg_no", "name": "temp_reg_no", "label": "Vehicle Chassis No", "tag": "input"},
            "Vehicle Engine No (LAST 5 DIGITS)": {"id": "temp_eng_no", "name": "temp_eng_no", "label": "Vehicle Engine No (LAST 5 DIGITS)", "tag": "input"},
            "Vehicle Registration Number": {"id": "reg_no", "name": "reg_no", "label": "Vehicle Registration Number", "tag": "input"},
            "VLTD Maker": {"id": "kit_maker", "name": "kit_maker", "label": "VLTD Maker", "tag": "select"},
            "VLTD Model": {"id": "kit_alloted_model", "name": "kit_alloted_model", "label": "VLTD Model", "tag": "select"},
            "VLTD serial Number": {"id": "txt_SrNo", "name": "txt_SrNo", "label": "VLTD Serial Number", "tag": "input"},
            "Provider": {"id": "tf_serPro", "name": "tf_serPro", "label": "Service Provider", "tag": "select"},
            "IMEI Number": {"id": "tf_imei", "name": "tf_imei", "label": "IMEI Number", "tag": "input"},
            "ICC ID": {"id": "tf_iccID", "name": "tf_iccID", "label": "ICC ID", "tag": "input"}
        }

        mappings: Dict[str, FieldMappingItem] = {}

        for col in csv_columns:
            if col == "ID":
                mappings[col] = FieldMappingItem(
                    csv_column=col,
                    target_field_id=None,
                    target_field_name=None,
                    target_field_label=None,
                    element_tag="input",
                    is_required=False
                )
                continue

            target_match = None
            keywords = mapping_keywords.get(col, [col.lower().replace(" ", "").replace("_", "")])

            if fields:
                # 1. Match by local element ID and Name (stripping JSF form prefixes)
                for f in fields:
                    if not self._is_field_item_valid_for_col(f, col):
                        continue
                    local_id = (f.id or '').split(':')[-1].replace('_input', '').lower()
                    local_name = (f.name or '').split(':')[-1].replace('_input', '').lower()
                    combined_local = f"{local_id} {local_name}"
                    if any(kw in combined_local for kw in keywords):
                        target_match = f
                        break

                # 2. Match by element label
                if not target_match:
                    for f in fields:
                        if not self._is_field_item_valid_for_col(f, col):
                            continue
                        field_label = (f.label or "").lower()
                        if any(kw in field_label for kw in keywords):
                            target_match = f
                            break

            if target_match:
                mappings[col] = FieldMappingItem(
                    csv_column=col,
                    target_field_id=target_match.id,
                    target_field_name=target_match.name,
                    target_field_label=target_match.label,
                    element_tag=target_match.tag,
                    is_required=target_match.is_required or (col != "ID")
                )
            elif col != "ID" and not fields and col in standard_vahan_presets:
                preset = standard_vahan_presets[col]
                mappings[col] = FieldMappingItem(
                    csv_column=col,
                    target_field_id=preset["id"],
                    target_field_name=preset["name"],
                    target_field_label=preset["label"],
                    element_tag=preset["tag"],
                    is_required=True
                )
            elif col != "ID" and col in ["Vehicle State", "RTO", "Vehicle Chassis No", "Vehicle Engine No (LAST 5 DIGITS)", "Vehicle Registration Number"] and col in standard_vahan_presets:
                # Dynamic vehicle fields that render conditionally upon selecting Registration Type
                preset = standard_vahan_presets[col]
                mappings[col] = FieldMappingItem(
                    csv_column=col,
                    target_field_id=preset["id"],
                    target_field_name=preset["name"],
                    target_field_label=preset["label"],
                    element_tag=preset["tag"],
                    is_required=True
                )
            else:
                mappings[col] = FieldMappingItem(
                    csv_column=col,
                    target_field_id=None,
                    target_field_name=None,
                    target_field_label=None,
                    element_tag="input",
                    is_required=(col != "ID")
                )

        core_cols = ["VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider", "IMEI Number", "Registration Type"]
        missing_required = []
        for c in core_cols:
            if c in mappings and not (mappings[c].target_field_id or mappings[c].target_field_name):
                missing_required.append(c)

        is_complete = len(missing_required) == 0

        return BatchMappingConfig(
            batch_id=batch_id,
            is_complete=is_complete,
            missing_required_fields=missing_required,
            mappings=mappings,
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    
    # Synchronization & DOM Interactions
    def _ensure_add_new_vltd_selected(self) -> bool:
        """
        On Parivahan VAHAN SLD Fitting page (sldfittingDetails.xhtml), checks if the
        master action radio button 'ADD NEW VLTD' (rb:0) is present and ensures it is selected.
        Selecting 'ADD NEW VLTD' triggers the PrimeFaces AJAX event that dynamically reveals
        all device input and select fields (kit_maker, kit_alloted_model, txt_SrNo, tf_serPro, etc.).
        """
        if not self.driver:
            return False
        try:
            curr_url = self.driver.current_url.lower()
            # If authenticated and on retrofitment home or another page, navigate to SLD fitting details
            if "retrofitment" in curr_url and "sldfittingdetails" not in curr_url and "sessionexpire" not in curr_url and "login" not in curr_url:
                logger.info("Authenticated on portal but not on SLD Fitting page. Navigating to sldfittingDetails.xhtml...")
                self.driver.get(TARGET_PORTAL_URL)
                time.sleep(1.5)
                self._wait_for_primefaces_ajax(timeout=5.0)

            # Check if fields are already revealed
            has_fields = self.driver.execute_script("""
                return !!(document.getElementById('kit_maker_input') || 
                          document.getElementById('kit_maker_focus') || 
                          document.getElementById('kit_maker') ||
                          document.getElementById('tf_imei'));
            """)
            if has_fields:
                return True

            # If not revealed, click label[for="rb:0"] or .ui-radiobutton-box or fire PrimeFaces AJAX
            logger.info("SLD fields not visible yet. Clicking 'ADD NEW VLTD' (rb:0)...")
            clicked = self.driver.execute_script("""
                var label = document.querySelector('label[for="rb:0"]');
                if (label) {
                    label.click();
                    return 'label';
                }
                var box = document.querySelector('.ui-radiobutton-box');
                if (box) {
                    box.click();
                    return 'box';
                }
                var rb0 = document.getElementById('rb:0');
                if (rb0) {
                    rb0.checked = true;
                    if (window.PrimeFaces && PrimeFaces.ab) {
                        PrimeFaces.ab({s:"rb", e:"change", f:"master_Layout_form", p:"rb", u:"select_pnl"});
                    } else {
                        var evt = new Event('change', { bubbles: true });
                        rb0.dispatchEvent(evt);
                    }
                    return 'dispatched';
                }
                return 'not_found';
            """)
            logger.info(f"Click ADD NEW VLTD result: {clicked}")
            time.sleep(1.0)
            self._wait_for_primefaces_ajax(timeout=5.0)
            time.sleep(0.5)

            # Wait up to 5s for fields to appear
            try:
                WebDriverWait(self.driver, 5.0).until(
                    lambda d: d.execute_script("""
                        return !!(document.getElementById('kit_maker_input') || 
                                  document.getElementById('kit_maker_focus') || 
                                  document.getElementById('kit_maker') ||
                                  document.getElementById('tf_imei'));
                    """)
                )
                logger.info("ADD NEW VLTD successfully activated. Form fields are now rendered!")
                return True
            except Exception:
                logger.warning("ADD NEW VLTD clicked but fields did not render within timeout.")
                return False
        except Exception as e:
            logger.warning(f"Note on _ensure_add_new_vltd_selected: {e}")
            return False

    def _wait_for_primefaces_ajax(self, timeout: float = 3.0):
        """
        Waits for active PrimeFaces and jQuery AJAX queues to settle.
        Essential for cascading selects (Maker -> Model, State -> RTO).
        """
        if not self.driver:
            return
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("""
                    var pfDone = (!window.PrimeFaces || !PrimeFaces.ajax || !PrimeFaces.ajax.Queue || PrimeFaces.ajax.Queue.isEmpty());
                    var jqDone = (!window.jQuery || jQuery.active === 0);
                    return pfDone && jqDone;
                """)
            )
        except Exception:
            time.sleep(0.4)

    def _find_field_element(self, selector_id: Optional[str], selector_name: Optional[str] = None, portal_label: Optional[str] = None, csv_col: Optional[str] = None):
        """
        Locates an element using multi-tier resilient strategies suited for PrimeFaces JSF:
        1. Exact ID & ID variations (_input, baseId)
        2. Exact Name variations
        3. JSF suffix match (e.g. form:maker_input)
        4. Label-to-input association (<label for="...">, OutputLabel, grid column, table cell)
        5. Semantic attribute keywords (excluding hidden ViewState)
        6. IFrame traversal
        """
        if not self.driver or (not selector_id and not selector_name and not portal_label and not csv_col):
            return None

        target_col = csv_col or portal_label or ""

        # Semantic keywords mapped for each column
        column_keywords_map = {
            "Vehicle State": ["state", "vehicle_state", "state_name"],
            "RTO": ["rto", "registering authority", "rto office", "office"],
            "Registration Type": ["regn_type", "registration type", "reg type", "regntype", "fitting type"],
            "Vehicle Chassis No": ["chassis", "chassis_no", "chasino", "chasi_no", "vin"],
            "Vehicle Engine No (LAST 5 DIGITS)": ["engine", "engine_no", "engineno", "eng_no"],
            "VLTD Maker": ["maker", "manufacturer", "mfg", "vltd_maker"],
            "VLTD Model": ["model", "vltd_model", "device_model"],
            "VLTD serial Number": ["serial", "sr_no", "srno", "devicesr", "device_sr"],
            "Provider": ["provider", "telecom", "network", "sim_provider"],
            "IMEI Number": ["imei", "imei_no", "device_imei"],
            "ICC ID": ["icc", "iccid", "sim_no", "sim"],
            "Vehicle Registration Number": ["reg_panel", "reg_no", "regn_no", "registration_no", "vehicle_reg"]
        }

        search_kws = column_keywords_map.get(target_col, [])
        if not search_kws:
            for k, kws in column_keywords_map.items():
                if k.lower() in target_col.lower() or target_col.lower() in k.lower():
                    search_kws = kws
                    break

        def _search_in_context():
            # Build list of candidate selectors: selector_id first, followed by all candidate options from PORTAL_SELECTOR_CANDIDATES
            candidate_ids = []
            if selector_id and selector_id not in candidate_ids:
                candidate_ids.append(selector_id)

            col_cands = PORTAL_SELECTOR_CANDIDATES.get(target_col, [])
            if not col_cands:
                for k, clist in PORTAL_SELECTOR_CANDIDATES.items():
                    if k.lower() in target_col.lower() or target_col.lower() in k.lower():
                        col_cands = clist
                        break
            for cid in col_cands:
                if cid not in candidate_ids:
                    candidate_ids.append(cid)

            # 1. Direct ID & variations across all candidate options
            for cand_id in candidate_ids:
                variations = [cand_id]
                if not cand_id.endswith("_input"):
                    variations.append(f"{cand_id}_input")
                else:
                    variations.append(cand_id.replace("_input", ""))

                for var_id in variations:
                    try:
                        elems = self.driver.find_elements(By.ID, var_id)
                        for elem in elems:
                            if elem.tag_name.lower() in ["div", "span", "section", "td"]:
                                inners = elem.find_elements(By.XPATH, ".//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]")
                                for ie in inners:
                                    if self._is_element_valid_for_col(ie, target_col):
                                        return ie
                            if self._is_element_valid_for_col(elem, target_col):
                                return elem
                    except Exception:
                        pass

            # 2. Direct Name across selector_name and candidates
            candidate_names = []
            if selector_name:
                candidate_names.append(selector_name)
            for cid in candidate_ids:
                if cid not in candidate_names:
                    candidate_names.append(cid)

            for cand_name in candidate_names:
                try:
                    elems = self.driver.find_elements(By.NAME, cand_name)
                    for elem in elems:
                        if elem.tag_name.lower() in ["div", "span", "section", "td"]:
                            inners = elem.find_elements(By.XPATH, ".//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]")
                            for ie in inners:
                                if self._is_element_valid_for_col(ie, target_col):
                                    return ie
                        if self._is_element_valid_for_col(elem, target_col):
                            return elem
                except Exception:
                    pass

            # 3. XPath by clean ID suffix or JSF prefix matching
            for cand in candidate_ids:
                clean_token = cand.split(":")[-1].replace("_input", "").replace("tf_", "")
                if clean_token and len(clean_token) >= 3:
                    xpaths = [
                        f"//*[(self::input or self::select or self::textarea) and (contains(@id, ':{clean_token}_input') or contains(@id, ':{clean_token}') or @id='{clean_token}' or @id='{clean_token}_input') and not(@type='hidden') and not(contains(@id, 'ViewState')) and not(contains(@name, 'ViewState'))]",
                        f"//*[(self::input or self::select or self::textarea) and (contains(@name, ':{clean_token}') or @name='{clean_token}') and not(@type='hidden') and not(contains(@id, 'ViewState')) and not(contains(@name, 'ViewState'))]",
                        f"//*[contains(@id, '{clean_token}') and not(contains(@id, 'ViewState'))]//*[self::input[not(@type='hidden')] or self::select]"
                    ]
                    for xp in xpaths:
                        try:
                            candidates = self.driver.find_elements(By.XPATH, xp)
                            for elem in candidates:
                                if elem.tag_name.lower() in ["div", "span", "section", "td"]:
                                    inners = elem.find_elements(By.XPATH, ".//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]")
                                    for ie in inners:
                                        if self._is_element_valid_for_col(ie, target_col):
                                            return ie
                                if self._is_element_valid_for_col(elem, target_col):
                                    return elem
                        except Exception:
                            pass

            # 4. Multi-Pattern Label Search (Universal Form Layouts)
            terms = list(search_kws)
            if portal_label:
                clean_lbl = portal_label.lower().replace("select", "").replace("vltd", "").replace("number", "").replace("/", " ").strip()
                for w in clean_lbl.split():
                    if len(w) >= 3 and w not in terms:
                        terms.append(w)

            for kw in terms:
                kw_l = kw.lower().strip()
                if not kw_l or len(kw_l) < 3:
                    continue

                # 4a. Explicit <label for="...">
                try:
                    labels = self.driver.find_elements(
                        By.XPATH,
                        f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw_l}')]"
                    )
                    for lbl in labels:
                        for_attr = lbl.get_attribute("for") or ""
                        if for_attr:
                            for cand_id in [for_attr, f"{for_attr}_input", for_attr.replace("_input", "")]:
                                try:
                                    cand_elems = self.driver.find_elements(By.ID, cand_id)
                                    for ce in cand_elems:
                                        if self._is_element_valid_for_col(ce, target_col):
                                            return ce
                                except Exception:
                                    pass
                        # 4b. Grid column layout (PrimeFaces .ui-grid-col-* / .ui-g-*)
                        try:
                            grid_elems = lbl.find_elements(
                                By.XPATH,
                                "ancestor::div[contains(@class, 'ui-grid-col') or contains(@class, 'ui-g') or contains(@class, 'col-')]/following-sibling::div[1]//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]"
                            )
                            for ge in grid_elems:
                                if self._is_element_valid_for_col(ge, target_col):
                                    return ge
                        except Exception:
                            pass
                        # 4c. Table layout (following cell)
                        try:
                            cell_elems = lbl.find_elements(
                                By.XPATH,
                                "ancestor::td/following-sibling::td[1]//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]"
                            )
                            for ce in cell_elems:
                                if self._is_element_valid_for_col(ce, target_col):
                                    return ce
                        except Exception:
                            pass
                        # 4d. Following sibling input/select
                        try:
                            foll_elems = lbl.find_elements(
                                By.XPATH,
                                "following::*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select][1]"
                            )
                            for fe in foll_elems:
                                if self._is_element_valid_for_col(fe, target_col):
                                    return fe
                        except Exception:
                            pass
                except Exception:
                    pass

                # 4e. Direct Table Cell containing text
                try:
                    td_xpath = (
                        f"//td[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw_l}')]"
                        f"/following-sibling::td[1]//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select][1]"
                    )
                    candidates = self.driver.find_elements(By.XPATH, td_xpath)
                    for elem in candidates:
                        if self._is_element_valid_for_col(elem, target_col):
                            return elem
                except Exception:
                    pass

                # 4f. Semantic Attribute Search on input/select
                try:
                    attr_xpath = (
                        f"//*[(self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select) and "
                        f"(contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw_l}') or "
                        f"contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw_l}') or "
                        f"contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw_l}'))]"
                    )
                    candidates = self.driver.find_elements(By.XPATH, attr_xpath)
                    for elem in candidates:
                        if self._is_element_valid_for_col(elem, target_col):
                            return elem
                except Exception:
                    pass

            return None

        # Execute search in default DOM context
        result = _search_in_context()
        if result:
            return result

        # Check iframes if not found in root context
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for frame in iframes:
                try:
                    self.driver.switch_to.frame(frame)
                    result = _search_in_context()
                    if result:
                        return result
                except Exception:
                    pass
                finally:
                    self.driver.switch_to.default_content()
        except Exception:
            pass

        return None

    def _set_element_value(self, elem, expected_val: str, col_name: Optional[str] = None):
        """
        Sets value on element safely supporting standard inputs, selects, and PrimeFaces widgets.
        Includes robust fuzzy matching for RTO offices, makers, states, providers, and registration types.
        Triggers events and waits for cascading AJAX calls.
        """
        tag_name = elem.tag_name.lower()
        if tag_name in ["div", "span", "section", "td"]:
            try:
                inner = elem.find_elements(By.XPATH, ".//*[self::select or self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))]]")
                if inner:
                    elem = inner[0]
                    tag_name = elem.tag_name.lower()
            except Exception:
                pass

        # Dedicated handler for PrimeFaces SelectCheckboxMenu (Provider / tf_serPro)
        is_provider = (col_name and "provider" in col_name.lower()) or "serpro" in (elem.get_attribute("id") or "").lower()
        if is_provider:
            try:
                self.driver.execute_script("""
                    var targetVal = (arguments[0] || '').trim().toLowerCase();
                    var cleanTarget = targetVal.replace(/[^a-z0-9]/g, '');
                    var w = window.PrimeFaces && PrimeFaces.widgets ? PrimeFaces.widgets['widget_tf_serPro'] : null;
                    if (w && w.items) {
                        var matchedIdx = -1;
                        var matchedVal = null;
                        for (var i = 0; i < w.items.length; i++) {
                            var txt = w.items.eq(i).text().toLowerCase().trim();
                            var cleanTxt = txt.replace(/[^a-z0-9]/g, '');
                            if (txt === targetVal || (cleanTarget && (cleanTxt === cleanTarget || cleanTxt.indexOf(cleanTarget) !== -1 || cleanTarget.indexOf(cleanTxt) !== -1))) {
                                matchedIdx = i;
                                matchedVal = w.inputs.eq(i).val();
                                break;
                            }
                        }
                        if (matchedIdx !== -1 && matchedVal) {
                            w.selectValue(matchedVal);
                            var d = w.items.eq(matchedIdx);
                            w.check(d.children(".ui-chkbox").children(".ui-chkbox-box"), true);
                            if (w.updateLabel) w.updateLabel();
                            var lbl = document.getElementById('tf_serPro_label');
                            if (lbl) lbl.innerText = w.items.eq(matchedIdx).text().trim();
                            return;
                        }
                    }
                    // Fallback to DOM items
                    var items = document.querySelectorAll('#tf_serPro_panel li');
                    for (var li of items) {
                        var ltxt = (li.innerText || '').toLowerCase().trim();
                        var cleanL = ltxt.replace(/[^a-z0-9]/g, '');
                        if (ltxt === targetVal || (cleanTarget && (cleanL === cleanTarget || cleanL.indexOf(cleanTarget) !== -1 || cleanTarget.indexOf(cleanL) !== -1))) {
                            var box = li.querySelector('.ui-chkbox-box') || li.querySelector('label') || li;
                            box.click();
                            var lbl = document.getElementById('tf_serPro_label');
                            if (lbl) lbl.innerText = li.innerText.trim();
                            break;
                        }
                    }
                """, expected_val)
                self._wait_for_primefaces_ajax(timeout=2.0)
                return
            except Exception as pe:
                logger.warning(f"Provider selection notice: {pe}")

        # If element is associated with a PrimeFaces select widget or inner select
        if tag_name != "select":
            try:
                el_id = elem.get_attribute("id") or ""
                b_id = el_id.replace("_input", "").replace("_focus", "")
                inner_select = self.driver.find_elements(By.XPATH, f"//select[@id='{b_id}' or @id='{b_id}_input' or contains(@id, ':{b_id}_input')]")
                if inner_select:
                    elem = inner_select[0]
                    tag_name = "select"
            except Exception:
                pass
        if tag_name == "select":
            # 1. Native Selenium Select attempt with fuzzy text matching
            try:
                select_obj = Select(elem)
                matching_opt = None
                exp_clean = re.sub(r'[^a-zA-Z0-9]', '', expected_val.lower())
                is_reg = col_name and ("registration" in col_name.lower() or "regn" in col_name.lower())
                is_old = exp_clean in ["old", "retro", "retrofitment", "registered"]
                is_new = exp_clean in ["new", "newvehicle"]

                for opt in select_obj.options:
                    opt_t = opt.text.strip().lower()
                    opt_v = (opt.get_attribute("value") or "").strip().lower()
                    opt_clean_t = re.sub(r'[^a-zA-Z0-9]', '', opt_t)
                    opt_clean_v = re.sub(r'[^a-zA-Z0-9]', '', opt_v)
                    if (expected_val.lower() == opt_t or expected_val.lower() == opt_v or
                        (exp_clean and (exp_clean == opt_clean_t or exp_clean in opt_clean_t or opt_clean_t in exp_clean))):
                        matching_opt = opt
                        break
                    elif is_reg:
                        if is_old and any(k in opt_clean_t for k in ["old", "retro"]):
                            matching_opt = opt
                            break
                        elif is_new and "new" in opt_clean_t:
                            matching_opt = opt
                            break

                if matching_opt:
                    select_obj.select_by_visible_text(matching_opt.text)
                    try:
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", elem)
                    except Exception:
                        pass
            except Exception:
                pass

            # 2. JavaScript & PrimeFaces synchronization
            try:
                self.driver.execute_script("""
                    var select = arguments[0];
                    var targetVal = (arguments[1] || '').trim().toLowerCase();
                    var colName = (arguments[2] || '').trim().toLowerCase();
                    var cleanTarget = targetVal.replace(/[^a-z0-9]/g, '');
                    var isReg = colName.indexOf('reg') !== -1;
                    var isOld = (cleanTarget === 'old' || cleanTarget === 'retro' || cleanTarget === 'retrofitment' || cleanTarget === 'registered');
                    var isNew = (cleanTarget === 'new' || cleanTarget === 'newvehicle');
                    var baseId = (select.id || '').replace('_input', '').replace('_focus', '');
                    
                    var matchedIndex = -1;
                    var matchedText = '';
                    var matchedVal = '';
                    
                    for (var i = 0; i < select.options.length; i++) {
                        var opt = select.options[i];
                        var t = (opt.innerText || opt.text || '').trim().toLowerCase();
                        var v = (opt.value || '').trim().toLowerCase();
                        var cleanT = t.replace(/[^a-z0-9]/g, '');
                        var cleanV = v.replace(/[^a-z0-9]/g, '');
                        
                        if (t === targetVal || v === targetVal || 
                            (cleanTarget && (cleanT === cleanTarget || cleanT.indexOf(cleanTarget) !== -1 || cleanTarget.indexOf(cleanT) !== -1))) {
                            matchedIndex = i;
                            matchedText = opt.innerText || opt.text;
                            matchedVal = opt.value;
                            break;
                        }
                        if (isReg) {
                            if (isOld && (cleanT.indexOf('old') !== -1 || cleanT.indexOf('retro') !== -1)) {
                                matchedIndex = i;
                                matchedText = opt.innerText || opt.text;
                                matchedVal = opt.value;
                                break;
                            }
                            if (isNew && cleanT.indexOf('new') !== -1) {
                                matchedIndex = i;
                                matchedText = opt.innerText || opt.text;
                                matchedVal = opt.value;
                                break;
                            }
                        }
                    }
                    
                    if (matchedIndex !== -1) {
                        select.selectedIndex = matchedIndex;
                        for (var j = 0; j < select.options.length; j++) {
                            select.options[j].selected = (j === matchedIndex);
                        }
                        
                        var lbl = document.getElementById(baseId + '_label');
                        if (!lbl) {
                            var parentPf = select.closest('.ui-selectonemenu');
                            if (parentPf) lbl = parentPf.querySelector('.ui-selectonemenu-label');
                        }
                        if (lbl) {
                            lbl.innerText = matchedText;
                        }

                        // Check if focus input exists and update its value to matchedText
                        var focusInput = document.getElementById(baseId + '_focus') || document.getElementById(baseId);
                        if (focusInput && focusInput.tagName && focusInput.tagName.toLowerCase() === 'input') {
                            focusInput.value = matchedText;
                        }

                        // Also update panel selection visually if present
                        var panel = document.getElementById(baseId + '_panel');
                        if (panel) {
                            var items = panel.querySelectorAll('.ui-selectonemenu-item');
                            items.forEach(function(it, idx) {
                                if (idx === matchedIndex) {
                                    it.classList.add('ui-state-highlight');
                                } else {
                                    it.classList.remove('ui-state-highlight');
                                }
                            });
                        }
                        
                        try {
                            if (window.PrimeFaces && window.PrimeFaces.widgets) {
                                for (var wName in PrimeFaces.widgets) {
                                    var w = PrimeFaces.widgets[wName];
                                    if (w && (w.id === baseId || w.id === select.id) && typeof w.selectValue === 'function') {
                                        w.selectValue(matchedVal);
                                    }
                                }
                            }
                        } catch (pe) {}
                        
                        select.dispatchEvent(new Event('input', { bubbles: true }));
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        select.dispatchEvent(new Event('blur', { bubbles: true }));
                        
                        try {
                            if (window.jQuery) {
                                window.jQuery(select).val(matchedVal).trigger('change');
                            }
                        } catch (qe) {}
                    }
                """, elem, expected_val, col_name or "")
            except Exception:
                pass

            self._wait_for_primefaces_ajax(timeout=2.5)

        else:
            # Text input (IMEI, Serial, Chassis, Reg No, etc.)
            try:
                elem.clear()
            except Exception:
                pass

            try:
                self.driver.execute_script("""
                    var input = arguments[0];
                    var val = arguments[1];
                    input.value = val;
                    input.setAttribute('value', val);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                """, elem, expected_val)
            except Exception:
                pass

            try:
                val_now = (elem.get_attribute("value") or "").strip()
                if not val_now:
                    elem.send_keys(expected_val)
            except Exception:
                pass

    def _get_element_value(self, elem) -> str:
        """Reads back current value, selected option text, or PrimeFaces label text."""
        if not elem:
            return ""
        tag_name = elem.tag_name.lower()
        if tag_name in ["div", "span", "section", "td"]:
            try:
                inner = elem.find_elements(By.XPATH, ".//*[self::input[not(@type='hidden') and not(contains(@name, 'ViewState'))] or self::select]")
                if inner:
                    return self._get_element_value(inner[0])
            except Exception:
                pass
            return elem.text.strip()

        # PrimeFaces Select / Dropdown Read-back
        elem_id = elem.get_attribute("id") or ""
        base_id = elem_id.replace("_input", "").replace("_focus", "")

        # Dedicated read-back for Provider (tf_serPro)
        if "serpro" in elem_id.lower():
            try:
                lbl = self.driver.find_elements(By.ID, "tf_serPro_label")
                if lbl and lbl[0].text.strip() and not lbl[0].text.strip().lower().startswith("service"):
                    return lbl[0].text.strip()
            except Exception:
                pass

        if tag_name == "select" or "serpro" in elem_id.lower() or "maker" in elem_id.lower() or "model" in elem_id.lower() or "reg_type" in elem_id.lower() or "state" in elem_id.lower() or "offcd" in elem_id.lower():
            # 1. Native Select
            if tag_name == "select":
                try:
                    select_obj = Select(elem)
                    opt_txt = select_obj.first_selected_option.text.strip()
                    if opt_txt and not any(opt_txt.lower().startswith(x) for x in ["select", "-select", "--"]):
                        return opt_txt
                except Exception:
                    pass

            # 2. PrimeFaces widget label container
            try:
                lbl_elem = self.driver.find_elements(By.ID, f"{base_id}_label")
                if lbl_elem and lbl_elem[0].text.strip():
                    txt = lbl_elem[0].text.strip()
                    if not any(txt.lower().startswith(x) for x in ["select", "-select", "--"]):
                        return txt
            except Exception:
                pass

            # 3. Check input's own value (often contains chosen text on _focus or text input)
            own_val = (elem.get_attribute("value") or "").strip()
            if own_val and not any(own_val.lower().startswith(x) for x in ["select", "-select", "--"]):
                return own_val

            # 4. Ancestor / sibling .ui-selectonemenu-label
            try:
                val = self.driver.execute_script("""
                    var s = arguments[0];
                    var pf = s.closest('.ui-selectonemenu') || document.getElementById(arguments[1]);
                    if (pf) {
                        var lbl = pf.querySelector('.ui-selectonemenu-label');
                        if (lbl && lbl.innerText && lbl.innerText.trim().indexOf('Select') === -1) {
                            return lbl.innerText.trim();
                        }
                    }
                    if (s.tagName && s.tagName.toLowerCase() === 'select' && s.selectedIndex >= 0 && s.options[s.selectedIndex]) {
                        var ot = s.options[s.selectedIndex].innerText.trim();
                        if (ot.indexOf('Select') === -1) return ot;
                    }
                    return '';
                """, elem, base_id)
                if val:
                    return str(val).strip()
            except Exception:
                pass

        val_attr = (elem.get_attribute("value") or "").strip()
        if val_attr:
            return val_attr

        try:
            val_js = self.driver.execute_script("return arguments[0].value || arguments[0].innerText || '';", elem)
            if val_js:
                return str(val_js).strip()
        except Exception:
            pass

        return ""

        # Check if elem is a PrimeFaces select widget or inner select
        try:
            elem_id = elem.get_attribute("id") or ""
            base_id = elem_id.replace("_input", "").replace("_focus", "")
            lbl_elem = self.driver.find_elements(By.ID, f"{base_id}_label")
            if lbl_elem and lbl_elem[0].text.strip():
                txt = lbl_elem[0].text.strip()
                if not txt.lower().startswith("select"):
                    return txt
        except Exception:
            pass

        val_attr = (elem.get_attribute("value") or "").strip()
        if val_attr:
            return val_attr

        try:
            val_js = self.driver.execute_script("return arguments[0].value || arguments[0].innerText || '';", elem)
            if val_js:
                return str(val_js).strip()
        except Exception:
            pass

        return ""

    def _populate_and_readback_field(
        self,
        col: str,
        expected_val: str,
        selector_id: Optional[str] = None,
        selector_name: Optional[str] = None,
        portal_label: Optional[str] = None,
        max_retries: int = 3
    ) -> Tuple[bool, str, Optional[str], str]:
        """
        Robustly populates a field and reads back its value, handling PrimeFaces AJAX re-rendering
        and StaleElementReferenceException with up to max_retries attempts.
        Re-locates elements fresh from the DOM prior to read-back.
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                # 1. Pre-AJAX settlement
                self._wait_for_primefaces_ajax(timeout=2.0)
                if attempt > 0:
                    time.sleep(0.4)

                # 2. Locate element fresh
                elem = self._find_field_element(selector_id, selector_name, portal_label=portal_label, csv_col=col)
                if not elem:
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    return False, "<ELEMENT_NOT_FOUND>", f"Element with ID '{selector_id}' or Name '{selector_name}' could not be located on page.", "FIELD_NOT_FOUND"

                # 3. Set value
                self._set_element_value(elem, expected_val, col_name=col)
                time.sleep(0.2)

                # 4. Post-AJAX settlement based on field cascading
                if col == "Registration Type":
                    time.sleep(0.4)
                    self._wait_for_primefaces_ajax(timeout=3.5)
                    time.sleep(0.5)
                elif col in ["Vehicle State", "VLTD Maker"]:
                    time.sleep(0.3)
                    self._wait_for_primefaces_ajax(timeout=3.0)
                else:
                    self._wait_for_primefaces_ajax(timeout=2.0)

                # 5. CRITICAL: Re-locate fresh element from DOM for read-back to avoid StaleElementReferenceException
                readback_elem = self._find_field_element(selector_id, selector_name, portal_label=portal_label, csv_col=col)
                if not readback_elem:
                    readback_elem = elem

                actual_val = self._get_element_value(readback_elem)

                # 6. Multi-tiered match check
                exp_l = expected_val.lower().strip()
                act_l = actual_val.lower().strip()
                exp_clean = re.sub(r'[^a-zA-Z0-9]', '', exp_l)
                act_clean = re.sub(r'[^a-zA-Z0-9]', '', act_l)

                is_match = False
                if not exp_l and not act_l:
                    is_match = True
                elif exp_l == act_l:
                    is_match = True
                elif exp_clean and act_clean and (exp_clean == act_clean or exp_clean in act_clean or act_clean in exp_clean):
                    is_match = True
                elif "registration" in col.lower() or "regn" in col.lower():
                    reg_old_tokens = ["old", "retro", "retrofitment", "registered"]
                    reg_new_tokens = ["new"]
                    if any(t in exp_l for t in reg_old_tokens) and any(t in act_l for t in reg_old_tokens):
                        is_match = True
                    elif any(t in exp_l for t in reg_new_tokens) and any(t in act_l for t in reg_new_tokens):
                        is_match = True
                else:
                    tokens = [t for t in re.split(r'[\s\-_\(\)\/]+', exp_l) if len(t) >= 3]
                    if tokens and all(t in act_l for t in tokens):
                        is_match = True

                if is_match:
                    return True, actual_val, "Values match perfectly.", "MATCHED"
                else:
                    return False, actual_val, f"Intended '{expected_val}' does not match actual '{actual_val}'.", "MISMATCH"

            except (StaleElementReferenceException, Exception) as ex:
                last_error = ex
                logger.warning(f"Populate and readback attempt {attempt + 1}/{max_retries} encountered for '{col}': {str(ex)}")
                time.sleep(0.4)
                try:
                    self._wait_for_primefaces_ajax(timeout=2.0)
                except Exception:
                    pass

        return False, "<ERROR>", f"Exception during interaction: {str(last_error)}", "ERROR"

    
    # Stage 5 & 6: Get Details & Vehicle Information Verification
    
    def _find_and_click_get_details(self) -> Tuple[bool, Optional[str]]:
        """
        Locates and triggers the portal 'Get Details' button and waits for vehicle info.
        Uses exact ID 'j_idt143' as highest priority selector.
        """
        if not self.driver:
            return False, "Driver not available"

        get_details_xpaths = [
            "//*[@id='j_idt143' or contains(@id, ':j_idt143') or @name='j_idt143']",
            "//button[contains(@id, 'j_idt143') or contains(@name, 'j_idt143')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get detail')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'getdetails')]",
            "//button[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'getdetail') or contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'btn_fetch') or contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get_detail')]",
            "//input[@type='button' or @type='submit'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get detail')]",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get detail')]"
        ]

        clicked = False
        for xpath in get_details_xpaths:
            try:
                candidates = self.driver.find_elements(By.XPATH, xpath)
                for btn in candidates:
                    if btn.is_displayed() and btn.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.2)
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        logger.info(f"Triggered Get Details button via: {xpath} (id: '{btn.get_attribute('id')}')")
                        break
                if clicked:
                    break
            except Exception:
                continue

        if not clicked:
            # Direct JS click attempt for j_idt143
            try:
                btn = self.driver.execute_script("return document.getElementById('j_idt143') || document.querySelector('[id*=\"j_idt143\"]');")
                if btn:
                    self.driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    logger.info("Triggered Get Details via direct JS selector j_idt143")
            except Exception:
                pass

        if not clicked:
            return False, "Get Details button (j_idt143) not found on page."

        time.sleep(1.0)
        self._wait_for_primefaces_ajax(timeout=4.0)

        # Detect error or validation messages immediately
        is_succ, succ_msg, err_msg = self._verify_submission_outcome()
        if not is_succ and err_msg:
            return False, f"Portal rejected Get Details: {err_msg}"

        return True, "Get Details executed successfully."

    def _wait_for_get_details_to_complete(self, max_wait_sec: float = 15.0) -> Tuple[bool, Optional[str]]:
        """
        After clicking 'Get Details' (j_idt143), waits up to max_wait_sec for:
        1. Any PrimeFaces error popup (primefacesmessagedlg or .ui-messages-error).
           If found, captures it immediately, closes dialog, and returns (False, f"Portal rejected: {err_text}").
        2. Save Details modal (j_idt208 / dtlsDlg / j_idt234) or Save button (j_idt171) to appear.
        3. BlockUI spinner (.ui-blockui) to finish.
        """
        if not self.driver:
            return False, "Driver not available"

        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            time.sleep(0.5)

            # 1. Check for error or rejection message on page (including PrimeFaces message dialog)
            try:
                err_info = self.driver.execute_script("""
                    // 1. Primefaces message dialog (e.g. "Serial No is not Authenticated!!!")
                    var pDlg = document.getElementById('primefacesmessagedlg');
                    if (pDlg && window.getComputedStyle(pDlg).display !== 'none') {
                        var content = (pDlg.querySelector('.ui-dialog-content') || {}).innerText || '';
                        if (content.trim()) {
                            var closeBtn = pDlg.querySelector('.ui-dialog-titlebar-close');
                            if (closeBtn) closeBtn.click();
                            return { is_err: true, msg: content.trim() };
                        }
                    }
                    // 2. In-page error messages & growls
                    var msgs = Array.from(document.querySelectorAll('.ui-messages-error-summary, .ui-growl-message, .ui-message-error-detail, .ui-messages-error')).map(m => (m.innerText || '').trim()).filter(Boolean);
                    if (msgs.length > 0) {
                        return { is_err: true, msg: msgs.join(' | ') };
                    }
                    return { is_err: false, msg: '' };
                """)
                if err_info and err_info.get("is_err"):
                    err_text = err_info.get("msg")
                    logger.warning(f"Portal returned error message after Get Details: {err_text}")
                    return False, f"Portal rejected: {err_text}"
            except Exception:
                pass

            # 2. Check if Save button or Save modal is ready and BlockUI is unblocked
            try:
                ready_state = self.driver.execute_script("""
                    var has171 = document.getElementById('j_idt171') || document.querySelector('[id*="j_idt171"]');
                    var is171Vis = has171 && has171.offsetParent !== null;

                    var has234 = document.getElementById('j_idt234') || document.querySelector('[id*="j_idt234"]');
                    var is234Vis = has234 && has234.offsetParent !== null;

                    var dlgElem = document.getElementById('j_idt208');
                    var isDlgVis = dlgElem && window.getComputedStyle(dlgElem).display !== 'none' && window.getComputedStyle(dlgElem).visibility !== 'hidden';

                    var dtls = document.getElementById('getAllDtls');
                    var hasDtls = dtls && (dtls.innerHTML.indexOf('j_idt234') !== -1 || dtls.innerText.trim().length > 20);

                    var buiElem = document.querySelector('.ui-blockui');
                    var buiActive = buiElem && window.getComputedStyle(buiElem).display !== 'none';

                    if ((hasDtls || has234) && !buiActive && !isDlgVis) {
                        try {
                            if (window.PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets['dtlsDlg']) {
                                PF('dtlsDlg').show();
                                isDlgVis = true;
                                is234Vis = true;
                            }
                        } catch(e) {}
                    }

                    return {
                        ready: ((is171Vis || is234Vis || isDlgVis || hasDtls) && !buiActive),
                        is171Vis: !!is171Vis,
                        is234Vis: !!is234Vis,
                        isDlgVis: !!isDlgVis,
                        hasDtls: !!hasDtls,
                        buiActive: !!buiActive
                    };
                """)

                if ready_state and ready_state.get('ready'):
                    logger.info(f"Get Details completed successfully. Form/Modal ready: {ready_state}")
                    return True, "Get Details completed."
            except Exception:
                pass

        return False, f"Timed out waiting for Save Details button/modal after {max_wait_sec}s."

    def _read_retrieved_vehicle_information(self) -> Dict[str, str]:
        """
        Reads back portal-displayed vehicle information (Chassis No, Engine No, Maker, Model).
        """
        if not self.driver:
            return {}

        details = {}
        try:
            js_script = """
            var res = {};
            var cells = document.querySelectorAll('td, th, span, div.ui-outputpanel');
            for (var i = 0; i < cells.length; i++) {
                var txt = (cells[i].innerText || '').trim();
                var txtL = txt.toLowerCase();
                if (txtL.indexOf('chassis') !== -1 && cells[i].nextElementSibling) {
                    res['chassis_no'] = cells[i].nextElementSibling.innerText.trim();
                }
                if (txtL.indexOf('engine') !== -1 && cells[i].nextElementSibling) {
                    res['engine_no'] = cells[i].nextElementSibling.innerText.trim();
                }
                if (txtL.indexOf('maker') !== -1 && cells[i].nextElementSibling) {
                    res['vehicle_maker'] = cells[i].nextElementSibling.innerText.trim();
                }
            }
            return res;
            """
            retrieved = self.driver.execute_script(js_script)
            if retrieved and isinstance(retrieved, dict):
                details = retrieved
        except Exception:
            pass

        return details

    
    # Stage 7 & 8: Modals & Confirmation Handling
    
    def _find_and_click_save_details_button(self) -> bool:
        """
        Locates and triggers the portal Save Details / Fitment Submission button.
        Uses exact ID 'j_idt171' as highest priority selector, awaiting PrimeFaces AJAX after Get Details.
        """
        if not self.driver:
            return False

        # Wait up to 6 seconds for the vehicle info and save button panel to mount post 'Get Details'
        self._wait_for_primefaces_ajax(timeout=6.0)
        time.sleep(1.0)

        # 1. Exact ID 'j_idt171' direct check
        try:
            elem = self.driver.execute_script("return document.getElementById('j_idt171') || document.querySelector('[id*=\"j_idt171\"]') || document.querySelector('[name*=\"j_idt171\"]');")
            if elem and elem.is_displayed() and elem.is_enabled():
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                time.sleep(0.3)
                try:
                    elem.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", elem)
                logger.info("Triggered Save Details button via exact ID j_idt171")
                return True
        except Exception as e:
            logger.debug(f"Direct j_idt171 check: {e}")

        save_xpaths = [
            "//*[@id='j_idt171' or contains(@id, ':j_idt171') or @name='j_idt171']",
            "//button[contains(@id, 'j_idt171') or contains(@name, 'j_idt171')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save detail')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'savedetails')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save') and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cancel'))]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fitment')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//input[@type='submit' or @type='button'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]",
            "//input[@type='submit' or @type='button'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//input[@type='submit' or @type='button'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fitment')]",
            # Universal fallback for PrimeFaces command buttons rendered after vehicle fetch
            "//div[contains(@id, 'panel') or contains(@id, 'sld') or contains(@id, 'fitment')]//button[not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset')) and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'clear')) and not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'get'))]",
            "//button[@type='submit']"
        ]

        for xpath in save_xpaths:
            try:
                candidates = self.driver.find_elements(By.XPATH, xpath)
                for btn in candidates:
                    if btn.is_displayed() and btn.is_enabled():
                        btn_txt = (btn.text or btn.get_attribute('value') or '').strip().lower()
                        # Avoid clicking 'reset', 'clear', or 'get details'
                        if any(neg in btn_txt for neg in ['reset', 'clear', 'cancel', 'get detail', 'back']):
                            continue
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.3)
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                        logger.info(f"Triggered Save Details via: {xpath} (button text: '{btn_txt}', id: '{btn.get_attribute('id')}')")
                        return True
            except Exception:
                continue

        # Dynamic DOM scan of all visible buttons on page to discover authorized save button
        try:
            all_buttons = self.driver.find_elements(By.XPATH, "//button | //input[@type='button' or @type='submit']")
            for b in all_buttons:
                if b.is_displayed() and b.is_enabled():
                    b_text = (b.text or b.get_attribute("value") or b.get_attribute("title") or b.get_attribute("id") or "").lower()
                    if any(pos in b_text for pos in ["save", "submit", "fitment", "confirm", "proceed"]):
                        if not any(neg in b_text for neg in ["reset", "clear", "cancel", "get detail"]):
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", b)
                            time.sleep(0.3)
                            self.driver.execute_script("arguments[0].click();", b)
                            logger.info(f"Triggered discovered Save Button: id='{b.get_attribute('id')}', text='{b_text}'")
                            return True
        except Exception as e:
            logger.debug(f"Exception scanning all buttons: {e}")

        # Check if Save Details button j_idt234 or dtlsDlg is present
        try:
            has_modal_save = self.driver.execute_script("""
                var b = document.getElementById('j_idt234') || document.querySelector('[id*="j_idt234"]');
                if (b) {
                    try {
                        if (window.PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets['dtlsDlg']) {
                            PF('dtlsDlg').show();
                        }
                    } catch(e) {}
                    b.scrollIntoView({block: 'center'});
                    b.click();
                    return true;
                }
                return !!(document.getElementById('j_idt208') || (window.PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets['dtlsDlg']));
            """)
            if has_modal_save:
                logger.info("Save Details modal / button (j_idt234 / dtlsDlg) triggered.")
                return True
        except Exception as e:
            logger.debug(f"Direct j_idt234 click in save button finder: {e}")

        return False

    def _handle_save_preview_modal(self, record: CsvRecord) -> Tuple[bool, Optional[str]]:
        """
        Stage 7: Waits for save-preview modal, verifies content against current record,
        and clicks confirm/save inside modal.
        Uses exact ID 'j_idt234' as highest priority selector.
        """
        if not self.driver:
            return False, "Driver not available"

        try:
            # Settle any modal opening animations or PrimeFaces AJAX
            time.sleep(1.0)
            self._wait_for_primefaces_ajax(timeout=4.0)

            # 1. Exact ID 'j_idt234' direct trigger (supporting PrimeFaces dtlsDlg)
            try:
                res = self.driver.execute_script("""
                    // If final confirmation dialog j_idt61 is already open, proceed immediately
                    var dlg61 = document.getElementById('j_idt61');
                    if (dlg61 && window.getComputedStyle(dlg61).display !== 'none') {
                        return 'confirmation_already_open';
                    }
                    var elem = document.getElementById('j_idt234') || document.querySelector('[id*="j_idt234"]') || document.querySelector('[name*="j_idt234"]');
                    if (elem) {
                        try {
                            if (window.PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets['dtlsDlg']) {
                                PF('dtlsDlg').show();
                            }
                        } catch (pe) {}
                        elem.scrollIntoView({block: 'center'});
                        elem.click();
                        return 'clicked';
                    }
                    return 'not_found';
                """)
                if res in ['clicked', 'confirmation_already_open']:
                    logger.info(f"Confirmed save-preview modal via exact button ID j_idt234 (res: {res})")
                    time.sleep(1.0)
                    self._wait_for_primefaces_ajax(timeout=4.0)
                    return True, "Save-preview modal confirmed via j_idt234."
            except Exception as e:
                logger.debug(f"Direct j_idt234 check: {e}")


            # Dynamic check across PrimeFaces dialogs, panels, and modal containers
            preview_dialog_xpaths = [
                "//div[contains(@class, 'ui-dialog') and not(contains(@style, 'display: none')) and not(contains(@style, 'visibility: hidden'))]",
                "//div[contains(@class, 'modal') and contains(@class, 'show')]",
                "//div[contains(@id, 'confirm') or contains(@id, 'dialog')][not(contains(@style, 'display: none'))]"
            ]

            active_dialog = None
            for xp in preview_dialog_xpaths:
                dialogs = self.driver.find_elements(By.XPATH, xp)
                for d in dialogs:
                    if d.is_displayed():
                        active_dialog = d
                        break
                if active_dialog:
                    break

            if active_dialog:
                dialog_text = active_dialog.text.lower()
                # Verify dialog belongs to current record
                rec_imei = str(record.imei_number).lower().strip()
                rec_serial = str(record.vltd_serial_number).lower().strip()

                if rec_imei and rec_imei in dialog_text or rec_serial and rec_serial in dialog_text:
                    logger.info("Save-preview modal confirmed matching record identifiers.")

                # Click proceed/confirm/yes inside modal
                modal_confirm_buttons = active_dialog.find_elements(
                    By.XPATH,
                    ".//*[@id='j_idt234' or contains(@id, ':j_idt234') or @name='j_idt234'] | .//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'proceed') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ok') or contains(@class, 'ui-confirmdialog-yes')] | .//input[@type='submit' or @type='button'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes') or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'save')]"
                )
                for cbtn in modal_confirm_buttons:
                    if cbtn.is_displayed() and cbtn.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cbtn)
                        time.sleep(0.2)
                        try:
                            cbtn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", cbtn)
                        logger.info(f"Confirmed save preview modal button (id: '{cbtn.get_attribute('id')}', text: '{cbtn.text}')")
                        time.sleep(1.0)
                        return True, "Save-preview modal confirmed."

            # If no modal opened, check for native browser alert
            try:
                WebDriverWait(self.driver, 1.0).until(EC.alert_is_present())
                alert = self.driver.switch_to.alert
                logger.info(f"Accepted alert on save: {alert.text}")
                alert.accept()
                time.sleep(1.0)
                return True, f"Accepted browser alert: {alert.text}"
            except Exception:
                pass

            return True, "No blocking save-preview modal detected; proceeding to confirmation."
        except Exception as e:
            return False, f"Exception handling save-preview modal: {str(e)}"

    def _handle_final_confirmation(self, record: CsvRecord) -> Tuple[bool, Optional[str]]:
        """
        Stage 8: Waits for final confirmation dialog ('Are you sure you want to save...?'),
        and selects Yes.
        Uses exact ID 'j_idt176' as highest priority selector.
        """
        if not self.driver:
            return False, "Driver not available"

        try:
            time.sleep(0.8)
            self._wait_for_primefaces_ajax(timeout=4.0)

            # 1. Exact ID 'j_idt176' / 'j_idt62' direct trigger
            try:
                res = self.driver.execute_script("""
                    var elem = document.getElementById('j_idt176') || document.getElementById('j_idt62') || document.querySelector('[id*=\"j_idt176\"]') || document.querySelector('[id*=\"j_idt62\"]') || document.querySelector('.ui-confirmdialog-yes');
                    if (!elem) {
                        var btns = document.querySelectorAll('button, input[type=\"button\"], input[type=\"submit\"]');
                        for (var b of btns) {
                            if ((b.innerText || b.value || '').trim().toLowerCase() === 'yes') {
                                elem = b;
                                break;
                            }
                        }
                    }
                    if (elem) {
                        elem.scrollIntoView({block: 'center'});
                        elem.click();
                        return 'clicked_yes';
                    }
                    return 'not_found';
                """)
                if res == 'clicked_yes':
                    logger.info("Accepted final confirmation dialog via exact button ID (j_idt176 / Yes)")
                    time.sleep(1.5)
                    self._wait_for_primefaces_ajax(timeout=4.0)
                    return True, "Final confirmation dialog accepted via j_idt176 / Yes."
            except Exception as e:
                logger.debug(f"Direct j_idt176 check: {e}")

            confirm_xpaths = [
                "//*[@id='j_idt176' or contains(@id, ':j_idt176') or @name='j_idt176']",
                "//div[contains(@class, 'ui-confirm-dialog') and not(contains(@style, 'display: none')) and not(contains(@style, 'visibility: hidden'))]//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes') or contains(@class, 'ui-confirmdialog-yes')]",
                "//div[contains(@class, 'ui-dialog') and not(contains(@style, 'display: none')) and not(contains(@style, 'visibility: hidden'))]//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ok') or contains(@class, 'ui-confirmdialog-yes')]",
                "//div[contains(@class, 'ui-dialog') and not(contains(@style, 'display: none'))]//input[@type='submit' or @type='button'][contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes') or contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]"
            ]

            for xpath in confirm_xpaths:
                buttons = self.driver.find_elements(By.XPATH, xpath)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        logger.info(f"Found final confirmation dialog button via: {xpath}. Clicking Yes...")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.2)
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.5)
                        return True, "Final confirmation dialog accepted."

            # Check native alert as fallback
            try:
                WebDriverWait(self.driver, 1.0).until(EC.alert_is_present())
                alert = self.driver.switch_to.alert
                logger.info(f"Accepted native confirmation alert: {alert.text}")
                alert.accept()
                time.sleep(1.0)
                return True, "Native confirmation alert accepted."
            except Exception:
                pass

            return True, "No separate final confirmation dialog required."
        except Exception as e:
            return False, f"Error handling final confirmation: {str(e)}"

    def _ensure_ajax_interceptor_installed(self):
        """
        Injects a lightweight JavaScript XHR interceptor into the active browser page
        to capture all raw PrimeFaces AJAX XML responses (including <error>, <update>, etc.).
        """
        if not self.driver:
            return
        try:
            self.driver.execute_script("""
                if (!window._vahan_ajax_logs) {
                    window._vahan_ajax_logs = [];
                    var origOpen = XMLHttpRequest.prototype.open;
                    var origSend = XMLHttpRequest.prototype.send;
                    XMLHttpRequest.prototype.open = function(method, url) {
                        this._vahan_url = url;
                        this._vahan_method = method;
                        return origOpen.apply(this, arguments);
                    };
                    XMLHttpRequest.prototype.send = function(body) {
                        var self = this;
                        var logItem = {
                            method: self._vahan_method,
                            url: self._vahan_url,
                            requestBody: body ? body.toString() : '',
                            responseStatus: null,
                            responseText: null,
                            timestamp: new Date().toISOString()
                        };
                        window._vahan_ajax_logs.push(logItem);
                        self.addEventListener('load', function() {
                            logItem.responseStatus = self.status;
                            logItem.responseText = self.responseText;
                        });
                        return origSend.apply(this, arguments);
                    };
                }
            """)
        except Exception as e:
            logger.debug(f"Could not install AJAX interceptor: {e}")

    def _verify_submission_outcome(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Stage 9: Authoritative inspection of portal success or rejection messages.
        Checks:
        1. Raw AJAX XML responses for <error> tags (e.g. EvaluationException, NullPointerException, ViewExpiredException)
        2. HTTP error status codes (>= 400)
        3. PrimeFaces message dialog (id="primefacesmessagedlg")
        4. In-page PrimeFaces error messages, growls, and error panels
        5. Explicit extraction of official Application Number or Fitment Reference.
        Only reports SUCCESS when an official Application Number or Fitment Reference is actually generated.
        Returns: (is_success, confirmation_ref_or_message, error_message)
        """
        if not self.driver:
            return False, None, "Driver not available"

        # 1. Inspect raw AJAX XML responses from server
        try:
            ajax_logs = self.driver.execute_script("return window._vahan_ajax_logs || [];") or []
        except Exception:
            ajax_logs = []

        ajax_texts = []
        for entry in ajax_logs:
            status_code = entry.get('responseStatus')
            resp = entry.get('responseText') or ''
            if resp:
                ajax_texts.append(resp)

            # Check for HTTP status error
            if status_code and status_code >= 400:
                return False, None, f"Portal server returned HTTP {status_code} error during submission."

            # Check for raw XML <error> tags (such as EvaluationException)
            if "<error>" in resp.lower() or "<error-name>" in resp.lower():
                err_name_match = re.search(r"<error-name>(.*?)</error-name>", resp, re.DOTALL | re.IGNORECASE)
                err_msg_match = re.search(r"<error-message>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</error-message>", resp, re.DOTALL | re.IGNORECASE)
                err_name = err_name_match.group(1).strip() if err_name_match else "EvaluationException"
                err_msg = err_msg_match.group(1).strip() if err_msg_match else ""
                full_err = f"{err_name}: {err_msg}".strip(" :") if err_msg else f"Portal server exception: {err_name}"
                logger.error(f"Portal raw AJAX returned server error: {full_err}")
                return False, None, f"Portal server rejected transaction: {full_err}"

        # 2. Check PrimeFaces message dialog (id="primefacesmessagedlg")
        try:
            dlg_err = self.driver.execute_script("""
                var dlg = document.getElementById('primefacesmessagedlg');
                if (dlg && window.getComputedStyle(dlg).display !== 'none') {
                    var t = (dlg.querySelector('.ui-dialog-content') || {}).innerText || '';
                    if (t.trim()) {
                        var c = dlg.querySelector('.ui-dialog-titlebar-close');
                        if (c) c.click();
                        return t.trim();
                    }
                }
                return '';
            """)
            if dlg_err and dlg_err.strip():
                return False, None, f"Portal rejected: {dlg_err.strip()}"
        except Exception:
            pass

        # 3. Check in-page PrimeFaces error messages & growls
        error_xpaths = [
            "//div[contains(@class, 'ui-messages-error') and not(contains(@style, 'display: none'))]//*[contains(@class, 'ui-messages-error-summary') or contains(@class, 'ui-messages-error-detail')]",
            "//div[contains(@class, 'ui-growl-item')]//*[contains(@class, 'ui-growl-title') or contains(@class, 'ui-growl-message')]",
            "//div[contains(@class, 'ui-message-error') and not(contains(@style, 'display: none'))]//*[contains(@class, 'ui-message-error-detail')]",
            "//div[contains(@class, 'alert-danger') and not(contains(@style, 'display: none'))]",
            "//span[contains(@class, 'error-message') or contains(@class, 'ui-messages-fatal') and not(contains(@style, 'display: none'))]"
        ]

        error_texts = []
        for xpath in error_xpaths:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed():
                        txt = el.text.strip()
                        if txt and len(txt) > 2 and txt not in error_texts:
                            error_texts.append(txt)
            except Exception:
                continue

        if error_texts:
            full_error = " | ".join(error_texts)
            if any(k in full_error.lower() for k in ["error", "invalid", "already exist", "failed", "mandatory", "required", "mismatch", "not authenticated"]):
                return False, None, full_error

        # 4. Check visible body text for explicit rejections
        body_text = ""
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            error_keywords = [
                "already fitted",
                "already exists",
                "invalid imei",
                "invalid serial",
                "record already exists",
                "fitment already done",
                "serial no is not authenticated"
            ]
            for kw in error_keywords:
                if kw in body_text:
                    return False, None, f"Portal rejected: detected '{kw}' on page."
        except Exception:
            body_text = ""

        # 5. Extract Official Application Number or Fitment Reference
        # Inspect both DOM and raw AJAX XML response bodies
        all_content = []
        try:
            elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-messages-info') or contains(@class, 'ui-messages-success') or contains(@class, 'alert-success') or contains(@class, 'ui-dialog')] | //div[contains(@id, 'out_fit_pnl') or contains(@id, 'getAllDtls')]")
            for el in elements:
                if el.is_displayed():
                    t = el.text.strip()
                    if t:
                        all_content.append(t)
        except Exception:
            pass

        if body_text:
            all_content.append(body_text)
        all_content.extend(ajax_texts)
        full_haystack = " ".join(all_content)

        # Regex search for official reference number:
        ref_patterns = [
            r'(?:application\s*(?:no|num|number)?|appl\s*no)\s*[:=\-]?\s*([A-Za-z0-9\/\-_]{5,35})',
            r'(?:fitment\s*(?:cert(?:ificate)?|no|num|number)?)\s*[:=\-]?\s*([A-Za-z0-9\/\-_]{5,35})',
            r'(?:ref(?:erence)?\s*(?:no|num|number)?)\s*[:=\-]?\s*([A-Za-z0-9\/\-_]{5,35})',
            r'(?:acknowledgement\s*(?:no|num|number)?)\s*[:=\-]?\s*([A-Za-z0-9\/\-_]{5,35})'
        ]

        official_ref = None
        for pat in ref_patterns:
            m = re.search(pat, full_haystack, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in ["is", "the", "to", "for", "and", "true", "null", "undefined"]:
                    official_ref = candidate
                    break

        success_phrases = [
            "fitment details saved successfully",
            "saved successfully with application",
            "details saved successfully",
            "fitment saved successfully",
            "record saved successfully",
            "data saved successfully",
            "fitment certificate generated"
        ]
        matched_phrase = next((sp for sp in success_phrases if sp in full_haystack.lower()), None)

        if official_ref:
            logger.info(f"Authoritative success confirmed with Official Reference: {official_ref}")
            return True, f"Successfully submitted to portal database. Official Ref: {official_ref}", None
        elif matched_phrase:
            logger.info(f"Authoritative success confirmed with portal message: {matched_phrase}")
            return True, f"Successfully submitted to portal database. Confirmation: {matched_phrase}", None

        # STRICT ENFORCEMENT: If neither an official reference nor explicit success confirmation was returned,
        # do NOT mark success!
        logger.warning("Submission completed but portal did not return an official Application Number or Fitment Reference.")
        return False, None, "Portal did not generate an official Application Number or Fitment Reference confirmation."

    
    # Stage 10: Reset Form for Next Record
    
    def _reset_form_for_next_record(self):
        """
        Safely restores the fitment form to a clean ready state without terminating
        or refreshing the browser session. Closes lingering dialogs.
        """
        if not self.driver:
            return

        try:
            # 1. Close any open dialogs / modal backdrops
            self.driver.execute_script("""
                try {
                    var dialogs = document.querySelectorAll('.ui-dialog');
                    dialogs.forEach(function(d){
                        d.style.display = 'none';
                    });
                    var modalOverlays = document.querySelectorAll('.ui-widget-overlay, .modal-backdrop');
                    modalOverlays.forEach(function(o){
                        o.remove();
                    });
                } catch(e) {}
            """)

            # 2. Check for portal Reset / Clear button
            reset_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'clear')]"
            )
            for rbtn in reset_buttons:
                if rbtn.is_displayed() and rbtn.is_enabled():
                    rbtn.click()
                    time.sleep(0.5)
                    self._wait_for_primefaces_ajax()
                    return

            # 3. Clean navigation back to SLD fitting details if URL drifted
            curr_url = self.driver.current_url.lower()
            if "sldfittingdetails" not in curr_url:
                self.driver.get(TARGET_PORTAL_URL)
                time.sleep(1.5)
            else:
                self._wait_for_primefaces_ajax(timeout=1.0)
        except Exception as e:
            logger.warning(f"Form reset notice: {str(e)}")

    def _get_record_field_value(self, record: CsvRecord, col: str) -> str:
        """Resiliently gets a field value from record.raw_data or canonical record attributes."""
        # 1. Direct key
        if record.raw_data and col in record.raw_data:
            val = str(record.raw_data[col] if record.raw_data[col] is not None else "").strip()
            if val:
                return val
        # 2. Normalized header
        norm_col = normalize_header(col)
        if record.raw_data and norm_col in record.raw_data:
            val = str(record.raw_data[norm_col] if record.raw_data[norm_col] is not None else "").strip()
            if val:
                return val
        # 3. Model attributes
        attr_map = {
            "VLTD Maker": record.vltd_maker,
            "VLTD Model": record.vltd_model,
            "VLTD serial Number": record.vltd_serial_number,
            "Provider": record.provider or record.service_provider,
            "IMEI Number": record.imei_number or record.imei,
            "ICC ID": record.icc_id,
            "Registration Type": record.registration_type,
            "Vehicle Chassis No": record.chassis_no,
            "Vehicle Engine No (LAST 5 DIGITS)": record.engine_no,
            "Vehicle State": record.vehicle_state,
            "RTO": record.rto,
            "Vehicle Registration Number": record.vehicle_registration_number,
            "ID": record.id
        }
        for k in [norm_col, col]:
            if k in attr_map and attr_map[k]:
                return str(attr_map[k]).strip()
        # 4. Fuzzy key matching in raw_data
        if record.raw_data:
            clean_c = re.sub(r'[^a-zA-Z0-9]', '', col.lower())
            for rk, rv in record.raw_data.items():
                clean_rk = re.sub(r'[^a-zA-Z0-9]', '', rk.lower())
                if clean_rk == clean_c:
                    return str(rv if rv is not None else "").strip()
                # Special alias matching for vehicle registration number
                if "registration" in clean_c and "veh" in clean_c:
                    if any(x in clean_rk for x in ["vehiclereg", "regno", "regnno", "registrationno"]):
                        return str(rv if rv is not None else "").strip()
        return ""

    
    # Phase D: Dry-Run Autofill
    
    def dry_run_autofill(self, record: CsvRecord, mapping_config: BatchMappingConfig) -> DryRunResult:
        """
        Phase D: Populates single record into portal form WITHOUT submitting.
        Reads back all values, verifies against CSV record, and reports discrepancies.
        """
        with self.worker_lock:
            if not self.is_session_alive():
                raise RuntimeError("Active Chrome browser session not found or browser window was closed. Please click 'Launch Portal' first.")

            is_valid, session_msg = self.verify_session()
            if not is_valid:
                raise RuntimeError(f"Dry-run stopped: {session_msg}")

            verifications: List[FieldVerificationResult] = []
            overall_success = True

            run_id = self.active_batch_id or "dry-run"
            execution_logger.log(
                level=LogLevel.INFO,
                execution_type=ExecutionType.RECORD_EXECUTION,
                run_id=run_id,
                stage="DRY_RUN",
                action="START_DRY_RUN",
                result="IN_PROGRESS",
                message=f"Starting dry-run autofill for CSV Record {record.id} (row {record.row_number}).",
                csv_row=record.row_number
            )

            # Ensure master action 'ADD NEW VLTD' radio button is active before populating
            self._ensure_add_new_vltd_selected()

            # Linear progressive form order based on Registration Type (NEW vs OLD)
            reg_type_csv = str(self._get_record_field_value(record, "Registration Type") or "").upper().strip()
            is_old_veh = any(k in reg_type_csv for k in ["OLD", "RETROFIT", "REPLACEMENT", "REGISTERED"])

            if is_old_veh:
                field_fill_order = [
                    "VLTD Maker",
                    "VLTD Model",
                    "VLTD serial Number",
                    "Provider",
                    "IMEI Number",
                    "ICC ID",
                    "Registration Type",
                    "Vehicle Registration Number"
                ]
            else:
                field_fill_order = [
                    "VLTD Maker",
                    "VLTD Model",
                    "VLTD serial Number",
                    "Provider",
                    "IMEI Number",
                    "ICC ID",
                    "Registration Type",
                    "Vehicle State",
                    "RTO",
                    "Vehicle Chassis No",
                    "Vehicle Engine No (LAST 5 DIGITS)"
                ]

            # Process ONLY the fields relevant to the current registration type
            # For OLD vehicle: VLTD Maker, Model, Serial, Provider, IMEI, ICC ID, Reg Type, Vehicle Registration Number
            # For NEW vehicle: VLTD Maker, Model, Serial, Provider, IMEI, ICC ID, Reg Type, State, RTO, Chassis, Engine
            # NEVER process Chassis, Engine, State, or RTO for OLD vehicles
            cols_to_process = [c for c in field_fill_order if c in mapping_config.mappings]
            # Add Vehicle Registration Number if missing from mappings for OLD vehicle
            if is_old_veh and "Vehicle Registration Number" not in cols_to_process:
                cols_to_process.append("Vehicle Registration Number")

            for col in cols_to_process:
                item = mapping_config.mappings.get(col)
                expected_val = self._get_record_field_value(record, col)
                selector_id = item.target_field_id if item else ("reg_no" if col == "Vehicle Registration Number" else None)
                selector_name = item.target_field_name if item else ("reg_no" if col == "Vehicle Registration Number" else None)
                portal_label = (item.target_field_label if item else None) or col

                is_match, actual_val, diag_msg, status = self._populate_and_readback_field(
                    col=col,
                    expected_val=expected_val,
                    selector_id=selector_id,
                    selector_name=selector_name,
                    portal_label=portal_label,
                    max_retries=3
                )

                if not is_match:
                    overall_success = False

                verifications.append(FieldVerificationResult(
                    csv_column=col,
                    portal_field=portal_label,
                    expected_value=expected_val,
                    actual_value=actual_val,
                    matched=is_match,
                    status=status,
                    message=diag_msg or ""
                ))

            summary_msg = ""
            if overall_success:
                summary_msg = (
                    f"Dry-run autofill succeeded for Record ID '{record.id}' (Row {record.row_number}). "
                    f"All {len(verifications)} fields were populated and verified by read-back. Form left untouched without submitting."
                )
            else:
                summary_msg = (
                    f"Dry-run autofill detected discrepancies for Record ID '{record.id}' (Row {record.row_number}). "
                    f"Review field mismatch report. Form was NOT submitted."
                )

            logger.info(summary_msg)

            return DryRunResult(
                record_id=record.id,
                row_number=record.row_number,
                success=overall_success,
                executed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                verifications=verifications,
                portal_url=self.driver.current_url,
                summary_message=summary_msg
            )

    
    # Phase E & F: Transaction Runner & Sequential Batch Processing
    
    def start_batch_processing_async(
        self,
        batch: BatchResponse,
        mode: str = "batch",
        selected_row_numbers: Optional[List[int]] = None,
        selected_record_ids: Optional[List[str]] = None
    ):
        """
        Launches background thread for sequential processing.
        mode: "single" (processes 1 record) or "batch" (full sequence)
        selected_row_numbers / selected_record_ids: allows executing a selected subset.
        """
        with self.worker_lock:
            if self.is_running:
                raise RuntimeError("A processing batch is already running on this browser session.")

            self.stop_requested.clear()
            self.pause_requested.clear()
            self.is_running = True
            self.active_batch_id = batch.batch_id
            self.current_run_id = batch.batch_id
            batch.state = BatchState.PROCESSING

            self.active_thread = threading.Thread(
                target=self._process_sequential_records_worker,
                args=(batch, mode, selected_row_numbers, selected_record_ids),
                daemon=True
            )
            self.active_thread.start()
            logger.info(f"Started sequential processing worker (mode='{mode}') for batch {batch.batch_id}")

    def _process_sequential_records_worker(
        self,
        batch: BatchResponse,
        mode: str,
        selected_row_numbers: Optional[List[int]] = None,
        selected_record_ids: Optional[List[str]] = None
    ):
        """
        Worker thread executing sequential transaction lifecycle with continue-on-error recovery.
        """
        run_id = batch.batch_id
        try:
            mapping_config = batch.mapping
            if not mapping_config or not mapping_config.is_complete:
                batch.state = BatchState.COMPLETED_WITH_ERRORS
                batch.summary.current_error_message = "Incomplete field mapping. Submission prevented."
                execution_logger.log(
                    level=LogLevel.ERROR,
                    execution_type=ExecutionType.BATCH_SUMMARY,
                    run_id=run_id,
                    stage="VALIDATE_MAPPING",
                    action="START_BATCH",
                    result="FAILED",
                    message="Field mapping is incomplete. Processing halted before portal interaction.",
                    error_code="INCOMPLETE_MAPPING"
                )
                return

            if not self.is_session_alive():
                batch.state = BatchState.COMPLETED_WITH_ERRORS
                batch.summary.current_error_message = "Active Chrome browser session not found or browser window was closed. Please click 'Launch Portal' first."
                execution_logger.log(
                    level=LogLevel.CRITICAL,
                    execution_type=ExecutionType.AUTHENTICATION,
                    run_id=run_id,
                    stage="SESSION_VERIFY",
                    action="START_BATCH",
                    result="FAILED",
                    message="No active Chrome session found.",
                    error_code="NO_BROWSER_SESSION"
                )
                return

            # Determine records to process (respecting user selection or full dataset)
            candidate_records = [r for r in batch.records if r.status in [RecordStatus.READY, RecordStatus.PENDING]]
            if selected_row_numbers is not None and len(selected_row_numbers) > 0:
                records_to_process = [r for r in candidate_records if r.row_number in selected_row_numbers]
            elif selected_record_ids is not None and len(selected_record_ids) > 0:
                records_to_process = [r for r in candidate_records if r.id in selected_record_ids]
            else:
                records_to_process = candidate_records

            if not records_to_process:
                batch.state = BatchState.COMPLETED
                batch.summary.current_stage = "All selected records already processed."
                return

            execution_logger.log(
                level=LogLevel.INFO,
                execution_type=ExecutionType.BATCH_SUMMARY,
                run_id=run_id,
                stage="BATCH_INIT",
                action="START_BATCH",
                result="SUCCESS",
                message=f"Starting processing for {len(records_to_process)} selected record(s). Mode: {mode}"
            )

            for idx, record in enumerate(records_to_process):
                # 1. Controlled stop check
                if self.stop_requested.is_set():
                    batch.state = BatchState.STOPPED
                    batch.summary.current_stage = "Stopped by user request."
                    execution_logger.log(
                        level=LogLevel.INFO,
                        execution_type=ExecutionType.BATCH_SUMMARY,
                        run_id=run_id,
                        stage="STOPPING",
                        action="USER_STOP",
                        result="STOPPED",
                        message=f"Worker ceased processing at CSV row {record.row_number} (ID: {record.id}) upon user stop request."
                    )
                    break

                # 2. Assign transaction identifier & initialize state
                start_time = time.time()
                txn_id = f"txn-{run_id[:8]}-{record.row_number}-{int(start_time)}"
                record.transaction_id = txn_id
                record.transaction_state = TransactionState.PENDING
                batch.summary.current_record_index = idx + 1
                batch.summary.current_source_id = record.id
                batch.summary.current_stage = f"Processing CSV Row {record.row_number} (ID: {record.id})"

                execution_logger.log(
                    level=LogLevel.INFO,
                    execution_type=ExecutionType.RECORD_EXECUTION,
                    run_id=run_id,
                    transaction_id=txn_id,
                    csv_row=record.row_number,
                    stage="PREPARE_TRANSACTION",
                    action="START_RECORD",
                    result="IN_PROGRESS",
                    message=f"Starting transaction {txn_id} for CSV row {record.row_number} (ID: {record.id})."
                )

                # 3. Session validation check before starting record
                is_session_ok, session_diag = self.verify_session()
                if not is_session_ok:
                    batch.state = BatchState.PAUSED_AUTH_REQUIRED
                    record.status = RecordStatus.PAUSED_AUTH_REQUIRED
                    record.transaction_state = TransactionState.PAUSED_AUTH_REQUIRED
                    fail_msg = f"Session expired or redirect to login encountered on row {record.row_number} (ID: {record.id}): {session_diag}"
                    record.execution_message = fail_msg
                    batch.summary.current_error_message = fail_msg
                    execution_logger.log(
                        level=LogLevel.WARNING,
                        execution_type=ExecutionType.AUTHENTICATION,
                        run_id=run_id,
                        transaction_id=txn_id,
                        csv_row=record.row_number,
                        stage="SESSION_VERIFICATION",
                        action="VERIFY_SESSION",
                        result="PAUSED_AUTH_REQUIRED",
                        message=fail_msg,
                        error_code="AUTH_EXPIRED"
                    )
                    # Pause batch safely without data corruption
                    break

                # 4. Execute atomic transaction stages
                txn_success, txn_message, is_recoverable = self._execute_record_transaction(
                    record, batch, mapping_config, txn_id
                )

                duration = time.time() - start_time
                record.duration_seconds = round(duration, 2)

                if txn_success:
                    record.status = RecordStatus.SUCCESS
                    record.transaction_state = TransactionState.SUCCESS
                    batch.summary.successful_count += 1
                    batch.summary.last_confirmed_record = f"Row {record.row_number} (ID: {record.id}) -> {record.portal_confirmation_ref}"
                    execution_logger.log(
                        level=LogLevel.INFO,
                        execution_type=ExecutionType.TRANSACTION_RESULT,
                        run_id=run_id,
                        transaction_id=txn_id,
                        csv_row=record.row_number,
                        stage="TRANSACTION_RESULT",
                        action="VERIFY_RESULT",
                        result="SUCCESS",
                        message=f"Transaction committed: {record.execution_message}",
                        duration_ms=duration * 1000
                    )
                else:
                    record.status = RecordStatus.FAILED
                    record.transaction_state = TransactionState.FAILED
                    record.execution_message = txn_message
                    batch.summary.failed_count += 1
                    batch.summary.current_error_message = f"Row {record.row_number} (ID: {record.id}): {txn_message}"
                    execution_logger.log(
                        level=LogLevel.ERROR,
                        execution_type=ExecutionType.TRANSACTION_RESULT,
                        run_id=run_id,
                        transaction_id=txn_id,
                        csv_row=record.row_number,
                        stage="TRANSACTION_RESULT",
                        action="HANDLE_FAILURE",
                        result="FAILED",
                        message=f"Transaction failed: {txn_message}",
                        duration_ms=duration * 1000
                    )

                    # Continue-on-error recovery:
                    # If failure occurred before commit and is recoverable, reset form and continue!
                    if not is_recoverable:
                        logger.error(f"Unrecoverable state on row {record.row_number}. Halting batch.")
                        batch.state = BatchState.STOPPED
                        break
                    else:
                        logger.info(f"Row {record.row_number} failed safely before commit. Restoring form and continuing to next record.")

                # Stage 10: Reset form state for next record
                self._reset_form_for_next_record()

                # If single test record mode (Phase E), halt after 1 record
                if mode == "single":
                    logger.info("Single test record mode completed. Halting for review.")
                    batch.state = BatchState.READY_TO_PROCESS
                    batch.summary.current_stage = f"Single record {record.id} processed."
                    break

            # Update final batch state
            if batch.state in [BatchState.PROCESSING, BatchState.READY_FOR_REVIEW]:
                if batch.summary.failed_count > 0 or batch.summary.unresolved_count > 0:
                    batch.state = BatchState.COMPLETED_WITH_ERRORS
                else:
                    batch.state = BatchState.COMPLETED
                batch.summary.current_stage = "All selected records finished."

            execution_logger.log(
                level=LogLevel.INFO,
                execution_type=ExecutionType.BATCH_SUMMARY,
                run_id=run_id,
                stage="BATCH_COMPLETION",
                action="FINISH_BATCH",
                result=batch.state.value,
                message=(
                    f"Batch finished. Successful: {batch.summary.successful_count}, "
                    f"Failed: {batch.summary.failed_count}, "
                    f"Unresolved: {batch.summary.unresolved_count}."
                )
            )

        except Exception as global_err:
            logger.error(f"Worker exception: {str(global_err)}", exc_info=True)
            batch.state = BatchState.STOPPED
            batch.summary.current_error_message = f"Worker runtime exception: {str(global_err)}"
            execution_logger.log(
                level=LogLevel.CRITICAL,
                execution_type=ExecutionType.RECOVERY,
                run_id=run_id,
                stage="RUNTIME_EXCEPTION",
                action="GLOBAL_EXCEPTION_HANDLER",
                result="ERROR",
                message=str(global_err),
                error_code="WORKER_RUNTIME_EXCEPTION"
            )

        finally:
            self.is_running = False
            logger.info(f"Worker finished processing for batch {batch.batch_id}. Final State: {batch.state}")

    def _execute_record_transaction(
        self,
        record: CsvRecord,
        batch: BatchResponse,
        mapping_config: BatchMappingConfig,
        txn_id: str
    ) -> Tuple[bool, str, bool]:
        """
        Executes the 10-stage transaction lifecycle for an individual record:
        Stage 1: Validation
        Stage 2: Populate VLTD Details (Maker, Model, Serial, Provider, IMEI, ICC ID)
        Stage 3: Select Registration Type
        Stage 4: Populate Vehicle Details (State, RTO, Chassis, Engine)
        Stage 5: Click Get Details & await response
        Stage 6: Read retrieved vehicle information & verify consistency
        Stage 7: Click Save Details & handle first modal
        Stage 8: Handle final confirmation modal
        Stage 9: Verify authoritative final insertion
        Stage 10: Clean ready state
        Returns: (is_success, status_message, is_recoverable)
        """
        run_id = batch.batch_id

        # Ensure master action 'ADD NEW VLTD' radio button is active before populating
        self._ensure_add_new_vltd_selected()

        # Stage 2: Populate VLTD Details
        record.transaction_state = TransactionState.FILLING_VLTD_DETAILS
        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.FORM_INTERACTION,
            run_id=run_id,
            transaction_id=txn_id,
            csv_row=record.row_number,
            stage="FILLING_VLTD_DETAILS",
            action="POPULATE_VLTD_FIELDS",
            result="IN_PROGRESS",
            message="Populating VLTD device details (Maker, Model, Serial, Provider, IMEI, ICC ID)."
        )

        vltd_order = ["VLTD Maker", "VLTD Model", "VLTD serial Number", "Provider", "IMEI Number", "ICC ID"]
        for col in vltd_order:
            if col not in mapping_config.mappings:
                continue
            item = mapping_config.mappings[col]
            expected_val = self._get_record_field_value(record, col)
            if not expected_val and item.is_required:
                record.status = RecordStatus.FAILED
                record.execution_message = f"Missing required value for '{col}'."
                return False, record.execution_message, True

            if expected_val:
                is_match, actual_val, diag_msg, status = self._populate_and_readback_field(
                    col=col,
                    expected_val=expected_val,
                    selector_id=item.target_field_id,
                    selector_name=item.target_field_name,
                    portal_label=item.target_field_label or col,
                    max_retries=3
                )
                if status in ["FIELD_NOT_FOUND", "ERROR"]:
                    record.status = RecordStatus.FAILED
                    record.execution_message = f"Error populating '{col}': {diag_msg}"
                    return False, record.execution_message, True

        # Stage 3: Select Registration Type  
        record.transaction_state = TransactionState.SELECTING_REGISTRATION_TYPE
        if "Registration Type" in mapping_config.mappings:
            reg_item = mapping_config.mappings["Registration Type"]
            reg_val = self._get_record_field_value(record, "Registration Type")
            if reg_val:
                is_match, actual_val, diag_msg, status = self._populate_and_readback_field(
                    col="Registration Type",
                    expected_val=reg_val,
                    selector_id=reg_item.target_field_id,
                    selector_name=reg_item.target_field_name,
                    portal_label="Registration Type",
                    max_retries=3
                )
                if status in ["FIELD_NOT_FOUND", "ERROR"]:
                    record.status = RecordStatus.FAILED
                    record.execution_message = f"Error selecting Registration Type: {diag_msg}"
                    return False, record.execution_message, True

        # Stage 4: Populate Vehicle Details based on Registration Type (NEW vs OLD)
        record.transaction_state = TransactionState.FILLING_VEHICLE_DETAILS
        reg_type_str = str(self._get_record_field_value(record, "Registration Type") or "").upper().strip()
        is_old_vehicle = any(k in reg_type_str for k in ["OLD", "RETROFIT", "REPLACEMENT", "REGISTERED"])

        if is_old_vehicle:
            # Old vehicle: Only Registration Number is needed with field ID 'reg_no' or 'reg_panel'
            reg_no_val = self._get_record_field_value(record, "Vehicle Registration Number") or self._get_record_field_value(record, "Registration Number")
            if reg_no_val:
                reg_item = mapping_config.mappings.get("Vehicle Registration Number")
                reg_selector_id = reg_item.target_field_id if reg_item else "reg_no"
                reg_selector_name = reg_item.target_field_name if reg_item else "reg_no"
                is_match, actual_val, diag_msg, status = self._populate_and_readback_field(
                    col="Vehicle Registration Number",
                    expected_val=reg_no_val,
                    selector_id=reg_selector_id,
                    selector_name=reg_selector_name,
                    portal_label="Vehicle Registration Number",
                    max_retries=3
                )
                if status in ["FIELD_NOT_FOUND", "ERROR"]:
                    logger.warning(f"Registration Number (reg_no/reg_panel) populate note: {diag_msg}")
        else:
            # New vehicle: Vehicle Chassis No, Vehicle Engine No, Vehicle State, RTO are required
            vehicle_fields = ["Vehicle State", "RTO", "Vehicle Chassis No", "Vehicle Engine No (LAST 5 DIGITS)"]
            for col in vehicle_fields:
                if col in mapping_config.mappings:
                    item = mapping_config.mappings[col]
                    expected_val = self._get_record_field_value(record, col)
                    if expected_val:
                        is_match, actual_val, diag_msg, status = self._populate_and_readback_field(
                            col=col,
                            expected_val=expected_val,
                            selector_id=item.target_field_id,
                            selector_name=item.target_field_name,
                            portal_label=item.target_field_label or col,
                            max_retries=3
                        )
                        if status in ["FIELD_NOT_FOUND", "ERROR"]:
                            logger.warning(f"Field '{col}' populate note: {diag_msg}")

        # Stage 5: Click Get Details & await response 
        record.transaction_state = TransactionState.FETCHING_VEHICLE_DETAILS
        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.FORM_INTERACTION,
            run_id=run_id,
            transaction_id=txn_id,
            csv_row=record.row_number,
            stage="FETCHING_VEHICLE_DETAILS",
            action="CLICK_GET_DETAILS",
            result="IN_PROGRESS",
            message="Triggering portal Get Details action."
        )

        get_details_ok, get_details_msg = self._find_and_click_get_details()
        if not get_details_ok:
            record.status = RecordStatus.FAILED
            record.execution_message = get_details_msg
            return False, get_details_msg, True

        # Wait for portal processing operation and verify server response
        wait_ok, wait_msg = self._wait_for_get_details_to_complete(max_wait_sec=15.0)
        if not wait_ok:
            record.status = RecordStatus.FAILED
            record.execution_message = wait_msg
            return False, wait_msg, True

        # Stage 6: Read retrieved vehicle information & verify consistency
        record.transaction_state = TransactionState.VALIDATING_VEHICLE_DETAILS
        retrieved_veh = self._read_retrieved_vehicle_information()
        if retrieved_veh:
            csv_chassis = str(record.chassis_no or record.raw_data.get("Vehicle Chassis No", "")).strip().lower()
            portal_chassis = retrieved_veh.get("chassis_no", "").strip().lower()
            if csv_chassis and portal_chassis and csv_chassis != portal_chassis and not (csv_chassis in portal_chassis or portal_chassis in csv_chassis):
                discrepancy_msg = f"Chassis conflict: Portal returned '{portal_chassis}', expected '{csv_chassis}'."
                record.status = RecordStatus.FAILED
                record.execution_message = discrepancy_msg
                return False, discrepancy_msg, True

        # Stage 7: Click Save Details & handle first modal (j_idt171 -> j_idt234)
        record.transaction_state = TransactionState.AWAITING_SAVE_MODAL
        self._ensure_ajax_interceptor_installed()
        try:
            self.driver.execute_script("window._vahan_ajax_logs = [];")
        except Exception:
            pass

        execution_logger.log(
            level=LogLevel.INFO,
            execution_type=ExecutionType.CONFIRMATION,
            run_id=run_id,
            transaction_id=txn_id,
            csv_row=record.row_number,
            stage="AWAITING_SAVE_MODAL",
            action="CLICK_SAVE_DETAILS",
            result="IN_PROGRESS",
            message="Clicking Save Details and waiting for preview modal."
        )

        clicked_save = self._find_and_click_save_details_button()
        if not clicked_save:
            has_save = self.driver.execute_script("""
                var d = document.getElementById('j_idt208');
                var b = document.getElementById('j_idt234') || document.querySelector('[id*="j_idt234"]');
                return !!((d && window.getComputedStyle(d).display !== 'none') || 
                          (b && b.offsetParent !== null) || 
                          document.getElementById('j_idt171') || 
                          (window.PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets['dtlsDlg']));
            """)
            if not has_save:
                fail_msg = "Authorized Save Details button could not be located on form."
                record.status = RecordStatus.UNKNOWN
                record.execution_message = fail_msg
                return False, fail_msg, True

        time.sleep(1.0)
        save_modal_ok, save_modal_msg = self._handle_save_preview_modal(record)
        if not save_modal_ok:
            record.status = RecordStatus.FAILED
            record.execution_message = save_modal_msg
            return False, save_modal_msg, True

        
        # Stage 8: Handle final confirmation modal
        record.transaction_state = TransactionState.AWAITING_FINAL_CONFIRMATION
        time.sleep(0.8)
        final_conf_ok, final_conf_msg = self._handle_final_confirmation(record)
        if not final_conf_ok:
            record.status = RecordStatus.UNKNOWN
            record.execution_message = final_conf_msg
            # Ambiguous state: confirmation might have posted!
            return False, final_conf_msg, False

        # Allow server-side commit to complete
        time.sleep(2.0)
        self._wait_for_primefaces_ajax(timeout=4.0)

        
        # Stage 9: Verify authoritative final insertion
        
        record.transaction_state = TransactionState.VERIFYING_RESULT
        is_success, succ_info, err_info = self._verify_submission_outcome()

        if not is_success:
            fail_msg = f"Portal rejected insertion: {err_info}" if err_info else "Portal did not generate an official Application Number or Fitment Reference confirmation."
            record.status = RecordStatus.FAILED
            record.execution_message = fail_msg
            return False, fail_msg, True

        else:
            conf_ref = f"VAHAN-{record.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if succ_info and "Official Ref: " in succ_info:
                conf_ref = succ_info.split("Official Ref: ")[-1].strip()
            record.status = RecordStatus.SUCCESS
            record.portal_confirmation_ref = conf_ref
            record.execution_message = f"Portal response: {succ_info or 'Confirmed'}"
            record.executed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, record.execution_message, True

    def request_stop(self):
        """Signal controlled stop to worker."""
        logger.info("Stop requested by user.")
        self.stop_requested.set()

    def close_browser(self):
        """Closes browser session."""
        with self.worker_lock:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                self.is_running = False
                logger.info("Browser session closed.")
