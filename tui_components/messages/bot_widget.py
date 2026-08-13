# tui_components/messages/bot_widget.py
from textual.app import ComposeResult
from textual.widgets import Static
from .auto_copy_widgets import AutoCopyStatic, AutoCopyMarkdown
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
    """AI 回复组件 - 流式期间用 Static，结束后切 Markdown。

    正文净化和增量累积由 MessageStreamHandler 的 display buffer 负责；
    widget 只应用已净化的显示快照，并在结束时渲染完整 Markdown。
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

    def __init__(self, message: BotMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._display_text = ""
        self._raw_text = message.content or ""
        self._mounted = False
        self._terminal_received = False
        self._final_view_applied = False
        # 缓存 child widget 引用，避免流式期间反复 query_one
        self._content_static = None
        self._content_md = None
        _log(f"init: content_len={len(self._raw_text)}")

    def compose(self) -> ComposeResult:
        _log(f"compose: content_len={len(self._raw_text)}")
        with Vertical():
            yield AutoCopyStatic(self._display_text or "", id="content-static")
            yield AutoCopyMarkdown(self._display_text or "", id="content-md", classes="hidden")

    def on_mount(self) -> None:
        self._mounted = True
        try:
            self._content_static = self.query_one("#content-static", Static)
            self._content_md = self.query_one("#content-md", AutoCopyMarkdown)
        except Exception:
            pass
        _log(f"on_mount: content_len={len(self._raw_text)}")
        if self._terminal_received:
            self._apply_final_view_once()
        elif self._display_text:
            self._update_content_display()
        self._apply_error_style()

    def _update_content_display(self) -> None:
        """Render the already-sanitized stream snapshot without re-sanitizing it."""
        try:
            if self._content_static is not None:
                self._content_static.update(self._display_text or " ")
        except Exception as e:
            _log(f"_update_content_display: ERROR - {e}")

    def apply_stream_snapshot(
        self, display_text: str, raw_text: str | None = None
    ) -> None:
        """Apply one scheduler-owned, already-sanitized stream snapshot."""
        self._display_text = display_text
        if raw_text is not None:
            self._raw_text = raw_text
        if self._mounted:
            self._update_content_display()

    def set_raw_text(self, raw_text: str) -> None:
        """Store authoritative raw text for terminal styling without rendering."""
        self._raw_text = raw_text

    def finalize(self, final_text: str) -> None:
        """Record terminal state and apply complete Markdown when mounted."""
        self._display_text = final_text
        self._terminal_received = True
        _log(f"finalize: content_len={len(final_text)}")
        self._apply_final_view_once()

    def _apply_final_view_once(self) -> None:
        """Apply terminal Markdown once; pre-mount state remains retryable."""
        if self._final_view_applied or not self._terminal_received or not self._mounted:
            return
        try:
            if self._content_static is None or self._content_md is None:
                self._content_static = self.query_one("#content-static", Static)
                self._content_md = self.query_one("#content-md", AutoCopyMarkdown)

            self._content_md.update(self._display_text or " ")
            self._content_static.add_class("hidden")
            self._content_md.remove_class("hidden")
            self._apply_error_style()
            self._final_view_applied = True
        except Exception as e:
            _log(f"finalize: ERROR - {e}")

    def _apply_error_style(self) -> None:
        """检测内容是否为错误消息（以 ❌ 开头），应用红色错误样式"""
        content = self._raw_text or self._display_text
        if content and content.strip().startswith("❌"):
            self.add_class("error")
            _log("_apply_error_style: error class added")
