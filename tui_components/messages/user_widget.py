# tui_components/messages/user_widget.py
import sys
import os
from datetime import datetime
from textual.app import ComposeResult
from textual.widgets import Static
from .auto_copy_widgets import AutoCopyStatic
from textual.reactive import reactive

from .types import UserMessage

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")

# 用户消息展示的最大行数和最大字符数
MAX_DISPLAY_LINES = 10
MAX_DISPLAY_CHARS = 2000


def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [USER_WIDGET] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


def _truncate_content(content: str, max_lines: int = MAX_DISPLAY_LINES, max_chars: int = MAX_DISPLAY_CHARS) -> str:
    """截断过长内容，避免 TUI 布局爆炸。

    优先按行数截断，再按字符数截断。截断后在末尾追加省略提示。
    保持完整消息内容仍可通过 message.content 访问。

    Args:
        content: 原始内容
        max_lines: 最大展示行数
        max_chars: 最大展示字符数

    Returns:
        截断后的展示内容（可能等于原始内容）
    """
    if not content:
        return content

    lines = content.split('\n')
    total_lines = len(lines)
    total_chars = len(content)

    # 判断是否需要截断
    needs_truncate = total_lines > max_lines or total_chars > max_chars

    if not needs_truncate:
        return content

    # 优先按行截断
    if total_lines > max_lines:
        lines = lines[:max_lines]
        result = '\n'.join(lines)
    else:
        result = content

    # 再按字符截断
    if len(result) > max_chars:
        result = result[:max_chars]

    # 追加省略提示
    omitted_lines = total_lines - max_lines if total_lines > max_lines else 0
    parts = []
    if omitted_lines > 0:
        parts.append(f"{omitted_lines} 行")
    if total_chars > len(result):
        parts.append(f"{total_chars - len(result)} 字符")
    detail = "，".join(parts)
    result += f"\n\n📋 ... (内容过长已省略: {detail})"

    return result


class UserMessageWidget(Static):
    """用户消息组件 - 参考 Kilo CLI 风格设计

    长内容自动截断展示，避免 TUI 布局爆炸。
    完整内容始终保留在 message.content 中供 Agent 使用。
    """

    DEFAULT_CSS = """
UserMessageWidget {
    width: 100%;
    height: auto;
    background: #252526;  /* RGB(45, 45, 48) */
    border-left: thick #007ACC;
    padding: 1 2;
    margin: 1 0 1 0;
}

UserMessageWidget > Static {
    color: #c0caf5;
    /* text-style removed */
}
"""

    content: reactive[str] = reactive("")

    def __init__(self, message: UserMessage, **kwargs):
        display = _truncate_content(message.content)
        _log(f"__init__: "
             f"full_len={len(message.content) if message.content else 0}, "
             f"display_len={len(display)}, "
             f"truncated={display != message.content}")
        super().__init__(**kwargs)
        self.message = message
        self.content = display

    def compose(self) -> ComposeResult:
        _log(f"compose: content preview='{self.content[:30] if self.content else 'empty'}...'")
        yield AutoCopyStatic(self.content)

    def watch_content(self, new_content: str):
        try:
            static = self.query_one(Static)
            static.update(new_content)
        except Exception:
            pass
