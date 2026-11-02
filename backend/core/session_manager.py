# backend/core/session_manager.py
import time
import logging
from typing import Tuple, Optional
from selenium.webdriver.common.by import By
from .browser_manager import browser_manager

logger = logging.getLogger("SessionManager")

TARGET_PORTAL_URL = "https://vahan.parivahan.gov.in/vltdmaker/vahan/user/retrofitment/sldfittingDetails.xhtml"

class SessionManager:
    """
    Manages VAHAN portal authentication state, session validation,
    session expiry detection, and target navigation across all modules.
    """

    def __init__(self, browser_mgr=browser_manager):
        self.browser_mgr = browser_mgr

    def verify_session(self) -> Tuple[bool, str]:
        """
        Checks whether active browser session is alive and authenticated.
        Returns: (is_authenticated, status_message)
        """
        if not self.browser_mgr.is_session_alive():
            return False, "Browser window is not running or disconnected. Please launch the portal."

        driver = self.browser_mgr.driver
        try:
            curr_url = driver.current_url.lower()

            if "login" in curr_url or "login.xhtml" in curr_url or "sessionexpire" in curr_url:
                return False, f"Portal session at login or expired ({curr_url}). Operator authentication required."

            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "session expired" in body_text or "session timeout" in body_text or "please login again" in body_text:
                return False, "Portal indicates session timeout. Re-authentication required."

            return True, "Session active and authenticated."
        except Exception as e:
            return False, f"Error verifying portal session: {str(e)}"

    def ensure_authenticated_portal(self, target_url: str = TARGET_PORTAL_URL) -> Tuple[bool, str]:
        """
        Launches or verifies the browser on the target portal.
        Returns: (is_authenticated, message)
        """
        driver = self.browser_mgr.get_or_launch_browser(target_url=target_url)
        time.sleep(1.0)
        return self.verify_session()

    def get_session_info(self) -> dict:
        """Returns structured metadata about current browser & session."""
        is_alive = self.browser_mgr.is_session_alive()
        if not is_alive:
            return {
                "is_alive": False,
                "is_authenticated": False,
                "current_url": None,
                "title": None,
                "message": "Browser is not running."
            }

        driver = self.browser_mgr.driver
        is_auth, msg = self.verify_session()
        try:
            url = driver.current_url
            title = driver.title
        except Exception:
            url = None
            title = None

        return {
            "is_alive": True,
            "is_authenticated": is_auth,
            "current_url": url,
            "title": title,
            "message": msg
        }

session_manager = SessionManager()

