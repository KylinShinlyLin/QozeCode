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

                # Enhanced stealth args
                args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",  # Can help with stability in headless environments
                    "--hide-scrollbars",
                    "--mute-audio",
                ]

                # Launch persistent context
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=args,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800},
                    ignore_default_args=["--enable-automation"],
                    java_script_enabled=True,
                )

                # Inject advanced stealth scripts to all pages
                stealth_script = """
                    // 1. Pass the Webdriver Test
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });

                    // 2. Mock Chrome object
                    if (!window.chrome) {
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                    }

                    // 3. Mock Permissions API
                    if (navigator.permissions) {
                        const originalQuery = navigator.permissions.query;
                        navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                        );
                    }

                    // 4. Mock Plugins
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });

                    // 5. WebGL vendor/renderer spoofing
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        // UNMASKED_VENDOR_WEBGL
                        if (parameter === 37445) {
                            return 'Intel Inc.';
                        }
                        // UNMASKED_RENDERER_WEBGL
                        if (parameter === 37446) {
                            return 'Intel(R) Iris(R) Plus Graphics 640';
                        }
                        return getParameter(parameter);
                    };
                    
                    // 6. Broken Image Handling (optional but useful)
                    ['height', 'width'].forEach(property => {
                        const imageDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, property);
                        Object.defineProperty(HTMLImageElement.prototype, property, {
                            ...imageDescriptor,
                            get: function() {
                                if (this.complete && this.naturalHeight == 0) {
                                    return 20; // Fake dimensions for broken images
                                }
                                return imageDescriptor.get.apply(this);
                            },
                        });
                    });
                """
                await self.context.add_init_script(stealth_script)

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
async def browser_scroll(direction: str = "down", amount: str = "page") -> str:
    """Scroll the current page content.

    Args:
        direction: The direction to scroll: "up" or "down". Default is "down".
        amount: The amount to scroll: "page" (full screen), "half" (half screen), "top" (to the top), "bottom" (to the bottom), or specific pixels (e.g. "500"). Default is "page".

    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        if amount == "top":
            await _session.page.evaluate("window.scrollTo(0, 0)")
            return "Scrolled to the top of the page."
        elif amount == "bottom":
            await _session.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return "Scrolled to the bottom of the page."

        # Calculate pixels
        if amount.isdigit():
            pixels = int(amount)
        else:
            # Evaluate viewport height for relative scrolling
            viewport_height = await _session.page.evaluate("window.innerHeight")
            if amount == "page":
                pixels = viewport_height
            elif amount == "half":
                pixels = viewport_height // 2
            else:
                return f"Error: Invalid amount '{amount}'"

        if direction == "up":
            pixels = -pixels
        elif direction != "down":
            return f"Error: Invalid direction '{direction}'"

        await _session.page.evaluate(f"window.scrollBy(0, {pixels})")

        # Human-like delay after scroll
        import random
        await asyncio.sleep(random.uniform(0.5, 1.0))

        return f"Scrolled {direction} by {amount}"
    except Exception as e:
        return f"Error scrolling: {str(e)}"


# @tool
# async def browser_screenshot() -> str:
#     """Take a screenshot of the current page.
#
#     Returns:
#         The path to the saved screenshot file.
#     """
#     try:
#         if not _session.page:
#             return "Error: No active page. Use browser_navigate first."
#
#         # Ensure .qoze directory exists
#         output_dir = ".qoze"
#         if not os.path.exists(output_dir):
#             os.makedirs(output_dir)
#
#         filename = f"screenshot_{os.urandom(4).hex()}.png"
#         path = os.path.join(output_dir, filename)
#
#         await _session.page.screenshot(path=path)
#         return f"Screenshot saved to: {path}"
#     except Exception as e:
#         return f"Error taking screenshot: {str(e)}"


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
async def browser_open_tab(urls: list[str]) -> str:
    """Open one or multiple browser tabs and navigate to the given URLs.

    Args:
        urls: A single URL string or a list of URL strings.

    Returns:
        Status message including the new tab indices.
    """
    try:
        await _session.ensure_active()
        if not _session.context:
            return "Error: Could not initialize browser context."

        # Handle single string input for backward compatibility or LLM flexibility
        if isinstance(urls, str):
            urls = [urls]

        results = []
        for url in urls:
            try:
                # Create new page
                new_page = await _session.context.new_page()
                _session.page = new_page

                # Navigate
                await new_page.goto(url, wait_until="domcontentloaded")
                title = await new_page.title()

                # Get index
                pages = _session.context.pages
                index = pages.index(new_page)

                results.append(f"Tab [{index}]: {title} ({url})")
            except Exception as e_inner:
                results.append(f"Error opening {url}: {str(e_inner)}")

        return "Opened tabs:\n" + "\n".join(results)
    except Exception as e:
        return f"Error opening tabs: {str(e)}"


@tool
async def browser_switch_tab(index: int) -> str:
    """Switch to a specific browser tab by index.

    Args:
        index: The index of the tab to switch to (0-based).

    Returns:
        Status message with the title of the active tab.
    """
    try:
        if not _session.context:
            return "Error: No active browser context."

        pages = _session.context.pages
        if index < 0 or index >= len(pages):
            return f"Error: Invalid tab index {index}. Total tabs: {len(pages)}"

        target_page = pages[index]
        await target_page.bring_to_front()
        _session.page = target_page

        title = await target_page.title()
        url = target_page.url
        return f"Switched to tab {index}.\nTitle: {title}\nURL: {url}"
    except Exception as e:
        return f"Error switching tab: {str(e)}"


@tool
async def browser_list_tabs() -> str:
    """List all open browser tabs.

    Returns:
        A formatted list of open tabs with their indices, titles, and URLs.
    """
    try:
        if not _session.context:
            return "Error: No active browser context."

        pages = _session.context.pages
        if not pages:
            return "No open tabs."

        result = ["Open Tabs:"]
        current_page = _session.page

        for i, page in enumerate(pages):
            try:
                title = await page.title()
                url = page.url
                prefix = "*" if page == current_page else " "
                result.append(f"{prefix} [{i}] {title} - {url}")
            except Exception:
                result.append(f"  [{i}] <Error reading page info>")

        return "\n".join(result)
    except Exception as e:
        return f"Error listing tabs: {str(e)}"


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
