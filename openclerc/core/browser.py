"""
BrowserEngine -- Playwright wrapper for government portal automation.

Key features:
- Stealth mode (bot detection mitigation)
- Human-like typing and clicking
- Screenshot capture at every step
- Configurable timeouts and retries
"""
import asyncio
import logging
import os
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("openclerc")


class BrowserEngine:

    def __init__(
        self,
        session_id: Optional[str] = None,
        screenshots_dir: str = "./screenshots",
        headless: bool = False,
        timeout: int = 30000,
        window_bounds: Optional[dict] = None,
    ):
        raw_id = session_id or str(uuid.uuid4())[:8]
        self.session_id = "".join(c for c in raw_id if c.isalnum() or c in ("_", "-"))[:64]
        self.screenshots_dir = Path(screenshots_dir) / self.session_id
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.timeout = timeout
        self.window_bounds = window_bounds

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._screenshot_counter = 0
        self._started = False

    async def start(self) -> "BrowserEngine":
        """Launch browser. Returns self for chaining."""
        if self._started:
            return self

        self._playwright = await async_playwright().start()

        if self.window_bounds:
            win_w = self.window_bounds.get("width", 1280)
            win_h = self.window_bounds.get("height", 900)
            win_x = self.window_bounds.get("x", 0)
            win_y = self.window_bounds.get("y", 0)
        else:
            win_w, win_h, win_x, win_y = 1280, 900, 0, 0

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            f"--window-size={win_w},{win_h}",
            f"--window-position={win_x},{win_y}",
        ]

        import sys
        effective_headless = self.headless
        if not self.headless and sys.platform != "win32":
            if not os.environ.get("DISPLAY"):
                effective_headless = True

        self._browser = await self._playwright.chromium.launch(
            headless=effective_headless,
            args=launch_args,
        )

        self._context = await self._browser.new_context(
            viewport={"width": win_w, "height": win_h},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
        )

        # Stealth patches
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            if (!window.chrome) {
                window.chrome = {
                    runtime: {
                        onMessage: { addListener: function() {} },
                        sendMessage: function() {},
                    },
                    loadTimes: function() { return {}; },
                    csi: function() { return {}; },
                };
            }
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
                          description: 'Portable Document Format',
                          length: 1, item: () => ({type: 'application/x-google-chrome-pdf'}) },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                          description: '', length: 1, item: () => ({}) },
                        { name: 'Native Client', filename: 'internal-nacl-plugin',
                          description: '', length: 2, item: () => ({}) },
                    ];
                    plugins.refresh = () => {};
                    return plugins;
                }
            });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
        """)

        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout)

        # Auto-dismiss unexpected dialogs
        self._page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))

        self._started = True
        return self

    async def stop(self):
        """Clean up browser resources."""
        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.debug(f"Error closing browser context: {e}")
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping Playwright: {e}")
        finally:
            self._started = False
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    @property
    def is_started(self) -> bool:
        return self._started

    # --- Human-like actions ---

    async def human_type(self, selector: str, text: str, clear_first: bool = True):
        """Type text with human-like delays."""
        element = await self.page.wait_for_selector(selector, state="visible")
        if clear_first:
            await element.click(click_count=3)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            await self.page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.2))

        for char in text:
            await self.page.keyboard.type(char, delay=random.uniform(50, 150))
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    async def human_click(self, selector: str):
        """Click with human-like behavior."""
        element = await self.page.wait_for_selector(selector, state="visible")
        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            await self.page.mouse.move(x, y, steps=random.randint(5, 15))
            await asyncio.sleep(random.uniform(0.05, 0.2))
        await element.click()

    async def human_select(self, selector: str, value: str):
        """Select a dropdown option."""
        await self.page.select_option(selector, value)
        await asyncio.sleep(random.uniform(0.2, 0.5))

    async def human_delay(self, min_sec: float = 0.3, max_sec: float = 1.0):
        """Random delay between actions."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    # --- Navigation ---

    async def navigate(self, url: str, wait_until: str = "domcontentloaded"):
        """Navigate to URL and wait for page load."""
        await self.page.goto(url, wait_until=wait_until, timeout=self.timeout)
        await self.human_delay(0.5, 1.5)

    async def wait_for_url(self, url_pattern: str, timeout: int = None):
        """Wait for URL to match pattern."""
        await self.page.wait_for_url(url_pattern, timeout=timeout or self.timeout)

    async def wait_for_element(
        self, selector: str, state: str = "visible", timeout: int = None
    ):
        """Wait for element to be in specified state."""
        return await self.page.wait_for_selector(
            selector, state=state, timeout=timeout or self.timeout
        )

    # --- Screenshots ---

    async def take_screenshot(self, label: str = "") -> str:
        """Take screenshot. Returns the file path."""
        self._screenshot_counter += 1
        timestamp = datetime.now().strftime("%H%M%S")
        safe_label = "".join(
            c if c.isalnum() or c in ("_", "-") else "_" for c in (label or "step")
        )[:50]
        filename = f"{self._screenshot_counter:03d}_{timestamp}_{safe_label}.png"
        filepath = self.screenshots_dir / filename
        await self.page.screenshot(path=str(filepath), full_page=False)
        return str(filepath)

    async def get_screenshot_bytes(self) -> bytes:
        """Get screenshot as bytes."""
        return await self.page.screenshot(full_page=False)

    # --- Page inspection ---

    async def get_text(self, selector: str) -> str:
        """Get text content of element."""
        element = await self.page.wait_for_selector(selector, state="visible", timeout=5000)
        return (await element.text_content() or "").strip()

    async def get_value(self, selector: str) -> str:
        """Get input value."""
        return await self.page.input_value(selector)

    async def is_visible(self, selector: str) -> bool:
        """Check if element is visible on page."""
        try:
            element = await self.page.query_selector(selector)
            return await element.is_visible() if element else False
        except Exception:
            return False

    async def page_contains_text(self, text: str) -> bool:
        """Check if page body contains specific text (case-insensitive)."""
        content = await self.page.content()
        return text.lower() in content.lower()

    async def get_current_url(self) -> str:
        """Get current page URL."""
        return self.page.url

    # --- Error detection ---

    async def detect_session_expired(self) -> bool:
        """Check if the current page indicates a session timeout."""
        indicators = [
            "session has expired", "session timed out",
            "please log in again", "your session has ended",
            "login required",
        ]
        content = (await self.page.content()).lower()
        return any(ind in content for ind in indicators)

    async def detect_error_page(self) -> Optional[str]:
        """Check if current page is an error page."""
        indicators = [
            ("server error", "500"), ("page not found", "404"),
            ("service unavailable", "503"), ("access denied", "403"),
            ("forbidden", "403"), ("internal error", "500"),
            ("system is currently unavailable", "503"),
            ("under maintenance", "503"),
        ]
        content = (await self.page.content()).lower()
        for text, code in indicators:
            if text in content:
                return f"Portal returned {code}: {text}"
        return None

    async def detect_captcha(self) -> bool:
        """Check if a CAPTCHA is present on the page."""
        captcha_indicators = [
            "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
            "#captcha", ".g-recaptcha", "[data-sitekey]",
        ]
        for selector in captcha_indicators:
            if await self.is_visible(selector):
                return True
        return False
