"""
sandbox/primitives/browser.py — Playwright Browser Automation Primitive

Provides agent-controlled browser interactions for testing XSS, DOM-based
vulnerabilities, CSRF, and JavaScript-heavy applications inside the sandbox.
Requires: playwright (install via `playwright install chromium --with-deps`)
"""

import asyncio
import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PlaywrightBrowser:
    """
    Async Playwright wrapper that exposes targeted browser primitives to agents.
    Run only inside the sandbox container where Playwright is installed.
    """

    def __init__(self, headless: bool = True, timeout: int = 30_000):
        """
        Args:
            headless: Run browser without a visible window (always True in sandbox).
            timeout: Default page action timeout in milliseconds.
        """
        self.headless = headless
        self.timeout = timeout
        self._browser = None
        self._context = None
        self._page = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Launch the browser. Must be called before any action."""
        try:
            from playwright.async_api import async_playwright  # type: ignore
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox'],
            )
            self._context = await self._browser.new_context(
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(self.timeout)
            logger.debug("Playwright browser started.")
        except ImportError:
            raise RuntimeError(
                "playwright not installed. Run: pip install playwright && "
                "playwright install chromium --with-deps"
            )

    async def close(self) -> None:
        """Gracefully shut down the browser."""
        try:
            if self._browser:
                await self._browser.close()
            if hasattr(self, '_pw') and self._pw:
                await self._pw.stop()
        except Exception as exc:
            logger.debug(f"Browser close warning: {exc}")
        finally:
            self._browser = self._context = self._page = None

    # ── Actions ───────────────────────────────────────────────────────────────
    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL and return page metadata + full HTML."""
        resp = await self._page.goto(url, wait_until="networkidle", timeout=self.timeout)
        return {
            "url":    self._page.url,
            "status": resp.status if resp else 0,
            "title":  await self._page.title(),
            "html":   await self._page.content(),
        }

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element identified by CSS/XPath selector."""
        try:
            await self._page.click(selector, timeout=self.timeout)
            return {"success": True, "selector": selector}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill an input field with a value (for form-based injection)."""
        try:
            await self._page.fill(selector, value)
            return {"success": True, "selector": selector, "value": value}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def evaluate(self, expression: str) -> Dict[str, Any]:
        """Execute JavaScript in the page context and return the result."""
        try:
            result = await self._page.evaluate(expression)
            return {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def screenshot(self) -> Dict[str, Any]:
        """Take a full-page PNG screenshot and return it as base64."""
        try:
            png_bytes = await self._page.screenshot(full_page=True)
            return {
                "success": True,
                "screenshot_b64": base64.b64encode(png_bytes).decode(),
                "size_bytes": len(png_bytes),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def get_cookies(self) -> Dict[str, Any]:
        """Return all cookies from the current browser context."""
        cookies = await self._context.cookies()
        return {"cookies": cookies}

    async def intercept_dialog(self, action: str = "accept") -> None:
        """Auto-handle alert/confirm/prompt dialogs (useful for XSS confirmation)."""
        async def _handler(dialog):
            logger.info(f"Browser dialog [{dialog.type}]: {dialog.message!r}")
            if action == "accept":
                await dialog.accept()
            else:
                await dialog.dismiss()

        self._page.on("dialog", _handler)

    # ── Context manager ───────────────────────────────────────────────────────
    async def __aenter__(self) -> 'PlaywrightBrowser':
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


async def run_browser_action(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point called by sandbox/server.py POST /browser.

    Supported actions:
        navigate, click, fill, evaluate, screenshot, get_cookies
    """
    async with PlaywrightBrowser() as browser:
        fn = getattr(browser, action, None)
        if fn is None:
            return {"error": f"Unknown browser action: {action!r}"}
        return await fn(**args)
