# tui_components/messages/message_list.py
from textual.containers import ScrollableContainer
from textual.widgets import Static
import uuid
import time
import sys
import os
from datetime import datetime

from .types import UserMessage
from .user_widget import UserMessageWidget
from .bot_widget import BotMessageWidget
from .stream_handler import MessageStreamHandler

# 日志文件路径
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")

def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [MSG_LIST] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] {e}", file=sys.stderr)


class ToolResultWidget(Static):
    DEFAULT_CSS = """
    ToolResultWidget {
        width: 100%;
        height: auto;
        margin: 0;
    }
    ToolResultWidget.success { color: #9ece6a; }
    ToolResultWidget.error { color: #f7768e; }
    """

    def __init__(self, display_text: str, is_error: bool = False, elapsed_time: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        display_text = display_text.replace("run:", "command:", 1)
        status_icon = "✗" if is_error else "✓"
        elapsed_str = f" in {elapsed_time:.2f}s" if elapsed_time > 0 else ""
        text = f"{status_icon} {display_text}{elapsed_str}"
        self.update(text)
        if is_error:
            self.add_class("error")
        else:
            self.add_class("success")


class ToolPlaceholderWidget(Static):
    DEFAULT_CSS = """
    ToolPlaceholderWidget {
        width: 100%;
        height: auto;
        margin: 0;
        display: none;
    }
    """

    def __init__(self, tool_id: str, **kwargs):
        self.tool_id = tool_id
        super().__init__(**kwargs)


class MessageList(ScrollableContainer):
    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        background: #13131c;
        padding: 1 2;
        border: none;
        overflow-y: auto;
    }
    """

    def __init__(self, token_callback=None, tool_status_panel=None, **kwargs):
        super().__init__(**kwargs)
        self._token_callback = token_callback
        self._tool_status_panel = tool_status_panel
        self._pending_tools: dict = {}
        self._tool_placeholders: dict = {}
        self._last_scroll_time = 0
        self._scroll_interval = 0.2
        _log(f"init: tool_status_panel={tool_status_panel is not None}")

        self._stream_handler = MessageStreamHandler(
            on_bot_created=self._add_widget,
            on_bot_updated=self._update_widget,
            on_tool_started=self._on_tool_started,
            on_tool_completed=self._on_tool_completed,
            on_stream_complete=self._on_stream_complete
        )

    def add_user_message(self, content: str, is_command: bool = False):
        msg = UserMessage(id=str(uuid.uuid4()), content=content, is_command=is_command)
        widget = UserMessageWidget(msg)
        self.mount(widget)
        self._scroll_to_end()
        return widget

    async def stream_agent_response(self, agent_stream):
        _log("stream_agent_response called")
        try:
            await self._stream_handler.process_stream(agent_stream)
        except Exception as e:
            _log(f"Error: {e}")
            import traceback
            _log(traceback.format_exc())

    def _add_widget(self, widget):
        _log(f"_add_widget: {type(widget).__name__}")
        self.mount(widget)
        self._scroll_to_end()

    def _update_widget(self, widget):
        thinking_len = len(widget._thinking_buffer) if hasattr(widget, '_thinking_buffer') and widget._thinking_buffer else 0
        content_len = len(widget._content_buffer) if hasattr(widget, '_content_buffer') and widget._content_buffer else 0
        _log(f"_update_widget: thinking_len={thinking_len}, content_len={content_len}")
        # 刷新 widget 以确保显示更新
        widget.refresh()
        self._scroll_to_end()

    def _scroll_to_end(self):
        current_time = time.time()
        if current_time - self._last_scroll_time > self._scroll_interval:
            self.scroll_end(animate=False)
            self._last_scroll_time = current_time

    def _on_tool_started(self, tool_id: str, display_text: str):
        _log(f"tool_started: {tool_id[:20]}...")
        self._pending_tools[tool_id] = display_text
        if self._tool_status_panel:
            self._tool_status_panel.add_tool(tool_id, display_text)
        placeholder = ToolPlaceholderWidget(tool_id)
        self._tool_placeholders[tool_id] = placeholder
        self.mount(placeholder)

    def _on_tool_completed(self, tool_id: str, display_text: str, is_error: bool):
        _log(f"tool_completed: {tool_id[:20]}...")
        elapsed_time = 0.0
        if self._tool_status_panel:
            elapsed_time = self._tool_status_panel.remove_tool(tool_id)
        self._pending_tools.pop(tool_id, None)

        widget = ToolResultWidget(
            display_text=display_text,
            is_error=is_error,
            elapsed_time=elapsed_time
        )

        if tool_id in self._tool_placeholders:
            placeholder = self._tool_placeholders.pop(tool_id)
            self.mount(widget, before=placeholder)
            placeholder.remove()
        else:
            self.mount(widget)

        self._scroll_to_end()

    def _on_stream_complete(self, total_tokens: int):
        _log(f"stream_complete: tokens={total_tokens}")
        self.scroll_end(animate=False)
        if self._token_callback:
            self._token_callback(total_tokens)
        for placeholder in self._tool_placeholders.values():
            placeholder.remove()
        self._tool_placeholders.clear()

    def clear_messages(self):
        self.remove_children()
        self._pending_tools.clear()
        self._tool_placeholders.clear()
