# tui_components/messages/user_widget.py
import sys
import os
from datetime import datetime
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical
from .auto_copy_widgets import AutoCopyStatic

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

    注意：内容使用普通属性 _content_buffer 而非 Textual reactive，
    在 super().__init__() 之前完成设置，避免 reactive 初始化时序
    在某些终端上导致中文渲染为 Unicode codepoint 占位符的问题。
    """

    DEFAULT_CSS = """
UserMessageWidget {
    width: 100%;
    height: auto;
    background: #252526;
    border-left: thick #007ACC;
    padding: 1 2;
    margin: 1 0 1 0;
}

UserMessageWidget Vertical {
    width: 100%;
    height: auto;
    margin: 0;
    padding: 0;
}

UserMessageWidget Static {
    color: #c0caf5;
    width: 100%;
    height: auto;
    margin: 0;
    padding: 0;
}
"""

    def __init__(self, message: UserMessage, **kwargs):
        self.message = message
        # 关键修复：在 super().__init__() 之前完成所有属性设置，
        # 避免 Textual 内部 reactive/初始化时序导致渲染问题
        self._content_buffer = _truncate_content(message.content)
        self._mounted = False
        _log(f"__init__: "
             f"full_len={len(message.content) if message.content else 0}, "
             f"display_len={len(self._content_buffer)}, "
             f"truncated={self._content_buffer != message.content}")
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        _log(f"compose: content preview='{self._content_buffer[:30] if self._content_buffer else 'empty'}...'")
        with Vertical():
            yield AutoCopyStatic(self._content_buffer, id="user-content")

    def on_mount(self) -> None:
        self._mounted = True
        _log(f"on_mount: content_len={len(self._content_buffer)}")
        if self._content_buffer:
            self._update_content_display()

    def _update_content_display(self):
        """将 _content_buffer 同步到子 Static 组件"""
        try:
            content_static = self.query_one("#user-content", Static)
            content_static.update(self._content_buffer if self._content_buffer else " ")
        except Exception as e:
            _log(f"_update_content_display: ERROR - {e}")
