# tui_components/messages/subagent_widget.py
"""
Subagent 专用消息组件

视觉区分于 BotMessageWidget：
  - 左侧橙色边框 + 暗背景
  - 头部：运行中显示 braille spinner，完成显示 ✅
  - 可折叠：默认收起，头部显示 ▸ 箭头；点击展开显示 ▾ 箭头
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
    """Subagent 消息组件 — 可折叠展开

    头部（纯文本 emoji，无 Rich markup）：
       运行中:   `⠋ ▸ Subagent · 探索 opencode...`（收起）/ `⠋ ▾ ...`（展开）
       完成:     `✓ ▸ Subagent · 探索 opencode...`（收起）/ `✓ ▾ ...`（展开）

    默认收起，点击头部切换展开/收起。
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
        height: 1;
        color: #e0af68;
        text-style: bold;
        margin: 0;
        padding: 0;
        overflow: hidden;
        text-overflow: ellipsis;
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
        self._collapsed = True  # 默认收起，与 ThinkingWidget 一致
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
            yield AutoCopyStatic("", id="subagent-content-static", classes="subagent-content hidden")
            yield AutoCopyMarkdown("", id="subagent-content-md", classes="hidden")

    def on_mount(self) -> None:
        self._mounted = True
        self._start_timer()
        if self._content_buffer:
            self._update_content_display()

    # ---------- Spinner / Header ----------

    # 头部标签最大显示字符数（不含前缀 "✓ ▸ Subagent · "）
    _MAX_LABEL_CHARS = 60

    def _render_header(self) -> str:
        """渲染头部文本，包含折叠箭头。
        
        label 可能来自 subagent 的 task 描述，包含换行符。
        此处清洗：去换行、去首尾空白、超长截断加省略号。
        """
        # 清洗 label：换行→空格，合并连续空白，去首尾
        clean = " ".join(self.label.split())
        if len(clean) > self._MAX_LABEL_CHARS:
            clean = clean[:self._MAX_LABEL_CHARS] + "…"
        arrow = "▾" if not self._collapsed else "▸"
        if self._is_done:
            return f"✓ {arrow} Subagent · {clean}"
        else:
            frame = SPINNER_FRAMES[self._spinner_frame % len(SPINNER_FRAMES)]
            return f"{frame} {arrow} Subagent · {clean}"

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

    # ---------- 内容可见性管理 ----------

    def _hide_content(self):
        """隐藏所有内容区域"""
        try:
            static = self.query_one("#subagent-content-static", Static)
            static.add_class("hidden")
        except Exception:
            pass
        try:
            md = self.query_one("#subagent-content-md", AutoCopyMarkdown)
            md.add_class("hidden")
        except Exception:
            pass

    def _show_content(self):
        """显示当前应可见的内容区域（static 或 md，取决于是否已完成）"""
        if self._is_done:
            try:
                md = self.query_one("#subagent-content-md", AutoCopyMarkdown)
                md.remove_class("hidden")
            except Exception:
                pass
            try:
                static = self.query_one("#subagent-content-static", Static)
                static.add_class("hidden")
            except Exception:
                pass
        else:
            try:
                static = self.query_one("#subagent-content-static", Static)
                static.remove_class("hidden")
            except Exception:
                pass
            try:
                md = self.query_one("#subagent-content-md", AutoCopyMarkdown)
                md.add_class("hidden")
            except Exception:
                pass

    # ---------- 内容更新 ----------

    def _update_content_display(self):
        """刷新内容区域，折叠状态下仅更新 buffer 不显示"""
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
        """流式追加内容 — 仅累积到 buffer，不立即更新显示。

        显示更新由 _update_widget() 在调用方节流后统一处理。
        """
        self._content_buffer += text

    def append_tool(self, tool_name: str, tool_args: str, status: str):
        """追加工具调用信息到内容区 — 仅累积，不立即更新显示"""
        if status == "start":
            args = f"({tool_args})" if tool_args else ""
            line = f"\n🔧 {tool_name}{args}\n"
        else:
            line = ""
        self._content_buffer += line

    # ---------- 完成 ----------

    def finalize(self):
        """流式结束：停 spinner、切 ✅、Static → Markdown，保持折叠状态"""
        self._is_done = True
        self._stop_timer()
        self._update_header()

        if not self._mounted:
            return
        try:
            content_static = self.query_one("#subagent-content-static", Static)
            content_md = self.query_one("#subagent-content-md", AutoCopyMarkdown)

            # 始终更新 Markdown 内容
            content_md.update(self._content_buffer if self._content_buffer else " ")

            # 根据折叠状态决定显示哪个以及是否隐藏
            if self._collapsed:
                content_static.add_class("hidden")
                content_md.add_class("hidden")
            else:
                content_static.add_class("hidden")
                content_md.remove_class("hidden")

            self.refresh(layout=True)
        except Exception:
            pass

    # ---------- 交互 ----------

    def on_click(self, event) -> None:
        """点击切换折叠/展开"""
        event.stop()
        self._collapsed = not self._collapsed
        self._update_header()

        if self._collapsed:
            self._hide_content()
        else:
            self._show_content()

        self.refresh(layout=True)
