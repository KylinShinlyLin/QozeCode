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
        # 事件收集器
        self.console_messages: list[dict] = []
        self.network_requests: list[dict] = []
        self._collecting = False
        self._collected_pages = set()
        self._pending_requests: dict[str, dict] = {}  # url -> request dict

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
                # 启动 console 和 network 事件收集
                _start_collecting(self, self.page)

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


async def _wait_for_stable_dom(timeout: int = 3000, stable_for: int = 200):
    """等待 DOM 稳定（借鉴 Chrome DevTools MCP 的 WaitForHelper 机制）。
    
    通过 MutationObserver 检测 DOM 变化，等待一段时间没有变化后返回。
    
    Args:
        timeout: 最大等待时间 (ms)
        stable_for: 需要稳定的时间 (ms)
    """
    if not _session.page:
        return
    try:
        import asyncio as _asyncio
        await _session.page.evaluate("""
            (timeout, stableFor) => {
                return new Promise((resolve, reject) => {
                    let stableTimer;
                    let timeoutTimer;
                    
                    const onMutation = () => {
                        clearTimeout(stableTimer);
                        stableTimer = setTimeout(() => {
                            cleanup();
                            resolve();
                        }, stableFor);
                    };
                    
                    const cleanup = () => {
                        clearTimeout(stableTimer);
                        clearTimeout(timeoutTimer);
                        observer.disconnect();
                    };
                    
                    timeoutTimer = setTimeout(() => {
                        cleanup();
                        resolve();  // timeout, resolve anyway
                    }, timeout);
                    
                    // Start initial stable timer
                    stableTimer = setTimeout(() => {
                        cleanup();
                        resolve();
                    }, stableFor);
                    
                    const observer = new MutationObserver(onMutation);
                    if (document.body) {
                        observer.observe(document.body, {
                            childList: true,
                            subtree: true,
                            attributes: true
                        });
                    }
                });
            }
        """, (timeout, stable_for))
    except Exception:
        pass  # DOM stability is best-effort


# 将 _wait_for_stable_dom 添加到 BrowserSession 类中
BrowserSession._wait_for_stable_dom = staticmethod(_wait_for_stable_dom)


def _start_collecting(session, page):
    """开始收集 console 消息和网络请求事件（每个页面只启动一次）"""
    page_id = id(page)
    if page_id in session._collected_pages:
        return
    session._collected_pages.add(page_id)

    def _on_console(msg):
        session.console_messages.append({
            "id": len(session.console_messages),
            "type": msg.type,
            "text": msg.text,
            "location": str(msg.location) if msg.location else "",
        })

    def _on_page_error(err):
        session.console_messages.append({
            "id": len(session.console_messages),
            "type": "error",
            "text": str(err),
            "location": "page",
        })

    def _on_request(request):
        req_dict = {
            "id": len(session.network_requests),
            "url": request.url,
            "method": request.method,
            "resource_type": request.resource_type,
            "headers": dict(request.headers) if request.headers else {},
            "post_data": request.post_data,
            "status": None,
            "status_text": None,
            "response_headers": None,
        }
        session.network_requests.append(req_dict)
        session._pending_requests[request.url + "|" + request.method] = req_dict

    def _on_response(response):
        key = response.url + "|" + response.request.method if response.request else response.url
        req_dict = session._pending_requests.pop(key, None)
        if req_dict:
            req_dict["status"] = response.status
            req_dict["status_text"] = response.status_text
            req_dict["response_headers"] = dict(response.headers) if response.headers else {}
            try:
                # 使用 Content-Length header 获取响应体大小
                # response.body() 是协程，不能在此同步上下文中调用
                cl = response.headers.get("content-length")
                req_dict["response_body_size"] = int(cl) if cl else None
            except Exception:
                req_dict["response_body_size"] = None

    page.on("console", _on_console)
    page.on("pageerror", _on_page_error)
    page.on("request", _on_request)
    page.on("response", _on_response)


def _clear_collected_data(session):
    """清空收集的数据（导航时自动调用）"""
    session.console_messages.clear()
    session.network_requests.clear()
    session._pending_requests.clear()


# 挂载到 BrowserSession 类上
BrowserSession._start_collecting = staticmethod(_start_collecting)
BrowserSession.clear_collected_data = _clear_collected_data

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

        # 新导航时清空之前的 console 和 network 数据（必须在 goto 之前）
        _clear_collected_data(_session)
        await _session.page.goto(url, wait_until="domcontentloaded")
        title = await _session.page.title()
        return f"Successfully navigated to: {url}\nPage Title: {title}"
    except Exception as e:
        return f"Error navigating to {url}: {str(e)}"


@tool
async def browser_click(selector: str) -> str:
    """Click an element on the current page identified by a CSS selector.

    Uses Playwright's Locator API which provides built-in auto-waiting:
    waits for element to be visible, stable, enabled, and not covered by other elements.
    Also waits for DOM to stabilize after the click. Falls back to force click if needed.

    Args:
        selector: The CSS selector for the element to click (e.g., 'button.submit', '#login-btn').

    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Use Locator API which has built-in auto-waiting and retry
        locator = _session.page.locator(selector)

        # Human-like delay before click
        import random
        await asyncio.sleep(random.uniform(0.3, 0.8))

        # Try hover first for better human simulation
        try:
            await locator.hover(timeout=3000)
            await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass  # Hover is optional

        # Click using Locator API (auto-waits for actionability:
        # visible, stable, enabled, not covered)
        await locator.click(timeout=5000)

        # Wait for DOM to stabilize after click
        await _wait_for_stable_dom()

        return f"Clicked element: {selector}"
    except Exception as e:
        # Fallback: try force click (bypasses actionability checks)
        try:
            await _session.page.locator(selector).click(force=True, timeout=3000)
            await _wait_for_stable_dom()
            return f"Clicked element (force): {selector}"
        except Exception:
            pass
        return f"Error clicking {selector}: {str(e)}"


@tool
async def browser_type(selector: str, text: str) -> str:
    """Type text into an input field identified by a CSS selector.

    Uses Playwright's Locator API with fill() for reliable input.
    First clears existing content, then types with proper focus.

    Args:
        selector: The CSS selector for the input field.
        text: The text to type.

    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        locator = _session.page.locator(selector)

        # Human-like delay
        import random
        await asyncio.sleep(random.uniform(0.3, 0.6))

        # Click to focus first
        await locator.click(timeout=5000)

        # Clear and fill using Locator API
        await locator.fill(text, timeout=5000)

        await _wait_for_stable_dom()

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
                _start_collecting(_session, new_page)
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


# ============================================================
# 以下为借鉴 Chrome DevTools MCP 新增的增强工具
# ============================================================

@tool
async def browser_snapshot(verbose: bool = False) -> str:
    """Take a text snapshot of the current page based on the accessibility tree.

    Lists page elements along with unique identifiers (uid). The snapshot is MUCH
    more token-efficient than full HTML and provides structured element info.
    Each element shows: uid, role, name, and interactive attributes (focusable, disabled, etc.)

    Use this when you need to locate elements for clicking/typing but don't need full HTML.
    Prefer this over browser_get_html for element discovery.

    Args:
        verbose: Whether to include all a11y tree nodes. Default False (interesting only).

    Returns:
        Formatted accessibility tree text with uid for each element.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Get accessibility snapshot
        snapshot = await _session.page.accessibility.snapshot(
            interestingOnly=not verbose,
            includeIframes=True,
        )
        if not snapshot:
            return "Error: Could not create accessibility snapshot. Page may not be loaded."

        # Generate uid for each node and format
        uid_counter = [0]

        def format_node(node, depth=0) -> str:
            uid = f"snap_{uid_counter[0]}"
            uid_counter[0] += 1

            # Build attributes
            attrs = [f"uid={uid}"]
            role = node.get("role", "")
            if role and role != "none":
                attrs.append(role)
            elif role == "none":
                attrs.append("ignored")

            name = node.get("name", "")
            if name:
                attrs.append(f'"{name}"')

            # Boolean attributes
            for attr in ["focusable", "disabled", "selected", "checked", "expanded", "pressed", "multiselectable",
                         "required", "readonly"]:
                if node.get(attr):
                    attrs.append(attr)

            # Value attribute
            value = node.get("value")
            if isinstance(value, str) and value:
                attrs.append(f'value="{value}"')
            elif isinstance(value, (int, float)):
                attrs.append(f'value="{value}"')

            line = "  " * depth + " ".join(attrs) + "\n"

            # Process children
            for child in node.get("children", []):
                line += format_node(child, depth + 1)

            return line

        result = format_node(snapshot)

        # Limit output size
        if len(result) > 15000:
            result = result[:15000] + "\n\n... [snapshot truncated]"

        return f"Page Accessibility Snapshot:\n{result}"
    except Exception as e:
        return f"Error taking snapshot: {str(e)}"


@tool
async def browser_wait_for(text: str, timeout: int = 5000) -> str:
    """Wait for the specified text to appear on the current page.

    Useful for waiting for page transitions, form submissions, or dynamic content loading.

    Args:
        text: The text to wait for on the page.
        timeout: Maximum wait time in milliseconds. Default is 5000.

    Returns:
        Status message indicating whether the text was found.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Use Locator API to wait for text
        locator = _session.page.get_by_text(text, exact=False)
        await locator.first.wait_for(state="visible", timeout=timeout)

        return f"Text '{text}' found on page."
    except Exception as e:
        return f"Timeout waiting for text '{text}': {str(e)}"


@tool
async def browser_handle_dialog(action: str = "accept", prompt_text: str = "") -> str:
    """Handle a browser dialog (alert, confirm, or prompt) that is currently open.

    Use this when a dialog appears and blocks page interaction.

    Args:
        action: "accept" to accept the dialog, "dismiss" to dismiss/cancel it. Default is "accept".
        prompt_text: Optional text to enter for prompt dialogs.

    Returns:
        Status message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        # Check if there's an active dialog
        try:
            dialog = await _session.page.wait_for_event("dialog", timeout=500)
        except Exception:
            return "Error: No dialog detected on the page."

        if action == "accept":
            if prompt_text:
                await dialog.accept(prompt_text)
                return f"Dialog accepted with prompt text: '{prompt_text}'"
            else:
                await dialog.accept()
                return "Dialog accepted."
        elif action == "dismiss":
            await dialog.dismiss()
            return "Dialog dismissed."
        else:
            return f"Error: Invalid action '{action}'. Use 'accept' or 'dismiss'."
    except Exception as e:
        return f"Error handling dialog: {str(e)}"


@tool
async def browser_evaluate(script: str) -> str:
    """Execute JavaScript code in the context of the current page and return the result.

    Useful for extracting data, manipulating the DOM, or triggering page behavior
    that isn't accessible through other tools.

    Args:
        script: JavaScript code to execute. Can use 'document', 'window', etc.
               The return value will be serialized and returned.

    Returns:
        The result of the script execution as a string.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        result = await _session.page.evaluate(script)

        # Format result
        if result is None:
            return "Script executed (returned undefined/null)."
        elif isinstance(result, (dict, list)):
            import json
            return json.dumps(result, indent=2, ensure_ascii=False)
        else:
            return str(result)
    except Exception as e:
        return f"Error executing script: {str(e)}"


# ============================================================
# Console 消息和网络请求分析工具
# ============================================================

@tool
async def browser_console_messages(types: str = "", limit: int = 50) -> str:
    """List console messages from the current page since the last navigation.

    Captures console.log, console.warn, console.error, console.info, console.debug
    as well as unhandled page errors.

    Args:
        types: Comma-separated message types to filter. E.g., "error,warn".
               Available: log, warn, error, info, debug, dir, table, trace,
               startGroup, endGroup, assert, count, timeEnd.
               Leave empty to show all types.
        limit: Maximum number of messages to return. Default 50.

    Returns:
        Raw console messages, one per line, with type prefix.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        messages = _session.console_messages

        # Apply type filter
        if types:
            type_set = set(t.strip() for t in types.split(","))
            messages = [m for m in messages if m["type"] in type_set]

        # Apply limit (most recent first)
        messages = messages[-limit:]

        if not messages:
            return "No console messages captured."

        lines = []
        for msg in messages:
            lines.append(f"[{msg['type']}] {msg['text']}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing console messages: {str(e)}"


@tool
async def browser_console_get(msg_id: int) -> str:
    """Get a specific console message by its ID.

    Use browser_console_messages first to list messages and get their IDs.

    Args:
        msg_id: The message ID from browser_console_messages output.

    Returns:
        Full details of the console message.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        if msg_id < 0 or msg_id >= len(_session.console_messages):
            return f"Error: Invalid message ID {msg_id}. Total messages: {len(_session.console_messages)}"

        msg = _session.console_messages[msg_id]
        import json
        return json.dumps(msg, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return f"Error getting console message: {str(e)}"


@tool
async def browser_network_requests(resource_types: str = "", limit: int = 50) -> str:
    """List network requests from the current page since the last navigation.

    Each request shows: id, method, URL, status, resource type.

    Args:
        resource_types: Comma-separated resource types to filter. E.g., "xhr,fetch,document".
               Available: document, stylesheet, image, media, font, script,
               xhr, fetch, websocket, manifest, other.
               Leave empty to show all.
        limit: Maximum number of requests to return. Default 50.

    Returns:
        One request per line: [status] method url (type)
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        requests = _session.network_requests

        # Apply type filter
        if resource_types:
            type_set = set(t.strip() for t in resource_types.split(","))
            requests = [r for r in requests if r.get("resource_type", "other") in type_set]

        # Apply limit
        requests = requests[-limit:]

        if not requests:
            return "No network requests captured."

        lines = []
        for req in requests:
            status = req.get("status", "?")
            method = req.get("method", "?")
            url = req.get("url", "")
            rtype = req.get("resource_type", "other")
            lines.append(f"[{status}] {method} {url} ({rtype})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing network requests: {str(e)}"


@tool
async def browser_network_get(req_id: int) -> str:
    """Get full details of a specific network request by its ID.

    Includes request headers, response headers, status, post data, etc.
    Use browser_network_requests first to list requests and get their IDs.

    Args:
        req_id: The request ID from browser_network_requests output.

    Returns:
        Raw dict of the network request in JSON format.
    """
    try:
        if not _session.page:
            return "Error: No active page. Use browser_navigate first."

        if req_id < 0 or req_id >= len(_session.network_requests):
            return f"Error: Invalid request ID {req_id}. Total requests: {len(_session.network_requests)}"

        req = _session.network_requests[req_id]
        import json
        return json.dumps(req, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return f"Error getting network request: {str(e)}"

        return "\n".join(result)
    except Exception as e:
        return f"Error getting network request: {str(e)}"
