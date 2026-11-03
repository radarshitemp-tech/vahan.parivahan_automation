# backend/core/browser_manager.py
import os
import sys
import glob
import time
import socket
import tempfile
import threading
import logging
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logger = logging.getLogger("BrowserManager")

def create_robust_chrome_options(headless: Optional[bool] = None) -> Options:
    """
    Creates robust Chrome options supporting:
    - Visible desktop operation (when DISPLAY exists or Windows)
    - Headless operation (when HEADLESS=true or on Linux server without GUI)
    - Crash prevention flags (--no-sandbox, --disable-dev-shm-usage, --disable-gpu)
    - Anti-detection flags
    """
    options = Options()

    # Determine headless mode
    is_linux = sys.platform.startswith("linux")
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    force_headless = os.environ.get("HEADLESS", "").lower() in ("1", "true", "yes")

    if headless is True or force_headless or (is_linux and not has_display):
        logger.info("Configuring Chrome in headless mode (no GUI display detected or HEADLESS=true)")
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    # Essential stability and container/sandbox flags to prevent crash on launch
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--metrics-recording-only")

    # Eager strategy so page doesn't hang waiting for slow third-party scripts/images
    options.page_load_strategy = "eager"

    # Anti-detection parameters
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    return options

def launch_chrome_with_fallback(options: Optional[Options] = None) -> webdriver.Chrome:
    """
    Attempts to launch Chrome with the given options.
    If launch fails with session not created / instance exited (e.g. on headless servers),
    automatically attempts fallback to --headless=new.
    Sets explicit page load and script timeouts to prevent hanging.
    """
    opts = options or create_robust_chrome_options()
    drv = None
    try:
        drv = webdriver.Chrome(options=opts)
    except Exception as launch_err:
        err_str = str(launch_err)
        # Check if already headless
        arg_list = [str(a) for a in opts.arguments]
        if ("instance exited" in err_str.lower() or "session not created" in err_str.lower()) and "--headless=new" not in arg_list:
            logger.warning(f"Visible Chrome launch failed ({err_str}). Retrying with --headless=new fallback...")
            fallback_opts = create_robust_chrome_options(headless=True)
            drv = webdriver.Chrome(options=fallback_opts)
        else:
            raise

    # Configure bounded timeouts to prevent 120s ReadTimeoutError when portals hang
    if drv is not None:
        try:
            drv.set_page_load_timeout(30)
            drv.set_script_timeout(30)
        except Exception:
            pass

    return drv

def is_devtools_port_active(port: int) -> bool:
    """
    Verifies that the given port is an actively responding Chrome DevTools WebSocket / HTTP endpoint.
    Prevents ChromeDriver from hanging for 120s if the port is stale, dead, or non-Chrome.
    """
    import urllib.request
    import json
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "webSocketDebuggerUrl" in data or "Browser" in data
    except Exception:
        return False

def safe_driver_get(driver: webdriver.Chrome, url: str, timeout: int = 30) -> Tuple[bool, str]:
    """
    Safely navigates driver to URL with explicit timeout handling.
    Prevents ChromeDriver from hanging indefinitely if a firewall blocks/drops packets.
    """
    try:
        driver.set_page_load_timeout(timeout)
    except Exception:
        pass

    try:
        driver.get(url)
        return True, "Navigation successful."
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Note on driver.get({url}): {err_msg}")
        try:
            curr = driver.current_url.lower()
            if "parivahan" in curr or "vahan" in curr:
                return True, f"Landed on page ({curr}) despite subresource timeout."
        except Exception:
            pass
        return False, f"Navigation to {url} timed out: {err_msg}"

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
            # Fast verification before attempting ChromeDriver connection to prevent 120s ReadTimeoutError
            if not is_devtools_port_active(port):
                continue

            try:
                att_opts = Options()
                att_opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
                att_opts.page_load_strategy = "eager"
                d = webdriver.Chrome(options=att_opts)
                d.set_page_load_timeout(30)
                d.set_script_timeout(30)
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

                logger.info("Launching Chrome instance with stability options...")
                chrome_options = create_robust_chrome_options()
                self._driver = launch_chrome_with_fallback(chrome_options)
                logger.info("Chrome launched successfully.")

            if target_url:
                try:
                    curr_url = self._driver.current_url.lower()
                    if target_url.lower() not in curr_url:
                        logger.info(f"Navigating to {target_url}...")
                        safe_driver_get(self._driver, target_url, timeout=30)
                        time.sleep(1.5)
                except Exception as e:
                    logger.warning(f"Error checking/navigating URL: {e}")
                    safe_driver_get(self._driver, target_url, timeout=30)
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

