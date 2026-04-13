# tui_components/messages/user_widget.py
from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive

from .types import UserMessage


class UserMessageWidget(Static):
    """用户消息组件"""
    
    DEFAULT_CSS = """
    UserMessageWidget {
        width: 100%;
        height: auto;
        color: #bb9af7;
        text-style: bold;
        margin: 1 0;
    }
    """
    
    content: reactive[str] = reactive("")
    
    def __init__(self, message: UserMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.content = f">>> {message.content}"
    
    def compose(self) -> ComposeResult:
        yield Static(self.content)
    
    def watch_content(self, new_content: str):
        try:
            static = self.query_one(Static)
            static.update(new_content)
        except Exception:
            pass
