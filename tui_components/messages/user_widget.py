# tui_components/messages/user_widget.py
import sys
import os
from datetime import datetime
from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive

from .types import UserMessage

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")


def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [USER_WIDGET] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


class UserMessageWidget(Static):
    """用户消息组件 - 参考 Kilo CLI 风格设计"""

    DEFAULT_CSS = """
UserMessageWidget {
    width: 100%;
    height: auto;
    background: #252526;  /* RGB(45, 45, 48) */
    border-left: thick #007ACC;
    padding: 1 2;
    margin: 1 0 1 0;
}

UserMessageWidget > Static {
    color: #c0caf5;
    /* text-style removed */
}
"""

    content: reactive[str] = reactive("")

    def __init__(self, message: UserMessage, **kwargs):
        _log(f"__init__: content='{message.content[:30] if message.content else 'empty'}...'")
        super().__init__(**kwargs)
        self.message = message
        self.content = message.content

    def compose(self) -> ComposeResult:
        _log(f"compose: content='{self.content[:30] if self.content else 'empty'}...'")
        yield Static(self.content)

    def watch_content(self, new_content: str):
        try:
            static = self.query_one(Static)
            static.update(new_content)
        except Exception:
            pass
