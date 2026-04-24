# tui_components/messages/auto_copy_widgets.py
"""
提供带自动复制到剪贴板功能的 Static 和 Markdown 子类。

当用户在组件中选择文本时，会自动将选中的文本内容复制到系统剪贴板，
并通过 toast 通知用户。
"""

import subprocess
import platform

from textual.widgets import Static, Markdown
from textual.selection import Selection
from textual import events


def _copy_text_to_clipboard(text: str) -> bool:
    """将文本复制到系统剪贴板。

    在 macOS 上使用 pbcopy（原生支持，所有终端可用）；
    其他平台使用 Textual 内置的 OSC 52 转义序列。

    Returns:
        True 表示复制成功。
    """
    if platform.system() == "Darwin":
        # macOS: pbcopy 始终可用，不受终端类型限制
        try:
            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
                timeout=3,
            )
            return True
        except Exception:
            return False
    else:
        # Linux / Windows: 依赖终端对 OSC 52 的支持
        # 大多数现代终端（iTerm2, kitty, wezterm, Windows Terminal 等）都支持
        return False  # 让调用方使用 Textual 内置方法


class _AutoCopyMixin:
    """为 Static 和 Markdown 子类提供自动复制能力的混入。"""

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """记录鼠标按下位置，用于判断是否发生了拖拽选择。"""
        self._mouse_down_pos = (event.x, event.y)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """鼠标释放时检查是否有文本被选中，有则复制到剪贴板。"""
        self._check_and_copy()

    def _check_and_copy(self) -> None:
        """检查当前 screen 上是否有文本被选中，有则复制并通知。"""
        try:
            screen = self.screen
            selected_text = screen.get_selected_text()
            if not selected_text or not selected_text.strip():
                return

            copied = _copy_text_to_clipboard(selected_text)
            if not copied:
                # 非 macOS 平台：回退到 Textual 内置方法
                self.app.copy_to_clipboard(selected_text)

            # Toast 提示
            preview = selected_text[:60].replace("\n", " ")
            suffix = "…" if len(selected_text) > 60 else ""
            self.app.notify(
                f"📋 [bold]已复制[/bold]: {preview}{suffix}",
                timeout=2,
            )
        except Exception:
            pass

    def selection_updated(self, selection: Selection | None) -> None:
        """当 Textual 内部选择更新时也触发自动复制（备用路径）。"""
        super().selection_updated(selection)
        if selection is not None:
            try:
                result = self.get_selection(selection)
                if result is not None:
                    text, _ = result
                    if text and text.strip():
                        copied = _copy_text_to_clipboard(text)
                        if not copied:
                            self.app.copy_to_clipboard(text)
                        preview = text[:60].replace("\n", " ")
                        suffix = "…" if len(text) > 60 else ""
                        self.app.notify(
                            f"📋 [bold]已复制[/bold]: {preview}{suffix}",
                            timeout=2,
                        )
            except Exception:
                pass


class AutoCopyStatic(_AutoCopyMixin, Static):
    """Static 组件子类：选中文本后自动复制到系统剪贴板。"""
    pass


class AutoCopyMarkdown(_AutoCopyMixin, Markdown):
    """Markdown 组件子类：选中文本后自动复制到系统剪贴板。"""
    pass
