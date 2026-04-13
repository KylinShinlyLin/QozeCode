# tui_components/messages/bot_widget.py
from textual.app import ComposeResult
from textual.widgets import Static, Markdown
from textual.reactive import reactive
from textual.containers import Vertical

from .types import BotMessage


class BotMessageWidget(Static):
    """AI 回复组件"""

    DEFAULT_CSS = """
    BotMessageWidget {
        width: 100%;
        height: auto;
        margin: 0;  /* 移除外边距 */
    }

    BotMessageWidget .thinking {
        color: #909090;
        text-style: italic;
        margin: 0;  /* 移除外边距 */
        padding: 0;
    }
    
    BotMessageWidget .thinking:empty {
        display: none;  /* 空内容时不显示 */
    }

    BotMessageWidget > Vertical {
        width: 100%;
        height: auto;
    }
    """

    content: reactive[str] = reactive("")
    thinking_content: reactive[str] = reactive("")

    def __init__(self, message: BotMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.content = message.content
        self.thinking_content = message.thinking_content
        self._content_buffer = message.content
        self._last_update = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            # thinking 内容 - 只有非空时才显示
            if self.thinking_content:
                yield Static(self.thinking_content, classes="thinking")
            # content 内容 - 使用 Markdown
            yield Markdown(self.content if self.content else " ", id="content-md")

    def watch_thinking_content(self, new_content: str):
        """更新 thinking 内容"""
        try:
            thinking_static = self.query_one(".thinking", Static)
            if new_content:
                thinking_static.update(new_content)
        except Exception:
            pass

    def watch_content(self, new_content: str):
        """更新 content 内容"""
        self._content_buffer = new_content
        try:
            md = self.query_one("#content-md", Markdown)
            md.update(new_content)
        except Exception:
            pass
