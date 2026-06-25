# tui_components/messages/bot_widget.py
from textual.app import ComposeResult
from textual.widgets import Static
from .auto_copy_widgets import AutoCopyStatic, AutoCopyMarkdown
from textual.reactive import reactive
from textual.containers import Vertical
import sys
import os
from datetime import datetime

from .types import BotMessage

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")


_LOG_ENABLED = os.environ.get("QOZE_DEBUG", "") != ""


def _log(msg):
    if not _LOG_ENABLED:
        return
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [BOT_WIDGET] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] {e}", file=sys.stderr)


class BotMessageWidget(Static):
    """AI 回复组件 - 流式期间用 Static，结束后切 Markdown

    注意：thinking 内容已独立为 ThinkingWidget，本组件只展示 content。
    """

    DEFAULT_CSS = """
    BotMessageWidget {
        width: 100%;
        height: auto;
        margin: 0;
    }

    BotMessageWidget > Vertical {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
    }

    BotMessageWidget Static {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
        color: white;
    }

    BotMessageWidget Markdown {
        margin: 0;
        padding: 0;
        color: white;
    }

    BotMessageWidget .hidden {
        display: none;
    }

    /* 错误消息样式 */
    BotMessageWidget.error {
        border-left: solid #f7768e;
    }
    BotMessageWidget.error Static {
        color: #f7768e;
    }
    BotMessageWidget.error Markdown {
        color: #f7768e;
    }
    """

    content: reactive[str] = reactive("")

    def __init__(self, message: BotMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._content_buffer = message.content or ""
        self._last_update = 0
        self._mounted = False
        _log(f"init: content_len={len(self._content_buffer)}")

    def compose(self) -> ComposeResult:
        _log(f"compose: content_len={len(self._content_buffer)}")
        with Vertical():
            # 流式期间显示 Static，结束后隐藏
            yield AutoCopyStatic(self._content_buffer or "", id="content-static")
            # Markdown 初始隐藏，流式结束后显示
            yield AutoCopyMarkdown(self._content_buffer or "", id="content-md", classes="hidden")

    def on_mount(self) -> None:
        self._mounted = True
        _log(f"on_mount: content_len={len(self._content_buffer)}")
        if self._content_buffer:
            self._update_content_display()
        # 检测是否为错误消息，应用红色样式
        self._apply_error_style()

    def _update_content_display(self):
        try:
            content_static = self.query_one("#content-static", Static)
            content_static.update(self._content_buffer if self._content_buffer else " ")
        except Exception as e:
            _log(f"_update_content_display: ERROR - {e}")

    def watch_content(self, new_content: str):
        # 保护：reactive 挂载时初始值为空字符串，不应覆盖流式期间已设置的内容
        if not new_content and self._content_buffer:
            return
        self._content_buffer = new_content
        if self._mounted:
            self._update_content_display()

    def append_content(self, text: str):
        self._content_buffer += text
        if self._mounted:
            self._update_content_display()

    def finalize(self):
        """流式结束，从 Static 切换到 Markdown 渲染"""
        _log(f"finalize: content_len={len(self._content_buffer)}")
        if not self._mounted:
            return
        try:
            content_static = self.query_one("#content-static", Static)
            content_md = self.query_one("#content-md", AutoCopyMarkdown)

            # 隐藏 Static，显示 Markdown
            content_static.add_class("hidden")
            content_md.remove_class("hidden")
            content_md.update(self._content_buffer if self._content_buffer else " ")

            # 触发布局刷新，确保高度重新计算
            self.refresh(layout=True)
            # 检测是否为错误消息，应用红色样式
            self._apply_error_style()
        except Exception as e:
            _log(f"finalize: ERROR - {e}")

    def _apply_error_style(self):
        """检测内容是否为错误消息（以 ❌ 开头），应用红色错误样式"""
        if self._content_buffer and self._content_buffer.strip().startswith("❌"):
            self.add_class("error")
            _log("_apply_error_style: error class added")
