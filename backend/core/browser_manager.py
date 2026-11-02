# backend/core/browser_manager.py
import os
import glob
import time
import socket
import tempfile
import threading
import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger("BrowserManager")

class BrowserManager:
    """
    Centralized Chrome WebDriver lifecycle manager.
    Supports:
    - Launching visible Chrome instances with anti-detection options.
    - Fast socket-probing and DevToolsActivePort detection to automatically attach
      to existing running debugging instances without duplicating browser windows.
    - Session liveness checks and graceful cleanup.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BrowserManager, cls).__new__(cls)
                cls._instance._driver = None
                cls._instance._manager_lock = threading.Lock()
            return cls._instance

    @property
    def driver(self) -> Optional[webdriver.Chrome]:
        return self._driver

    @driver.setter
    def driver(self, drv: Optional[webdriver.Chrome]):
        self._driver = drv

    def is_session_alive(self) -> bool:
        """
        Verifies if current driver instance exists and has an active, responsive session.
        If browser window was closed or session is invalid, cleans up dead driver.
        Automatically checks for and attaches to an existing running debug Chrome instance if disconnected.
        """
        if self._driver is not None:
            try:
                _ = self._driver.current_window_handle
                return True
            except Exception:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None

        # Dynamically discover active Chrome DevTools ports
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
                self._driver = d
                logger.info(f"Auto-attached to running Chrome on 127.0.0.1:{port}")
                return True
            except Exception:
                continue

        return False

    def get_or_launch_browser(self, target_url: Optional[str] = None) -> webdriver.Chrome:
        """
        Reuses existing active browser or launches a new visible Chrome instance.
        Navigates to target_url if specified.
        """
        with self._manager_lock:
            if not self.is_session_alive():
                if self._driver is not None:
                    try:
                        self._driver.quit()
                    except Exception:
                        pass
                    self._driver = None

                logger.info("Launching new visible Chrome instance...")
                chrome_options = Options()
                chrome_options.add_argument("--start-maximized")
                chrome_options.add_argument("--disable-notifications")
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option("useAutomationExtension", False)

                self._driver = webdriver.Chrome(options=chrome_options)
                logger.info("Chrome launched successfully.")

            if target_url:
                try:
                    curr_url = self._driver.current_url.lower()
                    if target_url.lower() not in curr_url:
                        logger.info(f"Navigating to {target_url}...")
                        self._driver.get(target_url)
                        time.sleep(1.5)
                except Exception as e:
                    logger.warning(f"Error checking/navigating URL: {e}")
                    self._driver.get(target_url)
                    time.sleep(1.5)

            return self._driver

    def close_browser(self):
        """Closes the current browser session and cleans up."""
        with self._manager_lock:
            if self._driver is not None:
                try:
                    self._driver.quit()
                    logger.info("Browser session closed.")
                except Exception as e:
                    logger.warning(f"Error during browser close: {e}")
                finally:
                    self._driver = None

browser_manager = BrowserManager()

