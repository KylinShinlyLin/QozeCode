import asyncio
import os
from typing import Optional

from langchain_core.tools import tool
from playwright.async_api import async_playwright, BrowserContext, Page
import html2text


# Global state to maintain browser session
class BrowserSession:
    def __init__(self):
        self.playwright = None
        # In persistent context mode, browser and context are essentially the same object wrapper
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._lock = asyncio.Lock()

    async def ensure_active(self):
        """Ensure browser context and page are active using persistent context for anti-detection."""
        async with self._lock:
            if not self.playwright:
                self.playwright = await async_playwright().start()

            if not self.context:
                # Use persistent context to save cookies/session and avoid detection
                user_data_dir = os.path.expanduser("~/.qoze/browser_data")
                if not os.path.exists(user_data_dir):
                    os.makedirs(user_data_dir, exist_ok=True)

                # Launch options for anti-detection
                args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-setuid-sandbox",
                ]

                # Launch persistent context
                # Note: 'channel="chrome"' uses installed Chrome if available, otherwise defaults to bundled Chromium
                # We stick to default Chromium for stability but with stealth args
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,  # Set to False if you need to see the browser locally
                    args=args,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    ignore_default_args=["--enable-automation"]
                    # Hide "Chrome is being controlled by automated test software"
                )

                # Inject stealth scripts to all pages
                await self.context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

            if not self.page:
                pages = self.context.pages
                if pages:
                    self.page = pages[0]
                else:
                    self.page = await self.context.new_page()

    async def close(self):
        """Close all browser resources."""
        async with self._lock:
            if self.page:
                # No need to close page individually if closing context
                self.page = None
            if self.context:
                await self.context.close()
                self.context = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None


# Global instance
_session = BrowserSession()


@tool
async def browser_navigate(url: str) -> str:
    """Navigate the browser to a specific URL.
    
    Args:
        url: The URL to navigate to (must include http:// or https://).
    
    Returns:
        A message indicating success or failure, and the page title.
    """
    try:
        await _session.ensure_active()
        if not _session.page:
            return "Error: Could not initialize browser page."

        # Add random delay to simulate human behavior
        import random
        await asyncio.sleep(random.uniform(0.5, 1.5))

        await _session.page.goto(url, wait_until="domcontentloaded")
        title = await _session.page.title()
        return f"Successfully navigated to: {url}\nPage Title: {title}"
    except Exception as e:
        return f"Error navigating to {url}: {str(e)}"


@tool
async def browser_click(selector: str) -> str:
    """Click an element on the current page identified by a CSS selector.
    
    Args:
        selector: The CSS selector for the element to click (e.g., 'button.submit', '#login-btn').
    
    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Wait for element to be visible
        await _session.page.wait_for_selector(selector, state="visible", timeout=5000)

        # Human-like delay
        import random
        await asyncio.sleep(random.uniform(0.2, 0.7))

        await _session.page.click(selector)
        return f"Clicked element: {selector}"
    except Exception as e:
        return f"Error clicking {selector}: {str(e)}"


@tool
async def browser_type(selector: str, text: str) -> str:
    """Type text into an input field identified by a CSS selector.
    
    Args:
        selector: The CSS selector for the input field.
        text: The text to type.
    
    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        await _session.page.wait_for_selector(selector, state="visible", timeout=5000)

        # Type with random delay between keystrokes to simulate human
        await _session.page.type(selector, text, delay=50)
        return f"Typed text into {selector}"
    except Exception as e:
        return f"Error typing into {selector}: {str(e)}"


@tool
async def browser_read_page() -> str:
    """Extract the text content of the current page as Markdown.
    
    Returns:
        The page content converted to Markdown format.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        html_content = await _session.page.content()

        # Convert HTML to Markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # No wrapping
        markdown_content = h.handle(html_content)

        # Limit content size if too large (optional, but good for LLM context)
        if len(markdown_content) > 20000:
            markdown_content = markdown_content[:20000] + "\n\n[Content truncated...]"

        return markdown_content
    except Exception as e:
        return f"Error reading page: {str(e)}"


@tool
async def browser_screenshot() -> str:
    """Take a screenshot of the current page.
    
    Returns:
        The path to the saved screenshot file.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Ensure .qoze directory exists
        output_dir = ".qoze"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        filename = f"screenshot_{os.urandom(4).hex()}.png"
        path = os.path.join(output_dir, filename)

        await _session.page.screenshot(path=path)
        return f"Screenshot saved to: {path}"
    except Exception as e:
        return f"Error taking screenshot: {str(e)}"


@tool
async def browser_get_html() -> str:
    """Get the raw HTML of the current page.
    
    Returns:
        The raw HTML string.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."
        return await _session.page.content()
    except Exception as e:
        return f"Error getting HTML: {str(e)}"


@tool
async def browser_close() -> str:
    """Close the browser session and release resources.
    
    Returns:
        Status message.
    """
    try:
        await _session.close()
        return "Browser session closed."
    except Exception as e:
        return f"Error closing browser: {str(e)}"
