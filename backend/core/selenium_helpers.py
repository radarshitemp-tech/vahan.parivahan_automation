# backend/core/selenium_helpers.py
import time
import logging
from typing import Optional, List, Dict, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

logger = logging.getLogger("SeleniumHelpers")

def wait_for_primefaces_ajax(driver, timeout: float = 3.0):
    """
    Waits for active PrimeFaces and jQuery AJAX queues to settle.
    Essential for cascading dropdowns, dynamically revealed sections, and AJAX buttons.
    """
    if not driver:
        return
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("""
                var pfDone = (!window.PrimeFaces || !PrimeFaces.ajax || !PrimeFaces.ajax.Queue || PrimeFaces.ajax.Queue.isEmpty());
                var jqDone = (!window.jQuery || jQuery.active === 0);
                return pfDone && jqDone;
            """)
        )
    except Exception:
        time.sleep(0.4)

def click_element_safely(driver, elem) -> bool:
    """
    Attempts normal selenium click, falling back to JavaScript click if intercepted.
    """
    if not driver or not elem:
        return False
    try:
        elem.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", elem)
            return True
        except Exception as e:
            logger.warning(f"Click failed: {e}")
            return False

def set_element_value(driver, elem, val: str, col_name: Optional[str] = None):
    """
    Safely inputs value into text, textarea, or input field.
    Handles readonly masking and fires 'change', 'input', and 'blur' events.
    """
    if not driver or not elem:
        return
    val_str = str(val).strip()
    try:
        tag_name = elem.tag_name.lower()
        if tag_name in ["input", "textarea"]:
            # Try clearing and typing
            try:
                elem.clear()
            except Exception:
                pass
            elem.send_keys(val_str)
            # Verify and fallback to JS if empty or mismatched
            curr = elem.get_attribute("value") or ""
            if curr != val_str:
                driver.execute_script("""
                    var el = arguments[0];
                    var val = arguments[1];
                    el.value = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                """, elem, val_str)
        else:
            driver.execute_script("arguments[0].innerText = arguments[1];", elem, val_str)
    except Exception as e:
        logger.warning(f"Error setting element value ({val_str}): {e}")

def get_element_value(driver, elem) -> str:
    """
    Reads value from input, select, or display element.
    """
    if not driver or not elem:
        return ""
    try:
        tag_name = elem.tag_name.lower()
        if tag_name == "select":
            try:
                sel = Select(elem)
                return sel.first_selected_option.text.strip()
            except Exception:
                return elem.get_attribute("value") or ""
        elif tag_name in ["input", "textarea"]:
            return (elem.get_attribute("value") or "").strip()
        else:
            return (elem.text or elem.get_attribute("innerText") or "").strip()
    except Exception:
        return ""

def select_dropdown_option(driver, select_or_label_elem, expected_val: str) -> Tuple[bool, str]:
    """
    High-resilience option selection for PrimeFaces and standard HTML select tags.
    Handles:
    - Standard <select> elements via Selenium Select class and JS fallback.
    - PrimeFaces .ui-selectonemenu wrappers and custom label/panel combinations.
    - Matches exact value, clean alphanumeric matching, and case-insensitive matching.
    """
    if not driver or not select_or_label_elem or not expected_val:
        return False, "Invalid dropdown element or expected value."

    val_str = str(expected_val).strip()
    clean_val = "".join(filter(str.isalnum, val_str)).upper()

    try:
        tag_name = select_or_label_elem.tag_name.lower()

        # Case 1: Standard <select>
        if tag_name == "select":
            try:
                sel = Select(select_or_label_elem)
                for opt in sel.options:
                    opt_text = opt.text.strip()
                    opt_val = (opt.get_attribute("value") or "").strip()
                    clean_opt = "".join(filter(str.isalnum, opt_text)).upper()
                    if opt_text == val_str or opt_val == val_str or clean_opt == clean_val or clean_val in clean_opt:
                        sel.select_by_visible_text(opt_text)
                        wait_for_primefaces_ajax(driver, timeout=2.0)
                        return True, opt_text
            except Exception as ex:
                logger.debug(f"Standard Select error: {ex}")

        # Case 2: JavaScript selection on underlying <select> (e.g. reg_input or sibling select)
        js_result = driver.execute_script("""
            var root = arguments[0];
            var searchClean = arguments[1];
            var rawSearch = arguments[2];

            // Resolve target select element
            var sel = null;
            if (root.tagName && root.tagName.toLowerCase() === 'select') {
                sel = root;
            } else {
                sel = root.querySelector('select') || 
                      (root.closest('.ui-selectonemenu') ? root.closest('.ui-selectonemenu').querySelector('select') : null) ||
                      document.getElementById('reg_input') ||
                      document.querySelector('select[id*="reg"]');
            }

            if (!sel || !sel.options) return { success: false, reason: 'NO_SELECT_FOUND' };

            var matchedIndex = -1;
            var matchedText = '';
            for (var i = 0; i < sel.options.length; i++) {
                var optText = sel.options[i].text.trim();
                var optVal = sel.options[i].value.trim();
                var cleanOpt = optText.replace(/[^A-Za-z0-9]/g, '').toUpperCase();

                if (cleanOpt === searchClean || optText === rawSearch || optVal === rawSearch || cleanOpt.indexOf(searchClean) !== -1) {
                    matchedIndex = i;
                    matchedText = optText;
                    break;
                }
            }

            if (matchedIndex >= 0) {
                sel.selectedIndex = matchedIndex;
                sel.options[matchedIndex].selected = true;

                // Update PrimeFaces visible label if present
                var label = root.id && root.id.indexOf('_label') !== -1 ? root : 
                            (root.querySelector('.ui-selectonemenu-label') || document.getElementById('reg_label') || document.querySelector('[id$="reg_label"]'));
                if (label) {
                    label.innerText = matchedText;
                }

                // Dispatch native events and PrimeFaces change handler
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));

                if (window.PrimeFaces && PrimeFaces.ab) {
                    var form = sel.closest('form');
                    var formId = form ? form.id : '';
                    try {
                        PrimeFaces.ab({s: sel.id || 'reg', e: "change", f: formId, p: sel.id || 'reg', u: "@form"});
                    } catch(e) {}
                }

                return { success: true, matched: matchedText };
            }

            return { success: false, reason: 'OPTION_NOT_FOUND', total_options: sel.options.length };
        """, select_or_label_elem, clean_val, val_str)

        if js_result and js_result.get("success"):
            wait_for_primefaces_ajax(driver, timeout=2.0)
            return True, js_result.get("matched", val_str)

        # Case 3: PrimeFaces popup panel items (e.g. #reg_panel li, .ui-selectonemenu-item)
        # Click label or trigger to open dropdown list
        click_element_safely(driver, select_or_label_elem)
        time.sleep(0.5)

        items = driver.find_elements(By.CSS_SELECTOR, ".ui-selectonemenu-panel li, .ui-selectonemenu-item, [id$='_panel'] li")
        for item in items:
            try:
                t = item.text.strip()
                c = "".join(filter(str.isalnum, t)).upper()
                if c == clean_val or val_str.lower() in t.lower():
                    click_element_safely(driver, item)
                    wait_for_primefaces_ajax(driver, timeout=2.0)
                    return True, t
            except Exception:
                continue

        return False, f"Option matching '{val_str}' was not found in dropdown."
    except Exception as e:
        return False, f"Dropdown selection exception: {str(e)}"

def wait_for_modal(driver, selector_id_or_class: str, timeout: float = 10.0) -> bool:
    """
    Waits for a modal dialog to become visible.
    """
    if not driver:
        return False
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("""
                var sel = arguments[0];
                var el = document.getElementById(sel) || document.querySelector(sel);
                if (!el) {
                    var allDlg = document.querySelectorAll('.ui-dialog, [role="dialog"]');
                    for (var i = 0; i < allDlg.length; i++) {
                        if (allDlg[i].offsetParent !== null && window.getComputedStyle(allDlg[i]).display !== 'none') {
                            return true;
                        }
                    }
                    return false;
                }
                return el.offsetParent !== null && window.getComputedStyle(el).display !== 'none';
            """, selector_id_or_class)
        )
        return True
    except Exception:
        return False

def capture_portal_messages(driver) -> List[Dict[str, str]]:
    """
    Scrapes PrimeFaces messages, growl alerts, and standard notification boxes.
    Returns list of {'type': 'INFO'|'WARN'|'ERROR', 'message': str}.
    """
    if not driver:
        return []
    try:
        result = driver.execute_script("""
            var msgs = [];
            // PrimeFaces messages
            var els = document.querySelectorAll('.ui-messages-info-detail, .ui-messages-info-summary, .ui-messages-error-detail, .ui-messages-error-summary, .ui-messages-warn-detail, .ui-growl-message, .ui-messages ul li');
            for (var i = 0; i < els.length; i++) {
                var txt = els[i].innerText.trim();
                if (!txt) continue;
                var p = els[i].closest('.ui-messages-error') || els[i].closest('.ui-growl-error') ? 'ERROR' : 
                        (els[i].closest('.ui-messages-warn') || els[i].closest('.ui-growl-warn') ? 'WARN' : 'INFO');
                msgs.push({ type: p, message: txt });
            }
            return msgs;
        """)
        return result or []
    except Exception:
        return []

def find_field_element(driver, selector_id: Optional[str], selector_name: Optional[str] = None, portal_label: Optional[str] = None, csv_col: Optional[str] = None):
    """
    Multi-tier element finder suited for PrimeFaces JSF layouts.
    """
    if not driver:
        return None
    strategies = []
    if selector_id:
        strategies.append((By.ID, selector_id))
        strategies.append((By.ID, f"{selector_id}_input"))
        strategies.append((By.CSS_SELECTOR, f"[id$='{selector_id}']"))
        strategies.append((By.CSS_SELECTOR, f"[id$='{selector_id}_input']"))
    if selector_name:
        strategies.append((By.NAME, selector_name))
        strategies.append((By.CSS_SELECTOR, f"[name$='{selector_name}']"))

    for by, selector in strategies:
        try:
            elem = driver.find_element(by, selector)
            if elem and elem.is_displayed():
                return elem
        except Exception:
            continue

    return None

