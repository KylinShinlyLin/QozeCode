# tui_components/messages/auto_copy_widgets.py
"""
提供带自动复制到剪贴板功能的 Static 和 Markdown 子类。

当用户在组件中选择文本时，会自动将选中的文本内容复制到系统剪贴板，
并通过 toast 通知用户。所有复制操作都带 try/except 保护，失败时 toast 提示。
"""

import subprocess
import platform

from textual.widgets import Static, Markdown
from textual.selection import Selection
from textual import events


def _copy_text_to_clipboard(text: str) -> bool:
    """将文本复制到系统剪贴板。

    在 macOS 上使用 pbcopy（原生支持，所有终端可用）；
    其他平台返回 False 让调用方使用 Textual 内置方法。

    Returns:
        True 表示复制成功。
    """
    if platform.system() == "Darwin":
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
        return False


def _safe_notify(app, message: str):
    """安全地弹出 toast，失败不抛异常"""
    try:
        if app is not None:
            app.notify(message, timeout=2)
    except Exception:
        pass


def _safe_copy_to_clipboard(app, text: str) -> bool:
    """安全地调用 Textual 内置剪贴板，失败返回 False"""
    try:
        if app is not None:
            app.copy_to_clipboard(text)
            return True
    except Exception:
        pass
    return False


class _AutoCopyMixin:
    """为 Static 和 Markdown 子类提供自动复制能力的混入。"""

    def on_mouse_down(self, event: events.MouseDown) -> None:
        try:
            self._mouse_down_pos = (event.x, event.y)
        except Exception:
            pass

    def on_mouse_up(self, event: events.MouseUp) -> None:
        try:
            self._check_and_copy()
        except Exception:
            _safe_notify(getattr(self, 'app', None), "⚠️ 复制失败")

    def _check_and_copy(self) -> None:
        """检查当前 screen 上是否有文本被选中，有则复制并通知。"""
        try:
            screen = self.screen
            if screen is None:
                return
            selected_text = screen.get_selected_text()
            if not selected_text or not selected_text.strip():
                return
            self._do_copy(selected_text)
        except Exception:
            _safe_notify(getattr(self, 'app', None), "⚠️ 复制失败")

    def _do_copy(self, text: str) -> None:
        """执行复制 + toast"""
        try:
            copied = _copy_text_to_clipboard(text)
            if not copied:
                copied = _safe_copy_to_clipboard(self.app, text)

            if not copied:
                _safe_notify(self.app, "⚠️ 复制失败，请手动复制")
                return

            preview = text[:60].replace("\n", " ")
            suffix = "…" if len(text) > 60 else ""
            _safe_notify(self.app, f"📋 已复制: {preview}{suffix}")
        except Exception:
            _safe_notify(getattr(self, 'app', None), "⚠️ 复制失败")

    def selection_updated(self, selection: Selection | None) -> None:
        """当 Textual 内部选择更新时也触发自动复制（备用路径）。"""
        try:
            super().selection_updated(selection)
        except Exception:
            pass

        if selection is None:
            return

        try:
            result = self.get_selection(selection)
            if result is not None:
                text, _ = result
                if text and text.strip():
                    self._do_copy(text)
        except Exception:
            _safe_notify(getattr(self, 'app', None), "⚠️ 复制失败")


class AutoCopyStatic(_AutoCopyMixin, Static):
    """Static 组件子类：选中文本后自动复制到系统剪贴板。

    默认关闭 Rich 标记解析，避免内容中的方括号 [...] 被误解析为标记语法导致 MarkupError。
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("markup", False)
        super().__init__(*args, **kwargs)


class AutoCopyMarkdown(_AutoCopyMixin, Markdown):
    """Markdown 组件子类：选中文本后自动复制到系统剪贴板。"""
    pass
