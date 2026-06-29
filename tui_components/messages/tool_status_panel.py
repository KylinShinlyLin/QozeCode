# tui_components/messages/tool_status_panel.py
from textual.containers import Vertical
from textual.widgets import Static
from textual.reactive import reactive
from textual.app import ComposeResult
from typing import Dict
from datetime import datetime

from ..tui_constants import SPINNER_FRAMES


class RunningToolItem(Static):
    """单个运行中工具的显示项"""

    DEFAULT_CSS = """
    RunningToolItem {
        width: 100%;
        height: auto;
        color: #7aa2f7;
        text-style: none;
    }
    """

    display_text: reactive[str] = reactive("")

    def __init__(self, tool_id: str, display_text: str, **kwargs):
        self.tool_id = tool_id
        self._start_time = datetime.now()
        self._timer = None
        super().__init__(**kwargs)
        self.display_text = display_text

    def compose(self) -> ComposeResult:
        yield Static(self._render_text())

    def _render_text(self) -> str:
        elapsed = (datetime.now() - self._start_time).total_seconds()
        m, s = divmod(int(elapsed), 60)
        elapsed_str = f"{m:02d}:{s:02d}"
        # 限制显示文本前60个字符
        text = self.display_text
        if len(text) > 50:
            text = text[:47] + "..."
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        return f"{frame} {text} {elapsed_str}"

    def watch_display_text(self, new_text: str):
        """当 display_text 变化时更新"""
        self._update()

    def _update(self):
        """更新显示"""
        try:
            static = self.query_one(Static)
            static.update(self._render_text())
        except Exception:
            pass

    def on_mount(self):
        self._timer = self.set_interval(0.1, self._update)

    def on_unmount(self):
        if self._timer:
            self._timer.stop()
            self._timer = None

    def get_elapsed_time(self) -> float:
        return (datetime.now() - self._start_time).total_seconds()


class ToolStatusPanel(Vertical):
    """工具状态面板 - 显示运行中的工具"""

    DEFAULT_CSS = """
    ToolStatusPanel {
        width: 100%;
        height: auto;
        max-height: 20;
        border-top: solid #414868;
        padding: 0 2;
        display: none;
    }

    ToolStatusPanel.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._running_tools: Dict[str, RunningToolItem] = {}

    def compose(self) -> ComposeResult:
        # 不再显示 "运行中..." header
        yield from ()

    MAX_VISIBLE_TOOLS = 6  # 最多同时显示的工具数

    @staticmethod
    def _extract_tool_name(display_text: str) -> str:
        """从 display_text 中提取稳定工具名用于去重
        例如: "command: date +%Y" → "command", "read_file: utils" → "read_file"
        """
        colon_idx = display_text.find(":")
        if colon_idx > 0:
            return display_text[:colon_idx].strip()
        return display_text.strip()

    def add_tool(self, tool_id: str, display_text: str) -> RunningToolItem:
        """添加或更新运行中的工具
        使用工具名（而非 tool_id）做去重键，解决流式过程中 tool_id 变化导致重复条目的问题
        """
        tool_name = self._extract_tool_name(display_text)

        # 同 tool_id 直接更新（最快路径）
        if tool_id in self._running_tools:
            self._running_tools[tool_id].display_text = display_text
            return self._running_tools[tool_id]

        # 查找同名工具（流式过程中不同 tool_id 但同一工具）
        for tid, item in list(self._running_tools.items()):
            if self._extract_tool_name(item.display_text) == tool_name:
                # 更新 display_text 并重映射 key
                item.display_text = display_text
                del self._running_tools[tid]
                self._running_tools[tool_id] = item
                self.refresh()
                return item

        # 限制最大显示数量，移除最旧的条目
        while len(self._running_tools) >= self.MAX_VISIBLE_TOOLS:
            oldest_id = next(iter(self._running_tools))
            oldest_item = self._running_tools[oldest_id]
            oldest_item.remove()
            del self._running_tools[oldest_id]

        # 显示面板
        self.add_class("visible")
        self.styles.display = "block"

        # 创建并挂载工具项
        item = RunningToolItem(tool_id, display_text)
        self._running_tools[tool_id] = item
        self.mount(item)

        self.refresh()
        return item

    def remove_tool(self, tool_id: str, display_name: str = "") -> float:
        """移除运行中的工具
        Args:
            tool_id: 工具唯一 ID
            display_name: 可选，当精确 ID 匹配失败时用于模糊匹配
        """
        elapsed = 0.0
        if tool_id in self._running_tools:
            item = self._running_tools[tool_id]
            elapsed = item.get_elapsed_time()
            item.remove()
            del self._running_tools[tool_id]
        elif display_name and self._running_tools:
            # 精确 ID 不匹配时，尝试通过显示名称匹配（流式 ID 不一致的兜底）
            for tid, item in list(self._running_tools.items()):
                if item.display_text == display_name:
                    elapsed = item.get_elapsed_time()
                    item.remove()
                    del self._running_tools[tid]
                    break

        # 如果没有运行中的工具，隐藏面板
        if not self._running_tools:
            self.remove_class("visible")
            self.styles.display = "none"

        self.refresh()
        return elapsed

    def clear_all(self):
        for item in self._running_tools.values():
            item.remove()
        self._running_tools.clear()
        self.remove_class("visible")
        self.styles.display = "none"

    def has_tool(self, tool_id: str) -> bool:
        return tool_id in self._running_tools
