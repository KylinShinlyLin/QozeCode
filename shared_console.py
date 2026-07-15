"""
共享的 Rich Console 实例
所有模块都应该从这里导入 console，确保使用同一个实例
"""
import sys
import os

from rich.console import Console
from rich.progress import TimeElapsedColumn
from rich.text import Text
from datetime import timedelta

# 全局共享的 console 实例
console = Console(
    file=sys.stdout,
    width=None,  # 不限制宽度
    height=None,  # 不限制高度
    force_terminal=True
)

# TUI 模式标志：当 TUI 运行时，禁止 console 直接输出到终端
_tui_mode = False
_null_file = None


def set_tui_mode(enabled: bool = True):
    """切换 TUI 模式。TUI 模式下 console 输出重定向到 /dev/null，
    避免破坏 Textual 界面渲染。"""
    global _tui_mode, _null_file
    _tui_mode = enabled
    if enabled:
        if _null_file is None:
            _null_file = open(os.devnull, "w", encoding="utf-8")
        console.file = _null_file
    else:
        console.file = sys.stdout


def is_tui_mode() -> bool:
    return _tui_mode


class CustomTimeElapsedColumn(TimeElapsedColumn):
    def __init__(self, style: str = "bright_green"):
        super().__init__()
        self.style = style

    def render(self, task: "Task") -> Text:
        """Show time elapsed with custom style."""
        elapsed = task.finished_time if task.finished else task.elapsed
        if elapsed is None:
            return Text("-:--:--", style=self.style)
        delta = timedelta(seconds=max(0, int(elapsed)))
        return Text(str(delta), style=self.style)


# 导出 console 实例
__all__ = ['console', 'set_tui_mode', 'is_tui_mode']
