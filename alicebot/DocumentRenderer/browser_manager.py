import asyncio
import os
import subprocess
import sys
from pyppeteer import connect
from pyppeteer.errors import NetworkError
from typing import Callable, Any
# Assuming log_func is defined elsewhere
# from your_logging_module import log_func
log_func: Callable[[Any], None]

class BrowserManager:
    """Manages the lifecycle of a browser instance launched via subprocess."""

    def __init__(self, browser_path, port=9222):
        """
        Initializes the BrowserManager.

        Args:
            browser_path (str): Path to the browser executable.
            port (int): Port for remote debugging.
        """
        if not os.path.exists(browser_path):
            raise FileNotFoundError(f"Browser executable not found at: {browser_path}")
        self.browser_path = browser_path
        self.port = port
        self.cache_dir = os.path.abspath("./.pyppeteer")
        self.browser = None
        self.browser_process = None
        self._component_name = "BrowserManager"

    async def start_browser(self):
        """Launches the browser process and connects pyppeteer."""
        if await self.check_connection():
            log_func(
                "INFO",
                self._component_name,
                f"Browser already running and connected on port {self.port}.",
            )
            return True

        # Ensure any previous process is terminated before starting a new one
        await self.close_browser()

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        args = [
            # "--headless=new", # Consider using the new headless mode if supported
            "--headless",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.cache_dir}",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-features=Translate",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--disable-sync",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--no-first-run",
            "--enable-automation",
            "--password-store=basic",
            "--use-mock-keychain",
            "--mute-audio",
            "--remote-debugging-address=0.0.0.0",
        ]

        if sys.platform.startswith("linux"):
            args.extend(["--no-sandbox", "--disable-setuid-sandbox"])
        # Add platform specific args if needed for win/darwin

        try:
            log_func(
                "INFO",
                self._component_name,
                f"Attempting to launch browser: {self.browser_path} on port {self.port}",
            )
            # Use CREATE_NO_WINDOW on Windows to hide the console window
            creationflags = 0
            if sys.platform.startswith("win"):
                creationflags = subprocess.CREATE_NO_WINDOW
            self.browser_process = subprocess.Popen(
                [self.browser_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )

            poll_result = self.browser_process.poll()
            if poll_result is not None:
                stderr_output = self.browser_process.stderr.read().decode(
                    errors="ignore"
                )
                raise RuntimeError(
                    f"Browser process terminated unexpectedly with code {poll_result}. Stderr: {stderr_output}"
                )
            return True

        except (FileNotFoundError, RuntimeError, NetworkError, Exception) as e:
            log_func(
                "ERROR",
                self._component_name,
                f"Failed to launch or connect to {self.browser_path}: {e}",
            )
            await self.close_browser()  # Ensure cleanup on failure
            return False

    async def connect(self):
        self.browser = await connect(
            browserURL=f"http://127.0.0.1:{self.port}", defaultViewport=None
        )
        log_func(
            "INFO",
            self._component_name,
            f"Successfully connected to browser on port {self.port}",
        )
        # Add a disconnect listener to clear the browser instance if connection is lost
        self.browser.on("disconnected", self._handle_disconnect)

    async def reconnect(self, attempts=3, delay=5):
        """Attempts to reconnect to the browser if disconnected."""
        for attempt in range(attempts):
            try:
                log_func(
                    "INFO",
                    self._component_name,
                    f"Attempting to reconnect to browser (attempt {attempt + 1})...",
                )
                await self.connect()
                return True
            except Exception as e:
                log_func(
                    "WARNING",
                    self._component_name,
                    f"Reconnection attempt {attempt + 1} failed: {e}",
                )
                await asyncio.sleep(delay)
        return False

    async def check_connection(self):
        return (
            self.browser is not None
            and self.browser_process
            and self.browser_process.poll() is None
            and self.browser._connection is not None
            and self.browser._connection._connected
        )

    async def close_browser(self):
        """Closes the browser and terminates the process."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.browser_process:
            log_func(
                "INFO",
                self._component_name,
                "Closing browser process and cleaning up...",
            )
            self._terminate_process()

    def _handle_disconnect(self):
        """Callback for when the browser disconnects unexpectedly."""
        log_func("WARNING", self._component_name, "Browser disconnected.")
        self.browser = (
            None  # Clear browser instance, process might still be running or dead
        )
        # Optionally try to kill the process if it's still alive
        if self.browser_process and self.browser_process.poll() is None:
            log_func(
                "INFO",
                self._component_name,
                "Attempting to terminate process after disconnect.",
            )
            self._terminate_process()  # Use internal helper

    def _terminate_process(self):
        """Helper to terminate the browser subprocess."""
        if self.browser_process and self.browser_process.poll() is None:
            log_func("INFO", self._component_name, "Terminating browser process...")
            try:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=5)
                log_func("INFO", self._component_name, "Browser process terminated.")
            except subprocess.TimeoutExpired:
                log_func(
                    "WARNING",
                    self._component_name,
                    "Browser process did not terminate gracefully, killing.",
                )
                self.browser_process.kill()
            except Exception as term_ex:
                log_func(
                    "ERROR",
                    self._component_name,
                    f"Error during browser process termination: {term_ex}",
                )
            finally:
                self.browser_process = None  # Ensure it's cleared even if wait fails

    async def get_browser(self, auto_reconnect=True):
        """
        Gets the browser instance after ensuring the connection is active.

        Returns:
            pyppeteer.browser.Browser or None: The browser instance if connected, otherwise None.
        """
        if await self.check_connection():
            return self.browser
        else:
            log_func(
                "WARNING",
                self._component_name,
                "Browser not connected, attempting to reconnect...",
            )
            if auto_reconnect:
                if await self.reconnect():
                    return self.browser
                else:
                    log_func(
                        "ERROR",
                        self._component_name,
                        "Failed to reconnect to browser.",
                    )
                    return None
            else:
                log_func(
                    "ERROR",
                    self._component_name,
                    "Auto-reconnect is disabled, cannot get browser instance.",
                )
                return None
