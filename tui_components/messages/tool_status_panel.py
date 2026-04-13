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
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        return f"{frame} {self.display_text} {elapsed_str}"
    
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
        background: #1a1b26;
        border-top: solid #414868;
        padding: 0 2;
        display: none;
    }
    
    ToolStatusPanel.visible {
        display: block;
    }
    
    ToolStatusPanel Static.header {
        color: #565f89;
        text-style: italic;
        margin-bottom: 1;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._running_tools: Dict[str, RunningToolItem] = {}
    
    def compose(self) -> ComposeResult:
        yield Static("运行中...", classes="header")
    
    def add_tool(self, tool_id: str, display_text: str) -> RunningToolItem:
        """添加或更新运行中的工具"""
        # 如果已存在，更新显示文本
        if tool_id in self._running_tools:
            self._running_tools[tool_id].display_text = display_text
            return self._running_tools[tool_id]
        
        # 显示面板
        self.add_class("visible")
        self.styles.display = "block"
        
        # 创建并挂载工具项
        item = RunningToolItem(tool_id, display_text)
        self._running_tools[tool_id] = item
        
        header = self.query_one(".header", Static)
        self.mount(item, after=header)
        
        self.refresh()
        return item
    
    def remove_tool(self, tool_id: str) -> float:
        """移除运行中的工具"""
        elapsed = 0.0
        if tool_id in self._running_tools:
            item = self._running_tools[tool_id]
            elapsed = item.get_elapsed_time()
            item.remove()
            del self._running_tools[tool_id]
        
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
