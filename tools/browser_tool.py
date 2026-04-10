import asyncio
import os
from typing import Optional

from langchain_core.tools import tool
from playwright.async_api import async_playwright, BrowserContext, Page


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

                # Enhanced stealth args to evade detection
                args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-zygote",
                ]

                # Launch persistent context
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=args,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", 
                    viewport=None,
                    java_script_enabled=True,
                )

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
                self.page = None
            if self.context:
                await self.context.close()
                self.context = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None


# Global instance
_session = BrowserSession()


def _html_to_markdown(html_content: str) -> str:
    """将 HTML 转换为 Markdown（懒加载 html2text）"""
    # 延迟导入 html2text
    import html2text
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0  # No wrapping
    return h.handle(html_content)


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
        await asyncio.sleep(random.uniform(1.0, 3.0))

        # Randomize mouse movement to simulate human (basic)
        try:
             await _session.page.mouse.move(random.randint(0, 500), random.randint(0, 500))
        except:
             pass

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

        # Human-like delay and movement
        import random
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Try to hover first
        try:
            await _session.page.hover(selector)
            await asyncio.sleep(random.uniform(0.2, 0.5))
        except:
            pass

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
        import random
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await _session.page.click(selector)
        await _session.page.type(selector, text, delay=random.randint(50, 150))
        return f"Typed text into {selector}"
    except Exception as e:
        return f"Error typing into {selector}: {str(e)}"


@tool
async def browser_read_page() -> str:
    """Convert the current page HTML to Markdown text for easy reading.

    Returns:
        The page content converted to Markdown format.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        html_content = await _session.page.content()

        # Convert HTML to Markdown (懒加载 html2text)
        markdown_content = _html_to_markdown(html_content)

        # Limit content size if too large
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


@tool
async def browser_get_html() -> str:
    """Get the raw HTML of the current page.

    This method is primarily used to assist with page input and locating buttons/elements for clicking.
    Warning: This returns a large amount of data and consumes a significant number of tokens.

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

        # Handle single string input for backward compatibility
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


# @tool
# async def browser_close() -> str:
#     """Close the browser session and release resources.
#
#     Returns:
#         Status message.
#     """
#     try:
#         await _session.close()
#         return "Browser session closed."
#     except Exception as e:
#         return f"Error closing browser: {str(e)}"


@tool
async def browser_press_key(key: str) -> str:
    """Press a keyboard key or key combination on the current page.

    Use this to simulate keyboard actions like pressing Enter to submit a form,
    Escape to close a modal, F5 to refresh, or keyboard shortcuts like Ctrl+S.

    Args:
        key: The key to press. Common keys:
             - Single keys: "Enter", "Escape", "Tab", "Backspace", "Delete",
               "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
               "Home", "End", "PageUp", "PageDown", "F1"-"F12", "Insert"
             - Combinations: "Control+a", "Shift+Enter", "Alt+Tab", "Meta+s" (Cmd on Mac)
             - Multiple keys in sequence: "Control+a Control+c" (select all then copy)

    Returns:
        Status message indicating success or failure.

    Examples:
        - browser_press_key("Enter") - Press Enter key
        - browser_press_key("Escape") - Close modal/dialog
        - browser_press_key("F5") - Refresh page
        - browser_press_key("Control+a") - Select all content
        - browser_press_key("Shift+Enter") - New line in textarea
        - browser_press_key("Control+f") - Open find dialog
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Human-like delay before key press
        import random
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Check if it's a combination (contains +)
        if "+" in key:
            # Handle key combination like "Control+a" or "Shift+Enter"
            await _session.page.keyboard.press(key)
        else:
            # Single key press
            await _session.page.keyboard.press(key)

        # Small delay after key press
        await asyncio.sleep(random.uniform(0.1, 0.2))

        return f"Successfully pressed key: {key}"
    except Exception as e:
        return f"Error pressing key '{key}': {str(e)}"


@tool
async def browser_send_keys(selector: str, keys: str) -> str:
    """Send keyboard input to a specific element identified by CSS selector.

    This is useful for typing in input fields or sending keyboard shortcuts
    to specific elements. Unlike browser_type, this doesn't clear the field first
    and can send special keys.

    Args:
        selector: The CSS selector for the target element.
        keys: The keys to send. Can include text and special keys like "Enter", "Tab", "Escape".
              Use curly braces for special keys: "Hello{Enter}World" or "{Control}a".

    Returns:
        Status message indicating success or failure.

    Examples:
        - browser_send_keys("#search", "query{Enter}") - Type "query" and press Enter
        - browser_send_keys("#editor", "{Control}a{Delete}") - Select all and delete
        - browser_send_keys("#input", "{Tab}") - Move focus to next field
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Wait for element to be visible
        element = await _session.page.wait_for_selector(selector, state="visible", timeout=5000)
        if not element:
            return f"Error: Element not found: {selector}"

        # Focus the element
        await element.focus()

        # Human-like delay
        import random
        await asyncio.sleep(random.uniform(0.2, 0.4))

        # Send the keys
        await element.press(keys)

        # Small delay after
        await asyncio.sleep(random.uniform(0.1, 0.2))

        return f"Successfully sent keys '{keys}' to element: {selector}"
    except Exception as e:
        return f"Error sending keys to '{selector}': {str(e)}"


@tool
async def browser_hotkey(keys: list[str]) -> str:
    """Press multiple keys simultaneously (hotkey combination).

    Use this for keyboard shortcuts that require multiple keys pressed at once.

    Args:
        keys: List of keys to press simultaneously. Order matters for some shortcuts.
              Example: ["Control", "Shift", "T"] for reopening closed tab.

    Returns:
        Status message indicating success or failure.

    Examples:
        - browser_hotkey(["Control", "t"]) - Open new tab
        - browser_hotkey(["Control", "Shift", "t"]) - Reopen closed tab
        - browser_hotkey(["Control", "v"]) - Paste
        - browser_hotkey(["Alt", "Left"]) - Browser back
        - browser_hotkey(["Meta", "s"]) - Save (Cmd+S on Mac, Ctrl+S elsewhere)
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        if not keys or len(keys) < 2:
            return "Error: Hotkey requires at least 2 keys. Use browser_press_key for single keys."

        # Human-like delay
        import random
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # Press down all keys in order
        for key in keys:
            await _session.page.keyboard.down(key)

        # Release all keys in reverse order
        for key in reversed(keys):
            await _session.page.keyboard.up(key)

        # Small delay after
        await asyncio.sleep(random.uniform(0.1, 0.2))

        key_combo = "+".join(keys)
        return f"Successfully pressed hotkey: {key_combo}"
    except Exception as e:
        return f"Error pressing hotkey: {str(e)}"


@tool
async def browser_focus(selector: str) -> str:
    """Focus on a specific element without clicking it.

    Useful for preparing to type in a field or triggering focus-related events.

    Args:
        selector: The CSS selector for the element to focus.

    Returns:
        Status message indicating success or failure.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        element = await _session.page.wait_for_selector(selector, state="visible", timeout=5000)
        if not element:
            return f"Error: Element not found: {selector}"

        await element.focus()

        return f"Successfully focused element: {selector}"
    except Exception as e:
        return f"Error focusing element '{selector}': {str(e)}"
