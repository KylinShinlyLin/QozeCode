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
from ..terminal_compat import sanitize_display_text

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
    优化：缓存 child widget 引用避免每次更新的 DOM 查询。
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
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
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
        # 缓存的 child widget 引用，避免流式期间反复 query_one
        self._content_static = None
        self._content_md = None
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
        # 缓存 child widget 引用
        try:
            self._content_static = self.query_one("#content-static", Static)
            self._content_md = self.query_one("#content-md", AutoCopyMarkdown)
        except Exception:
            pass
        _log(f"on_mount: content_len={len(self._content_buffer)}")
        if self._content_buffer:
            self._update_content_display()
        # 检测是否为错误消息，应用红色样式
        self._apply_error_style()

    def _update_content_display(self):
        """流式期间更新 Static 显示 — 直接使用缓存的引用，无 DOM 查询开销"""
        try:
            if self._content_static is not None:
                text = sanitize_display_text(self._content_buffer) if self._content_buffer else " "
                self._content_static.update(text)
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
        """流式追加内容 — 仅累积到 buffer，不立即更新显示。

        显示更新由 _update_widget() 在 _flush_update 节流周期内统一处理，
        避免每个 chunk 都触发 Static.update() 导致渲染队列积压。
        """
        self._content_buffer += text

    def finalize(self):
        """流式结束，从 Static 切换到 Markdown 渲染
        
        优化：不再手动 refresh(layout=True)，update() + class toggle 已足够触发重排。
        """
        _log(f"finalize: content_len={len(self._content_buffer)}")
        if not self._mounted:
            return
        try:
            # 使用缓存引用
            if self._content_static is None or self._content_md is None:
                self._content_static = self.query_one("#content-static", Static)
                self._content_md = self.query_one("#content-md", AutoCopyMarkdown)

            text = sanitize_display_text(self._content_buffer) if self._content_buffer else " "
            # 先更新 Markdown 内容，再切换显隐，减少中间帧的布局抖动
            self._content_md.update(text)
            self._content_static.add_class("hidden")
            self._content_md.remove_class("hidden")

            # 检测是否为错误消息，应用红色样式
            self._apply_error_style()
        except Exception as e:
            _log(f"finalize: ERROR - {e}")

    def _apply_error_style(self):
        """检测内容是否为错误消息（以 ❌ 开头），应用红色错误样式"""
        if self._content_buffer and self._content_buffer.strip().startswith("❌"):
            self.add_class("error")
            _log("_apply_error_style: error class added")
