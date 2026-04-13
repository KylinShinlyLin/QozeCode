# tui_components/messages/message_list.py
from textual.containers import ScrollableContainer
from textual.reactive import reactive
import uuid

from .types import UserMessage
from .user_widget import UserMessageWidget
from .bot_widget import BotMessageWidget
from .tool_widget import ToolMessageWidget
from .stream_handler import MessageStreamHandler


class MessageList(ScrollableContainer):
    """消息列表容器 - 管理所有消息组件"""
    
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
    
    def __init__(self, token_callback=None, **kwargs):
        super().__init__(**kwargs)
        self._token_callback = token_callback
        self._stream_handler = MessageStreamHandler(
            on_bot_created=self._add_widget,
            on_bot_updated=self._update_widget,
            on_tool_created=self._add_widget,
            on_tool_updated=self._update_widget,
            on_stream_complete=self._on_stream_complete
        )
    
    def add_user_message(self, content: str, is_command: bool = False) -> UserMessageWidget:
        """添加用户消息"""
        msg = UserMessage(
            id=str(uuid.uuid4()),
            content=content,
            is_command=is_command
        )
        widget = UserMessageWidget(msg)
        self.mount(widget)
        self.scroll_end(animate=False)
        return widget
    
    async def stream_agent_response(self, agent_stream):
        """流式展示 Agent 响应"""
        try:
            await self._stream_handler.process_stream(agent_stream)
        except Exception as e:
            import logging
            logging.error(f"Stream error: {e}", exc_info=True)
            from textual.widgets import Static
            error_widget = Static(f"[Stream Error: {e}]")
            self.mount(error_widget)
            self.scroll_end(animate=False)
    
    def _add_widget(self, widget):
        """添加组件回调"""
        self.mount(widget)
        self.scroll_end(animate=False)
    
    def _update_widget(self, widget):
        """更新组件回调"""
        self.scroll_end(animate=False)
    
    def _on_stream_complete(self, total_tokens: int):
        """流完成回调"""
        if self._token_callback:
            self._token_callback(total_tokens)
    
    def clear_messages(self):
        """清空所有消息"""
        self.remove_children()
