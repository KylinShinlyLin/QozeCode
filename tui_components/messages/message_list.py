# tui_components/messages/message_list.py
from textual.containers import ScrollableContainer
from textual.widgets import Static
import uuid
import time

from .types import UserMessage
from .user_widget import UserMessageWidget
from .bot_widget import BotMessageWidget
from .stream_handler import MessageStreamHandler


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
        self._scroll_interval = 0.2  # 滚动节流间隔
        
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
        try:
            await self._stream_handler.process_stream(agent_stream)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _add_widget(self, widget):
        self.mount(widget)
        self._scroll_to_end()

    def _update_widget(self, widget):
        """更新组件 - 节流滚动"""
        self._scroll_to_end()

    def _scroll_to_end(self):
        """滚动到底部 - 节流"""
        current_time = time.time()
        if current_time - self._last_scroll_time > self._scroll_interval:
            self.scroll_end(animate=False)
            self._last_scroll_time = current_time

    def _on_tool_started(self, tool_id: str, display_text: str):
        self._pending_tools[tool_id] = display_text
        if self._tool_status_panel:
            self._tool_status_panel.add_tool(tool_id, display_text)
        placeholder = ToolPlaceholderWidget(tool_id)
        self._tool_placeholders[tool_id] = placeholder
        self.mount(placeholder)
        self._scroll_to_end()

    def _on_tool_completed(self, tool_id: str, display_text: str, is_error: bool):
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
        # 确保最终滚动
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
