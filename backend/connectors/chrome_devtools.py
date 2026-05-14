"""Chrome DevTools / Selenium connector scaffold.

Provides a hardened API that uses Selenium WebDriver when available, with fallbacks.
Improvements: webdriver-manager support, explicit waits, retries, JS-click fallback, and pyautogui fallback for scroll.
"""
import time
import logging

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except Exception:
    webdriver = None
    By = None
    Keys = None
    WebDriverWait = None
    EC = None
    TimeoutException = Exception
    WebDriverException = Exception
    SELENIUM_AVAILABLE = False

# try webdriver-manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER = True
except Exception:
    ChromeDriverManager = None
    WEBDRIVER_MANAGER = False


logger = logging.getLogger(__name__)


class ChromeDevToolsConnector:
    def __init__(self, headless: bool = True, default_timeout: int = 8, retry_interval: float = 0.5):
        self.headless = headless
        self.driver = None
        self.default_timeout = default_timeout
        self.retry_interval = retry_interval

    def start_browser(self):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError('selenium not available')
        if self.driver is not None:
            return
        options = webdriver.ChromeOptions()
        if self.headless:
            # new headless mode flag for modern Chrome
            try:
                options.add_argument('--headless=new')
            except Exception:
                options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        try:
            if WEBDRIVER_MANAGER and ChromeDriverManager is not None:
                driver_path = ChromeDriverManager().install()
                self.driver = webdriver.Chrome(driver_path, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
            # small implicit wait to help find_element
            try:
                self.driver.implicitly_wait(1)
            except Exception:
                pass
        except WebDriverException as e:
            logger.exception('Failed to start Chrome WebDriver')
            raise

    def open_url(self, url: str, wait_for_load: bool = True, timeout: int = None):
        if not SELENIUM_AVAILABLE or self.driver is None:
            return False
        try:
            self.driver.get(url)
            if wait_for_load:
                to = timeout or self.default_timeout
                try:
                    WebDriverWait(self.driver, to).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete'
                    )
                except Exception:
                    # proceed even if readyState wait fails
                    logger.debug('Page readyState wait timed out')
            return True
        except Exception:
            logger.exception('open_url failed')
            return False

    def find_by_selector(self, selector: str, timeout: int = None):
        """Wait for presence of element and return it, or None."""
        if not SELENIUM_AVAILABLE or self.driver is None:
            return None
        to = timeout or self.default_timeout
        try:
            el = WebDriverWait(self.driver, to).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return el
        except TimeoutException:
            logger.debug('find_by_selector timed out for %s', selector)
            return None
        except Exception:
            logger.exception('find_by_selector error')
            return None

    def click_selector(self, selector: str, timeout: int = None):
        el = self.find_by_selector(selector, timeout=timeout)
        if not el:
            return False
        try:
            # try clickable wait
            to = timeout or self.default_timeout
            try:
                el_clickable = WebDriverWait(self.driver, to).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                el_clickable.click()
                return True
            except Exception:
                # fallback to JS click
                try:
                    self.driver.execute_script('arguments[0].click();', el)
                    return True
                except Exception:
                    logger.exception('JS click fallback failed')
                    return False
        except Exception:
            logger.exception('click_selector failed')
            return False

    def scroll(self, pixels: int = 500):
        # prefer execute_script
        if SELENIUM_AVAILABLE and self.driver is not None:
            try:
                self.driver.execute_script(f"window.scrollBy(0, {pixels});")
                return True
            except Exception:
                logger.exception('Selenium scroll failed')
        # fallback to pyautogui
        try:
            import pyautogui
            pyautogui.scroll(-pixels)
            return True
        except Exception:
            logger.debug('pyautogui scroll fallback failed')
            return False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


# Module-level connector instance
_connector = ChromeDevToolsConnector(headless=True)


def start_browser(headless: bool = True, default_timeout: int = 8):
    global _connector
    _connector.headless = headless
    _connector.default_timeout = default_timeout
    try:
        _connector.start_browser()
        return True
    except Exception:
        return False


def open_url(url: str):
    return _connector.open_url(url)


def scroll(pixels: int = 500):
    return _connector.scroll(pixels)


def click_selector(sel: str):
    return _connector.click_selector(sel)


def find_selector(sel: str):
    return _connector.find_by_selector(sel)
