# tui_components/messages/subagent_widget.py
"""
Subagent 专用消息组件

视觉区分于 BotMessageWidget：
  - 左侧橙色边框 + 暗背景
  - 头部：运行中显示 braille spinner，完成显示 ✅
  - 流式期间 Static 逐 token 更新，结束后切 Markdown
  - 高度自适应内容
"""
import os
from datetime import datetime
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual.reactive import reactive

from .auto_copy_widgets import AutoCopyStatic, AutoCopyMarkdown
from ..tui_constants import SPINNER_FRAMES

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")


def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [SUBAGENT_WIDGET] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


class SubagentWidget(Static):
    """Subagent 消息组件

    头部（纯文本 emoji，无 Rich markup）：
      运行中: `⠋ Subagent · 探索 opencode...`
      完成:   `✅ Subagent · 探索 opencode...`
    """

    DEFAULT_CSS = """
    SubagentWidget {
        width: 100%;
        height: auto;
        min-height: 1;
        background: #1a1b26;
        border-left: thick #e0af68;
        padding: 0 2 0 2;
        margin: 1 0 0 0;
    }

    SubagentWidget > Vertical {
        height: auto;
        min-height: 1;
    }

    SubagentWidget .subagent-header {
        height: auto;
        color: #e0af68;
        text-style: bold;
        margin: 0;
        padding: 0;
    }

    SubagentWidget .subagent-content {
        height: auto;
        min-height: 0;
        color: #a9b1d6;
        margin: 0;
        padding: 0 0 1 0;
    }

    SubagentWidget Markdown {
        height: auto;
        margin: 0;
        padding: 0 0 1 0;
        color: #c0caf5;
    }

    SubagentWidget .hidden {
        display: none;
    }
    """

    content: reactive[str] = reactive("")

    def __init__(self, agent_id: str, label: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.label = label
        self._content_buffer = ""
        self._mounted = False
        self._is_done = False
        self._spinner_frame = 0
        self._timer = None

    # ---------- 生命周期 ----------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield AutoCopyStatic(
                self._render_header(),
                classes="subagent-header",
                id="subagent-header",
            )
            yield AutoCopyStatic("", id="subagent-content-static", classes="subagent-content")
            yield AutoCopyMarkdown("", id="subagent-content-md", classes="hidden")

    def on_mount(self) -> None:
        self._mounted = True
        self._start_timer()
        if self._content_buffer:
            self._update_content_display()

    # ---------- Spinner / Header ----------

    def _render_header(self) -> str:
        if self._is_done:
            return f"✓ Subagent · {self.label}"
        else:
            frame = SPINNER_FRAMES[self._spinner_frame % len(SPINNER_FRAMES)]
            return f"{frame} Subagent · {self.label}"

    def _update_header(self):
        try:
            header = self.query_one("#subagent-header", Static)
            header.update(self._render_header())
        except Exception:
            pass

    def _on_tick(self):
        if self._is_done:
            return
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        self._update_header()

    def _start_timer(self):
        if self._timer is None and self._mounted and not self._is_done:
            self._timer = self.set_interval(0.1, self._on_tick)

    def _stop_timer(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ---------- 内容更新 ----------

    def _update_content_display(self):
        try:
            static = self.query_one("#subagent-content-static", Static)
            static.update(self._content_buffer if self._content_buffer else " ")
        except Exception:
            pass

    def watch_content(self, new_content: str):
        if not new_content and self._content_buffer:
            return
        self._content_buffer = new_content
        if self._mounted:
            self._update_content_display()

    def append_content(self, text: str):
        """流式追加内容（逐 token）"""
        self._content_buffer += text
        if self._mounted:
            self._update_content_display()

    def append_tool(self, tool_name: str, tool_args: str, status: str):
        """追加工具调用信息到内容区"""
        if status == "start":
            args = f"({tool_args})" if tool_args else ""
            line = f"\n🔧 {tool_name}{args}\n"
        else:
            line = ""
        self._content_buffer += line
        if self._mounted:
            self._update_content_display()

    # ---------- 完成 ----------

    def finalize(self):
        """流式结束：停 spinner、切 ✅、Static → Markdown"""
        self._is_done = True
        self._stop_timer()
        self._update_header()

        if not self._mounted:
            return
        try:
            content_static = self.query_one("#subagent-content-static", Static)
            content_md = self.query_one("#subagent-content-md", AutoCopyMarkdown)
            content_static.add_class("hidden")
            content_md.remove_class("hidden")
            content_md.update(self._content_buffer if self._content_buffer else " ")
            self.refresh(layout=True)
        except Exception:
            pass
