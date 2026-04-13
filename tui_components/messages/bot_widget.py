# tui_components/messages/bot_widget.py
from textual.app import ComposeResult
from textual.widgets import Static, Markdown
from textual.reactive import reactive
from textual.containers import Vertical
import sys
import os
from datetime import datetime

from .types import BotMessage

# 日志文件路径
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")

def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [BOT_WIDGET] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] {e}", file=sys.stderr)


class BotMessageWidget(Static):
    """AI 回复组件"""

    DEFAULT_CSS = """
    BotMessageWidget {
        width: 100%;
        height: auto;
        margin: 0;
    }

    BotMessageWidget .thinking {
        color: #808080;
        text-style: italic;
        margin: 0;
        padding: 0 0 1 0;
        display: block;
    }

    BotMessageWidget .thinking-content {
        color: #808080;
        text-style: italic;
        margin: 0;
        padding: 0 0 1 0;
    }

    BotMessageWidget > Vertical {
        width: 100%;
        height: auto;
    }
    
    BotMessageWidget Markdown {
        margin: 0;
        padding: 0;
    }
    
    BotMessageWidget Markdown:empty {
        height: 0;
        display: none;
    }
    """

    content: reactive[str] = reactive("")
    thinking_content: reactive[str] = reactive("")

    def __init__(self, message: BotMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._content_buffer = message.content or ""
        self._thinking_buffer = message.thinking_content or ""
        self._last_update = 0
        self._mounted = False  # 标记是否已挂载
        _log(f"init: thinking_content='{self._thinking_buffer[:50] if self._thinking_buffer else 'empty'}'")

    def compose(self) -> ComposeResult:
        _log(f"compose: thinking='{self._thinking_buffer[:50] if self._thinking_buffer else 'empty'}'")
        with Vertical():
            # 使用 Markdown 来显示 thinking，这样可以处理多行
            yield Markdown(self._thinking_buffer or "", classes="thinking", id="thinking-md")
            yield Markdown(self._content_buffer or "", id="content-md")

    def on_mount(self) -> None:
        """组件挂载后调用"""
        self._mounted = True
        # _log(f"on_mount: thinking_buffer len={len(self._thinking_buffer)}")
        # 如果挂载时已有内容，立即更新
        if self._thinking_buffer:
            self._update_thinking_display()
        if self._content_buffer:
            self._update_content_display()

    def _set_thinking(self, thinking: str):
        """更新 thinking 显示"""
        self._thinking_buffer = thinking
        
        _log(f"_set_thinking: len={len(thinking)}, mounted={self._mounted}")
        
        if not self._mounted:
            _log(f"_set_thinking: not mounted yet, skipping DOM update")
            return
            
        self._update_thinking_display()

    def _update_thinking_display(self):
        """实际更新 thinking DOM"""
        try:
            thinking_md = self.query_one("#thinking-md", Markdown)
            # 如果有内容则显示，否则显示空格保持占位
            display_content = self._thinking_buffer if self._thinking_buffer else " "
            thinking_md.update(display_content)
            # _log(f"_update_thinking_display: updated Markdown with {len(self._thinking_buffer)} chars")
        except Exception as e:
            _log(f"_update_thinking_display: ERROR - {e}")

    def _update_content_display(self):
        """实际更新 content DOM"""
        try:
            content_md = self.query_one("#content-md", Markdown)
            content_md.update(self._content_buffer if self._content_buffer else " ")
        except Exception as e:
            _log(f"_update_content_display: ERROR - {e}")

    def watch_thinking_content(self, new_content: str):
        """reactive 属性变化时调用"""
        _log(f"watch_thinking_content: len={len(new_content) if new_content else 0}")
        self._thinking_buffer = new_content
        if self._mounted:
            self._update_thinking_display()

    def watch_content(self, new_content: str):
        """更新 content 内容"""
        self._content_buffer = new_content
        if self._mounted:
            self._update_content_display()

    def append_thinking(self, text: str):
        """追加 thinking 内容"""
        self._thinking_buffer += text
        if self._mounted:
            self._update_thinking_display()

    def append_content(self, text: str):
        """追加 content 内容"""
        self._content_buffer += text
        if self._mounted:
            self._update_content_display()
