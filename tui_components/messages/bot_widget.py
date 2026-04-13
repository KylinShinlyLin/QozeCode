# tui_components/messages/bot_widget.py
from textual.app import ComposeResult
from textual.widgets import Static, Markdown
from textual.reactive import reactive

from .types import BotMessage


class BotMessageWidget(Static):
    """AI 回复组件"""
    
    DEFAULT_CSS = """
    BotMessageWidget {
        width: 100%;
        height: auto;
        margin: 1 0;
    }
    
    BotMessageWidget .thinking {
        color: #909090;
        text-style: italic;
        margin-bottom: 1;
    }
    """
    
    content: reactive[str] = reactive("")
    thinking_content: reactive[str] = reactive("")
    
    def __init__(self, message: BotMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.content = message.content
        self.thinking_content = message.thinking_content
    
    def compose(self) -> ComposeResult:
        # 如果初始有 thinking 内容，显示它
        if self.thinking_content:
            yield Static(self.thinking_content, classes="thinking")
        else:
            yield Static("", classes="thinking")
        yield Markdown(self.content)
    
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
        try:
            md = self.query_one(Markdown)
            md.update(new_content)
        except Exception:
            pass
