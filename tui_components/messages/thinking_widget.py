# tui_components/messages/thinking_widget.py
"""
ThinkingWidget - 可折叠的思考内容组件

流式期间：收起显示"💭 已思考 xxx 字符 ▸"，展开显示完整思考过程
流式结束：保持可折叠，用户可随时回看
"""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual.reactive import reactive

from .auto_copy_widgets import AutoCopyStatic


class ThinkingWidget(Static):
    """可折叠的思考内容组件

    默认收起，显示字符计数；点击展开显示完整思考过程。
    """

    DEFAULT_CSS = """
    ThinkingWidget {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
    }

    ThinkingWidget > Vertical {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
    }

    ThinkingWidget .thinking-header {
        color: #808080;
        text-style: italic;
        height: auto;
        margin: 0;
        padding: 0;
    }

    ThinkingWidget .thinking-content {
        color: #808080;
        text-style: italic;
        margin: 0;
        padding: 0 0 0 2;
        height: auto;
    }

    ThinkingWidget .hidden {
        display: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._thinking_buffer = ""
        self._collapsed = True
        self._mounted = False
        self._is_finalized = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield AutoCopyStatic(
                "💭 已思考 0 字符 ▸",
                classes="thinking-header",
                id="thinking-header",
            )
            yield AutoCopyStatic(
                "",
                classes="thinking-content hidden",
                id="thinking-content",
            )

    def on_mount(self) -> None:
        self._mounted = True
        if self._thinking_buffer:
            self._update_display()

    # ---------- 公共接口 ----------

    def append_thinking(self, text: str):
        """流式追加思考内容，自动更新字符计数"""
        self._thinking_buffer += text
        if self._mounted:
            self._update_display()

    def finalize(self):
        """流式结束标记，箭头变为 ✓ 表示完成"""
        self._is_finalized = True
        if self._mounted:
            self._update_display()

    @property
    def char_count(self) -> int:
        return len(self._thinking_buffer)

    @property
    def thinking_content(self) -> str:
        return self._thinking_buffer

    # ---------- 内部更新 ----------

    def _update_display(self):
        """刷新头部计数和内容区域"""
        try:
            header = self.query_one("#thinking-header", Static)
            content = self.query_one("#thinking-content", Static)

            count = len(self._thinking_buffer)
            if self._collapsed:
                arrow = "✓" if self._is_finalized else "▸"
            else:
                arrow = "✓" if self._is_finalized else "▾"

            header.update(f"💭 已思考 {count:,} 字符 {arrow}")

            if self._thinking_buffer:
                content.update(self._thinking_buffer)
            else:
                content.update(" ")

            if self._collapsed:
                content.add_class("hidden")
            else:
                content.remove_class("hidden")

            self.refresh(layout=True)
        except Exception:
            pass

    # ---------- 交互 ----------

    def on_click(self, event) -> None:
        """点击切换折叠/展开"""
        event.stop()
        self._collapsed = not self._collapsed
        self._update_display()
