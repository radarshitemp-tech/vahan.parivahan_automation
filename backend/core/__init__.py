# backend/core/__init__.py
"""
Shared Automation Core for VAHAN VLTD Portal Automation.
Provides reusable browser lifecycle management, session tracking,
PrimeFaces synchronization, and resilient Selenium helpers.
"""
from .browser_manager import BrowserManager, browser_manager
from .session_manager import SessionManager, session_manager
from .selenium_helpers import (
    wait_for_primefaces_ajax,
    find_field_element,
    set_element_value,
    get_element_value,
    click_element_safely,
    select_dropdown_option,
    wait_for_modal,
    capture_portal_messages,
)

__all__ = [
    "BrowserManager",
    "browser_manager",
    "SessionManager",
    "session_manager",
    "wait_for_primefaces_ajax",
    "find_field_element",
    "set_element_value",
    "get_element_value",
    "click_element_safely",
    "select_dropdown_option",
    "wait_for_modal",
    "capture_portal_messages",
]

