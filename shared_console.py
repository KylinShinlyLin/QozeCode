"""
共享的 Rich Console 实例
所有模块都应该从这里导入 console，确保使用同一个实例
"""

from rich.console import Console

# 全局共享的 console 实例
console = Console(
    width=None,  # 不限制宽度
    height=None,  # 不限制高度
    force_terminal=True,
    legacy_windows=False,
    no_color=False,
    soft_wrap=True  # 允许软换行
)

# 导出 console 实例
__all__ = ['console']