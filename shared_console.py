"""
共享的 Rich Console 实例
所有模块都应该从这里导入 console，确保使用同一个实例
"""
import sys

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
__all__ = ['console']
